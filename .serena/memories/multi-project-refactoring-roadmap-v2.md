# Multi-Project Refactoring Roadmap (v2)

**Date**: 2026-01-12
**Status**: DEFINITIVE GUIDE
**Supersedes**: 
- `multi-project-implementation-plan-v1.md` (Integration section)
- `option-c-sync-refactor-plan.md` (Integration section)
- `multi-project-integration-complete.md` (Invalidated - claims rejected)

## Executive Summary

The current codebase is in a "mid-flight" state. While the behavioral contracts (`contracts/*.py`) and core isolation components (`SessionRegistry`, `MCPSessionBridge`) are defined, the legacy architecture (`SerenaAgent`, `Project`, `mcp.py`) actively prevents their use. The system currently enforces a single-session singleton pattern that violates the core requirement of multi-project support.

This roadmap defines the **mandatory refactoring phases** required to bridge the gap between the verified contracts and the actual application entry points.

---

## Phase 1: Foundation (Parallel Stack) - "The Strangler Fig Begins"

**Goal**: Wire new components WITHOUT breaking existing behavior.

### REQ-3: Initialize Global Services in Factory (MOVED FROM PHASE 2)
**WHAT**: Update `SerenaMCPFactory` (in `mcp.py`) to instantiate singleton instances of `SessionRegistry`, `MCPSessionBridge`, and `GlobalLanguageServerPool` at startup.
**WHY**: These components currently exist only in tests. They must exist in the production runtime to manage state.
**EXPECTED**: 
- The `FastMCP` server lifespan context initializes these services.
- `SerenaAgent` receives references to these registries via dependency injection (constructor) as **OPTIONAL** parameters.
- Existing behavior continues to work (parallel operation).

### REQ-7: Replace Naive _create_lsp Implementation (REVISED)
**WHAT**: Replace the naive, hardcoded `_create_lsp` implementation in `GlobalLanguageServerPool` with robust `LanguageServerFactory` logic.
**WHY**: Current implementation ignores user configuration (ignored_patterns, encoding, ls_specific_settings, ls_timeout) and crashes in tests (11 failures).
**EXPECTED**: 
- The pool correctly instantiates `SolidLanguageServer` with configuration derived from the target `Project`.
- User's `project.yml` settings are respected.

---

## Phase 2: The New Path

**Goal**: Implement new methods that use the Registry, alongside existing methods.

### REQ-4: Implement Session-Aware Activation
**WHAT**: Create NEW method `SerenaAgent.activate_session_project()` that uses `SessionRegistry.bind_session`.
**WHY**: The current `activate_project` calls `unbind_session` on the *previous* session, actively destroying concurrency.
**EXPECTED**: 
- New method binds the **current** session ID (from ContextVar) to the target project path.
- It does **NOT** affect other active sessions.
- Old `activate_project` continues to work for backward compatibility.

### REQ-5: Route LSPs via Global Pool
**WHAT**: Implement `SessionAwareToolDispatch` inside `SerenaAgent` that routes to `GlobalLanguageServerPool`.
**WHY**: Tools must request LSPs from the global pool to enable sharing and idle reclamation.
**EXPECTED**: 
- New dispatch path:
    1. Identifies the current session (ContextVar).
    2. Resolves the session's workspace root.
    3. Acquires an LSP from `GlobalLanguageServerPool`.
    4. Executes the request.
    5. Releases the LSP reference (start idle timer).
- Old path continues to work for backward compatibility.

---

## Phase 3: The Switch

**Goal**: Migrate `mcp.py` to use the new path, with shim layer for legacy.

### REQ-4b: Update mcp.py to Call New Methods
**WHAT**: Update `SerenaMCPFactory` to call `activate_session_project()` instead of `activate_project()`.
**WHY**: This activates the multi-project path for MCP clients.
**EXPECTED**: 
- MCP clients use the new session-aware activation.
- CLI (if it exists) can still use old path temporarily.

### REQ-5b: Shim Layer for Legacy Methods
**WHAT**: Refactor `SerenaAgent` legacy methods to delegate to the new path.
**WHY**: Single entry point reduces maintenance burden.
**EXPECTED**: 
- `activate_project()` internally calls `activate_session_project()`.
- Old API preserved, new implementation.

### REQ-6: Implement Real Integration Tests
**WHAT**: Create a new test suite that initializes the full `SerenaMCPFactory` stack.
**WHY**: Current tests are unit-level mocks. We need to prove that `Client A` can work on `Project A` while `Client B` works on `Project B`.
**EXPECTED**: 
- Test: Connect Client A, Activate Project A.
- Test: Connect Client B, Activate Project B.
- Test: Verify Client A cannot read Project B files.
- Test: Verify Client A disconnect does not affect Client B.

---

## Phase 4: Cleanup (The Strangulation)

**Goal**: Remove legacy code after verification.

### REQ-1: Make SerenaAgent Stateless (MOVED FROM PHASE 1)
**WHAT**: Remove `_active_project` and `_current_session_id` instance variables from `SerenaAgent`.
**WHY**: These variables enforce a Singleton pattern. Now that Phase 3 is complete, they are no longer needed.
**EXPECTED**: 
- `SerenaAgent` methods no longer rely on `self._active_project`.
- All context resolved dynamically via `SessionRegistry`.

### REQ-2: Convert Project to Configuration Holder
**WHAT**: Remove `LanguageServerManager` ownership from the `Project` class.
**WHY**: `Project` currently owns LSP lifecycles. `GlobalLanguageServerPool` now manages shared LSPs.
**EXPECTED**: 
- `Project` class acts solely as a configuration loader (paths, ignore patterns, settings).
- `Project` does **not** start or stop subprocesses.

### REQ-8: Remove Legacy Single-Session Code
**WHAT**: Delete `LanguageServerManager` (the old class) now that `GlobalLanguageServerPool` is fully operational.
**WHY**: Dead code creates confusion and maintenance burden.
**EXPECTED**: 
- Clean codebase with one clear way to manage LSPs.

---

## Critical Checkpoints (Strangler Fig Ordering)

1. **Phase 1 Gate**: New components initialized in parallel. Existing tests still pass.
2. **Phase 2 Gate**: New methods work. Old methods still work. Both paths coexist.
3. **Phase 3 Gate**: mcp.py uses new path. Integration tests pass (Client A + Client B concurrent).
4. **Phase 4 Gate**: Legacy code removed. Only new path exists. All tests pass.

**Key Safety Principle**: Never break existing behavior until new behavior is verified.

---

## Adversarial Debate Consensus (2026-01-12)

This roadmap was refined through adversarial debate. Key resolutions:

- **REQ-1 moved to Phase 4**: Don't remove state until replacement is verified (Strangler Fig)
- **REQ-3 moved to Phase 1**: Wire new components first, before decoupling
- **REQ-7 revised**: "De-stub" → "Replace naive implementation with robust factory logic"
- **Phase ordering**: Foundation → New Path → Switch → Cleanup (not Unwire → Rewire)

See `.serena/memories/adversarial-debate-multi-project-findings.md` for full debate record.

This roadmap serves as the authoritative source for the remaining work on Issue #6.
