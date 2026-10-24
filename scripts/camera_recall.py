r"""Run RECALL with one Windows USB camera and YOLO-World.

Run from the repository root:
    .\.venv\Scripts\python.exe -m scripts.camera_recall --scan-cameras
    .\.venv\Scripts\python.exe -m scripts.camera_recall --camera-index 0 --check-camera
    .\.venv\Scripts\python.exe -m scripts.camera_recall --camera-index 0

Press M in the video window to print remembered locations. Press Q to quit.
"""

import argparse
import sys
import time

from src.CameraMemoryBridge import CameraMemoryBridge
from src.Detection import Detection
from src.ObjectMemory import ObjectMemory
from src.Zone import Zone


def open_camera(cv2, camera_index):
    """Open one Windows camera through DirectShow."""
    capture = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not capture.isOpened():
        capture.release()
        return None
    return capture


def scan_cameras(cv2, maximum_index=5):
    """Report camera indices that can produce a frame."""
    available = []
    for camera_index in range(maximum_index + 1):
        capture = open_camera(cv2, camera_index)
        if capture is None:
            continue
        success, frame = capture.read()
        capture.release()
        if success and frame is not None:
            height, width = frame.shape[:2]
            available.append(camera_index)
            print(f"Camera index {camera_index}: {width}x{height}")
    if not available:
        print("No readable USB cameras found.")
    return available


def build_zones(frame_width, frame_height):
    """Divide one fixed camera view into left, center, and right zones."""
    one_third = frame_width / 3
    return [
        Zone("left side", 0, 0, one_third, frame_height),
        Zone("center", one_third, 0, 2 * one_third, frame_height),
        Zone("right side", 2 * one_third, 0, frame_width, frame_height),
    ]


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


def draw_zones(cv2, frame, zones):
    for zone in zones:
        cv2.rectangle(
            frame,
            (int(zone.x_min), int(zone.y_min)),
            (int(zone.x_max), int(zone.y_max)),
            (255, 180, 0),
            1,
        )
        cv2.putText(
            frame,
            zone.name,
            (int(zone.x_min) + 8, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 180, 0),
            2,
        )


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
    parser = argparse.ArgumentParser(description="Connect one USB camera to RECALL memory")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--scan-cameras", action="store_true")
    parser.add_argument("--check-camera", action="store_true")
    parser.add_argument("--scan-through-index", type=int, default=5)
    parser.add_argument("--confidence", type=float, default=0.50)
    parser.add_argument("--model", default="yolov8s-worldv2.pt")
    parser.add_argument(
        "--objects",
        nargs="+",
        default=["keys", "phone", "glasses", "remote control"],
        help="Object names for YOLO-World to search for",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        import cv2
    except ImportError:
        print("OpenCV is missing. Run: .\\.venv\\Scripts\\python.exe -m pip install -r requirements-camera.txt")
        return 1

    if args.scan_cameras:
        return 0 if scan_cameras(cv2, args.scan_through_index) else 1

    capture = open_camera(cv2, args.camera_index)
    if capture is None:
        print(
            f"Could not open camera index {args.camera_index}. "
            "Run again with --scan-cameras to find a readable index."
        )
        return 1

    success, frame = capture.read()
    if not success or frame is None:
        capture.release()
        print(f"Camera index {args.camera_index} opened but did not return a frame.")
        return 1

    frame_height, frame_width = frame.shape[:2]
    print(f"Connected to camera index {args.camera_index}: {frame_width}x{frame_height}")

    if args.check_camera:
        capture.release()
        print("Camera check passed. Remove --check-camera to start object detection.")
        return 0

    try:
        from ultralytics import YOLOWorld
    except ImportError:
        capture.release()
        print("Ultralytics is missing. Run: .\\.venv\\Scripts\\python.exe -m pip install -r requirements-camera.txt")
        return 1

    print("Loading YOLO-World. The model weights may download on the first run...")
    model = YOLOWorld(args.model)
    model.set_classes(args.objects)

    memory = ObjectMemory()
    zones = build_zones(frame_width, frame_height)
    bridge = CameraMemoryBridge(
        memory=memory,
        zones=zones,
        min_confidence=args.confidence,
    )

    print(f"Looking for: {', '.join(args.objects)}")
    print("Press M to print memory; press Q to quit.")

    try:
        while True:
            if frame.shape[1] != frame_width or frame.shape[0] != frame_height:
                frame_height, frame_width = frame.shape[:2]
                zones = build_zones(frame_width, frame_height)
                bridge.zones = zones

            result = model.predict(frame, conf=args.confidence, verbose=False)[0]
            detections = detections_from_result(result, model)
            sightings = bridge.process_detections(detections, time.time())

            for sighting in sightings:
                print(f"Remembered: {sighting!r}")

            draw_zones(cv2, frame, zones)
            for detection in detections:
                draw_detection(cv2, frame, detection)

            cv2.imshow("RECALL camera - M: memory, Q: quit", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("m"):
                print_memory(memory)

            success, frame = capture.read()
            if not success or frame is None:
                print("Lost the camera frame stream.")
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()

    print_memory(memory)
    return 0


if __name__ == "__main__":
    sys.exit(main())
