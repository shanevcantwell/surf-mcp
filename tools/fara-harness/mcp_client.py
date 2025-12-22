"""
MCP Client wrapper for Fara Test Harness.

Uses the official MCP SDK to communicate with surf-mcp server
via subprocess stdio. Supports both Docker and local installation.
"""

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Environment variables to pass through to Docker container
PASSTHROUGH_ENV_VARS = [
    "LMSTUDIO_SERVERS",
    "FARA_MODEL_IDS",
    "FARA_MAX_FAILURES",
    "FARA_PROBE_TIMEOUT",
    "FARA_MIN_CONFIDENCE",
    "FARA_MAX_AGENT_STEPS",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "GOOGLE_API_KEY",
    "SURF_LLM_PROVIDER",
    "SURF_LLM_MODEL",
    "SURF_BROWSER_HEADLESS",
    "SURF_LOG_LEVEL",
]


def build_docker_args(image: str = "surf-mcp") -> List[str]:
    """Build docker run arguments with environment passthrough."""
    args = ["run", "-i", "--rm"]

    # Add host.docker.internal for Linux (works by default on Mac/Windows)
    args.extend(["--add-host", "host.docker.internal:host-gateway"])

    # Pass through environment variables that are set
    for var in PASSTHROUGH_ENV_VARS:
        value = os.environ.get(var)
        if value:
            args.extend(["-e", f"{var}={value}"])

    # Always set headless mode in container
    if "SURF_BROWSER_HEADLESS" not in os.environ:
        args.extend(["-e", "SURF_BROWSER_HEADLESS=true"])

    args.append(image)
    return args


