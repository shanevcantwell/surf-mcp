# Surf MCP Architecture

**Version:** 0.4.0
**Last Updated:** 2025-12-20

---

## Overview

Surf MCP is a Model Context Protocol (MCP) server for visual browser automation via Fara. The core insight: an AI that can *see* the page doesn't need to parse HTML. Instead of brittle CSS selectors, you describe what you see ("the blue Submit button") and Fara clicks it.

```
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Client (Claude, LAS, etc.)               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ JSON-RPC over stdio
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Surf MCP Server                          │
│                         (server.py)                             │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Session Manager                        │   │
│  │               (session_manager.py)                       │   │
│  │  • Browser sessions                                      │   │
│  │  • Lifecycle: create → use → destroy                     │   │
│  │  • Pool limits and idle cleanup                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                     Browser Driver                         │ │
│  │                      (browser.py)                          │ │
│  │                                                            │ │
│  │  • URL navigation           • Visual grounding             │ │
│  │  • act() / act_autonomous   • Screenshots                  │ │
│  │  • Storage state persistence                               │ │
│  └────────────────────────────────────────────────────────────┘ │
│                          │                                      │
│           ┌──────────────┼──────────────┐                       │
│           ▼              ▼              ▼                       │
│  ┌────────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ Security       │  │ Grounder   │  │ Executor   │            │
│  │ Controls       │  │ (LLM)      │  │ (Playwright)│           │
│  │                │  │            │  │            │            │
│  │ • DomainFilter │  │ • OpenAI   │  │ • Execute  │            │
│  │ • RateLimiter  │  │ • Gemini   │  │ • Tab mgmt │            │
│  │ • AuditLogger  │  │ • Failover │  │            │            │
│  └────────────────┘  └────────────┘  └────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Abstractions

### NavigatorDriver (Abstract Base Class)

Location: `src/surf_mcp/drivers/base.py`

The interface all navigation contexts implement:

```python
class NavigatorDriver(ABC):
    driver_type: str  # "browser"
    history: List[HistoryEntry]
    history_index: int

    async def goto(self, location: str) -> NavigatorState
    async def current(self) -> str
    async def back(self) -> NavigatorState
    async def forward(self) -> NavigatorState
    async def list(self) -> List[Dict[str, Any]]
    async def read(self, target: Optional[str] = None) -> str
    async def snapshot(self) -> str
    async def cleanup(self) -> None
```

**Key Types:**

- `NavigatorState`: Result of navigation operations (location, success, snapshot, error)
- `HistoryEntry`: Single navigation history item (location, timestamp, action)

### FaraToolCall (ADR-005)

Location: `src/surf_mcp/llm/base.py`

Represents a complete Fara action decision, enabling direct execution without parsing:

```python
@dataclass
class FaraToolCall:
    action: str           # left_click, type, scroll, key, visit_url, terminate
    coordinate: Optional[Tuple[int, int]]  # (x, y) for click/type
    text: Optional[str]   # Text for type action
    direction: Optional[str]  # up/down for scroll
    pixels: Optional[int]     # Scroll amount
    url: Optional[str]        # URL for visit_url
    keys: Optional[List[str]] # Keys for key action
    confidence: float = 1.0   # 0.0-1.0
    reasoning: str = ""       # Chain-of-thought explanation
```

### ExecutionResult

Result of executing a FaraToolCall:

```python
@dataclass
class ExecutionResult:
    success: bool
    action: Optional[str]
    error: Optional[str]
    new_page: Optional[Page]  # If click opened new tab
```

### Session Manager

Location: `src/surf_mcp/session_manager.py`

Manages the lifecycle of browser sessions:

```python
class SessionManager:
    async def create_session(drivers_config: Dict) -> Session
    async def get_session(session_id: str) -> Optional[Session]
    async def destroy_session(session_id: str) -> Optional[Dict]
    async def list_sessions() -> List[Dict]
    async def cleanup_all() -> None
