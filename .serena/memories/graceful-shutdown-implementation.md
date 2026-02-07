# REQ-GRACEFUL-SHUTDOWN-001: Graceful LSP Shutdown Implementation

**Status**: COMPLETE (2026-02-07)
**Branch**: ketema
**Commits**: 50b2f977 (implementation), 536a947 (robustness fix)

## Summary
Wired graceful LSP shutdown on HTTP server restart (SIGTERM from launchd).

## Four Gaps Fixed
1. **SEQ-SHUT-01**: SIGTERM handler in `start_mcp_server()` calls `factory.agent.shutdown()` (cli.py)
2. **SEQ-SHUT-02**: `SerenaAgent.shutdown()` calls `self._lsp_pool.stop_all(save_cache=True)` (agent.py)
3. **SEQ-SHUT-03**: `GlobalLanguageServerPool.stop_all()` calls `self.timeout_manager.stop_monitoring()` (global_lsp_pool.py)
4. **SEQ-SHUT-04**: `atexit.register(factory.agent.shutdown)` as fallback (cli.py)

## Contract: contracts/graceful_shutdown_contract.py
- 14 clause IDs: SEQ-SHUT-01..04, INV-SHUT-01..04, POST-SHUT-01..04, ERR-SHUT-01..02
- Tests: tests/test_graceful_shutdown_contract.py (13 tests, 12/14 clauses)

## Key Design Decisions (User-Decided)
- **Idempotency**: threading.Lock + boolean flag (not simple bool, not threading.Event)
- **Signal handler location**: start_mcp_server() CLI entry point (Process Concern, not Domain Concern)

## Robustness Fix (536a947)
- Moved `_shutdown_lock`/`_shutdown_called` to FIRST lines of `__init__` (before failable code)
- Added `hasattr` guard in `shutdown()` for `object.__new__()` bypass case
- Eliminates 21 PytestUnraisableExceptionWarning warnings

## Regression: 328 passed, 6 skipped, 0 failures
