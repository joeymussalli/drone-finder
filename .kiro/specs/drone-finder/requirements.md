# Requirements Document

## Introduction

Drone Finder is an indoor lost-item search system for a hackathon demo. A user types the name of a lost item; a small quadcopter takes off, performs a lawnmower sweep of a configured indoor area, streams live video to a laptop, and uses computer vision plus LLM confirmation to locate the item. When found, the UI shows a photo and a short natural-language description of the item's location. If the item is not found after completing the sweep, the drone lands and reports failure. A simulation mode (fake drone + fake video) lets the team build and test the full software stack before physical hardware is available.

## Glossary

- **System**: The Drone Finder application as a whole, running on the laptop.
- **UI**: The web-based user interface served locally by the System.
- **Command_Box**: The text input control on the UI where the user types a search request.
- **Stop_Button**: The prominent button on the UI that immediately lands the drone.
- **Status_Log**: The scrolling log panel on the UI that displays real-time status messages.
- **Result_Card**: The UI panel shown after a search completes, displaying outcome, photo, and location description.
- **Detection_Box**: A bounding-box overlay drawn on the live video feed when a candidate item is detected.
- **Planner**: The software component that converts a search request into an ordered list of flight moves.
- **Safety_Checker**: The software component that validates a flight plan against bounds and duration limits.
- **Flight_Plan**: An ordered list of moves (takeoff, land, move, turn, hover, stop) produced by the Planner.
- **Drone_Interface**: The abstract software interface through which all flight commands are issued (takeoff, land, move, turn, hover, stop).
- **Real_Drone_Adapter**: The concrete Drone_Interface implementation that sends commands to the ESP32.
- **Sim_Drone_Adapter**: The concrete Drone_Interface implementation used in simulation mode.
- **Vision_Module**: The software component that processes video frames to detect and classify items.
- **LLM_Interface**: The abstract interface through which all LLM calls are made.
- **Claude_Adapter**: The concrete LLM_Interface implementation that calls Claude via the Anthropic API.
- **Video_Stream**: The MJPEG or WebSocket stream of frames from the ESP32-CAM (real) or Sim_Video_Source (simulation).
- **Sim_Video_Source**: The simulation component that serves still images as a fake video stream, cycling through images as the simulated drone moves.
- **Search_Area**: The rectangular bounding box, in metres, within which the drone is permitted to fly; defined in the config file with a default of 3 m × 3 m.
- **Sweep_Pattern**: The lawnmower (bidirectional row) path that covers the Search_Area systematically.
- **Confidence_Window**: Three consecutive video frames in which the Vision_Module detects the target item above the confidence threshold.
- **Config_File**: The configuration file (e.g. `.env` or `config.yaml`) that holds API keys, Search_Area dimensions, and runtime mode (real / simulation).

---

## Requirements

### Requirement 1: Search Request Input

**User Story:** As a user, I want to type what I am looking for so that the drone knows which item to search for.

#### Acceptance Criteria

1. THE UI SHALL display a Command_Box that accepts free-text input of up to 200 characters.
2. WHEN the user submits a non-empty search request, THE System SHALL pass the request text to the Planner and THE UI SHALL display a visual indicator that a search is in progress.
3. IF the user submits an empty search request, THEN THE UI SHALL display an inline validation message indicating that search text is required, SHALL clear that message when the user modifies the Command_Box input, and SHALL NOT begin a search.
4. WHILE a search is in progress, THE UI SHALL disable the Command_Box to prevent a second concurrent search.
5. WHEN the search completes or is terminated, THE UI SHALL re-enable the Command_Box.

---

### Requirement 2: Flight Planning

**User Story:** As a developer, I want the Planner to turn a search request into a safe, concrete flight plan so that the drone follows a predictable path.

#### Acceptance Criteria

1. WHEN a search request is received, THE Planner SHALL generate a Flight_Plan consisting solely of the primitive moves: takeoff, land, move, turn, hover, and stop.
2. WHEN a search request is received, THE Planner SHALL generate a Flight_Plan whose Sweep_Pattern covers every cell of the Search_Area exactly once, with no cell visited more than once and no cell omitted.
3. THE Planner SHALL read the Search_Area dimensions from the Config_File.
4. IF the Config_File contains no Search_Area dimensions, THEN THE Planner SHALL use a default Search_Area of 3 m × 3 m.
5. IF the Config_File cannot be read, THEN THE Planner SHALL use a default Search_Area of 3 m × 3 m and record an error indicating the Config_File was inaccessible.
6. WHEN a Flight_Plan is generated, THE Safety_Checker SHALL validate the plan and produce a pass or fail result before any move primitive is executed.
7. IF THE Safety_Checker produces a fail result, THEN THE Planner SHALL not execute the Flight_Plan and SHALL surface an error indicating the plan failed safety validation.

