"""Scene-mode sim camera: one photo, smooth continuous views."""

import json

import cv2
import numpy as np

import app.vision.sim_video as sv
from app.vision.sim_video import SimVideoSource


def _make_scene(tmp_path):
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (700, 700, 3), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "scene.jpg"), img)
    (tmp_path / "sim_layout.json").write_text(json.dumps({
        "scene": "scene.jpg", "grid": [7, 7],
        "items": [{"name": "backpack", "cell": [3, 4], "aliases": ["backpack", "bag"]}],
    }))
    return SimVideoSource(str(tmp_path), (0, 0))


def _decode(b):
    return cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)


def test_scene_mode_resolves_items_and_renders(tmp_path):
    src = _make_scene(tmp_path)
    assert src.is_scene
    src.set_query("where is my bag")
    assert src.active_target_cell == (3, 4)
    frame = _decode(src.get_frame((0, 0)))
    assert frame.shape == (720, 960, 3)


def test_camera_glides_instead_of_jumping(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(sv.time, "monotonic", lambda: clock[0])
    src = _make_scene(tmp_path)
    src.takeoff()
    src.get_frame((0, 0))
    for _ in range(40):
        clock[0] += 0.05
        src.get_frame((0, 0))
    assert src.camera_settled
    # Move one cell: right after the move the camera is still gliding...
    clock[0] += 0.1
    src.get_frame((1, 0))
    assert not src.camera_settled
    # ...and it arrives within about a second.
    for _ in range(20):
        clock[0] += 0.05
        src.get_frame((1, 0))
    assert src.camera_settled
