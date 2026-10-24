"""Safety validator for FlightPlan objects."""

import math
from app.models import Direction, FlightPlan, Move, MoveType, SearchArea, ValidationResult

# Speed constants for flight time estimation
MOVE_SPEED_MS = 0.5      # metres per second
TURN_SPEED_DPS = 45.0    # degrees per second
TAKEOFF_TIME_S = 3.0
LAND_TIME_S = 3.0


def _move_time(move: Move) -> float:
    """Estimate execution time for a single move in seconds."""
    if move.type == MoveType.TAKEOFF:
        return TAKEOFF_TIME_S
    if move.type == MoveType.LAND:
        return LAND_TIME_S
    if move.type == MoveType.HOVER:
        return move.duration_s or 0.0
    if move.type == MoveType.MOVE:
        return (move.distance_m or 0.0) / MOVE_SPEED_MS
    if move.type == MoveType.TURN:
        return abs(move.angle_deg or 0.0) / TURN_SPEED_DPS
    return 0.0


def _apply_move(x: float, y: float, heading: float, move: Move) -> tuple[float, float, float]:
    """Return (new_x, new_y, new_heading) after applying a move.

    heading is in degrees; 0 = facing +y (forward), 90 = facing +x (right).
    """
    if move.type != MoveType.MOVE:
        if move.type == MoveType.TURN:
            heading = (heading + (move.angle_deg or 0.0)) % 360
        return x, y, heading

    dist = move.distance_m or 0.0
    direction = move.direction

    # Map direction + heading to dx/dy
    # heading 0° → facing +y; 90° → facing +x; 180° → facing -y; 270° → facing -x
    if direction == Direction.FORWARD:
        angle = heading
    elif direction == Direction.BACKWARD:
        angle = (heading + 180) % 360
    elif direction == Direction.RIGHT:
        angle = (heading + 90) % 360
    elif direction == Direction.LEFT:
        angle = (heading - 90) % 360
    else:
        return x, y, heading

    rad = math.radians(angle)
    dx = dist * math.sin(rad)
    dy = dist * math.cos(rad)
    return x + dx, y + dy, heading


def validate(plan: FlightPlan, area: SearchArea) -> ValidationResult:
    """Validate a FlightPlan against bounds and time limits.

    Returns ValidationResult(ok=True) if the plan is safe.
    Returns ValidationResult(ok=False, reason=...) if any check fails.
    """
    # Reject null or empty plans
    if not plan or not plan.moves:
        return ValidationResult(ok=False, reason="Flight plan is empty or null.")

    total_time = 0.0
    x, y, heading = 0.0, 0.0, 0.0  # start at origin, facing forward (+y)

    for move in plan.moves:
        # Accumulate time
        total_time += _move_time(move)
        if total_time > 300.0:
            return ValidationResult(
                ok=False,
                reason=f"Estimated flight time {total_time:.1f}s exceeds the 5-minute limit."
            )

        # Track position for MOVE commands
        new_x, new_y, new_heading = _apply_move(x, y, heading, move)

        if move.type == MoveType.MOVE:
            if not (0.0 <= new_x <= area.width_m and 0.0 <= new_y <= area.depth_m):
                return ValidationResult(
                    ok=False,
                    reason=(
                        f"Move would place drone at ({new_x:.2f}, {new_y:.2f}) m, "
                        f"outside bounds ({area.width_m} x {area.depth_m}) m."
                    )
                )

        x, y, heading = new_x, new_y, new_heading

    return ValidationResult(ok=True)
