from src.ObjectMemory import ObjectMemory


class QueryService:
    def __init__(self, memory: ObjectMemory):
        """Hold the shared ObjectMemory this service reads from.

        The memory is passed in (not created here) so the camera side and the
        query side use the SAME live memory -- one is writing sightings while
        this one answers questions.

        TODO (you): store memory on self.
        """
        # TODO: assign self.memory
        pass

    def find_object_label(self, question: str) -> str | None:
        """Work out which remembered object the question is about.

        Start simple: scan the question text for any label that already exists
        in memory (self.memory.all_objects()). If "keys" is a known object and
        the question contains "keys", return "keys".

        Args:
            question: the raw user text, e.g. "where are my keys?".

        Returns:
            the matched object label, or None if nothing in memory matches.

        TODO (you): lowercase the question, then loop over
        self.memory.all_objects() and return the first label that appears in
        the question. Return None if none match. (Normalize case so "Keys"
        and "keys" still match.)
        """
        # TODO: match a known object label inside the question
        pass

    def answer_question(self, question: str, now: float | None = None) -> str:
        """Turn a full question into a user-facing answer string.

        This is the one method a caller (terminal loop or web route) actually
        uses. It ties find_object_label to ObjectMemory.answer.

        Args:
            question: the raw user text.
            now: current time, forwarded to ObjectMemory for testability.

        Returns:
            a plain-language answer, always a string (never None).

        TODO (you): call self.find_object_label(question). If it returns None,
        return a gentle "I'm not sure which item you mean" style message
        (optionally listing what you DO know via self.memory.all_objects()).
        Otherwise return self.memory.answer(label, now).
        """
        # TODO: resolve the label, then delegate to memory.answer (or a kind fallback)
        pass
