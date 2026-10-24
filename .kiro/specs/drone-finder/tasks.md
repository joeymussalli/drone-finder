# Implementation Plan: Drone Finder

## Overview

Implementation follows a simulation-first strategy so the full end-to-end demo runs as early as possible without any physical hardware. Real hardware integration is deferred to the final task. The ordering matches the dependency graph: scaffold → config → models → drone ABC + sim adapter → planner + safety checker → sim video → vision → LLM → search manager → FastAPI routes → frontend → tests → sim demo validation → real hardware.

All Python code targets Python 3.11+. Tests use pytest + Hypothesis.

---

## Tasks

- [x] 1. Project scaffold
  - Create the directory tree from `design.md` (`app/`, `app/planner/`, `app/drone/`, `app/vision/`, `app/llm/`, `static/`, `sim_images/`, `tests/`)
  - Add `__init__.py` to every package directory
  - Write `requirements.txt` with pinned versions: `fastapi`, `uvicorn[standard]`, `opencv-python-headless`, `anthropic`, `python-dotenv`, `ultralytics`, `hypothesis`, `pytest`, `httpx`
  - Write `.env.example` listing every required key (`MODE`, `SEARCH_AREA_WIDTH_M`, `SEARCH_AREA_DEPTH_M`, `SIM_IMAGES_DIR`, `SIM_TARGET_CELL`, `ANTHROPIC_API_KEY`, `LLM_PROVIDER`, `ESP32_ADDRESS`, `VOICE_INPUT_ENABLED`, `STEP_SIZE_M`) with placeholder values and a one-line comment each
  - Add three placeholder JPEG images to `sim_images/` (`target.jpg`, `empty_1.jpg`, `empty_2.jpg`) — 1×1 pixel solid-colour images are fine for scaffolding
  - Write a skeleton `README.md` with section headings: Prerequisites, Config file setup, Running in simulation mode, Running with real hardware
  - _Requirements: 12.1, 12.2, 12.4_

- [x] 2. Config loader
  - [x] 2.1 Implement `load_config()` in `app/config.py`
    - Use `python-dotenv` to load `.env`
    - Parse and type-cast all keys into an `AppConfig` dataclass (imported from `app/models.py` — see task 3)
    - Raise `ConfigError(missing_key)` for any absent required key; `ConfigError` should be a custom exception defined in `config.py`
    - Return the fully populated `AppConfig` instance; call this once at FastAPI startup and inject it everywhere
    - _Requirements: 12.1, 12.3_

- [x] 3. Data models
  - [x] 3.1 Write all dataclasses and enums in `app/models.py`
    - Implement `Direction`, `MoveType`, `Move`, `SearchArea`, `FlightPlan`, `ValidationResult`, `FrameResult`, `CandidateFoundEvent`, `AppConfig`, `WSMessage` exactly as specified in the `## Data Models` section of `design.md`
    - Add `__post_init__` validation where useful (e.g. `FrameResult.confidence` must be in `[0.0, 1.0]`)
    - _Requirements: 2.1, 3.4, 4.1, 7.1_

- [x] 4. Drone Interface ABC and SimDroneAdapter
  - [x] 4.1 Implement `DroneInterface` ABC in `app/drone/interface.py`
    - Declare all six abstract async methods: `takeoff`, `land`, `move`, `turn`, `hover`, `stop` exactly as shown in `design.md`
    - _Requirements: 4.1_
  - [x] 4.2 Implement `SimDroneAdapter` in `app/drone/sim_adapter.py`
    - Accept all `DroneInterface` calls and return immediately (no sleep)
    - Log `[SIM] <command>(<params>)` via a callback/queue that will be wired to the WebSocket status channel in task 9
    - Track current simulated grid position internally (`self._cell: tuple[int,int]`) so `SimVideoSource` can query it
    - _Requirements: 4.2, 11.2, 11.3_

