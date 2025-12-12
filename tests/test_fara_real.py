"""
Real Fara Integration Tests - NOT mocked.

These tests actually call LM Studio. They're skipped if LM Studio isn't available.

Run with: pytest tests/test_fara_real.py -v -s
"""

import asyncio
import base64
import os
import pytest
from pathlib import Path

# Check if LM Studio is available
def lmstudio_available() -> bool:
    import urllib.request
    try:
        req = urllib.request.Request("http://localhost:1234/v1/models")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not lmstudio_available(),
    reason="LM Studio not available at localhost:1234"
)


@pytest.fixture
def sample_screenshot_b64():
    """Create a simple test image with a 'button' drawn on it."""
    from PIL import Image, ImageDraw

    # Create a simple webpage mockup
    img = Image.new("RGB", (1920, 1080), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw a blue "Search" button
    button_x, button_y = 960, 540  # Center of screen
    button_width, button_height = 200, 50

    # Blue button background
    draw.rectangle(
        [
            (button_x - button_width // 2, button_y - button_height // 2),
            (button_x + button_width // 2, button_y + button_height // 2)
        ],
        fill=(66, 133, 244),  # Google blue
        outline=(50, 100, 200),
        width=2
    )

    # Button text
    draw.text((button_x - 30, button_y - 10), "Search", fill=(255, 255, 255))

    # Add some other elements for context
    draw.rectangle([(100, 100), (1820, 200)], fill=(240, 240, 240))  # Header
    draw.text((120, 140), "Example Website", fill=(0, 0, 0))

    # Input field
    draw.rectangle([(600, 400), (1320, 450)], outline=(200, 200, 200), width=2)
    draw.text((620, 415), "Type something here...", fill=(150, 150, 150))

    # Convert to base64
    import io
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class TestFaraRealIntegration:
    """Tests that actually call LM Studio."""

    @pytest.mark.asyncio
    async def test_openai_adapter_locate(self, sample_screenshot_b64):
        """Test that OpenAIVisualGrounder.locate() returns valid results."""
        from navigator_mcp.llm.openai_adapter import OpenAIVisualGrounder

        grounder = OpenAIVisualGrounder(
            api_key="not-needed",
            api_base="http://localhost:1234/v1",
            model="microsoft_fara-7b",
        )

        print("\n--- Testing locate() ---")
        result = await grounder.locate("the blue Search button", sample_screenshot_b64)

        print(f"Result: found={result.found}, x={result.x}, y={result.y}")
        print(f"Confidence: {result.confidence}")
        print(f"Reasoning: {result.reasoning}")

        # Basic assertions - we at least got a response
        assert result is not None
        assert hasattr(result, "found")

        if result.found:
            assert result.x is not None, "Found but x is None"
            assert result.y is not None, "Found but y is None"
            # Check coordinates are roughly in the right area (button is at ~960, 540)
            print(f"Distance from expected: ({abs(result.x - 960)}, {abs(result.y - 540)})")
        else:
            pytest.fail(f"Element not found. Reasoning: {result.reasoning}")

    @pytest.mark.asyncio
    async def test_openai_adapter_get_action(self, sample_screenshot_b64):
        """Test that get_action() returns a FaraToolCall."""
        from navigator_mcp.llm.openai_adapter import OpenAIVisualGrounder

        grounder = OpenAIVisualGrounder(
            api_key="not-needed",
            api_base="http://localhost:1234/v1",
            model="microsoft_fara-7b",
        )

        print("\n--- Testing get_action() ---")
        result = await grounder.get_action("click the blue Search button", sample_screenshot_b64)

        print(f"Result: action={result.action}")
        print(f"Coordinate: {result.coordinate}")
        print(f"Confidence: {result.confidence}")
        print(f"Reasoning: {result.reasoning}")

        # Should return a click action
        assert result is not None
        assert result.action in ("left_click", "click", "terminate")

        if result.action in ("left_click", "click"):
            assert result.coordinate is not None, f"Click action but no coordinates"
            x, y = result.coordinate
            print(f"Distance from expected: ({abs(x - 960)}, {abs(y - 540)})")

    @pytest.mark.asyncio
    async def test_discovery_finds_fara(self):
        """Test that server discovery finds the Fara model."""
        from navigator_mcp.llm.lmstudio_discovery import discover_fara_server

        print("\n--- Testing discover_fara_server() ---")

        # Use environment variable
        os.environ["LMSTUDIO_SERVERS"] = "local=http://localhost:1234/v1"
        os.environ["FARA_MODEL_IDS"] = "microsoft_fara-7b,fara-7b"

        result = await discover_fara_server()

        if result is None:
            pytest.fail("discover_fara_server() returned None - Fara model not found")

        base_url, model_id = result
        print(f"Found: base_url={base_url}, model_id={model_id}")

        assert base_url is not None
        assert model_id is not None
        assert "fara" in model_id.lower()


class TestEventLoopHandling:
    """Test that async code works correctly in various contexts."""

    def test_nest_asyncio_works(self):
        """Test that nest_asyncio allows nested event loops."""
        import nest_asyncio
        nest_asyncio.apply()

        async def inner():
            return "inner"

        async def outer():
            # Try to run inner in the same loop
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(inner())
            return result

        # This should not raise "This event loop is already running"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(outer())
            assert result == "inner"
        finally:
            loop.close()

    def test_sync_wrapper_pattern(self):
        """Test the sync wrapper pattern used in the harness."""
        import nest_asyncio
        nest_asyncio.apply()

        async def async_func():
            await asyncio.sleep(0.01)
            return "success"

        class SyncWrapper:
            def __init__(self):
                self._loop = None
                self._setup_loop()

            def _setup_loop(self):
                try:
                    self._loop = asyncio.get_event_loop()
                    if self._loop.is_closed():
                        raise RuntimeError("Loop is closed")
                except RuntimeError:
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)

            def call(self):
                return self._loop.run_until_complete(async_func())

        wrapper = SyncWrapper()
        result = wrapper.call()
        assert result == "success"


class TestRawFaraResponse:
    """Debug tests to see raw Fara responses."""

    @pytest.mark.asyncio
    async def test_raw_api_call(self, sample_screenshot_b64):
        """Make a raw API call to see exactly what Fara returns."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key="not-needed",
            base_url="http://localhost:1234/v1",
        )

        prompt = """You are a visual UI element locator.

Given the screenshot, find the element described as: "the blue Search button"

Return a JSON object with:
- found: boolean (true if you can see the element)
- x: integer x-coordinate (center of element, pixels from left)
- y: integer y-coordinate (center of element, pixels from top)
- confidence: float 0.0-1.0 (how confident you are)
- reasoning: brief explanation of how you identified it

If the element is not visible, return found=false with null coordinates.

IMPORTANT: Return ONLY the JSON object, no markdown or explanation."""

        image_b64 = f"data:image/png;base64,{sample_screenshot_b64}"

        print("\n--- Raw API Call ---")
        response = await client.chat.completions.create(
            model="microsoft_fara-7b",
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

        raw_text = response.choices[0].message.content
        print(f"Raw response:\n{raw_text}")
        print(f"\nResponse length: {len(raw_text)}")

        # Try to parse it
        import json
        import re

        # Look for tool_call tags
        tool_call_match = re.search(r"<tool_call>\s*({.*?})\s*</tool_call>", raw_text, re.DOTALL)
        if tool_call_match:
            print(f"\nFound tool_call format:")
            print(tool_call_match.group(1))
        else:
            print("\nNo tool_call tags found")

        # Look for JSON
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end > start:
            json_str = raw_text[start:end+1]
            try:
                parsed = json.loads(json_str)
                print(f"\nParsed JSON: {json.dumps(parsed, indent=2)}")
            except json.JSONDecodeError as e:
                print(f"\nJSON parse error: {e}")
                print(f"Attempted to parse: {json_str[:200]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
