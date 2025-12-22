"""
Session Manager Tests.

Tests for SessionManager class using real Playwright browser.
These require Chromium installed locally (not in Docker).

REQUIREMENTS:
    pip install -e ".[dev]"
    playwright install chromium

RUN:
    pytest tests/test_session_manager.py -v

NOTE:
    These tests use LOCAL Playwright, not Docker.
    For Docker-based browser tests, see test_docker_e2e.py.
"""

import pytest

# Skip entire module if surf_mcp not installed
pytest.importorskip("surf_mcp", reason="Requires: pip install -e '.[dev]'")

from surf_mcp.session_manager import SessionManager


# =============================================================================
# Session Lifecycle Tests
# =============================================================================


@pytest.mark.browser
class TestSessionLifecycle:
    """Tests for session creation and destruction."""

    @pytest.mark.asyncio
    async def test_create_session_browser(self):
        """Test creating a session with browser driver."""
        manager = SessionManager(max_sessions=5)

        session = await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })

        assert session.session_id is not None
        assert "web" in session.drivers
        assert session.drivers["web"].driver_type == "browser"

        await manager.cleanup_all()

    @pytest.mark.asyncio
    async def test_create_session_multiple_drivers(self):
        """Test creating session with multiple browser drivers."""
        manager = SessionManager(max_sessions=5)

        session = await manager.create_session({
            "web1": {"type": "browser", "headless": True, "visual_grounding": False},
            "web2": {"type": "browser", "headless": True, "visual_grounding": False},
        })

        assert "web1" in session.drivers
        assert "web2" in session.drivers

        await manager.cleanup_all()

    @pytest.mark.asyncio
    async def test_destroy_session(self):
        """Test destroying a session."""
        manager = SessionManager()

        session = await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })

        summary = await manager.destroy_session(session.session_id)

        assert summary is not None
        assert await manager.get_session(session.session_id) is None


# =============================================================================
# Session Retrieval Tests
# =============================================================================


@pytest.mark.browser
class TestSessionRetrieval:
    """Tests for getting and listing sessions."""

    @pytest.mark.asyncio
    async def test_get_session(self):
        """Test getting a session by ID."""
        manager = SessionManager()

        created = await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })

        retrieved = await manager.get_session(created.session_id)

        assert retrieved is not None
        assert retrieved.session_id == created.session_id

        await manager.cleanup_all()

    @pytest.mark.asyncio
    async def test_get_session_not_found(self):
        """Test getting a non-existent session."""
        manager = SessionManager()

        retrieved = await manager.get_session("nonexistent")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        """Test listing sessions."""
        manager = SessionManager()

        await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })
        await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })

        sessions = await manager.list_sessions()

        assert len(sessions) == 2

        await manager.cleanup_all()


# =============================================================================
# Session Limits Tests
# =============================================================================


@pytest.mark.browser
class TestSessionLimits:
    """Tests for session limits and cleanup."""

    @pytest.mark.asyncio
    async def test_max_sessions_limit(self):
        """Test max sessions enforcement."""
        manager = SessionManager(max_sessions=2)

        await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })
        await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })

        # Third session should cleanup oldest
        session3 = await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })

        sessions = await manager.list_sessions()
        assert len(sessions) == 2
        assert session3.session_id in [s["session_id"] for s in sessions]

        await manager.cleanup_all()

    @pytest.mark.asyncio
    async def test_cleanup_all(self):
        """Test cleaning up all sessions."""
        manager = SessionManager()

        await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })
        await manager.create_session({
            "web": {"type": "browser", "headless": True, "visual_grounding": False}
        })

        await manager.cleanup_all()

        sessions = await manager.list_sessions()
        assert len(sessions) == 0
