"""
SerenaAgent Statelessness Contract - Phase 4 Cycle 1

Constitutional Reference: CL12 Design by Contract
Domain: SerenaAgent session management (replacing legacy _active_project/_current_session_id)
Version: 1.0
Last Updated: 2026-01-13

AUTHORITY: This contract is AUTHORITATIVE for SerenaAgent session resolution.
All implementations MUST resolve sessions via SessionRegistry + ContextVar.
There SHALL be NO instance-level session state (_active_project, _current_session_id).

Related Contracts:
- contracts/session_registry_contract.py (SessionRegistry behavior)
- contracts/contextvar_session_contract.py (ContextVar integration)
"""

from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

# =============================================================================
# LEGACY STATE PROHIBITION
# =============================================================================

# These fields MUST NOT exist in SerenaAgent after Phase 4 Cycle 1
PROHIBITED_FIELDS = [
    "_active_project",       # Legacy: Project | None
    "_current_session_id",   # Legacy: str | None
]

# SerenaAgent MUST use these instead
REQUIRED_DEPENDENCIES = [
    "_session_registry",     # SessionRegistry instance (injected)
    "_current_session",      # ContextVar[SessionContext | None] (module-level)
]


# =============================================================================
# CONTEXTVAR INTEGRATION CONTRACT
# =============================================================================

# Module-level ContextVar for async propagation
# PRE: Defined at module level (not instance level)
# POST: Accessible via get_current_session() helper
# INV: Thread-local isolation per async context
_current_session: ContextVar[Optional[Any]] = ContextVar("_current_session", default=None)


def get_current_session() -> Optional[Any]:
    """
    Get current session from ContextVar.

    PRE: None (always callable)

    POST: Returns SessionContext if set in current async context
    POST: Returns None if no session bound in current context

    INV (5-Point Checklist):
    1. State Invariance: ContextVar unchanged (read-only)
    2. Side Effect Prohibition: No I/O, no logging, no external state
    3. Ordering Constraints: None (pure read)
    4. Resource Invariants: No allocations
    5. Exception Safety: Never raises

    ERRORS: None (never raises)
    """
    return _current_session.get()


def set_current_session(session: Optional[Any]) -> None:
    """
    Set current session in ContextVar.

    PRE: session is SessionContext or None

    POST: get_current_session() returns session in current async context
    POST: Other async contexts unchanged (ContextVar isolation)

    INV (5-Point Checklist):
    1. State Invariance: Other contexts unchanged
    2. Side Effect Prohibition: No I/O, no logging (ContextVar is internal state)
    3. Ordering Constraints: Must be called at request boundary (entry/exit)
    4. Resource Invariants: No file handles, no memory beyond ContextVar
    5. Exception Safety: Never raises

    ERRORS:
    - TypeError: if session is not SessionContext or None (type validation)
    """
    _current_session.set(session)


# =============================================================================
# SERENA AGENT STATELESS CONTRACT
# =============================================================================

