"""Regression test: vision/search state must not leak between searches.

Reproduces the bug where searching item A, then immediately searching item B,
let B finish instantly using a stale detection left over from A. The fix resets
all vision/search state at the start of every search and tags detection results
with a search id so stale results are dropped.
"""

import asyncio
import json

import cv2
import numpy as np

from app.models import (
    AppConfig, SearchArea, FrameResult, CandidateFoundEvent, Direction, MoveType,
)
from app.drone.sim_adapter import SimDroneAdapter
from app.llm.interface import NullLLMAdapter
from app.search_manager import SearchManager


# Item -> grid cell, mirroring the manifest layout (rows 3-6 of a 7x7 grid).
ITEM_CELLS = {
    "backpack": (5, 3),
    "coffee mug": (3, 4),
}


_TINY_JPEG = cv2.imencode(".jpg", np.zeros((8, 8, 3), dtype=np.uint8))[1].tobytes()


class FakeVideoSource:
    """Minimal manifest-like video source: resolves a query to its cell."""
    def __init__(self):
        self._active = None

    def set_query(self, query):
        self._active = None
        q = (query or "").lower()
        for name, cell in ITEM_CELLS.items():
            if name in q or q in name:
                self._active = (name, cell)

    @property
    def active_target_cell(self):
        return self._active[1] if self._active else None

    def get_frame(self, cell):
        # Return a real (decodable) JPEG; detection is driven by FakeVision
        # off the drone's current cell, not the pixels.
        return _TINY_JPEG


class FakeVision:
    """Detects the active query's item once the drone has VISITED that
    item's cell. Detection keys off the drone's visited trail (mgr._trail),
    which is updated synchronously on every cell entry, rather than the
    instantaneous mgr._cell. That removes any dependence on frame-loop vs.
    plan-loop timing (the real app dwells >1s per cell so the frame loop
    always samples each cell; this keeps the fast test deterministic).

    It honours set_query()/reset() so a detection primed for one item can
    never satisfy a search for another -- the core behaviour under test.
    """
    def __init__(self, mgr_ref):
        self._mgr_ref = mgr_ref
        self._query = None

    def set_query(self, query):
        self._query = (query or "").lower()

    def reset(self):
        self._query = None

    def analyse_frame(self, frame, query):
        mgr = self._mgr_ref[0]
        q = (query or "").lower()
        if q != self._query:
            self.set_query(q)
        target = None
        for name, cell in ITEM_CELLS.items():
            if name in q or q in name:
                target = cell
        # Fire only once the target cell has actually been entered.
        visited = target is not None and [target[0], target[1]] in mgr._trail
        if visited:
            mgr.on_candidate_found(
                CandidateFoundEvent(best_frame_bytes=b"\xff\xd8\xff\xd9",
                                    bbox=(1, 1, 5, 5), confidence=0.9))
            return FrameResult(detected=True, confidence=0.9, bbox=(1, 1, 5, 5))
        return FrameResult(detected=False, confidence=0.0)


def _make_manager():
    # 3x3 m @ 0.5 m => 7x7 grid so ITEM_CELLS are reachable in the sweep.
    cfg = AppConfig(mode="sim", search_area=SearchArea(3.0, 3.0), sim_images_dir="sim_images",
                    sim_target_cell=(0, 0), anthropic_api_key="x", llm_provider="claude",
                    esp32_address="0.0.0.0", voice_input_enabled=False, step_size_m=0.5,
                    demo_speed_s=6.0)
    mgr_ref = [None]
    drone = SimDroneAdapter(log_callback=lambda m: None)
    vision = FakeVision(mgr_ref)
    vsrc = FakeVideoSource()
    mgr = SearchManager(cfg, drone, NullLLMAdapter(), vision, vsrc)
    mgr_ref[0] = mgr
    # Speed the test up: no real dwell needed since FakeVision is instant.
    mgr._cell_dwell_s = 0.2
    return mgr


class Recorder:
    def __init__(self):
        self.events = []        # (type, payload)
    async def send_text(self, data):
        d = json.loads(data)
        self.events.append((d["type"], d.get("payload", {})))


async def _search(mgr, rec, query):
    mgr.add_client(rec)
    await mgr.start(query)
    if mgr._search_task:
        await mgr._search_task


def test_second_search_does_not_finish_before_visiting_its_cell():
    """Search A to completion, then B immediately; B must only be 'found' after
    the drone actually reaches B's cell -- never instantly from A's leftover."""
    async def scenario():
        mgr = _make_manager()

        # Search A (backpack) to a found result.
        recA = Recorder()
        await _search(mgr, recA, "backpack")
        a_found = [p for t, p in recA.events if t == "result" and p.get("found")]
        assert a_found, "search A (backpack) should have found its item"

        # Immediately search B (coffee mug). Record B's event order.
        recB = Recorder()
        recB.events.clear()
        # Track the drone cell at the moment the found_preview fires.
        await _search(mgr, recB, "coffee mug")

        # B must report a found result...
        b_found = [p for t, p in recB.events if t == "result" and p.get("found")]
        assert b_found, "search B (coffee mug) should have found its item"

        # ...and the found cell must be coffee mug's cell, NOT backpack's.
        found_cell = tuple(b_found[0]["found_cell"])
        assert found_cell == ITEM_CELLS["coffee mug"], (
            f"B finished at {found_cell}, expected {ITEM_CELLS['coffee mug']} "
            f"(leaked stale detection from A?)"
        )

        # B must have visited its own cell before the found_preview event:
        # count the position events that occur before the first found_preview.
        seq = [(t, p) for t, p in recB.events if t in ("position", "found_preview")]
        visited_before_find = set()
        reached_before_find = False
        for t, p in seq:
            if t == "position":
                visited_before_find.add((p["col"], p["row"]))
            elif t == "found_preview":
                reached_before_find = ITEM_CELLS["coffee mug"] in visited_before_find
                break
        assert reached_before_find, (
            "B emitted found_preview before ever visiting coffee mug's cell"
        )

    asyncio.run(scenario())


def test_stop_clears_pending_candidate():
    """After stop(), a leftover candidate must not survive into the next search."""
    async def scenario():
        mgr = _make_manager()
        # Inject a stale candidate as if a previous detection had fired.
        mgr._candidate_event = CandidateFoundEvent(b"\xff\xd8\xff\xd9", (1, 1, 5, 5), 0.9)
        mgr._candidate_search_id = mgr._search_id
        await mgr.stop()
        assert mgr._candidate_event is None
        assert mgr._last_bbox is None
    asyncio.run(scenario())
