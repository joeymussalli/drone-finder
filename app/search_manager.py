"""Search orchestrator for Drone Finder.

Drives both the functional search and the rich virtual-demo narrative:
grid/position/confirming/ai_confirming/result events are broadcast over the
existing WebSocket so the UI can render a top-down map, live detection, a
staged confirmation indicator, and a final pin drop. All demo events are
additive; the real-hardware and sim search paths are unchanged in behaviour.
"""

import asyncio
import base64
import json
import math
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
from app.planner.planner import generate_plan, _grid_dims
from app.planner.safety_checker import validate
from app.vision.vision_module import VisionModule
from app.vision.sim_video import SimVideoSource


class SearchManager:
    """Central orchestrator for a drone search session."""

    MAX_LOG = 200
    DETECTION_FPS = 8
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

        # Grid / demo state
        self._cols, self._rows = _grid_dims(config.search_area, config.step_size_m)
        self._cell: tuple[int, int] = (0, 0)   # authoritative (col, row)
        self._trail: list[list[int]] = []
        self._announced_first_row = False
        # Budget the whole sweep to ~demo_speed_s. Reserve a little time
        # for takeoff/land and the confirmation animation so the TOTAL
        # (not just the cell dwells) lands near the target duration.
        total_cells = max(1, self._cols * self._rows)
        reserved_s = 4.0  # takeoff + land + confirm animation overhead
        budget_s = max(2.0, config.demo_speed_s - reserved_s)
        per_cell = budget_s / total_cells
        # Floor: enough for the 3-frame vision window at DETECTION_FPS.
        min_dwell = 3.5 / self.DETECTION_FPS
        self._cell_dwell_s = max(min_dwell, min(1.0, per_cell))

    @property
    def _sim_mode(self) -> bool:
        return self._video_source is not None

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
    # Grid / position helpers
    # ------------------------------------------------------------------

    def _sync_drone_cell(self) -> None:
        """Push the authoritative cell into the sim adapter so the video
        source serves the photo for the current position."""
        try:
            from app.drone.sim_adapter import SimDroneAdapter
            if isinstance(self._drone, SimDroneAdapter):
                self._drone._cell = self._cell
        except Exception:
            pass

    async def _enter_cell(self, col: int, row: int) -> None:
        """Move the authoritative position to (col,row), extend the trail,
        broadcast a position event, and announce row changes in plain
        language for the status log."""
        prev_row = self._cell[1]
        self._cell = (col, row)
        self._sync_drone_cell()
        if [col, row] not in self._trail:
            self._trail.append([col, row])
        await self.broadcast(WSMessage(
            type="position",
            payload={
                "col": col,
                "row": row,
                "trail": list(self._trail),
            },
        ))
        if row != prev_row or not self._announced_first_row:
            self._announced_first_row = True
            await self._log(f"Scanning row {row + 1} of {self._rows}")

    # ------------------------------------------------------------------
    # Video frame access
    # ------------------------------------------------------------------

    def get_current_frame(self) -> Optional[bytes]:
        """Return the most recent JPEG frame with bbox overlay (if any)."""
        if self._last_frame_bytes is None:
            return None
        if self._last_bbox is not None:
            buf = np.frombuffer(self._last_frame_bytes, dtype=np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is not None:
                x, y, w, h = self._last_bbox
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
                _, enc = cv2.imencode(".jpg", frame)
                return enc.tobytes()
        return self._last_frame_bytes

    def _get_raw_frame(self) -> Optional[bytes]:
        """Pull the next raw frame from the video source."""
        if self._video_source is not None:
            return self._video_source.get_frame(self._cell)
        return self._fetch_esp32cam_frame()

    def _fetch_esp32cam_frame(self) -> Optional[bytes]:
        """Pull a single JPEG frame from the ESP32-CAM MJPEG stream (best-effort)."""
        try:
            import urllib.request
            cam_url = f"http://{self._config.esp32_address}:81/stream"
            req = urllib.request.Request(cam_url)
            with urllib.request.urlopen(req, timeout=1) as resp:
                chunk = resp.read(65536)
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
        self._trail = []
        self._announced_first_row = False
        self._cell = (0, 0)
        self._search_task = asyncio.create_task(self._run_search(query))

    async def stop(self) -> None:
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

        plan = generate_plan(query, self._config.search_area, self._config.step_size_m)
        result = validate(plan, self._config.search_area)
        if not result.ok:
            await self._log(f"Safety check failed: {result.reason}", "error")
            self._is_searching = False
            self._last_bbox = None
            await self.broadcast(WSMessage(
                type="result",
                payload={"found": False, "message": f"Search could not start: {result.reason}"},
            ))
            return

        # Resolve which item this query maps to (manifest-driven sim) so the
        # correct photo appears at the correct cell during the sweep.
        target_cell = None
        if self._sim_mode:
            try:
                self._video_source.set_query(query)
                cell = self._video_source.active_target_cell
                target_cell = list(cell) if cell is not None else None
            except Exception:
                target_cell = list(self._config.sim_target_cell)

        # Tell the UI about the grid up front so it can draw the map.
        await self.broadcast(WSMessage(
            type="grid",
            payload={
                "cols": self._cols,
                "rows": self._rows,
                "sim": self._sim_mode,
                "query": query,
                "target_cell": target_cell,
            },
        ))

        self._vision.set_query(query)
        frame_task = asyncio.create_task(self._frame_loop(query))

        try:
            found = await self._execute_plan(plan, query)
        except asyncio.CancelledError:
            frame_task.cancel()
            raise
        except Exception as exc:
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
        """Continuously fetch frames and run detection."""
        interval = 1.0 / self.DETECTION_FPS
        last_video_ok = time.monotonic()
        hover_issued = False

        while True:
            raw = self._get_raw_frame()
            now = time.monotonic()

            if raw is None:
                if now - last_video_ok > self.VIDEO_TIMEOUT_S:
                    await self._log("Video lost - signal interrupted.", "error")
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
        """Execute moves one by one, tracking grid position for the map.

        Returns True if the item was found, False if the sweep completed.
        """
        for move in plan.moves:
            if self._stop_event.is_set():
                return False

            await self._log("Move: " + move.type.value + (
                f" {move.direction.value} {move.distance_m}m" if move.type == MoveType.MOVE else
                f" {move.angle_deg} deg" if move.type == MoveType.TURN else
                f" {move.duration_s}s" if move.type == MoveType.HOVER else ""
            ), level="debug")

            try:
                await self._execute_move(move, query)
            except DroneCommandError as exc:
                await self._log(f"Drone command failed ({move.type.value}): {exc}", "error")
                await self._emergency_land()
                return False

            await asyncio.sleep(0)

            if self._candidate_event is not None:
                event = self._candidate_event
                self._candidate_event = None
                found = await self._handle_candidate(event, query)
                if found:
                    return True

        return False

    async def _execute_move(self, move: Move, query: str) -> None:
        """Execute a single move, updating the authoritative grid cell and
        pacing to the configured demo speed."""
        if move.type == MoveType.TAKEOFF:
            await self._drone.takeoff()
            await self._enter_cell(0, 0)
            # Short, fixed takeoff beat (not part of the per-cell budget).
            await asyncio.sleep(0.4)
        elif move.type == MoveType.LAND:
            await self._drone.land()
        elif move.type == MoveType.STOP:
            await self._drone.stop()
        elif move.type == MoveType.HOVER:
            await self._drone.hover(move.duration_s or 1.0)
            # The per-cell time budget lives here: dwell so the camera
            # "captures" the cell and the viewer can follow along.
            await asyncio.sleep(self._cell_dwell_s)
        elif move.type == MoveType.MOVE:
            await self._drone.move(move.direction, move.distance_m or 0.5)
            col, row = self._cell
            if move.direction == Direction.RIGHT:
                col += 1
            elif move.direction == Direction.LEFT:
                col -= 1
            elif move.direction == Direction.FORWARD:
                row += 1
            elif move.direction == Direction.BACKWARD:
                row -= 1
            await self._enter_cell(col, row)
            await asyncio.sleep(0.05)  # near-instant hop; budget is in the hover
        elif move.type == MoveType.TURN:
            await self._drone.turn(move.angle_deg or 0.0)

    async def _handle_candidate(self, event: CandidateFoundEvent, query: str) -> bool:
        """Run the staged confirmation narrative, confirm, then reveal the find."""
        from app.llm.interface import NullLLMAdapter
        have_llm = not isinstance(self._llm, NullLLMAdapter)

        # Staged "confirming 1/3 -> 2/3 -> 3/3" indicator, paced so the audience
        # can read each step.
        for stage in (1, 2, 3):
            await self.broadcast(WSMessage(
                type="confirming",
                payload={"stage": stage, "of": 3, "confidence": event.confidence},
            ))
            await self._log(f"Spotted candidate - confirming {stage}/3 (confidence {event.confidence:.2f})")
            await asyncio.sleep(0.7)

        confirmed = True
        location = ""
        if have_llm:
            # Real LLM: show the "AI confirming..." step and call it.
            await self.broadcast(WSMessage(type="ai_confirming", payload={"query": query}))
            await self._log("AI confirming the match...")
            try:
                confirmed, location = await asyncio.wait_for(
                    self._llm.confirm(event.best_frame_bytes, query),
                    timeout=self.LLM_TIMEOUT_S,
                )
                await self._log(f"AI confirmation: {'YES' if confirmed else 'NO'}")
            except (asyncio.TimeoutError, LLMError) as exc:
                # Land the story: fall back to a vision-only confirmation.
                await self._log(f"AI unavailable ({exc}) - confirmed by vision model.", "error")
                confirmed = True
                location = ""
        else:
            # No API key: do NOT claim an AI confirmation. The 3-frame vision
            # window is the confirmation.
            await self._log("Confirmed by vision model.")

        if not confirmed:
            return False

        await self._drone.hover(5.0)

        description = ""
        if have_llm and location.strip():
            description = location.strip()
        elif have_llm:
            try:
                description = await asyncio.wait_for(
                    self._llm.describe(event.best_frame_bytes, query),
                    timeout=self.LLM_TIMEOUT_S,
                )
            except (asyncio.TimeoutError, LLMError):
                description = ""
        if not description:
            description = self._fallback_location_sentence(query)

        # Draw the detection box on the result photo so the find is obvious.
        photo_bytes = self._draw_box_on(event.best_frame_bytes, event.bbox)
        photo_b64 = base64.b64encode(photo_bytes).decode()
        found_cell = list(self._cell)

        # Reveal the pin and pulse on the map FIRST, then after a beat show the
        # result card (UI places it over the camera side, leaving the map visible).
        await self.broadcast(WSMessage(
            type="found_preview",
            payload={"found_cell": found_cell, "confidence": event.confidence},
        ))
        await self._log(f"Item found: {description}")
        await asyncio.sleep(2.0)

        await self.broadcast(WSMessage(
            type="result",
            payload={
                "found": True,
                "description": description,
                "photo": photo_b64,
                "found_cell": found_cell,
            },
        ))
        return True

    def _draw_box_on(self, jpeg_bytes: bytes, bbox) -> bytes:
        """Return the JPEG with the detection bounding box drawn, if any."""
        if not bbox:
            return jpeg_bytes
        try:
            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return jpeg_bytes
            x, y, w, h = bbox
            cv2.rectangle(frame, (int(x), int(y)), (int(x + w), int(y + h)), (0, 255, 0), 3)
            ok, enc = cv2.imencode(".jpg", frame)
            return enc.tobytes() if ok else jpeg_bytes
        except Exception:
            return jpeg_bytes

    def _fallback_location_sentence(self, query: str) -> str:
        """A sensible human-readable location when the LLM is unavailable."""
        col, row = self._cell
        col_word = "left" if col < self._cols / 3 else ("right" if col > 2 * self._cols / 3 else "centre")
        row_word = "front" if row < self._rows / 3 else ("back" if row > 2 * self._rows / 3 else "middle")
        return f"The {query} appears in the {row_word}-{col_word} area of the room."

    def on_candidate_found(self, event: CandidateFoundEvent) -> None:
        """Callback registered with VisionModule -- stores event for pickup in the plan loop."""
        self._candidate_event = event
