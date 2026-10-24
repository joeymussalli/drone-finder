r"""Run RECALL with an ESP32-CAM MJPEG stream and YOLO-World.

Before running, connect Windows to the ESP32 Wi-Fi network (DroneCamera).
Run from the repository root:
    .\.venv\Scripts\python.exe -m scripts.camera_recall --check-camera
    .\.venv\Scripts\python.exe -m scripts.camera_recall

Press M in the video window to print remembered locations. Press Q to quit.
"""

import argparse
import os
import sys
import time
import urllib.request

# Ensure the repository root is importable so ``src`` resolves no matter how
# this script is launched (``-m scripts.camera_recall`` or a direct file path).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.CameraMemoryBridge import CameraMemoryBridge
from src.Detection import Detection
from src.ObjectMemory import ObjectMemory

DEFAULT_CAMERA_WEBPAGE = "http://192.168.4.1/"
DEFAULT_STREAM_URL = "http://192.168.4.1:81/stream"
ESP32_WIFI_NAME = "DroneCamera"
WINDOW_NAME = "RECALL ESP32-CAM - M: memory, Q: quit"


def window_was_closed(cv2):
    """True if the display window was closed with the X button."""
    try:
        return cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        # The window does not exist yet; treat that as "not closed".
        return False


class MjpegStream:
    """Read JPEG frames from an HTTP MJPEG stream and decode them with OpenCV."""

    JPEG_START = b"\xff\xd8"
    JPEG_END = b"\xff\xd9"
    MAX_BUFFER_BYTES = 8 * 1024 * 1024

    def __init__(self, cv2, numpy, url, timeout_seconds=10.0):
        self.cv2 = cv2
        self.numpy = numpy
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.response = None
        self.buffer = bytearray()
        self.last_error = None

    def open(self):
        """Open the HTTP response without waiting for a complete frame."""
        self.release()
        request = urllib.request.Request(
            self.url,
            headers={"User-Agent": "RECALL-ESP32-CAM/1.0"},
        )
        try:
            self.response = urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            )
            self.buffer.clear()
            self.last_error = None
            return True
        except (OSError, ValueError) as error:
            self.last_error = str(error)
            self.response = None
            return False

    def is_opened(self):
        return self.response is not None

    def read(self):
        """Return the next decoded BGR frame as ``(success, frame)``."""
        if self.response is None:
            return False, None

        try:
            while True:
                chunk = self.response.read(4096)
                if not chunk:
                    self.last_error = "the ESP32 closed the HTTP stream"
                    return False, None
                self.buffer.extend(chunk)

                start = self.buffer.find(self.JPEG_START)
                if start < 0:
                    if len(self.buffer) > self.MAX_BUFFER_BYTES:
                        self.buffer = self.buffer[-1:]
                    continue

                end = self.buffer.find(self.JPEG_END, start + 2)
                if end < 0:
                    if len(self.buffer) > self.MAX_BUFFER_BYTES:
                        self.buffer = self.buffer[start:]
                        if len(self.buffer) > self.MAX_BUFFER_BYTES:
                            self.buffer.clear()
                    continue

                jpeg = bytes(self.buffer[start : end + 2])
                del self.buffer[: end + 2]
                encoded = self.numpy.frombuffer(jpeg, dtype=self.numpy.uint8)
                frame = self.cv2.imdecode(encoded, self.cv2.IMREAD_COLOR)
                if frame is not None:
                    self.last_error = None
                    return True, frame
        except Exception as error:
            self.last_error = str(error)
            return False, None

    def release(self):
        if self.response is not None:
            try:
                self.response.close()
            finally:
                self.response = None
        self.buffer.clear()


def connect_stream(cv2, numpy, url, timeout_seconds, attempts, retry_delay):
    """Connect to an MJPEG endpoint and read its first decodable frame."""
    stream = MjpegStream(cv2, numpy, url, timeout_seconds)
    for attempt in range(1, attempts + 1):
        print(f"Connecting to ESP32-CAM stream ({attempt}/{attempts}): {url}")
        if stream.open():
            success, frame = stream.read()
            if success:
                return stream, frame

        reason = stream.last_error or "no decodable JPEG frame was received"
        print(f"Connection attempt failed: {reason}")
        stream.release()
        if attempt < attempts:
            time.sleep(retry_delay)

    return None, None


