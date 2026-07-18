"""
Rate Limiting for browser automation actions.

Prevents runaway automation loops per ADR-SURF-001 Phase 1.
"""

import time
from collections import deque
from typing import Deque


class RateLimiter:
    """
    Token bucket rate limiter for browser actions.

    Tracks actions within a sliding window and blocks when limit exceeded.

    Usage:
        limiter = RateLimiter(max_per_minute=30)
        if limiter.allow():
            # Perform action
        else:
            # Rate limited
    """

    def __init__(self, max_per_minute: int = 30):
        """
        Initialize rate limiter.

        Args:
            max_per_minute: Maximum allowed actions per minute window
        """
        self.max_per_minute = max_per_minute
        self._window_seconds = 60.0
        self._timestamps: Deque[float] = deque()

    def allow(self) -> bool:
        """
        Check if action is allowed under rate limit.

        Returns:
            True if action allowed, False if rate limited
        """
        now = time.time()
        window_start = now - self._window_seconds

        # Remove timestamps outside the window
        while self._timestamps and self._timestamps[0] < window_start:
            self._timestamps.popleft()

        # Check if under limit
        if len(self._timestamps) < self.max_per_minute:
            self._timestamps.append(now)
            return True

        return False

    def remaining(self) -> int:
        """Return number of actions remaining in current window."""
        now = time.time()
        window_start = now - self._window_seconds

        # Count actions in window
        while self._timestamps and self._timestamps[0] < window_start:
            self._timestamps.popleft()

        return max(0, self.max_per_minute - len(self._timestamps))

    def _reset_window(self) -> None:
        """
        Reset the rate limit window (for testing).

        Clears all tracked timestamps, effectively resetting the limit.
        """
        self._timestamps.clear()

    def __repr__(self) -> str:
        return f"RateLimiter(max_per_minute={self.max_per_minute}, remaining={self.remaining()})"
