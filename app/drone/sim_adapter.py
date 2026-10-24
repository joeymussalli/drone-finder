"""Simulation drone adapter — no hardware required."""

import asyncio
from typing import Callable
from app.drone.interface import DroneInterface, DroneCommandError
from app.models import Direction


class SimDroneAdapter(DroneInterface):
    """Drone adapter for simulation mode.
    
    Accepts all DroneInterface calls, logs them, and returns immediately
    without communicating with any hardware. Tracks grid cell position
    so SimVideoSource can serve the correct frame.
    """

    def __init__(self, log_callback: Callable[[str], None]) -> None:
        self._log = log_callback
        self._cell: tuple[int, int] = (0, 0)  # (col, row)

    @property
    def current_cell(self) -> tuple[int, int]:
        return self._cell

    async def _emit(self, msg: str) -> None:
        if asyncio.iscoroutinefunction(self._log):
            await self._log(msg)
        else:
            self._log(msg)

    async def takeoff(self) -> None:
        await self._emit("[SIM] takeoff()")

    async def land(self) -> None:
        await self._emit("[SIM] land()")

    async def move(self, direction: Direction, distance_m: float) -> None:
        await self._emit(f"[SIM] move(direction={direction.value}, distance_m={distance_m})")
        col, row = self._cell
        if direction == Direction.FORWARD:
            col += 1
        elif direction == Direction.BACKWARD:
            col -= 1
        elif direction == Direction.RIGHT:
            row += 1
        elif direction == Direction.LEFT:
            row -= 1
        self._cell = (col, row)

    async def turn(self, angle_deg: float) -> None:
        await self._emit(f"[SIM] turn(angle_deg={angle_deg})")

    async def hover(self, duration_s: float) -> None:
        await self._emit(f"[SIM] hover(duration_s={duration_s})")

    async def stop(self) -> None:
        await self._emit("[SIM] stop()")
