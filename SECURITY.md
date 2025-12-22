# Security Model

## Local Use Only

**surf-mcp is designed for LOCAL stdio transport.**

The MCP protocol does not encrypt data. If you expose surf-mcp over a network without encryption, you will leak:
- Browser cookies and session tokens
- localStorage contents
- Full navigation history

For remote execution, use SSH tunneling (see [Advanced Usage](#remote-execution-via-ssh) below).

---

## Threat Model

### Trust Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                    TRUSTED MACHINE                          │
│  ┌─────────────┐    stdio     ┌─────────────┐              │
│  │  MCP Client │◄────────────►│  surf-mcp   │              │
│  │  (Claude,   │   (trusted)  │             │              │
│  │   Cursor,   │              │  ┌───────┐  │              │
│  │   LAS...)   │              │  │Browser│  │              │
│  └─────────────┘              │  └───────┘  │              │
│                               └─────────────┘              │
│                                     │                       │
│                               ┌─────▼─────┐                │
│                               │  Fara/LLM │ (trusted)      │
│                               └───────────┘                │
└─────────────────────────────────────────────────────────────┘
                                     │
                         ────────────┼──────────── UNTRUSTED
                                     │
                              ┌──────▼──────┐
                              │   Internet  │
                              └─────────────┘
```

The trust boundary is the machine (or container) running surf-mcp. Everything inside that boundary is trusted; the internet is not.

### What We Protect Against

| Threat | Protection |
|--------|------------|
| Credential logging | Redacted in all log levels |
| Malformed input | Schema validation on storage_state |
| Runaway automation | Rate limiting (30 actions/min default) |
| Malicious domains | Configurable allowlist/blocklist |
| Incident investigation | Audit trail with screenshot hashes |

### What We Accept

| Risk | Rationale |
|------|-----------|
| Process memory inspection | Inherent to any credential handling |
| Session-lifetime token validity | Standard browser session semantics |
| Trusted LLM responses | Fara/Gemini are infrastructure, not user input |

### Why No Encryption?

If an attacker has process access to intercept stdio, they also have access to:
- Any encryption keys we could use
- The browser process memory
- The AI client's memory

Adding encryption would create complexity without meaningful security benefit. The correct solution for remote access is SSH tunneling, which provides proven encryption and authentication.

---

## Remote Execution via SSH

For remote GPU servers or headless machines, use SSH as the transport layer:

### MCP Client Configuration

```json
{
  "mcpServers": {
    "surf-remote": {
      "command": "ssh",
      "args": [
        "-i", "/path/to/private_key",
        "-o", "StrictHostKeyChecking=accept-new",
        "user@gpu-server.local",
        "surf-mcp"
      ]
    }
  }
}
```

### Python/LAS Configuration

```python
tools = [
    {
        "name": "surf-mcp",
        "command": "ssh",
        "args": [
            "-i", "/path/to/key",
            "user@remote-box",
            "surf-mcp"
        ]
    }
]
```

### Why SSH Works

- **Encryption**: SSH handles the handshake and encryption transparently
- **Authentication**: Standard SSH keys (Ed25519 recommended)
- **Transparency**: surf-mcp sees normal stdio; it doesn't know it's remote
- **No code changes**: Works with stock surf-mcp

### What NOT To Do

```bash
# DANGEROUS: Exposes credentials in plaintext
socat TCP-LISTEN:8080 EXEC:surf-mcp

# DANGEROUS: No encryption
nc -l 8080 -e surf-mcp

# DANGEROUS: Raw port forwarding without SSH
ssh -L 8080:localhost:8080 user@host  # then connecting to 8080 directly
```

---

## Security Controls

### Domain Filtering

Restrict which domains the browser can access:

```bash
# Allowlist mode (only these domains)
SURF_BROWSER_ALLOWED_DOMAINS=example.com,internal.corp

# Blocklist mode (block these, allow others)
SURF_BROWSER_BLOCKED_DOMAINS=*.bank.com,paypal.com,accounts.google.com
```

Default blocklist includes sensitive financial and identity sites.

### Rate Limiting

Prevent runaway automation:

```bash
SURF_MAX_ACTIONS_PER_MINUTE=30  # Default
```

### Audit Logging

All browser actions are logged with:
- Timestamp and session ID
- Action type and parameters
- Screenshot hash (SHA256)
- LLM response details
- Outcome (success/failed/blocked)

Access via the `AuditLogger` class or enable debug logging:

```bash
SURF_LOG_LEVEL=DEBUG
```

**Note:** Debug logs redact `storage_state` contents to prevent credential exposure.

---

## Storage State Security

### What storage_state Contains

Playwright's storage_state includes:
- **Cookies**: Session tokens, auth cookies, tracking cookies
- **localStorage**: App-specific tokens and preferences
- **sessionStorage**: Temporary session data

This is sensitive data equivalent to having the user's logged-in browser session.

### How We Handle It

1. **Never logged**: storage_state is redacted in all log output
2. **Never persisted**: Server is stateless; state flows through tool calls
3. **Validated**: Schema validation rejects malformed input
4. **Round-tripped**: Returned on `session_destroy` for client-side persistence

### Client Responsibilities

The MCP client (Claude, Cursor, your agent) receives storage_state on session destroy. The client should:
- Store it securely (encrypted at rest)
- Never log it
- Never commit it to version control

---

## Containerized Deployment

For production, run surf-mcp in an isolated container:

```yaml
# docker-compose.yml
services:
  surf-mcp:
    build: .
    environment:
      - LMSTUDIO_SERVERS=default=http://host.docker.internal:1234/v1
      - SURF_BROWSER_HEADLESS=true
    # No ports exposed - stdio only via docker exec or SSH
```

Benefits:
- Process isolation
- Network namespace isolation
- Resource limits
- Clean credential scope per container

---

## Reporting Security Issues

Please report security vulnerabilities via [GitHub Security Advisories](https://github.com/shanevcantwell/surf-mcp/security/advisories).

Do not open public issues for security vulnerabilities.
