"""
Navigator MCP Server - Main entrypoint.

Unified MCP server for persistent navigation across filesystem and browser domains.
Provides JSON-RPC over stdio interface for MCP clients.

Usage:
    navigator-mcp  # Starts server on stdio
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .session_manager import SessionManager
from .commands import session, navigation, content, filesystem, browser

# Configure logging
logging.basicConfig(
    level=os.environ.get("NAVIGATOR_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize components
session_manager = SessionManager()

# Create MCP server
server = Server("navigator-mcp")


# =============================================================================
# Tool Registration
# =============================================================================

@server.list_tools()
async def list_tools() -> List[Tool]:
    """List all available tools."""
    tools = []

    # Session lifecycle tools
    tools.extend(session.get_tools())

    # Universal navigation tools
    tools.extend(navigation.get_tools())

    # Content tools (read, write, list, snapshot)
    tools.extend(content.get_tools())

    # Filesystem-specific tools
    tools.extend(filesystem.get_tools())

    # Browser-specific tools
    tools.extend(browser.get_tools())

    return tools


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """
    Handle tool calls.

    Routes to appropriate command handler based on tool name.
    """
    logger.debug(f"Tool call: {name} with args: {arguments}")

    try:
        # Session lifecycle
        if name == "session_create":
            result = await session.create(session_manager, arguments)
        elif name == "session_destroy":
            result = await session.destroy(session_manager, arguments)
        elif name == "session_list":
            result = await session.list_sessions(session_manager)

        # Universal navigation
        elif name == "goto":
            result = await navigation.goto(session_manager, arguments)
        elif name == "current":
            result = await navigation.current(session_manager, arguments)
        elif name == "back":
            result = await navigation.back(session_manager, arguments)
        elif name == "forward":
            result = await navigation.forward(session_manager, arguments)
        elif name == "history":
            result = await navigation.history(session_manager, arguments)

        # Content operations
        elif name == "list":
            result = await content.list_contents(session_manager, arguments)
        elif name == "read":
            result = await content.read(session_manager, arguments)
        elif name == "snapshot":
            result = await content.snapshot(session_manager, arguments)

        # Filesystem-specific
        elif name == "write":
            result = await filesystem.write(session_manager, arguments)
        elif name == "delete":
            result = await filesystem.delete(session_manager, arguments)
        elif name == "copy":
            result = await filesystem.copy(session_manager, arguments)
        elif name == "move":
            result = await filesystem.move(session_manager, arguments)
        elif name == "find":
            result = await filesystem.find(session_manager, arguments)

        # Browser-specific
        elif name == "locate":
            result = await browser.locate(session_manager, arguments)
        elif name == "click":
            result = await browser.click(session_manager, arguments)
        elif name == "type":
            result = await browser.type_text(session_manager, arguments)
        elif name == "scroll":
            result = await browser.scroll(session_manager, arguments)
        elif name == "wait":
            result = await browser.wait(session_manager, arguments)

        # ADR-005: Direct Fara Execution
        elif name == "act":
            result = await browser.act(session_manager, arguments)
        elif name == "act_autonomous":
            result = await browser.act_autonomous(session_manager, arguments)

        else:
            result = {"error": f"Unknown tool: {name}"}

        # Format result as TextContent
        import json
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        logger.error(f"Tool {name} failed: {e}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


# =============================================================================
# Main Entry Point
# =============================================================================

async def run_server():
    """Run the MCP server."""
    logger.info("Starting Navigator MCP server...")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await session_manager.cleanup_all()
        logger.info("Navigator MCP server shutdown complete")


def main():
    """Main entry point."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