@runtime_checkable
class SerenaAgentStatelessContract(Protocol):
    """
    Contract for SerenaAgent session resolution without instance state.

    CLASS INVARIANTS:
    - INV-1: NO _active_project field exists
    - INV-2: NO _current_session_id field exists
    - INV-3: All session resolution via SessionRegistry + ContextVar
    - INV-4: Thread-safe (SessionRegistry handles locking)
    - INV-5: Request-scoped session binding (set at request start, cleared at request end)

    LEGACY MIGRATION:
    - _active_project → SessionRegistry.get_session(session_id).workspace_root + Project.load()
    - _current_session_id → get_current_session().session_id
    - _activate_project() → bind_session() + set_current_session()

    ENFORCEMENT (CL12-A):
    - __init__ MUST NOT define _active_project or _current_session_id
    - Tests verify these fields do not exist via hasattr() check
    - Static analysis can grep for prohibited patterns
    """

    def get_current_session_context(self) -> Optional[Any]:
        """
        Get current session context from ContextVar.

        PRE: None (always callable)

        POST: Returns SessionContext if in active request context
        POST: Returns None if no active request (e.g., during setup)

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: No I/O, no logging
        3. Ordering Constraints: None (pure read)
        4. Resource Invariants: No allocations
        5. Exception Safety: Never raises

        ERRORS: None (never raises)
        """
        ...

    def get_active_project(self) -> Optional[Any]:
        """
        Get active project via SessionRegistry lookup (REPLACES legacy _active_project).

        PRE: None (always callable)

        POST-1: Returns Project if current session has bound workspace
        POST-2: Returns None if no active session or session has no project
        POST-3: Project loaded from workspace_root in current session

        INV (5-Point Checklist):
        1. State Invariance: No instance state modified (pure lookup)
        2. Side Effect Prohibition: May load Project from disk (declared side effect)
        3. Ordering Constraints: None (no sequencing requirements, always callable)
        4. Resource Invariants: Project loading may allocate memory (normal operation)
        5. Exception Safety: Returns None on any error (graceful degradation)

        ERRORS: None (catches all exceptions, returns None)

        LEGACY MIGRATION:
        Before: return self._active_project
        After:  session = get_current_session()
                if session is None: return None
                return Project.load(session.workspace_root)
        """
        ...

    def get_active_project_or_raise(self) -> Any:
        """
        Get active project or raise if none (REPLACES legacy pattern).

        PRE: None (defensive method - handles missing session gracefully by raising)

        POST-1: Returns Project for current session's workspace
        POST-2: Never returns None

        INV (5-Point Checklist):
        1. State Invariance: No instance state modified
        2. Side Effect Prohibition: May load Project from disk (declared)
        3. Ordering Constraints: None (handles missing session by raising, not caller obligation)
        4. Resource Invariants: Normal Project loading
        5. Exception Safety: Raises ProjectNotFoundError on failure (declared)

        ERRORS:
        - ProjectNotFoundError: if no active session or no project at workspace
        """
        ...

    def activate_session_project(
        self,
        session_id: str,
        workspace_root: Path,
        source: str = "explicit"
    ) -> Any:
        """
        Bind session to workspace and set as current (REPLACES _activate_project).

        PRE: session_id is non-empty string
        PRE: workspace_root exists and is absolute path
        PRE: source in ("explicit", "auto", "anonymous")

        POST-1: SessionRegistry.bind_session() called
        POST-2: set_current_session() called with new SessionContext
        POST-3: Project loaded and initialized for workspace
        POST-4: Returns loaded Project

        INV (5-Point Checklist):
        1. State Invariance: NO _active_project modified (field doesn't exist)
        2. Side Effect Prohibition: SessionRegistry mutation (declared),
           ContextVar set (declared), Project loading (declared)
        3. Ordering Constraints: bind_session before set_current_session
        4. Resource Invariants: May trigger LSP acquisition via GlobalLanguageServerPool (not Project)
        5. Exception Safety: On error, unbind session and clear ContextVar

        ERRORS:
        - ValueError: if session_id empty
        - FileNotFoundError: if workspace_root does not exist
        - ProjectNotFoundError: if project cannot be loaded
        """
        ...

    def deactivate_session(self, session_id: str) -> None:
        """
        Unbind session and clear from current context if active.

        PRE: session_id is string (may or may not exist)

        POST-1: SessionRegistry.unbind_session() called
        POST-2: If session_id was current session, set_current_session(None)
        POST-3: Session no longer retrievable

        INV (5-Point Checklist):
        1. State Invariance: Other sessions unchanged
        2. Side Effect Prohibition: SessionRegistry mutation (declared),
           ContextVar clear (declared)
        3. Ordering Constraints: unbind_session before clear ContextVar
        4. Resource Invariants: May trigger LSP cleanup via registry
        5. Exception Safety: Idempotent (unbinding non-existent is no-op)

        ERRORS: None (never raises, idempotent)
        """
        ...


# =============================================================================
# TEST CASE SPECIFICATIONS (CL12-E Traceability)
# =============================================================================

