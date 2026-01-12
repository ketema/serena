# Phase 1: Foundation Implementation Plan

**Date**: 2026-01-12
**Status**: APPROVED
**Branch**: feature/multi-project-support
**AI Panel Conversation**: 2c0f6a41-ad72-4d5d-881a-4956a7adb021

## Constitutional Requirements

**CL6 & M4 MANDATE**: All TDD cycles MUST use adversarial sub-agents:
- **test-writer skill**: Writes tests BLIND to implementation (RED phase)
- **coder skill**: Implements BLIND to test source (GREEN phase)

This ensures true isolation and self-documenting error messages.

## TDD Cycle Overview

| Cycle | Description | Sub-Agent |
|-------|-------------|-----------|
| 1.1 | Contract tests for `get_pooling_policy()` and `get_launch_arguments()` | test-writer |
| 1.2 | Implement `PoolingPolicy` enum + contract methods | coder |
| 1.3 | Implement Clangd and TypeScript adapters | coder |
| 1.4 | Edge case tests (unknown LSP, null workspace) | test-writer |
| 2.1 | Tests for `SerenaMCPFactory` initialization | test-writer |
| 2.2 | Implement singleton initialization in mcp.py | coder |
| 2.3 | Wire optional DI params to `SerenaAgent` constructor | coder |
| 2.4 | Strangler Fig isolation test | test-writer |
| 3.1 | Verify 11 failing tests are valid (RED state) | coordinator review |
| 3.2 | Replace naive `_create_lsp` with robust factory | coder |
| 3.3 | Integrate `get_launch_arguments()` into LSP creation | coder |
| 3.4 | Thread safety test (async reaper → sync pool) | test-writer |
| Gate | All tests pass + Strangler Fig verified | coordinator |

---

## TDD Cycle 1: Contract Evolution

### Cycle 1.1 - RED: Contract Tests

**Invoke**: ↪ test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- REQ-ADAPT-1: `get_pooling_policy()` returns `PoolingPolicy` enum
- REQ-ADAPT-2: `get_launch_arguments(workspace_root, session_id)` returns `list[str]`
- REQ-ADAPT-3: Default adapters return sensible defaults
- REQ-ADAPT-4: Unknown LSP type returns `ISOLATED_PROCESS` (conservative)

**TSR (Test Specification Review)**:
```
Feature: LSP Capability Adapter Contract Extension
Given: LSPCapabilityAdapterContract with new methods
When: Adapter queried for pooling policy
Then: Returns valid PoolingPolicy enum value

When: Adapter queried for launch arguments
Then: Returns list of CLI arguments (may be empty)

Edge Cases:
- Unknown language → DefaultAdapter → ISOLATED_PROCESS
- null workspace_root → raise ValueError
- empty session_id → raise ValueError
```

### Cycle 1.2 - GREEN: PoolingPolicy Enum + Contract Methods

**Invoke**: ↪ coder | 🚫 test source | ✓ error messages

**Expected Implementation**:
```python
class PoolingPolicy(Enum):
    SHARED_INSTANCE = "shared"           # Multi-root: rust-analyzer, pylsp, gopls
    ISOLATED_PROCESS = "isolated"        # Single-root default
    ISOLATED_WITH_RESOURCE_MANAGEMENT = "managed"  # TypeScript (memory limits)
    FORCED_ISOLATION = "forced"          # Terraform (unsafe to share)
```

### Cycle 1.3 - GREEN: Concrete Adapters

**Invoke**: ↪ coder | 🚫 test source | ✓ error messages

**ClangdIsolatedAdapter**:
```python
def get_launch_arguments(self, workspace_root: Path, session_id: str) -> list[str]:
    cache_path = f"/tmp/serena_clangd_{session_id}_{hash(str(workspace_root))}"
    return [f"--cache-path={cache_path}"]
```

**TsServerResourceManagedAdapter**:
```python
def get_launch_arguments(self, workspace_root: Path, session_id: str) -> list[str]:
    return ["--max-old-space-size=3072"]
```

### Cycle 1.4 - RED: Edge Case Tests

**Invoke**: ↪ test-writer | 🚫 impl | ✓ req+TSR

