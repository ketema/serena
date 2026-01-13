# Cycle 3.3 RED Phase Complete

**Date**: 2026-01-12
**Branch**: feature/multi-project-support
**Phase**: M4.2 RED - COMPLETE

## Test Results (3 FAIL)

### FAILED Tests (Target for GREEN phase)

1. **test_activate_project_delegates_when_session_present**
   - AttributeError: 'SerenaAgent' object has no attribute 'activate_project'
   - REQ-5b: Legacy activate_project() should delegate to activate_session_project() when session context exists

2. **test_activate_project_backwards_compatible**
   - AttributeError: 'SerenaAgent' object has no attribute 'activate_project'
   - REQ-BACKWARDS-COMPAT: Legacy single-session behavior preserved without session context

3. **test_activate_project_unknown_project_raises**
   - AttributeError: 'SerenaAgent' object has no attribute 'activate_project'
   - REQ-CONFIG: ProjectNotFoundError for unknown project names

## Error Messages for GREEN Phase Coder

All tests fail with same root cause:
```
AttributeError: 'SerenaAgent' object has no attribute 'activate_project'
```

## Implementation Required

Add `activate_project(self, project_name: str)` method to SerenaAgent:
- If `_current_session_id` is set: delegate to `activate_session_project()`
- If no session context: activate project without session binding (legacy behavior)
- Raise ProjectNotFoundError for unknown project names

## Next Step

Proceed to Cycle 3.4 GREEN phase - implement Legacy Shim in src/serena/agent.py