- [x] 5. Planner and Safety Checker
  - [x] 5.1 Implement `generate_plan()` in `app/planner/planner.py`
    - Accept `query: str` and `area: SearchArea`; return `FlightPlan`
    - Generate a lawnmower sweep: row-by-row bidirectional traversal of the grid quantised to `step_size_m`
    - Plan MUST start with `MoveType.TAKEOFF` and end with `MoveType.LAND`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 5.2 Implement `validate()` in `app/planner/safety_checker.py`
    - Accept `plan: FlightPlan` and `area: SearchArea`; return `ValidationResult`
    - Reject if any move displaces the drone outside `SearchArea` bounds → `ValidationResult(ok=False, reason=...)`
    - Reject if total estimated flight time > 300 s → `ValidationResult(ok=False, reason=...)`
    - Reject if plan is empty or null → `ValidationResult(ok=False, reason=...)`
    - Return `ValidationResult(ok=True)` with the plan unchanged on pass
    - _Requirements: 3.1, 3.2, 3.4, 3.5_

- [x] 6. SimVideoSource
  - [x] 6.1 Implement `SimVideoSource` in `app/vision/sim_video.py`
    - Read all JPEG files from `sim_images/` at construction time
    - Implement `get_frame(cell: tuple[int,int]) -> bytes`
      - Return `target.jpg` bytes when `cell == config.sim_target_cell`
      - Round-robin through `empty_N.jpg` files otherwise
    - Update the served image within 500 ms of the drone entering a new cell (synchronous call satisfies this trivially)
    - _Requirements: 11.4, 11.5, 11.6, 11.7_

- [x] 7. Vision Module
  - [x] 7.1 Implement `analyse_frame()` and confidence window in `app/vision/vision_module.py`
    - Load YOLO-World model via `from ultralytics import YOLOWorld`
    - Before each search call `model.set_classes([query])` to set the open-vocabulary target class
    - `analyse_frame(frame: np.ndarray, query: str) -> FrameResult` — run model inference, return `FrameResult(detected=True, confidence=score, bbox=(x,y,w,h))` or `FrameResult(detected=False)` if nothing detected above threshold
    - Implement a 3-frame sliding window: emit `CandidateFoundEvent` when 3 consecutive frames all score ≥ 0.7; carry the frame with the highest confidence (earliest on tie)
    - Reset the window to zero on any frame scoring < 0.7
    - All `FrameResult.confidence` values MUST be in `[0.0, 1.0]`
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 8. LLM Interface ABC and ClaudeAdapter
  - [x] 8.1 Implement `LLMInterface` ABC in `app/llm/interface.py`
    - Declare two abstract async methods: `confirm(image_bytes: bytes, query: str) -> tuple[bool, str]` and `describe(image_bytes: bytes, query: str) -> str`
    - _Requirements: 8.5, 9.1_
  - [x] 8.2 Implement `ClaudeAdapter` in `app/llm/claude_adapter.py`
    - Load API key exclusively from `AppConfig` — never hard-code it
    - `confirm()`: base64-encode image, call `anthropic.Anthropic().messages.create()` with the vision model; return `(bool, location_str)`
    - `describe()`: same pattern; return location description ≤ 30 words as a single natural-language sentence
    - Raise `LLMError` if the key is missing; raise `LLMError` if the API returns an error or is unreachable
    - _Requirements: 8.7, 8.8, 9.2, 9.3, 9.5, 9.6, 10.4_

- [x] 9. Search Manager
  - [x] 9.1 Implement `SearchManager` in `app/search_manager.py`
    - Orchestrate the full search lifecycle: accept a `start(query)` call, validate input (reject empty/whitespace-only), invoke `generate_plan()` → `validate()` → execute moves via `DroneInterface`
    - Execute the flight plan step-by-step with `await asyncio.sleep(0)` yields between moves to keep the event loop responsive
    - Feed frames from `Video_Stream` to `Vision_Module.analyse_frame()` at ≥ 2 fps (detection cycle); maintain MJPEG render at 15 fps using last known frame + bbox between detection cycles
    - On `CandidateFoundEvent`: call `LLMInterface.confirm()`; if confirmed → hover + emit `result` WSMessage; if not → resume plan
    - Accept a `stop()` call: issue `DroneInterface.stop()` then `DroneInterface.land()` within 500 ms; cancel the in-progress flight plan coroutine
    - Implement `broadcast(msg: WSMessage)` to push structured events to all connected WebSocket clients
    - Handle all error paths from `design.md` Error Handling table (drone command fail, video lost > 3 s, LLM timeout 10 s, land-after-failure 10 s)
    - Maintain a status log buffer of at least 200 most recent messages
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.6, 2.7, 3.3, 4.5, 4.6, 5.2, 5.3, 5.4, 5.5, 6.5, 6.6, 8.1, 8.2, 8.3, 8.4, 8.6, 10.2, 10.5, 13.1, 13.3_

