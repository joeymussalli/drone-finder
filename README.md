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

Simulation mode serves real photos from the `sim_images/` folder so the
vision model can actually find something during a demo. Drop your own
JPGs into `sim_images/`:

1. Add **one** photo named `target.jpg` that clearly shows the item you
   will search for (e.g. a blue water bottle on a table). This is the
   photo the drone "sees" when it reaches the target cell.
2. Add **one or more** other room photos with any filename (e.g.
   `room1.jpg`, `hallway.jpg`, `desk.jpg`). These are shown while the
   drone sweeps the rest of the area and must NOT contain the item.
3. Supported extensions: `.jpg`, `.jpeg`, `.png`. Any file named
   `target.*` is the target; every other image is treated as a
   non-target room photo.
4. Set `SIM_TARGET_CELL` in `.env` to the grid cell where the target
   photo should appear (default `1,2`). The drone must pass through this
   cell during the sweep for the item to be found.
5. Search for the item by name in the UI (e.g. `blue water bottle`). The
   detector runs against whichever photo is being served for the drone's
   current cell.

> **Note:** The repo ships with solid-colour placeholder images so the
> server starts out of the box, but nothing can be detected in them.
> Replace them with real photos for a working find. You need at least a
> `target.jpg` plus one other photo.

## Running with Real Hardware

1. Connect your laptop to the ESP32's Wi-Fi network (or same local network).
2. In `.env`, set:
   - `MODE=real`
   - `ESP32_ADDRESS=<IP address of your ESP32>` (e.g. `192.168.4.1`)
3. Make sure the ESP32-CAM stream URL is reachable from the laptop.
4. Start the server:
   ```
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
5. Open your browser and go to: http://127.0.0.1:8000
6. The live video feed from the ESP32-CAM will appear in the video panel.
7. Type a search query and press **Search**.
8. The drone will take off and begin the lawnmower sweep.
9. Use the red **STOP** button at any time to land immediately.

> **Tip:** If the drone does not respond, check the `ESP32_ADDRESS` in `.env` and verify the ESP32 firmware is running and connected.

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
