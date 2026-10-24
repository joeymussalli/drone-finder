"""FastAPI application entry point for Drone Finder."""

import asyncio
import json
import sys
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import load_config, ConfigError
from app.drone.sim_adapter import SimDroneAdapter
from app.drone.real_adapter import RealDroneAdapter
from app.llm.claude_adapter import ClaudeAdapter
from app.llm.interface import LLMError, NullLLMAdapter
from app.models import WSMessage
from app.search_manager import SearchManager
from app.vision.sim_video import SimVideoSource
from app.vision.vision_module import VisionModule


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str


# ---------------------------------------------------------------------------
# Application state (module-level, set in lifespan)
# ---------------------------------------------------------------------------

_manager: SearchManager | None = None
_sim_mode: bool = True


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------

def _make_blank_frame() -> bytes:
    """Return a 320x240 grey JPEG frame as a placeholder when no frame is available."""
    frame = np.full((240, 320, 3), 100, dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes()


def _overlay_sim_label(jpeg_bytes: bytes) -> bytes:
    """Draw a persistent 'SIMULATION' text overlay on a JPEG frame."""
    buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None:
        return jpeg_bytes
    # Small corner badge: a compact filled pill with small text so the
    # camera view stays unobstructed.
    label = "SIM"
    scale = 0.5
    thick = 1
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    pad = 5
    x0, y0 = 8, 8
    cv2.rectangle(frame, (x0, y0), (x0 + tw + 2 * pad, y0 + th + 2 * pad), (0, 40, 40), -1)
    cv2.putText(
        frame, label, (x0 + pad, y0 + th + pad - 1),
        cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 255, 255), thick, cv2.LINE_AA,
    )
    _, enc = cv2.imencode(".jpg", frame)
    return enc.tobytes()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _manager, _sim_mode

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"[FATAL] Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    _sim_mode = config.mode.lower() == "sim"

    video_source: SimVideoSource | None = None
    if _sim_mode:
        drone = SimDroneAdapter(log_callback=lambda msg: None)
        video_source = SimVideoSource(
            sim_images_dir=config.sim_images_dir,
            target_cell=config.sim_target_cell,
        )
    else:
        drone = RealDroneAdapter(
            esp32_address=config.esp32_address,
            log_callback=lambda msg: None,
        )
        # video_source stays None; SearchManager._get_raw_frame() will pull
        # from the ESP32-CAM MJPEG URL in real mode (to be implemented).

    # LLM adapter: non-fatal at startup so the sim demo works without an API key.
    try:
        llm = ClaudeAdapter(config)
    except LLMError as exc:
        print(f"[WARNING] LLM not configured: {exc}", file=sys.stderr)
        llm = NullLLMAdapter()

    vision = VisionModule(candidate_callback=lambda event: None)

    manager = SearchManager(
        config=config,
        drone=drone,
        llm=llm,
        vision=vision,
        video_source=video_source,
    )

    vision._callback = manager.on_candidate_found

    async def _drone_log(msg: str) -> None:
        # Raw [SIM]/hardware command lines go to debug so the projector
        # status log stays clean; they remain in the server buffer.
        await manager._log(msg, level="debug")

    drone._log = _drone_log
    _manager = manager

    yield


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Drone Finder", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    """Serve the main UI."""
    return FileResponse("static/index.html")


@app.post("/search")
async def search(req: SearchRequest):
    if not req.query.strip():
        return JSONResponse(status_code=400, content={"error": "Search query cannot be empty."})
    await _manager.start(req.query)
    return {"status": "search started"}


@app.post("/stop")
async def stop():
    await _manager.stop()
    return {"status": "stopped"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _manager.add_client(ws)
    for entry in _manager.get_log_history():
        try:
            await ws.send_text(json.dumps({"type": "status", "payload": {"message": entry}}))
        except Exception:
            break
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _manager.remove_client(ws)


async def _mjpeg_generator():
    interval = 1.0 / 15
    blank = _make_blank_frame()
    while True:
        frame = _manager.get_current_frame() if _manager is not None else None
        if frame is None:
            frame = blank
        if _sim_mode:
            frame = _overlay_sim_label(frame)
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        await asyncio.sleep(interval)


@app.get("/video")
async def video():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# Static assets (CSS, images, etc.) — explicit routes above take precedence
app.mount("/static", StaticFiles(directory="static"), name="static")