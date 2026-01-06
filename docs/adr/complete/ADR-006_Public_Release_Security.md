# ADR-006: Public Release Security Hardening

**Status:** Accepted
**Date:** 2025-12-21
**Authors:** Shane Cantwell

---

## Context

surf-mcp handles browser credentials (`storage_state` containing cookies, session tokens, localStorage) via MCP tool calls. Before public release, we need to:

1. Document the security model and trust boundaries
2. Address credential exposure in logs
3. Validate untrusted input
4. Provide guidance for remote execution

The MCP protocol itself provides no encryption - it's an application-layer standard (JSON-RPC) that assumes the transport handles security.

---

## Decision

### 1. Document Threat Model

Create `SECURITY.md` documenting:
- Trust boundary (the machine running surf-mcp)
- What we protect against (logging, input validation, rate limiting)
- What we accept (stdio interception requires machine compromise)
- SSH tunneling as the secure remote pattern

### 2. Redact Credentials in Logs

`server.py` DEBUG logging exposes full `storage_state`. Redact before logging.

### 3. Validate storage_state Input

Add schema validation to reject malformed input that could cause crashes or unexpected behavior.

### 4. SSH for Remote Execution

Document that remote execution should use SSH as the transport:

```json
{
  "command": "ssh",
  "args": ["-i", "key", "user@host", "surf-mcp"]
}
```

This provides encryption and authentication without modifying surf-mcp.

### 5. Accept stdio Trust Boundary

If an attacker can intercept stdio, they already have access to encryption keys, browser memory, and the client. Adding encryption would create complexity without meaningful benefit.

---

## Implementation

| Deliverable | Location |
|-------------|----------|
| Threat model documentation | `SECURITY.md` |
| README security notice | `README.md` |
| Log redaction | `src/surf_mcp/server.py` |
| Input validation | `src/surf_mcp/security/storage_state.py` |
| Harness gitignore | `tools/fara-harness/.gitignore` |

---

## Consequences

### Not Suitable For

- **Multi-tenant environments** - trust boundary is the machine
- **Untrusted networks** without SSH tunneling
- **Compliance-sensitive contexts** - no formal security audit
- **Untrusted MCP clients** - surf-mcp trusts its client completely

### Residual Risks

- **No formal security audit** - best-effort analysis only
- **MCP protocol limitations** - no encryption, no authentication
- **LLM trust** - Fara/Gemini responses executed without verification
- **Browser automation risks** - agent can click/type anything visible

---

## References

- [SECURITY.md](/SECURITY.md)
- [MCP Security Best Practices](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices)
