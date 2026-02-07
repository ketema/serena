# Logging Observability Batch C - RED Phase Complete

**Date**: 2026-02-07  
**Contract**: contracts/logging_observability_contract.py  
**Test File**: tests/test_logging_observability_batch_c.py

## Scope

**9 contract clauses tested across 11 test methods**:
- **Tier 5 (Tool Dispatch)**: LOG-DISP-01, LOG-DISP-02
- **Tier 6 (Security)**: LOG-SEC-01, LOG-SEC-02
- **Tier 7 (Infrastructure)**: LOG-TMO-01, LOG-TMO-02, LOG-TMO-03, LOG-RST-01, LOG-RST-02

## Test Execution Summary

```
poetry run pytest tests/test_logging_observability_batch_c.py -v
```

**Result**: 11/11 tests FAILED (RED phase success)

All failures are expected:
```
E   AssertionError: no logs of level {DEBUG|WARNING|INFO} triggered on {module}
```

## CL12 Compliance Checklist

- [x] Contract Authority Record (CAR) extracted — 9 clauses
- [x] Clause registry built with POST-only clauses (logging contracts)
- [x] CL12-B consistency check passed (no contradictions)
- [x] Every test cites clause ID in docstring (CL12-E)
- [x] Every assertion references clause ID in error message (CL12-E)
- [x] 5-point error messages implemented (What/Why/Expected/Actual/Guidance)
- [x] Observable enforcement testing (CL12-A) — log levels verified
- [x] Theater test check passed (all tests fail if logging missing)
- [x] No mocks without verified contracts (CL10) — only mocking dependencies
- [x] Clause coverage report: 9/9 clauses covered

## Test Structure

### Tier 5: Tool Dispatch (2 tests)
- `test_log_disp_01_tool_dispatched` — DEBUG log with session/tool/category
- `test_log_disp_02_path_validated` — DEBUG log on successful validation

### Tier 6: Security Boundary (2 tests)
- `test_log_sec_01_boundary_violation` — WARNING on path traversal
- `test_log_sec_02_resolution_failure` — WARNING on broken symlink

### Tier 7: Infrastructure (7 tests)
- `test_log_tmo_01_monitor_started` — INFO log when monitoring starts
- `test_log_tmo_01_already_active` — DEBUG log when already monitoring
- `test_log_tmo_02_monitor_stopped` — INFO log when monitoring stops
- `test_log_tmo_02_not_active` — DEBUG log when not monitoring
- `test_log_tmo_03_reclamation_logs` — INFO per reclaimed language + summary
- `test_log_rst_01_http_mode_blocked` — INFO when HTTP mode blocks restart
- `test_log_rst_02_stdio_restart` — INFO before STDIO restart

## Implementation Targets (GREEN Phase)

### Files to Modify:
1. `src/serena/session_tool_dispatch.py` — Add logger, implement LOG-DISP-01/02
2. `src/serena/path_validation.py` — Add logger, implement LOG-SEC-01/02
3. `src/serena/lsp_timeout.py` — Implement LOG-TMO-01/02/03 (logger already exists)
4. `src/serena/tools/symbol_tools.py` — Implement LOG-RST-01/02

### Logger Initialization Required:
- `serena.session_tool_dispatch`: `logger = logging.getLogger(__name__)` (NEW)
- `serena.path_validation`: `logger = logging.getLogger(__name__)` (NEW)
- `serena.lsp_timeout`: Already has logger
- `serena.tools.symbol_tools`: Uses `log = logging.getLogger(__name__)` (existing)

## Lessons from Batch B Applied

✅ **Constructor signature verified** — LSPTimeoutManager uses `check_interval`, not `check_interval_seconds`  
✅ **Attribute names verified** — `_timeout_config`, not `_timeouts`  
✅ **Directory cleanup** — Used `shutil.rmtree()` for broken symlink cleanup  
✅ **macOS path resolution** — Used `str(path.resolve())` for path comparisons  
✅ **Logger names verified** — Module name, not variable name  
✅ **Actual import paths checked** — All imports validated against source  

## Theater Test Detection

All tests pass the theater test question:
- **"Can implementation be wrong and test pass?"** → NO
- All tests verify absence of logs → implementation MUST emit logs to pass
- Log level verified (DEBUG vs INFO vs WARNING)
- Log message content verified (session ID, language, paths)
- Exact log counts verified (1 per event, not 0 or 2+)

## Next Steps

→ **GREEN Phase**: Implement 9 logging clauses across 4 files  
→ Verify all 11 tests pass after implementation  
→ Run full test suite to ensure no regressions
