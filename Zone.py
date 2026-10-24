"""Zone: a named rectangular region of the camera frame.

With a single fixed camera, we don't know an object's real-world (x, y, z)
position. Instead we divide the camera image into named regions (e.g.
"counter", "table", "floor") and report which region an object was seen in.
A Zone is one such region, defined by pixel bounds in the frame.
"""


class Zone:
    # Constructor
    def __init__(self, name, x_min, y_min, x_max, y_max):
        self.name = name # Name of rectangular region
        self.x_min, self.y_min = x_min, y_min # Top left corner of rectangular region
        self.x_max, self.y_max = x_max, y_max # Bottom Right corner of rectangular region

    # Returns Boolean. True if point is within boundaries. False Otherwise
    def contains_point(self, x, y):
        return (self.x_min <= x <= self.x_max) and (self.y_min <= y <= self.y_max)

    # Returns Boolean. True if rectangle is within boundaries, with a focus on the center point. False Otherwise
    def contains_box(self, x_min, y_min, x_max, y_max):
        x_center = (x_min + x_max) / 2
        y_center = (y_min + y_max) / 2
        return self.contains_point(x_center, y_center)

    # Debug-friendly string representation
    def __repr__(self):
        return f"Zone({self.name!r}, [{self.x_min},{self.y_min}]-[{self.x_max},{self.y_max}])"
