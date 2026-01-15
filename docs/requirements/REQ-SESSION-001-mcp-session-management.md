# REQ-SESSION-001: MCP HTTP Session Management

## 1. Intent Traceability
- **Source Prose**:
  > "My expectation is that an mcp client without a session id or with a stale session id will cause the server to give them a new valid session id
  > a client must not be able to spoof a session id
  > a client must not be able to hijack a session that is not theirs
  > the server will issue sessions that are the maximum allowable by the http protocol
  >
  > are there any other valid expectations that would cover correct client and server behavior regarding session initiation and management?"
  >
  > [After spec research]: "A follow the spec strictly."

- **Our Understanding**: Implement MCP Streamable HTTP session management per specification 2025-03-26, with strict adherence to protocol-mandated error codes and recovery flows.

- **Ambiguity Score**: 1 (Resolved via spec reference)

## 2. The Actor Matrix
| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| MCP Client | Session participant | Spoofing session IDs, hijacking other sessions |
| MCP Server (Serena) | Session authority | Issuing non-cryptographic IDs, accepting invalid sessions |
| Malicious Actor | None | All session operations |

## 3. The State Transition

### Session Creation
- **Initial State ($S_0$)**: No session exists for client
- **Transformation**: POST InitializeRequest (no Mcp-Session-Id header)
- **Terminal State ($S_1$)**: Session created, Mcp-Session-Id returned in response

### Session Usage
- **Initial State ($S_0$)**: Valid session exists
- **Transformation**: POST/GET with valid Mcp-Session-Id header
- **Terminal State ($S_1$)**: Request processed, session state maintained

### Stale Session Recovery
- **Initial State ($S_0$)**: Client has stale/invalid session ID
- **Transformation**: Any request with stale Mcp-Session-Id
- **Terminal State ($S_1$)**: Server returns 404, client MUST reinitialize

## 4. Hard Invariants (The "Never" List)
| ID | Category | Invariant |
|----|----------|-----------|
| INV-01 | Security | Session IDs MUST be cryptographically secure (UUID, JWT, or crypto hash) |
| INV-02 | Security | Session IDs MUST only contain visible ASCII (0x21-0x7E) |
| INV-03 | Security | Server MUST NOT accept client-fabricated session IDs |
| INV-04 | Isolation | Server MUST NOT allow session ID reuse across different logical sessions |
| INV-05 | Protocol | Only POST InitializeRequest MAY create a new session |
| INV-06 | Protocol | Stale session ID MUST return 404 Not Found |
| INV-07 | Protocol | Missing session ID (non-init) MUST return 400 Bad Request |
| INV-08 | Lifecycle | Server restart MUST invalidate all existing sessions |

## 5. High-Entropy Zones (Adjudicated)
| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| Session Timeout | How long do sessions live? | Maximum per MCP spec, then HTTP spec | User + Spec |
| Concurrent Sessions | One per client or many? | One per connection, server handles many | User |
| GET Session Creation | Can GET create sessions? | NO - only POST InitializeRequest | Spec (strict) |
| Stale ID Handling | Auto-recover or signal client? | Return 404, client reinitializes | Spec (strict) |
| Rate Limiting | Limit session creation? | DEFERRED - keep current behavior | User |
| Session ID Rotation | Rotate IDs periodically? | DEFERRED | User |
| Audit Trail | Log session events? | YES - full auditing | User |

## 5.5 Rejected Alternatives
| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Return 404 for stale sessions | Auto-create new session transparently | Violates MCP spec; client must reinitialize |
| GET cannot create sessions | Allow GET to create sessions | Violates MCP spec; only InitializeRequest creates |
| Strict spec compliance | Extended "helpful" behavior | User chose spec-strict; predictable, interoperable |

## 6. Tool/API Interface Summary
| Interface | Purpose | Mutates State? |
|-----------|---------|----------------|
| POST /mcp (InitializeRequest) | Create session | YES - creates session |
| POST /mcp (other) | Send JSON-RPC messages | Depends on message |
| GET /mcp | Open SSE stream | NO - read-only stream |
| DELETE /mcp | Terminate session | YES - destroys session |

## 6.5 Blocking Dependencies
| Unresolved Zone | Blocks |
|-----------------|--------|
| None | - |

## 7. Completion Promise (Ralph Loop Exit)
> "Session management is complete when:
> 1. POST InitializeRequest without session ID creates new session and returns Mcp-Session-Id
> 2. Requests with valid Mcp-Session-Id are processed normally
> 3. Requests with stale/invalid Mcp-Session-Id return 404 Not Found
> 4. Requests without Mcp-Session-Id (non-init) return 400 Bad Request
> 5. Session IDs are cryptographically secure UUIDs
> 6. All session lifecycle events are logged (creation, usage, termination, rejection)
> 7. Claude Code can successfully connect, reconnect after server restart (via reinit), and operate"

## 8. Contract Authority
**Authoritative Source**: MCP Specification 2025-03-26

```
MCP Specification 2025-03-26 (external authority)
        ↓
REQ-SESSION-001 (this manifest)
        ↓
contracts/mcp_session_contract.py
        ↓
tests/contracts/test_mcp_session_contract.py
        ↓
src/serena/patches/mcp/server/streamable_http_manager.py
```

**Spec Reference**: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#session-management

## 9. Protocol-Mandated Behavior (from MCP Spec)

### Response Codes
| Scenario | Required Response | Client Action |
|----------|------------------|---------------|
| POST InitializeRequest (no session ID) | 200 + Mcp-Session-Id + InitializeResult | Store session ID |
| Request with valid session ID | 200/202 (per message type) | Continue |
| Request with stale/invalid session ID | **404 Not Found** | MUST POST new InitializeRequest |
| Request without session ID (non-init) | **400 Bad Request** | MUST POST InitializeRequest |
| GET for SSE stream (valid session) | 200 + text/event-stream | Listen for events |
| DELETE session | 200 or 405 | Session ended |

### Session ID Requirements
- SHOULD be globally unique
- SHOULD be cryptographically secure (UUID, JWT, crypto hash)
- MUST only contain visible ASCII (0x21-0x7E)

## 10. Revision History
| Date | Author | Change |
|------|--------|--------|
| 2026-01-15 | User + Claude | Initial manifest from req-elicit |
| 2026-01-15 | User | Decision: Follow MCP spec strictly |
