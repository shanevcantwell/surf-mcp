"""
Integration tests for Fara visual grounding.

These tests exercise the full path from visual grounder to parsed result
using realistic Fara responses. They mock the LLM API but test everything else.

Run with: pytest tests/test_fara_integration.py -v
"""

import base64
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

from navigator_mcp.llm.openai_adapter import OpenAIVisualGrounder
from navigator_mcp.llm.base import LocateResult


def create_test_screenshot(width: int = 1920, height: int = 1080) -> str:
    """Create a test screenshot as base64."""
    img = Image.new("RGB", (width, height), color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class TestFaraIntegration:
    """Integration tests for Fara visual grounding with realistic responses."""

    @pytest.fixture
    def grounder(self):
        """Create a grounder instance."""
        return OpenAIVisualGrounder(
            api_base="http://localhost:1234/v1",
            model="fara-7b",
        )

    @pytest.fixture
    def screenshot(self):
        """Create a test screenshot."""
        return create_test_screenshot()

    # ==================== Realistic Fara Responses ====================

    @pytest.mark.asyncio
    async def test_fara_left_click_response(self, grounder, screenshot):
        """Test full flow with Fara's left_click response."""
        # Realistic Fara response with chain-of-thought
        fara_response = """I can see the Google search page. The search input field is located in the center of the page.

<tool_call>{"name": "computer_use", "arguments": {"action": "left_click", "coordinate": [960, 540]}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("the search input field", screenshot)

            assert result.found is True
            assert result.x is not None
            assert result.y is not None
            assert "left_click" in result.reasoning

    @pytest.mark.asyncio
    async def test_fara_type_response(self, grounder, screenshot):
        """Test full flow with Fara's type action response."""
        fara_response = """The email input field is visible. I'll type the email address.

<tool_call>{"name": "computer_use", "arguments": {"action": "type", "text": "user@example.com", "coordinate": [400, 300]}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("email input field", screenshot)

            assert result.found is True
            assert result.x is not None
            assert result.y is not None

    @pytest.mark.asyncio
    async def test_fara_scroll_response(self, grounder, screenshot):
        """Test full flow with Fara's scroll action (no coordinates)."""
        fara_response = """I need to scroll down to see more content.

<tool_call>{"name": "computer_use", "arguments": {"action": "scroll", "pixels": 500}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("more content below", screenshot)

            assert result.found is True
            assert result.x is None  # scroll has no coordinates
            assert result.y is None
            assert "scroll" in result.reasoning

    @pytest.mark.asyncio
    async def test_fara_terminate_response(self, grounder, screenshot):
        """Test full flow with Fara's terminate action."""
        fara_response = """The task has been completed successfully.

<tool_call>{"name": "computer_use", "arguments": {"action": "terminate", "status": "success"}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("completion indicator", screenshot)

            assert result.found is True
            assert "terminate" in result.reasoning

    @pytest.mark.asyncio
    async def test_fara_playwright_format(self, grounder, screenshot):
        """Test full flow with playwright tool name variant."""
        fara_response = """<tool_call>{"name": "playwright", "arguments": {"action": "click", "coordinate": [512, 384]}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("submit button", screenshot)

            assert result.found is True
            assert result.x is not None

    @pytest.mark.asyncio
    async def test_fara_visit_url_response(self, grounder, screenshot):
        """Test Fara's visit_url action."""
        fara_response = """<tool_call>{"name": "computer_use", "arguments": {"action": "visit_url", "url": "https://example.com"}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("navigation target", screenshot)

            assert result.found is True
            assert "visit_url" in result.reasoning

    @pytest.mark.asyncio
    async def test_fara_web_search_response(self, grounder, screenshot):
        """Test Fara's web_search action."""
        fara_response = """<tool_call>{"name": "computer_use", "arguments": {"action": "web_search", "query": "python documentation"}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("search action", screenshot)

            assert result.found is True
            assert "web_search" in result.reasoning

    @pytest.mark.asyncio
    async def test_fara_key_press_response(self, grounder, screenshot):
        """Test Fara's key press action."""
        fara_response = """<tool_call>{"name": "computer_use", "arguments": {"action": "key", "keys": ["Enter"]}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("submit form", screenshot)

            assert result.found is True
            assert "key" in result.reasoning

    # ==================== Error Cases ====================

    @pytest.mark.asyncio
    async def test_fara_unknown_tool_name(self, grounder, screenshot):
        """Test handling of unknown tool name."""
        fara_response = """<tool_call>{"name": "unknown_tool", "arguments": {"foo": "bar"}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("something", screenshot)

            assert result.found is False
            assert "unknown_tool" in result.reasoning

    @pytest.mark.asyncio
    async def test_fara_missing_coordinates_for_click(self, grounder, screenshot):
        """Test handling of click action missing coordinates."""
        fara_response = """<tool_call>{"name": "computer_use", "arguments": {"action": "left_click"}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("button", screenshot)

            assert result.found is False
            assert "missing coordinates" in result.reasoning

    @pytest.mark.asyncio
    async def test_fara_malformed_json(self, grounder, screenshot):
        """Test handling of malformed JSON in tool_call."""
        fara_response = """<tool_call>{"name": "computer_use", "arguments": {broken json</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("button", screenshot)

            assert result.found is False

    @pytest.mark.asyncio
    async def test_fara_no_tool_call(self, grounder, screenshot):
        """Test handling when Fara returns text without tool_call."""
        fara_response = """I cannot find the element you described on this page. The page appears to be blank or the element is not visible."""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("nonexistent element", screenshot)

            assert result.found is False

    @pytest.mark.asyncio
    async def test_fara_api_error(self, grounder, screenshot):
        """Test handling of API errors."""
        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                side_effect=Exception("API timeout")
            )

            result = await grounder.locate("button", screenshot)

            assert result.found is False
            assert "Error" in result.reasoning

    # ==================== Resolution Scaling ====================

    @pytest.mark.asyncio
    async def test_coordinate_scaling_landscape(self, grounder):
        """Test coordinate scaling for landscape screenshots."""
        # Create a landscape screenshot (wider than tall)
        screenshot = create_test_screenshot(1920, 1080)

        # Fara returns coordinates in native resolution (1428x896 for landscape)
        fara_response = """<tool_call>{"name": "computer_use", "arguments": {"action": "left_click", "coordinate": [714, 448]}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("center element", screenshot)

            assert result.found is True
            # Coordinates should be scaled back to original resolution
            # 714 * (1920/1428) ≈ 960, 448 * (1080/896) ≈ 540
            assert result.x is not None
            assert result.y is not None

    @pytest.mark.asyncio
    async def test_coordinate_scaling_portrait(self, grounder):
        """Test coordinate scaling for portrait screenshots."""
        screenshot = create_test_screenshot(1080, 1920)

        fara_response = """<tool_call>{"name": "computer_use", "arguments": {"action": "left_click", "coordinate": [448, 714]}}</tool_call>"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fara_response

        with patch.object(grounder, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            result = await grounder.locate("element", screenshot)

            assert result.found is True
            assert result.x is not None
            assert result.y is not None


class TestRealFaraResponses:
    """Tests using actual recorded Fara responses.

    These test cases are based on real Fara outputs observed during testing.
    Add new test cases here when encountering new response formats.
    """

    @pytest.fixture
    def grounder(self):
        return OpenAIVisualGrounder()

    def test_recorded_google_search_click(self, grounder):
        """Test parsing of recorded Fara response for Google search."""
        # Actual response format observed from Fara
        response = """I can see the Google homepage with a search box in the center. I'll click on the search input field.

<tool_call>{"name": "playwright", "arguments": {"action": "left_click", "coordinate": [624, 432]}}</tool_call>"""

        result = grounder._parse_response(response)

        assert result.found is True
        assert result.x == 624
        assert result.y == 432

    def test_recorded_type_action(self, grounder):
        """Test parsing of recorded type action."""
        response = """<tool_call>{"name": "computer_use", "arguments": {"action": "type", "text": "hello world", "coordinate": [500, 300]}}</tool_call>"""

        result = grounder._parse_response(response)

        assert result.found is True
        assert result.x == 500
        assert result.y == 300

    def test_recorded_scroll_down(self, grounder):
        """Test parsing of recorded scroll action."""
        response = """The content continues below. I need to scroll down.

<tool_call>{"name": "computer_use", "arguments": {"action": "scroll", "direction": "down", "pixels": 300}}</tool_call>"""

        result = grounder._parse_response(response)

        assert result.found is True
        assert result.x is None
        assert "scroll" in result.reasoning

    def test_recorded_multiline_thinking(self, grounder):
        """Test parsing when Fara includes extensive chain-of-thought."""
        response = """Looking at this screenshot, I can see:
1. A navigation bar at the top
2. A main content area
3. A sidebar on the left

The "Submit" button appears to be in the main content area, roughly centered horizontally and near the bottom of a form.

Based on my analysis, I'll click on the submit button.

<tool_call>{"name": "computer_use", "arguments": {"action": "left_click", "coordinate": [800, 600]}}</tool_call>"""

        result = grounder._parse_response(response)

        assert result.found is True
        assert result.x == 800
        assert result.y == 600
