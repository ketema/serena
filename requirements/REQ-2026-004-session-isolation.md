# REQ-2026-004: Multi-Session State Isolation

## CCABDD Governance

Human owns: intent (front) + reality judgment (back).
AI owns: enforcement (middle).
Neither crosses the boundary.

---

## 1. Intent Traceability

- **Source Prose**:
  > "broken. it is not working"
  > "load /constitutional-orchestrator and /constitutional-refactor the bug"
  > "option 2 full fix of course. per constitutional law there is no other option."

  Context: M4.6 real-world test with 3 concurrent MCP HTTP sessions (serena/Python,
  ramp/PHP, OpenMemory/Python). OpenMemory session `209e29da` resolved paths against
  `/Users/ketema/projects/serena` instead of `/Users/ketema/projects/OpenMemory`.

- **Our Understanding**: Fix ALL shared mutable state on the single SerenaAgent instance
  so that concurrent MCP sessions are fully isolated. Both the wrong-workspace-at-creation
  bug (B1) and the shared-tool-set mutation bug (B2/B3/B4).

- **Ambiguity Score**: 1 (user approved Option 2, scope is clear from disconnect matrix)

## 2. The Actor Matrix

| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| MCP Client A | Read/write own workspace only | Access other client's workspace |
| MCP Client B | Read/write own workspace only | Access other client's workspace |
| SerenaAgent | Shared instance, session-aware dispatch | Mutate per-session state globally |
| SessionRegistry | Authoritative session→workspace mapping | Allow unregistered sessions |
| HTTP Transport | Set per-request ContextVar | Leak ContextVar across requests |

## 3. The State Transition

- **Initial State ($S_0$)**:
  - Single SerenaAgent shared across sessions
  - `on_transport_session_created()` binds to `Path.cwd()` (server's dir)
  - `_update_active_tools()` mutates shared `self._active_tools`
  - `_project_activation_callback()` fires globally

- **Transformation**: Session isolation fix (B1 + B2/B3/B4)

- **Terminal State ($S_1$)**:
  - Sessions start without workspace binding (no `Path.cwd()` fallback)
  - `activate_project` is the ONLY way to bind workspace to session
  - Tool availability computed per-session from session context
  - No global state mutation during `activate_project`

## 4. Hard Invariants (The "Never" List)

| ID | Category | Invariant |
|----|----------|-----------|
| INV-01 | Isolation | Session workspace MUST NEVER default to `Path.cwd()` |
| INV-02 | Isolation | `_update_active_tools()` MUST NOT mutate shared Agent state based on one session |
| INV-03 | Isolation | Tool calls from Session A MUST NOT affect Session B's state |
| INV-04 | Compatibility | STDIO mode (single-session) MUST continue to work unchanged |
| INV-05 | Resource | Shared LSP pool (CON-3) MUST be preserved — LSPs shared by language |
| INV-06 | Safety | PROJECT/LSP tools MUST fail gracefully if no project activated |
| INV-07 | Ordering | `activate_project` MUST be called before any PROJECT/LSP tool |

## 5. High-Entropy Zones (Adjudicated)

| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| B1-workspace | What workspace for new sessions? | None — sessions start without workspace, activate_project binds it | User (Option 2) |
| B2-toolset | Per-session tool set storage? | Compute dynamically from session context in tool dispatch | User (Option 2) |
| B3-callback | Project activation callback scope? | Session-scoped or removed | User (Option 2) |
| STDIO-compat | How does STDIO mode work without HTTP sessions? | Existing anonymous session fallback preserved | Discovery (B5 MATCH) |

## 5.5 Rejected Alternatives

| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Full fix (Option 2) | Minimal fix B1 only (Option 1) | "per constitutional law there is no other option" — B2/B3/B4 are bugs regardless |
| Full fix (Option 2) | HTTP header workspace (Option 3) | Requires MCP protocol changes, doesn't fix B2/B3/B4 |

## 6. Tool/API Interface Summary

| Interface | Purpose | Mutates State? |
|-----------|---------|----------------|
| `on_transport_session_created(sid)` | Register new MCP session | YES — session registry |
| `activate_project(name)` | Bind workspace to session | YES — session registry + project load |
| `run_with_session_context(sid, fn)` | Execute tool in session scope | YES — ContextVar (scoped) |
| `_update_active_tools()` | Compute available tools | YES — currently shared (BUG) |
| `get_active_project_or_raise()` | Get session's project | NO — reads ContextVar |

## 6.5 Blocking Dependencies

None — all requirements are resolvable from existing codebase.

## 7. Completion Promise (Ralph Loop Exit)

> "3 concurrent MCP HTTP sessions (2 Python, 1 PHP) can each activate different projects
> and execute LSP tool calls simultaneously. Each session resolves paths against its own
> workspace root. No session's `activate_project` call affects another session's tool
> availability or path resolution. Verified by M4.6 real-world execution."

## 8. Contract Authority

**Authoritative Source**: `contracts/session_isolation_contract.py`

```
requirements/REQ-2026-004-session-isolation.md (this file)
        ↓
contracts/session_isolation_contract.py
        ↓
tests/test_session_isolation.py
        ↓
src/serena/agent.py, mcp_session_bridge.py, mcp.py
```

## 9. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-06 | Human+AI | Initial manifest from Phase 1 Discovery DISCONNECT MATRIX |

## Cross-References

- `.claude/disconnect-matrix-session-contextvar.md` — Discovery findings
- `contracts/serena_agent_stateless_contract.py` — Existing agent contract
- `contracts/mcp_session_bridge_contract.py` — Existing bridge contract
- `requirements/REQ-2026-003-solidlsp-path-resolution.md` — LSP-level fix (COMPLETE)
