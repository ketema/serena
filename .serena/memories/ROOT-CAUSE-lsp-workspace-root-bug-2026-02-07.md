# ROOT CAUSE: LSP Workspace Root Bug

## Status

**FIXED** — Commit `b0561542` (2026-02-07)
- TDD cycle: RED (3 FAIL, 1 PASS) → GREEN (4/4 PASS) → COMMIT
- Constitutional audit: ZERO VIOLATIONS
- Full regression: 228/228 PASSED, 0 FAILED
- Live verification: Confirmed bug exists in running server (old code); server restart needed to deploy fix

## Root Cause

`LanguageServerSymbolRetriever.get_root_path()` at `symbol.py:493-498` returned
`self._explicit_language_server.repository_root_path` (the FIRST workspace, frozen at
LSP creation time) instead of `self.agent.get_active_project_or_raise().project_root`
(ContextVar-based, session-aware).

## Fix

Removed conditional branch. `get_root_path()` now unconditionally delegates to
`self.agent.get_active_project_or_raise().project_root`.

## Files Changed

- `src/serena/symbol.py` — 1 file, 5 deletions (removed conditional branch)
- `tests/test_caller_inv1_get_root_path.py` — NEW (4 tests, 250 lines)

## Contract

`contracts/solidlsp_path_resolution_contract.py` — CALLER-INV-1, POST-CW-2

## Impact

All 5 downstream callsites (symbol.py:537,583,646,669 + code_editor.py:247)
automatically pass the correct session-aware workspace to LSP methods.
