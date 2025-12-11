"""
OpenAI Visual Grounding Adapter.

Uses OpenAI's vision models (GPT-4V, GPT-4o) or OpenAI-compatible endpoints
(like LM Studio running Fara-7B) for visual grounding.

Supports multi-server discovery:
- Parses LMSTUDIO_SERVERS env var for server list
- Probes each server's /v1/models for model state
- Prefers servers with target model already loaded
- Falls back through server list on failures
"""

import asyncio
import base64
import io
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image

from .base import LocateResult, VisualGrounder

logger = logging.getLogger(__name__)

# Default native resolutions for vision models
DEFAULT_NATIVE_RESOLUTIONS = {
    "square": (1024, 1024),
    "landscape": (1428, 896),
    "portrait": (896, 1428),
}


@dataclass
class ServerInfo:
    """Information about an LM Studio server."""

    name: str
    url: str
    models: List[Dict[str, Any]] = None  # Cached manifest

    def __post_init__(self):
        if self.models is None:
            self.models = []


def parse_lmstudio_servers() -> Dict[str, str]:
    """
    Parse LMSTUDIO_SERVERS env var into name→URL mapping.

    Format: "name1=url1,name2=url2" (uses = separator since URLs contain :)
    Example: "rtx3090=http://localhost:1234/v1,rtx8000=http://192.168.137.2:1234/v1"

    Returns:
        Dict mapping server names to URLs
    """
    servers_str = os.getenv("LMSTUDIO_SERVERS", "")
    if not servers_str:
        # Fall back to single server from LMSTUDIO_BASE_URL or OPENAI_API_BASE
        fallback = os.getenv("LMSTUDIO_BASE_URL") or os.getenv(
            "OPENAI_API_BASE", "http://localhost:1234/v1"
        )
        return {"default": fallback}

    server_map = {}
    for entry in servers_str.split(","):
        entry = entry.strip()
        if "=" in entry:
            name, url = entry.split("=", 1)
            server_map[name.strip()] = url.strip()
        else:
            logger.warning(f"Invalid LMSTUDIO_SERVERS entry (missing '='): {entry}")

    if server_map:
        logger.debug(f"Parsed LMSTUDIO_SERVERS: {list(server_map.keys())}")

    return server_map or {"default": "http://localhost:1234/v1"}


def get_fara_model_ids() -> List[str]:
    """
    Get priority-ordered list of acceptable Fara model IDs.

    Returns:
        List of model IDs to search for
    """
    ids_str = os.getenv("FARA_MODEL_IDS", "microsoft_fara-7b")
    return [id.strip() for id in ids_str.split(",") if id.strip()]


async def probe_server_models(
    server_url: str, timeout: float = 2.0
) -> List[Dict[str, Any]]:
    """
    Probe server's /v1/models endpoint for available models.

    Args:
        server_url: Base URL of the server (e.g., http://localhost:1234/v1)
        timeout: Request timeout in seconds

    Returns:
        List of model objects with id, state, type, etc.
    """
    # Ensure URL ends without trailing slash for consistent joining
    base = server_url.rstrip("/")
    models_url = f"{base}/models"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(models_url)
            response.raise_for_status()
            data = response.json()
            models = data.get("data", [])
            logger.debug(f"Probed {server_url}: {len(models)} models")
            return models
    except httpx.TimeoutException:
        logger.debug(f"Probe timeout for {server_url}")
        return []
    except Exception as e:
        logger.debug(f"Probe failed for {server_url}: {e}")
        return []


