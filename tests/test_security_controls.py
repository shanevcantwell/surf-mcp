"""
Security Controls Unit Tests.

Unit tests for security features (ADR-SURF-001):
- URL Allowlist/Blocklist - domain access control
- Audit Logging - forensic capability
- Rate Limiting - runaway automation prevention

REQUIREMENTS:
    pip install -e ".[dev]"

RUN:
    pytest tests/test_security_controls.py -v

NOTE:
    These are unit tests with MOCKED browsers.
    They verify security logic, not browser behavior.
    For real browser security tests, see test_docker_e2e.py.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Skip entire module if surf_mcp not installed
pytest.importorskip("surf_mcp", reason="Requires: pip install -e '.[dev]'")


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