---

### Requirement 3: Safety Validation

**User Story:** As a developer, I want a safety check on every plan so that the drone cannot fly out of bounds or run indefinitely.

#### Acceptance Criteria

1. WHEN the Safety_Checker validates a Flight_Plan, THE Safety_Checker SHALL reject any plan that would move the drone outside the Search_Area boundary.
2. WHEN the Safety_Checker validates a Flight_Plan, THE Safety_Checker SHALL reject any plan whose total estimated flight time exceeds 5 minutes.
3. IF the Safety_Checker rejects a Flight_Plan, THEN THE System SHALL land the drone if airborne, and THE System SHALL append a rejection reason to the Status_Log within 1 second of rejection.
4. WHEN a Flight_Plan passes validation, THE Safety_Checker SHALL return the validated plan unchanged to the caller.
5. IF the Safety_Checker receives a Flight_Plan with no waypoints or a null Flight_Plan, THEN THE Safety_Checker SHALL reject the plan and THE System SHALL append an error message indicating an invalid plan to the Status_Log.

---

### Requirement 4: Drone Control Interface

**User Story:** As a developer, I want all flight commands issued through a single abstract interface so that real hardware and simulation can be swapped without changing other components.

#### Acceptance Criteria

1. THE Drone_Interface SHALL expose exactly these operations: takeoff, land, move(direction, distance), turn(angle), hover(duration), and stop; where direction is one of {forward, backward, left, right}, distance is in the range 0.1–500.0 m, angle is in the range -360–360 degrees, and duration is in the range 0.1–300.0 seconds.
2. WHILE the System runs in simulation mode, THE System SHALL use the Sim_Drone_Adapter to execute all Drone_Interface calls.
3. WHILE the System runs in real mode, THE System SHALL use the Real_Drone_Adapter to execute all Drone_Interface calls.
4. THE Real_Drone_Adapter SHALL send commands to the ESP32 over the configured network address and SHALL consider a command failed if no acknowledgement is received within 5 seconds, without exposing hardware details to other components.
5. IF a Drone_Interface call fails, THEN THE System SHALL log the failure including the operation name and failure reason to the Status_Log and SHALL attempt to issue a land command before halting the search.
6. IF the safety land command issued after a Drone_Interface call failure does not succeed within 10 seconds, THEN THE System SHALL log a critical error to the Status_Log indicating the drone may be uncontrolled.

---

### Requirement 5: Stop Button

**User Story:** As a user, I want a prominent stop button so that I can land the drone immediately at any point.

#### Acceptance Criteria

1. THE UI SHALL display a Stop_Button that is visible and enabled at all times while the application is running.
2. WHEN the user activates the Stop_Button, THE System SHALL issue a stop command followed immediately by a land command via the Drone_Interface within 500 ms of the user action.
3. WHEN the Stop_Button is activated, THE System SHALL cancel any in-progress search and SHALL update the Status_Log with a message indicating the search was stopped by the user.
4. IF the Drone_Interface does not acknowledge the stop command within 500 ms of the user action, THEN THE System SHALL update the Status_Log with an error message indicating the stop command failed and SHALL retain the last known drone state.
5. IF the Drone_Interface does not acknowledge the land command within 10 seconds of the stop command being issued, THEN THE System SHALL update the Status_Log with an error message indicating the land command failed.

---

### Requirement 6: Live Video Feed

**User Story:** As a user, I want to see live video from the drone so that I can monitor the search in real time.

#### Acceptance Criteria

1. THE UI SHALL display the Video_Stream as a continuously updating video panel at a minimum of 15 frames per second alongside the Status_Log.
2. WHILE the Vision_Module detects a candidate item, THE UI SHALL overlay a Detection_Box on the video panel at the item's bounding-box coordinates; WHEN the Vision_Module no longer detects the candidate item, THE UI SHALL remove the Detection_Box.
3. WHEN the System runs in real mode, THE System SHALL source the Video_Stream from the ESP32-CAM over Wi-Fi.
4. WHEN the System runs in simulation mode, THE System SHALL source the Video_Stream from the Sim_Video_Source.
5. IF the Video_Stream is interrupted for more than 3 seconds, THEN THE System SHALL display a "Video lost" warning in the Status_Log.
6. IF the Video_Stream is interrupted for more than 3 seconds and the drone is airborne, THEN THE System SHALL issue a hover command to hold the drone in place.