```

**Session Structure:**
- `session_id`: 8-character UUID prefix
- `drivers`: Dict mapping alias → NavigatorDriver instance
- `created_at`, `last_activity`: Timestamps for lifecycle management

---

## Driver Implementation

### BrowserDriver

Location: `src/surf_mcp/drivers/browser.py`

Navigates web pages via Playwright with visual grounding for element interaction.

**Key Features:**
- `headless`: Run without visible browser window
- `viewport`: Browser dimensions (default 1920x1080)
- `grounder`: Visual grounding LLM adapter
- Security controls: Domain filter, rate limiter, audit logger
- Multi-tab support with auto-switch
- Storage state persistence (cookies, localStorage)

**Operations:**
| Method | Description |
|--------|-------------|
| `goto(url)` | Navigate to URL |
| `list()` | Extract page links |
| `read(selector)` | Get text content |
| `locate(description)` | Find element by NL description |
| `click(description)` | Click element by description |
| `type(description, text)` | Type into element |
| `scroll(direction, amount)` | Scroll page |
| `wait(description, seconds)` | Wait for element/delay |
| `act(goal)` | Direct Fara execution (ADR-005) |
| `act_autonomous(goal)` | Multi-step autonomous (ADR-005) |
| `snapshot()` | Base64 PNG screenshot |

**Multi-Tab Handling:**
When a click opens a new tab (target="_blank" links), BrowserDriver automatically switches the active page to the new tab. This follows user intent for single-prompt actions.

### PlaywrightExecutor

Location: `src/surf_mcp/drivers/playwright_executor.py`

Executes FaraToolCalls directly against Playwright. A thin translation layer that runs what Fara decides.

**Supported Actions:**
| Action | Description |
|--------|-------------|
| `left_click`, `click` | Click at coordinates |
| `double_click` | Double-click at coordinates |
| `type` | Type text (click first if coords provided) |
| `scroll` | Scroll page up/down |
| `key` | Press keyboard keys |
| `visit_url` | Navigate to URL (security-checked) |
| `terminate` | Task complete signal |
| `wait` | Wait for network idle |

**New Tab Detection:**
Tracks pages before/after click to detect new tabs. Returns `new_page` in ExecutionResult for BrowserDriver to switch.

### AgentRunner

Location: `src/surf_mcp/drivers/agent_runner.py`

Autonomous multi-step Fara execution with progress streaming.

**Flow:**
```
Goal → Screenshot → Fara → Execute → Repeat → (terminate) → Done
```

**Features:**
- MCP progress notifications via callback
- Cancellation support between steps
- Configurable max steps (FARA_MAX_AGENT_STEPS, default 20)
- Step history tracking (AgentStep records)

---

## Visual Grounding

Location: `src/surf_mcp/llm/`

Visual grounding enables natural language element location ("the blue Submit button") instead of brittle CSS selectors.

### VisualGrounder Interface

```python
class VisualGrounder(ABC):
    async def locate(description: str, screenshot_b64: str) -> LocateResult
    async def verify(description: str, screenshot_b64: str) -> LocateResult
    async def get_action(goal: str, screenshot_b64: str) -> FaraToolCall
```

The key method is `get_action()` (ADR-005) which returns a complete FaraToolCall rather than just coordinates.

### Adapters

**OpenAIVisualGrounder** (`openai_adapter.py`):
- Primary adapter for OpenAI API or LM Studio (Fara-7B)
- Resolution scaling for vision model native resolutions
- JSON extraction from multiple response formats

**GeminiVisualGrounder** (`gemini_adapter.py`):
- Google Gemini API integration
- Async execution via run_in_executor

### Multi-Server LM Studio

Location: `src/surf_mcp/llm/lmstudio_discovery.py`, `factory.py`

**Server Discovery:**
- Probes each configured LM Studio server's `/v1/models` endpoint
- Prioritizes servers with Fara already loaded in VRAM
- Supports multiple model ID variants

**FailoverGrounder:**
- Wraps adapters with automatic retry logic
- On failure, tries next server/model combination
- Transparent to callers - they just call `locate()` or `get_action()`

**Configuration:**
```bash
LMSTUDIO_SERVERS="rtx3090=http://localhost:1234/v1,rtx8000=http://192.168.1.100:1234/v1"
FARA_MODEL_IDS="microsoft_fara-7b,fara-7b-gguf"
FARA_MAX_FAILURES=2
FARA_PROBE_TIMEOUT=2.0
```

---

## Security Controls

Location: `src/surf_mcp/security/`

Per ADR-001 Phase 1, browser automation includes security controls.

### DomainFilter

URL allowlist/blocklist with sensible defaults:

```python
filter = DomainFilter(
    allowed_domains=["example.com", "*.google.com"],
    blocked_domains=["accounts.google.com"]
)
allowed, reason = filter.check("https://www.google.com/search")
```

**Default Blocklist:**
- `*.bank.com`, `*.paypal.com`, `paypal.com`
- `accounts.google.com`, `login.microsoftonline.com`
- `*.stripe.com`, `stripe.com`

Blocklist takes precedence over allowlist (defense in depth).

### RateLimiter

Token bucket limiting for browser actions:

```python
limiter = RateLimiter(max_per_minute=30)
if limiter.allow():
    # Perform action
else:
    # Rate limited
