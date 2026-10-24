"""Flight plan generator for Drone Finder."""

import math
from app.models import (
    Direction, Move, MoveType, FlightPlan, SearchArea
)


def generate_plan(query: str, area: SearchArea, step_size_m: float = 0.5) -> FlightPlan:
    """Generate a lawnmower sweep FlightPlan for the given SearchArea.

    The plan covers every grid cell exactly once in a bidirectional row
    (lawnmower) pattern. Always starts with TAKEOFF and ends with LAND.

    Args:
        query: The user's search query (stored in FlightPlan for reference).
        area: The SearchArea dimensions in metres.
        step_size_m: Grid cell size; defaults to 0.5 m.

    Returns:
        A FlightPlan whose moves cover the full search area.
    """
    moves: list[Move] = []

    # Always start with takeoff
    moves.append(Move(type=MoveType.TAKEOFF))

    num_cols = max(1, math.ceil(area.width_m / step_size_m))
    num_rows = max(1, math.ceil(area.depth_m / step_size_m))

    for row in range(num_rows):
        # Determine traversal direction for this row
        left_to_right = (row % 2 == 0)

        # Traverse all columns in this row
        for col in range(num_cols):
            # Hover at this cell to allow the camera to capture frames
            moves.append(Move(type=MoveType.HOVER, duration_s=0.5))

            # Move to next column (except at the last column)
            if col < num_cols - 1:
                direction = Direction.FORWARD if left_to_right else Direction.BACKWARD
                moves.append(Move(
                    type=MoveType.MOVE,
                    direction=direction,
                    distance_m=step_size_m,
                ))

        # At end of row: if not the last row, move to the next row
        if row < num_rows - 1:
            # Turn 90° to face the next row, step across, turn 90° back
            if left_to_right:
                # Finished going left→right: turn right, step, turn right (now facing right→left)
                moves.append(Move(type=MoveType.TURN, angle_deg=90.0))
                moves.append(Move(type=MoveType.MOVE, direction=Direction.FORWARD, distance_m=step_size_m))
                moves.append(Move(type=MoveType.TURN, angle_deg=90.0))
            else:
                # Finished going right→left: turn left, step, turn left (now facing left→right)
                moves.append(Move(type=MoveType.TURN, angle_deg=-90.0))
                moves.append(Move(type=MoveType.MOVE, direction=Direction.FORWARD, distance_m=step_size_m))
                moves.append(Move(type=MoveType.TURN, angle_deg=-90.0))

    # Always end with land
    moves.append(Move(type=MoveType.LAND))

    return FlightPlan(moves=moves, area=area, query=query)