---

### Requirement 7: Vision Detection

**User Story:** As a developer, I want the Vision_Module to detect the target item in the video feed reliably so that false positives are minimised.

#### Acceptance Criteria

1. WHEN a video frame is received, THE Vision_Module SHALL analyse the frame and, if the target item is detected, return bounding-box coordinates and a confidence score in the range 0.0 to 1.0 for each detected instance; if no instance is detected, THE Vision_Module SHALL return an empty result for that frame.
2. WHEN the Vision_Module detects the target item with a confidence score of 0.7 or above in each of 3 consecutive frames, THE Vision_Module SHALL emit a candidate-found event carrying the bounding-box coordinates and confidence score of the frame with the highest confidence score among those 3 frames; if two or more frames share the highest score, THE Vision_Module SHALL select the earliest of those frames.
3. IF any frame in the current sequence of consecutive detections has a confidence score below 0.7, THEN THE Vision_Module SHALL reset the consecutive-detection count to zero and SHALL NOT emit a candidate-found event.
4. THE Vision_Module SHALL process each incoming frame within 200 ms on the host laptop.

---

### Requirement 8: LLM Confirmation

**User Story:** As a developer, I want an LLM to confirm a candidate detection so that the System avoids false positives before declaring the item found.

#### Acceptance Criteria

1. WHEN the Vision_Module emits a candidate-found event, THE System SHALL send the frame with the highest confidence score from that event and the original search request text to the LLM_Interface for confirmation.
2. WHEN the LLM_Interface returns a positive confirmation, THE System SHALL declare the item found and hover the drone in place.
3. WHEN the LLM_Interface returns a positive confirmation, THE System SHALL display the Result_Card.
4. WHEN the LLM_Interface returns a negative confirmation, THE System SHALL resume the Flight_Plan from the current position.
5. THE LLM_Interface SHALL expose a confirm(image, query) operation that returns a boolean result and a location description string of no more than 150 characters.
6. IF the LLM_Interface call fails or does not return a result within 10 seconds, THEN THE System SHALL resume the Flight_Plan from the current position and log a confirmation-timeout event to the Status_Log.
7. WHERE the Claude_Adapter is enabled, THE System SHALL load the Anthropic API key exclusively from the Config_File and SHALL NOT hard-code the key in source files.
8. IF the Claude_Adapter is enabled and the Anthropic API key is absent from the Config_File, THEN THE System SHALL abort the search session and display an error indicating that the API key is missing.

---

### Requirement 9: LLM Provider Interface

**User Story:** As a developer, I want all LLM calls routed through an abstract interface so that the LLM provider can be swapped (e.g. from Claude to Amazon Bedrock) without modifying other components.

#### Acceptance Criteria

1. THE LLM_Interface SHALL define a confirm(image, query) operation that returns a boolean result and a describe(image, query) operation that returns a text description as its full public contract.
2. IF the System is configured to use Claude, THEN THE System SHALL use the Claude_Adapter to fulfil all LLM_Interface calls.
3. THE Claude_Adapter SHALL call the Anthropic API using the key from the Config_File.
4. WHERE an alternative LLM provider is configured, THE System SHALL use the corresponding adapter without changes to the Vision_Module or Planner.
5. IF the Config_File does not contain a valid Anthropic API key, THEN THE Claude_Adapter SHALL reject the call and return an error indicating that the API key is missing or invalid without invoking the Anthropic API.
6. IF the Anthropic API returns an error response or is unreachable, THEN THE Claude_Adapter SHALL propagate an error to the caller indicating that the LLM call failed.

---

### Requirement 10: Result Display

**User Story:** As a user, I want to see a clear result when the drone finds (or fails to find) my item so that I know the search outcome.

#### Acceptance Criteria

