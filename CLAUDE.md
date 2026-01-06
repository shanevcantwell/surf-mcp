# Surf MCP Server

**Purpose:** MCP server for visual browser automation via Fara.

**Version:** 0.5.0

---

## Core Concepts

### Visual Grounding
Surf uses multimodal LLMs (Fara-7B via LM Studio, or Gemini/GPT-4V) to locate UI elements by natural language description instead of brittle CSS selectors.

An AI that can *see* the page doesn't need to parse HTML.

### Direct Fara Execution (ADR-005)
Fara returns complete tool_calls, not just coordinates. We execute what Fara decides:

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

### FaraToolCall Data Model
The `FaraToolCall` dataclass preserves Fara's full action context:
- `action`: Action type (left_click, type, scroll, etc.)
- `coordinate`: (x, y) pixel coordinates
- `text`: Text to type (for type action)
- `direction`: Scroll direction (up/down)
- `pixels`: Scroll amount in pixels
- `url`: URL to navigate to (for visit_url action)
- `keys`: Keys to press (for key action)
- `delete_existing_text`: Clear field before typing (Ctrl+A, Delete)
- `press_enter`: Press Enter after typing
- `confidence`: Model confidence (0.0-1.0)
- `reasoning`: Fara's chain-of-thought explanation

### Multi-Server LM Studio Support
Supports multiple LM Studio instances across different GPUs/machines:
- **Server Discovery**: Probes each server's `/v1/models` manifest
- **Prefer Loaded**: Prioritizes servers with Fara already loaded in VRAM
- **Fallback**: Sequential retry across servers on failure

Configure in `.env`:
```bash
LMSTUDIO_SERVERS="rtx3090=http://localhost:1234/v1,rtx8000=http://192.168.137.2:1234/v1"
FARA_MODEL_IDS="microsoft_fara-7b,fara-7b-gguf,gao-zijian/fara-7b"
FARA_MAX_FAILURES=2
FARA_PROBE_TIMEOUT=2.0
```

### Autonomous Mode (ADR-006)
Multi-step execution via `act_autonomous` with:
- **Multi-screenshot context**: Last N screenshots sent to Fara for visual continuity
- **ReAct history**: Text-based action history with success/failure markers
- **Configurable steps**: Adjust `FARA_MAX_AGENT_STEPS` for complex flows

Configure in `.env`:
```bash
FARA_MAX_AGENT_STEPS=20          # Max steps before giving up
FARA_CONTEXT_SCREENSHOTS=3       # Screenshots in context (default 3)
# FARA_SYSTEM_PROMPT_FILE=/path/to/prompt.txt  # Override system prompt
```

**Known limitations**: Date pickers with multiple dropdowns may struggle. Use specific instructions or break into smaller steps.

---

## Installation & Running

### Docker (Recommended)
```bash
docker compose up
```

### Direct Installation (Development)
```bash
pip install -e ".[dev]"
playwright install chromium
surf-mcp  # Run the server
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

---

## Architecture Notes

### Session Isolation
Each session is independent with its own browser context.

### Security Controls (ADR-001)
- **DomainFilter**: URL allowlist/blocklist with sensible defaults
- **RateLimiter**: Token bucket limiting (30 actions/minute)
- **AuditLogger**: Forensic logging with screenshot hashing

### Error Handling
Commands return structured results with success/error fields. Never raise exceptions across MCP boundary.

---

## Key Files

### Core
- `src/surf_mcp/server.py` - MCP entrypoint
- `src/surf_mcp/session_manager.py` - Session lifecycle

### Drivers
- `src/surf_mcp/drivers/base.py` - NavigatorDriver interface
- `src/surf_mcp/drivers/browser.py` - BrowserDriver with visual grounding
- `src/surf_mcp/drivers/playwright_executor.py` - Direct Fara action execution (ADR-005)
- `src/surf_mcp/drivers/agent_runner.py` - Autonomous multi-step execution (ADR-005)

### LLM Adapters
- `src/surf_mcp/llm/base.py` - VisualGrounder ABC, FaraToolCall dataclass
- `src/surf_mcp/llm/openai_adapter.py` - OpenAI/LM Studio visual grounder
- `src/surf_mcp/llm/gemini_adapter.py` - Google Gemini visual grounder
- `src/surf_mcp/llm/factory.py` - FailoverGrounder with multi-server support
- `src/surf_mcp/llm/lmstudio_discovery.py` - Multi-server LM Studio discovery
- `src/surf_mcp/llm/json_utils.py` - JSON extraction from LLM responses

### Security
- `src/surf_mcp/security/domain_filter.py` - URL allowlist/blocklist
- `src/surf_mcp/security/rate_limiter.py` - Token bucket rate limiting
- `src/surf_mcp/security/audit.py` - Action logging

### Test Harness
- `tools/fara-harness/app.py` - Streamlit UI for Fara testing
- `tools/fara-harness/mcp_client.py` - MCP client wrapper
- `tools/fara-harness/utils.py` - Image utilities (storage state, overlays)

**Architecture:** All user commands go directly to Fara via `act()` without parsing or manipulation. The harness does not interpret commands - Fara decides what action to take.

---

## MCP Commands

### Session Lifecycle
- `session_create` - Create browser session
- `session_destroy` - Cleanup session
- `session_list` - List active sessions

### Navigation
- `goto` - Navigate to URL
- `current` - Get current URL
- `back` / `forward` - Navigate history
- `history` - Get navigation history

### Content Operations
- `list` - Extract page links
- `read` - Read page content
- `snapshot` - Capture screenshot

### Visual Grounding
- `locate` - Find element by description
- `click` - Click element by description
- `type` - Type into element by description
- `scroll` - Scroll page
- `wait` - Wait for element or delay
- `act` - Direct Fara execution (Fara decides the action)
- `act_autonomous` - Multi-step autonomous execution

---

## Design Decisions

### Multi-Tab Handling

**Decision:** Auto-switch to new tab when click opens one.

When a `target="_blank"` link opens a new tab, BrowserDriver automatically switches the active page to the new tab. This follows user intent for single-prompt single-action calls.

**Implementation:** PlaywrightExecutor returns `new_page` in ExecutionResult when a click opens a new tab. BrowserDriver updates `self._page` to the new tab.

### Browser-Only Scope

**Decision:** Focus exclusively on browser automation, no filesystem operations.

Filesystem is already solved by `filesystem-mcp`. Our differentiator is visual grounding via Fara - that's the unique value. A focused scope means:
- Simpler codebase
- Easier to support as open source
- Clear value proposition