- [x] 10. FastAPI routes and MJPEG video endpoint
  - [x] 10.1 Implement `app/main.py` with FastAPI app, routes, and startup
    - Call `load_config()` at startup; exit non-zero on `ConfigError`
    - Instantiate `SearchManager`, `DroneInterface` (sim or real based on config), `LLMInterface`, `SimVideoSource` (sim mode)
    - `POST /search` — body `{query: str}`; hand off to `SearchManager.start()`; return 400 with validation message on empty/whitespace input
    - `POST /stop` — call `SearchManager.stop()`
    - `GET /ws` — WebSocket endpoint; register client with `SearchManager`; forward all `WSMessage` events
    - `GET /video` — MJPEG stream (`multipart/x-mixed-replace; boundary=frame`); pull frames from `SearchManager` at 15 fps via `asyncio.sleep(1/15)`; draw detection bbox with `cv2.rectangle()` server-side; append `SIMULATION` text overlay with `cv2.putText()` when `config.mode == "sim"`
    - Mount `static/` as FastAPI `StaticFiles` so `index.html` is served at `/`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 11.8, 12.3_

- [x] 11. Frontend
  - [ ] 11.1 Write `static/index.html` as a single self-contained file (HTML + CSS + JS inline, no build step)
    - Command_Box: `<input>` accepting up to 200 characters; disabled while search is in progress; shows inline validation message on empty submit; clears validation message on input change
    - Stop_Button: always visible and enabled; `POST /stop` on click
    - Video panel: `<img id="video-feed" src="/video">` — no JS needed beyond setting the `src`
    - Status_Log: scrolling `<div>` or `<ul>`; auto-scrolls to latest message unless user has manually scrolled up; stops auto-scroll until user scrolls back to the bottom
    - Result_Card: hidden until search completes; shows "Found it" heading + best-frame photo + location description on success; shows "Not found" message on sweep completion without detection; includes fallback "description unavailable" message if `describe` fails
    - WebSocket client: connect to `/ws`; dispatch incoming `WSMessage` events by type (`status` → append to log, `detection` → show/hide bbox overlay note, `result` → render Result_Card, `error` → append styled error to log)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 5.1, 6.1, 6.2, 10.1, 10.2, 10.3, 10.6, 13.2_

