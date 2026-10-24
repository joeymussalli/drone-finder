# RECALL Project Context

RECALL is an assistive Python system that turns camera detections into searchable object-sighting memory. It is designed to help people experiencing memory difficulties find commonly misplaced items.

## Project structure

- Keep reusable domain, memory, and query logic in `src/`.
- Keep executable demos and command-line interfaces in `scripts/`.
- Keep camera transport and presentation concerns outside the core memory classes.
- Preserve the separation between `Detection`, `Sighting`, `ObjectMemory`, `CameraMemoryBridge`, and `QueryService`.

## Camera and location rules

- The camera is carried by a moving drone.
- Image-space positions and bounding boxes are relative to the camera and must not be presented as persistent room locations.
- Only store a non-null `resolved_object_location` when a stable location is supplied by a staged demo area or by the team's synchronized localization system.
- Do not treat the drone's position as the object's position unless the camera footprint and mapping assumptions make that relationship valid.
- Prefer an honest unknown-location response over an unsupported location claim.

## Uncertainty behavior

- Preserve detector confidence on every `Sighting`.
- Use time decay when deciding whether a sighting is trustworthy enough to report.
- Reject weak detections and avoid filling history with repeated detections from adjacent frames.
- User-facing responses should clearly communicate when RECALL is uncertain.

## Development conventions

- Use Python 3.13 and the project-local `.venv`.
- Add type hints where they materially improve comprehension, especially optional return values and collections.
- Keep the implementation simple enough to explain during the hackathon presentation.
- Do not commit model weight files or virtual environments.
- Update `README.md` whenever setup or demo commands change.

## Validation

Compile the source and scripts:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts
```

Check camera connectivity before loading the model:

```powershell
.\.venv\Scripts\python.exe -m scripts.camera_recall --check-camera
```

Run the staged live demo:

```powershell
.\.venv\Scripts\python.exe -m scripts.recall_demo --resolved-location "demo table"
```
