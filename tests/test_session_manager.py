"""
Tests for SessionManager.
"""

import pytest

from surf_mcp.session_manager import SessionManager


@pytest.mark.browser
@pytest.mark.asyncio
async def test_create_session_browser():
    """Test creating a session with browser driver."""
    manager = SessionManager(max_sessions=5)

    session = await manager.create_session({
        "web": {"type": "browser", "headless": True, "visual_grounding": False}
    })

    assert session.session_id is not None
    assert "web" in session.drivers
    assert session.drivers["web"].driver_type == "browser"

    await manager.cleanup_all()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_create_session_multiple_drivers():
    """Test creating session with multiple browser drivers."""
    manager = SessionManager(max_sessions=5)

    session = await manager.create_session({
        "web1": {"type": "browser", "headless": True, "visual_grounding": False},
        "web2": {"type": "browser", "headless": True, "visual_grounding": False},
    })

    assert "web1" in session.drivers
    assert "web2" in session.drivers

    await manager.cleanup_all()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_get_session():
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
async def test_get_session_not_found():
    """Test getting a non-existent session."""
    manager = SessionManager()

    retrieved = await manager.get_session("nonexistent")

    assert retrieved is None


@pytest.mark.browser
@pytest.mark.asyncio
async def test_destroy_session():
    """Test destroying a session."""
    manager = SessionManager()

    session = await manager.create_session({
        "web": {"type": "browser", "headless": True, "visual_grounding": False}
    })

    summary = await manager.destroy_session(session.session_id)

    assert summary is not None
    assert await manager.get_session(session.session_id) is None


@pytest.mark.browser
@pytest.mark.asyncio
async def test_list_sessions():
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


@pytest.mark.browser
@pytest.mark.asyncio
async def test_max_sessions_limit():
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


@pytest.mark.browser
@pytest.mark.asyncio
async def test_cleanup_all():
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
