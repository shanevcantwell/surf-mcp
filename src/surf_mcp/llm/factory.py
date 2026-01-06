"""
Visual Grounder Factory.

Handles adapter instantiation, server discovery, and failover logic.
Callers use the factory and are completely ignorant of multi-GPU/retry details.

Usage:
    # Simple - get a configured grounder
    grounder = await VisualGrounderFactory.create()
    result = await grounder.locate(description, screenshot)

    # With automatic failover across servers
    grounder = await VisualGrounderFactory.create_with_failover()
    result = await grounder.locate(description, screenshot)  # Retries on failure
"""

import logging
import os
from typing import List, Optional

from .base import FaraToolCall, LocateResult, StepContext, VisualGrounder
from .lmstudio_discovery import (
    discover_fara_server,
    parse_lmstudio_servers,
    get_fara_model_ids,
)

logger = logging.getLogger(__name__)


class VisualGrounderFactory:
    """
    Factory for creating properly configured visual grounders.

    Handles all the discovery and configuration complexity so callers
    just get a working grounder instance.
    """

    @classmethod
    async def create(cls, provider: Optional[str] = None) -> VisualGrounder:
        """
        Create a configured visual grounder.

        For LM Studio/OpenAI providers, performs server discovery to find
        the best server with the target model.

        Args:
            provider: "gemini", "openai", or None (auto-detect from env)

        Returns:
            Configured VisualGrounder ready to use
        """
        if provider is None:
            provider = os.environ.get("SURF_LLM_PROVIDER", "openai")

        if provider == "gemini":
            from .gemini_adapter import GeminiVisualGrounder
            return GeminiVisualGrounder()

        # OpenAI/LM Studio - discover best server
        from .openai_adapter import OpenAIVisualGrounder

        url, model = await discover_fara_server()
        logger.info(f"Factory: Created OpenAI grounder with {url}, model={model}")
        return OpenAIVisualGrounder(api_base=url, model=model)

    @classmethod
    async def create_with_failover(
        cls,
        provider: Optional[str] = None,
        max_failures: Optional[int] = None,
    ) -> "FailoverGrounder":
        """
        Create a grounder with automatic failover across servers.

        On failure, automatically retries with the next available server.

        Args:
            provider: "gemini", "openai", or None (auto-detect)
            max_failures: Max retries before giving up (default from FARA_MAX_FAILURES)

        Returns:
            FailoverGrounder that wraps adapters with retry logic
        """
        if provider is None:
            provider = os.environ.get("SURF_LLM_PROVIDER", "openai")

        if max_failures is None:
            max_failures = int(os.environ.get("FARA_MAX_FAILURES", "2"))

        if provider == "gemini":
            # Gemini doesn't have multi-server, just wrap single adapter
            from .gemini_adapter import GeminiVisualGrounder
            return FailoverGrounder(
                servers=[("gemini", None)],
                model_ids=["gemini"],
                provider="gemini",
                max_failures=1,
            )

        # OpenAI/LM Studio - get all servers for failover
        servers = parse_lmstudio_servers()
        model_ids = get_fara_model_ids()

        return FailoverGrounder(
            servers=list(servers.items()),
            model_ids=model_ids,
            provider="openai",
            max_failures=max_failures,
        )


