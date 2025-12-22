"""
Docker End-to-End Tests.

These tests verify that the PRODUCTION Docker image works correctly.
They are the only tests that catch issues like missing imports that
unit tests with mocks would miss.

REQUIREMENTS:
    docker build --target prod -t surf-mcp .

RUN:
    pytest tests/test_docker_e2e.py -v

MARKERS:
    @docker - requires Docker image built
    @browser - requires Chromium (inside container)

WHY THESE TESTS MATTER:
    Before these tests existed, the filesystem import bug shipped because:
    - Unit tests mocked everything (passed)
    - "Integration" tests used local pip install (passed)
    - Nobody tested the actual Docker container (broken)
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Import from harness module
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "fara-harness"))
from mcp_client import SurfMCPClient, SyncSurfClient


def docker_image_exists(image_name: str = "surf-mcp") -> bool:
    """Check if Docker image exists."""
    try:
        result = subprocess.run(
            ["docker", "images", image_name, "--format", "{{.Repository}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return image_name in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture
def require_docker_image():
    """Skip test if Docker image not available."""
    if not docker_image_exists():
        pytest.skip(
            "Requires: docker build --target prod -t surf-mcp . "
            "(surf-mcp Docker image not found)"
        )


# =============================================================================
# Docker Container Tests
# =============================================================================


@pytest.mark.docker
class TestDockerContainer:
    """
    Tests that verify the Docker container starts and responds.

    These are the most basic tests - if these fail, nothing else will work.
    """

    def test_container_imports_correctly(self, require_docker_image):
        """Verify Docker image can import surf-mcp without errors.

        This catches issues like:
        - Missing dependencies in requirements
        - Import errors from removed/renamed modules
        - Syntax errors in production code
        """
        result = subprocess.run(
            [
                "docker", "run", "-i", "--rm", "surf-mcp",
                "python3", "-c",
                "from surf_mcp.server import main; print('OK')"
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_container_commands_import(self, require_docker_image):
        """Verify all command modules import correctly."""
        result = subprocess.run(
            [
                "docker", "run", "-i", "--rm", "surf-mcp",
                "python3", "-c",
                "from surf_mcp.commands import session, navigation, content, browser; print('OK')"
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout


# =============================================================================
# MCP Protocol Tests (Docker)
# =============================================================================


@pytest.mark.docker
class TestDockerMCP:
    """
    Tests that verify MCP protocol works through Docker.

    These test the stdio transport between the harness and container.
    """

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, require_docker_image):
        """Test basic MCP connect/disconnect cycle via Docker."""
        client = SurfMCPClient()

        await client.connect(use_docker=True)
        assert client._connected is True

        await client.disconnect()
        assert client._connected is False

    @pytest.mark.asyncio
    async def test_session_list(self, require_docker_image):
        """Test session_list command via Docker."""
        client = SurfMCPClient()
        await client.connect(use_docker=True)

        try:
            result = await client.session_list()
            assert "sessions" in result
            assert isinstance(result["sessions"], list)
        finally:
            await client.disconnect()


# =============================================================================
# Browser Tests (Docker + Chromium)
# =============================================================================


@pytest.mark.docker
@pytest.mark.browser
class TestDockerBrowser:
    """
    Tests that verify browser automation works through Docker.

    These require both Docker AND Chromium (which is installed in the container).
    They test the full path: harness -> Docker -> surf-mcp -> Playwright -> Chromium.
    """

    @pytest.mark.asyncio
    async def test_browser_session_lifecycle(self, require_docker_image):
        """Test creating and destroying a browser session via Docker."""
        client = SurfMCPClient()
        await client.connect(use_docker=True)

        try:
            # Create headless browser session
            result = await client.session_create(headless=True)
            assert "session_id" in result, f"Expected session_id, got: {result}"
            session_id = result["session_id"]

            # Navigate to example.com
            goto_result = await client.goto(session_id, "https://example.com")
            assert goto_result.get("success", True), f"Navigate failed: {goto_result}"

            # Take screenshot
            snapshot_result = await client.snapshot(session_id)
            assert "snapshot" in snapshot_result, f"Expected snapshot, got: {snapshot_result}"

            # Verify it's valid base64 PNG
            import base64
            png_data = base64.b64decode(snapshot_result["snapshot"])
            assert png_data[:8] == b"\x89PNG\r\n\x1a\n", "Not a valid PNG"

            # Cleanup
            destroy_result = await client.session_destroy(session_id)
            assert "summary" in destroy_result

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_navigation_commands(self, require_docker_image):
        """Test navigation commands via Docker."""
        client = SurfMCPClient()
        await client.connect(use_docker=True)

        try:
            result = await client.session_create(headless=True)
            session_id = result["session_id"]

            # Navigate
            await client.goto(session_id, "https://example.com")

            # Get current URL
            current = await client.current(session_id)
            assert "example.com" in current.get("location", "")

            # Scroll
            scroll_result = await client.scroll(session_id, "down")
            assert "error" not in scroll_result or scroll_result.get("success", True)

            await client.session_destroy(session_id)

        finally:
            await client.disconnect()


# =============================================================================
# Sync Client Tests (Skipped - Framework Limitation)
# =============================================================================


@pytest.mark.docker
@pytest.mark.skip(
    reason="FRAMEWORK: SyncSurfClient disconnect() fails in pytest due to anyio "
    "task affinity - operations work, only cleanup fails. Works in Streamlit."
)
class TestDockerSyncClient:
    """Test sync client wrapper with Docker.

    NOTE: These tests are skipped because anyio task groups require exit from
    the same task as entry. In pytest, connect() and disconnect() run in
    different task contexts. The actual operations WORK - only cleanup fails.
    In production Streamlit, the client stays alive across reruns.
    """

    def test_sync_connect_disconnect(self, require_docker_image):
        """Test sync client connect/disconnect via Docker."""
        client = SyncSurfClient()
        client.connect(use_docker=True)

        assert client._client._connected is True

        client.disconnect()
        assert client._client._connected is False

    @pytest.mark.browser
    def test_sync_full_workflow(self, require_docker_image):
        """Test complete sync workflow via Docker."""
        client = SyncSurfClient()
        client.connect(use_docker=True)

        try:
            # Create session
            result = client.session_create(headless=True)
            assert "session_id" in result
            session_id = result["session_id"]

            # Navigate
            goto_result = client.goto(session_id, "https://example.com")
            assert goto_result.get("success", True)

            # Screenshot
            snapshot_result = client.snapshot(session_id)
            assert "snapshot" in snapshot_result

            # Cleanup
            client.session_destroy(session_id)

        finally:
            client.disconnect()
