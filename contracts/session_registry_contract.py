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

        PRE: session_id not already bound
        PRE: workspace_root.is_absolute() and workspace_root.exists()
        POST: get_session(session_id) returns SessionContext
        POST: returned SessionContext.workspace_root == workspace_root.resolve()

        Thread-safety: Acquires threading.Lock during mutation.
        """
        ...

    def unbind_session(self, session_id: str) -> None:
        """
        Unbind a session and cleanup if last for workspace (SYNC).

        PRE: session_id in registry (silent no-op if not)
        POST: get_session(session_id) returns None
        POST: if was last session for workspace, LSP cleanup scheduled

        Thread-safety: Acquires threading.Lock during mutation.
        """
        ...

    def get_session(self, session_id: str) -> "SessionContextContract | None":
        """
        Get session context by ID.

        PRE: none
        POST: returns SessionContext if exists, None otherwise
        """
        ...

    def get_sessions_for_workspace(self, workspace_root: Path) -> list[str]:
        """
        Get all session IDs bound to a workspace.

        PRE: none
        POST: returns list of session_ids (may be empty)
        """
        ...

    def get_session_overview(self) -> dict:
        """
        Get overview of all active sessions for observability.
        
        PRE: none
        POST: Returns dict with keys:
            - "sessions": list of session detail dicts
            - "total_count": int matching len(sessions)
        POST: Each session dict contains:
            - session_id: str
            - workspace_root: str (absolute path)
            - project_name: str (basename of workspace_root)
            - connected_at: str (ISO 8601 format)
            - activation_source: str ("explicit" or "auto")
        POST: len(sessions) == total_count
        
        Thread-safety: Safe to call concurrently.
        """
        ...


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================

def verify_session_context(ctx: Any) -> bool:
    """Verify an object satisfies SessionContext contract."""
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
    """Verify two sessions are properly isolated."""
    ctx_a = registry.get_session(session_a)
    ctx_b = registry.get_session(session_b)

    if ctx_a is None or ctx_b is None:
        return False

    # Different workspaces = isolated
    if ctx_a.workspace_root != ctx_b.workspace_root:
        return True

    # Same workspace = shared (not isolated for files, but session IDs differ)
    return ctx_a.session_id != ctx_b.session_id
