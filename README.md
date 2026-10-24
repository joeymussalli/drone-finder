# Drone Finder

An indoor lost-item search system: type what you're looking for and a small quadcopter sweeps the area using YOLO-World computer vision and Claude LLM confirmation to find it. A simulation mode lets you run the full demo without any hardware.

## Prerequisites

1. Install **Python 3.11 or newer** (tested on 3.11+). Download from https://python.org
2. Clone or download this repository to your machine.
3. Open a terminal in the project root (`drone-finder/`).
4. Install all dependencies:
   ```
   pip install -r requirements.txt
   ```
5. The first time YOLO-World runs it will download the model weights (~50 MB). This happens automatically on the first search.

## Config File Setup

1. Copy the example config:
   ```
   copy .env.example .env
   ```
2. Open `.env` in a text editor.
3. Set `ANTHROPIC_API_KEY` to your Anthropic API key (get one at https://console.anthropic.com).
4. Leave all other values at their defaults for simulation mode:
   - `MODE=sim`
   - `SEARCH_AREA_WIDTH_M=3.0`
   - `SEARCH_AREA_DEPTH_M=3.0`
   - `SIM_TARGET_CELL=1,2` (the grid cell where the target item appears in simulation)
   - `STEP_SIZE_M=0.5`
5. Save the file.

> **Note:** The sim demo runs without an API key — Claude is only called when YOLO detects a candidate item. If the key is missing, searches log a warning and resume without LLM confirmation.

## Running in Simulation Mode

1. Make sure you have completed the config setup above (`MODE=sim` in `.env`).
2. Generate the simulation images (only needed once after first install):
   ```
   python sim_images/generate_sim_images.py
   ```
3. Start the server:
   ```
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
4. Open your browser and go to: http://127.0.0.1:8000
5. You should see the Drone Finder UI with a **SIMULATION** label on the video feed.
6. Type a search query (e.g. `blue water bottle`) and press **Search** or Enter.
7. Watch the status log as the simulated drone sweeps the area.
8. Use the red **STOP** button at any time to land immediately.

## Sim Demo Photos

Simulation mode serves real photos from `sim_images/` so the vision model
actually finds things. The repo ships with a working set already: five
item photos, three plain room photos, and a `sim_layout.json` manifest
that pins each item to a fixed cell on the room map.

Out of the box you can search for any of these and the drone will find it
at its spot on the map:

- `water bottle`, `backpack`, `coffee mug`, `laptop`, and `cell phone`.
  Each sits in a different spot (rows 3-6 of the map), so each search runs for
  a good while before the find.

To customise, edit `sim_images/sim_layout.json`:

1. Add your photo to `sim_images/` (any filename; `.jpg`/`.jpeg`/`.png`).
2. Add an entry under `items` with its `name`, `file`, `cell` ([col,row]
   on the grid), and `aliases` (search phrases that should match it).
3. List plain room photos under `plain`; these fill every non-item cell.
4. Pick an item name that YOLO-World recognises well (water bottle,
   backpack, laptop, coffee mug, cell phone all work well) and search it.
   Detection uses the yolov8m-worldv2 model at a 0.5 confidence threshold.

The item photo only appears at its cell when the active search matches its
aliases, so searching "laptop" never false-triggers on the bottle photo.
Photo credits and licenses are in `sim_images/CREDITS.md`.

> **Legacy mode:** if there is no `sim_layout.json`, the app falls back to a
> single `target.*` photo served at `SIM_TARGET_CELL`, with other images as
> plain fillers.

## Running with the ESP32-CAM

There are three modes, set by `MODE` in `.env`:

| MODE | Camera | Drone | Use it for |
|---|---|---|---|
| `sim` | demo photos | simulated | judge demo with no hardware |
| `camera` | live ESP32-CAM | simulated | testing detection by holding the camera |
| `real` | live ESP32-CAM | real (ESP32) | the full flight |

The ESP32-CAM makes its own Wi-Fi network (`DroneCamera`, password `drone12345`)
and streams MJPEG at `http://192.168.4.1:81/stream`.

1. Connect the laptop to the `DroneCamera` Wi-Fi. **The laptop loses internet
   while on it** (no Claude confirmation step; the app still works). Use phone
   USB tethering for internet if you need both.
2. Close any browser tab showing the camera page. The ESP32 serves one stream
   viewer at a time.
3. Check the stream:
   ```
   python camera_check.py
   python camera_check.py --detect "water bottle"
   ```
   It prints the resolution and frame rate and saves `camera_snapshot.jpg`.
4. In `.env`, set `MODE=camera` (or `MODE=real` once flight control works).
   Set `CAMERA_URL` if the stream address is different.
5. Start the server (`run.bat`) and open http://127.0.0.1:8000. The camera
   panel shows the live feed right away; `/camera/status` reports the connection.
6. Search for an item and point the camera at it.

## Simulation Demo Checklist

Use this checklist to verify the sim demo is working end-to-end before a live presentation:

- [ ] Server starts without errors: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- [ ] Browser opens http://127.0.0.1:8000 and shows the Drone Finder UI
- [ ] **SIMULATION** label is visible on the video panel
- [ ] Submitting an empty search query shows an inline validation message (does not start a search)
- [ ] Typing a query and pressing Search starts the search: status log populates with move messages
- [ ] Video panel updates as the simulated drone moves through the sweep
- [ ] When the drone reaches the target cell (configured by `SIM_TARGET_CELL`), a detection badge appears
- [ ] If an API key is set, the LLM confirmation fires and a **Found it!** Result Card appears with a photo
- [ ] If no API key is set, the search completes with a **Not found** Result Card after the full sweep
- [ ] Pressing the red **STOP** button mid-search immediately cancels the search and logs "Search stopped by user"
- [ ] After a search completes, the **Search Again** button resets the UI for a new query
