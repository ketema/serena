"""
MCP Session Isolation Contract

Constitutional Reference: CL12 Design by Contract
Requirement: REQ-SESSION-002
Domain: Multi-project MCP session isolation

PURPOSE:
Defines the behavioral contract for MCP session isolation when multiple clients
connect to a single Serena HTTP server. Each client's session state must be
independent and persist across requests.

PROBLEM STATEMENT:
Observed: Client A activates project, Client B activates different project,
Client B's subsequent get_current_config returns "No active project".
Expected: Each client sees ONLY their own activated project.

ROOT CAUSE HYPOTHESIS:
The tool dispatch layer reads transport_session_id but does not restore
the application-layer session context before tool execution. The bridging
step from transport → application is missing or incomplete.

CONTRACT AUTHORITY:
This contract is the authoritative specification for session isolation behavior.
Tests and implementation MUST conform to this contract.

DESIGN DECISIONS (User-Adjudicated):
1. Session ID Unity: Transport session ID and application session ID MUST always
   be the same value. No translation, no mapping - one authoritative ID.
2. Early Propagation: Session ID MUST propagate from HTTP layer to application
   layer at the earliest possible point in the execution path.
3. Project Exclusivity: A project (by workspace root path) can only be activated
   by ONE session at a time on a given server.
4. LSP Resource Independence: LSP instances are shared resources, managed
   independently per existing LSP contracts. Session deactivation does NOT
   reclaim LSP resources if other sessions still need them.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


# =============================================================================
# EXCEPTIONS
# =============================================================================

class ProjectAlreadyActiveError(Exception):
    """
    Raised when attempting to activate a project that is already active
    in another session.

    INV-07: A project (workspace root) can only be active in ONE session at a time.
    """

    def __init__(self, project_name: str, workspace_root: Path, owning_session_id: str):
        self.project_name = project_name
        self.workspace_root = workspace_root
        self.owning_session_id = owning_session_id
        super().__init__(
            f"Project '{project_name}' (at {workspace_root}) is already active "
            f"in session '{owning_session_id}'. A project can only be active in "
            f"one session at a time."
        )


# =============================================================================
# DOMAIN TYPES
# =============================================================================

@dataclass(frozen=True)
class SessionContext:
    """
    Immutable session context bound to a workspace.

    INV: session_id is non-empty string
    INV: workspace_root is absolute path
    """
    session_id: str
    workspace_root: Path
    source: str = "explicit"  # "explicit" | "auto" | "anonymous"


# =============================================================================
# SESSION ID UNITY CONTRACT
# =============================================================================

@runtime_checkable
class SessionIdUnityContract(Protocol):
    """
    Contract for session ID unity between transport and application layers.

    INV-06: Transport session ID and application session ID MUST be identical.

    DESIGN DECISION (User-Adjudicated):
    "The two session IDs should always be the same."
    "The session ID needs to be set as soon as possible. As soon as the HTTP layer
    creates it, it needs to propagate up to the application layer. The earliest
    function in the execution path that can do that must take the responsibility."
    """

    def propagate_session_id_to_application(
        self,
        transport_session_id: str,
    ) -> None:
        """
        Propagate transport session ID to application layer.

        Called at the EARLIEST possible point after HTTP layer sets session ID.

        PRE-1: transport_session_id is non-empty string (from HTTP header)
        PRE-2: Called before any tool dispatch or application logic

        POST-1: Application session ID equals transport_session_id
        POST-2: get_current_session_id() returns transport_session_id

        INV-06: Transport and application session IDs are now identical

        ERRORS:
        - ValueError: if transport_session_id is empty
        """
        ...

    def verify_session_id_unity(
        self,
        transport_session_id: str,
        application_session_id: str | None,
    ) -> bool:
        """
        Verify that transport and application session IDs match.

        PRE: Both IDs obtained from their respective sources

        POST-1: Returns True if both are equal (including both None for STDIO)
        POST-2: Returns False if mismatch detected

        INV-06: Used for runtime verification of session ID unity

        ERRORS: None
        """
        ...


# =============================================================================
# SESSION ISOLATION CONTRACT
# =============================================================================

@runtime_checkable
class SessionIsolationContract(Protocol):
    """
    Contract for MCP session isolation.

    INVARIANTS (The "Never" List):
    - INV-01: Session A's project activation MUST NOT affect Session B's view
    - INV-02: get_current_config MUST return the project activated by THIS session
    - INV-03: Tool dispatch MUST use session ID from current request header
    - INV-04: At request start, session context MUST be restored from registry
    - INV-05: At request end, ContextVar MUST be reset to prevent leakage
    - INV-06: Transport session ID and application session ID MUST be identical
    - INV-07: A project (workspace root) can only be active in ONE session at a time
    - INV-08: Session switching projects deactivates previous project for THAT session
    - INV-09: LSP resources are NOT reclaimed on session project change (shared pool)
    """

    def restore_session_context_for_request(
        self,
        transport_session_id: str,
    ) -> bool:
        """
        Restore application-layer session context from transport session ID.

        Called at the START of each HTTP request/tool dispatch.

        PRE-1: transport_session_id is non-empty string (from HTTP header)
        PRE-2: Session registry is initialized and accessible

        POST-1: If session exists in registry:
                - _current_session_id ContextVar set to transport_session_id
                - _current_session ContextVar set to SessionContext from registry
                - Returns True
        POST-2: If session NOT in registry:
                - ContextVars unchanged
                - Returns False

        INV-03: Uses transport_session_id from parameter (current request),
                NOT any cached/stale value

        ERRORS:
        - ValueError: if transport_session_id is empty
        """
        ...

    def clear_session_context_after_request(self) -> None:
        """
        Clear application-layer session context after request completes.

        Called at the END of each HTTP request/tool dispatch.

        PRE: Called in finally block (guaranteed execution)

        POST-1: _current_session_id ContextVar reset to None
        POST-2: _current_session ContextVar reset to None

        INV-05: Prevents session context from leaking to next request

        ERRORS: None (idempotent, safe to call multiple times)
        """
        ...

    def get_current_session_for_request(self) -> SessionContext | None:
        """
        Get the session context for the current request.

        PRE: Called after restore_session_context_for_request()

        POST-1: Returns SessionContext if session was restored
        POST-2: Returns None if no session context (not restored or cleared)

        INV-02: Returns ONLY the session for THIS request's session_id

        ERRORS: None
        """
        ...


# =============================================================================
# TOOL DISPATCH CONTRACT
# =============================================================================

@runtime_checkable
class ToolDispatchSessionContract(Protocol):
    """
    Contract for tool dispatch with session context.

    This contract specifies how tool execution must handle session context
    to ensure isolation between concurrent clients.
    """

    def execute_tool_with_session_context(
        self,
        transport_session_id: str | None,
        tool_fn: callable,
        **kwargs,
    ) -> str:
        """
        Execute a tool within the correct session context.

        PRE-1: transport_session_id is from current request's HTTP header
               (may be None for STDIO mode)
        PRE-2: tool_fn is a callable that executes the tool

        POST-1: If transport_session_id is not None:
                - Session context restored before tool execution
                - Tool executes with correct session context
                - Session context cleared after execution (success or failure)
        POST-2: If transport_session_id is None (STDIO mode):
                - Tool executes directly without session context manipulation
        POST-3: Returns tool execution result as string

        INV-01: Session context is isolated per-request
        INV-03: Uses transport_session_id from parameter, not cached value
        INV-04: Context restored at start
        INV-05: Context cleared at end (in finally block)

        ERRORS:
        - Propagates any exception from tool_fn (after clearing context)
        """
        ...


# =============================================================================
# PROJECT EXCLUSIVITY CONTRACT
# =============================================================================

@runtime_checkable
class ProjectExclusivityContract(Protocol):
    """
    Contract for project exclusivity across sessions.

    A project (identified by workspace root path) can only be activated by
    ONE session at a time on a given server. This prevents resource conflicts
    and ensures clean session isolation.

    INV-07: A project (workspace root) can only be active in ONE session at a time
    """

    def is_project_active_in_other_session(
        self,
        workspace_root: Path,
        requesting_session_id: str,
    ) -> tuple[bool, str | None]:
        """
        Check if a project is already active in another session.

        PRE-1: workspace_root is absolute path
        PRE-2: requesting_session_id is non-empty string

        POST-1: Returns (True, other_session_id) if project active in different session
        POST-2: Returns (False, None) if project not active or active in same session

        INV-07: Enforces single-session-per-project rule

        ERRORS: None
        """
        ...

    def get_active_session_for_project(
        self,
        workspace_root: Path,
    ) -> str | None:
        """
        Get the session ID that currently has this project active.

        PRE: workspace_root is absolute path

        POST-1: Returns session_id if project is active in some session
        POST-2: Returns None if project not currently active

        ERRORS: None
        """
        ...


# =============================================================================
# SESSION PROJECT SWITCHING CONTRACT
# =============================================================================

@runtime_checkable
class SessionProjectSwitchingContract(Protocol):
    """
    Contract for session project switching behavior.

    When a session switches from Project A to Project C:
    - Project A is deactivated for that session
    - Project C becomes active for that session
    - LSP resources are NOT reclaimed (they may serve other sessions)

    INV-08: Session switching projects deactivates previous project for THAT session
    INV-09: LSP resources are NOT reclaimed on session project change
    """

    def switch_session_project(
        self,
        session_id: str,
        new_project_name: str,
    ) -> tuple[str | None, str]:
        """
        Switch a session from current project to new project.

        PRE-1: session_id is non-empty string
        PRE-2: new_project_name exists in config or is valid path
        PRE-3: new_project is not already active in ANOTHER session

        POST-1: Previous project (if any) deactivated for this session
        POST-2: New project activated for this session
        POST-3: Returns (previous_project_name, new_project_name)
        POST-4: LSP resources NOT reclaimed (INV-09)

        INV-07: If new project active in other session, raises error
        INV-08: Previous project deactivated for THIS session only

        ERRORS:
        - ValueError: if session_id is empty
        - ProjectNotFoundError: if new_project_name not found
        - ProjectAlreadyActiveError: if new_project active in another session
        """
        ...


# =============================================================================
# MULTI-CLIENT ISOLATION CONTRACT
# =============================================================================

@runtime_checkable
class MultiClientIsolationContract(Protocol):
    """
    Contract for multi-client session isolation.

    This is the high-level contract that defines the end-to-end behavior
    when multiple clients connect to the same server.

    COMPLETION PROMISE (Ralph Loop Exit):
    "Given two concurrent MCP clients with different session IDs, when each
    activates a different project, then each client's subsequent get_current_config
    call MUST return ONLY their own activated project (non-null, non-empty string)."
    """

    def activate_project_for_session(
        self,
        session_id: str,
        project_name: str,
    ) -> None:
        """
        Activate a project for a specific session.

        PRE-1: session_id is non-empty string
        PRE-2: project_name exists in config or is valid path
        PRE-3: Session context is restored for this session_id
        PRE-4: Project is NOT already active in a DIFFERENT session

        POST-1: Session bound to project's workspace_root in registry
        POST-2: Subsequent get_current_config for THIS session returns project
        POST-3: If session had previous project, it is deactivated

        INV-01: Other sessions' project bindings unaffected
        INV-07: Project exclusivity enforced

        ERRORS:
        - ValueError: if session_id is empty
        - ProjectNotFoundError: if project_name not found
        - ProjectAlreadyActiveError: if project active in another session
        """
        ...

    def get_current_config_for_session(
        self,
        session_id: str,
    ) -> dict:
        """
        Get current configuration for a specific session.

        PRE-1: session_id is non-empty string
        PRE-2: Session context is restored for this session_id

        POST-1: If session has activated project:
                Returns dict with "active_project" key containing project name
        POST-2: If session has no activated project:
                Returns dict with "active_project" = None or error message

        INV-02: Returns ONLY the project for THIS session
        INV-01: Other sessions' results unaffected

        ERRORS:
        - ValueError: if session_id is empty
        """
        ...


# =============================================================================
# VERIFICATION CRITERIA (Theater Detection)
# =============================================================================

"""
ADVERSARIAL TEST SCENARIO 1: Basic Session Isolation

