"""Simulation video source -- serves JPEG frames from disk by grid cell.

Two modes, chosen automatically:

1. Manifest mode (preferred for the judge demo): a ``sim_layout.json`` file in
   the images directory maps each searchable item to a photo and a fixed grid
   cell, plus a list of plain room photos. ``set_query(query)`` resolves which
   item the query matches; during the sweep the item photo is served only when
   the drone is on that item's cell, and plain photos fill every other cell.
   This lets several different items live at different spots on the map, and a
   search for one item never false-triggers on another item's photo.

2. Scene mode (used by the demo): the manifest names ONE overhead photo of a
   floor (``"scene"``) and the items that really appear in it. The sim camera
   is a moving window over that photo: it glides smoothly to whichever cell
   the drone is over, so the feed looks like one continuous downward camera
   pass over one room. Whatever the vision model finds is genuinely in the
   frame; nothing is swapped in per cell.

3. Legacy single-target mode (backward compatible): if there is no manifest,
   a single ``target.*`` photo is served on the configured target cell and any
   other images are served as plain photos.
"""

import json
import math
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

_IMAGE_EXTS = (".jpg", ".jpeg", ".png")
_TARGET_STEM = "target"
_MANIFEST = "sim_layout.json"


class SimVideoSource:
    """Serves still photos as a fake video stream for simulation mode."""

    def __init__(self, sim_images_dir: str, target_cell: tuple[int, int]) -> None:
        self._dir = Path(sim_images_dir)
        if not self._dir.is_dir():
            raise FileNotFoundError(f"Sim images directory not found: {sim_images_dir}")

        self._default_target_cell = target_cell
        self._manifest: Optional[dict] = None
        self._items: list[dict] = []          # each: {name, cell, aliases, bytes}
        self._plain: list[bytes] = []
        self._plain_index = 0

        # Active-query state (manifest mode)
        self._active_item: Optional[dict] = None   # resolved from set_query()

        # Legacy state
        self._legacy_target_bytes: Optional[bytes] = None

        # Scene mode state
        self._scene: Optional["_SceneCamera"] = None

        manifest_path = self._dir / _MANIFEST
        if manifest_path.is_file():
            self._load_manifest(manifest_path)
        else:
            self._load_legacy()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _read(self, filename: str) -> bytes:
        p = self._dir / filename
        if not p.is_file():
            raise FileNotFoundError(f"Image referenced in manifest not found: {filename}")
        return p.read_bytes()

    def _load_manifest(self, manifest_path: Path) -> None:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if data.get("scene"):
            self._load_scene(data)
            return
        items = data.get("items", [])
        if not items:
            raise ValueError(f"{_MANIFEST} has no 'items'.")
        for it in items:
            self._items.append({
                "name": it["name"],
                "cell": tuple(it["cell"]),
                "aliases": [a.lower() for a in it.get("aliases", [it["name"]])],
                "bytes": self._read(it["file"]),
            })
        plain_names = data.get("plain", [])
        self._plain = [self._read(n) for n in plain_names]
        if not self._plain:
            # Fall back to using any item photos as plain fillers so the sweep
            # still has something to show; never ideal, but keeps the demo alive.
            self._plain = [it["bytes"] for it in self._items]
        self._manifest = data

    def _load_scene(self, data: dict) -> None:
        scene_path = self._dir / data["scene"]
        if not scene_path.is_file():
            raise FileNotFoundError(f"Scene photo not found: {data['scene']}")
        img = cv2.imread(str(scene_path), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Could not read scene photo: {data['scene']}")
        grid = data.get("grid", [7, 7])
        self._scene = _SceneCamera(img, cols=int(grid[0]), rows=int(grid[1]))
        for it in data.get("items", []):
            self._items.append({
                "name": it["name"],
                "cell": tuple(it["cell"]),
                "aliases": [a.lower() for a in it.get("aliases", [it["name"]])],
                "bytes": None,
            })
        self._manifest = data

    @property
    def is_scene(self) -> bool:
        return self._scene is not None

    def set_grid(self, cols: int, rows: int) -> None:
        """Match the scene camera to the planner's grid."""
        if self._scene is not None:
            self._scene.set_grid(cols, rows)

    def takeoff(self) -> None:
        """Start a new flight: camera back at cell (0,0), rising off the floor."""
        if self._scene is not None:
            self._scene.takeoff()

    def render_current(self) -> Optional[bytes]:
        """Scene mode: the camera view right now (no change of target)."""
        if self._scene is None:
            return None
        return self._scene.render()

    @property
    def camera_settled(self) -> bool:
        """Scene mode: True when the camera has stopped gliding."""
        return self._scene is None or self._scene.settled

    def _load_legacy(self) -> None:
        target_bytes = None
        plain: list[bytes] = []
        for path in sorted(self._dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
                continue
            data = path.read_bytes()
            if path.stem.lower() == _TARGET_STEM:
                target_bytes = data
            else:
                plain.append(data)
        if target_bytes is None:
            raise FileNotFoundError(
                f"No manifest ({_MANIFEST}) and no 'target.*' photo found in {self._dir}."
            )
        if not plain:
            raise FileNotFoundError(
                f"No non-target room photos found in {self._dir}."
            )
        self._legacy_target_bytes = target_bytes
        self._plain = plain

    # ------------------------------------------------------------------
    # Query resolution
    # ------------------------------------------------------------------

    def set_query(self, query: str) -> None:
        """Resolve which item (if any) the query matches. Manifest mode only.

        Matching is case-insensitive and succeeds if the query contains an
        alias or an alias contains the query (so 'my blue water bottle'
        matches the 'water bottle' aliases).
        """
        self._active_item = None
        self._plain_index = 0
        if not self._items:
            return
        q = (query or "").strip().lower()
        if not q:
            return
        best = None
        for item in self._items:
            for alias in item["aliases"]:
                if alias in q or q in alias:
                    # Prefer the longest alias match for specificity.
                    score = len(alias)
                    if best is None or score > best[0]:
                        best = (score, item)
        if best:
            self._active_item = best[1]

    @property
    def active_target_cell(self) -> Optional[tuple[int, int]]:
        """The cell where the current query's item will be found, if resolved."""
        if self._active_item is not None:
            return self._active_item["cell"]
        if self._manifest is None:
            return self._default_target_cell
        return None

    # ------------------------------------------------------------------
    # Frame serving
    # ------------------------------------------------------------------

    def _next_plain(self) -> bytes:
        frame = self._plain[self._plain_index % len(self._plain)]
        self._plain_index += 1
        return frame

    def get_frame(self, cell: tuple[int, int]) -> bytes:
        """Return JPEG bytes for the given grid cell position."""
        cell = tuple(cell)
        if self._scene is not None:
            self._scene.set_target(cell)
            return self._scene.render()
        if self._manifest is not None:
            # Manifest mode: serve the active item's photo only on its cell.
            if self._active_item is not None and cell == self._active_item["cell"]:
                return self._active_item["bytes"]
            return self._next_plain()
        # Legacy single-target mode
        if cell == self._default_target_cell:
            return self._legacy_target_bytes
        return self._next_plain()

    @property
    def target_cell(self) -> tuple[int, int]:
        """Back-compat accessor; prefer active_target_cell."""
        cell = self.active_target_cell
        return cell if cell is not None else self._default_target_cell


class _SceneCamera:
    """A smooth, drone-like downward camera over one overhead photo.

    The drone's grid cell sets where the camera is heading; the view eases
    toward it over ~0.5 s, with a little hover drift, so consecutive frames
    always overlap like a real camera pass. Renders are cached for a few ms
    so the display stream and the detector see the same picture.
    """

    OUT_W, OUT_H = 960, 720
    VIEW_CELLS = 2.0      # view width in cells at cruise altitude
    GLIDE_TAU_S = 0.17    # position smoothing time constant
    CLIMB_TAU_S = 0.45    # takeoff zoom smoothing time constant
    GROUND_ZOOM = 0.55    # view size on the ground relative to cruise
    CACHE_S = 1 / 40

    def __init__(self, img: np.ndarray, cols: int, rows: int) -> None:
        self._lock = threading.Lock()
        h, w = img.shape[:2]
        self._w, self._h = w, h
        self.set_grid(cols, rows)
        # Pad with mirrored floor so views at the edges never show black.
        self._pad = int(max(self._cell_w, self._cell_h) * 1.5)
        self._img = cv2.copyMakeBorder(img, self._pad, self._pad, self._pad, self._pad,
                                       cv2.BORDER_REFLECT_101)
        # Camera look: soft vignette plus a fixed sensor-noise tile.
        yy, xx = np.mgrid[0:self.OUT_H, 0:self.OUT_W].astype(np.float32)
        r = np.sqrt(((xx - self.OUT_W / 2) / (self.OUT_W / 2)) ** 2 +
                    ((yy - self.OUT_H / 2) / (self.OUT_H / 2)) ** 2)
        self._vignette = np.clip(1.0 - 0.28 * r ** 2.2, 0.55, 1.0)[..., None]
        rng = np.random.default_rng(7)
        self._noise = rng.normal(0, 4.0, (self.OUT_H + 64, self.OUT_W + 64, 1)).astype(np.float32)
        self._pos = np.array([0.0, 0.0])
        self._target = np.array([0.0, 0.0])
        self._zoom = self.GROUND_ZOOM
        self._zoom_target = self.GROUND_ZOOM
        self._t = time.monotonic()
        self._t0 = self._t
        self._speed = 0.0
        self._cache: Optional[bytes] = None
        self._cache_t = 0.0

    def set_grid(self, cols: int, rows: int) -> None:
        self._cols, self._rows = max(1, cols), max(1, rows)
        self._cell_w = self._w / self._cols
        self._cell_h = self._h / self._rows

    def takeoff(self) -> None:
        with self._lock:
            self._pos[:] = 0.0
            self._target[:] = 0.0
            self._zoom = self.GROUND_ZOOM
            self._zoom_target = 1.0
            self._t = time.monotonic()
            self._cache = None

    def set_target(self, cell) -> None:
        with self._lock:
            self._target[:] = (float(cell[0]), float(cell[1]))
            self._zoom_target = 1.0

    @property
    def settled(self) -> bool:
        with self._lock:
            return float(np.abs(self._target - self._pos).max()) < 0.04

    def _advance(self, now: float) -> None:
        dt = min(0.25, max(0.0, now - self._t))
        self._t = now
        if dt == 0:
            return
        before = self._pos.copy()
        self._pos += (self._target - self._pos) * (1 - math.exp(-dt / self.GLIDE_TAU_S))
        self._zoom += (self._zoom_target - self._zoom) * (1 - math.exp(-dt / self.CLIMB_TAU_S))
        self._speed = float(np.linalg.norm(self._pos - before)) / dt

    def render(self) -> bytes:
        with self._lock:
            now = time.monotonic()
            if self._cache is not None and now - self._cache_t < self.CACHE_S:
                return self._cache
            self._advance(now)
            t = now - self._t0
            # Centre of view in scene pixels, plus a small hover drift.
            cx = (self._pos[0] + 0.5) * self._cell_w + 0.03 * self._cell_w * math.sin(t * 1.3)
            cy = (self._pos[1] + 0.5) * self._cell_h + 0.03 * self._cell_h * math.sin(t * 0.9 + 1.0)
            view_w = self.VIEW_CELLS * self._cell_w * self._zoom
            scale = self.OUT_W / view_w
            angle = 0.8 * math.sin(t * 0.7)  # degrees of gentle yaw wobble
            m = cv2.getRotationMatrix2D((cx + self._pad, cy + self._pad), angle, scale)
            m[0, 2] += self.OUT_W / 2 - (cx + self._pad)
            m[1, 2] += self.OUT_H / 2 - (cy + self._pad)
            frame = cv2.warpAffine(self._img, m, (self.OUT_W, self.OUT_H),
                                   flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            # Motion blur while gliding, scaled by speed (cells/s).
            k = int(min(9, self._speed * 6))
            if k >= 2:
                d = self._target - self._pos
                kernel = np.zeros((k, k), np.float32)
                if abs(d[0]) >= abs(d[1]):
                    kernel[k // 2, :] = 1.0
                else:
                    kernel[:, k // 2] = 1.0
                frame = cv2.filter2D(frame, -1, kernel / k)
            ox, oy = int(now * 997) % 64, int(now * 613) % 64
            noise = self._noise[oy:oy + self.OUT_H, ox:ox + self.OUT_W]
            out = np.clip(frame.astype(np.float32) * self._vignette + noise, 0, 255).astype(np.uint8)
            ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 82])
            self._cache = enc.tobytes()
            self._cache_t = now
            return self._cache
