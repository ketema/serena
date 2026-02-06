# Contract Authority Record (CAR)

**Contract File**: contracts/session_isolation_contract.py
**Authority**: "AUTHORITATIVE for session isolation behavior"
**Date**: 2026-02-06

## Extracted Clauses

### SessionCreationContract (B1 Fix)

**INVARIANTS**:
- INV-B1-01: on_transport_session_created() MUST NOT use Path.cwd() as default
- INV-B1-02: Sessions without workspace MUST be valid (workspace_root=None)
- INV-B1-03: activate_project is the ONLY mechanism to bind workspace to session
- INV-B1-04: STDIO mode backward compatibility preserved (anonymous sessions with cwd)

**PRECONDITIONS**:
- PRE-B1-01: mcp_session_id is non-empty string
- PRE-B1-02: workspace_root is None at session creation (HTTP mode)

**POSTCONDITIONS**:
- POST-B1-01: Session registered with workspace_root=None
- POST-B1-02: Session available via get_session(mcp_session_id)
- POST-B1-03: get_session().workspace_root is None until activate_project called

**ERRORS**:
- ERRORS-B1-01: ValueError if mcp_session_id is empty (propagated)

---

### SessionScopedToolsContract (B2/B4 Fix)

**INVARIANTS**:
- INV-B2-01: _active_tools dict MUST NOT be mutated by activate_project
- INV-B2-02: Tool availability MUST be derived from session's project config
- INV-B2-03: Concurrent sessions with different projects see correct tool sets
- INV-B2-04: Tool set computation MUST NOT have side effects on other sessions

**PRECONDITIONS**:
- PRE-B2-01: Session has active project (workspace_root is not None)
- PRE-B2-02: Project config is loadable from workspace_root

**POSTCONDITIONS**:
- POST-B2-01: Returns tool set appropriate for session's project
- POST-B2-02: Shared Agent state unchanged after call
- POST-B2-03: Result is consistent with project config at session's workspace_root

---

### SessionScopedActivationContract (B3 Fix)

**INVARIANTS**:
- INV-B3-01: activate_project MUST NOT call _update_active_tools() on shared Agent
- INV-B3-02: activate_project MUST NOT mutate any shared Agent fields
- INV-B3-03: Only the calling session's registry entry is modified
- INV-B3-04: Other sessions' tool availability MUST be unaffected

**PRECONDITIONS**:
- PRE-B3-01: session_id is non-empty string (from ContextVar)
- PRE-B3-02: workspace_root exists and is absolute path
- PRE-B3-03: Project loadable from workspace_root

**POSTCONDITIONS**:
- POST-B3-01: SessionRegistry updated for session_id only
- POST-B3-02: ContextVar set to new SessionContext
- POST-B3-03: Project loaded and LSP workspace roots added
- POST-B3-04: No shared Agent state mutated

**ERRORS**:
- ERRORS-B3-01: ProjectNotFoundError if workspace invalid (propagated)
- ERRORS-B3-02: ValueError if session_id empty (propagated)

---

### GracefulDegradationContract

**INVARIANTS**:
- INV-GD-01: CONFIG tools (activate_project, get_config) always available
- INV-GD-02: PROJECT tools fail with clear error when no workspace bound
- INV-GD-03: LSP tools fail with clear error when no workspace bound
- INV-GD-04: Error message MUST instruct user to call activate_project

**POSTCONDITIONS**:
- POST-GD-01: CONFIG tools return normally regardless of project state
- POST-GD-02: PROJECT/LSP tools raise NoProjectActivatedError when workspace is None
- POST-GD-03: Error message includes session_id for debugging

---

### STDIOCompatibilityContract

**INVARIANTS**:
- INV-STDIO-01: STDIO mode creates anonymous session with cwd workspace
- INV-STDIO-02: Single-session STDIO mode unaffected by isolation changes
- INV-STDIO-03: _update_active_tools() safe in STDIO (only one session)

**POSTCONDITIONS**:
- POST-STDIO-01: Anonymous session created on first tool call
- POST-STDIO-02: Tool set matches project at cwd

---

## CL12-B Consistency Check

**No contradictions detected**:
- ✓ No PRE clause contradicts ERRORS
- ✓ No INV clause contradicts POST
- ✓ All ERROR clauses map to specific PRE/INV violations

---

## Clause Coverage Plan

**Total clauses**: 33 (5 contracts)
**Minimum tests**: 33 (one per clause)
**Integration scenarios**: 4 (from contract file)

**Coverage strategy**:
- Each INV clause → boundary test
- Each PRE clause → negative test (violation)
- Each POST clause → positive test (satisfaction)
- Each ERROR clause → exception test
- Integration scenarios → multi-session concurrency tests
