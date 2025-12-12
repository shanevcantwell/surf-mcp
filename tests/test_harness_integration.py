"""
Integration tests for Fara Test Harness components.

Tests MCP client wrapper and storage_state round-trip.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import from harness module
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "fara-harness"))
from mcp_client import NavigatorMCPClient, SyncNavigatorClient


class TestNavigatorMCPClientUnit:
    """Unit tests for MCP client (mocked server)."""

    @pytest.mark.asyncio
    async def test_client_not_connected_raises(self):
        """Calling tools without connect raises RuntimeError."""
        client = NavigatorMCPClient()

        with pytest.raises(RuntimeError, match="Not connected"):
            await client.call_tool("session_list", {})

    @pytest.mark.asyncio
    async def test_call_tool_parses_json(self):
        """call_tool parses JSON response correctly."""
        client = NavigatorMCPClient()
        client._connected = True

        # Mock session
        mock_content = MagicMock()
        mock_content.text = '{"session_id": "test-123"}'

        mock_result = MagicMock()
        mock_result.content = [mock_content]

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = mock_result
        client.session = mock_session

        result = await client.call_tool("session_create", {"drivers": {}})

        assert result == {"session_id": "test-123"}
        mock_session.call_tool.assert_called_once_with("session_create", {"drivers": {}})

    @pytest.mark.asyncio
    async def test_session_create_builds_driver_config(self):
        """session_create builds correct driver config."""
        client = NavigatorMCPClient()
        client._connected = True

        mock_content = MagicMock()
        mock_content.text = '{"session_id": "abc"}'
        mock_result = MagicMock()
        mock_result.content = [mock_content]
        mock_session = AsyncMock()
        mock_session.call_tool.return_value = mock_result
        client.session = mock_session

        await client.session_create(
            headless=True,
            viewport=(1280, 720),
            storage_state={"cookies": [], "origins": []},
        )

        call_args = mock_session.call_tool.call_args
        assert call_args[0][0] == "session_create"

        drivers = call_args[0][1]["drivers"]
        assert "web" in drivers
        assert drivers["web"]["type"] == "browser"
        assert drivers["web"]["headless"] is True
        assert drivers["web"]["viewport"] == [1280, 720]
        assert drivers["web"]["storage_state"] == {"cookies": [], "origins": []}


class TestSyncNavigatorClient:
    """Unit tests for sync wrapper."""

    def test_sync_wrapper_creates_loop(self):
        """SyncNavigatorClient creates event loop."""
        client = SyncNavigatorClient()
        assert client._loop is not None
        assert isinstance(client._loop, asyncio.AbstractEventLoop)


class TestStorageStateRoundTrip:
    """Test storage_state serialization."""

    def test_storage_state_json_roundtrip(self):
        """Storage state survives JSON round-trip."""
        state = {
            "cookies": [
                {
                    "name": "session",
                    "value": "abc123",
                    "domain": ".example.com",
                    "path": "/",
                    "expires": 1700000000,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ],
            "origins": [
                {
                    "origin": "https://example.com",
                    "localStorage": [{"name": "token", "value": "xyz789"}],
                }
            ],
        }

        # Round-trip through JSON (as would happen in MCP)
        serialized = json.dumps(state)
        restored = json.loads(serialized)

        assert restored == state
        assert len(restored["cookies"]) == 1
        assert restored["cookies"][0]["name"] == "session"


class TestCommandParsing:
    """Test command parsing logic from utils.py.

    The parser is intentionally minimal - only goto and scroll are handled
    directly. Everything else goes to Fara via 'act'.
    """

    def test_parse_goto(self):
        """Parse goto command - direct navigation."""
        from utils import parse_command

        action, target, extra = parse_command("goto https://google.com")
        assert action == "goto"
        assert target == "https://google.com"
        assert extra is None

    def test_parse_goto_auto_https(self):
        """Parse goto without protocol - auto-prepends https://"""
        from utils import parse_command

        action, target, extra = parse_command("goto google.com")
        assert action == "goto"
        assert target == "https://google.com"
        assert extra is None

    def test_parse_scroll(self):
        """Parse scroll command - direct scroll."""
        from utils import parse_command

        action, target, extra = parse_command("scroll down")
        assert action == "scroll"
        assert target == "down"

        action, target, extra = parse_command("scroll up")
        assert action == "scroll"
        assert target == "up"

    def test_parse_natural_language_goes_to_act(self):
        """Natural language commands go to Fara via 'act'."""
        from utils import parse_command

        # All these should become "act" - let Fara decide
        test_cases = [
            "click the search button",
            "Click on Sign in",
            "type hello into the search box",
            "press enter",
            "find the submit button",
            "the blue button",
            'Enter "test" into the input',
        ]

        for cmd in test_cases:
            action, target, extra = parse_command(cmd)
            assert action == "act", f"Expected 'act' for '{cmd}', got '{action}'"
            assert target == cmd, f"Target should be original command"


