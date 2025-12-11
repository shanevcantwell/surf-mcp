# ADR-004: Compact Storage State for LLM Contexts

**Status:** Proposed
**Date:** 2025-12-11
**Authors:** Shane Cantwell, Claude

---

## Context

Navigator-mcp passes browser `storage_state` (cookies, localStorage) through MCP tool calls rather than persisting server-side. This keeps the server stateless and aligns with how LLM tool calls work.

Playwright's native `storage_state` format includes full cookie metadata:
```json
{
  "cookies": [
    {"name": "session_id", "value": "abc123", "domain": ".example.com",
     "path": "/", "expires": 1723844704, "httpOnly": true,
     "secure": true, "sameSite": "Lax"}
  ],
  "origins": [
    {"origin": "https://example.com",
     "localStorage": [{"name": "token", "value": "xyz..."}]}
  ]
}
```

For typical authenticated sessions, this can be **1-5KB+** of JSON, which translates to **250-1,250+ tokens** when passed through LLM conversation context.

---

## Problem

When an LLM agent (e.g., LAS) orchestrates browser automation, `storage_state` flows through conversation context:

1. `session_destroy` returns storage_state
2. Agent stores it in conversation
3. Next `session_create` passes it back

This consumes context window on every session cycle, potentially 1K+ tokens per round-trip.

---

## Proposed Solution

Add `compact: true` option to `session_destroy`:

```python
# Full format (default)
result = await session.call_tool("session_destroy", {"session_id": "abc123"})
# Returns: {"storage_state": {<full Playwright format>}}

# Compact format (for LLM contexts)
result = await session.call_tool("session_destroy", {
    "session_id": "abc123",
    "compact": True
})
# Returns: {"storage_state": {"c": [{"n": "session_id", "v": "abc", "d": ".example.com"}]}}
```

### Compact Schema

```json
{
  "c": [                           // cookies (shortened key)
    {"n": "name", "v": "value", "d": "domain"}
  ],
  "l": {                           // localStorage (shortened key)
    "https://example.com": {"key": "value"}
  }
}
```

- Strip metadata (expires, httpOnly, secure, sameSite, path)
- Use single-char keys
- Estimated savings: 60-80% token reduction

### Restoration

`session_create` would accept either format and expand compact to full:
- Missing `path` → defaults to `"/"`
- Missing `expires` → session cookie
- Missing flags → sensible defaults (httpOnly=false, secure=true, sameSite="Lax")

---

## Trade-offs

| Aspect | Full Format | Compact Format |
|--------|-------------|----------------|
| Token cost | High (250-1250+) | Low (50-250) |
| Fidelity | Preserves all metadata | Loses some cookie flags |
| Compatibility | Native Playwright | Requires expansion |
| Use case | Direct API, harness | LLM agents |

---

## Decision

**Defer to v0.4.0+**

Current priority is the Fara test harness (ADR-003), which uses direct MCP calls where token cost doesn't matter. Revisit when:

1. LAS integration is active and token usage is measurable
2. We have real data on storage_state sizes across target sites
3. The trade-off between fidelity and tokens is clearer

---

## References

- [ADR-002: Strategy Architecture](./ADR-002_Strategy_Architecture.md) - Session/credential separation
- [ADR-003: Fara Test Harness](./ADR-003_Fara_Test_Harness.md) - Test harness design
- [Playwright Storage State](https://playwright.dev/docs/auth)
