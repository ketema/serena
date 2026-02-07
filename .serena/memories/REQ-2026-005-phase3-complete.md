# REQ-2026-005 Phase 3 Complete

## Phase: Exception Handler Rewiring
## Status: GREEN — All tests passing
## Date: 2026-02-07

## Implementation Summary

### handle_lsp_termination() on SerenaAgent (agent.py:817-885)
- Calls surgical_restart_lsp(language) on pool
- Calls probe_workspace_readiness(new_lsp, workspace_root, 5.0)
- Calls retry_fn() on success
- Returns error string on LSPRestartError (ERRORS-TEH-01)
- Returns error string on retry termination (ERRORS-TEH-02, max 1 retry)
- Full contract traceability: POST-TEH-01 through POST-TEH-05, INV-TEH-01/02/03

### apply_ex() rewiring (tools_base.py:282-310)
- Replaced: self.agent.reset_language_server() + direct retry
- With: self.agent.handle_lsp_termination(language, workspace_root, retry_fn)
- Type-safe: isinstance guard for LanguageServerTerminatedException cause
- Null-safe: project None check before Path() wrap
- Thread-safe: frozen kwargs snapshot for retry closure

### LSPRestartError (global_lsp_pool.py:52-59)
- Moved from contracts/ to production code
- Used by surgical_restart_lsp failure → handle_lsp_termination catches

## Commits
- 753141a6: Phase 3 GREEN - handle_lsp_termination + apply_ex rewiring
- 25a1002b: AI Panel critique fixes - type safety, null reference, exception ordering

## Test Evidence
- 6 Phase 3 integration tests (test_phase3_exception_handler_integration.py)
- 73/73 total REQ-2026-005 tests passing
- Zero regression

## Contract Coverage
- SEQ-TEH-01: apply_ex → handle_lsp_termination (tested)
- SEQ-TEH-02: handle_lsp_termination → surgical_restart_lsp (tested)
- INV-TEH-01: NO reset_language_server calls (tested)
- POST-TEH-03: retry returns result (tested)
- ERRORS-TEH-01: restart failure returns error (tested)
- ERRORS-TEH-02: retry failure returns error, max 1 retry (tested)

## AI Panel
- conversation_id: ba62fe9e-d5ae-493d-9832-dbcb194cce3d
- 3 CRITICAL issues found and fixed
- HIGH: timeout hardcoding noted as future improvement (YAGNI)
- HIGH: kwargs closure fixed with frozen snapshot

## Remaining Phases
- Phase 4: on_transport_session_closed → pool.release(), acquire() readiness gate
