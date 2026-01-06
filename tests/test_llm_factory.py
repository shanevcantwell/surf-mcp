"""
Tests for VisualGrounderFactory and FailoverGrounder.

Tests the factory pattern for creating visual grounders with
automatic server discovery and failover.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from surf_mcp.llm.factory import VisualGrounderFactory, FailoverGrounder
from surf_mcp.llm.base import FaraToolCall, LocateResult, StepContext
from surf_mcp.llm.lmstudio_discovery import ModelInfo, ServerInfo


class TestVisualGrounderFactory:
    """Tests for the VisualGrounderFactory."""

    @pytest.mark.asyncio
    async def test_create_returns_openai_adapter_by_default(self):
        """Factory creates OpenAI adapter when no provider specified."""
        with patch.dict(os.environ, {"SURF_LLM_PROVIDER": "openai"}, clear=False):
            with patch(
                "surf_mcp.llm.factory.discover_fara_server",
                new_callable=AsyncMock,
                return_value=("http://localhost:1234/v1", "fara-7b"),
            ):
                grounder = await VisualGrounderFactory.create()

                assert grounder.__class__.__name__ == "OpenAIVisualGrounder"
                assert grounder.api_base == "http://localhost:1234/v1"
                assert grounder.model == "fara-7b"

    @pytest.mark.asyncio
    async def test_create_returns_gemini_adapter_when_specified(self):
        """Factory creates Gemini adapter when provider is gemini."""
        grounder = await VisualGrounderFactory.create(provider="gemini")

        assert grounder.__class__.__name__ == "GeminiVisualGrounder"

    @pytest.mark.asyncio
    async def test_create_with_failover_returns_failover_grounder(self):
        """Factory creates FailoverGrounder with correct config."""
        with patch.dict(
            os.environ,
            {
                "LMSTUDIO_SERVERS": "gpu1=http://server1/v1,gpu2=http://server2/v1",
                "FARA_MODEL_IDS": "model-a,model-b",
                "FARA_MAX_FAILURES": "3",
            },
            clear=False,
        ):
            grounder = await VisualGrounderFactory.create_with_failover()

            assert isinstance(grounder, FailoverGrounder)
            assert len(grounder.servers) == 2
            assert len(grounder.model_ids) == 2
            assert grounder.max_failures == 3

    @pytest.mark.asyncio
    async def test_create_uses_discovery_result(self):
        """Factory uses server discovered by discover_fara_server."""
        with patch(
            "surf_mcp.llm.factory.discover_fara_server",
            new_callable=AsyncMock,
            return_value=("http://best-server:1234/v1", "optimal-model"),
        ):
            grounder = await VisualGrounderFactory.create()

            assert grounder.api_base == "http://best-server:1234/v1"
            assert grounder.model == "optimal-model"


class TestFailoverGrounder:
    """Tests for FailoverGrounder failover behavior."""

    @pytest.fixture
    def failover_grounder(self):
        """Create a FailoverGrounder with test config."""
        return FailoverGrounder(
            servers=[
                ("server1", "http://server1:1234/v1"),
                ("server2", "http://server2:1234/v1"),
            ],
            model_ids=["model-a", "model-b"],
            provider="openai",
            max_failures=3,
        )

    @pytest.mark.asyncio
    async def test_locate_success_on_first_try(self, failover_grounder):
        """Locate succeeds on first try with no failover."""
        mock_result = LocateResult(found=True, x=100, y=200, confidence=0.9)

        with patch.object(
            failover_grounder,
            "_create_adapter",
            return_value=MagicMock(locate=AsyncMock(return_value=mock_result)),
        ):
            result = await failover_grounder.locate("button", "screenshot_b64")

            assert result.found is True
            assert result.x == 100
            assert result.y == 200

    @pytest.mark.asyncio
    async def test_locate_retries_on_failure(self, failover_grounder):
        """Locate retries with next server on failure."""
        mock_success = LocateResult(found=True, x=50, y=50)

        # First adapter fails, second succeeds
        failing_adapter = MagicMock(locate=AsyncMock(side_effect=Exception("Server down")))
        working_adapter = MagicMock(locate=AsyncMock(return_value=mock_success))

        call_count = 0

        def create_adapter(url, model):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return failing_adapter
            return working_adapter

        with patch.object(failover_grounder, "_create_adapter", side_effect=create_adapter):
            result = await failover_grounder.locate("button", "screenshot_b64")

            assert result.found is True
            assert call_count == 2  # Tried twice

    @pytest.mark.asyncio
    async def test_locate_fails_after_max_failures(self, failover_grounder):
        """Locate gives up after max_failures attempts."""
        failing_adapter = MagicMock(locate=AsyncMock(side_effect=Exception("Always fails")))

        with patch.object(
            failover_grounder, "_create_adapter", return_value=failing_adapter
        ):
            result = await failover_grounder.locate("button", "screenshot_b64")

            assert result.found is False
            assert "All servers failed" in result.reasoning

    @pytest.mark.asyncio
    async def test_locate_cycles_through_servers_and_models(self, failover_grounder):
        """Locate tries different server/model combinations."""
        configs_tried = []

        def create_adapter(url, model):
            configs_tried.append((url, model))
            adapter = MagicMock()
            adapter.locate = AsyncMock(side_effect=Exception("Fail"))
            return adapter

        with patch.object(failover_grounder, "_create_adapter", side_effect=create_adapter):
            await failover_grounder.locate("button", "screenshot_b64")

        # Should have tried multiple configs
        assert len(configs_tried) == failover_grounder.max_failures
        # Should cycle through model_ids
        assert configs_tried[0][1] == "model-a"
        assert configs_tried[1][1] == "model-b"

    @pytest.mark.asyncio
    async def test_verify_uses_locate(self, failover_grounder):
        """Verify delegates to locate."""
        mock_result = LocateResult(found=True)

        with patch.object(
            failover_grounder,
            "_create_adapter",
            return_value=MagicMock(locate=AsyncMock(return_value=mock_result)),
        ):
            result = await failover_grounder.verify("button", "screenshot_b64")

            assert result.found is True

    @pytest.mark.asyncio
    async def test_get_action_success(self, failover_grounder):
        """get_action delegates to adapter and returns FaraToolCall."""
        mock_result = FaraToolCall(
            action="left_click",
            coordinate=(100, 200),
            confidence=0.95,
            reasoning="Found the button",
        )

        with patch.object(
            failover_grounder,
            "_create_adapter",
            return_value=MagicMock(get_action=AsyncMock(return_value=mock_result)),
        ):
            result = await failover_grounder.get_action("click button", "screenshot_b64")

            assert result.action == "left_click"
            assert result.coordinate == (100, 200)
            assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_get_action_with_context_delegates_to_adapter(self, failover_grounder):
        """get_action_with_context delegates to adapter with history."""
        mock_result = FaraToolCall(
            action="type",
            coordinate=(150, 250),
            text="hello",
            confidence=0.9,
            reasoning="Typing in the field",
        )

        history = [
            StepContext(
                screenshot_b64="prev_screenshot",
                action="[1] left_click at (100, 200) ✓",
                reasoning="Clicked the input",
                success=True,
            ),
        ]

        # Mock adapter with get_action_with_context
        mock_adapter = MagicMock()
        mock_adapter.get_action_with_context = AsyncMock(return_value=mock_result)

        with patch.object(
            failover_grounder, "_create_adapter", return_value=mock_adapter
        ):
            result = await failover_grounder.get_action_with_context(
                "type hello", "screenshot_b64", history=history
            )

            assert result.action == "type"
            assert result.text == "hello"
            # Verify history was passed through
            mock_adapter.get_action_with_context.assert_called_once_with(
                "type hello", "screenshot_b64", history=history
            )

    @pytest.mark.asyncio
    async def test_get_action_with_context_falls_back_without_method(self, failover_grounder):
        """get_action_with_context falls back to get_action if adapter lacks method."""
        mock_result = FaraToolCall(
            action="scroll",
            direction="down",
            confidence=0.8,
        )

        # Mock adapter WITHOUT get_action_with_context
        mock_adapter = MagicMock(spec=["get_action"])  # Only has get_action
        mock_adapter.get_action = AsyncMock(return_value=mock_result)

        with patch.object(
            failover_grounder, "_create_adapter", return_value=mock_adapter
        ):
            result = await failover_grounder.get_action_with_context(
                "scroll down", "screenshot_b64", history=[]
            )

            assert result.action == "scroll"
            mock_adapter.get_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_action_with_context_retries_on_failure(self, failover_grounder):
        """get_action_with_context retries with next server on failure."""
        mock_success = FaraToolCall(action="terminate", confidence=1.0)

        # First adapter fails, second succeeds
        failing_adapter = MagicMock()
        failing_adapter.get_action_with_context = AsyncMock(
            side_effect=Exception("Server down")
        )
        working_adapter = MagicMock()
        working_adapter.get_action_with_context = AsyncMock(return_value=mock_success)

        call_count = 0

        def create_adapter(url, model):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return failing_adapter
            return working_adapter

        with patch.object(failover_grounder, "_create_adapter", side_effect=create_adapter):
            result = await failover_grounder.get_action_with_context(
                "goal", "screenshot_b64", history=[]
            )

            assert result.action == "terminate"
            assert call_count == 2  # Tried twice


class TestLMStudioDiscovery:
    """Tests for LM Studio server discovery."""

    @pytest.mark.asyncio
    async def test_discover_prefers_loaded_model(self):
        """Discovery returns server with model already loaded."""
        from surf_mcp.llm.lmstudio_discovery import discover_fara_server, probe_server

        # Mock probe_server to return different states
        async def mock_probe(url, timeout=2.0):
            if "server1" in url:
                return ServerInfo(
                    name="server1",
                    url=url,
                    reachable=True,
                    models=[ModelInfo(id="fara-7b", state="not-loaded", type="vlm")],
                )
            else:
                return ServerInfo(
                    name="server2",
                    url=url,
                    reachable=True,
                    models=[ModelInfo(id="fara-7b", state="loaded", type="vlm")],
                )

        with patch(
            "surf_mcp.llm.lmstudio_discovery.probe_server",
            side_effect=mock_probe,
        ):
            with patch.dict(
                os.environ,
                {
                    "LMSTUDIO_SERVERS": "server1=http://server1/v1,server2=http://server2/v1",
                    "FARA_MODEL_IDS": "fara-7b",
                },
            ):
                url, model = await discover_fara_server()

                # Should pick server2 because model is loaded
                assert "server2" in url
                assert model == "fara-7b"

    @pytest.mark.asyncio
    async def test_discover_falls_back_when_no_loaded(self):
        """Discovery returns first available when none loaded."""
        from surf_mcp.llm.lmstudio_discovery import discover_fara_server

        async def mock_probe(url, timeout=2.0):
            return ServerInfo(
                name="test",
                url=url,
                reachable=True,
                models=[ModelInfo(id="fara-7b", state="not-loaded", type="vlm")],
            )

        with patch(
            "surf_mcp.llm.lmstudio_discovery.probe_server",
            side_effect=mock_probe,
        ):
            with patch.dict(
                os.environ,
                {
                    "LMSTUDIO_SERVERS": "gpu1=http://first/v1,gpu2=http://second/v1",
                    "FARA_MODEL_IDS": "fara-7b",
                },
            ):
                url, model = await discover_fara_server()

                # Should pick first server since none have it loaded
                assert "first" in url


class TestFaraResponseParsing:
    """Tests for Fara tool_call response parsing."""

    @pytest.fixture
    def grounder(self):
        """Create an OpenAI grounder for testing parsing."""
        from surf_mcp.llm.openai_adapter import OpenAIVisualGrounder
        return OpenAIVisualGrounder()

    def test_parse_computer_use_left_click(self, grounder):
        """Parse Fara's computer_use left_click format."""
        tool_json = {
            "name": "computer_use",
            "arguments": {"action": "left_click", "coordinate": [624, 280]}
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is True
        assert result.x == 624
        assert result.y == 280
        assert result.confidence == 1.0
        assert "left_click" in result.reasoning

    def test_parse_computer_use_type_with_coords(self, grounder):
        """Parse Fara's computer_use type action with coordinates."""
        tool_json = {
            "name": "computer_use",
            "arguments": {"action": "type", "text": "hello", "coordinate": [100, 200]}
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is True
        assert result.x == 100
        assert result.y == 200

    def test_parse_playwright_format(self, grounder):
        """Parse Fara's playwright tool_call format."""
        tool_json = {
            "name": "playwright",
            "arguments": {"action": "click", "coordinate": [624, 280]}
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is True
        assert result.x == 624
        assert result.y == 280
        assert result.confidence == 1.0

    def test_parse_computer_format(self, grounder):
        """Parse Fara's computer tool_call format."""
        tool_json = {
            "name": "computer",
            "arguments": {"action": "left_click", "coordinate": [100, 200]}
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is True
        assert result.x == 100
        assert result.y == 200

    def test_parse_scroll_no_coordinates(self, grounder):
        """Parse Fara's scroll action (no coordinates needed)."""
        tool_json = {
            "name": "computer_use",
            "arguments": {"action": "scroll", "pixels": 100}
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is True
        assert result.x is None
        assert result.y is None
        assert "scroll" in result.reasoning

    def test_parse_terminate_action(self, grounder):
        """Parse Fara's terminate action."""
        tool_json = {
            "name": "computer_use",
            "arguments": {"action": "terminate", "status": "success"}
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is True
        assert result.x is None
        assert "terminate" in result.reasoning

    def test_parse_serpico_format(self, grounder):
        """Parse Fara's serpico format where x field contains [x, y] coords."""
        tool_json = {
            "name": "serpico",
            "arguments": {"found": True, "x": [300, 400]}  # x=[x_coord, y_coord]
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is True
        assert result.x == 300  # x_coord[0]
        assert result.y == 400  # x_coord[1]

    def test_parse_json_output_format(self, grounder):
        """Parse Fara's json_output format with bounding boxes."""
        tool_json = {
            "name": "json_output",
            "value": {
                "found": True,
                "x": [720, 446],
                "y": [483, 351],
                "confidence": 1.0,
                "reasoning": "Found the button"
            }
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is True
        # Center of bounding box
        assert result.x == 583  # (720 + 446) / 2
        assert result.y == 417  # (483 + 351) / 2
        assert result.confidence == 1.0
        assert result.reasoning == "Found the button"

    def test_parse_json_output_not_found(self, grounder):
        """Parse json_output when element not found."""
        tool_json = {
            "name": "json_output",
            "value": {
                "found": False,
                "reasoning": "Element not visible"
            }
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is False
        assert "not visible" in result.reasoning

    def test_parse_unknown_format_returns_not_found(self, grounder):
        """Unknown tool_call format returns found=False with debug info."""
        tool_json = {
            "name": "unknown_tool",
            "arguments": {"something": "else"}
        }
        result = grounder._normalize_tool_call(tool_json)

        assert result.found is False
        assert "unknown_tool" in result.reasoning

    def test_parse_response_with_tool_call_tags(self, grounder):
        """Parse response wrapped in <tool_call> tags."""
        text = '<tool_call>{"name": "playwright", "arguments": {"action": "click", "coordinate": [512, 384]}}</tool_call>'
        result = grounder._parse_response(text)

        assert result.found is True
        assert result.x == 512
        assert result.y == 384

    def test_parse_response_with_markdown_json(self, grounder):
        """Parse response with markdown code block."""
        text = '```json\n{"found": true, "x": 100, "y": 200, "confidence": 0.95}\n```'
        result = grounder._parse_response(text)

        assert result.found is True
        assert result.x == 100
        assert result.y == 200
        assert result.confidence == 0.95

    def test_parse_response_with_raw_json(self, grounder):
        """Parse raw JSON response."""
        text = '{"found": true, "x": 50, "y": 75, "confidence": 0.8, "reasoning": "Found button"}'
        result = grounder._parse_response(text)

        assert result.found is True
        assert result.x == 50
        assert result.y == 75

    def test_parse_response_unparseable_returns_not_found(self, grounder):
        """Unparseable response returns found=False."""
        text = "I cannot find the element you described."
        result = grounder._parse_response(text)

        assert result.found is False


class TestServerParsing:
    """Tests for LMSTUDIO_SERVERS parsing."""

    def test_parse_multiple_servers(self):
        """Parses comma-separated server list."""
        from surf_mcp.llm.lmstudio_discovery import parse_lmstudio_servers

        with patch.dict(
            os.environ,
            {"LMSTUDIO_SERVERS": "gpu1=http://a:1234/v1,gpu2=http://b:1234/v1"},
        ):
            servers = parse_lmstudio_servers()

            assert servers == {
                "gpu1": "http://a:1234/v1",
                "gpu2": "http://b:1234/v1",
            }

    def test_parse_single_server(self):
        """Parses single server."""
        from surf_mcp.llm.lmstudio_discovery import parse_lmstudio_servers

        with patch.dict(os.environ, {"LMSTUDIO_SERVERS": "main=http://localhost:1234/v1"}):
            servers = parse_lmstudio_servers()

            assert servers == {"main": "http://localhost:1234/v1"}

    def test_parse_fallback_when_empty(self):
        """Falls back to default when LMSTUDIO_SERVERS not set."""
        from surf_mcp.llm.lmstudio_discovery import parse_lmstudio_servers

        with patch.dict(os.environ, {}, clear=True):
            # Clear LMSTUDIO_SERVERS if it exists
            os.environ.pop("LMSTUDIO_SERVERS", None)
            servers = parse_lmstudio_servers()

            assert "default" in servers

    def test_parse_model_ids(self):
        """Parses comma-separated model IDs."""
        from surf_mcp.llm.lmstudio_discovery import get_fara_model_ids

        with patch.dict(os.environ, {"FARA_MODEL_IDS": "model-a,model-b,model-c"}):
            ids = get_fara_model_ids()

            assert ids == ["model-a", "model-b", "model-c"]


class TestUniformScaling:
    """Tests for proportional (non-anamorphic) image scaling."""

    @pytest.fixture
    def grounder(self):
        """Create OpenAI grounder for testing."""
        from surf_mcp.llm.openai_adapter import OpenAIVisualGrounder
        return OpenAIVisualGrounder()

    def test_scale_coordinates_uniform_landscape(self, grounder):
        """Scaling uses uniform factor for landscape images."""
        # Original: 1920x1080, native bounds: 1428x896
        # Scale to fit: min(1428/1920, 896/1080) = min(0.744, 0.830) = 0.744
        # Fara sees image at ~1428x803 (width-limited)
        # Coordinate (714, 400) in scaled -> (714/0.744, 400/0.744) = (960, 538)
        original_size = (1920, 1080)
        native_size = (1428, 896)

        x, y = grounder._scale_coordinates(714, 400, original_size, native_size)

        # Uniform scaling: same factor for both axes
        expected_scale = min(1428 / 1920, 896 / 1080)  # 0.74375
        expected_x = int(714 / expected_scale)  # ~960
        expected_y = int(400 / expected_scale)  # ~538

        assert x == expected_x
        assert y == expected_y
        # Both should use same inverse factor
        assert abs(x / 714 - y / 400) < 0.01  # Same ratio

    def test_scale_coordinates_uniform_tall_image(self, grounder):
        """Scaling uses uniform factor for height-limited images."""
        # Original: 1200x1800 (portrait), native bounds: 896x1428
        # Scale to fit: min(896/1200, 1428/1800) = min(0.747, 0.793) = 0.747
        original_size = (1200, 1800)
        native_size = (896, 1428)

        x, y = grounder._scale_coordinates(448, 714, original_size, native_size)

        expected_scale = min(896 / 1200, 1428 / 1800)
        expected_x = int(448 / expected_scale)
        expected_y = int(714 / expected_scale)

        assert x == expected_x
        assert y == expected_y

    def test_scale_coordinates_no_distortion(self, grounder):
        """Verify aspect ratio preserved in coordinate transform."""
        # Wide image: 2401x1121 (aspect ~2.14)
        # Native: 1428x896 (aspect ~1.59)
        # Old code would stretch differently in X vs Y
        original_size = (2401, 1121)
        native_size = (1428, 896)

        # Point at center of scaled image
        x, y = grounder._scale_coordinates(714, 448, original_size, native_size)

        # Ratio should be preserved (same scale factor)
        scale = min(1428 / 2401, 896 / 1121)  # ~0.595
        assert abs(x / 714 - y / 448) < 0.01
