"""
Visual Grounding LLM Adapters.

Factory (recommended):
- VisualGrounderFactory.create() - Get a configured grounder
- VisualGrounderFactory.create_with_failover() - Get grounder with auto-retry

Available adapters (low-level):
- OpenAIVisualGrounder: Works with OpenAI API or LM Studio (Fara-7B)
- GeminiVisualGrounder: Works with Google Gemini API

LM Studio server discovery:
- discover_fara_server: Find server with Fara model loaded
- get_server_status: Get status of all configured servers
"""

from .base import VisualGrounder, LocateResult
from .openai_adapter import OpenAIVisualGrounder
from .gemini_adapter import GeminiVisualGrounder
from .factory import VisualGrounderFactory, FailoverGrounder
from .lmstudio_discovery import (
    discover_fara_server,
    get_server_status,
    parse_lmstudio_servers,
    get_fara_model_ids,
    ModelInfo,
    ServerInfo,
)

__all__ = [
    # Factory (recommended)
    "VisualGrounderFactory",
    "FailoverGrounder",
    # Base
    "VisualGrounder",
    "LocateResult",
    # Adapters (low-level)
    "OpenAIVisualGrounder",
    "GeminiVisualGrounder",
    # LM Studio discovery
    "discover_fara_server",
    "get_server_status",
    "parse_lmstudio_servers",
    "get_fara_model_ids",
    "ModelInfo",
    "ServerInfo",
]
