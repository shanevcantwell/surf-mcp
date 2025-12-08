"""
Gemini Visual Grounding Adapter.

Uses Google's Gemini vision models for visual grounding.
Alternative to the OpenAI adapter when using Gemini API directly.
"""

import base64
import io
import json
import logging
import os
import re
from typing import Optional, Tuple

from PIL import Image

from .base import LocateResult, VisualGrounder

logger = logging.getLogger(__name__)


class GeminiVisualGrounder(VisualGrounder):
    """
    Visual grounding using Google Gemini vision API.

    Uses gemini-2.0-flash or similar multimodal models.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize Gemini visual grounder.

        Args:
            api_key: Google API key (defaults to GOOGLE_API_KEY env var)
            model: Model to use (defaults to gemini-2.0-flash)
        """
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self.model = model or os.environ.get(
            "NAVIGATOR_LLM_MODEL", "gemini-2.0-flash"
        )
        self._client = None

    def _get_client(self):
        """Get or create Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
            except ImportError:
                raise ImportError(
                    "google-generativeai package required. "
                    "Install with: pip install google-generativeai"
                )

            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model)

        return self._client

    async def locate(self, description: str, screenshot_b64: str) -> LocateResult:
        """Locate element by description using Gemini vision."""
        prompt = f"""You are a visual UI element locator.

Given the screenshot, find the element described as: "{description}"

Return a JSON object with:
- found: boolean (true if you can see the element)
- x: integer x-coordinate (center of element, pixels from left)
- y: integer y-coordinate (center of element, pixels from top)
- confidence: float 0.0-1.0 (how confident you are)
- reasoning: brief explanation of how you identified it

If the element is not visible, return found=false with null coordinates.

IMPORTANT: Return ONLY the JSON object, no markdown or explanation."""

        try:
            result = await self._invoke_vision(prompt, screenshot_b64)
            return result
        except Exception as e:
            logger.error(f"Gemini visual grounding failed: {e}")
            return LocateResult(
                found=False,
                reasoning=f"Error: {e}",
            )

    async def verify(self, description: str, screenshot_b64: str) -> LocateResult:
        """Verify element exists."""
        return await self.locate(description, screenshot_b64)

    async def _invoke_vision(self, prompt: str, image_b64: str) -> LocateResult:
        """Call Gemini vision API and parse response."""
        import asyncio

        client = self._get_client()

        # Decode image
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]

        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes))

        # Gemini's generate_content is sync, run in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.generate_content([prompt, img]),
        )

        text = response.text
        return self._parse_response(text)

    def _parse_response(self, text: str) -> LocateResult:
        """Parse model response into LocateResult."""
        # Try markdown code block
        match = re.search(r"```(?:json)?\s*({.*?})\s*```", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return LocateResult(**data)
            except (json.JSONDecodeError, Exception):
                pass

        # Try raw JSON
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return LocateResult(**data)
            except (json.JSONDecodeError, Exception):
                pass

        logger.warning(f"Could not parse Gemini response: {text[:200]}")
        return LocateResult(
            found=False,
            reasoning="Could not parse model response",
        )
