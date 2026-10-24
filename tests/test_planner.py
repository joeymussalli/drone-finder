"""Unit tests for generate_plan() in app.planner.planner.

Validates Requirements 2.1 and 2.2:
  - 2.1: Flight_Plan uses only the six valid primitive move types.
  - 2.2: Sweep_Pattern covers every cell of the Search_Area exactly once.
"""

import pytest
from app.planner.planner import generate_plan
from app.models import MoveType, SearchArea, Direction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_MOVE_TYPES = set(MoveType)


def hover_count(plan) -> int:
    return sum(1 for m in plan.moves if m.type == MoveType.HOVER)


def move_directions(plan) -> list[Direction]:
    """Return directions of all MOVE primitives in the plan."""
    return [m.direction for m in plan.moves if m.type == MoveType.MOVE]


# ---------------------------------------------------------------------------
# Test 1 – First move is TAKEOFF, last move is LAND (Req 2.1)
# ---------------------------------------------------------------------------

def test_first_move_is_takeoff():
    area = SearchArea(width_m=1.0, depth_m=1.0)
    plan = generate_plan("keys", area, step_size_m=0.5)
    assert plan.moves[0].type == MoveType.TAKEOFF


def test_last_move_is_land():
    area = SearchArea(width_m=1.0, depth_m=1.0)
    plan = generate_plan("keys", area, step_size_m=0.5)
    assert plan.moves[-1].type == MoveType.LAND


# ---------------------------------------------------------------------------
# Test 2 – All move types are valid enum values (Req 2.1)
# ---------------------------------------------------------------------------

def test_all_move_types_are_valid():
    area = SearchArea(width_m=2.0, depth_m=2.0)
    plan = generate_plan("wallet", area, step_size_m=1.0)
    for move in plan.moves:
        assert move.type in VALID_MOVE_TYPES, f"Unexpected move type: {move.type}"


def test_no_unknown_move_types():
    """Plan must not contain any move type outside the six defined primitives."""
    area = SearchArea(width_m=3.0, depth_m=3.0)
    plan = generate_plan("phone", area, step_size_m=1.0)
    unexpected = {m.type for m in plan.moves} - VALID_MOVE_TYPES
    assert unexpected == set(), f"Unexpected move types found: {unexpected}"


# ---------------------------------------------------------------------------
# Test 3 – 1 m × 1 m area, step 0.5 m → 2×2 = 4 grid cells → 4 HOVERs (Req 2.2)
# ---------------------------------------------------------------------------

def test_1x1_area_step_0_5_has_4_hovers():
    area = SearchArea(width_m=1.0, depth_m=1.0)
    plan = generate_plan("glasses", area, step_size_m=0.5)
    assert hover_count(plan) == 4, (
        f"Expected 4 HOVERs for 2×2 grid, got {hover_count(plan)}"
    )


# ---------------------------------------------------------------------------
# Test 4 – 3 m × 3 m area, step 1.0 m → 3×3 = 9 cells → 9 HOVERs (Req 2.2)
# ---------------------------------------------------------------------------

def test_3x3_area_step_1_has_9_hovers():
    area = SearchArea(width_m=3.0, depth_m=3.0)
    plan = generate_plan("remote", area, step_size_m=1.0)
    assert hover_count(plan) == 9, (
        f"Expected 9 HOVERs for 3×3 grid, got {hover_count(plan)}"
    )


# ---------------------------------------------------------------------------
# Test 5 – 3 m × 3 m area, step 0.5 m → 6×6 = 36 cells → 36 HOVERs (Req 2.2)
# ---------------------------------------------------------------------------

def test_3x3_area_step_0_5_has_36_hovers():
    area = SearchArea(width_m=3.0, depth_m=3.0)
    plan = generate_plan("book", area, step_size_m=0.5)
    assert hover_count(plan) == 36, (
        f"Expected 36 HOVERs for 6×6 grid, got {hover_count(plan)}"
    )


# ---------------------------------------------------------------------------
# Test 6 – Direction alternates: even rows FORWARD, odd rows BACKWARD (Req 2.2)
# ---------------------------------------------------------------------------

def test_move_direction_alternates_by_row():
    """Even rows travel FORWARD (left→right), odd rows travel BACKWARD (right→left)."""
    # Use a 2×2 grid so there is one even row and one odd row, each with
    # one inter-column MOVE.
    area = SearchArea(width_m=1.0, depth_m=1.0)
    plan = generate_plan("toy", area, step_size_m=0.5)

    # Collect only the horizontal MOVE directions (exclude row-transition moves
    # which also have direction=FORWARD).  We identify row-transition moves as
    # the MOVE that immediately follows the last HOVER of a row (sandwiched
    # between two TURNs).
    moves = plan.moves

    # Build a list of (row_index, direction) for column-traversal MOVEs.
    # Strategy: iterate move-by-move and track row boundaries by counting HOVERs.
    num_cols = 2  # width 1.0 / step 0.5
    row_directions: dict[int, list[Direction]] = {}
    row_idx = 0
    hover_in_row = 0
    in_transition = False

    for i, move in enumerate(moves):
        if move.type == MoveType.HOVER:
            hover_in_row += 1
            in_transition = False
        elif move.type == MoveType.TURN:
            in_transition = True
        elif move.type == MoveType.MOVE:
            if in_transition:
                # This is the row-gap MOVE (between TURNs); skip it.
                pass
            else:
                row_directions.setdefault(row_idx, []).append(move.direction)
        # Detect row boundary: after the last HOVER of a full row
        if hover_in_row == num_cols:
            hover_in_row = 0
            row_idx += 1
            in_transition = False

    for row, directions in row_directions.items():
        expected = Direction.FORWARD if row % 2 == 0 else Direction.BACKWARD
        for d in directions:
            assert d == expected, (
                f"Row {row}: expected {expected}, got {d}"
            )


# ---------------------------------------------------------------------------
# Test 7 – Plan contains only moves from the six valid primitives (Req 2.1)
# ---------------------------------------------------------------------------

def test_only_valid_primitives_present():
    """Exhaustive: every move type in the plan must be one of the six primitives."""
    valid = {
        MoveType.TAKEOFF,
        MoveType.LAND,
        MoveType.MOVE,
        MoveType.TURN,
        MoveType.HOVER,
        MoveType.STOP,
    }
    area = SearchArea(width_m=2.0, depth_m=2.0)
    plan = generate_plan("umbrella", area, step_size_m=1.0)
    for move in plan.moves:
        assert move.type in valid, f"Move type {move.type!r} is not a valid primitive"
