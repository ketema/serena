# REQ-2026-005 Phase 5: Production Wiring — COMPLETE

## Objective
Wire `lsp_pool` into `MCPSessionBridge` at `SerenaMCPFactory.get_session_bridge()` (mcp.py:495).

## Changes

| File | Change | Commits |
|------|--------|---------|
| `src/serena/mcp.py` | `get_session_bridge()` now passes `self.get_lsp_pool()` to `MCPSessionBridge` constructor. Defensive assertion added. | 95ea79b6, 956ca57f |
| `tests/test_phase5_factory_wiring.py` | 2 Tier 1.5 integration tests verifying factory wiring and singleton lifecycle | (part of 95ea79b6) |

## Key Design Decisions
- **RLock reentrant safety**: Factory uses `threading.RLock()`, so nested `get_lsp_pool()` call from within `get_session_bridge()`'s lock is safe.
- **No thread starts during pool init**: `LSPTimeoutManager.__init__()` does NOT start threads. `set_reclaim_callback()` only stores a reference. Thread starts only via explicit `start_monitoring()`.
- **lsp_pool remains optional**: MCPSessionBridge constructor param is `lsp_pool: GlobalLanguageServerPool | None = None`. Only the production factory path passes it.

## Regression
63/63 REQ-2026-005 tests GREEN

## AI Panel
Conversation: b765c565-c202-4aaf-8210-fcefc1d06474
- Plan critique: 6/10 (thread safety concerns mitigated after inspection)
- Code critique 1: MEDIUM defensive assertion recommendation → applied
- Code critique 2 (final): No issues

## REQ-2026-005 Overall Status
All 5 phases COMPLETE:
- Phase 1: Guards (RestartLanguageServerTool HTTP guard + pool integrity guard)
- Phase 2: LSP lifecycle utilities (surgical_restart, workspace roots, probe readiness)
- Phase 3: Exception handler rewiring (handle_lsp_termination, apply_ex)
- Phase 4: Integration wiring (SEQ-POOL-05, SEQ-POOL-06)
- Phase 5: Production wiring (factory → bridge lsp_pool)
