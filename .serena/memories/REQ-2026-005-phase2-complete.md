# REQ-2026-005 Phase 2 Complete

## Date: 2026-02-07

## Phase 2 Scope (COMPLETE)
- `GlobalLanguageServerPool.surgical_restart_lsp(language)` — restart single LSP, preserve workspace roots + session refs
- `GlobalLanguageServerPool.get_workspace_roots_for_language(language)` — read-only query
- `probe_workspace_readiness(lsp, root, timeout_seconds)` — module-level function, polls documentSymbol

## Commits
- db65fd21: Implementation (surgical_restart_lsp, get_workspace_roots_for_language, probe_workspace_readiness)
- 715de78: Test mock fix (adapter chain wiring)

## Implementation Location
- src/serena/global_lsp_pool.py lines 383-450 (pool methods) and 566-629 (probe function)
- Tests: tests/test_phase2_surgical_restart_integration.py (12 tests)

## Contract Clauses Enforced
- SurgicalRestartContract: POST-SR-01/03/04/05, INV-SR-01, SEQ-SR-01
- get_workspace_roots: POST-SR-GWR-01/02
- WorkspaceReadinessContract: POST-WR-01/02, ERRORS-WR-01, INV-WR-02

## Known Future Improvements
- AI Panel flagged: Pool lock held during long operations (stop, create, add_workspace_root). Contract suggests two-phase lock for contention reduction. Tests don't require this optimization.
- Pyright warnings: workspace_roots attribute not in SolidLanguageServer type stubs

## Test Results
- 12/12 Phase 2 tests pass
- 76/76 total REQ-2026-005 tests pass (zero regression)

## Remaining Phases
- Phase 3: handle_lsp_termination(), apply_ex() exception handler rewiring (NOT APPROVED YET)
- Phase 4: on_transport_session_closed → pool.release(), acquire() readiness gate (NOT APPROVED YET)
