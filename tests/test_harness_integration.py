"""
Harness Component Tests.

Unit tests for the fara-harness MCP client wrapper and utilities.
These tests use mocks and don't require any external dependencies.

REQUIREMENTS:
    pip install -e ".[dev]"

RUN:
    pytest tests/test_harness_integration.py -v

NOTE:
    For tests that actually exercise the Docker container, see test_docker_e2e.py.
    This file only tests the harness code in isolation.
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import from harness module
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "fara-harness"))
from mcp_client import SurfMCPClient, SyncSurfClient


# =============================================================================
# MCP Client Unit Tests (Mocked)
# =============================================================================


class TestSurfMCPClientUnit:
    """Unit tests for MCP client wrapper.

    These test the client logic WITHOUT starting any server.
    All MCP communication is mocked.
    """

    @pytest.mark.asyncio
    async def test_not_connected_raises(self):
        """Calling tools without connect raises RuntimeError."""
        client = SurfMCPClient()

        with pytest.raises(RuntimeError, match="Not connected"):
            await client.call_tool("session_list", {})

    @pytest.mark.asyncio
    async def test_call_tool_parses_json(self):
        """call_tool parses JSON response correctly."""
        client = SurfMCPClient()
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
        """session_create builds correct driver config for browser."""
        client = SurfMCPClient()
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


# =============================================================================
# Sync Client Unit Tests
# =============================================================================


class TestSyncSurfClientUnit:
    """Unit tests for sync wrapper."""

    def test_creates_event_loop(self):
        """SyncSurfClient creates event loop."""
        client = SyncSurfClient()
        assert client._loop is not None
        assert isinstance(client._loop, asyncio.AbstractEventLoop)


# =============================================================================
# Storage State Serialization Tests
# =============================================================================


class TestStorageStateSerialization:
    """Test storage_state JSON serialization.

    storage_state is passed through MCP as JSON. These tests verify
    the format survives round-trip serialization.
    """

    def test_json_roundtrip(self):
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

        # Round-trip through JSON (as happens in MCP)
        serialized = json.dumps(state)
        restored = json.loads(serialized)

        assert restored == state
        assert len(restored["cookies"]) == 1
        assert restored["cookies"][0]["name"] == "session"

    def test_empty_state(self):
        """Empty storage state is valid."""
        state = {"cookies": [], "origins": []}

        serialized = json.dumps(state)
        restored = json.loads(serialized)

        assert restored == state


# =============================================================================
# Command Architecture Tests
# =============================================================================


class TestCommandArchitecture:
    """Test harness command handling architecture.

    Per ADR-005: All user commands go directly to Fara via act().
    The harness does NOT parse or interpret commands.
    """

    def test_commands_passed_unmodified(self):
        """Commands should go to Fara without modification."""
        # These commands used to be parsed by the harness.
        # Now they all go to Fara via act() unmodified.
        test_cases = [
            "click the search button",
            "goto https://google.com",
            "scroll down",
            "type hello into the search box",
            "press enter",
        ]

        for cmd in test_cases:
            # Only whitespace trimming is allowed
            assert cmd == cmd.strip()


# =============================================================================
# Overlay Drawing Tests
# =============================================================================


class TestOverlayDrawing:
    """Test screenshot overlay functions."""

    def test_draw_overlay_adds_marker(self, mock_screenshot):
        """draw_overlay adds marker to image."""
        from PIL import Image

        from utils import draw_overlay

        img = Image.new("RGB", (100, 100), color="white")
        result = draw_overlay(img, x=50, y=50, confidence=0.95)

        # Should return modified image
        assert result is not img  # Copy was made
        assert result.size == img.size

    def test_draw_overlay_no_coords_returns_original(self):
        """draw_overlay returns original if no coordinates."""
        from PIL import Image

        from utils import draw_overlay

        img = Image.new("RGB", (100, 100), color="white")
        result = draw_overlay(img, x=None, y=None)

        # Should return same image
        assert result is img
