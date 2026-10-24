"""Real drone adapter — sends commands to the ESP32 over HTTP."""

import asyncio
from typing import Callable, Optional

import httpx

from app.drone.interface import DroneInterface, DroneCommandError
from app.models import Direction

COMMAND_TIMEOUT_S = 5.0


class RealDroneAdapter(DroneInterface):
    """Drone adapter for real hardware mode.
    
    Sends JSON commands to the ESP32 over HTTP POST /cmd.
    Raises DroneCommandError if the request times out or returns an error.
    No hardware details are exposed to callers.
    """

    def __init__(
        self,
        esp32_address: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._base_url = f"http://{esp32_address}"
        self._log = log_callback or (lambda msg: None)

    async def _send(self, payload: dict) -> None:
        """Send a command to the ESP32 and verify the response."""
        try:
            async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT_S) as client:
                resp = await client.post(f"{self._base_url}/cmd", json=payload)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise DroneCommandError(
                        f"ESP32 returned error for command {payload.get('cmd')!r}: {data}"
                    )
        except httpx.TimeoutException:
            raise DroneCommandError(
                f"Command {payload.get('cmd')!r} timed out after {COMMAND_TIMEOUT_S}s "
                f"(no response from {self._base_url})"
            )
        except httpx.HTTPStatusError as exc:
            raise DroneCommandError(
                f"Command {payload.get('cmd')!r} failed with HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise DroneCommandError(
                f"Command {payload.get('cmd')!r} could not be sent: {exc}"
            ) from exc

    async def takeoff(self) -> None:
        await self._send({"cmd": "takeoff"})

    async def land(self) -> None:
        await self._send({"cmd": "land"})

    async def move(self, direction: Direction, distance_m: float) -> None:
        await self._send({
            "cmd": "move",
            "direction": direction.value,
            "distance_m": distance_m,
        })

    async def turn(self, angle_deg: float) -> None:
        await self._send({"cmd": "turn", "angle_deg": angle_deg})

    async def hover(self, duration_s: float) -> None:
        await self._send({"cmd": "hover", "duration_s": duration_s})

    async def stop(self) -> None:
        await self._send({"cmd": "stop"})
