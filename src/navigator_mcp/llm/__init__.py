"""
Visual Grounding LLM Adapters.

Available adapters:
- OpenAIVisualGrounder: Works with OpenAI API or LM Studio (Fara-7B)
- GeminiVisualGrounder: Works with Google Gemini API
"""

from .base import VisualGrounder, LocateResult
from .openai_adapter import OpenAIVisualGrounder
from .gemini_adapter import GeminiVisualGrounder

__all__ = [
    "VisualGrounder",
    "LocateResult",
    "OpenAIVisualGrounder",
    "GeminiVisualGrounder",
]