1. WHEN the item is confirmed found, THE UI SHALL display a Result_Card containing a "Found it" heading, the best-scoring frame as a photo, and the LLM-generated location description.
2. WHEN the drone completes the full Sweep_Pattern without a confirmed detection, THE System SHALL land the drone and THE UI SHALL display a Result_Card with a "Not found" message.
3. IF the drone fails to land within 30 seconds of completing the Sweep_Pattern, THEN THE System SHALL display an error message indicating a landing failure and preserve the Result_Card with the "Not found" message.
4. THE LLM_Interface describe operation SHALL return a location description of no more than 30 words written as a single natural-language sentence.
5. WHEN the Result_Card is displayed, THE System SHALL append the outcome summary to the Status_Log within 2 seconds of the Result_Card becoming visible.
6. IF the LLM_Interface describe operation fails to return a location description, THEN THE UI SHALL display the Result_Card with a "Found it" heading and the best-scoring frame photo, substituting the location description with an error message indicating the description is unavailable.

---

### Requirement 11: Simulation Mode

**User Story:** As a developer, I want a simulation mode so that the full software stack can be built and demonstrated before the physical hardware is ready.

#### Acceptance Criteria

1. WHEN simulation mode is enabled in the Config_File and the application starts, THE System SHALL replace the Real_Drone_Adapter with the Sim_Drone_Adapter and the live ESP32-CAM stream with the Sim_Video_Source for the duration of that session.
2. THE Sim_Drone_Adapter SHALL accept all Drone_Interface calls and return a valid Drone_Interface response indicating success without communicating with any hardware.
3. WHEN the Sim_Drone_Adapter receives a Drone_Interface call, THE Sim_Drone_Adapter SHALL log the command name and its parameters to the Status_Log.
4. THE Sim_Video_Source SHALL maintain a set of at least 3 still images, where at least one image contains the target item and at least one image does not contain the target item.
5. WHEN the simulated drone enters a grid cell that is not the target item cell configured in the Config_File, THE Sim_Video_Source SHALL serve an image that does not contain the target item.
6. WHEN the simulated drone enters the grid cell designated as the target item cell in the Config_File, THE Sim_Video_Source SHALL serve the image that contains the target item.
7. WHEN the simulated drone moves to a new grid cell during a sweep, THE Sim_Video_Source SHALL update the served image within 500 milliseconds so that the UI video panel reflects the drone's current position along the Sweep_Pattern path.
8. WHILE simulation mode is active, THE UI SHALL display a "SIMULATION" label that is persistently visible on the video panel.

---

### Requirement 12: Configuration and Setup

**User Story:** As a teammate, I want to run the project from the README with minimal setup so that onboarding takes less than 10 minutes.

#### Acceptance Criteria

1. THE System SHALL load all runtime configuration (API keys, Search_Area dimensions, network addresses, operating mode) from a single Config_File.
2. THE System SHALL provide a template Config_File (e.g. `.env.example`) that lists every required key with placeholder values and a one-line comment.
3. WHEN a required configuration key is missing at startup, THE System SHALL log an error that names the missing key and SHALL exit with a non-zero exit code before attempting any network or hardware operation.
4. THE System SHALL include a README.md that describes, in order: prerequisites, config file setup, running in simulation mode, and running with real hardware; each section SHALL contain a numbered step list.

---

### Requirement 13: Status Logging

**User Story:** As a user, I want a live status log so that I can follow what the drone is doing at every step.

#### Acceptance Criteria

1. THE Status_Log SHALL display timestamped messages for each of the following events: search started, each flight move issued, item detection confidence update (only when the confidence score changes by 5% or more), LLM confirmation result, item found, item not found, search stopped, and any error.
2. THE UI SHALL automatically scroll the Status_Log to the latest message unless the user has manually scrolled up, in which case THE UI SHALL not auto-scroll until the user scrolls back to the bottom.
3. THE Status_Log SHALL retain at least the 200 most recent messages during a session.

---

### Requirement 14: Voice Input (Stretch Goal)

**User Story:** As a user, I want to speak my search request so that I can use the system hands-free.

#### Acceptance Criteria

1. WHERE voice input is enabled in the Config_File, THE UI SHALL display a microphone button adjacent to the Command_Box.
2. WHERE voice input is enabled, WHEN the user activates the microphone button, THE System SHALL capture audio and transcribe it into the Command_Box as editable text before the search begins; audio capture SHALL terminate when the user deactivates the microphone button or after 30 seconds, whichever comes first.
3. WHERE voice input is disabled, THE UI SHALL hide the microphone button and SHALL NOT load any audio-capture library.
4. IF voice transcription fails, THEN THE UI SHALL display an inline error message indicating that transcription failed and SHALL leave the Command_Box empty so the user can type instead.
