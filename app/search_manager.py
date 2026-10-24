"""Search orchestrator for Drone Finder."""

import asyncio
import json
import time
from collections import deque
from typing import Optional

import cv2
import numpy as np

from app.config import AppConfig
from app.drone.interface import DroneInterface, DroneCommandError
from app.llm.interface import LLMInterface, LLMError
from app.models import (
    CandidateFoundEvent, FlightPlan, Move, MoveType, WSMessage, Direction
)
from app.planner.planner import generate_plan
from app.planner.safety_checker import validate
from app.vision.vision_module import VisionModule
from app.vision.sim_video import SimVideoSource


class SearchManager:
    """Central orchestrator for a drone search session."""

    MAX_LOG = 200
    DETECTION_FPS = 2
    RENDER_FPS = 15
    VIDEO_TIMEOUT_S = 3.0
    LLM_TIMEOUT_S = 10.0
    LAND_TIMEOUT_S = 10.0

    def __init__(
        self,
        config: AppConfig,
        drone: DroneInterface,
        llm: LLMInterface,
        vision: VisionModule,
        video_source: Optional[SimVideoSource] = None,
    ) -> None:
        self._config = config
        self._drone = drone
        self._llm = llm
        self._vision = vision
        self._video_source = video_source

        self._ws_clients: set = set()
        self._log_buffer: deque[str] = deque(maxlen=self.MAX_LOG)

        self._search_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        self._last_frame_bytes: Optional[bytes] = None
        self._last_bbox: Optional[tuple[int, int, int, int]] = None
        self._candidate_event: Optional[CandidateFoundEvent] = None
        self._is_searching = False
        self._last_frame_time = time.monotonic()

    # ------------------------------------------------------------------
    # WebSocket client management
    # ------------------------------------------------------------------

    def add_client(self, ws) -> None:
        self._ws_clients.add(ws)

    def remove_client(self, ws) -> None:
        self._ws_clients.discard(ws)

    async def broadcast(self, msg: WSMessage) -> None:
        """Send a WSMessage to all connected WebSocket clients."""
        data = json.dumps({"type": msg.type, "payload": msg.payload})
        dead = set()
        for ws in self._ws_clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    # ------------------------------------------------------------------
    # Status logging
    # ------------------------------------------------------------------

    async def _log(self, message: str, level: str = "status") -> None:
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self._log_buffer.append(entry)
        await self.broadcast(WSMessage(type=level, payload={"message": entry}))

    def get_log_history(self) -> list[str]:
        return list(self._log_buffer)

    # ------------------------------------------------------------------
    # Video frame access
    # ------------------------------------------------------------------

    def get_current_frame(self) -> Optional[bytes]:
        """Return the most recent JPEG frame with bbox overlay (if any)."""
        if self._last_frame_bytes is None:
            return None
        if self._last_bbox is not None:
            # Decode, draw box, re-encode
            buf = np.frombuffer(self._last_frame_bytes, dtype=np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is not None:
                x, y, w, h = self._last_bbox
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                _, enc = cv2.imencode(".jpg", frame)
                return enc.tobytes()
        return self._last_frame_bytes

    def _get_raw_frame(self) -> Optional[bytes]:
        """Pull the next raw frame from the video source."""
        if self._video_source is not None:
            # Sim mode: ask the video source for the frame at the drone's current cell
            from app.drone.sim_adapter import SimDroneAdapter
            if isinstance(self._drone, SimDroneAdapter):
                cell = self._drone.current_cell
            else:
                cell = (0, 0)
            return self._video_source.get_frame(cell)
        # Real mode: pull a JPEG from the ESP32-CAM MJPEG stream
        return self._fetch_esp32cam_frame()

    def _fetch_esp32cam_frame(self) -> Optional[bytes]:
        """Pull a single JPEG frame from the ESP32-CAM MJPEG stream (best-effort).
        
        ESP32-CAM typically streams at http://<address>:81/stream.
        We read enough bytes to extract one JPEG, then return it.
        """
        try:
            import urllib.request
            cam_url = f"http://{self._config.esp32_address}:81/stream"
            req = urllib.request.Request(cam_url)
            with urllib.request.urlopen(req, timeout=1) as resp:
                chunk = resp.read(65536)
            # Extract first complete JPEG (SOI=FFD8 to EOI=FFD9)
            soi = chunk.find(b'\xff\xd8')
            eoi = chunk.find(b'\xff\xd9', soi)
            if soi != -1 and eoi != -1:
                return chunk[soi:eoi + 2]
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Search lifecycle
    # ------------------------------------------------------------------

    async def start(self, query: str) -> None:
        """Start a new search for the given query."""
        if self._is_searching:
            await self._log("A search is already in progress.", "error")
            return

        query = query.strip()
        if not query:
            await self._log("Search query cannot be empty.", "error")
            return

        self._stop_event.clear()
        self._is_searching = True
        self._last_bbox = None
        self._search_task = asyncio.create_task(self._run_search(query))

    async def stop(self) -> None:
        """Stop the current search immediately and land the drone."""
        self._stop_event.set()
        if self._search_task and not self._search_task.done():
            self._search_task.cancel()
            try:
                await self._search_task
            except asyncio.CancelledError:
                pass
        self._is_searching = False
        self._last_bbox = None
        await self._log("Search stopped by user.")
        await self._emergency_land()

    async def _emergency_land(self) -> None:
        """Issue stop then land, with timeout handling."""
        try:
            await asyncio.wait_for(self._drone.stop(), timeout=0.5)
        except (asyncio.TimeoutError, DroneCommandError) as exc:
            await self._log(f"Stop command failed: {exc}", "error")
        try:
            await asyncio.wait_for(self._drone.land(), timeout=self.LAND_TIMEOUT_S)
        except (asyncio.TimeoutError, DroneCommandError) as exc:
            await self._log(f"Land command failed: {exc}", "error")

    # ------------------------------------------------------------------
    # Main search coroutine
    # ------------------------------------------------------------------

    async def _run_search(self, query: str) -> None:
        await self._log(f"Search started: '{query}'")

        # Generate and validate plan
        plan = generate_plan(query, self._config.search_area, self._config.step_size_m)
        result = validate(plan, self._config.search_area)
        if not result.ok:
            await self._log(f"Safety check failed: {result.reason}", "error")
            self._is_searching = False
            self._last_bbox = None
            # Broadcast a failure result so the UI stops "Searching..."
            # and re-enables the command box.
            await self.broadcast(WSMessage(
                type="result",
                payload={"found": False, "message": f"Search could not start: {result.reason}"},
            ))
            return

        # Configure vision for this query
        self._vision.set_query(query)

        # Start frame capture task
        frame_task = asyncio.create_task(self._frame_loop(query))

        try:
            found = await self._execute_plan(plan, query)
        except asyncio.CancelledError:
            frame_task.cancel()
            raise
        except Exception as exc:
            # Any unexpected failure must still reset the UI.
            await self._log(f"Search failed: {exc}", "error")
            self._is_searching = False
            self._last_bbox = None
            await self.broadcast(WSMessage(
                type="result",
                payload={"found": False, "message": f"Search failed: {exc}"},
            ))
            return
        finally:
            frame_task.cancel()
            try:
                await frame_task
            except asyncio.CancelledError:
                pass

        self._is_searching = False
        self._last_bbox = None

        if not found:
            # Completed sweep without finding item
            await self._log("Search complete: item not found.")
            await self.broadcast(WSMessage(
                type="result",
                payload={"found": False, "message": "Item not found after full sweep."}
            ))
            try:
                await asyncio.wait_for(self._drone.land(), timeout=30.0)
            except (asyncio.TimeoutError, DroneCommandError) as exc:
                await self._log(f"Landing failed after sweep: {exc}", "error")

    async def _frame_loop(self, query: str) -> None:
        """Continuously fetch frames and run detection at ~2fps."""
        interval = 1.0 / self.DETECTION_FPS
        last_video_ok = time.monotonic()
        hover_issued = False

        while True:
            raw = self._get_raw_frame()
            now = time.monotonic()

            if raw is None:
                # Video lost check
                if now - last_video_ok > self.VIDEO_TIMEOUT_S:
                    await self._log("Video lost — signal interrupted.", "error")
                    if self._is_searching and not hover_issued:
                        try:
                            await self._drone.hover(5.0)
                        except DroneCommandError:
                            pass
                        hover_issued = True
                await asyncio.sleep(interval)
                continue

            last_video_ok = now
            hover_issued = False
            self._last_frame_time = now
            self._last_frame_bytes = raw

            # Decode to numpy for YOLO
            buf = np.frombuffer(raw, dtype=np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is not None:
                result = self._vision.analyse_frame(frame, query)
                if result.detected:
                    self._last_bbox = result.bbox
                    await self.broadcast(WSMessage(
                        type="detection",
                        payload={
                            "confidence": result.confidence,
                            "bbox": list(result.bbox) if result.bbox else None,
                        }
                    ))
                else:
                    self._last_bbox = None

            await asyncio.sleep(interval)

    async def _execute_plan(self, plan: FlightPlan, query: str) -> bool:
        """Execute moves one by one. Returns True if item was found, False if sweep completed."""
        for move in plan.moves:
            if self._stop_event.is_set():
                return False

            await self._log(f"Move: {move.type.value}" + (
                f" {move.direction.value} {move.distance_m}m" if move.type == MoveType.MOVE else
                f" {move.angle_deg}°" if move.type == MoveType.TURN else
                f" {move.duration_s}s" if move.type == MoveType.HOVER else ""
            ))

            try:
                await self._execute_move(move)
            except DroneCommandError as exc:
                await self._log(f"Drone command failed ({move.type.value}): {exc}", "error")
                await self._emergency_land()
                return False

            await asyncio.sleep(0)  # yield to event loop

            # Check if vision module emitted a candidate while we were moving
            if self._candidate_event is not None:
                event = self._candidate_event
                self._candidate_event = None
                found = await self._handle_candidate(event, query)
                if found:
                    return True

        return False

    async def _execute_move(self, move: Move) -> None:
        """Execute a single move with simulated timing for demo speed."""
        sim_scale = 0.1  # scale down hover/move wait times for demo

        if move.type == MoveType.TAKEOFF:
            await self._drone.takeoff()
        elif move.type == MoveType.LAND:
            await self._drone.land()
        elif move.type == MoveType.STOP:
            await self._drone.stop()
        elif move.type == MoveType.HOVER:
            await self._drone.hover(move.duration_s or 1.0)
            await asyncio.sleep((move.duration_s or 1.0) * sim_scale)
        elif move.type == MoveType.MOVE:
            await self._drone.move(move.direction, move.distance_m or 0.5)
            await asyncio.sleep(0.1)
        elif move.type == MoveType.TURN:
            await self._drone.turn(move.angle_deg or 0.0)
            await asyncio.sleep(0.05)

    async def _handle_candidate(self, event: CandidateFoundEvent, query: str) -> bool:
        """Ask the LLM to confirm a candidate detection. Returns True if confirmed."""
        await self._log(f"Candidate detected (confidence={event.confidence:.2f}) — asking LLM...")
        try:
            confirmed, location = await asyncio.wait_for(
                self._llm.confirm(event.best_frame_bytes, query),
                timeout=self.LLM_TIMEOUT_S,
            )
        except (asyncio.TimeoutError, LLMError) as exc:
            await self._log(f"LLM confirmation timed out or failed: {exc} — resuming search.", "error")
            return False

        await self._log(f"LLM confirmation: {'YES' if confirmed else 'NO'}")

        if confirmed:
            await self._drone.hover(5.0)
            # Try to get a location description
            description = location
            if not description:
                try:
                    description = await asyncio.wait_for(
                        self._llm.describe(event.best_frame_bytes, query),
                        timeout=self.LLM_TIMEOUT_S,
                    )
                except (asyncio.TimeoutError, LLMError):
                    description = "Description unavailable."

            # Encode best frame as base64 for sending to browser
            import base64
            photo_b64 = base64.b64encode(event.best_frame_bytes).decode()

            await self._log(f"Item found: {description}")
            await self.broadcast(WSMessage(
                type="result",
                payload={
                    "found": True,
                    "description": description,
                    "photo": photo_b64,
                }
            ))
            return True

        return False

    def on_candidate_found(self, event: CandidateFoundEvent) -> None:
        """Callback registered with VisionModule — stores event for pickup in plan loop."""
        self._candidate_event = event
