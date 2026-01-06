"""
Tests for Phase 1 Security Controls.

Following test-first approach per ADR-001:
1. URL Allowlist/Blocklist - domain access control
2. Audit Logging - forensic capability
3. Rate Limiting - runaway automation prevention
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================================
# URL Allowlist/Blocklist Tests
# ============================================================================


class TestURLAllowlistBlocklist:
    """Tests for domain-level access control in BrowserDriver."""

    @pytest.mark.asyncio
    async def test_blocked_domain_denied(self):
        """Blocked domains should be denied navigation."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver(
            blocked_domains=["*.bank.com", "paypal.com"]
        )

        # Mock browser initialization
        driver._page = MagicMock()
        driver._page.url = "about:blank"

        result = await driver.goto("https://my.bank.com/login")

        assert result.success is False
        assert "blocked" in result.error.lower()
        assert "bank.com" in result.error

    @pytest.mark.asyncio
    async def test_allowlist_only_permits_listed_domains(self):
        """When allowlist is set, only listed domains should be permitted."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver(
            allowed_domains=["gemini.google.com", "example.com"]
        )

        driver._page = MagicMock()
        driver._page.url = "about:blank"

        # Should be blocked (not in allowlist)
        result = await driver.goto("https://malicious-site.com")

        assert result.success is False
        assert "not in allowed" in result.error.lower() or "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_allowlist_permits_listed_domain(self):
        """Domains in allowlist should be permitted."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver(
            allowed_domains=["example.com"]
        )

        # Mock the page and navigation
        driver._page = AsyncMock()
        driver._page.url = "https://example.com/page"
        driver._page.goto = AsyncMock()
        driver._page.screenshot = AsyncMock(return_value=b"fake_screenshot")

        result = await driver.goto("https://example.com/test")

        # Should attempt navigation (not blocked)
        driver._page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_blocklist_blocks_sensitive_sites(self):
        """Default blocklist should block common sensitive sites."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver()  # Uses default blocklist

        driver._page = MagicMock()
        driver._page.url = "about:blank"

        # These should all be blocked by default
        sensitive_urls = [
            "https://accounts.google.com/signin",
            "https://login.microsoftonline.com",
            "https://www.paypal.com/login",
            "https://stripe.com/dashboard",
        ]

        for url in sensitive_urls:
            result = await driver.goto(url)
            assert result.success is False, f"Expected {url} to be blocked"

    @pytest.mark.asyncio
    async def test_blocklist_supports_wildcard_subdomains(self):
        """Blocklist should support wildcard patterns like *.bank.com."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver(
            blocked_domains=["*.bank.com"]
        )

        driver._page = MagicMock()
        driver._page.url = "about:blank"

        # All subdomains should be blocked
        blocked_urls = [
            "https://my.bank.com",
            "https://login.bank.com",
            "https://api.bank.com/v1",
            "https://bank.com",  # Base domain also blocked
        ]

        for url in blocked_urls:
            result = await driver.goto(url)
            assert result.success is False, f"Expected {url} to be blocked"

    @pytest.mark.asyncio
    async def test_blocklist_takes_precedence_over_allowlist(self):
        """If domain is in both lists, blocklist should win."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver(
            allowed_domains=["google.com", "accounts.google.com"],
            blocked_domains=["accounts.google.com"]
        )

        driver._page = MagicMock()
        driver._page.url = "about:blank"

        # accounts.google.com should be blocked even though in allowlist
        result = await driver.goto("https://accounts.google.com/signin")

        assert result.success is False


# ============================================================================
# Audit Logging Tests
# ============================================================================


class TestAuditLogging:
    """Tests for comprehensive audit logging."""

    @pytest.mark.asyncio
    async def test_goto_logs_audit_event(self):
        """Navigation should create audit log entry."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver()

        # Mock browser
        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.goto = AsyncMock()
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")

        await driver.goto("https://example.com")

        assert len(driver.audit_log) >= 1
        event = driver.audit_log[-1]
        assert event.action == "goto"
        assert "example.com" in event.details.get("url", "")

    @pytest.mark.asyncio
    async def test_click_logs_audit_event_with_coordinates(self):
        """Click should log coordinates and LLM response."""
        from surf_mcp.drivers.browser import BrowserDriver
        from surf_mcp.llm.base import LocateResult

        # Mock visual grounder
        mock_grounder = MagicMock()
        mock_grounder.locate = AsyncMock(return_value=LocateResult(
            found=True,
            x=100,
            y=200,
            confidence=0.95,
            reasoning="Found button"
        ))

        driver = BrowserDriver(visual_grounder=mock_grounder)

        # Mock browser
        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")
        driver._page.mouse = AsyncMock()
        driver._page.wait_for_load_state = AsyncMock()

        await driver.click("the Submit button")

        # Find the click audit event
        click_events = [e for e in driver.audit_log if e.action == "click"]
        assert len(click_events) >= 1

        event = click_events[-1]
        assert event.details.get("description") == "the Submit button"
        assert event.details.get("coordinates") == (100, 200)
        assert event.llm_response is not None

    @pytest.mark.asyncio
    async def test_audit_log_includes_timestamp(self):
        """All audit events should have timestamps."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver()

        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.goto = AsyncMock()
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")

        before = datetime.now(timezone.utc)
        await driver.goto("https://example.com")
        after = datetime.now(timezone.utc)

        event = driver.audit_log[-1]
        assert before <= event.timestamp <= after

    @pytest.mark.asyncio
    async def test_audit_log_includes_session_id(self):
        """Audit events should include session ID for correlation."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver()

        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.goto = AsyncMock()
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")

        await driver.goto("https://example.com")

        event = driver.audit_log[-1]
        # Session ID should be present and match driver's session
        assert event.session_id is not None
        assert len(event.session_id) > 0
        assert event.session_id == driver._session_id

    @pytest.mark.asyncio
    async def test_blocked_navigation_logged(self):
        """Blocked navigations should be logged for security monitoring."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver(
            blocked_domains=["evil.com"]
        )

        driver._page = MagicMock()
        driver._page.url = "about:blank"

        await driver.goto("https://evil.com/malware")

        # Should have audit entry with outcome="blocked"
        blocked_events = [e for e in driver.audit_log if e.outcome == "blocked"]
        assert len(blocked_events) >= 1

    @pytest.mark.asyncio
    async def test_audit_log_includes_screenshot_hash(self):
        """Audit events should include hash of screenshot used."""
        from surf_mcp.drivers.browser import BrowserDriver
        from surf_mcp.llm.base import LocateResult

        mock_grounder = MagicMock()
        mock_grounder.locate = AsyncMock(return_value=LocateResult(
            found=True, x=100, y=200, confidence=0.9, reasoning="Found"
        ))

        driver = BrowserDriver(visual_grounder=mock_grounder)

        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.screenshot = AsyncMock(return_value=b"screenshot_data")
        driver._page.mouse = AsyncMock()
        driver._page.wait_for_load_state = AsyncMock()

        await driver.click("some element")

        click_events = [e for e in driver.audit_log if e.action == "click"]
        assert len(click_events) >= 1

        event = click_events[-1]
        assert event.screenshot_hash is not None
        # SHA256 hash is 64 characters
        assert len(event.screenshot_hash) == 64


# ============================================================================
# Rate Limiting Tests
# ============================================================================


class TestRateLimiting:
    """Tests for action rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_excessive_actions(self):
        """Exceeding rate limit should block further actions."""
        from surf_mcp.drivers.browser import BrowserDriver
        from surf_mcp.llm.base import LocateResult

        mock_grounder = MagicMock()
        mock_grounder.locate = AsyncMock(return_value=LocateResult(
            found=True, x=100, y=200, confidence=0.9, reasoning="Found"
        ))

        driver = BrowserDriver(
            visual_grounder=mock_grounder,
            max_actions_per_minute=5
        )

        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")
        driver._page.mouse = AsyncMock()
        driver._page.wait_for_load_state = AsyncMock()

        # Execute 5 clicks (should all succeed)
        for i in range(5):
            result = await driver.click(f"button {i}")
            assert result.success is True, f"Click {i} should succeed"

        # 6th click should be rate limited
        result = await driver.click("button 6")
        assert result.success is False
        assert "rate limit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_rate_limit_resets_after_window(self):
        """Rate limit should reset after time window passes."""
        from surf_mcp.drivers.browser import BrowserDriver
        from surf_mcp.llm.base import LocateResult
        import time

        mock_grounder = MagicMock()
        mock_grounder.locate = AsyncMock(return_value=LocateResult(
            found=True, x=100, y=200, confidence=0.9, reasoning="Found"
        ))

        driver = BrowserDriver(
            visual_grounder=mock_grounder,
            max_actions_per_minute=2
        )

        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")
        driver._page.mouse = AsyncMock()
        driver._page.wait_for_load_state = AsyncMock()

        # Use up the rate limit
        await driver.click("button 1")
        await driver.click("button 2")

        # Should be rate limited
        result = await driver.click("button 3")
        assert result.success is False

        # Simulate time passing (mock the rate limiter's window)
        driver.rate_limiter._reset_window()

        # Should work again
        result = await driver.click("button 4")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_rate_limit_applies_to_all_action_types(self):
        """Rate limit should count clicks, types, and scrolls together."""
        from surf_mcp.drivers.browser import BrowserDriver
        from surf_mcp.llm.base import LocateResult

        mock_grounder = MagicMock()
        mock_grounder.locate = AsyncMock(return_value=LocateResult(
            found=True, x=100, y=200, confidence=0.9, reasoning="Found"
        ))

        driver = BrowserDriver(
            visual_grounder=mock_grounder,
            max_actions_per_minute=3
        )

        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")
        driver._page.mouse = AsyncMock()
        driver._page.keyboard = AsyncMock()
        driver._page.wait_for_load_state = AsyncMock()
        driver._page.wait_for_timeout = AsyncMock()

        # Mix of action types
        await driver.click("button")  # 1
        await driver.type("input", "text")  # 2
        await driver.scroll("down")  # 3

        # 4th action should be rate limited (any type)
        result = await driver.click("another button")
        assert result.success is False
        assert "rate limit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_navigation_not_rate_limited(self):
        """goto/back/forward should not count against rate limit."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver(
            max_actions_per_minute=2
        )

        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.goto = AsyncMock()
        driver._page.go_back = AsyncMock()
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")

        # Multiple navigations should not trigger rate limit
        for i in range(10):
            result = await driver.goto(f"https://example.com/page{i}")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_default_rate_limit_is_reasonable(self):
        """Default rate limit should allow normal use (30/min)."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver()

        # Default should be 30 actions per minute
        assert driver.max_actions_per_minute == 30


