"""
BrowserDriver - Navigate web pages with visual grounding.

Provides:
- URL-based navigation with history
- Screenshot capture
- Visual grounding for element location (via Fara/LLM)
- Click, type, scroll operations using natural language descriptions

Security Controls (ADR-001 Phase 1):
- URL Allowlist/Blocklist
- Audit Logging
- Rate Limiting
"""

import base64
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import HistoryEntry, NavigatorDriver, NavigatorState
from ..security.audit import AuditEvent, AuditLogger
from ..security.domain_filter import DomainFilter
from ..security.rate_limiter import RateLimiter

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page, Playwright
    from ..llm.base import VisualGrounder

logger = logging.getLogger(__name__)


class BrowserDriver(NavigatorDriver):
    """
    Navigate web pages with visual grounding.

    Uses Playwright for browser automation and multimodal LLMs
    (via VisualGrounder) for natural language element location.

    Security Controls:
    - URL allowlist/blocklist for domain access control
    - Audit logging for all actions
    - Rate limiting to prevent runaway automation
    """

    driver_type = "browser"

    def __init__(
        self,
        headless: bool = True,
        viewport: tuple = (1920, 1080),
        visual_grounder: Optional["VisualGrounder"] = None,
        storage_state: Optional[Dict[str, Any]] = None,
        # Security controls (ADR-001 Phase 1)
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
        max_actions_per_minute: int = 30,
    ):
        """
        Initialize browser driver.

        Args:
            headless: Run browser without visible window
            viewport: Browser viewport size (width, height)
            visual_grounder: LLM-based visual grounding implementation
            storage_state: Playwright storage state (cookies, localStorage) to restore
            allowed_domains: If set, only these domains allowed (allowlist mode)
            blocked_domains: Domains to always block (added to defaults)
            max_actions_per_minute: Rate limit for click/type/scroll actions
        """
        self.headless = headless
        self.viewport = viewport
        self.grounder = visual_grounder
        self.storage_state = storage_state
        self.max_actions_per_minute = max_actions_per_minute

        self._playwright: Optional["Playwright"] = None
        self._browser: Optional["Browser"] = None
        self._context: Optional[Any] = None  # BrowserContext for storage_state
        self._page: Optional["Page"] = None

        self.history: List[HistoryEntry] = []
        self.history_index = -1

        # Tracking for session summary
        self.screenshots: List[str] = []

        # Security controls (ADR-001 Phase 1)
        self._session_id = str(uuid.uuid4())[:8]
        self._audit_logger = AuditLogger(session_id=self._session_id)
        self._domain_filter = DomainFilter(
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        )
        self.rate_limiter = RateLimiter(max_per_minute=max_actions_per_minute)
        self._last_screenshot_b64: Optional[str] = None

    @property
    def audit_log(self) -> List[AuditEvent]:
        """Return audit log events (read-only view)."""
        return self._audit_logger.get_events()

    async def initialize(self) -> None:
        """
        Start browser (call once per session).

        Must be called before any navigation operations.
        Automatically configures proxy if HTTPS_PROXY env var is set.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "playwright package required. Install with: "
                "pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()

        try:
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
        except Exception as e:
            error_msg = str(e)
            if "Executable doesn't exist" in error_msg:
                raise RuntimeError(
                    "Playwright browser not installed. Run: playwright install chromium"
                ) from e
            raise

        # Configure context with optional proxy (for Squid integration per ADR-001)
        context_options: Dict[str, Any] = {
            "viewport": {"width": self.viewport[0], "height": self.viewport[1]}
        }

        proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        if proxy_url:
            context_options["proxy"] = {"server": proxy_url}
            logger.info(f"BrowserDriver using proxy: {proxy_url}")

        # Load storage_state if provided (cookies, localStorage)
        if self.storage_state:
            context_options["storage_state"] = self.storage_state
            logger.info("BrowserDriver loading storage_state")

        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()

        logger.info(
            f"BrowserDriver initialized: headless={self.headless}, "
            f"viewport={self.viewport}, session_id={self._session_id}"
        )

    async def goto(self, location: str) -> NavigatorState:
        """
        Navigate to URL.

        Security: Checks domain allowlist/blocklist before navigation.

        Args:
            location: URL to navigate to

        Returns:
            NavigatorState with success status and screenshot
        """
        if not self._page:
            return NavigatorState(
                location="",
                success=False,
                error="Browser not initialized. Call initialize() first.",
            )

        # Security check: Domain filter (ADR-001 Phase 1)
        allowed, reason = self._domain_filter.check(location)
        if not allowed:
            self._audit_logger.log(
                action="goto",
                details={"url": location, "reason": reason},
                outcome="blocked",
            )
            return NavigatorState(
                location=await self.current() if self._page else "",
                success=False,
                error=reason,
            )

        try:
            await self._page.goto(
                location, wait_until="networkidle", timeout=30000
            )
            self._add_history("goto", location)

            screenshot = await self.snapshot()

            # Audit log successful navigation
            self._audit_logger.log(
                action="goto",
                details={"url": location},
                outcome="success",
            )

            return NavigatorState(
                location=self._page.url,
                success=True,
                snapshot=screenshot,
            )
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            self._audit_logger.log(
                action="goto",
                details={"url": location, "error": str(e)},
                outcome="failed",
            )
            return NavigatorState(
                location=self._page.url if self._page else "",
                success=False,
                error=str(e),
            )

    async def current(self) -> str:
        """Return current URL."""
        return self._page.url if self._page else ""

    async def back(self) -> NavigatorState:
        """Go to previous page in browser history."""
        if not self._page:
            return NavigatorState(
                location="",
                success=False,
                error="Browser not initialized",
            )

        try:
            await self._page.go_back()
            self._add_history("back", self._page.url)

            return NavigatorState(
                location=self._page.url,
                success=True,
                snapshot=await self.snapshot(),
            )
        except Exception as e:
            return NavigatorState(
                location=self._page.url,
                success=False,
                error=str(e),
            )

    async def forward(self) -> NavigatorState:
        """Go to next page in browser history."""
        if not self._page:
            return NavigatorState(
                location="",
                success=False,
                error="Browser not initialized",
            )

        try:
            await self._page.go_forward()
            self._add_history("forward", self._page.url)

            return NavigatorState(
                location=self._page.url,
                success=True,
                snapshot=await self.snapshot(),
            )
        except Exception as e:
            return NavigatorState(
                location=self._page.url,
                success=False,
                error=str(e),
            )

    async def list(self) -> List[Dict[str, Any]]:
        """
        Extract links from current page.

        Returns:
            List of links with text and href
        """
        if not self._page:
            return []

        try:
            links = await self._page.eval_on_selector_all(
                "a[href]",
                "elements => elements.map(e => ({text: e.innerText.trim(), href: e.href}))",
            )
            return [link for link in links if link["text"]]
        except Exception as e:
            logger.warning(f"Error extracting links: {e}")
            return []

    async def read(self, target: Optional[str] = None) -> str:
        """
        Get page text content.

        Args:
            target: Optional CSS selector to read specific element

        Returns:
            Text content
        """
        if not self._page:
            return ""

        try:
            if target:
                element = await self._page.query_selector(target)
                return await element.inner_text() if element else ""
            return await self._page.inner_text("body")
        except Exception as e:
            logger.warning(f"Error reading content: {e}")
            return ""

    async def snapshot(self) -> str:
        """
        Take screenshot, return base64.

        Returns:
            Base64-encoded PNG screenshot
        """
        if not self._page:
            return ""

        try:
            screenshot_bytes = await self._page.screenshot()
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            self.screenshots.append(b64)
            # Track last screenshot for audit logging
            self._last_screenshot_b64 = b64
            return b64
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ""

    # ============ Visual Grounding Methods (Fara Core) ============

    async def locate(self, description: str) -> Dict[str, Any]:
        """
        Use visual grounding to find element by description.

        Args:
            description: Natural language description of the element
                e.g., "the blue Submit button"

        Returns:
            Dict with found, x, y, confidence, reasoning
        """
        if not self.grounder:
            return {"found": False, "error": "Visual grounder not configured"}

        screenshot = await self.snapshot()
        result = await self.grounder.locate(description, screenshot)
        return result.model_dump()

    async def click(self, description: str) -> NavigatorState:
        """
        Click element by visual description.

        Security: Rate limited and audit logged.

        Args:
            description: Natural language description of element to click

        Returns:
            NavigatorState with success status and post-click screenshot
        """
        if not self._page:
            return NavigatorState(
                location="",
                success=False,
                error="Browser not initialized",
            )

        # Security check: Rate limiting (ADR-001 Phase 1)
        if not self.rate_limiter.allow():
            self._audit_logger.log(
                action="click",
                details={"description": description},
                outcome="rate_limited",
            )
            return NavigatorState(
                location=self._page.url,
                success=False,
                error="Rate limit exceeded. Too many actions per minute.",
            )

        locate_result = await self.locate(description)

        if not locate_result.get("found"):
            self._audit_logger.log(
                action="click",
                details={"description": description},
                outcome="failed",
                llm_response=locate_result,
            )
            return NavigatorState(
                location=self._page.url,
                success=False,
                error=f"Element not found: {description}",
            )

        x, y = locate_result["x"], locate_result["y"]

        # Audit log with full context
        self._audit_logger.log(
            action="click",
            details={"description": description, "coordinates": (x, y)},
            outcome="success",
            screenshot_b64=self._last_screenshot_b64,
            llm_response=locate_result,
        )

        try:
            await self._page.mouse.click(x, y)
            # Wait for any navigation/updates
            await self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass  # Timeout is ok, page might not navigate

        return NavigatorState(
            location=self._page.url,
            success=True,
            snapshot=await self.snapshot(),
        )

    async def type(
        self, description: str, text: str, clear_first: bool = True
    ) -> NavigatorState:
        """
        Type into element by visual description.

        Security: Rate limited and audit logged.

        Args:
            description: Natural language description of input element
            text: Text to type
            clear_first: If True, select all before typing (clears existing)

        Returns:
            NavigatorState with success status
        """
        if not self._page:
            return NavigatorState(
                location="",
                success=False,
                error="Browser not initialized",
            )

        # Security check: Rate limiting (ADR-001 Phase 1)
        if not self.rate_limiter.allow():
            self._audit_logger.log(
                action="type",
                details={"description": description, "text_length": len(text)},
                outcome="rate_limited",
            )
            return NavigatorState(
                location=self._page.url,
                success=False,
                error="Rate limit exceeded. Too many actions per minute.",
            )

        locate_result = await self.locate(description)

        if not locate_result.get("found"):
            self._audit_logger.log(
                action="type",
                details={"description": description},
                outcome="failed",
                llm_response=locate_result,
            )
            return NavigatorState(
                location=self._page.url,
                success=False,
                error=f"Element not found: {description}",
            )

        x, y = locate_result["x"], locate_result["y"]

        # Audit log (redact actual text for security)
        self._audit_logger.log(
            action="type",
            details={
                "description": description,
                "coordinates": (x, y),
                "text_length": len(text),
            },
            outcome="success",
            screenshot_b64=self._last_screenshot_b64,
            llm_response=locate_result,
        )

        try:
            await self._page.mouse.click(x, y)

            if clear_first:
                await self._page.keyboard.press("Control+a")

            await self._page.keyboard.type(text, delay=50)

            return NavigatorState(
                location=self._page.url,
                success=True,
                snapshot=await self.snapshot(),
            )
        except Exception as e:
            return NavigatorState(
                location=self._page.url,
                success=False,
                error=str(e),
            )

    async def scroll(
        self, direction: str = "down", amount: Optional[int] = None
    ) -> NavigatorState:
        """
        Scroll page.

        Security: Rate limited and audit logged.

        Args:
            direction: "up" or "down"
            amount: Pixels to scroll (default: viewport height)

        Returns:
            NavigatorState with post-scroll screenshot
        """
        if not self._page:
            return NavigatorState(
                location="",
                success=False,
                error="Browser not initialized",
            )

        # Security check: Rate limiting (ADR-001 Phase 1)
        if not self.rate_limiter.allow():
            self._audit_logger.log(
                action="scroll",
                details={"direction": direction},
                outcome="rate_limited",
            )
            return NavigatorState(
                location=self._page.url,
                success=False,
                error="Rate limit exceeded. Too many actions per minute.",
            )

        if amount is None:
            amount = self.viewport[1]

        delta = amount if direction == "down" else -amount

        # Audit log
        self._audit_logger.log(
            action="scroll",
            details={"direction": direction, "amount": abs(delta)},
            outcome="success",
        )

        try:
            await self._page.mouse.wheel(0, delta)
            await self._page.wait_for_timeout(300)  # Let page settle

            return NavigatorState(
                location=self._page.url,
                success=True,
                snapshot=await self.snapshot(),
            )
        except Exception as e:
            return NavigatorState(
                location=self._page.url,
                success=False,
                error=str(e),
            )

    async def wait(
        self,
        description: Optional[str] = None,
        seconds: Optional[float] = None,
    ) -> NavigatorState:
        """
        Wait for condition.

        Args:
            description: Visual element to wait for (polls until found)
            seconds: Simple delay in seconds

        Returns:
            NavigatorState with final screenshot
        """
        if not self._page:
            return NavigatorState(
                location="",
                success=False,
                error="Browser not initialized",
            )

        try:
            if seconds:
                await self._page.wait_for_timeout(int(seconds * 1000))

            if description:
                # Poll for visual element
                max_attempts = 20
                for _ in range(max_attempts):
                    result = await self.locate(description)
                    if result.get("found"):
                        break
                    await self._page.wait_for_timeout(500)

            return NavigatorState(
                location=self._page.url,
                success=True,
                snapshot=await self.snapshot(),
            )
        except Exception as e:
            return NavigatorState(
                location=self._page.url,
                success=False,
                error=str(e),
            )

    async def get_storage_state(self) -> Optional[Dict[str, Any]]:
        """
        Get current storage state (cookies, localStorage).

        Returns:
            Playwright storage_state dict, or None if context not initialized
        """
        if not self._context:
            return None

        return await self._context.storage_state()

    async def cleanup(self) -> None:
        """Close browser and release resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        logger.debug(f"BrowserDriver cleanup: {len(self.screenshots)} screenshots taken")
