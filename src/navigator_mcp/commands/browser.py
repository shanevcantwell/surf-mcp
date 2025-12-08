"""
Browser-specific MCP commands.

Operations specific to the browser driver (visual grounding):
- locate: Find element by description
- click: Click element by description
- type: Type into element by description
- scroll: Scroll page
- wait: Wait for element or delay
"""

from typing import Any, Dict, List

from mcp.types import Tool

from ..session_manager import SessionManager
from ..drivers.browser import BrowserDriver


def get_tools() -> List[Tool]:
    """Return tool definitions for browser commands."""
    return [
        Tool(
            name="locate",
            description="Locate UI element by natural language description (browser driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be browser)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Natural language description of element (e.g., 'the blue Submit button')",
                    },
                },
                "required": ["session_id", "driver", "description"],
            },
        ),
        Tool(
            name="click",
            description="Click UI element by description (browser driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be browser)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Natural language description of element to click",
                    },
                },
                "required": ["session_id", "driver", "description"],
            },
        ),
        Tool(
            name="type",
            description="Type text into UI element by description (browser driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be browser)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Natural language description of input element",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type",
                    },
                    "clear_first": {
                        "type": "boolean",
                        "description": "Clear existing content before typing",
                        "default": True,
                    },
                },
                "required": ["session_id", "driver", "description", "text"],
            },
        ),
        Tool(
            name="scroll",
            description="Scroll page (browser driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be browser)",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Scroll direction",
                        "default": "down",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Pixels to scroll (default: viewport height)",
                    },
                },
                "required": ["session_id", "driver"],
            },
        ),
        Tool(
            name="wait",
            description="Wait for element or delay (browser driver only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID",
                    },
                    "driver": {
                        "type": "string",
                        "description": "Driver alias (must be browser)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Element to wait for (polls until visible)",
                    },
                    "seconds": {
                        "type": "number",
                        "description": "Delay in seconds",
                    },
                },
                "required": ["session_id", "driver"],
            },
        ),
    ]


async def _get_browser_driver(manager: SessionManager, args: Dict[str, Any]):
    """Helper to get browser driver from session."""
    session_id = args.get("session_id")
    driver_alias = args.get("driver")

    session = await manager.get_session(session_id)
    if not session:
        return None, {"error": f"Session not found: {session_id}"}

    driver = session.get_driver(driver_alias)
    if not driver:
        return None, {"error": f"Driver not found: {driver_alias}"}

    if not isinstance(driver, BrowserDriver):
        return None, {"error": f"Driver '{driver_alias}' is not a browser driver"}

    return driver, None


async def locate(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Locate element by description."""
    driver, error = await _get_browser_driver(manager, args)
    if error:
        return error

    description = args.get("description")
    if not description:
        return {"error": "description required"}

    result = await driver.locate(description)
    return result


async def click(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Click element by description."""
    driver, error = await _get_browser_driver(manager, args)
    if error:
        return error

    description = args.get("description")
    if not description:
        return {"error": "description required"}

    result = await driver.click(description)
    return result.model_dump()


async def type_text(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Type into element by description."""
    driver, error = await _get_browser_driver(manager, args)
    if error:
        return error

    description = args.get("description")
    text = args.get("text")
    clear_first = args.get("clear_first", True)

    if not description:
        return {"error": "description required"}
    if not text:
        return {"error": "text required"}

    result = await driver.type(description, text, clear_first=clear_first)
    return result.model_dump()


async def scroll(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Scroll page."""
    driver, error = await _get_browser_driver(manager, args)
    if error:
        return error

    direction = args.get("direction", "down")
    amount = args.get("amount")

    result = await driver.scroll(direction=direction, amount=amount)
    return result.model_dump()


async def wait(manager: SessionManager, args: Dict[str, Any]) -> Dict[str, Any]:
    """Wait for element or delay."""
    driver, error = await _get_browser_driver(manager, args)
    if error:
        return error

    description = args.get("description")
    seconds = args.get("seconds")

    result = await driver.wait(description=description, seconds=seconds)
    return result.model_dump()
