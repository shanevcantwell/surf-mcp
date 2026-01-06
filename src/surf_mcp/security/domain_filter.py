"""
Domain Filtering for URL access control.

Implements allowlist/blocklist per ADR-001 Phase 1.
"""

import fnmatch
import logging
from typing import List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default blocklist for sensitive sites
DEFAULT_BLOCKED_DOMAINS = [
    "*.bank.com",
    "*.paypal.com",
    "paypal.com",
    "accounts.google.com",
    "login.microsoftonline.com",
    "*.stripe.com",
    "stripe.com",
]


class DomainFilter:
    """
    URL access control via allowlist and blocklist.

    Blocklist takes precedence over allowlist for defense in depth.

    Usage:
        filter = DomainFilter(
            allowed_domains=["example.com", "*.google.com"],
            blocked_domains=["accounts.google.com"]
        )
        allowed, reason = filter.check("https://www.google.com/search")
    """

    def __init__(
        self,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
        use_default_blocklist: bool = True,
    ):
        """
        Initialize domain filter.

        Args:
            allowed_domains: If set, only these domains allowed (allowlist mode)
            blocked_domains: Domains to always block
            use_default_blocklist: Include default sensitive site blocklist
        """
        self.allowed_domains = allowed_domains
        self.blocked_domains = list(blocked_domains or [])

        if use_default_blocklist:
            self.blocked_domains.extend(DEFAULT_BLOCKED_DOMAINS)

    def check(self, url: str) -> Tuple[bool, str]:
        """
        Check if URL is allowed.

        Args:
            url: Full URL to check

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove port if present
            if ":" in domain:
                domain = domain.split(":")[0]

        except Exception as e:
            return False, f"Invalid URL: {e}"

        # Check blocklist first (takes precedence)
        if self._matches_patterns(domain, self.blocked_domains):
            logger.warning(f"Domain blocked by security policy: {domain}")
            return False, f"Domain blocked by security policy: {domain}"

        # If allowlist is set, domain must be in it
        if self.allowed_domains is not None:
            if not self._matches_patterns(domain, self.allowed_domains):
                logger.warning(f"Domain not in allowed list: {domain}")
                return False, f"Domain not in allowed list: {domain}"

        return True, "allowed"

    def _matches_patterns(self, domain: str, patterns: List[str]) -> bool:
        """
        Check if domain matches any pattern.

        Supports wildcards: *.google.com matches sub.google.com and google.com
        """
        for pattern in patterns:
            pattern = pattern.lower()

            # Exact match
            if domain == pattern:
                return True

            # Wildcard pattern (*.example.com)
            if pattern.startswith("*."):
                base_domain = pattern[2:]  # Remove "*."

                # Match the base domain itself
                if domain == base_domain:
                    return True

                # Match subdomains
                if domain.endswith("." + base_domain):
                    return True

            # fnmatch for other glob patterns
            if fnmatch.fnmatch(domain, pattern):
                return True

        return False

    def __repr__(self) -> str:
        return (
            f"DomainFilter("
            f"allowed={self.allowed_domains}, "
            f"blocked={len(self.blocked_domains)} patterns)"
        )
