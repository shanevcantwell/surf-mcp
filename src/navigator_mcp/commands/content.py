"""
Content MCP commands.

Universal content operations that work with any driver:
- list: List contents at current location
- read: Read content
- snapshot: Capture current state
"""

from typing import Any, Dict, List

from mcp.types import Tool

from ..session_manager import SessionManager


def get_tools() -> List[Tool]:
    """Return tool definitions for content commands."""
    return [
        Tool(
            name="list",
            description="List contents at current location (directory entries for filesystem, links for browser)",
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
            description="Read content (file for filesystem, page text for browser)",
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
                        "description": "Target to read (filename for filesystem, CSS selector for browser)",
                    },
                },
                "required": ["session_id", "driver"],
            },
        ),
        Tool(
            name="snapshot",
            description="Capture current state (JSON for filesystem, PNG screenshot for browser)",
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

    # Determine format based on driver type
    format_type = "application/json" if driver.driver_type == "filesystem" else "image/png"

    return {
        "snapshot": snapshot_data,
        "format": format_type,
    }
