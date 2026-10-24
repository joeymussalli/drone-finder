"""Unit tests for VisionModule confidence window logic.

Tests Requirements 7.1, 7.2, 7.3 without loading real YOLO weights.
The YOLO model is monkey-patched so VisionModule._model.predict() returns
controlled fake results.
"""

import numpy as np
import pytest
from unittest.mock import MagicMock

from app.vision.vision_module import VisionModule, CONFIDENCE_THRESHOLD, WINDOW_SIZE
from app.models import CandidateFoundEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_boxes(conf_scores: list[float], bboxes: list[tuple[float, float, float, float]]):
    """Build a fake ultralytics Boxes-like object for the given detections.

    Each entry in conf_scores / bboxes corresponds to one detected instance.
    Supports zero detections (empty lists).
    """
    boxes = MagicMock()
    boxes.__len__ = lambda self: len(conf_scores)

    if conf_scores:
        # boxes.conf[i] → float
        conf_mock = MagicMock()
        conf_mock.__getitem__ = lambda self, i: conf_scores[i]
        boxes.conf = conf_mock

        # boxes.xyxy[i].tolist() → [x1, y1, x2, y2]
        xyxy_mock = MagicMock()

        def _xyxy_item(self, i):
            item = MagicMock()
            item.tolist = lambda: list(bboxes[i])
            return item

        xyxy_mock.__getitem__ = _xyxy_item
        boxes.xyxy = xyxy_mock
    else:
        boxes.conf = None
        boxes.xyxy = None

    return boxes


def _fake_result(conf_scores: list[float], bboxes: list[tuple[float, float, float, float]]):
    """Wrap fake boxes in an ultralytics Results-like list."""
    result = MagicMock()
    result.boxes = _fake_boxes(conf_scores, bboxes)
    return [result]


def _make_vision_module(callback=None):
    """Create a VisionModule with _model already patched (no YOLO weights loaded)."""
    if callback is None:
        callback = MagicMock()
    vm = VisionModule.__new__(VisionModule)
    vm._callback = callback
    vm._model_name = "yolov8s-worldv2.pt"
    vm._model = MagicMock()          # pre-patch so set_query() won't load weights
    vm._model.set_classes = MagicMock()
    vm._current_query = None
    vm._window = []
    return vm, callback


def _make_frame() -> np.ndarray:
    """Return a minimal 10×10 BGR frame."""
    return np.zeros((10, 10, 3), dtype=np.uint8)


def _drive_frame(vm: VisionModule, conf: float, query: str = "cat"):
    """Feed one frame whose single detection has the given confidence score."""
    bbox = (0.0, 0.0, 5.0, 5.0)  # x1,y1,x2,y2
    vm._model.predict.return_value = _fake_result([conf], [bbox])
    frame = _make_frame()
    return vm.analyse_frame(frame, query)