- [x] 12. Checkpoint — full sim demo passes
  - Start the server with `uvicorn app.main:app --reload`
  - Verify: type a search query → search starts → video panel shows frames → status log scrolls → detection event triggers → Result_Card appears → Stop_Button cancels mid-search
  - Verify `SIMULATION` label visible on video panel
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Unit tests and property-based tests
  - [x] 13.1 Write unit tests for `generate_plan()` in `tests/test_planner.py`
    - Test with various `SearchArea` sizes; assert first move is `TAKEOFF`, last is `LAND`
    - Assert all moves have valid `MoveType` values
    - Assert the sweep visits every cell (count expected cells from area dimensions and step size)
    - _Requirements: 2.1, 2.2_
  - [ ]* 13.2 Write property test — Property 1: valid search requests reach Planner unchanged
    - `@given(st.text(min_size=1).filter(lambda s: s.strip()))` → assert `generate_plan(query, area).query == query`
    - `# Feature: drone-finder, Property 1: valid search requests reach the Planner unchanged`
    - _Requirements: 1.2_
  - [ ]* 13.3 Write property test — Property 2: whitespace-only inputs are rejected
    - `@given(st.text(alphabet=st.characters(whitelist_categories=('Zs',))).map(lambda s: s or ' '))` → assert `SearchManager.start(query)` does not call Planner
    - `# Feature: drone-finder, Property 2: whitespace-only inputs are rejected without starting a search`
    - _Requirements: 1.3_
  - [ ]* 13.4 Write property test — Property 3: flight plan moves are all valid primitives
    - `@given(valid_query, valid_area)` → assert every `move.type` in generated `FlightPlan` is a member of `MoveType`
    - `# Feature: drone-finder, Property 3: flight plan moves are all valid primitives`
    - _Requirements: 2.1_
  - [ ]* 13.5 Write property test — Property 4: sweep pattern covers every cell exactly once
    - `@given(valid_area, valid_step_size)` → collect visited cells from generated plan; assert len == expected cell count and no duplicates
    - `# Feature: drone-finder, Property 4: sweep pattern covers every cell exactly once`
    - _Requirements: 2.2_
  - [x] 13.6 Write unit tests for `validate()` in `tests/test_safety_checker.py`
    - Test in-bounds plan → `ValidationResult(ok=True)`
    - Test plan with one out-of-bounds move → `ValidationResult(ok=False)`
    - Test plan exceeding 300 s → `ValidationResult(ok=False)`
    - Test empty plan → `ValidationResult(ok=False)`
    - _Requirements: 3.1, 3.2, 3.4, 3.5_
  - [ ]* 13.7 Write property test — Property 5: safety checker rejects out-of-bounds plans
    - `@given(plan_with_oob_move, valid_area)` → assert `validate(plan, area).ok == False`
    - `# Feature: drone-finder, Property 5: safety checker rejects out-of-bounds plans`
    - _Requirements: 3.1_
  - [ ]* 13.8 Write property test — Property 6: safety checker rejects over-time plans
    - `@given(plan_exceeding_300s, valid_area)` → assert `validate(plan, area).ok == False`
    - `# Feature: drone-finder, Property 6: safety checker rejects over-time plans`
    - _Requirements: 3.2_
  - [ ]* 13.9 Write property test — Property 7: valid plans returned unchanged
    - `@given(valid_plan, valid_area)` → assert `validate(plan, area).ok == True`
    - `# Feature: drone-finder, Property 7: valid plans are returned unchanged by the safety checker`
    - _Requirements: 3.4_
  - [x] 13.10 Write unit tests for Vision Module confidence window in `tests/test_vision_module.py`
    - Test: 3 consecutive frames ≥ 0.7 → `CandidateFoundEvent` emitted with the highest-confidence (earliest-tie) frame
    - Test: frame < 0.7 anywhere in sequence → no event emitted, window resets
    - Test: exactly 2 high-confidence frames followed by a low frame → no event
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ]* 13.11 Write property test — Property 8: confidence scores always in `[0.0, 1.0]`
    - `@given(synthetic_frame)` → assert `0.0 <= analyse_frame(frame, query).confidence <= 1.0`
    - `# Feature: drone-finder, Property 8: Vision Module confidence scores are always in range`
    - _Requirements: 7.1_
  - [ ]* 13.12 Write property test — Property 9: candidate-found event emitted only after 3 consecutive high-confidence frames
    - `@given(st.lists(st.floats(min_value=0.7, max_value=1.0), min_size=3, max_size=3))` → feed frames to window; assert exactly one event emitted carrying the highest-confidence frame (earliest on tie)
    - `# Feature: drone-finder, Property 9: candidate-found event emitted only after 3 consecutive high-confidence frames`
    - _Requirements: 7.2_
  - [ ]* 13.13 Write property test — Property 10: sub-threshold frame resets detection window
    - `@given(frames_with_at_least_one_below_threshold)` → assert no event emitted
    - `# Feature: drone-finder, Property 10: sub-threshold frame resets the detection window`
    - _Requirements: 7.3_
  - [ ]* 13.14 Write property test — Property 11: status log retains at least 200 most recent messages
    - `@given(st.integers(min_value=201, max_value=500))` → publish N messages to `SearchManager`; assert log buffer contains exactly the 200 most recent
    - `# Feature: drone-finder, Property 11: status log retains at least the 200 most recent messages`
    - _Requirements: 13.3_

