# CONSTITUTIONAL IMPLEMENTATION PLAN: Cycle 2.6 - Structured Logging

**Date**: 2026-01-12
**Status**: AUDITED & APPROVED (Constitutional)
**Role**: Orchestrator (READ ONLY)
**Branch**: feature/multi-project-support

---

## 1. Objective & Philosophy
Implement session-aware structured logging. Every log record emitted within a session context MUST be traceable to its originating session. 

**Constitutional Adherence**:
- **CL6 (TDD)**: RED -> GREEN -> COMMIT cycle.
- **QS1 (Genuine Tests)**: Zero-tolerance for theater tests.
- **Contract Driven**: Docstrings are the Law.

---

## 2. Behavioral Contract (The Law)

**File**: `src/serena/mcp_session_bridge.py`
**Target**: `MCPSessionBridge.run_with_session_context`

```python
def run_with_session_context(self, session_id: str, func: Callable) -> Any:
    """
    Execute func within a session-bound logging context.

    PRE: session_id is non-empty string.
    PRE: func is callable.
    
    POST: All logging.LogRecords emitted by func (including descendants)
          MUST contain a 'session_id' attribute equal to session_id.
    POST: The log format MUST include "[Session: {session_id}]" prefix.
    POST: On function exit (success or failure), the logging context MUST 
          be restored to its previous state (Leak Prevention).
    
    INV: Concurrency Safety: Session prefixes MUST NOT leak across 
         threads or asyncio tasks.
    INV: Zero Side Effects: Code outside this context must remain unprefixed.

    SIDE EFFECT: Modifies the current thread/task ContextVar state.
    """
```

---

## 3. Adversarial TDD Specification

### RED Phase: Test Specification (6 Points)
**Agent**: CODEX (Blind to implementation)
**File**: `test/serena/test_structured_logging.py`

**Test Requirements**:
1. **test_logs_prefixed_for_session**: Verify `[Session: ABC]` is present in captured logs inside context.
2. **test_logs_unprefixed_outside_session**: Verify NO prefix is present before/after context.
3. **test_cleanup_on_failure**: Verify prefix is removed even if `func` raises `RuntimeError`. (MANDATORY `try...finally` verification).
4. **test_concurrent_independence**: 
   - Launch 3 threads/tasks simultaneously.
   - Each logs 10 unique messages.
   - Assert 100% mapping accuracy (No interleaving corruption).
5. **test_nested_session_restoration**: 
   - Session A -> Enter Session B -> Exit Session B.
   - Assert logs in A are prefixed A, logs in B are prefixed B, logs after B are prefixed A.

**Failure Format (MANDATORY)**:
Every test MUST use the 5-point failure message (WHAT, WHY, EXPECTED, ACTUAL, GUIDANCE).

---

## 4. Implementation Architecture (The GREEN Phase)

1. **State Management**: Use `contextvars.ContextVar` to store the active `session_id`.
2. **Injection Mechanism**: Implement a `logging.Filter` attached to the root logger or handlers.
   - Filter reads `ContextVar`.
   - If `session_id` set -> injects `record.session_id`.
3. **Formatting**: Update the `logging.Formatter` to include `[Session: %(session_id)s]` if the attribute exists (use a safe formatting string like `%(session_id)s` with a filter fallback).
4. **Lifecycle**: Use `ContextVar.set()` and `token.reset()` inside `run_with_session_context` wrapped in `try...finally`.

---

## 5. Audit Gates (Coordinator Action)

### Gate 1: RED Audit (M4.2)
- [ ] Do tests use exact values for prefixes?
- [ ] Is `test_cleanup_on_failure` present?
- [ ] Do concurrent tests verify 100% attribution?

### Gate 2: GREEN Audit (M4.5)
- [ ] Is `try...finally` used for `token.reset()`?
- [ ] Is `ContextVar` used (not `threading.local` or global)?
- [ ] Is the `logging.Filter` performant (no expensive lookups)?

---

## 6. Execution Command for Agent

"Read `.serena/memories/CONSTITUTIONAL-PLAN-cycle-2.6.md`. Execute RED Phase. Write tests to `test/serena/test_structured_logging.py`. Use exact behavioral assertions. Send 'TESTS WRITTEN' when done for audit."