async def find_fara_server(
    servers: Dict[str, str] = None,
    model_ids: List[str] = None,
    probe_timeout: float = None,
) -> Tuple[str, str]:
    """
    Find a server with a Fara model, preferring already-loaded models.

    Args:
        servers: Server name→URL mapping (defaults to LMSTUDIO_SERVERS)
        model_ids: Acceptable model IDs (defaults to FARA_MODEL_IDS)
        probe_timeout: Timeout for manifest probes (defaults to FARA_PROBE_TIMEOUT)

    Returns:
        Tuple of (server_url, model_id)
    """
    if servers is None:
        servers = parse_lmstudio_servers()
    if model_ids is None:
        model_ids = get_fara_model_ids()
    if probe_timeout is None:
        probe_timeout = float(os.getenv("FARA_PROBE_TIMEOUT", "2.0"))

    model_id_set = set(model_ids)

    # Phase 1: Find server with model already LOADED
    for name, url in servers.items():
        models = await probe_server_models(url, timeout=probe_timeout)
        for model in models:
            model_id = model.get("id", "")
            state = model.get("state", "")
            if model_id in model_id_set and state == "loaded":
                logger.info(f"Found loaded model '{model_id}' on server '{name}'")
                return (url, model_id)

    # Phase 2: Find server that HAS the model (not loaded yet)
    # LM Studio will auto-load on first request
    for name, url in servers.items():
        models = await probe_server_models(url, timeout=probe_timeout)
        for model in models:
            model_id = model.get("id", "")
            if model_id in model_id_set:
                logger.info(
                    f"Found model '{model_id}' on server '{name}' (not loaded, will auto-load)"
                )
                return (url, model_id)

    # Phase 3: Fallback to first server, first model ID
    first_url = list(servers.values())[0]
    first_model = model_ids[0]
    logger.warning(
        f"No Fara model found on any server, falling back to {first_url} with {first_model}"
    )
    return (first_url, first_model)


class OpenAIVisualGrounder(VisualGrounder):
    """
    Visual grounding using OpenAI-compatible vision API.

    Works with:
    - OpenAI GPT-4V, GPT-4o
    - LM Studio running Fara-7B (or other vision models)
    - Any OpenAI-compatible vision endpoint

    Supports multi-server discovery via LMSTUDIO_SERVERS env var.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        native_resolutions: Optional[Dict[str, Tuple[int, int]]] = None,
        max_failures: Optional[int] = None,
    ):
        """
        Initialize OpenAI visual grounder.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            api_base: API base URL (auto-discovered if not set)
            model: Model to use (auto-discovered if not set)
            native_resolutions: Resolution scaling config for the model
            max_failures: Max retries before giving up (defaults to FARA_MAX_FAILURES)
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "not-needed")
        self._api_base = api_base  # May be None, will be discovered
        self._model = model  # May be None, will be discovered
        self.native_resolutions = native_resolutions or DEFAULT_NATIVE_RESOLUTIONS
        self.max_failures = max_failures or int(os.environ.get("FARA_MAX_FAILURES", "2"))

        # Lazy initialization
        self._client = None
        self._discovered = False

    async def _ensure_discovered(self) -> None:
        """Discover server and model if not already set."""
        if self._discovered:
            return

        if self._api_base is None or self._model is None:
            url, model_id = await find_fara_server()
            if self._api_base is None:
                self._api_base = url
            if self._model is None:
                self._model = model_id
            logger.info(f"Discovered Fara server: {self._api_base}, model: {self._model}")

        self._discovered = True

    @property
    def api_base(self) -> str:
        """Get API base URL (may trigger sync discovery fallback)."""
        if self._api_base is None:
            # Sync fallback - use first server
            servers = parse_lmstudio_servers()
            self._api_base = list(servers.values())[0]
        return self._api_base

    @property
    def model(self) -> str:
        """Get model ID (may trigger sync discovery fallback)."""
        if self._model is None:
            # Sync fallback - use first model ID
            self._model = get_fara_model_ids()[0]
        return self._model

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

        Handles resolution scaling transparently and retries on failure.
        """
        await self._ensure_discovered()

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

        failures = 0
        servers = parse_lmstudio_servers()
        server_urls = list(servers.values())

        while failures < self.max_failures:
            try:
                result = await self._invoke_vision(prompt, scaled_screenshot)

                # Scale coordinates back to original resolution
                if result.found and result.x is not None and result.y is not None:
                    result.x, result.y = self._scale_coordinates(
                        result.x, result.y, original_size, native_size
                    )

                return result

            except Exception as e:
                failures += 1
                logger.warning(
                    f"Visual grounding failed (attempt {failures}/{self.max_failures}): {e}"
                )

                # Try next server if available
                if failures < len(server_urls):
                    next_url = server_urls[failures]
                    logger.info(f"Trying next server: {next_url}")
                    self._api_base = next_url
                    self._client = None  # Force client recreation

        return LocateResult(
            found=False,
            reasoning=f"Failed after {failures} attempts",
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
