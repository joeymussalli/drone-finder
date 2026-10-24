# drone-finder
Hackachusetts 2026: a drone that finds items for people

## Connect one USB camera to RECALL memory

Create the environment and install the pinned camera dependencies once:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-camera.txt
```

The camera pipeline then uses the Windows Python 3.13 virtual environment in `.venv`.
From the repository root, find the camera index:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall --scan-cameras
```

Check one index without loading the AI model:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall --camera-index 0 --check-camera
```

Start object detection and memory recording:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall --camera-index 0
```

The first detection run downloads the YOLO-World model weights. In the camera
window, press **M** to print remembered locations and **Q** (or Escape) to quit.
Change target objects by passing names after `--objects`, for example:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall --camera-index 0 --objects keys phone glasses
```

The current demo divides the fixed camera image into `left side`, `center`, and
`right side` zones. These can later be replaced with staged, semantic regions
such as `desk` and `side table` without changing `Sighting` or `ObjectMemory`.
