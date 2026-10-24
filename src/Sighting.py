"""Sighting: one immutable record that an object was seen somewhere at a time."""

import time


class Sighting:
    def __init__(self, object_label, zone_name, confidence, timestamp):
        self.object_label = object_label
        self.zone_name = zone_name
        self.confidence = confidence
        self.timestamp = timestamp

    # How many seconds ago this sighting happened.
    def age_seconds(self, now=None):
        if now is None:
            now = time.time()
        return now - self.timestamp

    # True if this sighting is older than max_age_seconds.
    def is_stale(self, max_age_seconds, now=None):
        return self.age_seconds(now) > max_age_seconds

    # A single 0..1 score for how much to trust this sighting right now.
    def trust_score(self, now=None, half_life_seconds=120.0):
        age = self.age_seconds(now)
        freshness = 0.5 ** (age / half_life_seconds)
        return self.confidence * freshness

    # A short, friendly phrase describing where and when this was seen.
    def describe(self, now=None):
        when = self._time_ago_phrase(self.age_seconds(now))
        if self.zone_name is None:
            return f"I saw your {self.object_label} {when}, but I'm not sure exactly where."
        return f"Your {self.object_label} was on the {self.zone_name}, seen {when}."

    # Turn a number of seconds into a soft, human phrase.
    def _time_ago_phrase(self, seconds):
        if seconds < 10:
            return "just now"
        if seconds < 60:
            return "a few seconds ago"
        minutes = seconds / 60
        if minutes < 2:
            return "about a minute ago"
        if minutes < 60:
            return f"about {int(round(minutes))} minutes ago"
        hours = minutes / 60
        if hours < 2:
            return "about an hour ago"
        return f"about {int(round(hours))} hours ago"

    def __repr__(self):
        return (f"Sighting({self.object_label!r}, zone={self.zone_name!r}, "
                f"conf={self.confidence}, t={self.timestamp})")
