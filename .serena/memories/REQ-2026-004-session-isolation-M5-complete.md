# REQ-2026-004: Multi-Session State Isolation — M5 COMPLETE

## Date: 2026-02-06

## Completion Promise (VERIFIED)
"3 concurrent MCP HTTP sessions can each activate different projects
and execute LSP tool calls simultaneously. Each session resolves paths
against its own workspace root."

## Evidence

### Commits (feature/multi-project-support)
- C:107d2892 — GREEN phase: SessionContext.workspace_root Optional, activate_session_project no shared mutation
- C:8977357a — Pyright fixes: handle None workspace throughout agent.py and session_registry.py
- C:4e68ff37 — Audit fixes: ERRORS sections, test improvements

### Tests
- T:tests/test_session_isolation.py = 33/33 PASSED
- T:scripts/m46_execution_gate.py = 5/5 PASSED

### Contract
- F:contracts/session_isolation_contract.py — 5 contract classes (B1, B2/B4, B3, GracefulDeg, STDIO)

### Live Testing
- 3 concurrent MCP clients on port 9122 (serena/Python, ramp/PHP, OpenMemory/Python)
- After restart_language_server, all sessions resolve correctly
- ContextVar isolation confirmed: initial transient race resolved, subsequent calls correct

### AI Panel
- AI:conversation=e3418bcd-4179-4a92-9171-d3494dab1396 — Gemini critique: MEDIUM finding on skipping _update_active_tools is the intended fix per INV-B3-01/INV-B2-01

## Architectural Decisions
1. workspace_root=None valid for HTTP sessions before activate_project (INV-B1-02)
2. _update_active_tools() and _project_activation_callback() REMOVED from session activation path (INV-B3-01)
3. Tool availability now derived dynamically from session ContextVar
4. STDIO backward compatibility via anonymous sessions with Path.cwd()

## Known Limitation
- After MCP client reconnect, restart_language_server mandatory to re-bind LSP to correct workspace
- Root cause: LSP's repository_root_path set at creation time, not updated on reconnect
- Partially addressed by REQ-2026-003 (workspace_root parameter on all LSP methods)

## Files Changed (core)
- src/serena/agent.py (+30 lines: None workspace handling, remove shared state mutation)
- src/serena/mcp_session_bridge.py (+9 lines: remove Path.cwd() fallback)
- src/serena/session_registry.py (+41 lines: Optional workspace, anonymous source)
- contracts/session_isolation_contract.py (new, 297 lines)
- tests/test_session_isolation.py (new, 1691 lines)
- scripts/m46_execution_gate.py (new, 278 lines)
- requirements/REQ-2026-004-session-isolation.md (new, 128 lines)