Setup:
1. Start Serena HTTP server on port 9122
2. Client A connects with session_id = "session-A"
3. Client B connects with session_id = "session-B"

Test:
1. Client A: activate_project("serena")
2. Client B: activate_project("ametek_chess")
3. Client A: get_current_config() -> MUST contain "serena"
4. Client B: get_current_config() -> MUST contain "ametek_chess"

Failure Modes (Theater Detection):
- If Client B sees "serena" -> FAIL: Cross-contamination (INV-01 violated)
- If Client B sees "No active project" -> FAIL: Session not persisted (POST-1 violated)
- If Client B sees null or "" -> FAIL: Invalid response (POST-2 violated)
- If Client B sees "ametek_chess" -> PASS: Session isolation working

---

ADVERSARIAL TEST SCENARIO 2: Project Exclusivity

Setup:
1. Client A connects, activates "serena"
2. Client B connects, attempts to activate "serena" (SAME project)

Test:
1. Client A: activate_project("serena") -> SUCCESS
2. Client B: activate_project("serena") -> MUST raise ProjectAlreadyActiveError

Failure Modes:
- If Client B activation succeeds -> FAIL: INV-07 violated (project exclusivity)
- If Client B gets different error -> FAIL: Wrong error type
- If Client B gets ProjectAlreadyActiveError -> PASS

