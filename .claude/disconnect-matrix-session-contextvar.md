# DISCONNECT MATRIX: Session ContextVar Cross-Contamination

## Discovery Date: 2026-02-06
## Branch: feature/multi-project-support
## Bug: Multi-project session isolation failure in HTTP transport

---

## OBSERVED FAILURE

3 concurrent MCP clients on HTTP transport (dev server port 9122):
- Client A: session `16edf956` → serena (Python)
- Client B: session `6273c4d5` → ramp (PHP)
- Client C: session `209e29da` → OpenMemory (Python)

**Error**: Client C's `get_symbols_overview` resolved against `/Users/ketema/projects/serena`
instead of `/Users/ketema/projects/OpenMemory`. Even Client A's session later resolved
against OpenMemory's root.

**Pattern**: Python+PHP works (different LSP instances). Python+Python FAILS.

---

## ARCHITECTURE SUMMARY

```
HTTP Request (Mcp-Session-Id: X)
    ↓
streamable_http_manager.py: set_transport_session_id(X)  [ContextVar #1]
    ↓
mcp.py execute_fn: get_transport_session_id() → X
    ↓
mcp_session_bridge.run_with_session_context(X, tool_fn)
    ↓
  set_session_context(X) → registry.get_session(X) → set_current_session(session)  [ContextVar #2]
    ↓
  tool_fn() executes with session context
    ↓
  finally: reset_session_context()
```

**Key Design**: ONE SerenaAgent instance, shared across ALL sessions.
Session state stored in SessionRegistry, accessed via ContextVar per-request.

---

## DISCONNECT MATRIX

| ID | Behavior | EXPECTED | OBSERVED | DELTA | Location |
|----|----------|----------|----------|-------|----------|
| B1 | Session creation workspace | Each session bound to client's workspace | All sessions bound to `Path.cwd()` (server's working dir) | OVERRIDE | mcp_session_bridge.py:102-103, mcp.py:389 |
| B2 | `_update_active_tools()` scope | Per-session tool set | Mutates SHARED `self._active_tools` on single Agent | OVERRIDE | agent.py:499-518, called from 867 |
| B3 | `_activate_project` session scope | Rebinds only calling session | Rebinds calling session + mutates shared Agent state | OVERRIDE | agent.py:646-662 |
| B4 | Tool set after concurrent activate | Each client sees own project's tools | Last `activate_project` wins for all clients | OVERRIDE | agent.py:512 (`self._active_tools = ...`) |
| B5 | ContextVar isolation in tool dispatch | Each request has isolated ContextVar | Correctly isolated per-request (set/reset in try/finally) | MATCH | mcp_session_bridge.py:269,338 |
| B6 | SessionRegistry binding correctness | Each session has correct workspace | Correct AFTER activate_project, wrong BEFORE | PARTIAL | session_registry.py bind_session |
| B7 | LSP workspace_root parameter | Uses session's workspace_root | Correct (REQ-2026-003 fix works) | MATCH | solidlsp/ls.py all 23 methods |
| B8 | `_project_activation_callback` | Per-session scoped | Called on shared Agent, affects all | OVERRIDE | agent.py:868-869 |

---

## ROOT CAUSE ANALYSIS

### Primary Bug (B1): Session Creation with Wrong Workspace

```python
# mcp.py:389 - callback wiring
on_session_created=lambda sid: bridge.on_transport_session_created(sid, workspace_root=None)

# mcp_session_bridge.py:102-103 - fallback
if workspace_root is None:
    workspace_root = Path.cwd()  # Server's cwd, NOT client's workspace!
```

**Impact**: Every new session starts with `workspace_root = /Users/ketema/projects/serena`
(server's cwd). Between session creation and `activate_project` call, all tool calls resolve
against the wrong workspace.

### Secondary Bug (B2/B3/B4): Shared Mutable State on Single Agent

```python
# agent.py:646-662 - _activate_project
def _activate_project(self, project):
    session_id = self._session_bridge.get_current_session_id()
    self.activate_session_project(session_id, workspace_root, "explicit")
    # activate_session_project calls:
    #   self._update_active_tools()  ← SHARED MUTATION!
    #   self._project_activation_callback()  ← SHARED MUTATION!
```

**Impact**: When Client C activates OpenMemory, `_update_active_tools()` updates the
SHARED `self._active_tools` dict based on OpenMemory's config. This affects tool
availability for ALL sessions.

### Why Python+PHP Works but Python+Python Fails

When Python+PHP: Different LSP instances (Pyright vs Intelephense). Each LSP's
`repository_root_path` is set correctly at creation time. Our REQ-2026-003 fix adds
`workspace_root` parameter, but the LSP itself doesn't cross-contaminate.

When Python+Python: Same Pyright LSP instance shared. The `workspace_root` parameter
is correct per-call (from session context), BUT:
1. Session creation gives wrong initial workspace (B1)
2. Any tool call before `activate_project` resolves against server's cwd (B1)
3. The shared Agent's `_active_tools` gets overwritten by last activation (B2/B4)

---

## FIX CATEGORIES

| Delta | Fix Strategy |
|-------|-------------|
| B1 (OVERRIDE) | Either: (a) Don't bind workspace at session creation (bind at activate_project only), or (b) Pass client workspace from HTTP headers |
| B2 (OVERRIDE) | Make tool set per-session, or compute dynamically from session context |
| B3 (OVERRIDE) | _activate_project should ONLY mutate session-scoped state |
| B4 (OVERRIDE) | Consequence of B2 fix |
| B8 (OVERRIDE) | Scope callback to session or remove global side effects |

---

## HALFSTEPPING (Where to Start)

**Priority**: B1 is the primary cause of the observed error. B2/B3/B4 are secondary
bugs that would manifest under different race conditions.

**Minimal Fix**: Fix B1 — don't register workspace at session creation, let `activate_project`
handle it exclusively. Sessions without activated projects should fail gracefully on
PROJECT/LSP tools.

**Full Fix**: Fix B1 + B2/B3/B4 — make `_update_active_tools()` session-aware.
