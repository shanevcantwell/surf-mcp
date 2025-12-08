# Navigator MCP Server

**Purpose:** Unified MCP server for persistent context navigation across filesystem and browser domains.

---

## Core Concepts

### The Navigator Abstraction
Navigator provides a consistent mental model for "being somewhere and moving around":
- **Location**: Where you are (cwd, URL)
- **Navigation**: Moving to new locations (goto, back, forward)
- **Content**: What's at your location (list, read, snapshot)
- **Interaction**: Acting on things there (write, click, type)
- **History**: Where you've been

### Multi-Driver Sessions
Sessions can contain multiple drivers (e.g., filesystem + browser), enabling cross-domain workflows like downloading web content to local files.

### Visual Grounding (Browser)
The browser driver uses multimodal LLMs (Fara-7B via LM Studio, or Gemini/GPT-4V) to locate UI elements by natural language description instead of brittle CSS selectors.

---

## Installation & Running

### Docker Compose (Recommended)
The project is designed to run via Docker Compose, which provides:
- Isolated container environment
- Squid proxy for network-level domain whitelisting (security)
- Consistent cross-platform execution

```bash
docker compose up
```

### Direct Installation (Development)
Install from pyproject.toml:
```bash
pip install -e ".[dev]"
playwright install chromium
```

Run the MCP server:
```bash
python -m navigator_mcp
```

---

## Development Directives

### Testing
```bash
pip install -e ".[dev]"
playwright install chromium
pytest
mypy src/
```

### Adding a New Driver

1. Create class in `src/navigator_mcp/drivers/`
2. Inherit from `NavigatorDriver`
3. Implement all abstract methods
4. Register in `drivers/__init__.py`
5. Add driver-specific commands if needed

### Adding a New Strategy

1. Create in `src/navigator_mcp/strategies/{domain}/`
2. Inherit from `BaseStrategy`
3. Implement `execute()` method
4. Register in `strategies/__init__.py`

---

## Architecture Notes

### Session Isolation
Each session is independent. Multiple drivers within a session can share data via the strategy engine but not with other sessions.

### Sandbox Enforcement
FileSystem driver respects root boundary by default. Cannot navigate above root unless `sandbox=false`.

### Error Handling
Commands return structured results with success/error fields. Never raise exceptions across MCP boundary.

---

## Key Files

- `src/navigator_mcp/server.py` - MCP entrypoint
- `src/navigator_mcp/session_manager.py` - Session lifecycle
- `src/navigator_mcp/drivers/base.py` - NavigatorDriver interface
- `src/navigator_mcp/drivers/filesystem.py` - FileSystemDriver
- `src/navigator_mcp/drivers/browser.py` - BrowserDriver with visual grounding
- `src/navigator_mcp/llm/` - Visual grounding LLM adapters (OpenAI/Gemini)

---

## MCP Commands

### Session Lifecycle
- `session_create` - Create session with drivers
- `session_destroy` - Cleanup session
- `session_list` - List active sessions

### Universal Navigation
- `goto` - Navigate to location
- `current` - Get current location
- `back` / `forward` - Navigate history
- `history` - Get navigation history

### Content Operations
- `list` - List contents at location
- `read` - Read content
- `snapshot` - Capture state (screenshot or JSON)

### Filesystem-Specific
- `write` - Write file
- `delete` - Delete file/directory
- `copy` / `move` - Copy/move files
- `find` - Search by glob pattern

### Browser-Specific (Visual Grounding)
- `locate` - Find element by description
- `click` - Click element by description
- `type` - Type into element by description
- `scroll` - Scroll page
- `wait` - Wait for element or delay
