"""
Universal navigation MCP commands.

These work with any driver type:
- goto: Navigate to location
- current: Get current location
- back: Go back in history
- forward: Go forward in history
- history: Get navigation history
"""

from typing import Any, Dict, List

from mcp.types import Tool

from ..session_manager import SessionManager


def get_tools() -> List[Tool]:
    """Return tool definitions for navigation commands."""
    return [
        Tool(
            name="goto",
            description="Navigate to a location (path for filesystem, URL for browser)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (e.g., 'fs', 'web')",
                    },
                    "location": {
                        "type": "string",
                        "description": "Target location (path or URL)",
                    },
                },
                "required": ["session_id", "driver", "location"],
            },
        ),
        Tool(
            name="current",
            description="Get current location for a driver",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias",
                    },
                },
                "required": ["session_id", "driver"],
            },
        ),
        Tool(
            name="back",
            description="Navigate back in history",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias",
                    },
                },
                "required": ["session_id", "driver"],
            },
        ),
        Tool(
            name="forward",
            description="Navigate forward in history",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias",
                    },
                },
                "required": ["session_id", "driver"],
            },
        ),
        Tool(
            name="history",
            description="Get navigation history for a driver",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias",
                    },
                },
                "required": ["session_id", "driver"],
            },
        ),
    ]


async def _get_driver(manager: SessionManager, args: Dict[str, Any]):
    """Helper to get driver from session."""
    session_id = args.get("session_id")
    driver_alias = args.get("driver")

    session = await manager.get_session(session_id)
    if not session:
        return None, {"error": f"Session not found: {session_id}"}

    driver = session.get_driver(driver_alias)
    if not driver:
        return None, {"error": f"Driver not found: {driver_alias}"}

    return driver, None


async def goto(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Navigate to location."""
    driver, error = await _get_driver(manager, args)
    if error:
        return error

    location = args.get("location")
    if not location:
        return {"error": "location required"}

    result = await driver.goto(location)
    return result.model_dump()


async def current(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Get current location."""
    driver, error = await _get_driver(manager, args)
    if error:
        return error

    location = await driver.current()
    return {"location": location}


async def back(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Navigate back."""
    driver, error = await _get_driver(manager, args)
    if error:
        return error

    result = await driver.back()
    return result.model_dump()


async def forward(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Navigate forward."""
    driver, error = await _get_driver(manager, args)
    if error:
        return error

    result = await driver.forward()
    return result.model_dump()


async def history(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Get navigation history."""
    driver, error = await _get_driver(manager, args)
    if error:
        return error

    return driver.get_history()
