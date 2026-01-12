# TDD Cycle 2.5: SessionAwareToolDispatch Implementation Plan

**Date**: 2026-01-12
**Status**: APPROVED - Constitutionally Compliant
**Auditor**: Gemini (Adversarial Mode)
**Branch**: feature/multi-project-support

---

## Executive Summary

This cycle implements the core routing logic for multi-project support. The `SessionAwareToolDispatch` class serves as the bridge between `SerenaAgent` and `GlobalLanguageServerPool`. It replaces the direct `LanguageServerManager` usage for sessions that are bound to the `SessionRegistry`.

**Adversarial Strategy**:
The `adversarial-test-writer` must verify that the dispatcher strictly honors session boundaries and correctly delegates to the `GlobalLanguageServerPool`. It must NOT allow cross-session contamination.

---

## Requirements (Refined)

- **REQ-5**: `dispatch_lsp_tool` correctly identifies current session context.
- **REQ-5a**: If session is bound, resolves `workspace_root` from `SessionRegistry`.
- **REQ-5b**: Acquires LSP from `GlobalLanguageServerPool` using (Language, workspace_root).
- **REQ-5c**: Executes tool on the acquired LSP.
- **REQ-5d**: Releases LSP reference after execution (critical for idle reclamation).
- **REQ-PERF-1**: Path validation overhead < 10ms.
- **REQ-FALLBACK**: If no session context (CLI mode), raises specific error (or delegates to legacy if configured - *Design Decision: New dispatcher handles bound sessions only. Legacy fallback happens in `SerenaAgent` call site.*)

---

## Behavioral Contract (The Law)

**File**: `contracts/session_tool_dispatch_contract.py` (Update or Create)

```python
def dispatch_lsp_tool(
    self,
    session_id: str,
    tool_name: str,
    tool_args: dict
) -> Any:
    """
    Route an LSP tool request to the correct isolated instance.

    PRE: session_id exists in SessionRegistry
    PRE: tool_name is valid LSP tool
    
    POST: Retrieves workspace_root for session_id from Registry
    POST: Acquires LSP from GlobalPool for (Language, workspace_root)
    POST: Executes tool_name(tool_args) on the LSP instance
    POST: Releases LSP back to GlobalPool immediately after execution
    
    INV: Thread-safe execution
    INV: No cross-talk between sessions (verified by workspace_root check)
    
    ERRORS:
    - SessionNotFoundError: if session_id not bound
    - ToolExecutionError: if LSP fails
    """
```

---

## Test Specification (6 tests)

**File**: `test/serena/test_session_tool_dispatch.py`

### 1. test_dispatch_routes_to_correct_workspace
- **Given**: Session A -> /project-a, Session B -> /project-b
- **When**: dispatch(session_a, "definition", ...)
- **Then**: LSP acquired for /project-a (Verified via mock pool spy)
- **Enforces**: REQ-5a, REQ-5b

### 2. test_dispatch_releases_lsp_after_execution
- **Given**: Tool execution completes
- **When**: dispatch returns
- **Then**: pool.release() called exactly once
- **Enforces**: REQ-5d (Leak prevention)

### 3. test_dispatch_handles_lsp_acquisition_failure
- **Given**: Pool.acquire raises Error
- **When**: dispatch called
- **Then**: Propagates error, does NOT attempt execute or release
- **Enforces**: Error handling robustness

### 4. test_dispatch_handles_tool_execution_failure
- **Given**: LSP.execute raises Error
- **When**: dispatch called
- **Then**: Propagates error AND calls pool.release()
- **Enforces**: REQ-5d (Release on error - try/finally block requirement)

### 5. test_path_validation_performance (REQ-PERF-1)
- **Given**: Valid session and tool args
- **When**: dispatch called 1000 times
- **Then**: Overhead < 10ms per call
- **Enforces**: REQ-PERF-1

### 6. test_missing_session_raises_error
- **Given**: Invalid session_id
- **When**: dispatch called
- **Then**: Raises SessionNotFoundError
- **Enforces**: Contract PRE condition

---

## Implementation Steps

| Step | Action | Deliverable |
|------|--------|-------------|
| 1 | Update Contract | `contracts/session_tool_dispatch_contract.py` |
| 2 | ↪ adversarial-test-writer (BLIND) | `test/serena/test_session_tool_dispatch.py` |
| 3 | Theater Check | Verify mock spies verify *arguments*, not just *called* |
| 4 | ↪ adversarial-coder (BLIND) | `src/serena/session_tool_dispatch.py` |
| 5 | Run Tests | GREEN validation |
| 6 | AI Panel Critique | Concurrency/Leak check |
| 7 | Commit | "feat: Implement SessionAwareToolDispatch (Cycle 2.5)" |

---

## Approval Checklist

- [ ] Requirements cover lifecycle (Acquire -> Execute -> Release)
- [ ] Leak prevention explicitly tested (Test 2, Test 4)
- [ ] Performance gate included (Test 5)
- [ ] Adversarial separation enforced (Sub-agents)

**User approval required before M4 execution.**
