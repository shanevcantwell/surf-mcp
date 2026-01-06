"""
MCP Command modules.

Each module provides:
- get_tools(): List of Tool definitions for registration
- Command handler functions
"""

from . import session, navigation, content, browser

__all__ = ["session", "navigation", "content", "browser"]
