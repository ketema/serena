# TDD Cycle 2.4: SerenaAgent.activate_session_project() - Implementation Plan (v2)

**Date**: 2026-01-12
**Status**: APPROVED - Constitutionally Compliant
**Auditor**: Gemini (Adversarial Mode)
**Branch**: feature/multi-project-support

---

## Executive Summary

This cycle implements the "New Path" for project activation. It adheres to the Strangler Fig pattern by introducing `activate_session_project` alongside the legacy `activate_project`.

**CRITICAL ARCHITECTURAL CHANGE**:
The new method MUST be **stateless** with respect to the Agent instance. It binds the project to the **SessionRegistry**, NOT `self._active_project`. Mutating `self._active_project` would re-introduce the Singleton conflict and break concurrency.

---

## Requirements (Refined)

- **REQ-4**: `activate_session_project(project_name)` binds CURRENT session (from ContextVar).
- **REQ-IDEMPOTENCY**: Multiple calls for same project = no-op.
- **REQ-4b**: Does NOT unbind other sessions.
- **REQ-STATELESS**: Does NOT mutate `self._active_project` (legacy state).
- **REQ-CONFIG**: Resolves project via `self.serena_config.get_project()`.

---

## Behavioral Contract (The Law)

This specification serves as the Contract for the Test Writer. Do NOT create a separate contract file.

```python
def activate_session_project(self, project_name: str) -> None:
    """
    Bind CURRENT session to project workspace.
    
    PRE: project_name exists in self.serena_config.projects
    PRE: Current session exists (from ContextVar) - raises ValueError if not
    
    POST: SessionRegistry.bind_session called with (session_id, project.root)
    POST: Legacy state (self._active_project) is UNTOUCHED
    POST: If session already bound to SAME workspace_root → no-op (idempotent)
    POST: If session bound to DIFFERENT workspace → unbind old, bind new
    
    INV: No side effects on other session_ids
    INV: Thread-safe via SessionRegistry lock
    
    ERRORS:
    - ValueError: No current session (PRE violation)
    - ProjectNotFoundError: project_name not registered
    """
```

---

## Test Specification (8 tests)

**File**: `test/serena/test_agent_session_activation.py`

### 1. test_activate_session_project_binds_registry
- **Given**: Session exists in ContextVar, project registered
- **When**: `activate_session_project("project-name")`
- **Then**: `session_registry.bind_session` called with correct args
- **Enforces**: REQ-4

### 2. test_activate_session_project_preserves_legacy_state
- **Given**: `self._active_project` is None (or "OldProject")
- **When**: `activate_session_project("NewProject")`
- **Then**: `self._active_project` remains unchanged
- **Enforces**: REQ-STATELESS (Critical Concurrency Requirement)

### 3. test_activate_session_project_idempotent
- **Given**: Session already bound to "project-name"
- **When**: Called again
- **Then**: Registry state unchanged (or bind called idempotently)
- **Enforces**: REQ-IDEMPOTENCY

### 4. test_activate_session_project_isolation
- **Given**: Session A bound to Project X
- **When**: Session B calls `activate_session_project("Project Y")`
- **Then**: Session A remains bound to Project X
- **Enforces**: REQ-4b

### 5. test_activate_session_project_rebinds
- **Given**: Session bound to Project X
- **When**: `activate_session_project("Project Y")`
- **Then**: Session bound to Project Y (registry updated)
- **Enforces**: POST (rebind behavior)

### 6. test_raises_without_session
- **Given**: No current session in ContextVar
- **When**: Called
- **Then**: Raises `ValueError("No current session")`
- **Enforces**: PRE (session required)

### 7. test_raises_invalid_project
- **Given**: "InvalidProject" not in config
- **When**: Called
- **Then**: Raises `ProjectNotFoundError`
- **Enforces**: REQ-CONFIG

### 8. test_thread_safety
- **Given**: 10 threads activating different projects for different sessions
- **When**: Concurrent execution
- **Then**: All bind successfully, no state corruption
- **Enforces**: INV (atomicity)

---

## Implementation Steps

| Step | Action | Deliverable |
|------|--------|-------------|
| 1 | ↪ adversarial-test-writer (BLIND) | `test/serena/test_agent_session_activation.py` (8 tests) |
| 2 | Theater check | Verify assertions check Registry, not Agent state |
| 3 | ↪ adversarial-coder (BLIND) | Implement method in `src/serena/agent.py` |
| 4 | Verify | Tests pass + Legacy tests still pass |
| 5 | Commit | "feat: Implement stateless session activation (Cycle 2.4)" |

---

## Approval Checklist

- [x] Contract excludes legacy state mutation (REQ-STATELESS added)
- [x] No new contract file created (Specification embedded)
- [x] Config integration defined (REQ-CONFIG)
- [x] Isolation test included (Test 4)

**Status**: **APPROVED** for Cycle 2.4 execution.