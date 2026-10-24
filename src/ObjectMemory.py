"""ObjectMemory: the spatial memory that remembers where objects were seen."""

from src.Sighting import Sighting

class ObjectMemory:
    # Constructor
    def __init__(self):
        self.memory = dict();

    # Store a new sighting under its object label.
    def record(self, sighting):
        if (sighting.object_label not in self.memory):
            self.memory[sighting.object_label] = []
        self.memory[sighting.object_label].append(sighting)

    # Return the most recent sighting for an object, or None.
    def latest(self, object_label):
        if (object_label not in self.memory):
            return None
        return self.memory[object_label][-1]   # last element is the newest

    # Return the full list of sightings for an object (oldest first).
    def history(self, object_label):
        if (object_label not in self.memory):
            return []
        return self.memory[object_label]

    # Return the set/list of object labels we have ever recorded.
    def all_objects(self):
        return list(self.memory.keys())

    # Return the sighting we most TRUST right now, or None if none clear the bar.
    def best(self, object_label, now=None, min_trust=0.25):
        most_trusted = None
        most_trusted_score = 0.0
        for sighting in self.history(object_label):
            score = sighting.trust_score(now)
            if score >= min_trust and score >= most_trusted_score:
                most_trusted = sighting
                most_trusted_score = score
        return most_trusted

    # Produce a plain-language answer to "where is my <object_label>?".
    def answer(self, object_label, now=None, min_trust=0.25):
        sighting = self.best(object_label, now, min_trust)
        if (sighting == None):
            return f"I'm sorry, I haven't seen your {object_label} recently."
        return sighting.describe(now)
