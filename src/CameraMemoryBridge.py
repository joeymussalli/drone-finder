import time

from src.Detection import Detection
from src.ObjectMemory import ObjectMemory
from src.Sighting import Sighting
from src.Zone import Zone

class CameraMemoryBridge:

    # Constructor
    def __init__(self, memory: ObjectMemory, zones: list[Zone], min_confidence = 0.50, record_interval_seconds = 2.0):
        self.memory = memory
        self.zones = zones
        self.min_confidence = min_confidence
        self.record_interval_seconds = record_interval_seconds
        self._last_recorded: dict[str, tuple[float, str | None]] = dict()

    # Return the first zone containing the detection's center point.
    def find_zone(self, detection: Detection) -> Zone | None:
        for zone in self.zones:
            if zone.contains_box(detection.x_min, detection.y_min, detection.x_max, detection.y_max):
                return zone
        return None

    # Record one qualifying detection and return its Sighting.
    def record_detection(self, detection: Detection, timestamp: float | None = None) -> Sighting | None:
        if detection.confidence < self.min_confidence:
            return None

        if timestamp is None:
            timestamp = time.time()

        object_label = detection.object_label.strip().lower()
        zone = self.find_zone(detection)
        if zone != None:
            zone_name = zone.name
        else: 
            zone_name = None

        last_recorded = self._last_recorded.get(object_label)
        if last_recorded != None:
            last_timestamp, last_zone_name = last_recorded
            elapsed = timestamp - last_timestamp
            if last_zone_name == zone_name and elapsed < self.record_interval_seconds:
                return None

        sighting = Sighting(object_label=object_label, zone_name=zone_name, confidence=detection.confidence, timestamp=timestamp)
        self.memory.record(sighting)
        self._last_recorded[object_label] = (timestamp, zone_name)
        return sighting

    # Record at most the strongest detection of each label in a frame.
    def process_detections(self, detections: list[Detection], timestamp: float | None = None) -> list[Sighting]:
        strongest_by_label: dict[str, Detection] = dict()
        for detection in detections:
            label = detection.object_label.strip().lower()
            current = strongest_by_label.get(label)
            if current is None or detection.confidence > current.confidence:
                strongest_by_label[label] = detection

        sightings = []
        for detection in strongest_by_label.values():
            sighting = self.record_detection(detection, timestamp)
            if sighting != None:
                sightings.append(sighting)
        return sightings
