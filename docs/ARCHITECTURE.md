# Navigator MCP Architecture

**Version:** 0.1.0
**Last Updated:** 2025-12-08

---

## Overview

Navigator MCP is a unified Model Context Protocol (MCP) server providing persistent, session-based navigation across multiple domains. The core abstraction treats navigation uniformly whether the context is a filesystem or a web browser.

```
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Client (LAS, prompt-prix)                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ JSON-RPC over stdio
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Navigator MCP Server                       │
│                         (server.py)                             │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Session Manager                        │   │
│  │               (session_manager.py)                       │   │
│  │  • Multi-driver sessions                                 │   │
│  │  • Lifecycle: create → use → destroy                     │   │
│  │  • Pool limits and idle cleanup                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────┐  ┌──────────────────────┐            │
│  │   FileSystem Driver  │  │    Browser Driver    │            │
│  │   (filesystem.py)    │  │    (browser.py)      │            │
│  │                      │  │                      │            │
│  │  • cwd navigation    │  │  • URL navigation    │            │
│  │  • File read/write   │  │  • Visual grounding  │            │
│  │  • Directory listing │  │  • Click/type/scroll │            │
│  │  • Sandbox boundary  │  │  • Screenshots       │            │
│  └──────────────────────┘  └──────────────────────┘            │
│                                   │                             │
│                                   ▼                             │
│                    ┌──────────────────────┐                     │
│                    │   Visual Grounder    │                     │
│                    │   (llm/adapters)     │                     │
│                    │                      │                     │
│                    │  • OpenAI/LM Studio  │                     │
│                    │  • Gemini            │                     │
│                    └──────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Abstractions

### NavigatorDriver (Abstract Base Class)

Location: `src/navigator_mcp/drivers/base.py`

The unified interface all navigation contexts implement:

```python
class NavigatorDriver(ABC):
    driver_type: str  # "filesystem" or "browser"
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

### Session Manager

Location: `src/navigator_mcp/session_manager.py`

Manages the lifecycle of multi-driver sessions:

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

## Driver Implementations

### FileSystemDriver

Location: `src/navigator_mcp/drivers/filesystem.py`

Navigates local filesystem with optional sandbox enforcement.

**Key Features:**
- `root`: Base directory for navigation
- `cwd`: Current working directory (starts at root)
- `sandbox`: If True, prevents navigation above root
- File tracking: `files_read`, `files_written` for session summary

**Operations:**
| Method | Description |
|--------|-------------|
| `goto(path)` | Change directory |
| `list()` | Directory contents with metadata |
| `read(filename)` | Read file content |
| `write(filename, content)` | Write file |
| `delete(target, recursive)` | Delete file/directory |
| `copy(src, dst)` | Copy file/directory |
| `move(src, dst)` | Move/rename |
| `find(pattern, recursive)` | Glob search |
| `snapshot()` | JSON directory listing |

### BrowserDriver

Location: `src/navigator_mcp/drivers/browser.py`

Navigates web pages via Playwright with visual grounding for element interaction.

**Key Features:**
- `headless`: Run without visible browser window
- `viewport`: Browser dimensions (default 1920x1080)
- `grounder`: Visual grounding LLM adapter
- Screenshot tracking for session summary

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
| `snapshot()` | Base64 PNG screenshot |

---

## Visual Grounding

Location: `src/navigator_mcp/llm/`

Visual grounding enables natural language element location ("the blue Submit button") instead of brittle CSS selectors.

### VisualGrounder Interface

```python
class VisualGrounder(ABC):
    async def locate(description: str, screenshot_b64: str) -> LocateResult
    async def verify(description: str, screenshot_b64: str) -> LocateResult
```

**LocateResult:**
- `found`: Boolean
- `x`, `y`: Pixel coordinates (center of element)
- `confidence`: 0.0-1.0
- `reasoning`: LLM's explanation

### Adapters

**OpenAIVisualGrounder** (`openai_adapter.py`):
- Primary adapter for OpenAI API or LM Studio (Fara-7B)
- Resolution scaling for vision model native resolutions
- Handles multiple response formats (JSON, tool_call XML)

**GeminiVisualGrounder** (`gemini_adapter.py`):
- Google Gemini API integration
- Async execution via run_in_executor

---

## MCP Commands

Location: `src/navigator_mcp/commands/`

17 tools exposed via MCP protocol:

### Session Lifecycle (`session.py`)
- `session_create`: Create session with driver configuration
- `session_destroy`: Cleanup session and drivers
- `session_list`: List active sessions

### Universal Navigation (`navigation.py`)
- `goto`: Navigate to location
- `current`: Get current location
- `back`: Navigate back in history
- `forward`: Navigate forward in history
- `history`: Get navigation history

### Content Operations (`content.py`)
- `list`: List contents at location
- `read`: Read content (file or page text)
- `snapshot`: Capture state (JSON or screenshot)

### Filesystem-Specific (`filesystem.py`)
- `write`: Write file content
- `delete`: Delete file/directory
- `copy`: Copy file/directory
- `move`: Move/rename file/directory
- `find`: Search by glob pattern

