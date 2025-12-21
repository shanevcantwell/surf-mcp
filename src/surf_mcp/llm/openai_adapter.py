"""
OpenAI Visual Grounding Adapter.

Uses OpenAI's vision models (GPT-4V, GPT-4o) or OpenAI-compatible endpoints
(like LM Studio running Fara-7B) for visual grounding.

This is a pure OpenAI-compatible adapter. For LM Studio server discovery,
see lmstudio_discovery.py which handles probing servers and finding models.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from PIL import Image

if TYPE_CHECKING:
    from openai import AsyncOpenAI

from .base import FaraToolCall, LocateResult, VisualGrounder

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
        from surf_mcp.llm.lmstudio_discovery import discover_fara_server
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
            model: Model to use (defaults to SURF_LLM_MODEL env var)
            native_resolutions: Resolution scaling config for the model
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "not-needed")
        self.api_base = api_base or os.environ.get(
            "OPENAI_API_BASE", "https://api.openai.com/v1"
        )
        self.model = model or os.environ.get("SURF_LLM_MODEL", "gpt-4o")
        self.native_resolutions = native_resolutions or DEFAULT_NATIVE_RESOLUTIONS

        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
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

    # ============ ADR-005: Direct Fara Execution ============

    async def get_action(
        self, goal: str, screenshot_b64: str, seed: Optional[int] = None
    ) -> FaraToolCall:
        """
        Get action from Fara, preserving full tool_call details.

        Per ADR-005: Returns FaraToolCall instead of LocateResult to preserve
        the complete action context for direct execution.

        Args:
            goal: Natural language goal (e.g., "click the search button")
            screenshot_b64: Base64-encoded screenshot
            seed: Optional seed for randomization (used for retry with different seeds)

        Returns:
            FaraToolCall with action, coordinates, and other parameters
        """
        # Get original dimensions and scale image
        original_size = self._get_image_dimensions(screenshot_b64)
        native_size = self._select_best_resolution(*original_size)
        scaled_screenshot = self._scale_to_native(screenshot_b64, native_size)

        # Fara-style agentic prompt
        prompt = f"""You are an autonomous web navigation agent.

Given the screenshot, determine the next action to achieve this goal: "{goal}"

Return a tool_call in this format:
<tool_call>
{{"name": "computer_use", "arguments": {{"action": "<action>", ...parameters...}}}}
</tool_call>

Available actions:
- left_click: Click at coordinates. Parameters: "coordinate": [x, y]
- double_click: Double-click at coordinates. Parameters: "coordinate": [x, y]
- type: Type text. Parameters: "coordinate": [x, y], "text": "text to type"
- scroll: Scroll page. Parameters: "direction": "up" or "down", "pixels": amount
- key: Press keys. Parameters: "keys": ["Enter"] or ["Control", "c"]
- visit_url: Navigate to URL. Parameters: "url": "https://..."
- terminate: Goal completed, no more actions needed.
- wait: Wait for page to load.

Include a brief "reasoning" field explaining your decision.