class SurfMCPClient:
    """
    Client wrapper for surf-mcp server.

    Handles subprocess lifecycle and provides typed methods for MCP tools.
    Supports Docker mode (default) or local installation.
    """

    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack: Optional[AsyncExitStack] = None
        self._connected = False

    async def connect(
        self,
        use_docker: bool = True,
        docker_image: str = "surf-mcp",
        local_command: str = "surf-mcp",
    ) -> None:
        """
        Connect to surf-mcp server.

        Args:
            use_docker: If True, spawn via 'docker run' (default: True)
            docker_image: Docker image name (default: surf-mcp)
            local_command: Command for local install (default: surf-mcp)
        """
        if self._connected:
            return

        self.exit_stack = AsyncExitStack()

        if use_docker:
            server_params = StdioServerParameters(
                command="docker",
                args=build_docker_args(docker_image),
                env=None,
            )
            print(f"Connecting via Docker: docker {' '.join(build_docker_args(docker_image))}")
        else:
            server_params = StdioServerParameters(
                command=local_command,
                args=[],
                env=None,
            )
            print(f"Connecting via local command: {local_command}")

        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        stdio, write = stdio_transport

        self.session = await self.exit_stack.enter_async_context(
            ClientSession(stdio, write)
        )

        await self.session.initialize()
        self._connected = True

        # List available tools for debugging
        response = await self.session.list_tools()
        print(f"Connected to surf-mcp with tools: {[t.name for t in response.tools]}")

    async def disconnect(self) -> None:
        """Disconnect from server."""
        if self.exit_stack:
            await self.exit_stack.aclose()
        self._connected = False
        self.session = None

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool and return parsed result.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Parsed JSON response
        """
        if not self.session:
            raise RuntimeError("Not connected. Call connect() first.")

        result = await self.session.call_tool(name, arguments)

        # Parse the text content as JSON
        if result.content and len(result.content) > 0:
            text = result.content[0].text
            return json.loads(text)

        return {}

    # ==================== Session Tools ====================

    async def session_create(
        self,
        headless: bool = False,
        viewport: tuple = (1920, 1080),
        storage_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a browser session.

        Args:
            headless: Run browser headless (default False for harness)
            viewport: Browser viewport size
            storage_state: Playwright storage state to restore

        Returns:
            Session info with session_id
        """
        driver_config: Dict[str, Any] = {
            "type": "browser",
            "headless": headless,
            "viewport": list(viewport),
        }

        if storage_state:
            driver_config["storage_state"] = storage_state

        return await self.call_tool("session_create", {
            "drivers": {"web": driver_config}
        })

    async def session_destroy(self, session_id: str) -> Dict[str, Any]:
        """
        Destroy a session and get storage_state.

        Returns:
            Summary including storage_state for browser driver
        """
        return await self.call_tool("session_destroy", {
            "session_id": session_id
        })

    async def session_list(self) -> Dict[str, Any]:
        """List active sessions."""
        return await self.call_tool("session_list", {})

    # ==================== Navigation Tools ====================

    async def goto(self, session_id: str, url: str) -> Dict[str, Any]:
        """Navigate to URL."""
        return await self.call_tool("goto", {
            "session_id": session_id,
            "driver": "web",
            "location": url,
        })

    async def current(self, session_id: str) -> Dict[str, Any]:
        """Get current URL."""
        return await self.call_tool("current", {
            "session_id": session_id,
            "driver": "web",
        })

    async def snapshot(self, session_id: str) -> Dict[str, Any]:
        """Take screenshot."""
        return await self.call_tool("snapshot", {
            "session_id": session_id,
            "driver": "web",
        })

    # ==================== Visual Grounding Tools ====================

    async def locate(self, session_id: str, description: str) -> Dict[str, Any]:
        """
        Locate element by natural language description.

        Returns:
            {found, x, y, confidence, reasoning}
        """
        return await self.call_tool("locate", {
            "session_id": session_id,
            "driver": "web",
            "description": description,
        })

    async def click(self, session_id: str, description: str) -> Dict[str, Any]:
        """Click element by description."""
        return await self.call_tool("click", {
            "session_id": session_id,
            "driver": "web",
            "description": description,
        })

    async def type_text(
        self,
        session_id: str,
        description: str,
        text: str,
        clear_first: bool = True,
    ) -> Dict[str, Any]:
        """Type text into element by description."""
        return await self.call_tool("type", {
            "session_id": session_id,
            "driver": "web",
            "description": description,
            "text": text,
            "clear_first": clear_first,
        })

    async def scroll(
        self,
        session_id: str,
        direction: str = "down",
        amount: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Scroll page."""
        args: Dict[str, Any] = {
            "session_id": session_id,
            "driver": "web",
            "direction": direction,
        }
        if amount:
            args["amount"] = amount
        return await self.call_tool("scroll", args)

    # ==================== ADR-005: Direct Fara Execution ====================

    async def act(self, session_id: str, goal: str) -> Dict[str, Any]:
        """
        Execute goal using direct Fara execution.

        Per ADR-005: Fara decides what action to take, returns full tool_call.

        Returns:
            Result with fara_action, coordinate, confidence, reasoning
        """
        return await self.call_tool("act", {
            "session_id": session_id,
            "driver": "web",
            "goal": goal,
        })

    async def act_autonomous(self, session_id: str, goal: str) -> Dict[str, Any]:
        """
        Execute goal autonomously with multi-step Fara loop.

        Returns:
            {success, step_count, steps[], final_screenshot, reason}
        """
        return await self.call_tool("act_autonomous", {
            "session_id": session_id,
            "driver": "web",
            "goal": goal,
        })


class SyncSurfClient:
    """
    Synchronous wrapper for Streamlit integration.

    Uses nest_asyncio to allow running async code even when an event loop
    is already running (as is the case with Streamlit).
    """

    def __init__(self):
        self._client = SurfMCPClient()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._setup_loop()

    def _setup_loop(self) -> None:
        """Setup event loop with nest_asyncio for reentrant execution."""
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            pass  # Will fail later if needed

        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    def _run(self, coro):
        """Run async coroutine synchronously."""
        if self._loop is None:
            self._setup_loop()
        return self._loop.run_until_complete(coro)

    def connect(
        self,
        use_docker: bool = True,
        docker_image: str = "surf-mcp",
        local_command: str = "surf-mcp",
    ) -> None:
        self._run(self._client.connect(use_docker, docker_image, local_command))

    def disconnect(self) -> None:
        self._run(self._client.disconnect())

    def session_create(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.session_create(**kwargs))

    def session_destroy(self, session_id: str) -> Dict[str, Any]:
        return self._run(self._client.session_destroy(session_id))

    def goto(self, session_id: str, url: str) -> Dict[str, Any]:
        return self._run(self._client.goto(session_id, url))

    def snapshot(self, session_id: str) -> Dict[str, Any]:
        return self._run(self._client.snapshot(session_id))

    def locate(self, session_id: str, description: str) -> Dict[str, Any]:
        return self._run(self._client.locate(session_id, description))

    def click(self, session_id: str, description: str) -> Dict[str, Any]:
        return self._run(self._client.click(session_id, description))

    def type_text(self, session_id: str, description: str, text: str) -> Dict[str, Any]:
        return self._run(self._client.type_text(session_id, description, text))

    def scroll(self, session_id: str, direction: str = "down") -> Dict[str, Any]:
        return self._run(self._client.scroll(session_id, direction))

    # ADR-005: Direct Fara Execution

    def act(self, session_id: str, goal: str) -> Dict[str, Any]:
        return self._run(self._client.act(session_id, goal))

    def act_autonomous(self, session_id: str, goal: str) -> Dict[str, Any]:
        return self._run(self._client.act_autonomous(session_id, goal))
