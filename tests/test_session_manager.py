"""
Tests for SessionManager.
"""

import pytest

from surf_mcp.session_manager import SessionManager


@pytest.mark.asyncio
async def test_create_session_filesystem(temp_workspace):
    """Test creating a session with filesystem driver."""
    manager = SessionManager(max_sessions=5)

    session = await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace), "sandbox": True}
    })

    assert session.session_id is not None
    assert "fs" in session.drivers
    assert session.drivers["fs"].driver_type == "filesystem"


@pytest.mark.asyncio
async def test_create_session_multiple_drivers(temp_workspace):
    """Test creating session with multiple drivers."""
    manager = SessionManager(max_sessions=5)

    # Note: Browser driver requires playwright, so we'll just test filesystem
    session = await manager.create_session({
        "fs1": {"type": "filesystem", "root": str(temp_workspace)},
        "fs2": {"type": "filesystem", "root": str(temp_workspace)},
    })

    assert "fs1" in session.drivers
    assert "fs2" in session.drivers


@pytest.mark.asyncio
async def test_get_session(temp_workspace):
    """Test getting a session by ID."""
    manager = SessionManager()

    created = await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace)}
    })

    retrieved = await manager.get_session(created.session_id)

    assert retrieved is not None
    assert retrieved.session_id == created.session_id


@pytest.mark.asyncio
async def test_get_session_not_found(temp_workspace):
    """Test getting a non-existent session."""
    manager = SessionManager()

    retrieved = await manager.get_session("nonexistent")

    assert retrieved is None


@pytest.mark.asyncio
async def test_destroy_session(temp_workspace):
    """Test destroying a session."""
    manager = SessionManager()

    session = await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace)}
    })

    summary = await manager.destroy_session(session.session_id)

    assert summary is not None
    assert await manager.get_session(session.session_id) is None


@pytest.mark.asyncio
async def test_list_sessions(temp_workspace):
    """Test listing sessions."""
    manager = SessionManager()

    await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace)}
    })
    await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace)}
    })

    sessions = await manager.list_sessions()

    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_max_sessions_limit(temp_workspace):
    """Test max sessions enforcement."""
    manager = SessionManager(max_sessions=2)

    await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace)}
    })
    await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace)}
    })

    # Third session should cleanup oldest
    session3 = await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace)}
    })

    sessions = await manager.list_sessions()
    assert len(sessions) == 2
    assert session3.session_id in [s["session_id"] for s in sessions]


@pytest.mark.asyncio
async def test_cleanup_all(temp_workspace):
    """Test cleaning up all sessions."""
    manager = SessionManager()

    await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace)}
    })
    await manager.create_session({
        "fs": {"type": "filesystem", "root": str(temp_workspace)}
    })

    await manager.cleanup_all()

    sessions = await manager.list_sessions()
    assert len(sessions) == 0