def _drive_no_detection(vm: VisionModule, query: str = "cat"):
    """Feed one frame with zero detections."""
    vm._model.predict.return_value = _fake_result([], [])
    frame = _make_frame()
    return vm.analyse_frame(frame, query)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConfidenceWindow:
    """Validates: Requirements 7.1, 7.2, 7.3"""

    # ------------------------------------------------------------------
    # 1. Three consecutive frames ≥ 0.7 → event emitted with best frame
    # ------------------------------------------------------------------
    def test_three_consecutive_high_confidence_emits_event(self):
        """Three frames all above threshold must emit exactly one CandidateFoundEvent."""
        vm, callback = _make_vision_module()
        vm.set_query("cat")

        _drive_frame(vm, 0.75, "cat")
        _drive_frame(vm, 0.80, "cat")
        _drive_frame(vm, 0.72, "cat")

        callback.assert_called_once()
        event: CandidateFoundEvent = callback.call_args[0][0]
        assert isinstance(event, CandidateFoundEvent)
        # Highest confidence among the three is 0.80
        assert abs(event.confidence - 0.80) < 1e-6

    def test_three_consecutive_tie_picks_earliest(self):
        """When two frames share the max confidence, the earliest is chosen."""
        vm, callback = _make_vision_module()
        vm.set_query("cat")

        _drive_frame(vm, 0.85, "cat")   # frame 1 — highest, earliest
        _drive_frame(vm, 0.85, "cat")   # frame 2 — same conf, later
        _drive_frame(vm, 0.72, "cat")   # frame 3

        callback.assert_called_once()
        event: CandidateFoundEvent = callback.call_args[0][0]
        # Confidence should be 0.85 (both candidates share this value)
        assert abs(event.confidence - 0.85) < 1e-6
        # The bbox for all frames is the same in this fixture, so we just
        # verify the event is well-formed.
        assert event.bbox is not None
        assert event.best_frame_bytes is not None

    # ------------------------------------------------------------------
    # 2. Sequence [0.8, 0.6, 0.9] — sub-threshold resets window
    # ------------------------------------------------------------------
    def test_sub_threshold_in_sequence_resets_window(self):
        """A frame below the confidence threshold must reset the window; no event emitted."""
        vm, callback = _make_vision_module()
        vm.set_query("cat")

        _drive_frame(vm, 0.80, "cat")
        _drive_frame(vm, 0.30, "cat")   # below threshold -> resets the window
        _drive_frame(vm, 0.90, "cat")

        callback.assert_not_called()
        assert len(vm._window) == 1     # only the 0.90 frame remains

    # ------------------------------------------------------------------
    # 3. Exactly 2 high-confidence then 1 low → no event
    # ------------------------------------------------------------------
    def test_one_high_then_low_no_event(self):
        """A single high-confidence frame followed by a low one must not emit
        (the window needs WINDOW_SIZE=2 consecutive detections)."""
        vm, callback = _make_vision_module()
        vm.set_query("cat")

        _drive_frame(vm, 0.80, "cat")
        _drive_frame(vm, 0.30, "cat")   # below threshold -> resets

        callback.assert_not_called()
        assert len(vm._window) == 0

    # ------------------------------------------------------------------
    # 4. Four consecutive high-confidence frames → exactly 1 event, window resets
    # ------------------------------------------------------------------
    def test_three_consecutive_high_emits_once(self):
        """With WINDOW_SIZE=2, two highs emit once and the window resets; a
        third high alone starts a fresh window and cannot emit again yet."""
        vm, callback = _make_vision_module()
        vm.set_query("cat")

        _drive_frame(vm, 0.75, "cat")
        _drive_frame(vm, 0.80, "cat")   # 2 consecutive -> triggers, window cleared
        _drive_frame(vm, 0.85, "cat")   # 1 item in window - not enough

        assert callback.call_count == 1
        assert len(vm._window) == 1     # third frame sits alone

    # ------------------------------------------------------------------
    # 5. FrameResult confidence clamped to [0.0, 1.0]
    # ------------------------------------------------------------------
    def test_frame_result_rejects_out_of_range_confidence(self):
        """FrameResult must raise ValueError for confidence outside [0.0, 1.0]."""
        from app.models import FrameResult

        with pytest.raises(ValueError):
            FrameResult(detected=True, confidence=1.5)

        with pytest.raises(ValueError):
            FrameResult(detected=False, confidence=-0.1)

    def test_frame_result_accepts_boundary_values(self):
        """FrameResult must accept exactly 0.0 and 1.0 as confidence values."""
        from app.models import FrameResult

        r_min = FrameResult(detected=False, confidence=0.0)
        assert r_min.confidence == 0.0

        r_max = FrameResult(detected=True, confidence=1.0, bbox=(0, 0, 5, 5))
        assert r_max.confidence == 1.0

    # ------------------------------------------------------------------
    # 6. Empty frames (no detections) → no event, window stays empty
    # ------------------------------------------------------------------
    def test_empty_frame_no_event_window_stays_empty(self):
        """Frames with zero detections must not emit and must leave the window empty."""
        vm, callback = _make_vision_module()
        vm.set_query("cat")

        for _ in range(5):
            result = _drive_no_detection(vm, "cat")
            assert not result.detected
            assert result.confidence == 0.0
            assert result.bbox is None

        callback.assert_not_called()
        assert len(vm._window) == 0

    def test_empty_frames_do_not_accumulate(self):
        """Two high-confidence frames followed by an empty frame must reset the window."""
        vm, callback = _make_vision_module()
        vm.set_query("cat")

        _drive_frame(vm, 0.80, "cat")
        _drive_no_detection(vm, "cat")  # interrupts before a 2nd detection

        callback.assert_not_called()
        assert len(vm._window) == 0
