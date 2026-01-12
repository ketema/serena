# TDD Cycle 2.6: Structured Logging Implementation Plan

**Date**: 2026-01-12
**Status**: DRAFT (for audit)
**Branch**: feature/multi-project-support

---

## Objective
Implement structured logging so that logs emitted within session context include a deterministic session prefix. This must be concurrency-safe and preserve existing logging behavior.

---

## Requirements (from Phase 2)

- **REQ-LOG**: Logs inside `run_with_session_context` must include `[Session: <id>]` prefix.
- **REQ-LOG-RACE (AI Panel)**: With 3 concurrent sessions, log lines must map to the correct session ID even under interleaving.

---

## Behavioral Contract Update (MANDATORY)

**File**: `contracts/session_registry_contract.py` or `contracts/mcp_session_bridge_contract.py` (confirm owner of `run_with_session_context`).

**Contract Addition** (example for `run_with_session_context`):
```
PRE: session_id is bound in SessionRegistry
PRE: callable is valid
POST: All logs emitted in this context include prefix "[Session: <session_id>]"
INV: Prefix applies only within the current session scope
INV: Concurrent sessions do not leak prefixes across threads
ERRORS:
- SessionNotFoundError: if session_id not bound
```

---

## Test Specification (RED phase)

**File**: `test/serena/test_structured_logging.py`

1. **test_logs_prefixed_for_session**
   - Given: bound session
   - When: `run_with_session_context` logs a message
   - Then: log line starts with `[Session: <id>]`
   - Enforces: REQ-LOG

2. **test_logs_unprefixed_outside_session**
   - Given: no session context
   - When: logger emits
   - Then: no session prefix
   - Enforces: scope isolation

3. **test_concurrent_sessions_do_not_cross_contaminate**
   - Given: 3 sessions in parallel, each logs N messages
   - When: interleaved logging
   - Then: each line maps to the correct session id
   - Enforces: REQ-LOG-RACE

4. **test_nested_session_context_restores_previous**
   - Given: session A context, enter session B context, exit
   - Then: logs return to A prefix
   - Enforces: INV (scope restoration)

---

## Implementation Steps (GREEN phase)

1. Identify owner of `run_with_session_context` and its logger plumbing.
2. Implement context-aware prefixing (thread-local or contextvar).
3. Ensure prefix is applied only inside session context (scope restoration).
4. Ensure concurrent sessions isolated (no shared mutable global prefix).

---

## Theater Test Checks

- Each test asserts concrete log line contents (exact prefix + message).
- Concurrent test validates every line maps to its session id (no generic presence-only checks).

---

## Approval Checklist

- [ ] Contract updated with PRE/POST/INV
- [ ] Tests written by adversarial test-writer (blind)
- [ ] No global state used for prefixes (thread-safe)
- [ ] Concurrent test covers interleaving
