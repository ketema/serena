# Phase 2: The New Path & Observability Implementation Plan (v2.1)

**Date**: 2026-01-12
**Status**: APPROVED
**Roadmap**: `multi-project-refactoring-roadmap-v2.md`
**Critique**: AI Panel (Claude-Sonnet) - 2026-01-12T15:08Z
**Goal**: Implement session-aware routing and observability WITHOUT breaking existing behavior (Strangler Fig).

## Constitutional Requirements

**CL6 & M4 MANDATE**: All TDD cycles MUST use adversarial sub-agents.
**CL10 MANDATE**: All mocks must derive from verified contracts.

## TDD Cycle Overview

| Cycle | Description | Sub-Agent |
|-------|-------------|-----------|
| 2.1 | `SessionRegistry.get_session_overview()` (Observability) | adversarial-test-writer → adversarial-coder |
| 2.2 | `GlobalLanguageServerPool.get_pool_stats()` (Observability) | adversarial-test-writer → adversarial-coder |
| 2.3 | Dashboard API endpoints (`/get_session_overview`, `/get_lsp_pool_stats`) | adversarial-test-writer → adversarial-coder |
| 2.4 | `SerenaAgent.activate_session_project()` (New Path) | adversarial-test-writer → adversarial-coder |
| 2.5 | `SessionAwareToolDispatch` Implementation | adversarial-test-writer → adversarial-coder |
| 2.6 | Structured Logging (`[Session: ID]`) | adversarial-test-writer → adversarial-coder |
| 2.7 | End-to-End Integration Test (Real Concurrency) | adversarial-test-writer → adversarial-coder |
| Gate | All Phase 2 tests pass + Observability verified | coordinator |

---

## TDD Cycle 2.1: Session Registry Observability

### Cycle 2.1 - RED: Contract & Tests

**Invoke**: ↪ adversarial-test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- REQ-API-1: `get_session_overview()` returns list of active sessions.
- **REQ-CONCURRENCY-1 (AI Panel)**: Must return **Point-in-Time Snapshot** (deepcopy).
- **REQ-CONCURRENCY-2**: Must use `RLock` (read lock) during iteration to prevent `RuntimeError: dictionary changed size`.

**Contract Update**:
- Update `SessionRegistryContract`.

### Cycle 2.1 - GREEN: Implementation

**Invoke**: ↪ adversarial-coder | 🚫 test source | ✓ error messages

---

## TDD Cycle 2.2: LSP Pool Observability

### Cycle 2.2 - RED: Contract & Tests

**Invoke**: ↪ adversarial-test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- REQ-API-2: `get_pool_stats()` returns active LSPs.
- **REQ-LEAK-TEST (AI Panel)**: Verify `get_pool_stats()` does NOT increment ref_count or prevent GC.

**Contract Update**:
- Update `GlobalLanguageServerPoolContract`.

### Cycle 2.2 - GREEN: Implementation

**Invoke**: ↪ adversarial-coder | 🚫 test source | ✓ error messages

---

## TDD Cycle 2.3: Dashboard API

### Cycle 2.3a - RED: Unit Tests (Mocked)

**Invoke**: ↪ adversarial-test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- `GET /get_session_overview` -> 200 OK (JSON)
- Mock registry/pool to isolate API logic.

### Cycle 2.3b - RED: Integration Tests (Real) (AI Panel Recommendation)

**Requirements**:
- Real Flask test client with real (test) Registry/Pool.
- Verify JSON serialization of actual data objects.

### Cycle 2.3 - GREEN: Flask Routes

**Invoke**: ↪ adversarial-coder | 🚫 test source | ✓ error messages

---

## TDD Cycle 2.4: Session-Aware Activation

### Cycle 2.4 - RED: Agent Activation Tests

**Invoke**: ↪ adversarial-test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- REQ-4: `activate_session_project(project_name)` binds CURRENT session.
- **REQ-IDEMPOTENCY (AI Panel)**: Multiple calls for same project = no-op.
- REQ-4b: Does NOT unbind other sessions.

### Cycle 2.4 - GREEN: Implementation

**Invoke**: ↪ adversarial-coder | 🚫 test source | ✓ error messages

---

## TDD Cycle 2.5: Tool Dispatch

### Cycle 2.5 - RED: Dispatcher Tests

**Invoke**: ↪ adversarial-test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- REQ-5: `dispatch_lsp_tool` routing flow.
- **REQ-PERF-1 (AI Panel)**: Path validation must be fast (<10ms).

### Cycle 2.5 - GREEN: Implementation

**Invoke**: ↪ adversarial-coder | 🚫 test source | ✓ error messages

---

## TDD Cycle 2.6: Structured Logging

### Cycle 2.6 - RED: Log Format Tests

**Invoke**: ↪ adversarial-test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- REQ-LOG: Logs inside `run_with_session_context` have `[Session: <id>]` prefix.
- **REQ-LOG-RACE (AI Panel)**: Test with 3 concurrent sessions. Verify log lines map to correct ID even with interleaving.

### Cycle 2.6 - GREEN: Implementation

**Invoke**: ↪ adversarial-coder | 🚫 test source | ✓ error messages

---

## Phase 2 Gate Criteria

- [ ] Observability methods are thread-safe (snapshot isolation).
- [ ] No memory leaks in stats collection.
- [ ] Logging is race-condition free.
- [ ] Dispatch latency < 10ms overhead.
- [ ] Dashboard API endpoints functional.