"""
Unit tests for app.planner.safety_checker.validate()

Requirements: 3.1, 3.2, 3.4, 3.5
"""

import pytest

from app.planner.safety_checker import validate
from app.models import (
    Direction,
    FlightPlan,
    Move,
    MoveType,
    SearchArea,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _area(w: float = 10.0, d: float = 10.0) -> SearchArea:
    return SearchArea(width_m=w, depth_m=d)


def _takeoff() -> Move:
    return Move(type=MoveType.TAKEOFF)


def _land() -> Move:
    return Move(type=MoveType.LAND)


def _hover(duration_s: float) -> Move:
    return Move(type=MoveType.HOVER, duration_s=duration_s)


def _move_forward(distance_m: float) -> Move:
    return Move(type=MoveType.MOVE, direction=Direction.FORWARD, distance_m=distance_m)


def _move_right(distance_m: float) -> Move:
    return Move(type=MoveType.MOVE, direction=Direction.RIGHT, distance_m=distance_m)


# ---------------------------------------------------------------------------
# 1. Empty plan (no moves) → ok=False
# ---------------------------------------------------------------------------

def test_empty_plan_is_invalid():
    """An empty moves list must be rejected."""
    plan = FlightPlan(moves=[], area=_area(), query="test")
    result = validate(plan, _area())
    assert isinstance(result, ValidationResult)
    assert result.ok is False


# ---------------------------------------------------------------------------
# 2. None plan → ok=False
# ---------------------------------------------------------------------------

def test_none_plan_is_invalid():
    """Passing None instead of a FlightPlan must be rejected gracefully."""
    result = validate(None, _area())
    assert isinstance(result, ValidationResult)
    assert result.ok is False


# ---------------------------------------------------------------------------
# 3. Valid TAKEOFF + LAND within bounds → ok=True
# ---------------------------------------------------------------------------

def test_takeoff_land_plan_is_valid():
    """A minimal plan with only TAKEOFF and LAND is safe."""
    moves = [_takeoff(), _land()]
    plan = FlightPlan(moves=moves, area=_area(), query="find person")
    result = validate(plan, _area())
    assert result.ok is True


# ---------------------------------------------------------------------------
# 4. MOVE that exits bounds (forward 10 m in a 3×3 area) → ok=False
# ---------------------------------------------------------------------------

def test_out_of_bounds_forward_move_is_invalid():
    """Moving forward 10 m in a 3×3 m area must be rejected."""
    area = _area(w=3.0, d=3.0)
    moves = [_takeoff(), _move_forward(10.0), _land()]
    plan = FlightPlan(moves=moves, area=area, query="find person")
    result = validate(plan, area)
    assert result.ok is False


# ---------------------------------------------------------------------------
# 5. Plan exceeding 300 s total flight time → ok=False
# ---------------------------------------------------------------------------

def test_plan_exceeding_time_limit_is_invalid():
    """A flight plan whose total time exceeds 5 minutes must be rejected."""
    # One hover of 301 s is over the limit
    moves = [_takeoff(), _hover(301.0), _land()]
    plan = FlightPlan(moves=moves, area=_area(), query="find person")
    result = validate(plan, _area())
    assert result.ok is False
    assert "300" in result.reason or "time" in result.reason.lower() or "limit" in result.reason.lower()


# ---------------------------------------------------------------------------
# 6. Plan at exactly 300 s total → ok=True
# ---------------------------------------------------------------------------

def test_plan_at_exact_time_limit_is_valid():
    """A flight plan whose total time is exactly 300 s (hover) should pass.

    TAKEOFF=3s, LAND=3s, so hover must be 294s to reach exactly 300s total.
    """
    moves = [_takeoff(), _hover(294.0), _land()]  # 3 + 294 + 3 = 300 s
    plan = FlightPlan(moves=moves, area=_area(), query="find person")
    result = validate(plan, _area())
    assert result.ok is True


# ---------------------------------------------------------------------------
# 7. Out-of-bounds in X direction → ok=False
# ---------------------------------------------------------------------------

def test_out_of_bounds_in_x_direction_is_invalid():
    """Moving right past the width boundary must be rejected."""
    area = _area(w=5.0, d=10.0)
    # Move right 6 m in a 5 m wide area → x = 6 > 5
    moves = [_takeoff(), _move_right(6.0), _land()]
    plan = FlightPlan(moves=moves, area=area, query="find person")
    result = validate(plan, area)
    assert result.ok is False


# ---------------------------------------------------------------------------
# 8. Out-of-bounds in Y direction → ok=False
# ---------------------------------------------------------------------------

def test_out_of_bounds_in_y_direction_is_invalid():
    """Moving forward past the depth boundary must be rejected."""
    area = _area(w=10.0, d=4.0)
    # Move forward 5 m in a 4 m deep area → y = 5 > 4
    moves = [_takeoff(), _move_forward(5.0), _land()]
    plan = FlightPlan(moves=moves, area=area, query="find person")
    result = validate(plan, area)
    assert result.ok is False


# ---------------------------------------------------------------------------
# 9. Valid plan returned unchanged (same moves list)
# ---------------------------------------------------------------------------

def test_valid_plan_moves_unchanged():
    """validate() must not mutate the moves list of a valid plan."""
    moves = [
        _takeoff(),
        _move_forward(3.0),
        _move_right(2.0),
        _land(),
    ]
    original_moves = list(moves)  # shallow copy to compare
    plan = FlightPlan(moves=moves, area=_area(w=10.0, d=10.0), query="find person")
    result = validate(plan, _area(w=10.0, d=10.0))
    assert result.ok is True
    # Moves list should be identical objects in the same order
    assert plan.moves == original_moves
