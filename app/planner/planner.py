"""Flight plan generator for Drone Finder."""

import math
from app.models import (
    Direction, Move, MoveType, FlightPlan, SearchArea
)


def _grid_dims(area: SearchArea, step_size_m: float) -> tuple[int, int]:
    """Return (num_cols, num_rows) of cell centres that fit inside the area.

    Uses floor(dim/step) + 1 so every cell centre sits at col*step <= dim,
    guaranteeing the whole sweep stays within [0, width] x [0, depth].
    """
    num_cols = max(1, int(area.width_m / step_size_m) + 1)
    num_rows = max(1, int(area.depth_m / step_size_m) + 1)
    return num_cols, num_rows


def generate_plan(query: str, area: SearchArea, step_size_m: float = 0.5) -> FlightPlan:
    """Generate a lawnmower sweep FlightPlan for the given SearchArea.

    Coordinate model (shared with the safety checker):
      - Origin (0, 0) is a corner of the area; the drone starts there.
      - X axis runs along columns; RIGHT = +x, LEFT = -x.
      - Y axis runs along rows; FORWARD = +y, BACKWARD = -y.
      - Column x positions: col * step_size_m, col in 0..num_cols-1.
      - Row y positions: row * step_size_m, row in 0..num_rows-1.

    Every grid cell is visited exactly once and gets exactly one HOVER.
    The plan always starts with TAKEOFF and ends with LAND. No TURN
    commands are emitted, so the geometry is unambiguous.
    """
    moves: list[Move] = []
    moves.append(Move(type=MoveType.TAKEOFF))

    num_cols, num_rows = _grid_dims(area, step_size_m)

    for row in range(num_rows):
        left_to_right = (row % 2 == 0)
        # Hover at the first cell of the row
        moves.append(Move(type=MoveType.HOVER, duration_s=0.5))
        # Traverse the remaining columns in this row
        for _col in range(num_cols - 1):
            direction = Direction.RIGHT if left_to_right else Direction.LEFT
            moves.append(Move(type=MoveType.MOVE, direction=direction, distance_m=step_size_m))
            moves.append(Move(type=MoveType.HOVER, duration_s=0.5))
        # Advance to the next row (except after the last row)
        if row < num_rows - 1:
            moves.append(Move(type=MoveType.MOVE, direction=Direction.FORWARD, distance_m=step_size_m))

    moves.append(Move(type=MoveType.LAND))
    return FlightPlan(moves=moves, area=area, query=query)