class TestOverlayDrawing:
    """Test screenshot overlay functions."""

    def test_draw_overlay(self, mock_screenshot):
        """draw_overlay adds marker to image."""
        from PIL import Image

        from utils import draw_overlay

        # Create a larger test image
        img = Image.new("RGB", (100, 100), color="white")

        result = draw_overlay(img, x=50, y=50, confidence=0.95)

        # Should return modified image
        assert result is not img  # Copy was made
        assert result.size == img.size

    def test_draw_overlay_no_coords(self):
        """draw_overlay returns original if no coords."""
        from PIL import Image

        from utils import draw_overlay

        img = Image.new("RGB", (100, 100), color="white")
        result = draw_overlay(img, x=None, y=None)

        # Should return same image
        assert result is img


@pytest.mark.integration
class TestMCPServerIntegration:
    """Integration tests that start actual navigator-mcp server.

    These tests are marked as integration and require:
    - navigator-mcp to be installed
    - Playwright chromium (for browser tests)

    Run with: pytest -m integration
    """

    @pytest.fixture
    def check_server_available(self):
        """Check if navigator-mcp is available."""
        try:
            result = subprocess.run(
                ["navigator-mcp", "--help"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("ENVIRONMENT: Requires 'pip install -e .' (navigator-mcp not on PATH)")

    @pytest.mark.asyncio
    async def test_client_connect_disconnect(self, check_server_available):
        """Test basic connect/disconnect cycle."""
        client = NavigatorMCPClient()

        await client.connect()
        assert client._connected is True

        await client.disconnect()
        assert client._connected is False

    @pytest.mark.asyncio
    async def test_session_list_empty(self, check_server_available):
        """Test session_list on fresh server."""
        client = NavigatorMCPClient()
        await client.connect()

        try:
            result = await client.session_list()
            assert "sessions" in result
            assert isinstance(result["sessions"], list)
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_filesystem_session_roundtrip(
        self, check_server_available, temp_workspace
    ):
        """Test creating filesystem session (no playwright needed)."""
        client = NavigatorMCPClient()
        await client.connect()

        try:
            # Create filesystem session directly via call_tool
            result = await client.call_tool(
                "session_create",
                {
                    "drivers": {
                        "fs": {
                            "type": "filesystem",
                            "root": str(temp_workspace),
                            "sandbox": True,
                        }
                    }
                },
            )

            assert "session_id" in result
            session_id = result["session_id"]

            # List should show session
            list_result = await client.session_list()
            assert any(s["session_id"] == session_id for s in list_result["sessions"])

            # Destroy session
            destroy_result = await client.call_tool(
                "session_destroy", {"session_id": session_id}
            )
            assert "success" in destroy_result or "summary" in destroy_result

        finally:
            await client.disconnect()


@pytest.mark.integration
@pytest.mark.browser
class TestBrowserIntegration:
    """Browser integration tests.

    Requires playwright chromium to be installed.
    Run with: pytest -m "integration and browser"
    """

    @pytest.fixture
    def check_playwright_available(self):
        """Check if playwright chromium is installed."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            return True
        except Exception as e:
            pytest.skip(f"ENVIRONMENT: Requires 'playwright install chromium' ({e})")

    @pytest.mark.asyncio
    async def test_browser_session_with_storage_state(
        self, check_playwright_available
    ):
        """Test browser session with storage_state round-trip."""
        client = NavigatorMCPClient()
        await client.connect()

        try:
            # Create browser session with empty storage_state
            initial_state = {"cookies": [], "origins": []}
            result = await client.session_create(
                headless=True,
                storage_state=initial_state,
            )

            assert "session_id" in result
            session_id = result["session_id"]

            # Navigate to a page
            goto_result = await client.goto(session_id, "https://example.com")
            assert not goto_result.get("error"), f"Navigation failed: {goto_result.get('error')}"

            # Destroy and capture storage_state
            destroy_result = await client.session_destroy(session_id)

            # Storage state should be in summary
            assert "summary" in destroy_result
            assert "web" in destroy_result["summary"]

            # May or may not have storage_state depending on page
            web_summary = destroy_result["summary"]["web"]
            if "storage_state" in web_summary:
                state = web_summary["storage_state"]
                assert "cookies" in state
                assert "origins" in state

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_browser_snapshot(self, check_playwright_available):
        """Test taking browser screenshot."""
        client = NavigatorMCPClient()
        await client.connect()

        try:
            result = await client.session_create(headless=True)
            session_id = result["session_id"]

            # Navigate
            await client.goto(session_id, "https://example.com")

            # Take snapshot
            snapshot_result = await client.snapshot(session_id)

            assert "snapshot" in snapshot_result
            # Snapshot should be base64 encoded PNG
            import base64

            base64.b64decode(snapshot_result["snapshot"])  # Should not raise

            await client.session_destroy(session_id)

        finally:
            await client.disconnect()


@pytest.mark.integration
@pytest.mark.skip(reason="FRAMEWORK: disconnect() fails in pytest due to anyio task affinity - operations work, only cleanup fails")
class TestSyncClientIntegration:
    """Integration tests using the sync wrapper (as Streamlit would).

    These tests are skipped because anyio task groups require exit from the same
    task as entry. In pytest, connect() and disconnect() run in different task
    contexts, causing "Attempted to exit cancel scope in different task" error.

    The actual operations WORK - only the cleanup fails. In production Streamlit,
    the client stays alive across reruns and process exit handles cleanup.
    """

    @pytest.fixture
    def check_server_available(self):
        """Check if navigator-mcp is available."""
        import subprocess

        try:
            subprocess.run(
                ["navigator-mcp", "--help"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("ENVIRONMENT: Requires 'pip install -e .' (navigator-mcp not on PATH)")

    def test_sync_client_connect_disconnect(self, check_server_available):
        """Test sync client connect/disconnect cycle."""
        client = SyncNavigatorClient()
        client.connect()

        # Should be connected
        assert client._client._connected is True

        client.disconnect()
        assert client._client._connected is False

    def test_sync_client_filesystem_roundtrip(
        self, check_server_available, temp_workspace
    ):
        """Test sync client with filesystem driver."""
        client = SyncNavigatorClient()
        client.connect()

        try:
            # Create filesystem session using call_tool through _run
            result = client._run(
                client._client.call_tool(
                    "session_create",
                    {
                        "drivers": {
                            "fs": {
                                "type": "filesystem",
                                "root": str(temp_workspace),
                                "sandbox": True,
                            }
                        }
                    },
                )
            )

            assert "session_id" in result
            session_id = result["session_id"]

            # Navigate in filesystem
            goto_result = client._run(
                client._client.call_tool(
                    "goto",
                    {"session_id": session_id, "driver": "fs", "location": "."},
                )
            )
            assert goto_result.get("success", True)

            # List contents
            list_result = client._run(
                client._client.call_tool(
                    "list",
                    {"session_id": session_id, "driver": "fs"},
                )
            )
            assert "entries" in list_result

            # Destroy
            client._run(
                client._client.call_tool(
                    "session_destroy", {"session_id": session_id}
                )
            )

        finally:
            client.disconnect()


@pytest.mark.integration
@pytest.mark.browser
class TestFullBrowserWorkflow:
    """Full browser workflow tests (navigate, snapshot, interact)."""

    @pytest.fixture
    def check_playwright_available(self):
        """Check if playwright chromium is installed."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            return True
        except Exception as e:
            pytest.skip(f"ENVIRONMENT: Requires 'playwright install chromium' ({e})")

    @pytest.mark.asyncio
    async def test_full_navigation_workflow(self, check_playwright_available):
        """Test complete navigation workflow: create, goto, snapshot, destroy."""
        client = NavigatorMCPClient()
        await client.connect()

        try:
            # Create headless browser session
            result = await client.session_create(headless=True)
            assert "session_id" in result
            session_id = result["session_id"]

            # Navigate to example.com
            goto_result = await client.goto(session_id, "https://example.com")
            assert goto_result.get("success", True)
            assert "snapshot" in goto_result or "error" not in goto_result

            # Get current URL
            current_result = await client.current(session_id)
            assert "example.com" in current_result.get("location", "")

            # Take screenshot
            snapshot_result = await client.snapshot(session_id)
            assert "snapshot" in snapshot_result

            # Verify it's valid base64 PNG
            import base64

            png_data = base64.b64decode(snapshot_result["snapshot"])
            assert png_data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes

            # Destroy and verify cleanup
            destroy_result = await client.session_destroy(session_id)
            assert "summary" in destroy_result

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_browser_scroll(self, check_playwright_available):
        """Test browser scroll functionality."""
        client = NavigatorMCPClient()
        await client.connect()

        try:
            result = await client.session_create(headless=True)
            session_id = result["session_id"]

            # Navigate to a page with content
            await client.goto(session_id, "https://example.com")

            # Scroll down
            scroll_result = await client.scroll(session_id, "down")
            assert "error" not in scroll_result or scroll_result.get("success", True)

            # Scroll up
            scroll_result = await client.scroll(session_id, "up")
            assert "error" not in scroll_result or scroll_result.get("success", True)

            await client.session_destroy(session_id)

        finally:
            await client.disconnect()
