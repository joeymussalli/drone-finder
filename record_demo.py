"""Record demo videos of Drone Finder (sim mode).

Drives the running app in a headless browser and saves one MP4 per search,
plus a combined MP4 of all of them.

Usage (with the server already running via run.bat):
    pip install playwright imageio-ffmpeg
    python -m playwright install chromium
    python record_demo.py

Options:
    python record_demo.py --items "laptop" "backpack"
    python record_demo.py --width 1280 --height 720
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

DEFAULT_ITEMS = ["backpack", "sunglasses", "camera"]


def ffmpeg_path():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def to_mp4(ffmpeg, src: Path, dst: Path):
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(dst)],
        check=True,
    )


def run_search(page, query: str, timeout_s: int, hold_s: float, typing: bool):
    """Run one search in an open page. Returns 'found', 'not found' or 'timeout'."""
    box = page.locator("#query-input")
    box.click()
    box.fill("")
    if typing:
        box.type(query, delay=90)
        page.wait_for_timeout(400)
        page.click("#search-btn")
    else:
        page.get_by_role("button", name=query, exact=True).click()
    try:
        page.wait_for_selector("#result-overlay.on", timeout=timeout_s * 1000)
    except PWTimeout:
        return "timeout"
    heading = page.locator("#result-heading").inner_text().strip().lower()
    page.wait_for_timeout(int(hold_s * 1000))
    return "found" if "found it" in heading else "not found"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--items", nargs="+", default=DEFAULT_ITEMS)
    ap.add_argument("--out", default="demo_videos")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--timeout", type=int, default=180, help="max seconds per search")
    ap.add_argument("--hold", type=float, default=6.0, help="seconds to hold on the result")
    ap.add_argument("--no-warmup", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    raw = out / "_raw"
    raw.mkdir(exist_ok=True)
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        print("ffmpeg not found (pip install imageio-ffmpeg); videos will stay as .webm")

    size = {"width": args.width, "height": args.height}
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch()

        if not args.no_warmup:
            # First search loads the vision model; do it off-camera.
            print("Warm-up search (not recorded)...")
            ctx = browser.new_context(viewport=size)
            page = ctx.new_page()
            page.goto(args.base)
            page.wait_for_timeout(1500)
            print("  warm-up:", run_search(page, args.items[0], args.timeout, 0.5, typing=False))
            ctx.close()

        for i, item in enumerate(args.items, 1):
            print(f"Recording {i}/{len(args.items)}: {item}")
            ctx = browser.new_context(viewport=size, record_video_dir=str(raw), record_video_size=size)
            page = ctx.new_page()
            page.goto(args.base)
            page.wait_for_timeout(2500)  # settle on the idle screen
            t0 = time.time()
            status = run_search(page, item, args.timeout, args.hold, typing=True)
            video = page.video
            ctx.close()  # finalizes the video file
            webm = Path(video.path())
            name = f"{i:02d}_{item.replace(' ', '_')}"
            final = out / f"{name}.webm"
            shutil.move(str(webm), final)
            if ffmpeg:
                mp4 = out / f"{name}.mp4"
                to_mp4(ffmpeg, final, mp4)
                final.unlink()
                final = mp4
            secs = time.time() - t0
            results.append((item, status, final))
            print(f"  -> {status} in {secs:.0f}s, saved {final}")

        browser.close()

    # Combined video of every clip, in order.
    clips = [f for _, _, f in results if f.suffix == ".mp4"]
    if ffmpeg and len(clips) > 1:
        listfile = out / "_concat.txt"
        listfile.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips))
        combined = out / "all_searches.mp4"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(listfile), "-c", "copy", str(combined)], check=True)
        listfile.unlink()
        print(f"Combined video: {combined}")

    shutil.rmtree(raw, ignore_errors=True)
    print("\nSummary:")
    for item, status, f in results:
        print(f"  {item:<14} {status:<10} {f}")
    if any(s != "found" for _, s, _ in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
