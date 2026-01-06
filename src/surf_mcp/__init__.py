"""
Surf MCP Server.

MCP server for visual browser automation via Fara.
"""

__version__ = "0.5.0"

from .session_manager import SessionManager
from .drivers.base import NavigatorDriver, NavigatorState, HistoryEntry
from .drivers.browser import BrowserDriver

__all__ = [
    "SessionManager",
    "NavigatorDriver",
    "NavigatorState",
    "HistoryEntry",
    "BrowserDriver",
]
