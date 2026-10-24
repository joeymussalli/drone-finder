"""Safety validator for FlightPlan objects."""

from app.models import Direction, FlightPlan, Move, MoveType, SearchArea, ValidationResult

# Speed constants for flight time estimation
MOVE_SPEED_MS = 0.5      # metres per second
TURN_SPEED_DPS = 45.0    # degrees per second
TAKEOFF_TIME_S = 3.0
LAND_TIME_S = 3.0
MAX_FLIGHT_TIME_S = 300.0
EPS = 1e-6               # float tolerance for bounds checks


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


def validate(plan: FlightPlan, area: SearchArea) -> ValidationResult:
    """Validate a FlightPlan against area bounds and the flight-time limit.

    Uses a FIXED coordinate frame (no heading):
      RIGHT = +x, LEFT = -x, FORWARD = +y, BACKWARD = -y.
    TURN moves do not change position (they only consume time).

    Returns ValidationResult(ok=True) if the plan is safe, otherwise
    ValidationResult(ok=False, reason=...).
    """
    if not plan or not plan.moves:
        return ValidationResult(ok=False, reason="Flight plan is empty or null.")

    total_time = 0.0
    x, y = 0.0, 0.0

    for move in plan.moves:
        total_time += _move_time(move)
        if total_time > MAX_FLIGHT_TIME_S:
            return ValidationResult(
                ok=False,
                reason=f"Estimated flight time {total_time:.1f}s exceeds the 5-minute limit.",
            )

        if move.type == MoveType.MOVE:
            dist = move.distance_m or 0.0
            if move.direction == Direction.RIGHT:
                x += dist
            elif move.direction == Direction.LEFT:
                x -= dist
            elif move.direction == Direction.FORWARD:
                y += dist
            elif move.direction == Direction.BACKWARD:
                y -= dist

            if (
                x < -EPS or x > area.width_m + EPS
                or y < -EPS or y > area.depth_m + EPS
            ):
                return ValidationResult(
                    ok=False,
                    reason=(
                        f"Move would place drone at ({x:.2f}, {y:.2f}) m, "
                        f"outside bounds ({area.width_m} x {area.depth_m}) m."
                    ),
                )

    return ValidationResult(ok=True)
