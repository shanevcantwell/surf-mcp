"""
PlaywrightExecutor - Execute Fara tool_calls directly against Playwright.

Per ADR-005: This is a thin translation layer. Fara decides what action to take,
we just execute it against the browser.

Supported actions:
- left_click, click, double_click: Click at coordinates
- type: Type text (optionally click first)
- scroll: Scroll page up/down
- key: Press keyboard keys
- visit_url: Navigate to URL (with domain filter check)
- history_back: Go back in browser history
- terminate: Task complete signal (no-op)
- wait: Wait for page to load
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from ..llm.base import ExecutionResult, FaraToolCall, UnsupportedActionError

if TYPE_CHECKING:
    from playwright.async_api import Page
    from ..security.domain_filter import DomainFilter

logger = logging.getLogger(__name__)

# Actions that this executor supports
SUPPORTED_ACTIONS = frozenset([
    "left_click",
    "click",
    "double_click",
    "type",
    "scroll",
    "key",
    "visit_url",
    "terminate",
    "wait",
    "history_back",
])


class BlockedDomainError(Exception):
    """Raised when attempting to navigate to a blocked domain."""

    pass


class PlaywrightExecutor:
    """
    Execute Fara tool_calls directly against Playwright.

    This is the execution layer in the Goal → Fara → Action → Result flow.
    It translates FaraToolCall actions into Playwright API calls.

    Error handling: Fails fast with UnsupportedActionError for unknown actions.
    This surfaces gaps in our action support rather than silently failing.

    Security: visit_url actions are checked against the domain filter if provided.
    """

    def __init__(
        self,
        default_scroll_pixels: int = 500,
        type_delay_ms: int = 50,
        domain_filter: Optional[DomainFilter] = None,
    ):
        """
        Initialize executor.

        Args:
            default_scroll_pixels: Default scroll amount if not specified in tool_call
            type_delay_ms: Delay between keystrokes when typing
            domain_filter: Optional domain filter for URL navigation security
        """
        self.default_scroll_pixels = default_scroll_pixels
        self.type_delay_ms = type_delay_ms
        self._domain_filter = domain_filter

    async def execute(
        self, tool_call: FaraToolCall, page: "Page"
    ) -> ExecutionResult:
        """
        Execute a single Fara tool_call against a Playwright page.

        Args:
            tool_call: The FaraToolCall to execute
            page: Playwright Page instance

        Returns:
            ExecutionResult with success status

        Raises:
            UnsupportedActionError: If the action is not supported
        """
        action = tool_call.action.lower()

        logger.debug(
            f"Executing action '{action}' "
            f"coord={tool_call.coordinate} "
            f"text={tool_call.text[:20] + '...' if tool_call.text and len(tool_call.text) > 20 else tool_call.text}"
        )

        try:
            match action:
                case "left_click" | "click":
                    if not tool_call.coordinate:
                        return ExecutionResult(
                            success=False,
                            action=action,
                            error="Click action requires coordinates",
                        )
                    x, y = tool_call.coordinate[0], tool_call.coordinate[1]

                    # Track pages before click to detect new tabs
                    context = page.context
                    pages_before = len(context.pages)

                    # Execute click
                    await page.mouse.click(x, y)

                    # Wait briefly for any popup/new tab
                    try:
                        await page.wait_for_timeout(500)
                    except Exception:
                        pass

                    # Check if a new tab opened (target="_blank" links)
                    if len(context.pages) > pages_before:
                        new_page = context.pages[-1]
                        logger.info(f"Click opened new tab: {new_page.url}")
                        # Wait for new page to load
                        try:
                            await new_page.wait_for_load_state("domcontentloaded", timeout=5000)
                        except Exception:
                            pass
                        # Return new_page for auto-switch by BrowserDriver
                        return ExecutionResult(success=True, action=action, new_page=new_page)
                    else:
                        # Wait for navigation on current page
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=3000)
                        except Exception:
                            pass  # No navigation is fine

                case "double_click":
                    if not tool_call.coordinate:
                        return ExecutionResult(
                            success=False,
                            action=action,
                            error="Double-click action requires coordinates",
                        )
                    await page.mouse.dblclick(
                        tool_call.coordinate[0], tool_call.coordinate[1]
                    )

                case "type":
                    if not tool_call.text:
                        return ExecutionResult(
                            success=False,
                            action=action,
                            error="Type action requires text",
                        )
                    # Click first if coordinates provided
                    if tool_call.coordinate:
                        await page.mouse.click(
                            tool_call.coordinate[0], tool_call.coordinate[1]
                        )
                    # Clear existing text if requested (Fara often sends this for form fields)
                    if tool_call.delete_existing_text:
                        await page.keyboard.press("Control+a")
                        await page.keyboard.press("Delete")
                    await page.keyboard.type(tool_call.text, delay=self.type_delay_ms)
                    # Press Enter after typing if requested
                    if tool_call.press_enter:
                        await page.keyboard.press("Enter")

                case "scroll":
                    if tool_call.pixels is not None and tool_call.direction is None:
                        # Fara convention: negative = down, positive = up
                        # Playwright convention: positive = down, negative = up
                        # Classic Microsoft...
                        delta = -tool_call.pixels
                    else:
                        pixels = abs(tool_call.pixels) if tool_call.pixels else self.default_scroll_pixels
                        direction = (tool_call.direction or "down").lower()
                        delta = pixels if direction == "down" else -pixels
                    await page.mouse.wheel(0, delta)

                case "key":
                    if not tool_call.keys:
                        return ExecutionResult(
                            success=False,
                            action=action,
                            error="Key action requires keys list",
                        )
                    for key in tool_call.keys:
                        await page.keyboard.press(key)

                case "visit_url":
                    if not tool_call.url:
                        return ExecutionResult(
                            success=False,
                            action=action,
                            error="visit_url action requires url",
                        )
                    # Security: Check domain filter before navigation
                    if self._domain_filter:
                        allowed, reason = self._domain_filter.check(tool_call.url)
                        if not allowed:
                            raise BlockedDomainError(reason)
                    await page.goto(tool_call.url, wait_until="networkidle")

                case "terminate":
                    # Task complete signal - no action needed
                    logger.info("Fara signaled task complete (terminate)")

                case "wait":
                    # Simple wait action - wait for network idle
                    await page.wait_for_load_state("networkidle", timeout=5000)

                case "history_back":
                    # Navigate back in browser history
                    await page.go_back(wait_until="domcontentloaded", timeout=10000)

                case _:
                    # Fail fast for unknown actions
                    raise UnsupportedActionError(
                        f"Fara returned unsupported action '{tool_call.action}'. "
                        f"Supported: {', '.join(sorted(SUPPORTED_ACTIONS))}"
                    )

            logger.debug(f"Action '{action}' completed successfully")
            return ExecutionResult(success=True, action=action)

        except (UnsupportedActionError, BlockedDomainError):
            raise  # Re-raise security/support errors to fail fast

        except Exception as e:
            logger.error(f"Action '{action}' failed: {e}")
            return ExecutionResult(success=False, action=action, error=str(e))

    def supports_action(self, action: str) -> bool:
        """Check if an action is supported by this executor."""
        return action.lower() in SUPPORTED_ACTIONS
