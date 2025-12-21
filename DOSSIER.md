# Surf MCP - Strategic Dossier

**Purpose:** Capture strategic context, positioning, and consumer insights for continuity across conversations.

**Last Updated:** 2025-12-20

---

## Project Identity

**Name:** surf-mcp (was: navigation-mcp, navigator-mcp)
**Tagline:** MCP server for visual browser automation via Fara
**Core Insight:** An AI that can *see* the page doesn't need to parse HTML.

### Why "Surf"?

- Evokes web navigation metaphorically ("surfing the web")
- Distinct from generic names like "browser-mcp"
- Not model-specific like "fara-mcp" (Fara could be swapped for future vision models)
- Short, memorable, available

---

## Scope Decision (v0.4.0)

### Browser-Only Focus

**Decision:** Remove filesystem functionality entirely.

**Rationale:**
1. **Filesystem already solved:** `filesystem-mcp` exists and is mature
2. **Unique value prop:** Visual grounding via Fara is what makes Surf distinctive
3. **Focus > features:** Better to do one thing well than two things mediocrely
4. **Maintenance burden:** Dual-domain abstraction adds complexity without clear benefit

**What was removed:**
- `FileSystemDriver` class
- Filesystem-specific commands (write, delete, copy, move, find)
- Strategy scaffold (was designed for cross-domain operations)
- All filesystem tests

**What remains:**
- BrowserDriver with full visual grounding
- Session management
- Security controls (DomainFilter, RateLimiter, AuditLogger)
- Multi-server LM Studio support

---

## Ecosystem Positioning

### Competitive Landscape (Dec 2025)

| Project | Approach | Strength | Weakness |
|---------|----------|----------|----------|
| **Playwright MCP** | DOM-based automation | Precise, fast | Brittle selectors, no vision |
| **Magentic-UI** | Full UI agent framework | Rich features | Heavy, not MCP-native |
| **Anthropic Computer Use** | General computer control | Broad applicability | Not web-specific |
| **Surf MCP** | Visual grounding + MCP | Natural language, model-agnostic | Requires vision LLM |

### Unique Position

Surf occupies the intersection of:
- **MCP protocol** (AI-native integration)
- **Visual grounding** (natural language element targeting)
- **Local-first** (Fara runs on consumer GPUs via LM Studio)

No direct competitor currently serves this niche.

---

## Known Consumers

### LAS (langgraph-agentic-scaffold)

Primary consumer. Integration documented in `docs/reports/NAVIGATION_MCP_CONSUMER_REPORT.md`.

**What LAS uses:**
- Browser navigation (goto, read, snapshot)
- Visual grounding (click, type via Fara)
- Session management with artifact persistence
- Graceful degradation when MCP unavailable

**What LAS needs (gaps):**

| Priority | Enhancement | LAS Use Case |
|----------|-------------|--------------|
| P0 | `wait_for_change` | Detect WebUI LLM response completion |
| P0 | `session_status` | Query session without side effects |
| P1 | Multi-element location | "Click the 3rd search result" |
| P1 | Batch operations | Multi-file upload scenarios |
| P2 | Progress streaming | Show page load progress |
| P2 | Structured extraction | Return parsed data, not raw text |

**Tested capabilities:**
- Browser core: 85% coverage
- Visual grounding: 70% coverage
- Session management: 90% coverage
- Error handling: 60% coverage
- Security constraints: 80% coverage

---

## Release Strategy

### Distribution (Planned)

**Primary:** Docker Hub (`shanecantwell/surf-mcp`)
- Pre-built container with Playwright browsers
- Works with external LM Studio (on host or remote)
- Squid proxy for domain allowlisting

**Secondary:** PyPI (`surf-mcp`)
- For direct installation
- Requires separate `playwright install chromium`

### Versioning

- **Current:** 0.4.0
- **Approach:** Stay at 0.x until:
  - Consumer APIs stabilized
  - Production usage validated
  - Security controls hardened

### What 1.0 Requires

1. Stable MCP tool schema (no breaking changes)
2. At least 2 independent consumers
3. Security audit of session isolation
4. Performance benchmarks documented

---

## Technical Debt

### Known Issues

1. **Test coverage gaps:**
   - `type` operation tested implicitly only
   - `scroll` has no dedicated tests
   - Concurrent sessions not tested

2. **Missing from LAS wishlist:**
   - No `wait_for_change` for DOM mutation detection
   - No `session_status` for introspection
   - Single-element location only

3. **Security hardening needed:**
   - Squid proxy scaffolded but not enforced
   - No sensitive action confirmation
   - No screenshot sanitization

### Deferred ADRs

- **ADR-004:** Compact storage state (deferred - base64 works for now)
- **ADR-002:** Strategy architecture (partially implemented, scope reduced)

---

## Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-12-20 | Remove filesystem | Focus on visual grounding as unique value |
| 2025-12-20 | Rename to surf-mcp | More descriptive than navigation, less generic than browse |
| 2025-12-20 | Stay at 0.x | Not ready for 1.0 stability commitment |
| 2025-12-20 | Docker Hub primary | Container includes browser, easier than pip install + playwright |
| 2025-12-13 | Auto-switch new tabs | User intent for single-prompt actions |
| 2025-12-10 | ADR-005 Direct Fara | Let Fara decide action, don't parse commands |

---

## Future Directions

### Near-term (v0.5-v0.6)

1. Implement `wait_for_change` for LAS WebUI adapters
2. Add `session_status` introspection
3. Multi-element location ("click Nth result")
4. Docker Hub publishing automation

### Medium-term

1. Strategy system for common workflows (login, form fill)
2. Recording mode for strategy creation
3. Additional vision model adapters (Claude 3.5, GPT-4o)

### Long-term

1. Browser extension for local-only mode
2. Learned strategies from user demonstrations
3. Multi-browser support (Firefox, Safari)

---

## Contact

**Maintainer:** Shane Cantwell
**Repo:** github.com/shanevcantwell/navigation-mcp (will rename to surf-mcp)
