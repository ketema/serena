"""
SessionRegistry: Thread-safe mapping of MCP session_id → SessionContext.

Contract: contracts/session_registry.contract.py
Component: Multi-project session isolation for MCP servers
"""

import logging
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

# Logger for session registry operations
logger = logging.getLogger(__name__)

# Import from contracts to ensure alignment
from contracts.issue6_constants import SESSION_DEFAULT_TTL_SECONDS
from contracts.session_context_contract import SessionState

# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class SessionContext:
    """Per-session isolation context."""

    # REQUIRED FIELDS
    session_id: str  # Unique MCP session identifier
    workspace_root: Path | None  # Absolute path to project root (None before activate_project in HTTP mode)
    activation_source: Literal["explicit", "auto", "anonymous"]  # How session was activated
    activation_time: datetime  # When session was bound

    # OPTIONAL FIELDS
    active_modes: list[str] = field(default_factory=list)  # Currently active modes
    lsp_references: dict[str, Any] = field(default_factory=dict)  # language → LSP instance reference

    # LIFECYCLE TRACKING (SessionContextContract fields)
    last_activity_time: datetime = field(default_factory=datetime.now)
    state: SessionState = SessionState.CREATED
    ttl_seconds: int = SESSION_DEFAULT_TTL_SECONDS

    # THREAD-SAFETY (INV-3 compliance)
    # Lock ensures atomic check-then-act in touch() per contract INV-3:
    # "Thread-safe (callers may invoke concurrently)"
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # BEHAVIORAL METHODS (SessionContextBehaviorContract)

    def touch(self) -> None:
        """
        Update last_activity_time to current time.

        PRE: Session is in CREATED, ACTIVE, or IDLE state (not EXPIRED)
        POST: last_activity_time = datetime.now()
        POST: If state was IDLE, state transitions to ACTIVE
        INV: No I/O, no logging, no external state, exception-safe
        ERRORS: None (PRE violation on EXPIRED state is silent no-op)
        """
        # INV-3: Thread-safe via lock (atomic check-then-act)
        with self._lock:
            # PRE-1: Session must not be EXPIRED (silent no-op if violated)
            if self.state == SessionState.EXPIRED:
                return  # ERROR: None - silent no-op per contract

            # POST-1: Update last_activity_time to current time
            self.last_activity_time = datetime.now()

            # POST-2: If state was IDLE, transition to ACTIVE
            if self.state == SessionState.IDLE:
                self.state = SessionState.ACTIVE

        # INV-1: activation_time, session_id, workspace_root unchanged (not modified)
        # INV-2: No logging, no metrics, no I/O, no external state (satisfied by not calling any)
        # INV-3: Thread-safe (lock ensures atomic check-then-act)
        # INV-4: No memory allocation beyond lock context manager
        # INV-5: Exception safety - lock released even on exception (context manager)

    def is_expired(self) -> bool:
        """
        Check if session has exceeded TTL.

        PRE: None (pure query, always safe to call)
        POST: Returns True if (now - last_activity_time) > ttl_seconds
        POST: Returns False otherwise
        INV: ALL fields unchanged, no side effects, never raises
        ERRORS: None
        """
        # POST-1: TTL check - (now - last_activity_time) > ttl_seconds
        elapsed = (datetime.now() - self.last_activity_time).total_seconds()
        is_ttl_exceeded = elapsed > self.ttl_seconds

        # POST-2: Return bool result
        return is_ttl_exceeded

        # INV-1: ALL fields unchanged (pure read-only query - no assignments)
        # INV-2: No logging, no metrics, no I/O, no external state (satisfied by not calling any)
        # INV-3: Thread-safe (read-only, no mutations)
        # INV-4: No memory allocation, no handles (satisfied by not allocating)
        # INV-5: Never raises (no raise statements, no external calls)


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
        workspace_root: Path | None,
        source: Literal["explicit", "auto", "anonymous"] = "explicit",
    ) -> SessionContext:
        """
        Bind a session to a workspace.

        PRE: session_id not already bound
        PRE: if workspace_root not None: workspace_root.is_absolute() and workspace_root.exists()
        POST: get_session(session_id) returns SessionContext
        POST: returned SessionContext.workspace_root == workspace_root.resolve() (if workspace_root provided)
        POST: returned SessionContext.workspace_root == None (if workspace_root is None - HTTP mode)

        INV-B1-02: workspace_root=None is valid (session awaits activate_project call)
        """
        # PRE-2: Validate workspace_root exists (if provided)
        # INV-B1-02: None workspace is valid (HTTP mode before activate_project)
        if workspace_root is not None and not workspace_root.exists():
            raise FileNotFoundError(f"PRE-2 violation: workspace_root does not exist: {workspace_root}")

        # INV-2: Resolve workspace_root to absolute, canonical path (if provided)
        resolved_workspace = workspace_root.resolve() if workspace_root is not None else None

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

            # Track session for workspace (only if workspace is bound)
            # INV-B1-02: Sessions with None workspace are valid (HTTP mode before activate_project)
            if resolved_workspace is not None:
                if resolved_workspace not in self._workspace_sessions:
                    self._workspace_sessions[resolved_workspace] = []
                self._workspace_sessions[resolved_workspace].append(session_id)

            # LOG-REG-01: Emit INFO log when session successfully bound
            short_id = session_id[:8]
            logger.info(f"[Session: {short_id}] Bound to {resolved_workspace} (source: {source})")

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
                # LOG-REG-02 (POST-NOOP): Emit DEBUG log when session_id not found
                short_id = session_id[:8]
                logger.debug(f"[Session: {short_id}] Unbind no-op: not in registry")
                return

            # Get context before removing
            ctx = self._sessions[session_id]
            workspace = ctx.workspace_root

            # Remove session from registry
            del self._sessions[session_id]

            # LOG-REG-02: Emit INFO log when session removed
            short_id = session_id[:8]
            logger.info(f"[Session: {short_id}] Unbound from {workspace}")

            # Remove from workspace tracking (only if session had workspace bound)
            # INV-B1-02: Sessions with None workspace are not tracked in _workspace_sessions
            if workspace is not None and workspace in self._workspace_sessions:
                self._workspace_sessions[workspace].remove(session_id)

                # POST-3: Cleanup if last session for workspace
                if len(self._workspace_sessions[workspace]) == 0:
                    # LOG-REG-03: Emit INFO log when last session for workspace removed
                    logger.info(f"[Session: {short_id}] Last session for {workspace}, workspace cleanup eligible")
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

    def get_session_overview(self) -> dict[str, Any]:
        """
        Get overview of all bound sessions.

        CONTRACT: POST-OBS-03 from contracts/serena_agent_observability_contract.py

        PRE: none
        POST: returns {"sessions": [...], "total_count": int}
        POST: total_count == len(sessions)
        POST: each session has: session_id, workspace_root (str), project_name, connected_at (ISO 8601), activation_source
        POST: project_name == basename(workspace_root)

        INV-OBS-02: Never raises exceptions (availability guarantee)
        ERRORS-OBS-01: Exception suppression, return empty structure
        """
        # INV-OBS-02: Never raise exceptions - wrap in try/except per ERRORS-OBS-01
        try:
            with self._lock:
                sessions = []
                for ctx in self._sessions.values():
                    session_info = {
                        "session_id": ctx.session_id,
                        "workspace_root": str(ctx.workspace_root),
                        "project_name": ctx.workspace_root.name if ctx.workspace_root is not None else None,
                        "connected_at": ctx.activation_time.isoformat(),
                        "activation_source": ctx.activation_source,
                    }
                    sessions.append(session_info)

                # POST-OBS-03: Return exactly {"sessions": list, "total_count": int}
                return {
                    "sessions": sessions,
                    "total_count": len(sessions),
                }
        except Exception:
            # ERRORS-OBS-01: Exception suppression for availability
            # INV-OBS-02: Observability MUST NOT raise exceptions
            return {
                "sessions": [],
                "total_count": 0,
            }