IMPORTANT: Return ONLY the tool_call tags with JSON, no other text."""

        try:
            raw_response = await self._invoke_vision_raw(prompt, scaled_screenshot, seed)
            tool_call = self._parse_to_fara_tool_call(raw_response)

            # Scale coordinates back to original resolution
            if tool_call.coordinate:
                scaled_x, scaled_y = self._scale_coordinates(
                    tool_call.coordinate[0],
                    tool_call.coordinate[1],
                    original_size,
                    native_size,
                )
                tool_call.coordinate = (scaled_x, scaled_y)

            return tool_call

        except Exception as e:
            logger.error(f"get_action failed: {e}")
            return FaraToolCall(
                action="terminate",
                confidence=0.0,
                reasoning=f"Error getting action: {e}",
            )

    async def get_action_with_retry(
        self, goal: str, screenshot_b64: str
    ) -> FaraToolCall:
        """
        Get action from Fara, retrying with new seed if low confidence.

        Per ADR-005: Uses env-configurable confidence threshold and retry count.
        Each retry uses a different seed to get varied model responses.

        Environment variables:
            FARA_MIN_CONFIDENCE: Minimum acceptable confidence (default: 0.7)
            FARA_CONFIDENCE_RETRIES: Max retries for low confidence (default: 2)

        Returns:
            Best FaraToolCall found, or highest-confidence result if all below threshold
        """
        min_confidence = float(os.environ.get("FARA_MIN_CONFIDENCE", "0.7"))
        max_retries = int(os.environ.get("FARA_CONFIDENCE_RETRIES", "2"))

        best_result: FaraToolCall = FaraToolCall(
            action="terminate",
            confidence=0.0,
            reasoning="No result obtained",
        )

        for attempt in range(max_retries + 1):
            result = await self.get_action(goal, screenshot_b64, seed=attempt)

            logger.debug(
                f"Attempt {attempt + 1}/{max_retries + 1}: "
                f"action={result.action}, confidence={result.confidence:.2f}"
            )

            if result.confidence >= min_confidence:
                return result

            if result.confidence > best_result.confidence:
                best_result = result

            if attempt < max_retries:
                logger.info(
                    f"Confidence {result.confidence:.2f} < {min_confidence}, "
                    f"retry {attempt + 2}/{max_retries + 1}"
                )

        # Return best attempt even if below threshold
        logger.warning(
            f"Using best result with confidence {best_result.confidence:.2f} "
            f"(below threshold {min_confidence})"
        )
        return best_result

    def _parse_to_fara_tool_call(self, text: str) -> FaraToolCall:
        """
        Parse Fara response into FaraToolCall.

        Per ADR-005: Preserves full action details instead of extracting
        only coordinates like _normalize_tool_call does.

        Args:
            text: Raw model response text

        Returns:
            FaraToolCall with all action parameters
        """
        logger.debug(f"Parsing to FaraToolCall: {text[:500]}")

        # Try <tool_call> XML tags (Fara-7B format)
        tool_call_match = re.search(
            r"<tool_call>\s*({.*?})\s*</tool_call>",
            text,
            re.DOTALL,
        )
        if tool_call_match:
            try:
                tool_json = json.loads(tool_call_match.group(1))
                return self._json_to_fara_tool_call(tool_json)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool_call JSON: {e}")

        # Try raw JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return self._json_to_fara_tool_call(data)
            except json.JSONDecodeError:
                pass

        # Fallback to terminate with error
        logger.warning(f"Could not parse FaraToolCall from: {text[:200]}")
        return FaraToolCall(
            action="terminate",
            confidence=0.0,
            reasoning="Could not parse model response",
        )

    def _json_to_fara_tool_call(self, tool_json: Dict[str, Any]) -> FaraToolCall:
        """
        Convert Fara's JSON tool_call to FaraToolCall dataclass.

        Handles Fara-7B's native format:
        {"name": "computer_use", "arguments": {"action": "left_click", "coordinate": [x, y], ...}}
        """
        name = tool_json.get("name", "")
        args = tool_json.get("arguments", {})

        # Handle different tool name formats
        if name in ("computer_use", "playwright", "computer"):
            action = args.get("action", "unknown")
            coordinate = args.get("coordinate")
            text = args.get("text")
            direction = args.get("direction")
            pixels = args.get("pixels")
            url = args.get("url")
            keys = args.get("keys")
            reasoning = args.get("reasoning", "")

            # Convert coordinate list to tuple
            coord_tuple = None
            if coordinate and len(coordinate) >= 2:
                coord_tuple = (int(coordinate[0]), int(coordinate[1]))

            return FaraToolCall(
                action=action,
                coordinate=coord_tuple,
                text=text,
                direction=direction,
                pixels=pixels,
                url=url,
                keys=keys,
                confidence=1.0,  # Fara doesn't provide confidence, assume high
                reasoning=reasoning,
            )

        # Unknown format - extract what we can
        logger.warning(f"Unknown tool_call format '{name}', attempting extraction")
        return FaraToolCall(
            action=args.get("action", "terminate"),
            confidence=0.5,
            reasoning=f"Unknown format: {name}",
        )

    async def _invoke_vision_raw(
        self, prompt: str, image_b64: str, seed: Optional[int] = None
    ) -> str:
        """
        Call vision API and return raw response text.

        Args:
            prompt: The prompt to send
            image_b64: Base64-encoded image
            seed: Optional seed for model randomization

        Returns:
            Raw response text from model
        """
        client = self._get_client()

        # Handle data URL prefix
        if not image_b64.startswith("data:"):
            image_b64 = f"data:image/png;base64,{image_b64}"

        # Build request params
        params = {
            "model": self.model,
            "messages": [
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
            "max_tokens": 500,
        }

        # Add seed if provided (for retry variation)
        if seed is not None:
            params["seed"] = seed

        response = await client.chat.completions.create(**params)
        return response.choices[0].message.content

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
        logger.debug(f"Parsing Fara response: {text[:500]}")

        # Try <tool_call> XML tags (Fara-7B format)
        tool_call_match = re.search(
            r"<tool_call>\s*({.*?})\s*</tool_call>",
            text,
            re.DOTALL,
        )
        if tool_call_match:
            try:
                tool_json = json.loads(tool_call_match.group(1))
                logger.debug(f"Parsed tool_call JSON: {tool_json}")
                return self._normalize_tool_call(tool_json)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool_call JSON: {e}")

        # Try markdown code block
        match = re.search(r"```(?:json)?\s*({.*?})\s*```", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return self._normalize_locate_json(data)
            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"Markdown JSON parse failed: {e}")

        # Try raw JSON
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return self._normalize_locate_json(data)
            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"Raw JSON parse failed: {e}")

        # Fallback
        logger.warning(f"Could not parse response: {text[:200]}")
        return LocateResult(
            found=False,
            reasoning="Could not parse model response",
        )

    def _normalize_locate_json(self, data: Dict[str, Any]) -> LocateResult:
        """
        Normalize JSON response to LocateResult, handling various Fara formats.

        Fara sometimes returns:
        - {"x": [x, y], "y": y, ...} - x is a coordinate pair
        - {"x": x, "y": y, ...} - standard format
        - {"found": true, "coordinate": [x, y], ...} - coordinate array format
        """
        found = data.get("found", False)
        x = data.get("x")
        y = data.get("y")
        confidence = data.get("confidence")
        reasoning = data.get("reasoning", "")

        # Handle case where x is a coordinate pair [x, y]
        if isinstance(x, list) and len(x) >= 2:
            logger.debug(f"Found x as coordinate pair: {x}")
            x, y = x[0], x[1]

        # Handle "coordinate" field instead of x/y
        coordinate = data.get("coordinate")
        if coordinate and isinstance(coordinate, list) and len(coordinate) >= 2:
            logger.debug(f"Found coordinate field: {coordinate}")
            x, y = coordinate[0], coordinate[1]

        # Ensure x, y are ints if present
        if x is not None:
            x = int(x)
        if y is not None:
            y = int(y)

        return LocateResult(
            found=found,
            x=x,
            y=y,
            confidence=confidence,
            reasoning=reasoning,
        )

    def _normalize_tool_call(self, tool_json: Dict[str, Any]) -> LocateResult:
        """
        Normalize Fara's tool_call format to LocateResult.

        Fara-7B returns agentic tool calls like:
        - {"name": "computer_use", "arguments": {"action": "left_click", "coordinate": [624, 280]}}
        - {"name": "computer_use", "arguments": {"action": "type", "text": "hello", "coordinate": [100, 200]}}
        - {"name": "playwright", "arguments": {"action": "click", "coordinate": [624, 280]}}
        - {"name": "computer", "arguments": {"action": "left_click", "coordinate": [624, 280]}}

        Actions with coordinates: left_click, click, type, mouse_move
        Actions without coordinates: scroll, key, visit_url, web_search, terminate, wait
        """
        name = tool_json.get("name", "")
        args = tool_json.get("arguments", {})
        action = args.get("action", "")

        # Handle case where action is the name directly (Fara variant)
        # e.g., {"name": "left_click", "arguments": {"coordinate": [x, y]}}
        action_names = {"left_click", "click", "double_click", "type", "scroll",
                        "key", "visit_url", "web_search", "terminate", "wait"}
        if name in action_names:
            action = name
            # Treat like computer_use format
            name = "computer_use"

        # Handle Fara's computer_use/playwright/computer tool formats
        if name in ("computer_use", "playwright", "computer"):
            coordinate = args.get("coordinate", [])

            # Actions with coordinates
            if coordinate and len(coordinate) >= 2:
                return LocateResult(
                    found=True,
                    x=coordinate[0],
                    y=coordinate[1],
                    confidence=1.0,
                    reasoning=f"Action: {action}",
                )

            # Actions without coordinates (scroll, terminate, etc.)
            if action in ("scroll", "key", "visit_url", "web_search", "history_back",
                          "terminate", "wait", "pause_and_memorize_fact"):
                return LocateResult(
                    found=True,
                    x=None,
                    y=None,
                    confidence=1.0,
                    reasoning=f"Action: {action} (no coordinates)",
                )

            # Action specified but no coordinates when expected
            if action:
                logger.warning(f"Action '{action}' missing coordinates: {tool_json}")
                return LocateResult(
                    found=False,
                    reasoning=f"Action '{action}' missing coordinates",
                )

        # Legacy serpico format
        elif name == "serpico":
            x_coord = args.get("x", [])
            if args.get("found") and x_coord and len(x_coord) >= 2:
                return LocateResult(
                    found=True,
                    x=x_coord[0],
                    y=x_coord[1],
                    confidence=1.0,
                )

        logger.warning(f"Unknown tool_call format: {tool_json}")
        return LocateResult(found=False, reasoning=f"Unknown tool_call format: {name}")

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
        scaled = img.resize(native_res, Image.Resampling.LANCZOS)

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