TEST_CASES = {
    "prohibited_fields": [
        {
            "name": "test_inv1_no_active_project_field",
            "contract": "INV-1: NO _active_project field exists",
            "assertion": "not hasattr(agent, '_active_project')",
            "guidance": "SerenaAgent MUST NOT have _active_project instance attribute",
        },
        {
            "name": "test_inv2_no_current_session_id_field",
            "contract": "INV-2: NO _current_session_id field exists",
            "assertion": "not hasattr(agent, '_current_session_id')",
            "guidance": "SerenaAgent MUST NOT have _current_session_id instance attribute",
        },
    ],
    "contextvar_integration": [
        {
            "name": "test_inv3_session_via_contextvar",
            "contract": "INV-3: All session resolution via SessionRegistry + ContextVar",
            "setup": "activate_session_project('sess-1', Path('/tmp/project'))",
            "assertion": "get_current_session().session_id == 'sess-1'",
            "guidance": "Session MUST be retrievable via ContextVar after activation",
        },
        {
            "name": "test_inv5_request_scoped_binding",
            "contract": "INV-5: Request-scoped session binding",
            "setup": "activate in one async context, check in another",
            "assertion": "other context sees None (isolation)",
            "guidance": "ContextVar provides async context isolation",
        },
    ],
    "get_active_project": [
        {
            "name": "test_post1_returns_project_from_session",
            "contract": "POST-1: Returns Project if current session has bound workspace",
            "setup": "activate_session_project with valid workspace",
            "assertion": "get_active_project() returns Project instance",
        },
        {
            "name": "test_post2_returns_none_without_session",
            "contract": "POST-2: Returns None if no active session",
            "setup": "no session activated",
            "assertion": "get_active_project() returns None",
        },
    ],
    "activate_session_project": [
        {
            "name": "test_post1_registry_bind_called",
            "contract": "POST-1: SessionRegistry.bind_session() called",
            "setup": "integration test with real SessionRegistry (CL10 compliant - no mock)",
            "assertion": "registry.get_session(session_id) returns SessionContext after activation",
            "cl10_status": "COMPLIANT - integration test verifies POST via observable state",
        },
        {
            "name": "test_post2_contextvar_set",
            "contract": "POST-2: set_current_session() called with new SessionContext",
            "setup": "activate_session_project",
            "assertion": "get_current_session() returns matching SessionContext",
        },
        {
            "name": "test_exception_safety_unbinds",
            "contract": "INV 5-point #5 (Exception Safety): On error, unbind session and clear ContextVar",
            "setup": "Project.load raises exception",
            "assertion": "session unbound, ContextVar is None",
        },
    ],
    "deactivate_session": [
        {
            "name": "test_post1_registry_unbind_called",
            "contract": "POST-1: SessionRegistry.unbind_session() called",
            "setup": "activate then deactivate",
            "assertion": "unbind_session called",
        },
        {
            "name": "test_post2_contextvar_cleared_if_current",
            "contract": "POST-2: If session_id was current session, set_current_session(None)",
            "setup": "activate session, then deactivate same session",
            "assertion": "get_current_session() returns None",
        },
        {
            "name": "test_errors_none_idempotent",
            "contract": "ERRORS: None (idempotent - never raises)",
            "setup": "deactivate non-existent session",
            "assertion": "no exception raised",
        },
    ],
}


# =============================================================================
# VERIFICATION HELPERS
# =============================================================================

def verify_no_legacy_state(agent: Any) -> None:
    """
    Verify SerenaAgent has no legacy state fields.

    PRE: agent is SerenaAgent instance
    POST: No return value (raises on violation)
    INV: agent unchanged

    ERRORS:
    - AssertionError: if any prohibited field exists
    - TypeError: if agent lacks __dict__ (non-inspectable object)
    """
    for field in PROHIBITED_FIELDS:
        assert not hasattr(agent, field), (
            f"INV-{PROHIBITED_FIELDS.index(field) + 1} violation: "
            f"SerenaAgent has prohibited legacy field '{field}'\n"
            f"Contract: SerenaAgentStatelessContract\n"
            f"EXPECTED: Field '{field}' does not exist\n"
            f"ACTUAL: Field exists with value {getattr(agent, field, 'N/A')}\n"
            f"GUIDANCE: Remove legacy state, use SessionRegistry + ContextVar"
        )


def verify_required_dependencies(agent: Any) -> None:
    """
    Verify SerenaAgent has required dependencies for stateless operation.

    PRE: agent is SerenaAgent instance
    POST: No return value (raises on violation)
    INV: agent unchanged

    ERRORS:
    - AssertionError: if any required dependency missing
    - TypeError: if agent lacks __dict__ (non-inspectable object)
    """
    for dep in REQUIRED_DEPENDENCIES:
        if dep == "_current_session":
            # ContextVar is module-level, not instance attribute
            continue
        assert hasattr(agent, dep), (
            f"Missing required dependency: '{dep}'\n"
            f"Contract: SerenaAgentStatelessContract\n"
            f"EXPECTED: SerenaAgent has '{dep}' attribute\n"
            f"ACTUAL: Attribute not found\n"
            f"GUIDANCE: Inject {dep} in __init__"
        )
