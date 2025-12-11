# Navigator MCP Server

Unified MCP server for persistent navigation across filesystem and browser domains, with visual grounding via Fara.

## Overview

Navigator provides a consistent mental model for "being somewhere and moving around" across different domains:

- **Filesystem**: Navigate directories, read/write files
- **Browser**: Navigate URLs, interact with pages via visual grounding

The key insight is that navigating a filesystem and navigating a web browser share the same fundamental model:
- You are "somewhere" (cwd, URL)
- You can move to new locations (cd, navigate)
- You can see what's at your location (ls, page content)
- You can interact with things there (read/write files, click/type)
- You maintain history of where you've been

## Features

- **Multi-driver sessions**: Combine filesystem + browser in one session
- **Visual grounding**: Click/type by natural language description (no CSS selectors)
- **Multi-server LM Studio**: Auto-discovery and failover across GPU servers
- **Session persistence**: Storage state (cookies, localStorage) round-trips through tool calls
- **Security controls**: Domain allowlists, rate limiting, sandbox enforcement

## Installation

```bash
# Install from source
pip install -e .

# Install Playwright browsers
playwright install chromium

# Optional: Install harness dependencies
pip install -e ".[harness]"
```

## Quick Start

### As MCP Server

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "navigator": {
      "command": "navigator-mcp"
    }
  }
}
```

### Docker

```bash
docker-compose up -d
```

### Fara Test Harness

Interactive UI for testing visual grounding:

```bash
cd tools/fara-harness
./run.sh    # Linux/Mac - auto-installs dependencies
run.bat     # Windows
```

See [tools/fara-harness/CHEATSHEET.md](tools/fara-harness/CHEATSHEET.md) for command reference.

## Usage Examples

### Filesystem Navigation

```python
# Create session with filesystem driver
session = await mcp.call("session_create", {
    "drivers": {
        "fs": {"type": "filesystem", "root": "./workspace", "sandbox": True}
    }
})

# Navigate and list files
await mcp.call("goto", {"session_id": session["session_id"], "driver": "fs", "location": "src"})
files = await mcp.call("list", {"session_id": session["session_id"], "driver": "fs"})

# Read a file
content = await mcp.call("read", {
    "session_id": session["session_id"],
    "driver": "fs",
    "target": "main.py"
})
```

### Browser Navigation with Visual Grounding

```python
# Create session with browser driver (with storage_state for persistence)
session = await mcp.call("session_create", {
    "drivers": {
        "web": {
            "type": "browser",
            "headless": False,
            "storage_state": saved_state  # Optional: restore cookies/localStorage
        }
    }
})

# Navigate to page
await mcp.call("goto", {
    "session_id": session["session_id"],
    "driver": "web",
    "location": "https://example.com"
})

# Click element by description (visual grounding via Fara)
await mcp.call("click", {
    "session_id": session["session_id"],
    "driver": "web",
    "description": "the blue Submit button"
})

# Type into element by description
await mcp.call("type", {
    "session_id": session["session_id"],
    "driver": "web",
    "description": "the email input field",
    "text": "user@example.com"
})

# Destroy session and capture storage_state for next time
result = await mcp.call("session_destroy", {"session_id": session["session_id"]})
saved_state = result["summary"]["web"]["storage_state"]
```

### Multi-Driver Session

```python
# Create session with both drivers
session = await mcp.call("session_create", {
    "drivers": {
        "fs": {"type": "filesystem", "root": "./downloads"},
        "web": {"type": "browser"}
    }
})
```

## Configuration

### Environment Variables

```bash
# Multi-server LM Studio (visual grounding)
LMSTUDIO_SERVERS="rtx3090=http://localhost:1234/v1,rtx8000=http://192.168.1.100:1234/v1"
FARA_MODEL_IDS="microsoft_fara-7b,fara-7b-gguf,gao-zijian/fara-7b"
FARA_MAX_FAILURES=2
FARA_PROBE_TIMEOUT=2.0

# Alternative: Single OpenAI-compatible endpoint
OPENAI_API_KEY=lm-studio
OPENAI_BASE_URL=http://localhost:1234/v1
NAVIGATOR_LLM_MODEL=microsoft_fara-7b

# Alternative: Gemini
GOOGLE_API_KEY=...
NAVIGATOR_LLM_PROVIDER=gemini
NAVIGATOR_LLM_MODEL=gemini-2.0-flash

# Browser defaults
NAVIGATOR_BROWSER_HEADLESS=true
NAVIGATOR_BROWSER_VIEWPORT_WIDTH=1920
NAVIGATOR_BROWSER_VIEWPORT_HEIGHT=1080

# Session management
NAVIGATOR_MAX_SESSIONS=10
NAVIGATOR_SESSION_TIMEOUT_SECONDS=3600

# Filesystem defaults
NAVIGATOR_FS_SANDBOX=true

# Security: Proxy for domain allowlist (Docker)
HTTPS_PROXY=http://squid:3128
```

### Multi-Server LM Studio

Navigator supports multiple LM Studio instances for redundancy and load distribution:

```bash
# Configure servers with aliases
LMSTUDIO_SERVERS="gpu1=http://localhost:1234/v1,gpu2=http://192.168.1.50:1234/v1"
```

Behavior:
- **Auto-discovery**: Probes each server's `/v1/models` to find loaded Fara model
- **Prefer loaded**: Prioritizes servers with Fara already in VRAM
- **Failover**: Automatically retries on another server if one fails
- **Multiple model IDs**: Supports priority list of acceptable model names

## MCP Tools

### Session Lifecycle
| Tool | Description |
|------|-------------|
| `session_create` | Create session with driver configuration |
| `session_destroy` | Cleanup session, returns storage_state |
| `session_list` | List active sessions |

### Universal Navigation
| Tool | Description |
|------|-------------|
| `goto` | Navigate to location (path or URL) |
| `current` | Get current location |
| `back` / `forward` | Navigate history |
| `history` | Get navigation history |

### Content Operations
| Tool | Description |
|------|-------------|
| `list` | List contents at location |
| `read` | Read content |
| `snapshot` | Capture state (screenshot or JSON) |

### Filesystem-Specific
| Tool | Description |
|------|-------------|
| `write` | Write file |
| `delete` | Delete file/directory |
| `copy` / `move` | Copy/move files |
| `find` | Search by glob pattern |

### Browser-Specific (Visual Grounding)
| Tool | Description |
|------|-------------|
| `locate` | Find element by description, return coordinates |
| `click` | Click element by description |
| `type` | Type into element by description |
| `scroll` | Scroll page up/down |
| `wait` | Wait for element or delay |

## Architecture

See [docs/](docs/) for architecture documentation and ADRs:

- [ADR-001](docs/adr/ADR-001_Security_Controls.md): Security Controls
- [ADR-002](docs/adr/ADR-002_Strategy_Architecture.md): Strategy Architecture
- [ADR-003](docs/adr/ADR-003_Fara_Test_Harness.md): Fara Test Harness
- [ADR-004](docs/adr/ADR-004_Compact_Storage_State.md): Compact Storage State

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/
```

## License

MIT
