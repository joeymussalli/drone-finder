r"""RECALL live demo: the drone camera fills memory while you ask questions.

This ties both halves of RECALL together in ONE process, sharing ONE
ObjectMemory:
  - the ESP32-CAM stream + YOLO-World continuously record what is seen, and
  - pressing A lets you type "where are my keys?" and get an answer from that
    same live memory.

It reuses the already-tested helpers in scripts/camera_recall.py (MjpegStream,
connect_stream, detections_from_result, draw_detection) so there is a single
source of truth for the streaming and detection code.

Before running, connect Windows to the ESP32 Wi-Fi network (DroneCamera).
Run from the repository root:
    .\.venv\Scripts\python.exe -m scripts.recall_demo

For a controlled demo where the whole search view is one known area:
    .\.venv\Scripts\python.exe -m scripts.recall_demo --resolved-location "demo table"

In the video window:
    A  -> type a question directly in the video window (camera pauses briefly)
    M  -> print everything currently remembered
    Q  -> quit (Escape or the window's X button also work)
"""

import argparse
import os
import sys
import textwrap
import time

# Ensure the repository root is importable so ``src`` resolves no matter how
# this script is launched (``-m scripts.recall_demo`` or a direct file path).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.camera_recall import (
    DEFAULT_CAMERA_WEBPAGE,
    DEFAULT_STREAM_URL,
    connect_stream,
    detections_from_result,
    draw_detection,
    print_connection_help,
)
from src.CameraMemoryBridge import CameraMemoryBridge
from src.ObjectMemory import ObjectMemory
from src.QueryService import QueryService

WINDOW_NAME = "RECALL live - A: ask, M: memory, Q: quit"


def window_was_closed(cv2):
    """True if the display window was closed with the X button."""
    try:
        return cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return False


def draw_message_panel(cv2, frame, lines):
    """Draw readable text over the bottom of a copy of the camera frame."""
    display = frame.copy()
    line_height = 28
    panel_height = min(display.shape[0], 24 + line_height * len(lines))
    top = display.shape[0] - panel_height
    cv2.rectangle(display, (0, top), (display.shape[1], display.shape[0]), (0, 0, 0), -1)

    for index, line in enumerate(lines):
        cv2.putText(
            display,
            line,
            (12, top + 25 + index * line_height),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )
    return display


def ask_once(cv2, frame, service: QueryService, memory: ObjectMemory) -> None:
    """Let the user type and submit one question inside the video window."""
    known = memory.all_objects()
    if known:
        hint = "Known objects: " + ", ".join(known)
    else:
        hint = "No objects remembered yet"

    question = ""
    while True:
        prompt_lines = [hint, "Type a question, then press Enter (Esc cancels):"]
        prompt_lines.extend(textwrap.wrap("> " + question, width=70) or ["> "])
        cv2.imshow(WINDOW_NAME, draw_message_panel(cv2, frame, prompt_lines))

        key = cv2.waitKey(50) & 0xFF
        if window_was_closed(cv2) or key == 27:
            return
        if key in (10, 13):
            if question.strip():
                break
            continue
        if key in (8, 127):
            question = question[:-1]
        elif 32 <= key <= 126:
            question += chr(key)

    answer = service.answer_question(question.strip())
    print(f"Question: {question.strip()}")
    print(f"RECALL: {answer}")

    answer_lines = ["RECALL:"]
    answer_lines.extend(textwrap.wrap(answer, width=70))
    answer_lines.append("Press any key to return to the camera.")
    cv2.imshow(WINDOW_NAME, draw_message_panel(cv2, frame, answer_lines))
    cv2.waitKey(0)


