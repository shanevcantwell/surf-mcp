"""
LM Studio Server Discovery.

Discovers LM Studio servers and finds models by probing the native
/api/v0/models endpoint which returns model state (loaded/not-loaded),
type (llm/vlm/embeddings), quantization, etc.

This is separate from the OpenAI adapter to maintain clean separation
of concerns - discovery is LM Studio-specific, inference is OpenAI-compatible.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a model from LM Studio."""

    id: str
    state: str = "unknown"  # "loaded", "not-loaded", "unknown"
    type: str = "unknown"  # "llm", "vlm", "embeddings"
    quantization: Optional[str] = None
    max_context_length: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelInfo":
        return cls(
            id=data.get("id", ""),
            state=data.get("state", "unknown"),
            type=data.get("type", "unknown"),
            quantization=data.get("quantization"),
            max_context_length=data.get("max_context_length"),
        )


@dataclass
class ServerInfo:
    """Information about an LM Studio server."""

    name: str
    url: str
    models: List[ModelInfo] = field(default_factory=list)
    reachable: bool = False
    error: Optional[str] = None


def parse_lmstudio_servers() -> Dict[str, str]:
    """
    Parse LMSTUDIO_SERVERS env var into name→URL mapping.

    Format: "name1=url1,name2=url2" (uses = separator since URLs contain :)
    Example: "rtx3090=http://localhost:1234/v1,rtx8000=http://192.168.137.2:1234/v1"

    Returns:
        Dict mapping server names to URLs
    """
    servers_str = os.getenv("LMSTUDIO_SERVERS", "")
    if not servers_str:
        fallback = os.getenv("LMSTUDIO_BASE_URL") or os.getenv(
            "OPENAI_API_BASE", "http://localhost:1234/v1"
        )
        return {"default": fallback}

    server_map = {}
    for entry in servers_str.split(","):
        entry = entry.strip()
        if "=" in entry:
            name, url = entry.split("=", 1)
            server_map[name.strip()] = url.strip()
        else:
            logger.warning(f"Invalid LMSTUDIO_SERVERS entry (missing '='): {entry}")

    if server_map:
        logger.debug(f"Parsed LMSTUDIO_SERVERS: {list(server_map.keys())}")

    return server_map or {"default": "http://localhost:1234/v1"}


def get_fara_model_ids() -> List[str]:
    """
    Get priority-ordered list of acceptable Fara model IDs.

    Returns:
        List of model IDs to search for
    """
    ids_str = os.getenv("FARA_MODEL_IDS", "microsoft_fara-7b")
    return [id.strip() for id in ids_str.split(",") if id.strip()]


def _extract_base_url(server_url: str) -> str:
    """Extract base URL, removing /v1 suffix if present."""
    base = server_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base


async def probe_server(
    server_url: str, timeout: float = 2.0
) -> ServerInfo:
    """
    Probe an LM Studio server for available models.

    Uses the native /api/v0/models endpoint which returns full model
    info including state (loaded/not-loaded), type (vlm for vision), etc.

    Args:
        server_url: Server URL (e.g., http://localhost:1234/v1)
        timeout: Request timeout in seconds

    Returns:
        ServerInfo with models list and reachability status
    """
    base = _extract_base_url(server_url)
    info = ServerInfo(name="", url=server_url)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Use native LM Studio API for full model info
        native_url = f"{base}/api/v0/models"
        try:
            response = await client.get(native_url)
            response.raise_for_status()
            data = response.json()

            # Handle both {data: [...]} and [...] formats
            models_data = data.get("data", data) if isinstance(data, dict) else data

            info.models = [ModelInfo.from_dict(m) for m in models_data]
            info.reachable = True
            logger.debug(f"Probed {server_url}: {len(info.models)} models")

        except httpx.TimeoutException:
            info.error = "timeout"
            logger.debug(f"Probe timeout for {server_url}")
        except httpx.ConnectError as e:
            info.error = f"connection failed: {e}"
            logger.debug(f"Connection failed for {server_url}: {e}")
        except Exception as e:
            info.error = str(e)
            logger.debug(f"Probe failed for {server_url}: {e}")

    return info


async def discover_fara_server(
    servers: Optional[Dict[str, str]] = None,
    model_ids: Optional[List[str]] = None,
    probe_timeout: Optional[float] = None,
) -> Tuple[str, str]:
    """
    Find a server with a Fara model, preferring already-loaded models.

    Discovery phases:
    1. Find server with target model already LOADED in VRAM
    2. Find server that HAS the model (will auto-load on request)
    3. Fallback to first server + first model ID

    Args:
        servers: Server name→URL mapping (defaults to LMSTUDIO_SERVERS)
        model_ids: Acceptable model IDs (defaults to FARA_MODEL_IDS)
        probe_timeout: Timeout for probes (defaults to FARA_PROBE_TIMEOUT)

    Returns:
        Tuple of (server_url, model_id) for use with OpenAI-compatible endpoint
    """
    if servers is None:
        servers = parse_lmstudio_servers()
    if model_ids is None:
        model_ids = get_fara_model_ids()
    if probe_timeout is None:
        probe_timeout = float(os.getenv("FARA_PROBE_TIMEOUT", "2.0"))

    model_id_set = set(model_ids)
    probed_servers: Dict[str, ServerInfo] = {}

    # Probe all servers
    for name, url in servers.items():
        info = await probe_server(url, timeout=probe_timeout)
        info.name = name
        probed_servers[name] = info

    # Phase 1: Find server with model already LOADED
    for name, info in probed_servers.items():
        if not info.reachable:
            continue
        for model in info.models:
            if model.id in model_id_set and model.state == "loaded":
                # Return the /v1 URL for OpenAI-compat inference
                inference_url = _ensure_v1_url(info.url)
                logger.info(f"Found loaded model '{model.id}' on server '{name}'")
                return (inference_url, model.id)

    # Phase 2: Find server that HAS the model (not loaded)
    for name, info in probed_servers.items():
        if not info.reachable:
            continue
        for model in info.models:
            if model.id in model_id_set:
                inference_url = _ensure_v1_url(info.url)
                logger.info(
                    f"Found model '{model.id}' on server '{name}' "
                    f"(state={model.state}, will auto-load)"
                )
                return (inference_url, model.id)

    # Phase 3: Fallback
    first_url = list(servers.values())[0]
    first_model = model_ids[0]
    inference_url = _ensure_v1_url(first_url)
    logger.warning(
        f"No Fara model found on any server, "
        f"falling back to {inference_url} with {first_model}"
    )
    return (inference_url, first_model)


def _ensure_v1_url(url: str) -> str:
    """Ensure URL ends with /v1 for OpenAI-compat inference."""
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


async def get_server_status(
    servers: Optional[Dict[str, str]] = None,
    probe_timeout: Optional[float] = None,
) -> Dict[str, ServerInfo]:
    """
    Get status of all configured servers.

    Useful for diagnostics and UI display.

    Returns:
        Dict mapping server name to ServerInfo with models and status
    """
    if servers is None:
        servers = parse_lmstudio_servers()
    if probe_timeout is None:
        probe_timeout = float(os.getenv("FARA_PROBE_TIMEOUT", "2.0"))

    result = {}
    for name, url in servers.items():
        info = await probe_server(url, timeout=probe_timeout)
        info.name = name
        result[name] = info

    return result
