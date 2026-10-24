"""A detector result expressed in camera-frame pixel coordinates."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Detection:
    """One object detection produced from a camera frame.

    The bounding box uses corner coordinates. This matches Zone.contains_box:
    (x_min, y_min) is the top-left corner and (x_max, y_max) is the
    bottom-right corner.
    """

    object_label: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self):
        if not self.object_label.strip():
            raise ValueError("object_label cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.x_min > self.x_max or self.y_min > self.y_max:
            raise ValueError("bounding-box minimums cannot exceed maximums")
