from src.ObjectMemory import ObjectMemory


class QueryService:
    # Constructor
    def __init__(self, memory: ObjectMemory):
        self.memory = memory

    # Work out which remembered object the question is about.
    def find_object_label(self, question: str) -> str | None:
        question_lower = question.lower()
        for label in self.memory.all_objects():
            if label in question_lower:       # handles multi-word labels like "remote control"
                return label
        return None

    def answer_question(self, question: str, now: float | None = None) -> str:
        label = self.find_object_label(question)
        if (label == None):
            return "I'm not sure which item you mean"
        return self.memory.answer(label, now)