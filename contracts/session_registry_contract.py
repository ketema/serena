"""
Contract: SessionRegistry

Defines the behavioral contract for multi-project session isolation.
Mocks for tests MUST derive from this contract (CL10).

Component: SessionRegistry
Purpose: Thread-safe mapping of MCP session_id → SessionContext

SYNC INTERFACE (v2):
- All methods are synchronous (no async/await)
- Thread-safety via threading.Lock (not asyncio.Lock)
- Compatible with sync SerenaAgent integration points
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Any

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SessionContextContract:
    """Contract for per-session isolation context."""

    # REQUIRED FIELDS (all must be present)
    session_id: str  # Unique MCP session identifier
    workspace_root: Path  # Absolute path to project root
    activation_source: Literal["explicit", "auto"]  # How session was activated
    activation_time: datetime  # When session was bound

    # OPTIONAL FIELDS (may be empty/None)
    active_modes: list[str]  # Currently active modes
    lsp_references: dict[str, Any]  # language → LSP instance reference


# =============================================================================
# BEHAVIORAL CONTRACTS
# =============================================================================

class SessionRegistryContract:
    """
    Behavioral contract for SessionRegistry.

    INVARIANTS:
    - INV-1: session_id is unique across all bound sessions
    - INV-2: workspace_root is always an absolute, resolved path
    - INV-3: A session can only be bound to one workspace at a time
    - INV-4: All mutations are atomic (thread-safe via threading.Lock)

    PRECONDITIONS:
    - PRE-1 (bind): session_id not already bound
    - PRE-2 (bind): workspace_root is valid, existing directory
    - PRE-3 (unbind): session_id exists in registry
    - PRE-4 (get): no preconditions (may return None)

    POSTCONDITIONS:
    - POST-1 (bind): session_id maps to SessionContext with provided values
    - POST-2 (unbind): session_id no longer in registry
    - POST-3 (unbind): if last session for workspace, LSPs are scheduled for cleanup
    - POST-4 (get): returns SessionContext if exists, None otherwise
    """

    # Method signatures for contract verification (SYNC - v2)

    def bind_session(
        self,
        session_id: str,
        workspace_root: Path,
        source: Literal["explicit", "auto"] = "explicit"
    ) -> "SessionContextContract":
        """
        Bind a session to a workspace (SYNC).

        PRE: session_id not already bound (raises ValueError if duplicate)
        PRE: workspace_root.is_absolute() and workspace_root.exists()

        POST: get_session(session_id) returns SessionContext
        POST: returned SessionContext.workspace_root == workspace_root.resolve()

        INV (5-Point Checklist):
        1. State Invariance: Other sessions unchanged, registry INV-1 through INV-4 preserved
        2. Side Effect Prohibition: No I/O, no logging, no external state modification
        3. Ordering Constraints: Lock acquired during mutation (INV-4), atomic operation
        4. Resource Invariants: No file handles opened, no memory leaks
        5. Exception Safety: On ValueError, registry unchanged (no partial state)

        ERRORS:
        - ValueError: if session_id already bound (INV-1 violation)
        - ValueError: if workspace_root is not absolute
        - FileNotFoundError: if workspace_root does not exist
        """
        ...

    def unbind_session(self, session_id: str) -> None:
        """
        Unbind a session and cleanup if last for workspace (SYNC).

        PRE: none (idempotent - session may or may not exist)

        POST: get_session(session_id) returns None
        POST: if was last session for workspace, LSP cleanup scheduled

        INV (5-Point Checklist):
        1. State Invariance: Other sessions unchanged, idempotent (no effect if not bound)
        2. Side Effect Prohibition: No I/O, no logging; EXCEPTION: LSP cleanup scheduling
           is a DECLARED side effect when last session for workspace
        3. Ordering Constraints: Lock acquired during mutation (INV-4), atomic operation
        4. Resource Invariants: Session entry fully removed, no dangling references
        5. Exception Safety: Never raises (idempotent), state always consistent

        ERRORS: None (idempotent - unbinding non-existent session is silent no-op)
        """
        ...

    def get_session(self, session_id: str) -> "SessionContextContract | None":
        """
        Get session context by ID.

        PRE: none (pure query, always safe to call)

        POST: Returns SessionContext if session_id exists in registry, None otherwise

        INV (5-Point Checklist):
        1. State Invariance: Registry completely unchanged (read-only query)
        2. Side Effect Prohibition: No I/O, no logging, no external state modification
        3. Ordering Constraints: Thread-safe (may be called concurrently with mutations)
        4. Resource Invariants: No memory allocation beyond return value
        5. Exception Safety: Never raises; always returns SessionContext or None

        ERRORS: None (pure query, never raises)
        """
        ...

    def get_sessions_for_workspace(self, workspace_root: Path) -> list[str]:
        """
        Get all session IDs bound to a workspace.

        PRE: none (pure query, always safe to call)

        POST: Returns list of session_ids bound to workspace_root (may be empty)
        POST: All returned session_ids satisfy get_session(id).workspace_root == workspace_root

        INV (5-Point Checklist):
        1. State Invariance: Registry completely unchanged (read-only query)
        2. Side Effect Prohibition: No I/O, no logging, no external state modification
        3. Ordering Constraints: Thread-safe (may be called concurrently with mutations)
        4. Resource Invariants: Returns new list (no internal state exposed)
        5. Exception Safety: Never raises; always returns list (possibly empty)

        ERRORS: None (pure query, never raises)
        """
        ...

    def get_session_overview(self) -> dict[str, Any]:
        """
        Get overview of all active sessions for observability.

        PRE: none (pure query, always safe to call)

        POST: Returns dict with exactly two keys: "sessions", "total_count"
        POST: "sessions" is list of session detail dicts
        POST: "total_count" is int matching len(sessions)
        POST: Each session dict contains exactly:
            - session_id: str (non-empty)
            - workspace_root: str (absolute path as string)
            - project_name: str (basename of workspace_root)
            - connected_at: str (ISO 8601 format)
            - activation_source: str ("explicit" or "auto")
        POST: len(sessions) == total_count (strict invariant)

        INV (5-Point Checklist):
        1. State Invariance: Registry completely unchanged (read-only query)
        2. Side Effect Prohibition: No I/O, no logging, no external state modification
        3. Ordering Constraints: Thread-safe (may be called concurrently with mutations)
        4. Resource Invariants: Returns new dict/lists (no internal state exposed)
        5. Exception Safety: Never raises; always returns dict with specified structure

        ERRORS: None (pure query, never raises)
        """
        ...


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================

def verify_session_context(ctx: Any) -> bool:
    """
    Verify an object satisfies SessionContext contract.

    PRE: ctx is any object (may be None, may lack expected attributes)

    POST: Returns True if ctx has all required fields with correct types
    POST: Returns False if any required field missing or has wrong type
    POST: Required fields: session_id (str), workspace_root (absolute Path),
          activation_source ("explicit"|"auto"), activation_time (datetime)

    INV (5-Point Checklist):
    1. State Invariance: ctx completely unchanged (read-only inspection)
    2. Side Effect Prohibition: No I/O, no logging, no external state modification
    3. Ordering Constraints: None (pure function, stateless)
    4. Resource Invariants: No memory allocation beyond bool return
    5. Exception Safety: Never raises (catches attribute access failures via hasattr)

    ERRORS: None (pure validation, never raises - returns False on invalid input)
    """
    required = ["session_id", "workspace_root", "activation_source", "activation_time"]
    for field in required:
        if not hasattr(ctx, field):
            return False

    if not isinstance(ctx.workspace_root, Path):
        return False
    if not ctx.workspace_root.is_absolute():
        return False
    if ctx.activation_source not in ("explicit", "auto"):
        return False
    if not isinstance(ctx.activation_time, datetime):
        return False

    return True


def verify_isolation(registry: Any, session_a: str, session_b: str) -> bool:
    """
    Verify two sessions are properly isolated.

    PRE: registry has get_session(session_id) method
    PRE: session_a, session_b are non-empty strings

    POST: Returns True if sessions are properly isolated (different workspaces OR different IDs)
    POST: Returns False if either session does not exist
    POST: Returns False if sessions have same session_id (identity violation)

    INV (5-Point Checklist):
    1. State Invariance: registry, session_a, session_b all unchanged (read-only queries)
    2. Side Effect Prohibition: No I/O, no logging, only calls registry.get_session()
    3. Ordering Constraints: None (pure function, queries only)
    4. Resource Invariants: No memory allocation beyond bool return
    5. Exception Safety: Never raises (None checks prevent attribute errors)

    ERRORS: None (pure validation, never raises - returns False on invalid input)
    """
    ctx_a = registry.get_session(session_a)
    ctx_b = registry.get_session(session_b)

    if ctx_a is None or ctx_b is None:
        return False

    # Different workspaces = isolated
    if ctx_a.workspace_root != ctx_b.workspace_root:
        return True

    # Same workspace = shared (not isolated for files, but session IDs differ)
    return ctx_a.session_id != ctx_b.session_id