class FailoverGrounder(VisualGrounder):
    """
    Visual grounder with automatic failover across multiple servers.

    On failure, tries the next server in the list. Completely transparent
    to callers - they just call locate() and get results.
    """

    def __init__(
        self,
        servers: List[tuple],  # [(name, url), ...]
        model_ids: List[str],
        provider: str,
        max_failures: int = 2,
    ):
        """
        Initialize failover grounder.

        Args:
            servers: List of (name, url) tuples
            model_ids: Priority-ordered list of model IDs to try
            provider: "openai" or "gemini"
            max_failures: Max failures before giving up
        """
        self.servers = servers
        self.model_ids = model_ids
        self.provider = provider
        self.max_failures = max_failures

        # Track which server we're currently using
        self._current_server_idx = 0
        self._current_model_idx = 0
        self._adapter: Optional[VisualGrounder] = None

    def _create_adapter(self, server_url: str, model_id: str) -> VisualGrounder:
        """Create an adapter for the given server and model."""
        if self.provider == "gemini":
            from .gemini_adapter import GeminiVisualGrounder
            return GeminiVisualGrounder()
        else:
            from .openai_adapter import OpenAIVisualGrounder
            return OpenAIVisualGrounder(api_base=server_url, model=model_id)

    def _get_next_config(self) -> Optional[tuple]:
        """
        Get next server/model config to try.

        Returns:
            (server_url, model_id) tuple or None if exhausted
        """
        if self._current_server_idx >= len(self.servers):
            return None

        name, url = self.servers[self._current_server_idx]
        model_id = self.model_ids[self._current_model_idx]

        # Move to next config for next failure
        self._current_model_idx += 1
        if self._current_model_idx >= len(self.model_ids):
            self._current_model_idx = 0
            self._current_server_idx += 1

        return (url, model_id)

    async def locate(self, description: str, screenshot_b64: str) -> LocateResult:
        """
        Locate element with automatic failover.

        Tries each server/model combination until success or max_failures reached.
        """
        failures = 0
        last_error = None

        # Reset for this request
        self._current_server_idx = 0
        self._current_model_idx = 0

        while failures < self.max_failures:
            config = self._get_next_config()
            if config is None:
                # Exhausted all servers, wrap around
                self._current_server_idx = 0
                self._current_model_idx = 0
                config = self._get_next_config()

            server_url, model_id = config

            try:
                adapter = self._create_adapter(server_url, model_id)
                result = await adapter.locate(description, screenshot_b64)

                # Success - cache this adapter for future calls
                self._adapter = adapter
                return result

            except Exception as e:
                failures += 1
                last_error = e
                logger.warning(
                    f"Failover: attempt {failures}/{self.max_failures} failed "
                    f"on {server_url} with {model_id}: {e}"
                )

        # All retries exhausted
        logger.error(f"Failover: all {self.max_failures} attempts failed")
        return LocateResult(
            found=False,
            reasoning=f"All servers failed after {failures} attempts. Last error: {last_error}",
        )

    async def verify(self, description: str, screenshot_b64: str) -> LocateResult:
        """Verify element exists (uses locate)."""
        return await self.locate(description, screenshot_b64)

    async def get_action(self, goal: str, screenshot_b64: str) -> "FaraToolCall":
        """
        Get action with automatic failover.

        Tries each server/model combination until success or max_failures reached.
        """
        from .base import FaraToolCall

        failures = 0
        last_error = None

        # Reset for this request
        self._current_server_idx = 0
        self._current_model_idx = 0

        while failures < self.max_failures:
            config = self._get_next_config()
            if config is None:
                # Exhausted all servers, wrap around
                self._current_server_idx = 0
                self._current_model_idx = 0
                config = self._get_next_config()

            server_url, model_id = config

            try:
                adapter = self._create_adapter(server_url, model_id)
                result = await adapter.get_action(goal, screenshot_b64)

                # Success - cache this adapter for future calls
                self._adapter = adapter
                return result

            except Exception as e:
                failures += 1
                last_error = e
                logger.warning(
                    f"Failover: attempt {failures}/{self.max_failures} failed "
                    f"on {server_url} with {model_id}: {e}"
                )

        # All retries exhausted
        logger.error(f"Failover: all {self.max_failures} attempts failed")
        return FaraToolCall(
            action="terminate",
            confidence=0.0,
            reasoning=f"All servers failed after {failures} attempts. Last error: {last_error}",
        )

    async def get_action_with_context(
        self,
        goal: str,
        screenshot_b64: str,
        history: Optional[List[StepContext]] = None,
    ) -> "FaraToolCall":
        """
        Get action with multi-screenshot context and automatic failover.

        Per Fara-7B docs: Uses "latest screenshots" and "full history of
        previous thoughts and actions" for better multi-step reasoning.

        Tries each server/model combination until success or max_failures reached.
        """
        failures = 0
        last_error = None

        # Reset for this request
        self._current_server_idx = 0
        self._current_model_idx = 0

        while failures < self.max_failures:
            config = self._get_next_config()
            if config is None:
                # Exhausted all servers, wrap around
                self._current_server_idx = 0
                self._current_model_idx = 0
                config = self._get_next_config()

            server_url, model_id = config

            try:
                adapter = self._create_adapter(server_url, model_id)
                # Use get_action_with_context if available, else fallback
                if hasattr(adapter, "get_action_with_context"):
                    result = await adapter.get_action_with_context(
                        goal, screenshot_b64, history=history
                    )
                else:
                    result = await adapter.get_action(goal, screenshot_b64)

                # Success - cache this adapter for future calls
                self._adapter = adapter
                return result

            except Exception as e:
                failures += 1
                last_error = e
                logger.warning(
                    f"Failover: attempt {failures}/{self.max_failures} failed "
                    f"on {server_url} with {model_id}: {e}"
                )

        # All retries exhausted
        logger.error(f"Failover: all {self.max_failures} attempts failed")
        return FaraToolCall(
            action="terminate",
            confidence=0.0,
            reasoning=f"All servers failed after {failures} attempts. Last error: {last_error}",
        )
