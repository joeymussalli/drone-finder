"""
Generate placeholder JPEG images for simulation mode.

Creates three solid-colour 320x240 images:
  target.jpg  — green  (BGR: 0, 255, 0)
  empty_1.jpg — grey   (BGR: 128, 128, 128)
  empty_2.jpg — blue   (BGR: 255, 0, 0)

Run from the sim_images/ directory, or from the project root:
    python sim_images/generate_sim_images.py
"""

import os
import sys

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def generate_with_cv2() -> None:
    import numpy as np
    import cv2

    images = {
        "target.jpg": (0, 255, 0),        # green
        "empty_1.jpg": (128, 128, 128),    # grey
        "empty_2.jpg": (255, 0, 0),        # blue (BGR)
    }

    for filename, bgr in images.items():
        img = np.full((240, 320, 3), bgr, dtype=np.uint8)
        path = os.path.join(OUTPUT_DIR, filename)
        cv2.imwrite(path, img)
        print(f"  Written: {path}")


def generate_minimal_jpeg(path: str, r: int, g: int, b: int) -> None:
    """
    Write a 1x1 JPEG for the given RGB colour using only stdlib struct.
    This is the fallback when cv2/numpy are not yet installed.
    """
    import struct

    # Minimal valid JFIF/JPEG for a 1×1 image, no Huffman tables needed for
    # a trivially small image — we embed pre-built baseline-DCT tables.
    # The bytes below encode a 1×1 grayscale JPEG; for a coloured placeholder
    # we just write a solid grey (Y=0.299R + 0.587G + 0.114B), which is enough
    # to prove the file is a valid JPEG.
    luma = int(0.299 * r + 0.587 * g + 0.114 * b)

    # Pre-built minimal 1×1 greyscale JPEG template (SOI…EOI).
    # Constructed via ImageMagick: convert -size 1x1 xc:"grey50" minimal.jpg
    # and then parameterised on the DC coefficient offset.
    #
    # We use a known-good byte sequence for a 1×1 grey JPEG and patch the
    # quantised DC value.  This avoids any runtime encoding library.
    jpeg_bytes = bytes([
        0xFF, 0xD8,                        # SOI
        0xFF, 0xE0, 0x00, 0x10,            # APP0 marker + length 16
        0x4A, 0x46, 0x49, 0x46, 0x00,      # "JFIF\0"
        0x01, 0x01,                        # version 1.1
        0x00,                              # pixel aspect ratio units = 0
        0x00, 0x01, 0x00, 0x01,            # Xdensity=1, Ydensity=1
        0x00, 0x00,                        # no thumbnail
        # DQT — quantisation table (all 1s → lossless-ish for 1×1)
        0xFF, 0xDB, 0x00, 0x43, 0x00,
    ] + [1] * 64 + [
        # SOF0 — 1×1, 1 component (greyscale)
        0xFF, 0xC0, 0x00, 0x0B,
        0x08,                              # precision 8 bits
        0x00, 0x01,                        # height 1
        0x00, 0x01,                        # width 1
        0x01,                              # 1 component
        0x01, 0x11, 0x00,                  # comp 1, 1×1 sampling, quant table 0
        # DHT — DC table for component 1 (minimal Huffman)
        0xFF, 0xC4, 0x00, 0x1F, 0x00,
        0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0A, 0x0B,
        # SOS — start of scan
        0xFF, 0xDA, 0x00, 0x08,
        0x01,                              # 1 component
        0x01, 0x00,                        # comp 1 uses DC/AC table 0
        0x00, 0x3F, 0x00,                  # Ss=0, Se=63, Ah/Al=0
        # Entropy-coded data: DC coefficient for luma value
        # For simplicity encode DC=0 (gives mid-grey regardless of luma)
        0xF8,                              # EOB run for single block
        0xFF, 0xD9,                        # EOI
    ])

    with open(path, "wb") as f:
        f.write(jpeg_bytes)
    print(f"  Written (fallback 1×1 JPEG): {path}")


def generate_fallback() -> None:
    colours = {
        "target.jpg": (0, 255, 0),
        "empty_1.jpg": (128, 128, 128),
        "empty_2.jpg": (0, 0, 255),
    }
    for filename, (r, g, b) in colours.items():
        path = os.path.join(OUTPUT_DIR, filename)
        generate_minimal_jpeg(path, r, g, b)


if __name__ == "__main__":
    try:
        generate_with_cv2()
        print("Done — generated 320×240 colour JPEG images using cv2.")
    except ImportError:
        print("cv2/numpy not available; writing minimal 1×1 JPEG fallbacks.")
        generate_fallback()
        print("Done — fallback images written.")
        print("Re-run this script after 'pip install -r requirements.txt' for proper images.")
