"""
Session lifecycle MCP commands.

- session_create: Create session with one or more drivers
- session_destroy: Cleanup session and all drivers
- session_list: List active sessions
"""

from typing import Any, Dict, List

from mcp.types import Tool

from ..session_manager import SessionManager


def get_tools() -> List[Tool]:
    """Return tool definitions for session commands."""
    return [
        Tool(
            name="session_create",
            description="Create a new navigator session with one or more drivers",
            inputSchema={
                "type": "object",
                "properties": {
                    "drivers": {
                        "type": "object",
                        "description": "Driver configurations keyed by alias",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["filesystem", "browser"],
                                    "description": "Driver type",
                                },
                                "root": {
                                    "type": "string",
                                    "description": "Root directory (filesystem only)",
                                },
                                "sandbox": {
                                    "type": "boolean",
                                    "description": "Enforce sandbox boundary (filesystem only)",
                                    "default": True,
                                },
                                "headless": {
                                    "type": "boolean",
                                    "description": "Run headless (browser only)",
                                    "default": True,
                                },
                                "viewport": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "description": "Viewport [width, height] (browser only)",
                                },
                                "storage_state": {
                                    "type": "object",
                                    "description": "Playwright storage state to restore (cookies, localStorage) (browser only)",
                                },
                            },
                            "required": ["type"],
                        },
                    },
                },
                "required": ["drivers"],
            },
        ),
        Tool(
            name="session_destroy",
            description="Destroy a session and cleanup all its drivers",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to destroy",
                    },
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="session_list",
            description="List all active sessions",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


async def create(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new session."""
    drivers_config = args.get("drivers", {})

    if not drivers_config:
        return {"error": "At least one driver configuration required"}

    try:
        session = await manager.create_session(drivers_config)
        return {
            "session_id": session.session_id,
            "drivers": list(session.drivers.keys()),
            "created_at": session.created_at.isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


async def destroy(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Destroy a session."""
    session_id = args.get("session_id")

    if not session_id:
        return {"error": "session_id required"}

    summary = await manager.destroy_session(session_id)

    if summary is None:
        return {"error": f"Session not found: {session_id}"}

    return {
        "success": True,
        "session_id": session_id,
        "summary": summary,
    }


async def list_sessions(manager: SessionManager) -> Dict[str, Any]:
    """List all active sessions."""
    sessions = await manager.list_sessions()
    return {"sessions": sessions}