**Edge Cases**:
- Unknown LSP language → returns `ISOLATED_PROCESS`
- `workspace_root=None` → raises `ValueError`
- `session_id=""` → raises `ValueError`
- `session_id=None` → raises `ValueError`

---

## TDD Cycle 2: REQ-3 Global Services

### Cycle 2.1 - RED: Factory Initialization Tests

**Invoke**: ↪ test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- REQ-3-1: `SerenaMCPFactory` creates `SessionRegistry` singleton at startup
- REQ-3-2: `SerenaMCPFactory` creates `MCPSessionBridge` singleton at startup
- REQ-3-3: `SerenaMCPFactory` creates `GlobalLanguageServerPool` singleton at startup
- REQ-3-4: Services initialized in FastMCP lifespan context
- REQ-3-5: Concurrent initialization is thread-safe

### Cycle 2.2 - GREEN: Implement Initialization

**Invoke**: ↪ coder | 🚫 test source | ✓ error messages

**Location**: `src/serena/mcp.py` in `SerenaMCPFactory`

### Cycle 2.3 - GREEN: SerenaAgent DI

**Invoke**: ↪ coder | 🚫 test source | ✓ error messages

**Signature Change**:
```python
def __init__(
    self,
    # ... existing params ...
    session_registry: SessionRegistry | None = None,
    session_bridge: MCPSessionBridge | None = None,
    lsp_pool: GlobalLanguageServerPool | None = None,
):
```

### Cycle 2.4 - RED: Strangler Fig Isolation Test

**Invoke**: ↪ test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- REQ-SF-1: When DI params are `None`, SerenaAgent uses old path (LanguageServerManager)
- REQ-SF-2: Existing single-project behavior is unchanged
- REQ-SF-3: Old tests still pass without new components

---

## TDD Cycle 3: REQ-7 Robust LSP Factory

### Cycle 3.1 - VERIFY: Existing RED State

**Coordinator Review** (not sub-agent):
- Run `pytest test/serena/test_global_lsp_pool.py -v`
- Verify 11 failures describe desired behavior
- Document which tests are valid behavioral specs

### Cycle 3.2 - GREEN: Replace Naive _create_lsp

**Invoke**: ↪ coder | 🚫 test source | ✓ error messages

**Must Respect**:
- `Project.ignored_patterns`
- `Project.encoding`
- `Project.ls_specific_settings`
- `Project.ls_timeout`

### Cycle 3.3 - GREEN: Integrate Launch Arguments

**Invoke**: ↪ coder | 🚫 test source | ✓ error messages

**Flow**:
1. Get adapter: `adapter = self.capability_registry.get_adapter(language)`
2. Get args: `args = adapter.get_launch_arguments(workspace_root, session_id)`
3. Pass to LSP: `SolidLanguageServer.create(..., extra_args=args)`

### Cycle 3.4 - RED: Thread Safety Test

**Invoke**: ↪ test-writer | 🚫 impl | ✓ req+TSR

**Requirements**:
- REQ-TS-1: Async reaper in MCPSessionBridge can safely call sync GlobalLanguageServerPool methods
- REQ-TS-2: No deadlock when reaper runs while pool is under lock
- REQ-TS-3: Concurrent acquire/release operations are safe

---

## Phase 1 Gate Criteria

- [ ] All existing tests pass (no regressions)
- [ ] New contract tests pass (Cycle 1)
- [ ] Factory initialization tests pass (Cycle 2)
- [ ] 11 previously failing tests now pass (Cycle 3)
- [ ] Strangler Fig isolation verified (old path works)
- [ ] Thread safety verified

---

## Adversarial TDD Reminder

**CONSTITUTIONAL VIOLATION** if coordinator writes tests or implementation directly.

**Correct Flow**:
1. Coordinator prepares TSR (Test Specification Review)
2. ↪ test-writer creates tests from TSR (BLIND to impl)
3. Coordinator runs tests → RED state
4. ↪ coder implements from error messages (BLIND to test source)
5. Coordinator runs tests → GREEN state
6. Coordinator commits with WHY/EXPECTED format
7. Repeat for next cycle
