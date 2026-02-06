# REQ-2026-002: Transport-Session Bridge Integration

## CCABDD Governance

Human owns: intent (front) + reality judgment (back).
AI owns: enforcement (middle).
Neither crosses the boundary.

Human MUST confirm real-world effect matches intent.
AI MAY NOT infer success from metrics.

---

## 1. Intent Traceability

- **Source Prose**:
  > "Fix transport-session bridge gap: HTTP transport creates sessions (streamable_http_manager.py:266) but never calls on_transport_session_created(). Evidence: (1) Log shows 'Created new transport with session ID' but no 'MCP session created', (2) activate_project succeeds but get_current_config shows no active project, (3) Session exists in ContextVar but not in SessionRegistry. Root issue: Transport layer has no reference to session_bridge. Location: src/serena/patches/mcp/server/streamable_http_manager.py and mcp.py wiring."

- **Our Understanding**: When HTTP transport creates a session, it must register that session in SessionRegistry via callback to MCPSessionBridge.on_transport_session_created(). Currently this doesn't happen, causing activate_project to fail silently.

- **Ambiguity Score**: 1 (Ready for contracts)

## 2. The Actor Matrix

| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| StreamableHTTPSessionManager | Create/close transport sessions, invoke callbacks | Directly access SessionRegistry |
| MCPSessionBridge | Register/unregister sessions in SessionRegistry | Create transport sessions |
| mcp.py (SerenaApp) | Wire callbacks during server setup | None |
| Client (Claude Code) | Call activate_project to bind workspace | Assume session is bound without calling activate_project |

## 3. The State Transition

- **Initial State ($S_0$)**:
  - HTTP request arrives with no session header
  - SessionRegistry has no entry for this client

- **Transformation**:
  1. Transport creates session_id
  2. Transport invokes on_session_created callback
  3. Callback registers session in SessionRegistry (workspace=None)
  4. Client calls activate_project
  5. SessionRegistry binds workspace to session

- **Terminal State ($S_1$)**:
  - Session registered in SessionRegistry
  - Workspace bound after activate_project
  - get_current_config returns active project

## 4. Hard Invariants (The "Never" List)

| ID | Category | Invariant |
|----|----------|-----------|
| INV-01 | Lifecycle | Transport MUST call on_session_created before first tool executes |
| INV-02 | Lifecycle | Transport MUST call on_session_closed when connection terminates |
| INV-03 | Separation | Transport layer SHALL NOT directly access SessionRegistry |
| INV-04 | Separation | Transport layer SHALL NOT know about MCPSessionBridge internals |
| INV-05 | Workspace | Session starts with workspace=None; activate_project required to bind |
| INV-06 | Tool Dispatch | Tool execution MUST fail if session_id not registered in SessionRegistry |
| INV-07 | Path Resolution | LSP server MUST have properly registered workspace path for ALL activated projects |

## 5. High-Entropy Zones (Adjudicated)

| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| Wiring Pattern | How should session_bridge be available to transport? | Callback injection (Option A) | User |
| Cleanup Scope | Wire only create or both create+close? | Wire both (Option A) | User |
| Workspace Binding | Auto-bind or require activate_project? | Require activate_project | User |

## 5.5 Rejected Alternatives

| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Callback injection | Global accessor | Creates coupling between transport and application layers |
| Callback injection | Event system | Adds complexity without clear benefit |
| Wire both callbacks | Only create callback | Would cause resource leaks, inconsistent with existing contract |

## 6. Tool/API Interface Summary

| Interface | Purpose | Mutates State? |
|-----------|---------|----------------|
| StreamableHTTPSessionManager.__init__(on_session_created, on_session_closed) | Accept lifecycle callbacks | NO |
| on_session_created(session_id) callback | Register session in SessionRegistry | YES |
| on_session_closed(session_id) callback | Unregister session from SessionRegistry | YES |
| mcp.py server setup | Wire callbacks to session_bridge methods | NO |

## 6.5 Blocking Dependencies

| Unresolved Zone | Blocks |
|-----------------|--------|
| None | N/A |

## 7. Completion Promise (Ralph Loop Exit)

> After server restart:
> 1. HTTP client connects → log shows "MCP session created: {session_id}"
> 2. Client calls activate_project("/path/to/project")
> 3. Client calls get_current_config → returns active project name
> 4. Client disconnects → log shows "MCP session closed: {session_id}"

## 8. Contract Authority

**Authoritative Source**: `contracts/transport_session_callback_contract.py`

```
REQUIREMENT_MANIFEST.md (this file)
        ↓
contracts/transport_session_callback_contract.py
        ↓
tests/test_transport_session_callback.py
        ↓
src/serena/patches/mcp/server/streamable_http_manager.py
src/serena/mcp.py
```

## 9. DISCONNECT MATRIX

| ID | Behavior | EXPECTED | OBSERVED | DELTA | Location |
|----|----------|----------|----------|-------|----------|
| B1 | Session registration on HTTP connect | on_transport_session_created(session_id) called | Session created but NOT registered | NEW | streamable_http_manager.py:266 |
| B2 | Session cleanup on HTTP disconnect | on_transport_session_closed(session_id) called | No cleanup callback | NEW | streamable_http_manager.py:287-294 |
| B3 | Callback injection pattern | Manager accepts on_session_created/closed callbacks | No callback mechanism exists | NEW | StreamableHTTPSessionManager.__init__ |
| B4 | Wiring in mcp.py | Callbacks set during server setup | No wiring exists | NEW | mcp.py server setup |

## 10. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-05 | User + Claude | Initial manifest from req-elicit |
