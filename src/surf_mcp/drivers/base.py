"""
Browser driver base class.

Provides consistent interface for browser navigation and content operations
with optional visual grounding via Fara.

All drivers implement:
- goto(url) - Navigate to URL
- current() - Get current URL
- back() / forward() - Navigate history
- list() - List links on page
- read(target) - Read page content
- snapshot() - Capture screenshot
- cleanup() - Release resources
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

from pydantic import BaseModel, Field


class NavigatorState(BaseModel):
    """Result of navigation operations (goto, back, forward)."""

    location: str = Field(..., description="Current URL")
    success: bool = Field(..., description="Whether the operation succeeded")
    snapshot: Optional[str] = Field(
        None, description="base64-encoded PNG screenshot"
    )
    error: Optional[str] = Field(None, description="Error message if failed")


class HistoryEntry(BaseModel):
    """Single entry in navigation history."""

    location: str = Field(..., description="URL that was navigated to")
    timestamp: datetime = Field(
        default_factory=_utc_now, description="When this navigation occurred"
    )
    action: str = Field(..., description="Action type: goto, back, forward")


class NavigatorDriver(ABC):
    """
    Abstract base class for browser drivers.

    Drivers maintain:
    - Current URL
    - Navigation history with forward/back capability
    - Optional visual grounding via Fara for element interaction
    """

    driver_type: str = "browser"
    history: List[HistoryEntry]
    history_index: int

    @abstractmethod
    async def goto(self, location: str) -> NavigatorState:
        """
        Navigate to URL.

        Args:
            location: Target URL

        Returns:
            NavigatorState with success status and screenshot
        """
        pass

    @abstractmethod
    async def current(self) -> str:
        """
        Return current URL.

        Returns:
            Current URL as string
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
        List links on current page.

        Returns:
            List of link entries with text and href
        """
        pass

    @abstractmethod
    async def read(self, target: Optional[str] = None) -> str:
        """
        Read page content.

        Args:
            target: Optional CSS selector to read specific element

        Returns:
            Page text content
        """
        pass

    @abstractmethod
    async def snapshot(self) -> str:
        """
        Capture screenshot as base64 PNG.

        Returns:
            base64-encoded PNG screenshot
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Release browser resources."""
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
                timestamp=_utc_now(),
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
