"""Tests for the MJPEG frame extractor used with the ESP32-CAM."""

import random

from app.vision.camera_stream import CameraStreamSource

BOUNDARY = b"123456789000000000000987654321"


def _jpeg(payload: bytes, thumbnail: bool = False) -> bytes:
    body = payload
    if thumbnail:  # embedded thumbnail: an inner JPEG start/end pair
        body = b"\xff\xd8thumb\xff\xd9" + payload
    return b"\xff\xd8" + body + b"\xff\xd9"


def _stream(frames, with_length=True) -> bytes:
    out = b""
    for f in frames:
        out += b"\r\n--" + BOUNDARY + b"\r\nContent-Type: image/jpeg\r\n"
        if with_length:
            out += b"Content-Length: %d\r\n" % len(f)
        out += b"\r\n" + f
    return out


def _feed(data: bytes, chunk_sizes):
    buf, got = b"", []
    i = 0
    while i < len(data):
        n = next(chunk_sizes)
        buf += data[i:i + n]
        i += n
        newest, buf = CameraStreamSource._extract_frames(buf)
        if newest is not None:
            got.append(newest)
    return got


def test_extracts_frames_with_thumbnails_using_content_length():
    frames = [_jpeg(b"A" * 500, thumbnail=True), _jpeg(b"B" * 300), _jpeg(b"C" * 900, thumbnail=True)]
    rnd = random.Random(0)
    got = _feed(_stream(frames), iter(lambda: rnd.randint(1, 200), None))
    assert got, "no frames extracted"
    for g in got:
        assert g in frames, "every extracted frame must be a complete original frame"
    assert got[-1] == frames[-1]


def test_falls_back_to_markers_without_content_length():
    frames = [_jpeg(b"X" * 400), _jpeg(b"Y" * 250)]
    got = _feed(_stream(frames, with_length=False), iter(lambda: 64, None))
    assert got[-1] == frames[-1]
    assert all(g in frames for g in got)


def test_get_frame_none_when_unreachable():
    cam = CameraStreamSource("http://127.0.0.1:9/stream", connect_timeout_s=0.5)
    try:
        assert cam.get_frame() is None
    finally:
        cam.close()
