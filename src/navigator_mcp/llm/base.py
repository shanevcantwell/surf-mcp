"""
Visual Grounding LLM Interface.

Visual grounding uses multimodal LLMs to locate UI elements by natural
language description instead of brittle CSS selectors.

The LLM receives a screenshot and a description like "the blue Submit button"
and returns coordinates (x, y) where the element is located.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class LocateResult(BaseModel):
    """Result of locating a UI element."""

    found: bool = Field(..., description="Whether the element was found")
    x: Optional[int] = Field(None, description="X coordinate (center of element)")
    y: Optional[int] = Field(None, description="Y coordinate (center of element)")
    confidence: Optional[float] = Field(None, description="Model confidence 0-1")
    reasoning: Optional[str] = Field(None, description="Model's explanation")


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
