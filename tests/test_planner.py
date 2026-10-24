"""Unit tests for generate_plan() in app.planner.planner.

Validates Requirements 2.1 and 2.2 with the floor+1 grid model:
  - num_cols = int(width/step) + 1, num_rows = int(depth/step) + 1
  - Every cell gets exactly one HOVER, so HOVER count == num_cols * num_rows.
  - Column traversal uses RIGHT on even rows, LEFT on odd rows; row
    advance uses FORWARD. No TURN commands are emitted.
"""

import pytest
from app.planner.planner import generate_plan
from app.planner.safety_checker import validate
from app.models import MoveType, SearchArea, Direction

VALID_MOVE_TYPES = set(MoveType)


def hover_count(plan) -> int:
    return sum(1 for m in plan.moves if m.type == MoveType.HOVER)


# --- First/last move -------------------------------------------------------

def test_first_move_is_takeoff():
    area = SearchArea(width_m=1.0, depth_m=1.0)
    plan = generate_plan("keys", area, step_size_m=0.5)
    assert plan.moves[0].type == MoveType.TAKEOFF


def test_last_move_is_land():
    area = SearchArea(width_m=1.0, depth_m=1.0)
    plan = generate_plan("keys", area, step_size_m=0.5)
    assert plan.moves[-1].type == MoveType.LAND


# --- Valid move types ------------------------------------------------------

def test_all_move_types_are_valid():
    area = SearchArea(width_m=2.0, depth_m=2.0)
    plan = generate_plan("wallet", area, step_size_m=1.0)
    for move in plan.moves:
        assert move.type in VALID_MOVE_TYPES, f"Unexpected move type: {move.type}"


def test_no_turn_commands_emitted():
    """The simple-geometry planner must not emit TURN commands."""
    area = SearchArea(width_m=3.0, depth_m=3.0)
    plan = generate_plan("phone", area, step_size_m=0.5)
    assert all(m.type != MoveType.TURN for m in plan.moves)


# --- Cell counts (floor+1 model) ------------------------------------------

def test_1x1_area_step_0_5_has_9_hovers():
    # int(1.0/0.5)+1 = 3 cols, 3 rows => 9 cells
    area = SearchArea(width_m=1.0, depth_m=1.0)
    plan = generate_plan("glasses", area, step_size_m=0.5)
    assert hover_count(plan) == 9


def test_3x3_area_step_1_has_16_hovers():
    # int(3.0/1.0)+1 = 4 cols, 4 rows => 16 cells
    area = SearchArea(width_m=3.0, depth_m=3.0)
    plan = generate_plan("remote", area, step_size_m=1.0)
    assert hover_count(plan) == 16


def test_3x3_area_step_0_5_has_49_hovers():
    # int(3.0/0.5)+1 = 7 cols, 7 rows => 49 cells
    area = SearchArea(width_m=3.0, depth_m=3.0)
    plan = generate_plan("book", area, step_size_m=0.5)
    assert hover_count(plan) == 49


# --- Direction alternation (RIGHT even rows, LEFT odd rows) ----------------

def test_column_moves_alternate_right_left_by_row():
    """Even rows traverse RIGHT, odd rows LEFT; row advance is FORWARD."""
    area = SearchArea(width_m=1.0, depth_m=1.0)  # 3x3 grid
    plan = generate_plan("toy", area, step_size_m=0.5)

    num_cols = 3
    row_idx = 0
    cols_seen = 0
    for move in plan.moves:
        if move.type == MoveType.HOVER:
            cols_seen += 1
        elif move.type == MoveType.MOVE:
            if move.direction == Direction.FORWARD:
                # row advance -> next row
                row_idx += 1
                cols_seen = 0
            else:
                expected = Direction.RIGHT if row_idx % 2 == 0 else Direction.LEFT
                assert move.direction == expected, (
                    f"Row {row_idx}: expected {expected}, got {move.direction}"
                )


# --- Sweep stays within bounds (the original bug) -------------------------

def test_3x3_step_0_5_plan_passes_safety():
    """Regression: the 3x3 @ 0.5 sweep must not exit the area."""
    area = SearchArea(width_m=3.0, depth_m=3.0)
    plan = generate_plan("blue water bottle", area, step_size_m=0.5)
    result = validate(plan, area)
    assert result.ok is True, result.reason


@pytest.mark.parametrize("w,d,step", [
    (3.0, 3.0, 0.5),
    (3.0, 3.0, 1.0),
    (2.0, 4.0, 0.5),
    (1.0, 1.0, 0.5),
    (5.0, 2.5, 0.5),
])
def test_generated_plans_are_always_in_bounds(w, d, step):
    area = SearchArea(width_m=w, depth_m=d)
    plan = generate_plan("item", area, step_size_m=step)
    result = validate(plan, area)
    assert result.ok is True, result.reason