```

Prevents runaway automation loops.

### AuditLogger

Forensic logging for security monitoring:

```python
logger = AuditLogger(session_id="abc123")
logger.log("click", {"description": "Submit"}, "success", screenshot_b64, llm_response)
```

**AuditEvent Fields:**
- `timestamp`, `session_id`, `action`, `details`
- `outcome`: success, failed, blocked, rate_limited
- `screenshot_hash`: SHA256 of screenshot used
- `llm_response`: Raw grounding result for forensics

---

## MCP Commands

Location: `src/surf_mcp/commands/`

### Session Lifecycle (`session.py`)
- `session_create`: Create session with driver configuration
- `session_destroy`: Cleanup session, returns storage_state
- `session_list`: List active sessions

### Navigation (`navigation.py`)
- `goto`: Navigate to URL
- `current`: Get current URL
- `back`: Navigate back in history
- `forward`: Navigate forward in history
- `history`: Get navigation history

### Content Operations (`content.py`)
- `list`: Extract page links
- `read`: Read page text content
- `snapshot`: Capture screenshot (base64 PNG)

### Visual Grounding (`browser.py`)
- `locate`: Find element by description
- `click`: Click element by description
- `type`: Type into element by description
- `scroll`: Scroll page
- `wait`: Wait for element or delay
- `act`: Direct Fara execution - Fara decides the action (ADR-005)
- `act_autonomous`: Multi-step autonomous execution until task complete

---

## Data Flow

### Browser Session

```
1. Client → session_create({drivers: {web: {type: browser, headless: false}}})
2. Server creates BrowserDriver with Playwright
3. Client → goto({session_id, driver: web, location: "https://example.com"})
4. BrowserDriver navigates, takes screenshot
5. Client → act({session_id, driver: web, goal: "click Sign In"})
6. BrowserDriver → Fara → PlaywrightExecutor → result
7. Client → session_destroy({session_id})
8. Server returns {summary: {web: {storage_state: {...}}}}
```

### Direct Fara Execution (ADR-005)

```
1. Client → act({session_id, driver: web, goal: "click the search button"})
2. BrowserDriver takes screenshot
3. BrowserDriver calls grounder.get_action(goal, screenshot)
4. VisualGrounder (Fara) analyzes screenshot + goal
5. Fara returns FaraToolCall{action="left_click", coordinate=(624,280), confidence=0.95}
6. PlaywrightExecutor.execute(tool_call, page) runs the click
7. If click opened new tab → BrowserDriver switches to new tab
8. BrowserDriver returns result with action details and screenshot
```

### Autonomous Agent Execution

```
1. Client → act_autonomous({session_id, driver: web, goal: "find and download the PDF"})
2. AgentRunner initializes with grounder + executor
3. Loop until terminate or max_steps:
   a. Take screenshot
   b. Send to Fara with goal context
   c. Fara returns FaraToolCall with next action
   d. If action == "terminate" → task complete, exit loop
   e. PlaywrightExecutor.execute() runs action
   f. Emit progress notification to client
4. Return AgentResult with full step history
```

---

## Fara Test Harness

Location: `tools/fara-harness/`

Interactive UI for testing and developing visual grounding capabilities.

### Architecture

```
User Input → Streamlit UI → MCP Client → surf-mcp → Fara → Result
                  ↓
            Visual Overlay + History
```

**Key Design:** All commands go directly to Fara via `act()` without parsing or manipulation. The harness doesn't interpret commands - Fara decides what action to take.

### Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit web UI (main application) |
| `mcp_client.py` | MCP SDK wrapper (async + sync) |
| `utils.py` | Image processing and storage state |
| `run.sh`, `run.bat` | Startup scripts with dependency checking |
| `CHEATSHEET.md` | Quick reference guide |

### Features

- **Visual overlay**: Red dot + crosshairs + confidence score on locate
- **Session persistence**: Storage state saved on disconnect, restored on reconnect
- **History tracking**: Scrollable log of commands and results
- **Direct navigation**: `goto` and `scroll` buttons for quick navigation

### Quick Reference

| Command | Purpose |
|---------|---------|
| `locate "description"` | Find element, show coordinates + confidence |
| `click "description"` | Click element by natural language |
| `type "description" text` | Type into field |
| `goto https://example.com` | Navigate to URL |
| `scroll up / scroll down` | Scroll by viewport height |

