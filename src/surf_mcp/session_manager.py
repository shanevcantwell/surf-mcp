"""
SessionManager - Multi-driver session pool for Navigator MCP.

Sessions can contain multiple drivers (e.g., filesystem + browser), enabling
cross-domain workflows like downloading web content to local files.

Session lifecycle:
1. Create session with driver configuration
2. Use drivers for navigation/interaction
3. Destroy session (cleanup all drivers)
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from .drivers.base import NavigatorDriver

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """A navigator session containing one or more drivers."""

    session_id: str
    drivers: Dict[str, NavigatorDriver] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()

    def get_driver(self, alias: str) -> Optional[NavigatorDriver]:
        """Get driver by alias."""
        driver = self.drivers.get(alias)
        if driver:
            self.touch()
        return driver

    async def cleanup(self) -> Dict[str, Any]:
        """
        Cleanup all drivers and return summary.

        Returns:
            Summary dict with per-driver stats and storage_state for browser drivers
        """
        summary = {}
        for alias, driver in self.drivers.items():
            driver_summary = {}

            # Collect driver-specific stats
            if hasattr(driver, "files_read"):
                driver_summary["files_read"] = driver.files_read
            if hasattr(driver, "files_written"):
                driver_summary["files_written"] = driver.files_written
            if hasattr(driver, "screenshots"):
                driver_summary["screenshots_taken"] = len(driver.screenshots)
            if hasattr(driver, "history"):
                driver_summary["locations_visited"] = [
                    h.location for h in driver.history
                ]

            # Capture storage_state BEFORE cleanup (browser drivers only)
            if hasattr(driver, "get_storage_state"):
                try:
                    storage_state = await driver.get_storage_state()
                    if storage_state:
                        driver_summary["storage_state"] = storage_state
                except Exception as e:
                    logger.warning(f"Error getting storage_state for {alias}: {e}")

            summary[alias] = driver_summary

            # Cleanup driver
            try:
                await driver.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up driver {alias}: {e}")

        return summary


class SessionManager:
    """
    Manages multiple navigator sessions with configurable limits.

    Thread-safe session pool with:
    - Max session enforcement
    - Idle timeout cleanup
    - Multi-driver sessions
    """

    def __init__(
        self,
        max_sessions: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self.max_sessions = max_sessions or int(
            os.environ.get("SURF_MAX_SESSIONS", 10)
        )
        self.timeout_seconds = timeout_seconds or int(
            os.environ.get("SURF_SESSION_TIMEOUT_SECONDS", 3600)
        )
        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self, drivers_config: Dict[str, Dict[str, Any]]
    ) -> Session:
        """
        Create a new session with specified drivers.

        Args:
            drivers_config: Dict mapping alias to driver config
                {
                    "fs": {"type": "filesystem", "root": "/path", "sandbox": True},
                    "web": {"type": "browser", "headless": True}
                }

        Returns:
            Created Session object

        Raises:
            ValueError: If max sessions exceeded or invalid driver type
        """
        async with self._lock:
            # Enforce max sessions
            if len(self._sessions) >= self.max_sessions:
                # Try to cleanup oldest idle session (unlocked - we already hold lock)
                await self._cleanup_oldest_session_unlocked()

                if len(self._sessions) >= self.max_sessions:
                    raise ValueError(
                        f"Maximum sessions ({self.max_sessions}) exceeded"
                    )

            session_id = str(uuid.uuid4())[:8]
            session = Session(session_id=session_id)

            # Create drivers
            for alias, config in drivers_config.items():
                driver_type = config.get("type")
                driver = await self._create_driver(driver_type, config)
                session.drivers[alias] = driver

            self._sessions[session_id] = session
            logger.info(
                f"Created session {session_id} with drivers: {list(drivers_config.keys())}"
            )

            return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID, updating activity timestamp."""
        session = self._sessions.get(session_id)
        if session:
            session.touch()
        return session

    async def destroy_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Destroy a session and cleanup all its drivers.

        Returns:
            Summary dict with per-driver stats, or None if session not found
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return None

            summary = await session.cleanup()
            logger.info(f"Destroyed session {session_id}")
            return summary

    async def list_sessions(self) -> list:
        """
        List all active sessions.

        Returns:
            List of session info dicts
        """
        return [
            {
                "session_id": session.session_id,
                "drivers": list(session.drivers.keys()),
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat(),
            }
            for session in self._sessions.values()
        ]

    async def _create_driver(
        self, driver_type: str, config: Dict[str, Any]
    ) -> NavigatorDriver:
        """Create a driver instance based on type."""
        if driver_type == "browser":
            from .drivers.browser import BrowserDriver
            from .security import validate_storage_state

            headless = config.get("headless", True)
            viewport = config.get("viewport", (1920, 1080))
            storage_state = config.get("storage_state")

            # Validate storage_state if provided
            if storage_state is not None:
                is_valid, error, sanitized = validate_storage_state(storage_state)
                if not is_valid:
                    raise ValueError(f"Invalid storage_state: {error}")
                storage_state = sanitized

            # Get visual grounder if configured
            grounder = None
            if config.get("visual_grounding", True):
                grounder = await self._get_visual_grounder()

            driver = BrowserDriver(
                headless=headless,
                viewport=viewport,
                visual_grounder=grounder,
                storage_state=storage_state,
            )
            await driver.initialize()
            return driver

        else:
            raise ValueError(f"Unknown driver type: {driver_type}")

    async def _get_visual_grounder(self, use_failover: bool = True):
        """
        Get visual grounder using the factory.

        Args:
            use_failover: If True, returns a FailoverGrounder that automatically
                         retries across servers. If False, returns a simple adapter.
        """
        from .llm.factory import VisualGrounderFactory

        if use_failover:
            return await VisualGrounderFactory.create_with_failover()
        else:
            return await VisualGrounderFactory.create()

    async def _cleanup_oldest_session_unlocked(self) -> None:
        """Remove oldest inactive session to make room.

        IMPORTANT: Caller must hold self._lock. This method does not acquire
        the lock to avoid deadlock when called from create_session.
        """
        if not self._sessions:
            return

        oldest = min(self._sessions.values(), key=lambda s: s.last_activity)
        session = self._sessions.pop(oldest.session_id, None)
        if session:
            await session.cleanup()
            logger.info(f"Cleaned up oldest session {oldest.session_id}")

    async def cleanup_all(self) -> None:
        """Cleanup all sessions (for shutdown)."""
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            await self.destroy_session(session_id)
        logger.info("All sessions cleaned up")
