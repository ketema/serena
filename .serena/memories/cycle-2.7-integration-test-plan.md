# CONSTITUTIONAL IMPLEMENTATION PLAN: Cycle 2.7 - End-to-End Integration Test

**Date**: 2026-01-12
**Status**: DRAFT
**Role**: Orchestrator
**Branch**: feature/multi-project-support

---

## 1. Objective & Philosophy
Verify the complete Phase 2 architecture ("The New Path") under real-world concurrent load.
This is the **Final Gate** for Phase 2.

**Philosophy**: "Trust but Verify". We have tested components in isolation. Now we test the assembly without mocks.

**Constitutional Adherence**:
- **Real Components**: No mocks allowed for Registry, Pool, or Dispatcher.
- **Concurrency**: Must verify thread-safety and isolation under load.
- **Observability**: Verification of structured logging in the wild.

---

## 2. Requirements (Integration)

- **REQ-INT-1 (Stack Integrity)**: `SerenaAgent` -> `SessionAwareToolDispatch` -> `GlobalLSPPool` -> `SolidLanguageServer` chain works for real requests.
- **REQ-INT-2 (Concurrent Isolation)**: Multiple sessions (threads) operating on different projects MUST NOT see each other's state or files.
- **REQ-INT-3 (Log Attribution)**: Interleaved logs from concurrent sessions MUST be correctly prefixed.
- **REQ-INT-4 (Resource Lifecycle)**: LSPs must be started on demand and released after use. No "zombie" processes.

---

## 3. Test Specification (RED Phase)

**File**: `test/serena/test_integration_concurrency.py`

### Test Scenario: `test_concurrent_multi_project_workflow`

1.  **Setup**:
    - Initialize `SessionRegistry`, `GlobalLanguageServerPool`.
    - Initialize `SerenaAgent` (or Dispatcher) with these real components.
    - Create 2 dummy projects on disk (`project_a`, `project_b`) with valid config and 1 source file each.

2.  **Execution (Concurrent)**:
    - Spawn **Thread A** (Session A):
        - `activate_session_project("project_a")`
        - Loop 10x: `dispatch_lsp_tool(..., "definition", ...)`
    - Spawn **Thread B** (Session B):
        - `activate_session_project("project_b")`
        - Loop 10x: `dispatch_lsp_tool(..., "definition", ...)`

3.  **Assertions (The "Check")**:
    - **Success**: All operations return valid results (not exceptions).
    - **Isolation**: Thread A never sees Project B's root in its context (verified via logs or result path).
    - **Logging**: Capture root logger. Verify `[Session: A]...` and `[Session: B]...` lines exist and are not mixed (e.g. A's message with B's prefix).
    - **LSP Pool**: Verify `pool.get_pool_stats()` shows correct active/idle counts during/after execution.

---

## 4. Execution Plan

1.  **RED Phase**: Write `test/serena/test_integration_concurrency.py`.
    - *Constraint*: Use `DummyLanguageServer` or a lightweight real LSP (like `pylsp` if available, or just mocking the *process* launch if full LSP is too heavy for CI, but plan says "REAL components". We should use `SolidLanguageServer` but maybe point it to a simple python script).
    - *Refinement*: To avoid external dependency flakiness, we can use `SolidLanguageServer` configured to run a simple echo script (acting as an LSP) or use the `MockLSP` class *if and only if* it exercises the full `SolidLanguageServer` wrapping logic.
    - *Decision*: Use **Real** `SolidLanguageServer` logic but executing a local python script `python -m test.resources.simple_lsp` to ensure deterministic behavior without needing `npm install` etc.

2.  **GREEN Phase**: Run the test.
    - If it passes: Success.
    - If it fails: Fix the integration bugs (Race conditions, lock contention, etc.).

3.  **Audit**: Verify log output and resource cleanup.

---

## 5. Audit Gates

- [ ] Does the test use `threading` or `concurrent.futures`?
- [ ] Are `SessionRegistry` and `GlobalLSPPool` real instances?
- [ ] Is structured logging verified?