### Browser-Specific (`browser.py`)
- `locate`: Find element by description
- `click`: Click element by description
- `type`: Type into element by description
- `scroll`: Scroll page
- `wait`: Wait for element or delay

---

## Data Flow

### Typical Filesystem Session

```
1. Client → session_create({drivers: {fs: {type: filesystem, root: /workspace}}})
2. Server creates FileSystemDriver with root=/workspace
3. Client → goto({session_id, driver: fs, location: src})
4. FileSystemDriver changes cwd to /workspace/src
5. Client → list({session_id, driver: fs})
6. FileSystemDriver returns directory entries
7. Client → read({session_id, driver: fs, target: main.py})
8. FileSystemDriver reads /workspace/src/main.py
9. Client → session_destroy({session_id})
10. Server cleans up, returns summary of files_read/files_written
```

### Typical Browser Session with Visual Grounding

```
1. Client → session_create({drivers: {web: {type: browser, headless: true}}})
2. Server creates BrowserDriver, launches Playwright
3. Client → goto({session_id, driver: web, location: https://example.com})
4. BrowserDriver navigates, returns screenshot
5. Client → click({session_id, driver: web, description: "the login button"})
6. BrowserDriver:
   a. Takes screenshot
   b. Sends to VisualGrounder with description
   c. VisualGrounder (LLM) returns coordinates
   d. BrowserDriver clicks at coordinates
   e. Returns post-click screenshot
7. Client → session_destroy({session_id})
8. Server closes browser, returns summary
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NAVIGATOR_LLM_PROVIDER` | `openai` | Visual grounding provider |
| `NAVIGATOR_LLM_MODEL` | `gpt-4o` | Model for visual grounding |
| `OPENAI_API_KEY` | - | OpenAI/LM Studio API key |
| `OPENAI_API_BASE` | OpenAI URL | API endpoint (LM Studio: `http://localhost:1234/v1`) |
| `GOOGLE_API_KEY` | - | Gemini API key |
| `NAVIGATOR_BROWSER_HEADLESS` | `true` | Browser visibility |
| `NAVIGATOR_BROWSER_VIEWPORT_WIDTH` | `1920` | Viewport width |
| `NAVIGATOR_BROWSER_VIEWPORT_HEIGHT` | `1080` | Viewport height |
| `NAVIGATOR_MAX_SESSIONS` | `10` | Maximum concurrent sessions |
| `NAVIGATOR_SESSION_TIMEOUT_SECONDS` | `3600` | Idle session timeout |
| `NAVIGATOR_FS_SANDBOX` | `true` | Filesystem sandbox default |

---

## File Structure

```
navigator-mcp/
├── src/navigator_mcp/
│   ├── __init__.py              # Package exports
│   ├── server.py                # MCP server entrypoint
│   ├── session_manager.py       # Session lifecycle
│   ├── drivers/
│   │   ├── __init__.py
│   │   ├── base.py              # NavigatorDriver ABC
│   │   ├── filesystem.py        # FileSystemDriver
│   │   └── browser.py           # BrowserDriver
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── session.py           # Session lifecycle commands
│   │   ├── navigation.py        # Universal navigation
│   │   ├── content.py           # Content operations
│   │   ├── filesystem.py        # FS-specific commands
│   │   └── browser.py           # Browser-specific commands
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py              # VisualGrounder ABC
│   │   ├── openai_adapter.py    # OpenAI/LM Studio adapter
│   │   └── gemini_adapter.py    # Gemini adapter
│   └── strategies/              # (scaffolded, not implemented)
│       ├── browser/
│       ├── filesystem/
│       └── cross/
├── tests/
│   ├── conftest.py              # Fixtures
│   ├── test_session_manager.py
│   └── drivers/
│       └── test_filesystem.py
├── docs/
│   ├── ARCHITECTURE.md          # This file
│   └── adr/
│       └── ADR-001_Agentic_Browser_Security.md
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── CLAUDE.md
└── README.md
```

---

## Extension Points

### Adding a New Driver

1. Create class in `drivers/` inheriting from `NavigatorDriver`
2. Implement all abstract methods
3. Add to `drivers/__init__.py` exports
4. Update `SessionManager._create_driver()` to handle new type
5. Add driver-specific commands if needed in `commands/`

### Adding a New Visual Grounder

1. Create adapter in `llm/` inheriting from `VisualGrounder`
2. Implement `locate()` and `verify()` methods
3. Add to `llm/__init__.py` exports
4. Update `SessionManager._get_visual_grounder()` to handle new provider

### Adding a Strategy

1. Create in `strategies/{domain}/`
2. Implement execution logic using driver primitives
3. Register in `strategies/__init__.py`
4. Add `strategy_execute` command handler

---

## Security Considerations

See [ADR-001: Agentic Browser Security](adr/ADR-001_Agentic_Browser_Security.md) for detailed security analysis and planned controls.

**Current Mitigations:**
- Filesystem sandbox enforcement (cannot escape root)
- Session isolation (separate BrowserContext per session)
- Explicit session lifecycle

**Planned Mitigations (Phase 1):**
- URL allowlist/blocklist
- Audit logging
- Rate limiting
- Squid proxy for network-level enforcement
