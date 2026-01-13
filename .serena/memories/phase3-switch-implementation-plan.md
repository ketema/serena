# Phase 3: The Switch - Implementation Plan (v2, AI-Panel Addressed)

**Date**: 2026-01-12
**Status**: DRAFT
**Branch**: feature/multi-project-support
**Source**: multi-project-refactoring-roadmap-v2.md (Phase 3)

---

## 1. Objective
Migrate MCP activation to the new session-aware path while preserving legacy APIs via a shim, and prove concurrent multi-client isolation with real integration tests.

---

## 2. Phase 3 Requirements (from Roadmap)

- **REQ-4b**: `mcp.py` uses `activate_session_project()` for MCP clients.
- **REQ-5b**: Legacy `activate_project()` delegates to the new path.
- **REQ-6**: Real integration tests prove concurrent multi-client isolation and lifecycle safety.

---

## 3. Contract Updates (MANDATORY, CL12)

### 3.1 SerenaMCPFactory Activation Contract
**File**: `src/serena/mcp.py` (exact method to be confirmed)
```
PRE: MCP session context exists when activation is invoked.
POST: Activation uses activate_session_project() for MCP clients.
INV: No other sessions are unbound or modified.
ERRORS: ValueError if no current session.
```

### 3.2 SerenaAgent.activate_project Contract (Shim)
**File**: `src/serena/agent.py`
```
PRE: project_name exists in config.
POST: Delegates to activate_session_project() when session context exists.
POST: Legacy API surface preserved (no breaking signature changes).
INV: No cross-session side effects.
ERRORS: ProjectNotFoundError for unknown project.
```

### 3.3 SessionRegistry Contract Touchpoints
**File**: `contracts/session_registry_contract.py`
```
PRE: session_id non-empty; workspace_root exists.
POST: bind_session records mapping for session_id.
POST: get_session returns correct workspace_root snapshot.
INV: bind/unbind do not affect other session_ids.
ERRORS: SessionNotFoundError on missing session_id.
```

### 3.4 Session-Aware Dispatcher Contract
**File**: `contracts/session_tool_dispatch_contract.py`
```
PRE: session_id exists in registry; tool_name valid.
POST: Retrieves workspace_root for session_id.
POST: Acquires LSP, executes tool, releases LSP.
INV: No cross-session leakage; release occurs even on error.
ERRORS: SessionNotFoundError, ToolExecutionError.
```

---

## 4. Test Environment (Integration)

- **Isolation**: Each client uses its own temp workspace (`tempfile.TemporaryDirectory`).
- **Cleanup**: Always use context managers; verify cleanup in teardown.
- **Concurrency Model**: `threading.Thread` for concurrent clients (explicit, deterministic).
- **Observability**: Verify isolation by checking resolved file paths and registry state snapshots, not just method calls.

---

## 5. Legacy Compatibility Surface (Regression Targets)

- `SerenaAgent.activate_project()` behavior unchanged for CLI/non-session usage.
- Existing single-session flows still work without registry interference.
- Error messages for invalid project names remain consistent.

---

## 6. Atomic TDD Cycles (RED -> GREEN)

### Cycle 3.1 - RED: MCP Switch Tests (REQ-4b)
**File**: `test/serena/test_mcp_activation_switch.py`
**Tests**:
1. `test_mcp_uses_activate_session_project`
   - Given: MCP client session established
   - When: activation is triggered via factory
   - Then: `SessionRegistry.get_session(session_id)` resolves to project root
2. `test_cli_path_still_works`
   - Given: non-MCP invocation
   - When: legacy activation path is used
   - Then: existing CLI flow succeeds without session context
3. `test_missing_session_raises`
   - Given: no session in context
   - When: activation invoked
   - Then: ValueError (or defined error) raised

**Theater Check**: Assertions verify registry state or concrete errors, not only call counts.

### Cycle 3.2 - GREEN: Implement MCP Switch (REQ-4b)
- Update `mcp.py` to call `activate_session_project()` for MCP client activation.
- Preserve non-MCP/CLI behavior.

### Cycle 3.3 - RED: Legacy Shim Tests (REQ-5b)
**File**: `test/serena/test_agent_legacy_shim.py`
**Tests**:
1. `test_activate_project_delegates_when_session_present`
   - Verify registry binding for current session
2. `test_activate_project_backwards_compatible`
   - Verify legacy single-session behavior preserved
3. `test_activate_project_unknown_project_raises`
   - Verify ProjectNotFoundError is raised

**Theater Check**: Verify registry mapping + explicit error types.

### Cycle 3.4 - GREEN: Implement Legacy Shim (REQ-5b)
- Refactor `SerenaAgent.activate_project()` to delegate to `activate_session_project()` when session context exists.
- Preserve legacy behavior for non-session contexts.

### Cycle 3.5 - RED: Real Integration Tests (REQ-6)
**File**: `test/serena/test_integration_multi_client.py`
**Constraints**:
- No mocks for Registry, Pool, or Dispatcher.
- Data isolation via temp directories only.

**Tests**:
1. `test_multi_client_isolation`
   - Client A activates Project A; Client B activates Project B
   - Assert Client A cannot access Project B paths (path boundary error)
   - Assert SessionRegistry snapshot shows correct roots per session
2. `test_disconnect_does_not_affect_other_client`
   - Disconnect A; verify B continues to operate and registry entry persists
3. `test_concurrent_activation_no_cross_talk`
   - Two threads activate different projects concurrently
   - Assert no registry leakage between session IDs

**Theater Check**: Assertions on concrete filesystem paths and registry snapshots.

### Cycle 3.6 - GREEN: Fixes for Integration Failures
- Resolve any concurrency, lifecycle, or binding issues revealed by Cycle 3.5.

---

## 7. Adversarial TDD Enforcement

- **RED phase** by test-writer (blind to implementation).
- **GREEN phase** by coder (blind to test source).
- **Coordinator Review**: Validate tests are non-theater and traceable to contracts.
- **Artifact Review**: Ensure each test failure message maps to PRE/POST/INV requirement.

---

## 8. Rollback/Isolation Strategy

- Each cycle is self-contained; if a cycle fails, revert to previous green state before proceeding.
- Integration tests run against ephemeral temp directories; no persistent data modified.

---

## 9. Audit Gates (Phase 3)

- **Gate A**: All contracts include PRE/POST/INV for touched public methods.
- **Gate B**: No theater tests (exact, deterministic assertions).
- **Gate C**: Integration tests use real components with isolated data.
- **Gate D**: REQ-4b, REQ-5b, REQ-6 evidence recorded.

---

## 10. Success Criteria

- MCP clients use session-aware activation by default.
- Legacy `activate_project()` still works and delegates to new path when session exists.
- Two concurrent clients operate on different projects without cross-contamination.
- Disconnect of one client does not affect another.

---

## 11. Notes

- This plan is M3 only. Implementation requires explicit approval and AI Panel critique per constitutional rules.
- Adversarial test-writer and coder phases apply unless explicitly waived in writing for execution.
