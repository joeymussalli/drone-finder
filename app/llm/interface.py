"""Abstract interface for LLM provider calls."""

from abc import ABC, abstractmethod


class LLMError(Exception):
    """Raised when an LLM call fails (missing key, API error, timeout)."""
    pass


class LLMInterface(ABC):
    """Abstract base class for all LLM adapters.

    The full public contract is two operations:
      - confirm: checks whether a given image contains the searched-for item
      - describe: returns a short natural-language location description

    Swap providers by swapping the concrete adapter -- no other code changes.
    """

    @abstractmethod
    async def confirm(self, image_bytes: bytes, query: str) -> tuple[bool, str]:
        """Check whether image_bytes shows the item described by query.

        Returns:
            (confirmed: bool, location_description: str)
            location_description is <=150 characters; empty string if not confirmed.

        Raises:
            LLMError: if the API key is missing, the call fails, or times out.
        """
        ...

    @abstractmethod
    async def describe(self, image_bytes: bytes, query: str) -> str:
        """Return a short location description from the image.

        Returns:
            A single natural-language sentence of <=30 words describing
            where the item appears in the image.

        Raises:
            LLMError: if the API key is missing, the call fails, or times out.
        """
        ...


class NullLLMAdapter(LLMInterface):
    """Fallback adapter used when no API key is configured.

    Always raises LLMError so the search manager logs a clear message
    and resumes the flight plan, rather than crashing at startup.
    """

    async def confirm(self, image_bytes: bytes, query: str) -> tuple[bool, str]:
        raise LLMError("No LLM configured. Set ANTHROPIC_API_KEY in .env to enable confirmation.")

    async def describe(self, image_bytes: bytes, query: str) -> str:
        raise LLMError("No LLM configured. Set ANTHROPIC_API_KEY in .env to enable descriptions.")
