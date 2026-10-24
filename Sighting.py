class Sighting:
    def __init__(self, object_label, zone_name, confidence, timestamp):
        self.object_label = object_label
        self.zone_name = zone_name
        self.confidence = confidence
        self.timestamp = timestamp