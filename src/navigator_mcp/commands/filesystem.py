"""
Filesystem-specific MCP commands.

Operations specific to the filesystem driver:
- write: Write content to file
- delete: Delete file or directory
- copy: Copy file or directory
- move: Move/rename file or directory
- find: Search for files by pattern
"""

from typing import Any, Dict, List

from mcp.types import Tool

from ..session_manager import SessionManager
from ..drivers.filesystem import FileSystemDriver


def get_tools() -> List[Tool]:
    """Return tool definitions for filesystem commands."""
    return [
        Tool(
            name="write",
            description="Write content to a file (filesystem driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be filesystem)",
                    },
                    "target": {
                        "type": "string",
                        "description": "Target file path (relative to cwd)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write",
                    },
                },
                "required": ["session_id", "driver", "target", "content"],
            },
        ),
        Tool(
            name="delete",
            description="Delete a file or directory (filesystem driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be filesystem)",
                    },
                    "target": {
                        "type": "string",
                        "description": "Target path to delete",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Delete directories recursively",
                        "default": False,
                    },
                },
                "required": ["session_id", "driver", "target"],
            },
        ),
        Tool(
            name="copy",
            description="Copy a file or directory (filesystem driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be filesystem)",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source path",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination path",
                    },
                },
                "required": ["session_id", "driver", "source", "destination"],
            },
        ),
        Tool(
            name="move",
            description="Move/rename a file or directory (filesystem driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be filesystem)",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source path",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination path",
                    },
                },
                "required": ["session_id", "driver", "source", "destination"],
            },
        ),
        Tool(
            name="find",
            description="Find files matching a pattern (filesystem driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be filesystem)",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '*.py', '**/*.txt')",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Search recursively",
                        "default": True,
                    },
                },
                "required": ["session_id", "driver", "pattern"],
            },
        ),
    ]


async def _get_fs_driver(manager: SessionManager, args: Dict[str, Any]):
    """Helper to get filesystem driver from session."""
    session_id = args.get("session_id")
    driver_alias = args.get("driver")

    session = await manager.get_session(session_id)
    if not session:
        return None, {"error": f"Session not found: {session_id}"}

    driver = session.get_driver(driver_alias)
    if not driver:
        return None, {"error": f"Driver not found: {driver_alias}"}

    if not isinstance(driver, FileSystemDriver):
        return None, {"error": f"Driver '{driver_alias}' is not a filesystem driver"}

    return driver, None


async def write(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Write content to file."""
    driver, error = await _get_fs_driver(manager, args)
    if error:
        return error

    target = args.get("target")
    content = args.get("content")

    if not target:
        return {"error": "target required"}
    if content is None:
        return {"error": "content required"}

    result = await driver.write(target, content)
    return result.model_dump()


async def delete(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Delete file or directory."""
    driver, error = await _get_fs_driver(manager, args)
    if error:
        return error

    target = args.get("target")
    recursive = args.get("recursive", False)

    if not target:
        return {"error": "target required"}

    result = await driver.delete(target, recursive=recursive)
    return result.model_dump()


async def copy(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Copy file or directory."""
    driver, error = await _get_fs_driver(manager, args)
    if error:
        return error

    source = args.get("source")
    destination = args.get("destination")

    if not source:
        return {"error": "source required"}
    if not destination:
        return {"error": "destination required"}

    result = await driver.copy(source, destination)
    return result.model_dump()


async def move(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Move/rename file or directory."""
    driver, error = await _get_fs_driver(manager, args)
    if error:
        return error

    source = args.get("source")
    destination = args.get("destination")

    if not source:
        return {"error": "source required"}
    if not destination:
        return {"error": "destination required"}

    result = await driver.move(source, destination)
    return result.model_dump()


async def find(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Find files by pattern."""
    driver, error = await _get_fs_driver(manager, args)
    if error:
        return error

    pattern = args.get("pattern")
    recursive = args.get("recursive", True)

    if not pattern:
        return {"error": "pattern required"}

    matches = await driver.find(pattern, recursive=recursive)
    return {"matches": matches}
