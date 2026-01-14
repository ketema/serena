# Constitutional Refactor: Dashboard Observability Interface

**Date**: 2026-01-14
**Branch**: feature/multi-project-support
**Commit**: 3f22121b

## Summary

Implemented dashboard multi-project observability interface via full constitutional-refactor 6-phase workflow.

## Problem

Dashboard `/get_session_overview` endpoint returned 500 error because `SerenaAgent._session_registry` was private and not exposed for dashboard queries.

## Solution

**Phase 1 (Discovery)**: Identified DISCONNECT MATRIX - EXPECTED public properties, OBSERVED private attributes

**Phase 2 (Bridge)**: Added bridge properties to `SerenaAgent`:
- `session_registry` property exposes `_session_registry`
- `lsp_pool` property exposes `_lsp_pool`

**Phase 3 (Contracts)**: Created `contracts/serena_agent_observability_contract.py` with 10 CL12 clauses:
- PRE-OBS-01: Agent initialization
- POST-OBS-01/02: Property return types
- POST-OBS-03/04: Response structures
- INV-OBS-01/02/03/04: Read-only, availability, encapsulation, thread-safety
- ERRORS-OBS-01: Exception suppression

**Phase 4 (RED)**: Created 25 adversarial tests via `/adversarial-test-writer`

**Phase 5 (GREEN)**: Implementation via `/adversarial-coder` with iteration cycle to fix test fixtures

**Phase 6 (Audit)**: Constitutional audit returned ZERO VIOLATIONS

## Key Implementation Details

### Exception Handling Pattern (ERRORS-OBS-01)
Both `SessionRegistry.get_session_overview()` and `GlobalLanguageServerPool.get_stats()` have try/except wrapping:
```python
try:
    with self._lock:
        # iteration over internal state
        return {"sessions": ..., "total_count": ...}
except Exception:
    return {"sessions": [], "total_count": 0}
```

### Theater Test Fix
Initial fixtures used mocks with `side_effect=Exception` which bypassed real exception handling. Fixed by using real implementations with corrupted internal state to exercise actual try/except code paths.

## Files Changed

- `src/serena/agent.py` - Bridge properties
- `src/serena/session_registry.py` - get_session_overview with contract
- `src/serena/global_lsp_pool.py` - get_stats with contract
- `contracts/serena_agent_observability_contract.py` - CL12 contract (NEW)
- `test/serena/test_serena_agent_observability_contract.py` - 25 tests (NEW)

## Test Results

```
25 passed, 1 warning in 2.39s
```

## Constitutional Compliance

- CL12: All public methods have PRE/POST/INV/ERRORS in docstrings
- CL12-E: All tests cite clause IDs in docstrings
- CL10: No traditional mocks - test doubles for exception injection verified
- Theater Detection: All tests assert measurable, deterministic properties

## Lessons Learned

1. **Bridge pattern** effective for constitutional refactoring - exposes internal state temporarily to understand requirements before formal contract
2. **Theater test detection** critical - mocks implementing exception handling in fixture don't test actual implementation
3. **CorruptedDict pattern** useful for testing exception paths without mocking entire objects