# ============================================================================
# Integration Tests
# ============================================================================


class TestSecurityIntegration:
    """Integration tests for combined security controls."""

    @pytest.mark.asyncio
    async def test_blocked_domain_audit_logged_rate_not_consumed(self):
        """Blocked navigation should log but not consume rate limit."""
        from surf_mcp.drivers.browser import BrowserDriver

        driver = BrowserDriver(
            blocked_domains=["evil.com"],
            max_actions_per_minute=2
        )

        driver._page = AsyncMock()
        driver._page.url = "about:blank"
        driver._page.goto = AsyncMock()
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")

        # Attempt blocked navigation multiple times
        for _ in range(10):
            await driver.goto("https://evil.com")

        # Should have audit entries
        assert len(driver.audit_log) >= 10

        # Rate limit should NOT be consumed by blocked navigations
        # So normal navigation should still work
        result = await driver.goto("https://safe.com")
        driver._page.goto.assert_called()  # Should have attempted

    @pytest.mark.asyncio
    async def test_rate_limited_action_still_logged(self):
        """Rate-limited actions should still be logged."""
        from surf_mcp.drivers.browser import BrowserDriver
        from surf_mcp.llm.base import LocateResult

        mock_grounder = MagicMock()
        mock_grounder.locate = AsyncMock(return_value=LocateResult(
            found=True, x=100, y=200, confidence=0.9, reasoning="Found"
        ))

        driver = BrowserDriver(
            visual_grounder=mock_grounder,
            max_actions_per_minute=1
        )

        driver._page = AsyncMock()
        driver._page.url = "https://example.com"
        driver._page.screenshot = AsyncMock(return_value=b"screenshot")
        driver._page.mouse = AsyncMock()
        driver._page.wait_for_load_state = AsyncMock()

        # First action succeeds
        await driver.click("button 1")

        # Second action is rate limited but should still be logged
        result = await driver.click("button 2")
        assert result.success is False

        # Both attempts should be in audit log
        click_events = [e for e in driver.audit_log if e.action == "click"]
        assert len(click_events) >= 2

        # Last one should have outcome indicating rate limited
        assert click_events[-1].outcome == "rate_limited"