---

ADVERSARIAL TEST SCENARIO 3: Session Project Switching

Setup:
1. Client A activates "serena"
2. Client A switches to "ametek_chess"
3. Client B attempts to activate "serena" (now should be available)

Test:
1. Client A: activate_project("serena") -> SUCCESS
2. Client A: activate_project("ametek_chess") -> SUCCESS (switches)
3. Client A: get_current_config() -> MUST contain "ametek_chess"
4. Client B: activate_project("serena") -> SUCCESS (serena is now free)

Failure Modes:
- If Client A still sees "serena" after switch -> FAIL: INV-08 violated
- If Client B cannot activate "serena" -> FAIL: Previous session not released
- If both succeed correctly -> PASS

---

ADVERSARIAL TEST SCENARIO 4: LSP Resource Preservation

Setup:
1. Client A activates Python project "serena"
2. Client B activates Python project "ametek_chess"
3. Both use Python LSP
4. Client A switches to non-Python project

Test:
1. Client A uses Python LSP -> works
2. Client B uses Python LSP -> works (shared)
3. Client A switches away from serena
4. Client B continues using Python LSP -> MUST still work

Failure Modes:
- If Python LSP destroyed when Client A switches -> FAIL: INV-09 violated
- If Client B loses LSP access -> FAIL: Resource incorrectly reclaimed
- If Client B still has working Python LSP -> PASS

---

IMPLEMENTATION VERIFICATION:
The fix must ensure that in mcp.py execute_fn:
1. get_transport_session_id() returns the HTTP header session ID
2. Session ID propagates to application layer at earliest opportunity (INV-06)
3. MCPSessionBridge.set_session_context() is called to restore registry state
4. Tool executes with correct session context
5. MCPSessionBridge.reset_session_context() is called in finally block
6. Project exclusivity checked before activation (INV-07)
7. Previous project deactivated on switch (INV-08)
8. LSP resources NOT reclaimed on project switch (INV-09)
"""
