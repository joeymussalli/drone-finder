"""
Data models for Drone Finder.

All dataclasses and enums used across the application are defined here so
every component imports from a single authoritative location.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Direction(str, Enum):
    """Valid movement directions for a drone move command."""
    FORWARD = "forward"
    BACKWARD = "backward"
    LEFT = "left"
    RIGHT = "right"


class MoveType(str, Enum):
    """All primitive move types that can appear in a FlightPlan."""
    TAKEOFF = "takeoff"
    LAND = "land"
    MOVE = "move"
    TURN = "turn"
    HOVER = "hover"
    STOP = "stop"


# ---------------------------------------------------------------------------
# Flight planning models
# ---------------------------------------------------------------------------

@dataclass
class Move:
    """A single primitive command in a FlightPlan.

    Fields are optional where the move type does not require them:
    - ``direction`` and ``distance_m`` are only meaningful for MOVE.
    - ``angle_deg`` is only meaningful for TURN.
    - ``duration_s`` is only meaningful for HOVER.
    """
    type: MoveType
    direction: Optional[Direction] = None   # move only
    distance_m: Optional[float] = None      # move only
    angle_deg: Optional[float] = None       # turn only
    duration_s: Optional[float] = None      # hover only


@dataclass
class SearchArea:
    """Rectangular bounding box (in metres) within which the drone may fly."""
    width_m: float
    depth_m: float


@dataclass
class FlightPlan:
    """Ordered list of moves produced by the Planner for a single search."""
    moves: list[Move]
    area: SearchArea
    query: str


@dataclass
class ValidationResult:
    """Outcome of a Safety_Checker validation pass.

    ``ok=True`` means the plan is safe to execute unchanged.
    ``ok=False`` carries a human-readable ``reason``.
    """
    ok: bool
    reason: str = ""


# ---------------------------------------------------------------------------
# Vision models
# ---------------------------------------------------------------------------

@dataclass
class FrameResult:
    """Detection result for a single video frame.

    ``confidence`` must be in [0.0, 1.0]; a ``ValueError`` is raised on
    construction if the value is out of range.
    ``bbox`` is (x, y, width, height) in pixels, present only when
    ``detected`` is True.
    """
    detected: bool
    confidence: float = 0.0
    bbox: Optional[tuple[int, int, int, int]] = None  # x, y, w, h (pixels)

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}"
            )


@dataclass
class CandidateFoundEvent:
    """Emitted by the Vision_Module after 3 consecutive high-confidence frames.

    Carries the JPEG bytes of the best-scoring frame, its bounding box, and
    the confidence score that triggered the event.
    """
    best_frame_bytes: bytes
    bbox: tuple[int, int, int, int]
    confidence: float


# ---------------------------------------------------------------------------
# Application configuration
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    """Fully parsed and type-cast application configuration.

    Loaded once at startup from the ``.env`` file via ``load_config()``.
    Injected into all components that need it.
    """
    mode: str                       # "sim" | "real"
    search_area: SearchArea
    sim_images_dir: str
    sim_target_cell: tuple[int, int]
    anthropic_api_key: str
    llm_provider: str               # "claude"
    esp32_address: str              # only used in real mode
    voice_input_enabled: bool
    step_size_m: float              # grid cell size for sweep
    demo_speed_s: float = 35.0      # target duration (s) for full demo sweep


# ---------------------------------------------------------------------------
# WebSocket message envelope
# ---------------------------------------------------------------------------

@dataclass
class WSMessage:
    """Envelope for all messages sent over the WebSocket to the browser.

    ``type`` is one of: "status" | "detection" | "result" | "error".
    ``payload`` carries type-specific data as a plain dict so it can be
    serialised directly to JSON.
    """
    type: str   # "status" | "detection" | "result" | "error"
    payload: dict
