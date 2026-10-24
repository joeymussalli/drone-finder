"""Quick check that the laptop can see the ESP32-CAM stream.

Connect the laptop to the camera's Wi-Fi first, then:
    python camera_check.py
    python camera_check.py --url http://192.168.4.1:81/stream --seconds 10
    python camera_check.py --detect "water bottle"     # also run the vision model

Prints frames per second and resolution, and saves the latest frame to
camera_snapshot.jpg (with a box drawn if --detect finds something).
"""

import argparse
import sys
import time

import cv2
import numpy as np

from app.vision.camera_stream import CameraStreamSource


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://192.168.4.1:81/stream")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--detect", default=None, help="item to look for, e.g. 'water bottle'")
    args = ap.parse_args()

    print(f"Connecting to {args.url} ...")
    cam = CameraStreamSource(args.url)
    deadline = time.monotonic() + 10
    while cam.get_frame() is None and time.monotonic() < deadline:
        time.sleep(0.2)
    if cam.get_frame() is None:
        st = cam.status()
        print("FAIL: no frames received.")
        print(f"  last error: {st['last_error']}")
        print("  Check: laptop is on the DroneCamera Wi-Fi, the URL is right,")
        print("  and the stream isn't already open in a browser tab (the ESP32 serves one viewer at a time).")
        sys.exit(1)

    start_frames = cam.status()["frames"]
    t0 = time.monotonic()
    time.sleep(args.seconds)
    fps = (cam.status()["frames"] - start_frames) / (time.monotonic() - t0)

    jpg = cam.get_frame()
    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    print(f"OK: {w}x{h} at {fps:.1f} fps")

    if args.detect:
        from app.vision.vision_module import VisionModule
        vm = VisionModule(candidate_callback=lambda e: None)
        vm.set_query(args.detect)
        res = vm.analyse_frame(img, args.detect)
        if res.bbox:
            x, y, bw, bh = res.bbox
            cv2.rectangle(img, (x, y), (x + bw, y + bh), (0, 255, 0), 3)
        print(f"Detect '{args.detect}': detected={res.detected} confidence={res.confidence:.2f}")

    cv2.imwrite("camera_snapshot.jpg", img)
    print("Saved camera_snapshot.jpg")
    cam.close()


if __name__ == "__main__":
    main()