# ============================================================================
# PlaywrightExecutor Scroll Tests
# ============================================================================


class TestPlaywrightExecutorScroll:
    """Tests for scroll sign convention handling in PlaywrightExecutor.

    Fara convention: negative pixels = scroll down, positive = scroll up
    Playwright convention: positive delta = scroll down, negative = scroll up
    Classic Microsoft...
    """

    @pytest.mark.asyncio
    async def test_fara_negative_pixels_scrolls_down(self):
        """Fara's negative pixels should result in positive wheel delta (scroll down)."""
        from surf_mcp.drivers.playwright_executor import PlaywrightExecutor
        from surf_mcp.llm.base import FaraToolCall

        executor = PlaywrightExecutor()

        # Mock page with spied wheel method
        mock_page = AsyncMock()
        mock_page.mouse = AsyncMock()
        mock_page.mouse.wheel = AsyncMock()

        # Fara returns negative pixels to mean "scroll down"
        tool_call = FaraToolCall(
            action="scroll",
            pixels=-480,  # Fara: negative = down
            direction=None,  # No explicit direction
        )

        await executor.execute(tool_call, mock_page)

        # Should call wheel with POSITIVE delta (Playwright: positive = down)
        mock_page.mouse.wheel.assert_called_once_with(0, 480)

    @pytest.mark.asyncio
    async def test_fara_positive_pixels_scrolls_up(self):
        """Fara's positive pixels should result in negative wheel delta (scroll up)."""
        from surf_mcp.drivers.playwright_executor import PlaywrightExecutor
        from surf_mcp.llm.base import FaraToolCall

        executor = PlaywrightExecutor()

        mock_page = AsyncMock()
        mock_page.mouse = AsyncMock()
        mock_page.mouse.wheel = AsyncMock()

        # Fara returns positive pixels to mean "scroll up"
        tool_call = FaraToolCall(
            action="scroll",
            pixels=300,  # Fara: positive = up
            direction=None,
        )

        await executor.execute(tool_call, mock_page)

        # Should call wheel with NEGATIVE delta (Playwright: negative = up)
        mock_page.mouse.wheel.assert_called_once_with(0, -300)

    @pytest.mark.asyncio
    async def test_explicit_direction_down(self):
        """Explicit direction='down' with unsigned pixels works correctly."""
        from surf_mcp.drivers.playwright_executor import PlaywrightExecutor
        from surf_mcp.llm.base import FaraToolCall

        executor = PlaywrightExecutor()

        mock_page = AsyncMock()
        mock_page.mouse = AsyncMock()
        mock_page.mouse.wheel = AsyncMock()

        tool_call = FaraToolCall(
            action="scroll",
            pixels=500,
            direction="down",
        )

        await executor.execute(tool_call, mock_page)

        mock_page.mouse.wheel.assert_called_once_with(0, 500)

    @pytest.mark.asyncio
    async def test_explicit_direction_up(self):
        """Explicit direction='up' with unsigned pixels works correctly."""
        from surf_mcp.drivers.playwright_executor import PlaywrightExecutor
        from surf_mcp.llm.base import FaraToolCall

        executor = PlaywrightExecutor()

        mock_page = AsyncMock()
        mock_page.mouse = AsyncMock()
        mock_page.mouse.wheel = AsyncMock()

        tool_call = FaraToolCall(
            action="scroll",
            pixels=500,
            direction="up",
        )

        await executor.execute(tool_call, mock_page)

        mock_page.mouse.wheel.assert_called_once_with(0, -500)


