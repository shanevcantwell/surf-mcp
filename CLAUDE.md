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

#### Fara Output Format (ADR-005)
Fara returns tool_calls in this format:
```json
{
  "name": "computer_use",
  "arguments": {
    "action": "left_click",
    "coordinate": [624, 280],
    "reasoning": "The search button is a blue element..."
  }
}
```

Available actions: `left_click`, `double_click`, `type`, `scroll`, `key`, `visit_url`, `terminate`, `wait`

#### FaraToolCall Data Model
The `FaraToolCall` dataclass preserves Fara's full action context:
- `action`: Action type (left_click, type, scroll, etc.)
- `coordinate`: (x, y) pixel coordinates
- `text`: Text to type (for type action)
- `direction`: Scroll direction (up/down)
- `keys`: Keys to press (for key action)
- `confidence`: Model confidence (0.0-1.0)
- `reasoning`: Fara's chain-of-thought explanation

### Multi-Server LM Studio Support
Supports multiple LM Studio instances across different GPUs/machines:
- **Server Discovery**: Probes each server's `/v1/models` manifest
- **Prefer Loaded**: Prioritizes servers with Fara already loaded in VRAM
- **Fallback**: Sequential retry across servers on failure
- **Multiple Model IDs**: Supports priority list of acceptable Fara model variants

Configure in `.env`:
```bash
LMSTUDIO_SERVERS="rtx3090=http://localhost:1234/v1,rtx8000=http://192.168.137.2:1234/v1"
FARA_MODEL_IDS="microsoft_fara-7b,fara-7b-gguf,gao-zijian/fara-7b"
FARA_MAX_FAILURES=2
FARA_PROBE_TIMEOUT=2.0
```

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
pytest                    # All tests (skips unavailable)
pytest -m "not live"      # Skip LLM tests (for CI)
pytest -m live -v -s      # Only live LLM tests
pytest -m integration     # MCP transport tests
pytest -m browser         # Playwright browser tests
mypy src/
```

#### Test Categories
| Marker | Description | External Deps |
|--------|-------------|---------------|
| (none) | Unit tests - mocked | None |
| `integration` | MCP client/server transport | MCP server |
| `browser` | Playwright browser automation | Chromium |
| `live` | Real LLM API calls | LM Studio / Gemini |

Skip reasons use prefixes:
- `ENVIRONMENT:` - Missing dependency (install something)
- `FRAMEWORK:` - Test harness limitation (known issue)

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

### Core
- `src/navigator_mcp/server.py` - MCP entrypoint
- `src/navigator_mcp/session_manager.py` - Session lifecycle

### Drivers
- `src/navigator_mcp/drivers/base.py` - NavigatorDriver interface
- `src/navigator_mcp/drivers/filesystem.py` - FileSystemDriver with sandbox enforcement
- `src/navigator_mcp/drivers/browser.py` - BrowserDriver with visual grounding
- `src/navigator_mcp/drivers/playwright_executor.py` - Direct Fara action execution (ADR-005)
- `src/navigator_mcp/drivers/agent_runner.py` - Autonomous multi-step execution (ADR-005)

### LLM Adapters
- `src/navigator_mcp/llm/base.py` - VisualGrounder ABC, FaraToolCall dataclass
- `src/navigator_mcp/llm/openai_adapter.py` - OpenAI/LM Studio visual grounder
- `src/navigator_mcp/llm/gemini_adapter.py` - Google Gemini visual grounder
- `src/navigator_mcp/llm/factory.py` - FailoverGrounder with multi-server support
- `src/navigator_mcp/llm/lmstudio_discovery.py` - Multi-server LM Studio discovery
- `src/navigator_mcp/llm/json_utils.py` - JSON extraction from LLM responses

### Utilities
- `src/navigator_mcp/commands/utils.py` - Shared driver retrieval and validation
- `scripts/summarize_tests.py` - Generate test suite summary

### Test Harness
- `tools/fara-harness/app.py` - Streamlit UI for Fara testing
- `tools/fara-harness/mcp_client.py` - MCP client wrapper
- `tools/fara-harness/utils.py` - Image utilities (storage state, overlays)

**Architecture:** All user commands go directly to Fara via `act()` without parsing or manipulation. The harness does not interpret commands - Fara decides what action to take.

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
- `act` - Direct Fara execution (Fara decides the action) (ADR-005)
- `act_autonomous` - Multi-step autonomous execution (ADR-005)

---

## Open Questions

### How should clicks that open new tabs be handled?

**Context:** Many sites (Google News, search results, etc.) use `target="_blank"` links. When Fara clicks these, the browser opens a new tab but the harness continues showing the original page.

**Current behavior:** PlaywrightExecutor detects new tabs and waits for them to load, but doesn't switch the active page. The screenshot refresh shows the original tab.

**Options to consider:**

1. **Auto-switch to new tab** - When a click opens a new tab, automatically make it the active page for future operations. Pro: Follows user intent. Con: May lose context of original page.

2. **Return new tab info in result** - Include `{"new_tab_opened": true, "new_tab_url": "..."}` in the action result so the caller can decide. Pro: Explicit control. Con: More complexity for caller.

3. **Multi-tab awareness** - Add tab management commands (`list_tabs`, `switch_tab`, `close_tab`). Pro: Full control. Con: Significant new surface area.

4. **Modifier for link behavior** - Add option like `{"follow_links_in_same_tab": true}` to force same-tab navigation. Pro: Predictable. Con: May not work with all sites/JS.

5. **Let Fara handle it** - If user says "click the article and read it", Fara should recognize the new tab and operate there. Pro: Natural. Con: Requires Fara to understand multi-tab context.

**Question:** What's the right abstraction? The Navigator model assumes "one location" - does multi-tab break that?
