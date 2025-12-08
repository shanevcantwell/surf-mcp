"""
Audit Logging for browser automation actions.

Provides forensic capability per ADR-001 Phase 1.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditEvent:
    """
    Record of a browser automation action.

    Captures all context needed for security monitoring and incident investigation.
    """

    timestamp: datetime
    session_id: str
    action: str  # "goto", "locate", "click", "type", "scroll", "wait"
    details: Dict[str, Any]
    outcome: str  # "success", "failed", "blocked", "rate_limited"
    screenshot_hash: Optional[str] = None  # SHA256 of screenshot used for visual grounding
    llm_response: Optional[Dict[str, Any]] = None  # Raw grounding result


class AuditLogger:
    """
    Collects and manages audit events for a browser session.

    Usage:
        logger = AuditLogger(session_id="abc123")
        logger.log("click", {"description": "Submit button"}, "success")
        events = logger.get_events()
    """

    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self._events: List[AuditEvent] = []

    def log(
        self,
        action: str,
        details: Dict[str, Any],
        outcome: str,
        screenshot_b64: Optional[str] = None,
        llm_response: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """
        Record an audit event.

        Args:
            action: Type of action (goto, click, type, etc.)
            details: Action-specific details
            outcome: Result (success, failed, blocked, rate_limited)
            screenshot_b64: Base64 screenshot used (will be hashed)
            llm_response: Raw LLM grounding response

        Returns:
            The created AuditEvent
        """
        screenshot_hash = None
        if screenshot_b64:
            screenshot_hash = hashlib.sha256(screenshot_b64.encode()).hexdigest()

        event = AuditEvent(
            timestamp=datetime.now(timezone.utc),
            session_id=self.session_id,
            action=action,
            details=details,
            outcome=outcome,
            screenshot_hash=screenshot_hash,
            llm_response=llm_response,
        )

        self._events.append(event)
        logger.debug(f"Audit: {action} -> {outcome} | {details}")

        return event

    def get_events(self) -> List[AuditEvent]:
        """Return all audit events."""
        return list(self._events)

    def get_events_by_action(self, action: str) -> List[AuditEvent]:
        """Return events filtered by action type."""
        return [e for e in self._events if e.action == action]

    def get_events_by_outcome(self, outcome: str) -> List[AuditEvent]:
        """Return events filtered by outcome."""
        return [e for e in self._events if e.outcome == outcome]

    def clear(self) -> None:
        """Clear all audit events."""
        self._events.clear()

    def __len__(self) -> int:
        return len(self._events)
