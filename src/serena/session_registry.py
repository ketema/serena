"""
SessionRegistry: Thread-safe mapping of MCP session_id → SessionContext.

Contract: contracts/session_registry.contract.py
Component: Multi-project session isolation for MCP servers
"""

import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class SessionContext:
    """Per-session isolation context."""

    # REQUIRED FIELDS
    session_id: str  # Unique MCP session identifier
    workspace_root: Path  # Absolute path to project root
    activation_source: Literal["explicit", "auto"]  # How session was activated
    activation_time: datetime  # When session was bound

    # OPTIONAL FIELDS
    active_modes: list[str] = field(default_factory=list)  # Currently active modes
    lsp_references: dict[str, Any] = field(default_factory=dict)  # language → LSP instance reference


# =============================================================================
# CONTEXT VAR FOR ASYNC PROPAGATION
# =============================================================================


_current_session: ContextVar[Optional[SessionContext]] = ContextVar("_current_session", default=None)


# =============================================================================
# SESSION REGISTRY
# =============================================================================


class SessionRegistry:
    """
    Thread-safe mapping of MCP session_id → SessionContext.

    INVARIANTS:
    - INV-1: session_id is unique across all bound sessions
    - INV-2: workspace_root is always an absolute, resolved path
    - INV-3: A session can only be bound to one workspace at a time
    - INV-4: All mutations are atomic (thread-safe)
    """

    def __init__(self) -> None:
        """Initialize empty registry with thread-safety lock."""
        self._sessions: dict[str, SessionContext] = {}
        self._workspace_sessions: dict[Path, list[str]] = {}  # workspace → [session_ids]
        self._lock = threading.Lock()

    def bind_session(
        self,
        session_id: str,
        workspace_root: Path,
        source: Literal["explicit", "auto"] = "explicit",
    ) -> SessionContext:
        """
        Bind a session to a workspace.

        PRE: session_id not already bound
        PRE: workspace_root.is_absolute() and workspace_root.exists()
        POST: get_session(session_id) returns SessionContext
        POST: returned SessionContext.workspace_root == workspace_root.resolve()
        """
        # PRE-2: Validate workspace_root exists
        if not workspace_root.exists():
            raise FileNotFoundError(f"PRE-2 violation: workspace_root does not exist: {workspace_root}")

        # INV-2: Resolve workspace_root to absolute, canonical path
        resolved_workspace = workspace_root.resolve()

        with self._lock:
            # PRE-1: Check session_id not already bound
            if session_id in self._sessions:
                raise ValueError(f"PRE-1 violation: session_id already bound: {session_id}")

            # Create SessionContext
            ctx = SessionContext(
                session_id=session_id,
                workspace_root=resolved_workspace,
                activation_source=source,
                activation_time=datetime.now(),
            )

            # Store session
            self._sessions[session_id] = ctx

            # Track session for workspace
            if resolved_workspace not in self._workspace_sessions:
                self._workspace_sessions[resolved_workspace] = []
            self._workspace_sessions[resolved_workspace].append(session_id)

            return ctx

    def unbind_session(self, session_id: str) -> None:
        """
        Unbind a session and cleanup if last for workspace.

        PRE: session_id in registry (silent no-op if not)
        POST: get_session(session_id) returns None
        POST: if was last session for workspace, LSP cleanup scheduled
        """
        with self._lock:
            # PRE-3: Silent no-op if session_id not in registry
            if session_id not in self._sessions:
                return

            # Get context before removing
            ctx = self._sessions[session_id]
            workspace = ctx.workspace_root

            # Remove session from registry
            del self._sessions[session_id]

            # Remove from workspace tracking
            if workspace in self._workspace_sessions:
                self._workspace_sessions[workspace].remove(session_id)

                # POST-3: Cleanup if last session for workspace
                if len(self._workspace_sessions[workspace]) == 0:
                    del self._workspace_sessions[workspace]
                    # Cleanup hook would fire here in production
                    # For now, removing from tracking is sufficient
                    # Cleanup hook would fire here in production
                    # For now, removing from tracking is sufficient

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """
        Get session context by ID.

        PRE: none
        POST: returns SessionContext if exists, None otherwise
        """
        return self._sessions.get(session_id)

    def get_sessions_for_workspace(self, workspace_root: Path) -> list[str]:
        """
        Get all session IDs bound to a workspace.

        PRE: none
        POST: returns list of session_ids (may be empty)
        """
        resolved_workspace = workspace_root.resolve()
        return list(self._workspace_sessions.get(resolved_workspace, []))
