"""
Content MCP commands.

Content operations for browser automation:
- list: List links on current page
- read: Read page content
- snapshot: Capture screenshot
"""

from typing import Any, Dict, List

from mcp.types import Tool

from ..session_manager import SessionManager


def get_tools() -> List[Tool]:
    """Return tool definitions for content commands."""
    return [
        Tool(
            name="list",
            description="List links on current page",
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
            name="read",
            description="Read page text content",
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
                    "target": {
                        "type": "string",
                        "description": "Optional CSS selector to read specific element",
                    },
                },
                "required": ["session_id", "driver"],
            },
        ),
        Tool(
            name="snapshot",
            description="Capture screenshot as base64 PNG",
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


async def list_contents(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """List contents at current location."""
    driver, error = await _get_driver(manager, args)
    if error:
        return error

    entries = await driver.list()
    return {"entries": entries}


async def read(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Read content."""
    driver, error = await _get_driver(manager, args)
    if error:
        return error

    target = args.get("target")

    try:
        content = await driver.read(target)
        return {"content": content}
    except Exception as e:
        return {"error": str(e)}


async def snapshot(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Capture snapshot."""
    driver, error = await _get_driver(manager, args)
    if error:
        return error

    snapshot_data = await driver.snapshot()

    return {
        "snapshot": snapshot_data,
        "format": "image/png",
    }