class TestPlaywrightExecutorType:
    """Tests for type action handling in PlaywrightExecutor.

    Fara sends delete_existing_text and press_enter params that must be handled.
    """

    @pytest.mark.asyncio
    async def test_type_with_delete_existing_text(self):
        """Type action with delete_existing_text clears field first."""
        from surf_mcp.drivers.playwright_executor import PlaywrightExecutor
        from surf_mcp.llm.base import FaraToolCall

        executor = PlaywrightExecutor()

        mock_page = AsyncMock()
        mock_page.mouse = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.keyboard.type = AsyncMock()

        tool_call = FaraToolCall(
            action="type",
            coordinate=(720, 333),
            text="hello world",
            delete_existing_text=True,
            press_enter=False,
        )

        result = await executor.execute(tool_call, mock_page)

        assert result.success is True
        # Should click at coordinates
        mock_page.mouse.click.assert_called_once_with(720, 333)
        # Should clear field (Ctrl+A, Delete) then type
        press_calls = mock_page.keyboard.press.call_args_list
        assert len(press_calls) == 2
        assert press_calls[0][0][0] == "Control+a"
        assert press_calls[1][0][0] == "Delete"
        mock_page.keyboard.type.assert_called_once()

    @pytest.mark.asyncio
    async def test_type_with_press_enter(self):
        """Type action with press_enter presses Enter after typing."""
        from surf_mcp.drivers.playwright_executor import PlaywrightExecutor
        from surf_mcp.llm.base import FaraToolCall

        executor = PlaywrightExecutor()

        mock_page = AsyncMock()
        mock_page.mouse = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.keyboard.type = AsyncMock()

        tool_call = FaraToolCall(
            action="type",
            coordinate=(100, 200),
            text="search query",
            delete_existing_text=False,
            press_enter=True,
        )

        result = await executor.execute(tool_call, mock_page)

        assert result.success is True
        mock_page.keyboard.type.assert_called_once()
        # Should press Enter after typing
        mock_page.keyboard.press.assert_called_once_with("Enter")

    @pytest.mark.asyncio
    async def test_type_with_both_params(self):
        """Type action with both delete_existing_text and press_enter."""
        from surf_mcp.drivers.playwright_executor import PlaywrightExecutor
        from surf_mcp.llm.base import FaraToolCall

        executor = PlaywrightExecutor()

        mock_page = AsyncMock()
        mock_page.mouse = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.keyboard.type = AsyncMock()

        tool_call = FaraToolCall(
            action="type",
            coordinate=(720, 333),
            text="olde boston bulldogges",
            delete_existing_text=True,
            press_enter=True,
        )

        result = await executor.execute(tool_call, mock_page)

        assert result.success is True
        # Should: click, Ctrl+A, Delete, type, Enter
        press_calls = mock_page.keyboard.press.call_args_list
        assert len(press_calls) == 3
        assert press_calls[0][0][0] == "Control+a"
        assert press_calls[1][0][0] == "Delete"
        assert press_calls[2][0][0] == "Enter"

    @pytest.mark.asyncio
    async def test_type_basic(self):
        """Basic type action without special params."""
        from surf_mcp.drivers.playwright_executor import PlaywrightExecutor
        from surf_mcp.llm.base import FaraToolCall

        executor = PlaywrightExecutor()

        mock_page = AsyncMock()
        mock_page.mouse = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.keyboard.type = AsyncMock()

        tool_call = FaraToolCall(
            action="type",
            coordinate=(500, 400),
            text="just text",
            # Defaults: delete_existing_text=False, press_enter=False
        )

        result = await executor.execute(tool_call, mock_page)

        assert result.success is True
        mock_page.mouse.click.assert_called_once_with(500, 400)
        mock_page.keyboard.type.assert_called_once()
        # No press calls (no delete, no enter)
        mock_page.keyboard.press.assert_not_called()