- [x] 14. End-to-end sim demo validation and README finalisation
  - [x] 14.1 Flesh out `README.md` with complete numbered step lists for each section
    - Prerequisites: Python 3.11+, `pip install -r requirements.txt`, place sim images
    - Config file setup: copy `.env.example` → `.env`, fill in values
    - Running in simulation mode: `uvicorn app.main:app --reload`, open `http://localhost:8000`
    - Running with real hardware: set `MODE=real`, set `ESP32_ADDRESS`, connect to drone Wi-Fi
    - _Requirements: 12.4_
  - [x] 14.2 Write end-to-end sim demo checklist as a `## Simulation Demo Checklist` section in `README.md`
    - Items: server starts without error, SIMULATION label visible, search query accepted, status log populates, detection triggers Result_Card, Stop_Button cancels mid-search, "not found" path shows correct Result_Card
    - _Requirements: 11.1, 11.8_

- [x] 15. Checkpoint — all tests pass
  - Run `pytest tests/` and confirm all unit tests and property tests pass.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. RealDroneAdapter and ESP32 integration
  - [x] 16.1 Implement `RealDroneAdapter` in `app/drone/real_adapter.py`
    - Send JSON commands to the ESP32 over the configured `esp32_address` (HTTP or UDP per hardware docs)
    - Time out after 5 s per command; raise `DroneCommandError` on no acknowledgement
    - Expose no hardware details to callers — matches `DroneInterface` ABC exactly
    - _Requirements: 4.3, 4.4_
  - [x] 16.2 Wire `RealDroneAdapter` into `app/main.py` startup
    - When `config.mode == "real"`, instantiate `RealDroneAdapter` instead of `SimDroneAdapter`
    - When `config.mode == "real"`, source video from `ESP32-CAM` MJPEG URL instead of `SimVideoSource`
    - _Requirements: 4.2, 4.3, 6.3_
  - [ ]* 16.3 Write integration smoke test for `RealDroneAdapter` (skipped when no hardware present)
    - Mark test with `pytest.mark.skipif` checking for `MODE=real` in environment
    - Test: `takeoff()` → `hover(1.0)` → `land()` completes without raising `DroneCommandError`
    - _Requirements: 4.4_

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP — the sim demo does not require them to run
- Property tests run with `pytest tests/` (single execution — do NOT use watch mode)
- Checkpoints (tasks 12 and 15) are not coding tasks; they are verification gates before continuing
- Task 16 (RealDroneAdapter) is deliberately last — nothing in tasks 1–15 requires real hardware
- All design decisions (lawnmower algorithm, YOLO-World class-setting, MJPEG approach) are already documented in `design.md`; implementers should read it before starting each task
- `AppConfig` is constructed in task 3 but fully implemented in task 2; keep both files open while implementing config

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "3.1"] },
    { "id": 1, "tasks": ["4.1", "5.1", "5.2"] },
    { "id": 2, "tasks": ["4.2", "6.1", "8.1"] },
    { "id": 3, "tasks": ["7.1", "8.2"] },
    { "id": 4, "tasks": ["9.1"] },
    { "id": 5, "tasks": ["10.1"] },
    { "id": 6, "tasks": ["11.1"] },
    { "id": 7, "tasks": ["13.1", "13.2", "13.3", "13.4", "13.5", "13.6", "13.7", "13.8", "13.9", "13.10", "13.11", "13.12", "13.13", "13.14"] },
    { "id": 8, "tasks": ["14.1", "14.2"] },
    { "id": 9, "tasks": ["16.1"] },
    { "id": 10, "tasks": ["16.2"] },
    { "id": 11, "tasks": ["16.3"] }
  ]
}
```
