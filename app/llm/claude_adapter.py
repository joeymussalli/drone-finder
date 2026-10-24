"""Claude adapter for the LLM interface using the Anthropic Python SDK."""

import asyncio
import base64
from app.llm.interface import LLMInterface, LLMError
from app.models import AppConfig

import anthropic as anthropic_sdk


class ClaudeAdapter(LLMInterface):
    """LLM adapter that calls Claude via the Anthropic API.
    
    The API key is loaded from AppConfig — never hard-coded.
    All calls use asyncio.to_thread to avoid blocking the event loop.
    """

    TIMEOUT_S = 10.0
    MODEL = "claude-3-5-haiku-20241022"

    def __init__(self, config: AppConfig) -> None:
        if not config.anthropic_api_key or config.anthropic_api_key == "your_key_here":
            raise LLMError("ANTHROPIC_API_KEY is missing or still set to the placeholder value.")
        self._client = anthropic_sdk.Anthropic(api_key=config.anthropic_api_key)

    def _encode_image(self, image_bytes: bytes) -> str:
        return base64.standard_b64encode(image_bytes).decode("utf-8")

    def _call_claude(self, system_prompt: str, image_bytes: bytes, user_text: str) -> str:
        """Synchronous Claude call — run inside asyncio.to_thread."""
        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=256,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": self._encode_image(image_bytes),
                                },
                            },
                            {"type": "text", "text": user_text},
                        ],
                    }
                ],
            )
            return response.content[0].text.strip()
        except anthropic_sdk.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

    async def confirm(self, image_bytes: bytes, query: str) -> tuple[bool, str]:
        """Ask Claude whether the image contains the searched-for item."""
        system = (
            "You are a visual assistant helping to locate a lost item. "
            "Answer concisely and factually."
        )
        user = (
            f'Does this image contain "{query}"? '
            "Reply with YES or NO on the first line, then in one sentence "
            "describe where in the image it is (if YES)."
        )
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(self._call_claude, system, image_bytes, user),
                timeout=self.TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            raise LLMError(f"Claude confirm() timed out after {self.TIMEOUT_S}s.")

        lines = raw.strip().splitlines()
        confirmed = lines[0].strip().upper().startswith("YES")
        location = lines[1].strip() if len(lines) > 1 and confirmed else ""
        # Trim to 150 chars
        location = location[:150]
        return confirmed, location

    async def describe(self, image_bytes: bytes, query: str) -> str:
        """Ask Claude for a short location description of the item in the image."""
        system = (
            "You are a visual assistant. Respond with a single natural-language "
            "sentence of at most 30 words describing where the item is located "
            "in the image. Do not include any preamble."
        )
        user = f'Describe where "{query}" is located in this image in one sentence of 30 words or fewer.'
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(self._call_claude, system, image_bytes, user),
                timeout=self.TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            raise LLMError(f"Claude describe() timed out after {self.TIMEOUT_S}s.")

        # Return first sentence, trimmed
        sentence = raw.strip().split(".")[0].strip()
        if sentence and not sentence.endswith("."):
            sentence += "."
        return sentence