class TestAgentRunnerReAct:
    """Tests for AgentRunner ReAct history context."""

    def test_format_step_visit_url(self):
        """Format visit_url action for history."""
        from surf_mcp.drivers.agent_runner import AgentRunner, AgentStep
        from surf_mcp.llm.base import FaraToolCall, ExecutionResult

        runner = AgentRunner(grounder=MagicMock(), executor=MagicMock())

        step = AgentStep(
            step_number=1,
            tool_call=FaraToolCall(action="visit_url", url="https://google.com"),
            execution_result=ExecutionResult(success=True, action="visit_url"),
        )

        result = runner._format_step(step)
        assert "[1]" in result
        assert "visit_url" in result
        assert "google.com" in result
        assert "✓" in result

    def test_format_step_type(self):
        """Format type action for history."""
        from surf_mcp.drivers.agent_runner import AgentRunner, AgentStep
        from surf_mcp.llm.base import FaraToolCall, ExecutionResult

        runner = AgentRunner(grounder=MagicMock(), executor=MagicMock())

        step = AgentStep(
            step_number=2,
            tool_call=FaraToolCall(
                action="type",
                text="hello world",
                coordinate=(100, 200),
            ),
            execution_result=ExecutionResult(success=True, action="type"),
        )

        result = runner._format_step(step)
        assert "[2]" in result
        assert "type" in result
        assert "hello world" in result
        assert "(100, 200)" in result

    def test_format_step_failed(self):
        """Format failed action shows ✗."""
        from surf_mcp.drivers.agent_runner import AgentRunner, AgentStep
        from surf_mcp.llm.base import FaraToolCall, ExecutionResult

        runner = AgentRunner(grounder=MagicMock(), executor=MagicMock())

        step = AgentStep(
            step_number=1,
            tool_call=FaraToolCall(action="left_click", coordinate=(50, 50)),
            execution_result=ExecutionResult(success=False, action="left_click", error="timeout"),
        )

        result = runner._format_step(step)
        assert "✗" in result

    def test_build_goal_with_history_empty(self):
        """No history returns original goal."""
        from surf_mcp.drivers.agent_runner import AgentRunner

        runner = AgentRunner(grounder=MagicMock(), executor=MagicMock())

        result = runner._build_goal_with_history("click the button", [])
        assert result == "click the button"

    def test_build_goal_with_history(self):
        """History is appended to goal."""
        from surf_mcp.drivers.agent_runner import AgentRunner, AgentStep
        from surf_mcp.llm.base import FaraToolCall, ExecutionResult

        runner = AgentRunner(grounder=MagicMock(), executor=MagicMock())

        steps = [
            AgentStep(
                step_number=1,
                tool_call=FaraToolCall(action="visit_url", url="https://google.com"),
                execution_result=ExecutionResult(success=True, action="visit_url"),
            ),
            AgentStep(
                step_number=2,
                tool_call=FaraToolCall(action="type", text="search", coordinate=(100, 200)),
                execution_result=ExecutionResult(success=True, action="type"),
            ),
        ]

        result = runner._build_goal_with_history("search for cats", steps)

        assert "search for cats" in result
        assert "Previous actions:" in result
        assert "[1]" in result
        assert "[2]" in result
        assert "visit_url" in result
        assert "type" in result
        assert "next action" in result.lower()
