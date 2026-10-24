"""Live MJPEG camera source (ESP32-CAM).

The ESP32 CameraWebServer serves a multipart MJPEG stream, usually at
http://192.168.4.1:81/stream. This class keeps one HTTP connection open in a
background thread, pulls JPEG frames out of the stream as they arrive, and
always holds the most recent one. Reconnects automatically if the camera
drops out.

It has the same ``get_frame(cell)`` shape as SimVideoSource so the
SearchManager can use either one. The cell argument is ignored: a real camera
shows whatever it is pointed at.
"""

import threading
import time
import urllib.request
from typing import Optional

_SOI = b"\xff\xd8"   # JPEG start-of-image
_EOI = b"\xff\xd9"   # JPEG end-of-image


class CameraStreamSource:
    """Background reader for an MJPEG-over-HTTP camera stream."""

    STALE_AFTER_S = 2.0      # a frame older than this counts as "no video"
    RECONNECT_DELAY_S = 1.0
    READ_CHUNK = 4096
    MAX_BUFFER = 2_000_000   # drop garbage if no JPEG boundary shows up

    def __init__(self, url: str, connect_timeout_s: float = 5.0) -> None:
        self.url = url
        self._timeout = connect_timeout_s
        self._lock = threading.Lock()
        self._latest: Optional[bytes] = None
        self._latest_time = 0.0
        self._frames = 0
        self._connected = False
        self._last_error: Optional[str] = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="camera-stream", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_frame(self, cell=None) -> Optional[bytes]:
        """Latest JPEG frame, or None if the stream is down or stale."""
        with self._lock:
            if self._latest is None:
                return None
            if time.monotonic() - self._latest_time > self.STALE_AFTER_S:
                return None
            return self._latest

    def status(self) -> dict:
        with self._lock:
            age = time.monotonic() - self._latest_time if self._latest else None
            return {
                "url": self.url,
                "connected": self._connected,
                "frames": self._frames,
                "last_frame_age_s": round(age, 2) if age is not None else None,
                "last_error": self._last_error,
            }

    def close(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------
    # Background reader
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._read_stream()
            except Exception as exc:  # network drop, timeout, bad URL...
                with self._lock:
                    self._connected = False
                    self._last_error = f"{type(exc).__name__}: {exc}"
            self._stop.wait(self.RECONNECT_DELAY_S)

    def _read_stream(self) -> None:
        req = urllib.request.Request(self.url, headers={"User-Agent": "DroneFinder/1.0"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            with self._lock:
                self._connected = True
                self._last_error = None
            buf = b""
            while not self._stop.is_set():
                chunk = resp.read1(self.READ_CHUNK) if hasattr(resp, "read1") else resp.read(self.READ_CHUNK)
                if not chunk:
                    raise ConnectionError("camera stream ended")
                buf += chunk
                newest, buf = self._extract_frames(buf)
                if newest is not None:
                    with self._lock:
                        self._latest = newest
                        self._latest_time = time.monotonic()
                        self._frames += 1
                if len(buf) > self.MAX_BUFFER:
                    buf = b""

    @staticmethod
    def _extract_frames(buf: bytes):
        """Pull every complete JPEG out of buf. Returns (newest_frame, leftover).

        Uses each part's Content-Length header when present (the ESP32 sends
        one), so JPEGs with embedded thumbnails aren't cut short. Falls back to
        scanning for JPEG start/end markers.
        """
        newest = None
        while True:
            start = buf.find(_SOI)
            if start == -1:
                # keep a little tail in case a header is split across reads
                return newest, buf[-256:]
            header = buf[:start]
            length = None
            idx = header.lower().rfind(b"content-length:")
            if idx != -1:
                line_end = header.find(b"\r\n", idx)
                try:
                    length = int(header[idx + 15:line_end if line_end != -1 else None].strip())
                except ValueError:
                    length = None
            if length:
                if len(buf) - start < length:
                    return newest, buf[start - len(header):] if idx != -1 else buf[start:]
                newest = buf[start:start + length]
                buf = buf[start + length:]
                continue
            end = buf.find(_EOI, start + 2)
            if end == -1:
                return newest, buf[start:]
            newest = buf[start:end + 2]
            buf = buf[end + 2:]
