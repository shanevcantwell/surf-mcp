"""
OpenAI Visual Grounding Adapter.

Uses OpenAI's vision models (GPT-4V, GPT-4o) or OpenAI-compatible endpoints
(like LM Studio running Fara-7B) for visual grounding.

This is a pure OpenAI-compatible adapter. For LM Studio server discovery,
see lmstudio_discovery.py which handles probing servers and finding models.
"""

import base64
import io
import json
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from .base import LocateResult, VisualGrounder

logger = logging.getLogger(__name__)

# Default native resolutions for vision models
DEFAULT_NATIVE_RESOLUTIONS = {
    "square": (1024, 1024),
    "landscape": (1428, 896),
    "portrait": (896, 1428),
}


class OpenAIVisualGrounder(VisualGrounder):
    """
    Visual grounding using OpenAI-compatible vision API.

    Works with:
    - OpenAI GPT-4V, GPT-4o
    - LM Studio running Fara-7B (or other vision models)
    - Any OpenAI-compatible vision endpoint

    For automatic LM Studio server discovery, use:
        from navigator_mcp.llm.lmstudio_discovery import discover_fara_server
        url, model = await discover_fara_server()
        grounder = OpenAIVisualGrounder(api_base=url, model=model)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        native_resolutions: Optional[Dict[str, Tuple[int, int]]] = None,
    ):
        """
        Initialize OpenAI visual grounder.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var, "not-needed" for LM Studio)
            api_base: API base URL (defaults to OPENAI_API_BASE env var)
            model: Model to use (defaults to NAVIGATOR_LLM_MODEL env var)
            native_resolutions: Resolution scaling config for the model
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "not-needed")
        self.api_base = api_base or os.environ.get(
            "OPENAI_API_BASE", "https://api.openai.com/v1"
        )
        self.model = model or os.environ.get("NAVIGATOR_LLM_MODEL", "gpt-4o")
        self.native_resolutions = native_resolutions or DEFAULT_NATIVE_RESOLUTIONS

        self._client = None

    def _get_client(self):
        """Get or create OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "openai package required. Install with: pip install openai"
                )

            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
            )
        return self._client

    async def locate(self, description: str, screenshot_b64: str) -> LocateResult:
        """
        Locate element by description using vision model.

        Handles resolution scaling transparently:
        1. Get original image dimensions
        2. Scale to model's native resolution
        3. Get coordinates from model
        4. Scale coordinates back to original resolution
        """
        # Get original dimensions and scale image
        original_size = self._get_image_dimensions(screenshot_b64)
        native_size = self._select_best_resolution(*original_size)
        scaled_screenshot = self._scale_to_native(screenshot_b64, native_size)

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
            result = await self._invoke_vision(prompt, scaled_screenshot)

            # Scale coordinates back to original resolution
            if result.found and result.x is not None and result.y is not None:
                result.x, result.y = self._scale_coordinates(
                    result.x, result.y, original_size, native_size
                )

            return result

        except Exception as e:
            logger.error(f"Visual grounding failed: {e}")
            return LocateResult(
                found=False,
                reasoning=f"Error: {e}",
            )

    async def verify(self, description: str, screenshot_b64: str) -> LocateResult:
        """Verify element exists (uses locate, ignores coordinates)."""
        return await self.locate(description, screenshot_b64)

    async def _invoke_vision(self, prompt: str, image_b64: str) -> LocateResult:
        """
        Call vision API and parse response.

        Args:
            prompt: The prompt to send
            image_b64: Base64-encoded image

        Returns:
            Parsed LocateResult
        """
        client = self._get_client()

        # Handle data URL prefix
        if not image_b64.startswith("data:"):
            image_b64 = f"data:image/png;base64,{image_b64}"

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_b64},
                        },
                    ],
                }
            ],
            max_tokens=500,
        )

        text = response.choices[0].message.content
        return self._parse_response(text)

    def _parse_response(self, text: str) -> LocateResult:
        """
        Parse model response into LocateResult.

        Handles multiple response formats:
        1. <tool_call> XML tags (Fara-7B native format)
        2. Markdown code blocks
        3. Raw JSON
        """
        # Try <tool_call> XML tags (Fara-7B format)
        tool_call_match = re.search(
            r"<tool_call>\s*({.*?})\s*</tool_call>",
            text,
            re.DOTALL,
        )
        if tool_call_match:
            try:
                tool_json = json.loads(tool_call_match.group(1))
                return self._normalize_tool_call(tool_json)
            except json.JSONDecodeError:
                pass

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

        # Fallback
        logger.warning(f"Could not parse response: {text[:200]}")
        return LocateResult(
            found=False,
            reasoning="Could not parse model response",
        )

    def _normalize_tool_call(self, tool_json: Dict[str, Any]) -> LocateResult:
        """
        Normalize Fara's tool_call format to LocateResult.

        Fara returns formats like:
        - {"name": "computer", "arguments": {"action": "left_click", "coordinate": [624, 280]}}
        - {"name": "serpico", "arguments": {"found": true, "x": [614, 280]}}
        """
        name = tool_json.get("name", "")
        args = tool_json.get("arguments", {})

        if name == "computer":
            coordinate = args.get("coordinate", [])
            if coordinate and len(coordinate) >= 2:
                return LocateResult(
                    found=True,
                    x=coordinate[0],
                    y=coordinate[1],
                    confidence=1.0,
                    reasoning=f"Action: {args.get('action', 'click')}",
                )

        elif name == "serpico":
            x_coord = args.get("x", [])
            if args.get("found") and x_coord and len(x_coord) >= 2:
                return LocateResult(
                    found=True,
                    x=x_coord[0],
                    y=x_coord[1],
                    confidence=1.0,
                )

        return LocateResult(found=False, reasoning="Unknown tool_call format")

    def _get_image_dimensions(self, b64_image: str) -> Tuple[int, int]:
        """Get dimensions of base64-encoded image."""
        if "," in b64_image:
            b64_image = b64_image.split(",", 1)[1]

        img_bytes = base64.b64decode(b64_image)
        img = Image.open(io.BytesIO(img_bytes))
        return img.size

    def _select_best_resolution(self, width: int, height: int) -> Tuple[int, int]:
        """Select best native resolution based on aspect ratio."""
        aspect_ratio = width / height

        if aspect_ratio > 1.2:
            return self.native_resolutions.get("landscape", (1428, 896))
        elif aspect_ratio < 0.8:
            return self.native_resolutions.get("portrait", (896, 1428))
        else:
            return self.native_resolutions.get("square", (1024, 1024))

    def _scale_to_native(self, b64_image: str, native_res: Tuple[int, int]) -> str:
        """Scale image to native resolution."""
        prefix = ""
        if "," in b64_image:
            prefix, b64_image = b64_image.split(",", 1)
            prefix += ","

        img_bytes = base64.b64decode(b64_image)
        img = Image.open(io.BytesIO(img_bytes))
        scaled = img.resize(native_res, Image.LANCZOS)

        buffer = io.BytesIO()
        scaled.save(buffer, format="PNG")
        scaled_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return prefix + scaled_b64

    def _scale_coordinates(
        self,
        x: int,
        y: int,
        original_size: Tuple[int, int],
        native_size: Tuple[int, int],
    ) -> Tuple[int, int]:
        """Scale coordinates from native to original resolution."""
        scale_x = original_size[0] / native_size[0]
        scale_y = original_size[1] / native_size[1]
        return int(x * scale_x), int(y * scale_y)
