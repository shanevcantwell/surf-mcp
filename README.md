# Navigator MCP Server

Unified MCP server for persistent navigation across filesystem and browser domains.

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

## Installation

```bash
# Install from source
pip install -e .

# Install Playwright browsers (for browser driver)
playwright install chromium

# Optional: Install OpenAI support
pip install -e ".[openai]"
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
# Create session with browser driver
session = await mcp.call("session_create", {
    "drivers": {
        "web": {"type": "browser", "headless": True}
    }
})

# Navigate to page
await mcp.call("goto", {
    "session_id": session["session_id"],
    "driver": "web",
    "location": "https://example.com"
})

# Click element by description (visual grounding)
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

# Download content from web and save to filesystem
# (future: use transfer strategy)
```

## Configuration

Environment variables:

```bash
# Visual grounding LLM
OPENAI_API_KEY=...            # For OpenAI/LM Studio
GOOGLE_API_KEY=...            # For Gemini
NAVIGATOR_LLM_PROVIDER=openai # or gemini
NAVIGATOR_LLM_MODEL=gpt-4o    # or gemini-2.0-flash

# Browser defaults
NAVIGATOR_BROWSER_HEADLESS=true
NAVIGATOR_BROWSER_VIEWPORT_WIDTH=1920
NAVIGATOR_BROWSER_VIEWPORT_HEIGHT=1080

# Session management
NAVIGATOR_MAX_SESSIONS=10
NAVIGATOR_SESSION_TIMEOUT_SECONDS=3600

# Filesystem defaults
NAVIGATOR_FS_SANDBOX=true
```

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
