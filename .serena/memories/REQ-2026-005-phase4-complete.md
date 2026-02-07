# REQ-2026-005 Phase 4 Complete

## What Was Done
Phase 4: Pool wiring integration — SEQ-POOL-05 and SEQ-POOL-06

### SEQ-POOL-05: on_transport_session_closed → pool.release()
- **Bug**: MCPSessionBridge.on_transport_session_closed() only called unbind_session(). Never released pool references.
- **Impact**: Ref count leak — LSPs never reclaimed after client disconnect.
- **Fix**: Added optional `lsp_pool` parameter to MCPSessionBridge.__init__(). In on_transport_session_closed(), before unbinding: get session context, iterate lsp_references, call pool.release() per language.
- **Thread safety**: Uses list() snapshot of lsp_references.keys() to prevent concurrent modification issues.
- **Guard**: Skips pool.release() when workspace_root is None (HTTP mode before activate_project).

### SEQ-POOL-06: acquire() → probe_workspace_readiness
- **Bug**: acquire() called adapter.add_workspace_root() but never called probe_workspace_readiness().
- **Impact**: Tool calls dispatched to un-indexed workspaces.
- **Fix**: After add_workspace_root() for multi-root new workspaces, call probe_workspace_readiness(lsp, workspace_root, 30).
- **Degraded mode**: If probe returns False, logs warning but returns LSP anyway (non-blocking).

## Files Changed
- src/serena/mcp_session_bridge.py: __init__ accepts lsp_pool, on_transport_session_closed calls pool.release()
- src/serena/global_lsp_pool.py: acquire() calls probe_workspace_readiness after add_workspace_root

## Commits
- 166f0f14: Phase 4 GREEN — SEQ-POOL-05 and SEQ-POOL-06 implementation
- 9352b43: Phase 4 tests — 6 Tier 1.5 integration tests
- 73f2863a: AI Panel fixes — thread safety, probe failure handling

## Test Results
- 6 Phase 4 tests (test_phase4_pool_wiring_integration.py)
- 67/67 total REQ-2026-005 tests passing

## AI Panel
- Conversation: c9a22881-a69e-4012-9498-64227ddc6fa0
- 3 findings addressed: probe failure handling (CRITICAL), thread-safe iteration (HIGH), hardcoded timeout (MEDIUM — deferred as YAGNI)

## NOTE: Wiring Not Yet Complete in Production
MCPSessionBridge is constructed in mcp.py:495 as `MCPSessionBridge(session_registry)` WITHOUT passing lsp_pool. The pool wiring is implemented and tested but the mcp.py construction site needs to be updated to pass lsp_pool for production use:
```python
# Current (mcp.py:495):
self._session_bridge = MCPSessionBridge(session_registry)

# Needs to become:
pool = self.get_lsp_pool()
self._session_bridge = MCPSessionBridge(session_registry, lsp_pool=pool)
```
This is a Phase 5 item (production wiring) that should be done when all phases are integrated.
