# REQ-2026-004: Multi-Session State Isolation — COMPLETE

## Status: GREEN + AUDITED
## Branch: feature/multi-project-support
## Date: 2026-02-06

## Commits
- 107d2892: GREEN phase — B1/B2/B3 fixes (33/33 tests)
- 8977357: Pyright type error fixes (Optional workspace_root)
- 4e68ff37: Constitutional audit fixes (4 findings resolved)

## What Was Fixed
### B1: Session Creation Without Workspace
- `mcp_session_bridge.py`: Removed `Path.cwd()` fallback from `on_transport_session_created()`
- Sessions now start with `workspace_root=None` in HTTP mode
- STDIO backward compatibility preserved via `get_or_create_anonymous_session()`

### B2/B3/B4: Shared Mutable State
- `agent.py`: Removed `_update_active_tools()` call from `activate_session_project()`
- `agent.py`: Removed `_project_activation_callback()` call from `activate_session_project()`
- `session_registry.py`: `workspace_root` now `Path | None` in SessionContext and bind_session

### Graceful Degradation
- `agent.py`: `get_active_project_or_raise()` now handles None workspace with clear error + session_id

## Test Evidence
- 33 session isolation tests (test_session_isolation.py)
- 66 existing tests (regression clean)
- 70 path resolution tests (REQ-2026-003 regression clean)
- M4.6 execution gate: 5/5 real integration tests PASSED
- Constitutional audit: 4 critical findings resolved, 5 MEDIUM remaining (traceability gaps, CL10 mock)

## Remaining MEDIUM Findings (Non-Blocking)
- POST-B3-02 (ContextVar set after activation) — implicit coverage only
- POST-B3-03 (Project loaded after activation) — implicit coverage only
- POST-GD-03 (session_id in error for workspace=None) — partial coverage
- CL10: Project.load mocked without contract file

## Architecture Decision
- Tool availability computation deferred — shared `_active_tools` no longer mutated but 
  dynamic per-session computation (`get_active_tools_for_session()`) not yet implemented.
  Current behavior: tools fixed at agent startup, not changed per-session activation.
  This is safe because `get_exposed_tool_instances()` docstring confirms clients don't react to changes.

## Files Modified
- src/serena/mcp_session_bridge.py
- src/serena/session_registry.py
- src/serena/agent.py
- tests/test_session_isolation.py (NEW)
- contracts/session_isolation_contract.py (NEW)
- requirements/REQ-2026-004-session-isolation.md (NEW)
- scripts/m46_execution_gate.py (NEW)
