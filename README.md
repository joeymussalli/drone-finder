# drone-finder
Hackachusetts 2026: a drone that finds items for people

## Connect the ESP32-CAM to RECALL memory

Create the environment and install the pinned camera dependencies while the
computer still has internet access:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-camera.txt
```

The camera pipeline uses the Windows Python 3.13 virtual environment in `.venv`.

### Connect to the camera

The ESP32-CAM creates its own Wi-Fi network:

- Network name: `DroneCamera`
- Password: `drone12345`
- Camera webpage: <http://192.168.4.1/>
- MJPEG stream: <http://192.168.4.1:81/stream>

Open Windows Wi-Fi settings and connect to `DroneCamera` using the password
above. Windows may report **No internet**; that is normal for the ESP32 access
point. The computer must remain connected to this network while RECALL runs.

Open <http://192.168.4.1/> in a browser first if you want to check whether the
ESP32 CameraWebServer is responding. The script reads the video from port 81,
not from the webpage on port 80. Avoid leaving the browser's live stream open
while running RECALL because some ESP32-CAM firmware supports only one stream
client reliably.

From the repository root, verify that Python can receive and decode one frame
without loading the AI model:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall --check-camera
```

Start object detection and memory recording:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall
```

The default stream is `http://192.168.4.1:81/stream`. If the ESP32 address or
route changes, override it explicitly:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall --stream-url "http://192.168.4.1:81/stream"
```

The script retries a dropped stream three times by default. While testing an
unstable connection, you can adjust the retry count, delay, and HTTP timeout:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall --connection-attempts 10 --retry-delay 2 --read-timeout 15
```

In the camera window, press **M** to print remembered locations and **Q** (or
Escape) to quit. Change target objects by passing names after `--objects`:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall --objects keys phone glasses
```

Because the camera moves with the drone, bounding-box positions such as "left"
or "center" describe only the current image and are **not** stored as object
locations. This standalone runner records that an object was seen, but leaves
its location unknown.

When this branch is integrated with the team's main app, pass a stable,
capture-synchronized location into `CameraMemoryBridge.process_detections` as
`resolved_object_location`. Only pass an actual resolved object location—not
merely the drone's current position—unless the camera footprint and grid model
make those equivalent. Metric localization would additionally require camera
pose/calibration and depth or a justified surface-intersection model.

### Connection troubleshooting

If `--check-camera` fails:

```powershell
Test-NetConnection 192.168.4.1 -Port 81
curl.exe --max-time 5 --verbose "http://192.168.4.1:81/stream" --output NUL
```

A successful stream normally reports HTTP success and a multipart MJPEG content
type. The `curl.exe` command timing out after receiving bytes is expected because
an MJPEG stream does not end. If the webpage works but port 81 does not, confirm
that the ESP32 CameraWebServer sketch started its stream server and that its
serial output reports the expected IP address.

## Run the live RECALL demo

Connect Windows to the `DroneCamera` Wi-Fi network, close any browser tab using
the live stream, and run this command from a PowerShell terminal at the
repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.recall_demo --resolved-location "demo table"
```

The `demo table` label is valid only when the entire search is deliberately
confined to that staged area. Wait until a green detection box appears and the
terminal prints `Remembered:` before asking about an object.

With the video window focused:

- Press **A**, type a question directly in the video window, and press Enter.
- Press any key after reading the answer to resume the camera stream.
- Press **M** to print all currently remembered objects.
- Press **Q** or Escape to stop.

For example, after the camera recognizes keys, press **A** and enter
`where are my keys`. The detector and query service share the same live
`ObjectMemory`, so the answer uses the sighting recorded by the camera.