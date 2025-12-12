"""
Visual Grounding LLM Interface.

Visual grounding uses multimodal LLMs to locate UI elements by natural
language description instead of brittle CSS selectors.

The LLM receives a screenshot and a description like "the blue Submit button"
and returns coordinates (x, y) where the element is located.

Per ADR-005: Fara is an agentic model that returns complete tool_calls.
FaraToolCall preserves the full action, while LocateResult is deprecated
(coordinate-only extraction).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ============ Exceptions ============


class UnsupportedActionError(Exception):
    """Raised when Fara returns an action we don't support."""

    pass


# ============ Data Models ============


class LocateResult(BaseModel):
    """
    Result of locating a UI element (coordinates only).

    DEPRECATED: Use FaraToolCall instead, which preserves the full action.
    This class remains for backwards compatibility during migration.
    """

    found: bool = Field(..., description="Whether the element was found")
    x: Optional[int] = Field(None, description="X coordinate (center of element)")
    y: Optional[int] = Field(None, description="Y coordinate (center of element)")
    confidence: Optional[float] = Field(None, description="Model confidence 0-1")
    reasoning: Optional[str] = Field(None, description="Model's explanation")


@dataclass
class FaraToolCall:
    """
    Represents a complete Fara tool_call, preserving all action details.

    Per ADR-005: Unlike LocateResult (coordinates only), this captures Fara's
    full decision including the action type, enabling direct execution.

    Supported actions:
    - left_click, click, double_click: Click at coordinates
    - type: Type text at coordinates
    - scroll: Scroll page up/down
    - key: Press keyboard keys
    - visit_url: Navigate to URL
    - terminate: Task complete signal
    """

    action: str
    """Action type: left_click, type, scroll, key, visit_url, terminate, etc."""

    coordinate: Optional[Tuple[int, int]] = None
    """(x, y) coordinates for click/type actions."""

    text: Optional[str] = None
    """Text to type (for type action)."""

    direction: Optional[str] = None
    """Scroll direction: 'up' or 'down'."""

    pixels: Optional[int] = None
    """Scroll amount in pixels."""

    url: Optional[str] = None
    """URL to navigate to (for visit_url action)."""

    keys: Optional[List[str]] = None
    """Key names to press (for key action), e.g., ['Enter'], ['Control', 'c']."""

    confidence: float = 1.0
    """Model confidence 0.0-1.0."""

    reasoning: str = ""
    """Fara's chain-of-thought explanation."""


@dataclass
class ExecutionResult:
    """Result of executing a FaraToolCall via PlaywrightExecutor."""

    success: bool
    """Whether the action executed successfully."""

    action: Optional[str] = None
    """The action that was executed."""

    error: Optional[str] = None
    """Error message if success=False."""


class VisualGrounder(ABC):
    """
    Abstract base for visual grounding implementations.

    Implementations should handle:
    - Resolution scaling (if needed for the model)
    - JSON response parsing
    - Error handling
    """

    @abstractmethod
    async def locate(self, description: str, screenshot_b64: str) -> LocateResult:
        """
        Locate an element by description in a screenshot.

        Args:
            description: Natural language description of the element
                e.g., "the blue Submit button", "the email input field"
            screenshot_b64: Base64-encoded PNG screenshot

        Returns:
            LocateResult with coordinates and confidence
        """
        pass

    @abstractmethod
    async def verify(self, description: str, screenshot_b64: str) -> LocateResult:
        """
        Verify that an element exists (doesn't need precise coordinates).

        Args:
            description: Natural language description of the element
            screenshot_b64: Base64-encoded PNG screenshot

        Returns:
            LocateResult with found status (coordinates optional)
        """
        pass

    @abstractmethod
    async def get_action(self, goal: str, screenshot_b64: str) -> FaraToolCall:
        """
        Get the action to perform based on goal and screenshot.

        Per ADR-005: Fara decides what action to take, returns full tool_call.

        Args:
            goal: Natural language goal (e.g., "click the search button")
            screenshot_b64: Base64-encoded PNG screenshot

        Returns:
            FaraToolCall with action type, coordinates, and other details
        """
        pass