def print_memory(memory: ObjectMemory) -> None:
    if not memory.all_objects():
        print("No objects have been remembered yet.")
        return
    print("\nRECALL memory:")
    for object_label in memory.all_objects():
        print(f"- {memory.answer(object_label)}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="RECALL live demo: camera fills memory while you ask questions"
    )
    parser.add_argument("--stream-url", default=DEFAULT_STREAM_URL)
    parser.add_argument("--webpage-url", default=DEFAULT_CAMERA_WEBPAGE)
    parser.add_argument("--connection-attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument("--read-timeout", type=float, default=10.0)
    parser.add_argument("--confidence", type=float, default=0.50)
    parser.add_argument(
        "--resolved-location",
        default=None,
        help=(
            "Known staged area containing the entire camera search view, such as "
            "'demo table'. Leave unset while the drone moves between areas."
        ),
    )
    parser.add_argument(
        "--model",
        default=os.path.join(_REPO_ROOT, "yolov8s-worldv2.pt"),
    )
    parser.add_argument(
        "--objects",
        nargs="+",
        default=["keys", "phone", "glasses", "remote control"],
        help="Object names for YOLO-World to search for",
    )
    args = parser.parse_args()
    if args.connection_attempts < 1:
        parser.error("--connection-attempts must be at least 1")
    if args.retry_delay < 0:
        parser.error("--retry-delay cannot be negative")
    if args.read_timeout <= 0:
        parser.error("--read-timeout must be greater than 0")
    return args


def main():
    args = parse_args()

    try:
        import cv2
        import numpy
    except ImportError:
        print(
            "OpenCV dependencies are missing. Run: "
            ".\\.venv\\Scripts\\python.exe -m pip install -r requirements-camera.txt"
        )
        return 1

    stream, frame = connect_stream(
        cv2,
        numpy,
        args.stream_url,
        args.read_timeout,
        args.connection_attempts,
        args.retry_delay,
    )
    if stream is None:
        print(f"Could not read the ESP32-CAM stream at {args.stream_url}.")
        print_connection_help(args.webpage_url)
        return 1

    frame_height, frame_width = frame.shape[:2]
    print(f"Connected to ESP32-CAM: {frame_width}x{frame_height}")

    try:
        from ultralytics import YOLOWorld
    except ImportError:
        stream.release()
        print(
            "Ultralytics is missing. Run: "
            ".\\.venv\\Scripts\\python.exe -m pip install -r requirements-camera.txt"
        )
        return 1

    print("Loading YOLO-World...")
    model = YOLOWorld(args.model)
    model.set_classes(args.objects)

    # ONE memory, shared by the camera (writer) and the query service (reader).
    memory = ObjectMemory()
    bridge = CameraMemoryBridge(memory=memory, min_confidence=args.confidence)
    service = QueryService(memory)

    print(f"Looking for: {', '.join(args.objects)}")
    if args.resolved_location:
        print(f"Staged location: {args.resolved_location}")
    else:
        print("Location mode: unknown (no world localization supplied)")
    print("In the video window: A = ask, M = memory, Q = quit.")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)

    try:
        while True:
            result = model.predict(frame, conf=args.confidence, verbose=False)[0]
            detections = detections_from_result(result, model)
            # A named location is valid only when the camera's entire search
            # view is deliberately constrained to that staged area.
            sightings = bridge.process_detections(
                detections,
                time.time(),
                resolved_object_location=args.resolved_location,
            )
            for sighting in sightings:
                print(f"Remembered: {sighting!r}")

            for detection in detections:
                draw_detection(cv2, frame, detection)

            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
            if window_was_closed(cv2):
                print("Window closed. Stopping.")
                break
            if key in (ord("a"), ord("A")):
                ask_once(cv2, frame, service, memory)
                # The stream kept producing frames while the question UI was open.
                # Reconnect so queued, stale frames are discarded before flight resumes.
                stream.release()
                stream, frame = connect_stream(
                    cv2,
                    numpy,
                    args.stream_url,
                    args.read_timeout,
                    args.connection_attempts,
                    args.retry_delay,
                )
                if stream is None:
                    print("Could not reconnect after the question.")
                    print_connection_help(args.webpage_url)
                    break
                print("Camera stream resumed. Click the video window for A/M/Q keys.")
                continue
            elif key in (ord("m"), ord("M")):
                print_memory(memory)

            success, frame = stream.read()
            if success:
                continue

            reason = stream.last_error or "unknown stream error"
            print(f"Lost the ESP32-CAM stream: {reason}")
            stream.release()
            stream, frame = connect_stream(
                cv2,
                numpy,
                args.stream_url,
                args.read_timeout,
                args.connection_attempts,
                args.retry_delay,
            )
            if stream is None:
                print("Could not reconnect to the ESP32-CAM stream.")
                print_connection_help(args.webpage_url)
                break
            print("Reconnected to ESP32-CAM.")
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        if stream is not None:
            stream.release()
        cv2.destroyAllWindows()

    print_memory(memory)
    return 0


if __name__ == "__main__":
    sys.exit(main())
