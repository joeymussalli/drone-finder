"""Simulation video source -- serves JPEG frames from disk by grid cell.

Two modes, chosen automatically:

1. Manifest mode (preferred for the judge demo): a ``sim_layout.json`` file in
   the images directory maps each searchable item to a photo and a fixed grid
   cell, plus a list of plain room photos. ``set_query(query)`` resolves which
   item the query matches; during the sweep the item photo is served only when
   the drone is on that item's cell, and plain photos fill every other cell.
   This lets several different items live at different spots on the map, and a
   search for one item never false-triggers on another item's photo.

2. Legacy single-target mode (backward compatible): if there is no manifest,
   a single ``target.*`` photo is served on the configured target cell and any
   other images are served as plain photos.
"""

import json
from pathlib import Path
from typing import Optional

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
