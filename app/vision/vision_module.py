"""Vision module using YOLO-World for open-vocabulary object detection."""

import numpy as np
import cv2
from typing import Callable, Optional
from ultralytics import YOLOWorld

from app.models import CandidateFoundEvent, FrameResult

CONFIDENCE_THRESHOLD = 0.5
WINDOW_SIZE = 2


class VisionModule:
    """Open-vocabulary object detector using YOLO-World.

    Call set_query(query) before each search to configure the target class.
    Call analyse_frame(frame, query) for each incoming video frame.
    When 2 consecutive frames all detect the target with confidence >= 0.5,
    emits a CandidateFoundEvent via the provided callback.
    """

    def __init__(
        self,
        candidate_callback: Callable[[CandidateFoundEvent], None],
        model_name: str = "yolov8m-worldv2.pt",
    ) -> None:
        self._callback = candidate_callback
        self._model_name = model_name
        self._model: Optional[YOLOWorld] = None  # lazy-loaded on first set_query()
        self._current_query: Optional[str] = None
        self._window: list[tuple[FrameResult, bytes]] = []  # (result, jpeg_bytes)

    def set_query(self, query: str) -> None:
        """Configure the target class. Call once per search before processing frames."""
        if self._model is None:
            self._model = YOLOWorld(self._model_name)
        self._current_query = query
        self._model.set_classes([query])
        self._window.clear()

    def reset(self) -> None:
        """Clear all per-search detection state.

        Clears the confidence window and forces the next analyse_frame() to
        re-apply set_classes() for whatever query is active. Call this at the
        start and end of every search so a window primed by a previous query
        can never carry over into the next one.
        """
        self._window.clear()
        self._current_query = None

    def analyse_frame(self, frame: np.ndarray, query: str) -> FrameResult:
        """Run YOLO-World inference on a single frame.

        Updates the confidence window and fires the candidate callback when
        3 consecutive high-confidence frames are seen.

        Args:
            frame: BGR numpy array from cv2/OpenCV.
            query: The search query (used to reset the model if the query changed).

        Returns:
            FrameResult with detected=True/False, confidence, and bbox if detected.
        """
        # Re-configure if query changed
        if query != self._current_query:
            self.set_query(query)

        results = self._model.predict(frame, verbose=False)

        best_conf = 0.0
        best_bbox: Optional[tuple[int, int, int, int]] = None

        if results and results[0].boxes is not None and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                conf = float(boxes.conf[i])
                if conf > best_conf:
                    best_conf = conf
                    x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                    x, y, w, h = int(x1), int(y1), int(x2 - x1), int(y2 - y1)
                    best_bbox = (x, y, w, h)

        # Clamp confidence to [0.0, 1.0]
        best_conf = max(0.0, min(1.0, best_conf))
        detected = best_conf >= CONFIDENCE_THRESHOLD

        result = FrameResult(
            detected=detected,
            confidence=best_conf,
            bbox=best_bbox if detected else None,
        )

        # Update sliding window
        if detected:
            # Encode frame to JPEG for potential use in CandidateFoundEvent
            _, jpeg_buf = cv2.imencode(".jpg", frame)
            frame_bytes = jpeg_buf.tobytes()
            self._window.append((result, frame_bytes))
            if len(self._window) > WINDOW_SIZE:
                self._window.pop(0)

            if len(self._window) == WINDOW_SIZE:
                self._emit_candidate()
        else:
            # Reset window on any sub-threshold frame
            self._window.clear()

        return result

    def _emit_candidate(self) -> None:
        """Pick the best frame from the window and fire the callback."""
        # Best = highest confidence; on tie, earliest (lowest index)
        best_idx = 0
        best_conf = self._window[0][0].confidence
        for i in range(1, len(self._window)):
            if self._window[i][0].confidence > best_conf:
                best_conf = self._window[i][0].confidence
                best_idx = i

        best_result, best_bytes = self._window[best_idx]
        event = CandidateFoundEvent(
            best_frame_bytes=best_bytes,
            bbox=best_result.bbox,
            confidence=best_result.confidence,
        )
        self._window.clear()  # Reset after emitting
        self._callback(event)