def print_connection_help(webpage_url):
    print(
        f"Connect Windows to Wi-Fi '{ESP32_WIFI_NAME}', then check {webpage_url} "
        "in a browser. The ESP32 network may correctly show 'No internet'."
    )


def detections_from_result(result, model):
    """Convert Ultralytics xyxy boxes into model-independent Detections."""
    detections = []
    if result.boxes is None:
        return detections

    for box in result.boxes:
        x_min, y_min, x_max, y_max = box.xyxy[0].tolist()
        confidence = float(box.conf[0])
        class_id = int(box.cls[0])
        object_label = model.names[class_id]
        detections.append(
            Detection(
                object_label=object_label,
                confidence=confidence,
                x_min=x_min,
                y_min=y_min,
                x_max=x_max,
                y_max=y_max,
            )
        )
    return detections


def draw_detection(cv2, frame, detection):
    top_left = (int(detection.x_min), int(detection.y_min))
    bottom_right = (int(detection.x_max), int(detection.y_max))
    cv2.rectangle(frame, top_left, bottom_right, (0, 220, 0), 2)
    label = f"{detection.object_label} {detection.confidence:.2f}"
    cv2.putText(
        frame,
        label,
        (top_left[0], max(20, top_left[1] - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 220, 0),
        2,
    )


def print_memory(memory):
    if not memory.all_objects():
        print("No objects have been remembered yet.")
        return
    print("\nRECALL memory:")
    for object_label in memory.all_objects():
        print(f"- {memory.answer(object_label)}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Connect an ESP32-CAM MJPEG stream to RECALL memory"
    )
    parser.add_argument(
        "--stream-url",
        default=DEFAULT_STREAM_URL,
        help=f"ESP32 MJPEG endpoint (default: {DEFAULT_STREAM_URL})",
    )
    parser.add_argument(
        "--webpage-url",
        default=DEFAULT_CAMERA_WEBPAGE,
        help=f"ESP32 diagnostic webpage (default: {DEFAULT_CAMERA_WEBPAGE})",
    )
    parser.add_argument(
        "--check-camera",
        action="store_true",
        help="Read one ESP32 frame without loading the detection model",
    )
    parser.add_argument(
        "--connection-attempts",
        type=int,
        default=3,
        help="Connection/reconnection attempts before exiting (default: 3)",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=2.0,
        help="Seconds between connection attempts (default: 2)",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=10.0,
        help="HTTP connection and frame-read timeout in seconds (default: 10)",
    )
    parser.add_argument("--confidence", type=float, default=0.50)
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

    if args.check_camera:
        stream.release()
        print("Camera check passed. Remove --check-camera to start object detection.")
        return 0

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

    memory = ObjectMemory()
    bridge = CameraMemoryBridge(
        memory=memory,
        min_confidence=args.confidence,
    )

    print(f"Looking for: {', '.join(args.objects)}")
    print("Press M to print memory; press Q or the window's X button to quit.")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)

    try:
        while True:
            result = model.predict(frame, conf=args.confidence, verbose=False)[0]
            detections = detections_from_result(result, model)
            # This standalone stream has no synchronized world localization.
            # Record the detection honestly with an unknown object location.
            sightings = bridge.process_detections(
                detections,
                time.time(),
                resolved_object_location=None,
            )

            for sighting in sightings:
                print(f"Remembered: {sighting!r}")

            for detection in detections:
                draw_detection(cv2, frame, detection)

            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if window_was_closed(cv2):
                print("Window closed. Stopping camera stream.")
                break
            if key == ord("m"):
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
        print("\nStopping camera stream.")
    finally:
        if stream is not None:
            stream.release()
        cv2.destroyAllWindows()

    print_memory(memory)
    return 0


if __name__ == "__main__":
    sys.exit(main())
