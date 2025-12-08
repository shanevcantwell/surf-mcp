"""
Navigator MCP Server.

Unified MCP server for persistent navigation across filesystem and browser domains.
"""

__version__ = "0.1.0"

from .session_manager import SessionManager
from .drivers.base import NavigatorDriver, NavigatorState, HistoryEntry
from .drivers.filesystem import FileSystemDriver
from .drivers.browser import BrowserDriver

__all__ = [
    "SessionManager",
    "NavigatorDriver",
    "NavigatorState",
    "HistoryEntry",
    "FileSystemDriver",
    "BrowserDriver",
]
