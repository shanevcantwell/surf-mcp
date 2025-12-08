"""
NavigatorDriver - Abstract base class for all navigation contexts.

The Navigator abstraction provides a consistent mental model for "being somewhere
and moving around" across different domains (filesystem, browser, future: database, API).

All drivers implement:
- goto(location) - Navigate to a location
- current() - Get current location
- back() / forward() - Navigate history
- list() - List contents at current location
- read(target) - Read content
- snapshot() - Capture current state
- cleanup() - Release resources
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NavigatorState(BaseModel):
    """State returned after navigation operations."""

    location: str = Field(..., description="Current location (path or URL)")
    success: bool = Field(..., description="Whether the operation succeeded")
    snapshot: Optional[str] = Field(
        None, description="base64 screenshot or JSON directory listing"
    )
    error: Optional[str] = Field(None, description="Error message if failed")


class HistoryEntry(BaseModel):
    """Single entry in navigation history."""

    location: str = Field(..., description="Location that was navigated to")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When this navigation occurred"
    )
    action: str = Field(..., description="Action type: goto, back, forward")


class NavigatorDriver(ABC):
    """
    Abstract base for all navigation contexts.

    Drivers maintain:
    - Current location (cwd, URL, etc.)
    - Navigation history with forward/back capability
    - Domain-specific operations (file I/O, click/type, etc.)
    """

    driver_type: str  # "filesystem" or "browser"
    history: List[HistoryEntry]
    history_index: int

    @abstractmethod
    async def goto(self, location: str) -> NavigatorState:
        """
        Navigate to absolute or relative location.

        Args:
            location: Target location (path, URL, etc.)

        Returns:
            NavigatorState with success status and optional snapshot
        """
        pass

    @abstractmethod
    async def current(self) -> str:
        """
        Return current location.

        Returns:
            Current location as string (path, URL, etc.)
        """
        pass

    @abstractmethod
    async def back(self) -> NavigatorState:
        """
        Go to previous location in history.

        Returns:
            NavigatorState with new location
        """
        pass

    @abstractmethod
    async def forward(self) -> NavigatorState:
        """
        Go to next location (if went back).

        Returns:
            NavigatorState with new location
        """
        pass

    @abstractmethod
    async def list(self) -> List[Dict[str, Any]]:
        """
        List contents at current location.

        Returns:
            List of entries with domain-specific metadata
            - Filesystem: name, type, size, modified
            - Browser: text, href
        """
        pass

    @abstractmethod
    async def read(self, target: Optional[str] = None) -> str:
        """
        Read content at target (or current location).

        Args:
            target: Optional relative target (filename, CSS selector)

        Returns:
            Content as string
        """
        pass

    @abstractmethod
    async def snapshot(self) -> str:
        """
        Capture current state as base64.

        Returns:
            base64-encoded snapshot (PNG for browser, JSON for filesystem)
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Release resources (close browser, etc.)."""
        pass

    def _add_history(self, action: str, location: str) -> None:
        """
        Add entry to navigation history.

        Truncates forward history if navigating after going back.
        """
        # Truncate forward history
        self.history = self.history[: self.history_index + 1]
        self.history.append(
            HistoryEntry(
                location=location,
                timestamp=datetime.utcnow(),
                action=action,
            )
        )
        self.history_index = len(self.history) - 1

    def get_history(self) -> Dict[str, Any]:
        """
        Get navigation history summary.

        Returns:
            Dict with entries list and current index
        """
        return {
            "entries": [entry.model_dump() for entry in self.history],
            "current_index": self.history_index,
        }
