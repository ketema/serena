"""
Session Creation Trigger Contract - When Sessions Are Created

Constitutional Reference: CL12 Design by Contract
Domain: Session creation timing and triggers
Version: 1.0

AUTHORITY: This contract is AUTHORITATIVE for session creation behavior.
"""

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path


class SessionCreationTrigger(Enum):
    """Session creation trigger points."""

    TRANSPORT_CONNECT = "transport_connect"  # MCP transport connection established
    FIRST_TOOL_CALL = "first_tool_call"  # First tool invocation
    EXPLICIT_ACTIVATE = "explicit_activate"  # activate_project() called
    MCP_INITIALIZE = "mcp_initialize"  # MCP initialize request


class SessionCreationTriggerContract(ABC):
    """
    Contract for session creation timing.

    Issue #6 Open Question: "Session creation trigger: First tool call? Explicit activate_project? MCP initialize?"

    ANSWER (based on implementation analysis):
    - MCP Path: Session created on transport connection (Mcp-Session-Id header)
    - CLI Path: No session created (legacy single-project mode)
    - Anonymous: Created on first tool call if no session exists

    INVARIANTS:
    - INV-1: MCP sessions created exactly once per transport connection
    - INV-2: CLI invocations do NOT create sessions (backward compatibility)
    - INV-3: Anonymous sessions created lazily (on-demand)
    - INV-4: Session ID format determined by creation trigger
    """

    @abstractmethod
    def create_session_for_mcp_transport(
        self,
        mcp_session_id: str,
    ) -> str:
        """
        Create session when MCP transport connects.

        PRE: mcp_session_id from Mcp-Session-Id header (non-empty string)
        PRE: mcp_session_id not already in registry (caller must check)

        POST: New session created in registry with state=CREATED
        POST: workspace_root is None (no project bound yet)
        POST: Returns mcp_session_id unchanged

        INV (5-Point Checklist):
        1. State Invariance: Other sessions unaffected (session isolation),
           _active_project unchanged, existing registry entries unchanged
        2. Side Effect Prohibition: No LSP operations, no logging, no metrics,
           no network I/O (registry is in-memory only)
        3. Ordering Constraints: Thread-safe (holds registry lock during mutation),
           must NOT be called concurrently with same mcp_session_id
        4. Resource Invariants: No file handles opened, no connections established,
           registry size increases by exactly 1
        5. Exception Safety: On ValueError, registry unchanged (atomic - all or nothing)

        ERRORS:
        - ValueError: if mcp_session_id is empty string
        - ValueError: if mcp_session_id already exists in registry (PRE violation)

        NOTE: This is NOT idempotent. Callers must use get_or_create pattern
        if idempotent behavior is needed.

        TRIGGER: SessionCreationTrigger.TRANSPORT_CONNECT
        """
        ...

    @abstractmethod
    def bind_project_to_session(
        self,
        session_id: str,
        workspace_root: Path,
    ) -> None:
        """
        Bind a project to an existing session.

        PRE: session_id exists in registry
        PRE: workspace_root is absolute, existing directory

        POST: session.workspace_root = workspace_root
        POST: session.state = ACTIVE
        POST: session.touch() called (updates last_activity_time)

        INV (5-Point Checklist):
        1. State Invariance: session_id unchanged, activation_time unchanged (set on creation),
           other sessions unaffected (session isolation)
        2. Side Effect Prohibition: No logging, no metrics (touch() handles activity tracking),
           no network I/O beyond potential LSP workspace registration
        3. Ordering Constraints: Thread-safe (holds registry lock), if already bound to
           same workspace: idempotent no-op, if bound to different workspace: unbind old first
        4. Resource Invariants: May establish LSP workspace folder registration if needed,
           no file handles left open
        5. Exception Safety: On error (KeyError/FileNotFoundError/ValueError), session state
           unchanged from before call (atomic)

        ERRORS:
        - KeyError: if session_id not in registry
        - FileNotFoundError: if workspace_root does not exist
        - ValueError: if workspace_root is not absolute

        TRIGGER: SessionCreationTrigger.EXPLICIT_ACTIVATE
        """
        ...

    @abstractmethod
    def create_anonymous_session(
        self,
        workspace_root: Path | None = None,
    ) -> str:
        """
        Create anonymous session for backward compatibility.

        PRE: none (always safe to call)

        POST: Returns new session_id starting with "anonymous-"
        POST: Session in registry with TTL = SESSION_ANONYMOUS_TTL_SECONDS
        POST: If workspace_root provided and valid, session bound to it

        INV (5-Point Checklist):
        1. State Invariance: Existing sessions unaffected (session isolation),
           generated session_id is globally unique (UUID-based)
        2. Side Effect Prohibition: No logging, no metrics, no network I/O,
           no LSP operations until workspace explicitly bound
        3. Ordering Constraints: Thread-safe (holds registry lock during creation),
           anonymous sessions have shorter TTL than MCP sessions
        4. Resource Invariants: No file handles opened, no connections established,
           registry size increases by exactly 1
        5. Exception Safety: Never raises (always succeeds); invalid workspace_root
           silently ignored (session created without workspace)

        ERRORS: None (never raises - invalid workspace_root silently ignored)

        TRIGGER: SessionCreationTrigger.FIRST_TOOL_CALL (when no session exists)
        """
        ...