See [tools/fara-harness/CHEATSHEET.md](../tools/fara-harness/CHEATSHEET.md) for full reference.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SURF_LLM_PROVIDER` | `openai` | Visual grounding provider (openai, gemini) |
| `SURF_LLM_MODEL` | `gpt-4o` | Model for visual grounding |
| `OPENAI_API_KEY` | - | OpenAI/LM Studio API key |
| `OPENAI_BASE_URL` | OpenAI URL | API endpoint (LM Studio: `http://localhost:1234/v1`) |
| `GOOGLE_API_KEY` | - | Gemini API key |
| `LMSTUDIO_SERVERS` | - | Multi-server format: `name1=url1,name2=url2` |
| `FARA_MODEL_IDS` | `microsoft_fara-7b` | Priority-ordered model IDs (comma-separated) |
| `FARA_MAX_FAILURES` | `2` | Max retries before failover |
| `FARA_PROBE_TIMEOUT` | `2.0` | Server discovery timeout (seconds) |
| `FARA_MIN_CONFIDENCE` | `0.7` | Retry threshold for low confidence |
| `FARA_CONFIDENCE_RETRIES` | `2` | Max retries for low confidence actions |
| `FARA_MAX_AGENT_STEPS` | `20` | Max steps in autonomous mode |
| `SURF_BROWSER_HEADLESS` | `true` | Browser visibility |
| `SURF_BROWSER_VIEWPORT_WIDTH` | `1920` | Viewport width |
| `SURF_BROWSER_VIEWPORT_HEIGHT` | `1080` | Viewport height |
| `SURF_MAX_SESSIONS` | `10` | Maximum concurrent sessions |
| `SURF_SESSION_TIMEOUT_SECONDS` | `3600` | Idle session timeout |
| `HTTPS_PROXY` / `HTTP_PROXY` | - | Proxy for domain allowlist (Docker) |

---

## File Structure

```
surf-mcp/
├── src/surf_mcp/
│   ├── __init__.py              # Package exports (version 0.4.0)
│   ├── server.py                # MCP server entrypoint
│   ├── session_manager.py       # Session lifecycle
│   ├── drivers/
│   │   ├── __init__.py
│   │   ├── base.py              # NavigatorDriver ABC
│   │   ├── browser.py           # BrowserDriver with visual grounding
│   │   ├── playwright_executor.py  # Direct Fara action execution (ADR-005)
│   │   └── agent_runner.py      # Autonomous multi-step execution (ADR-005)
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── session.py           # Session lifecycle commands
│   │   ├── navigation.py        # Navigation commands
│   │   ├── content.py           # Content operations
│   │   ├── browser.py           # Browser commands (incl. act, act_autonomous)
│   │   └── utils.py             # Shared utilities
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py              # VisualGrounder ABC, FaraToolCall, ExecutionResult
│   │   ├── openai_adapter.py    # OpenAI/LM Studio adapter
│   │   ├── gemini_adapter.py    # Gemini adapter
│   │   ├── factory.py           # VisualGrounderFactory, FailoverGrounder
│   │   ├── lmstudio_discovery.py  # Multi-server discovery
│   │   └── json_utils.py        # JSON extraction from LLM responses
│   └── security/
│       ├── __init__.py
│       ├── domain_filter.py     # URL allowlist/blocklist (ADR-001)
│       ├── rate_limiter.py      # Token bucket limiting (ADR-001)
│       └── audit.py             # Action logging (ADR-001)
├── tools/
│   └── fara-harness/            # Interactive test harness
│       ├── app.py               # Streamlit UI
│       ├── mcp_client.py        # MCP SDK wrapper
│       ├── utils.py             # Image and storage utilities
│       ├── run.sh, run.bat      # Startup scripts
│       └── CHEATSHEET.md        # Quick reference
├── tests/
│   ├── conftest.py              # Fixtures
│   ├── test_session_manager.py
│   ├── test_fara_integration.py
│   ├── test_llm_factory.py
│   └── test_security_controls.py
├── docs/
│   ├── ARCHITECTURE.md          # This file
│   ├── TEST_SUMMARY.md          # Auto-generated test summary
│   └── adr/
│       ├── ADR-001_Agentic_Browser_Security.md  # Phase 1 Complete
│       ├── ADR-002_Strategy_Architecture.md     # Proposed
│       ├── ADR-004_Compact_Storage_State.md     # Deferred
│       └── complete/
│           ├── ADR-003_Fara_Test_Harness.md     # Complete
│           └── ADR-005_Direct_Fara_Execution.md # Complete
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── CLAUDE.md
└── README.md
```

---

## Extension Points

### Adding a New Visual Grounder

1. Create adapter in `llm/` inheriting from `VisualGrounder`
2. Implement `locate()`, `verify()`, and `get_action()` methods
3. Add to `llm/__init__.py` exports
4. Update `VisualGrounderFactory.create()` to handle new provider

---

## Security Considerations

See [ADR-001: Agentic Browser Security](adr/ADR-001_Agentic_Browser_Security.md) for detailed security analysis.

**Implemented (Phase 1):**
- Domain allowlist/blocklist with sensible defaults
- Rate limiting (30 actions/minute)
- Audit logging with screenshot hashing
- Session isolation (separate BrowserContext per session)

**Planned (Phase 2+):**
- Squid proxy for network-level enforcement
- Sensitive action confirmation
- Screenshot sanitization
- Behavioral anomaly detection
