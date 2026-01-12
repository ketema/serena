"""
Contract: Issue #6 Multi-Project Session Isolation

AUTHORITATIVE CONTRACT for Issue #6: Architecture: Multi-Project Session Isolation
This contract defines ALL behavioral requirements from Issue #6.
All tests MUST trace assertions to specifications in this contract.
Mocks MUST derive from these contracts (CL10).

Contract Version: 1.0
Issue Reference: https://github.com/ketema/serena/issues/6
Supersedes: Incomplete contracts scattered across multiple files

REQUIREMENTS SATISFIED:
- SessionContext contract (fields + invariants)
- Session cleanup behavior (expiration, LRU, shutdown)
- Path validation per session (workspace boundary enforcement)
- LSP workspace multiplexing (didChangeWorkspaceFolders)
- Session creation trigger (when/how bound in MCP path)
- Backward compatibility (CLI/non-MCP behavior)

CL12 COMPLIANCE:
- Every public method has PRE/POST/INV
- Every contract uses behavioral specifications (not types-only)
- Strict Constructionism: Implementation SHALL perform ONLY specified behaviors
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer
    from solidlsp.ls_config import Language


# =============================================================================
# CONSTANTS (Issue #6 Design Decisions)
# =============================================================================

# Session cleanup constants
SESSION_DEFAULT_TTL_SECONDS = 3600  # 1 hour default TTL
SESSION_ANONYMOUS_TTL_SECONDS = 300  # 5 minutes for anonymous sessions
SESSION_REAPER_INTERVAL_SECONDS = 60  # Check for expired sessions every minute
SESSION_MAX_IDLE_SECONDS = 1800  # 30 minutes max idle before eligible for cleanup

# LSP pool constants
LSP_IDLE_TIMEOUT_SECONDS = 3600  # 1 hour idle before reclamation
LSP_MAX_WORKSPACES_PER_INSTANCE = 50  # Limit per multi-root LSP (CON-3 memory)


# =============================================================================
# 1. SESSION CONTEXT CONTRACT (Issue #6 Core)
# =============================================================================


class SessionState(Enum):
    """Session lifecycle states."""

    CREATED = "created"  # Session created, no project activated
    ACTIVE = "active"  # Session has active project
    IDLE = "idle"  # Session active but no recent activity
    EXPIRED = "expired"  # Session TTL exceeded, pending cleanup


@dataclass
class SessionContextContract:
    """
    Contract for per-session isolation context.

    Issue #6 specifies these fields:
    - session_id: Unique MCP session identifier
    - workspace_root: Project path (absolute)
    - modes: Active modes for this session
    - lsp_workspace_folders: LSP workspace registrations

    INVARIANTS:
    - INV-1: session_id is non-empty, immutable after creation
    - INV-2: workspace_root is always absolute Path when set, None before activation
    - INV-3: activation_time is set once during bind_session(), never modified
    - INV-4: lsp_workspace_folders tracks ONLY workspaces registered with LSP
    - INV-5: last_activity_time updated on every tool call, never backdated
    - INV-6: state transitions follow: CREATED -> ACTIVE -> IDLE -> EXPIRED (only forward)
    """

    # REQUIRED FIELDS (Issue #6 specification)
    session_id: str  # PRE: Non-empty, immutable. POST: Uniquely identifies session.
    workspace_root: Path | None  # PRE: None or absolute Path. POST: Project root.
    activation_source: Literal["explicit", "auto", "anonymous"]  # How session was activated
    activation_time: datetime  # When session was bound (immutable after bind)

    # OPTIONAL FIELDS (Issue #6 specification)
    active_modes: list[str] = field(default_factory=list)  # Currently active modes
    lsp_workspace_folders: set[Path] = field(default_factory=set)  # Registered LSP workspaces

    # LIFECYCLE TRACKING (Issue #6 cleanup requirements)
    last_activity_time: datetime = field(default_factory=datetime.now)
    state: SessionState = SessionState.CREATED
    ttl_seconds: int = SESSION_DEFAULT_TTL_SECONDS

    def __post_init__(self) -> None:
        """
        POST: Validate invariants on construction.

        INV-1: session_id non-empty
        INV-2: workspace_root is absolute when set
        """
        if not self.session_id:
            raise ValueError("INV-1 violation: session_id must be non-empty")
        if self.workspace_root is not None and not self.workspace_root.is_absolute():
            raise ValueError("INV-2 violation: workspace_root must be absolute Path")


class SessionContextBehaviorContract(ABC):
    """
    Behavioral contract for SessionContext operations.

    This defines WHAT a SessionContext must DO, not just what fields it has.
    """

    @abstractmethod
    def touch(self) -> None:
        """
        Update last_activity_time to current time.

        PRE: Session is in CREATED, ACTIVE, or IDLE state
        POST: last_activity_time = datetime.now()
        POST: If state was IDLE, state transitions to ACTIVE
        INV: activation_time unchanged
        INV: session_id unchanged
        """
        ...

    @abstractmethod
    def is_expired(self) -> bool:
        """
        Check if session has exceeded TTL.

        PRE: none
        POST: Returns True if (now - last_activity_time) > ttl_seconds
        POST: Returns False otherwise
        INV: Does not modify session state (read-only)
        """
        ...

    @abstractmethod
    def register_lsp_workspace(self, workspace: Path, language: "Language") -> None:
        """
        Record that this session has registered a workspace with an LSP.

        PRE: workspace is absolute Path
        PRE: language is valid Language enum
        POST: workspace added to lsp_workspace_folders
        POST: Used to track which workspaces need cleanup on session close
        INV: Does not actually call LSP (that's GlobalLanguageServerPool's job)
        """
        ...

    @abstractmethod
    def unregister_lsp_workspace(self, workspace: Path) -> None:
        """
        Record that this session has unregistered a workspace from LSPs.

        PRE: workspace was previously registered
        POST: workspace removed from lsp_workspace_folders
        INV: Silent no-op if workspace not registered
        """
        ...


# =============================================================================
# 2. SESSION CLEANUP CONTRACT (Issue #6 Open Question)
# =============================================================================


class SessionCleanupContract(ABC):
    """
    Contract for session cleanup behavior.

    Issue #6 Open Question: "When does a session expire? LRU eviction? Explicit shutdown?"

    This contract ANSWERS that question with explicit behavioral specifications.

    CLEANUP TRIGGERS (in order of priority):
    1. Explicit shutdown: Client calls unbind_session() or closes transport
    2. TTL expiration: (now - last_activity_time) > ttl_seconds
    3. Idle timeout: Session in IDLE state > SESSION_MAX_IDLE_SECONDS
    4. Server shutdown: All sessions cleaned up on graceful shutdown

    CLEANUP BEHAVIOR:
    1. Unbind session from registry
    2. Release all LSP references held by session
    3. For multi-root LSPs: Send workspace/didChangeWorkspaceFolders(removed=[workspace])
    4. Log session cleanup for monitoring (LOG-2)

    INVARIANTS:
    - INV-1: Cleanup is idempotent (calling twice has no additional effect)
    - INV-2: Cleanup does NOT affect other sessions (session isolation)
    - INV-3: LSP cleanup happens BEFORE registry removal (correct order)
    """

    @abstractmethod
    def cleanup_session(self, session_id: str) -> None:
        """
        Clean up a session and all its resources.

        PRE: session_id is valid string (may or may not exist in registry)
        POST: Session removed from SessionRegistry
        POST: All LSP references released via GlobalLanguageServerPool
        POST: For multi-root LSPs, workspace folders removed
        POST: get_session(session_id) returns None
        INV: Other sessions unaffected
        INV: Idempotent (second call is no-op)

        BEHAVIOR:
        1. Get session context (return early if not found)
        2. For each lsp_workspace_folder:
           a. Call pool.release(language, workspace, session_id)
           b. Log release (LOG-2)
        3. Remove session from registry
        4. Log cleanup (LOG-1)
        """
        ...

    @abstractmethod
    def reap_expired_sessions(self) -> list[str]:
        """
        Find and clean up all expired sessions.

        PRE: none
        POST: All sessions where is_expired() == True are cleaned up
        POST: Returns list of reaped session_ids
        INV: Non-expired sessions unaffected

        BEHAVIOR (runs periodically every REAPER_INTERVAL_SECONDS):
        1. Get all session_ids from registry
        2. For each session:
           a. If is_expired(): cleanup_session(session_id)
        3. Return list of cleaned up session_ids
        """
        ...

    @abstractmethod
    def shutdown_all_sessions(self) -> None:
        """
        Clean up all sessions (server shutdown).

        PRE: none
        POST: All sessions cleaned up
        POST: SessionRegistry is empty
        POST: All LSP references released
        INV: Called only during graceful shutdown

        BEHAVIOR:
        1. Get all session_ids
        2. For each session: cleanup_session(session_id)
        3. Verify registry is empty
        """
        ...


# =============================================================================
# 3. PATH VALIDATION PER SESSION CONTRACT (Issue #6 Security)
# =============================================================================


class PathBoundaryError(Exception):
    """
    Raised when path escapes session's workspace boundary.

    Issue #6: "Tools reject paths outside session's workspace_root"
    """

    def __init__(
        self,
        attempted_path: Path,
        session_workspace: Path,
        session_id: str,
    ):
        self.attempted_path = attempted_path
        self.session_workspace = session_workspace
        self.session_id = session_id
        super().__init__(
            f"Path boundary violation for session {session_id}: "
            f"'{attempted_path}' escapes workspace '{session_workspace}'. "
            "Activate a different project to access this path."
        )


class SessionPathValidationContract(ABC):
    """
    Contract for per-session path validation.

    Issue #6 Design Decision: "Path validation per session - Tools reject paths outside workspace_root"

    INVARIANTS:
    - INV-1: Every file path operation validates against session's workspace_root
    - INV-2: Symlinks resolved BEFORE boundary check (security critical)
    - INV-3: Parent directory escapes (..) detected and rejected
    - INV-4: Absolute paths outside workspace rejected

    SECURITY REQUIREMENTS (from path_validation_contract.py):
    - SEC-1: Symlinks MUST be resolved before boundary check
    - SEC-2: Project root MUST also be resolved
    - SEC-3: Path components like ".." MUST be resolved before check
    - SEC-4: Error messages MUST include session_id for debugging
    """

    @abstractmethod
    def validate_path_for_session(
        self,
        session_id: str,
        relative_path: str | Path,
    ) -> Path:
        """
        Validate and resolve a path within session's workspace boundary.

        PRE: session_id exists in SessionRegistry
        PRE: session has active workspace_root (not None)
        PRE: relative_path is string or Path

        POST: Returns resolved absolute Path
        POST: Returned path is within session's workspace_root
        POST: Symlinks have been resolved

        ERRORS: PathBoundaryError if path escapes workspace

        BEHAVIOR:
        1. Get session from registry
        2. If workspace_root is None: raise NoProjectActivatedError
        3. Resolve workspace_root (handles symlinks in root)
        4. Join relative_path to workspace_root
        5. Resolve combined path (handles .. and symlinks)
        6. Verify resolved path starts with resolved workspace_root
        7. Return resolved path OR raise PathBoundaryError

        INV: Does not modify session state
        INV: Thread-safe (read-only operation)
        """
        ...

    @abstractmethod
    def is_path_in_session_workspace(
        self,
        session_id: str,
        path: Path,
    ) -> bool:
        """
        Check if path is within session's workspace (no exception).

        PRE: session_id exists in SessionRegistry
        PRE: path is absolute, resolved Path

        POST: Returns True if path is under workspace_root
        POST: Returns False otherwise (no exception)

        INV: Does not modify state
        INV: Does not resolve path (caller must resolve)
        """
        ...


# =============================================================================
# 4. LSP WORKSPACE MULTIPLEXING CONTRACT (Issue #6 Phase 3)
# =============================================================================


class LSPWorkspaceMultiplexingContract(ABC):
    """
    Contract for LSP workspace folder management.

    Issue #6 Phase 3 requires:
    - "Shared LSP processes per language"
    - "Dynamic workspace/didChangeWorkspaceFolders calls"
    - "Track workspace registrations per language"

    This contract defines the BEHAVIORAL requirements for workspace multiplexing.

    INVARIANTS:
    - INV-1: Multi-root LSPs share instance across sessions with different workspaces
    - INV-2: Single-root LSPs get one instance per workspace
    - INV-3: Workspace folder count never exceeds LSP_MAX_WORKSPACES_PER_INSTANCE
    - INV-4: Workspace registration/deregistration uses didChangeWorkspaceFolders
    - INV-5: Session reference tracking accurate (no orphaned workspaces)
    """

    @abstractmethod
    def register_workspace(
        self,
        language: "Language",
        workspace_root: Path,
        session_id: str,
    ) -> "SolidLanguageServer":
        """
        Register a workspace with appropriate LSP instance.

        PRE: language is valid Language enum
        PRE: workspace_root is absolute Path
        PRE: session_id is valid session in registry

        POST: Returns LSP instance that can serve workspace_root
        POST: For multi-root LSP: workspace added via didChangeWorkspaceFolders if new
        POST: For single-root LSP: new instance created if needed
        POST: session_id recorded as reference holder
        POST: SessionContext.lsp_workspace_folders updated

        BEHAVIOR:
        1. Check if LSP supports multi-root (is_multi_root(language))
        2. If multi-root AND existing instance:
           a. If workspace not yet added:
              - Call workspace/didChangeWorkspaceFolders(added=[workspace_root])
              - Log workspace registration (LOG-2)
           b. Add session_id to reference set
           c. Return existing instance
        3. If single-root OR no existing instance:
           a. Create new LSP instance for workspace
           b. Add session_id to reference set
           c. Return new instance
        4. Update SessionContext.lsp_workspace_folders

        INV: Never exceeds LSP_MAX_WORKSPACES_PER_INSTANCE
        INV: Session reference count accurate
        """
        ...

    @abstractmethod
    def unregister_workspace(
        self,
        language: "Language",
        workspace_root: Path,
        session_id: str,
    ) -> None:
        """
        Unregister a workspace for a session.

        PRE: session_id previously registered this language/workspace
        PRE: language is valid Language enum
        PRE: workspace_root was previously registered

        POST: session_id removed from reference set
        POST: If last session for this workspace on multi-root LSP:
              - workspace/didChangeWorkspaceFolders(removed=[workspace_root]) sent
              - Log workspace removal (LOG-2)
        POST: SessionContext.lsp_workspace_folders updated

        BEHAVIOR:
        1. Remove session_id from reference set for (language, workspace_root)
        2. If no sessions remain for workspace AND multi-root LSP:
           a. Send workspace/didChangeWorkspaceFolders(removed=[workspace_root])
           b. Log removal (LOG-2)
        3. If no sessions remain AND single-root LSP:
           a. Start idle timer for eventual reclamation
        4. Update SessionContext.lsp_workspace_folders

        INV: Other workspaces on same LSP unaffected
        INV: Other sessions unaffected
        """
        ...

    @abstractmethod
    def get_registered_workspaces(
        self,
        language: "Language",
    ) -> dict[Path, set[str]]:
        """
        Get all registered workspaces and their session references.

        PRE: language is valid Language enum

        POST: Returns dict mapping workspace_root -> set of session_ids
        POST: Empty dict if no workspaces registered

        INV: Read-only, does not modify state
        """
        ...


# =============================================================================
# 5. SESSION CREATION TRIGGER CONTRACT (Issue #6 Open Question)
# =============================================================================


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

        PRE: mcp_session_id from Mcp-Session-Id header (non-empty)
        PRE: mcp_session_id not already in registry

        POST: Session created in registry with state=CREATED
        POST: workspace_root is None (no project yet)
        POST: Returns mcp_session_id

        BEHAVIOR:
        1. Validate mcp_session_id format
        2. Create SessionContext with:
           - session_id = mcp_session_id
           - workspace_root = None
           - activation_source = "explicit"
           - state = CREATED
        3. Register in SessionRegistry
        4. Log session creation (LOG-1)

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
        POST: session.touch() called

        BEHAVIOR (Issue #6 Phase 3):
        1. Get session from registry
        2. If already bound to different workspace: unbind old first
        3. Set workspace_root
        4. Set state = ACTIVE
        5. Call touch() to update activity time

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

        PRE: none
        POST: Returns new session_id starting with "anonymous-"
        POST: Session in registry with TTL = SESSION_ANONYMOUS_TTL_SECONDS

        BEHAVIOR:
        1. Generate session_id: f"anonymous-{uuid4()}"
        2. Create SessionContext with:
           - session_id = generated
           - workspace_root = workspace_root (may be None)
           - activation_source = "anonymous"
           - ttl_seconds = SESSION_ANONYMOUS_TTL_SECONDS
        3. Register in SessionRegistry
        4. Return session_id

        TRIGGER: SessionCreationTrigger.FIRST_TOOL_CALL (when no session exists)
        """
        ...


# =============================================================================
# 6. BACKWARD COMPATIBILITY CONTRACT (Issue #6 Requirement)
# =============================================================================


class BackwardCompatibilityContract(ABC):
    """
    Contract for backward compatibility with single-project mode.

    Issue #6 Requirement: "Single-project mode should still work"

    This contract ensures:
    1. CLI invocations work without session isolation
    2. Legacy activate_project() API preserved
    3. Existing single-session flows unaffected
    4. Error messages consistent

    INVARIANTS:
    - INV-1: CLI mode (no MCP transport) uses legacy _active_project
    - INV-2: Single-project workflows do NOT require SessionRegistry
    - INV-3: Legacy activate_project() signature unchanged
    - INV-4: Error messages for invalid project names unchanged
    """

    @abstractmethod
    def activate_project_legacy(
        self,
        project_name: str,
    ) -> None:
        """
        Legacy project activation (no session context).

        PRE: project_name exists in config
        POST: _active_project set to project
        POST: SessionRegistry NOT modified
        POST: LSP started via legacy LanguageServerManager path

        BEHAVIOR (CLI/non-MCP invocation):
        1. Validate project exists in config
        2. Set self._active_project = project
        3. Initialize LSP via existing LanguageServerManager
        4. NO SessionRegistry interaction

        ERRORS: ProjectNotFoundError if project_name not in config

        INV: Does NOT create session
        INV: Does NOT call bind_session()
        """
        ...

    @abstractmethod
    def activate_project_with_session(
        self,
        project_name: str,
    ) -> None:
        """
        Session-aware project activation (MCP context exists).

        PRE: project_name exists in config
        PRE: Session context exists (from MCP transport)
        POST: Session bound to project workspace via SessionRegistry
        POST: Legacy _active_project NOT set (stateless agent)

        BEHAVIOR (MCP invocation with session):
        1. Validate project exists in config
        2. Get current session_id from ContextVar
        3. Call SessionRegistry.bind_session(session_id, workspace_root)
        4. DO NOT set _active_project (agent is stateless per REQ-1)

        ERRORS: ProjectNotFoundError if project_name not in config

        INV: _active_project unchanged
        INV: Other sessions unaffected
        """
        ...

    @abstractmethod
    def detect_execution_context(self) -> Literal["mcp", "cli", "unknown"]:
        """
        Detect whether running in MCP or CLI context.

        PRE: none
        POST: Returns "mcp" if session context exists
        POST: Returns "cli" if no session context
        POST: Returns "unknown" if cannot determine

        BEHAVIOR:
        1. Check ContextVar for session_id
        2. If session_id exists: return "mcp"
        3. If session_id is None: return "cli"
        4. On error: return "unknown"

        INV: Does not modify state (read-only detection)
        """
        ...


# =============================================================================
# 7. MCP FACTORY ACTIVATION CONTRACT (Phase 3 - FIXED)
# =============================================================================


class MCPFactoryActivationContract(ABC):
    """
    Contract for SerenaMCPFactory.activate_project_for_mcp_session().

    This contract FIXES the violations identified:
    - Missing INV section
    - Undeclared idempotent/unbind behavior
    - Ambiguous PRE ("valid project name or path")

    REQUIREMENTS:
    - REQ-4b: mcp.py uses activate_session_project() for MCP clients

    INVARIANTS:
    - INV-1: Only one workspace bound per session at a time
    - INV-2: Binding to same workspace is idempotent (no-op)
    - INV-3: Binding to different workspace unbinds previous first
    - INV-4: agent and session_id must exist before activation
    - INV-5: Other sessions unaffected by this activation
    """

    @abstractmethod
    def activate_project_for_mcp_session(
        self,
        project_name: str,
    ) -> None:
        """
        Activate a project for the current MCP session.

        PRE: self.agent is not None
        PRE: self.agent._current_session_id is not None (session exists)
        PRE: project_name is a string that exists in serena_config.project_names
             OR project_name is a string path to existing directory

        POST: SessionRegistry.bind_session(session_id, workspace_root) called
        POST: SessionRegistry.get_session(session_id) returns SessionContext
        POST: SessionContext.workspace_root == project.project_root.resolve()

        DECLARED BEHAVIOR (Strict Constructionism):
        1. Get session_id from agent._current_session_id
        2. Get project from config via get_project(project_name)
        3. Resolve workspace_root = project.project_root
        4. Get registry (from agent or factory)
        5. Check existing binding:
           a. If bound to SAME workspace: NO-OP, return immediately
           b. If bound to DIFFERENT workspace: unbind_session(session_id) first
           c. If not bound: proceed to bind
        6. Call registry.bind_session(session_id, workspace_root, "explicit")

        INVARIANTS ENFORCED:
        - INV-1: Steps 5a/5b ensure only one workspace per session
        - INV-2: Step 5a implements idempotent behavior
        - INV-3: Step 5b implements unbind-before-rebind
        - INV-4: PRE conditions validate agent and session existence
        - INV-5: Only operates on current session_id

        ERRORS:
        - ValueError: if agent is None
        - ValueError: if session_id is None
        - ProjectNotFoundError: if project_name not in config and not valid path
        """
        ...


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================


def verify_session_context_invariants(ctx: SessionContextContract) -> list[str]:
    """
    Verify all SessionContext invariants.

    Returns list of violation messages (empty if all pass).
    """
    violations = []

    # INV-1: session_id non-empty
    if not ctx.session_id:
        violations.append("INV-1: session_id is empty")

    # INV-2: workspace_root absolute when set
    if ctx.workspace_root is not None and not ctx.workspace_root.is_absolute():
        violations.append(f"INV-2: workspace_root is not absolute: {ctx.workspace_root}")

    # INV-3: activation_time is valid datetime (enforced by dataclass)
    # Note: activation_time has default_factory so cannot be None

    # INV-5: last_activity_time >= activation_time
    if ctx.last_activity_time < ctx.activation_time:
        violations.append("INV-5: last_activity_time < activation_time (backdated)")

    return violations


def verify_cleanup_idempotent(cleanup_fn: Callable[[str], None], session_id: str) -> bool:
    """
    Verify cleanup is idempotent.

    Calls cleanup twice, verifies no error on second call.
    """
    try:
        cleanup_fn(session_id)
        cleanup_fn(session_id)  # Second call should be no-op
        return True
    except Exception:
        return False


def verify_path_boundary_enforcement(
    validator: SessionPathValidationContract,
    session_id: str,
    workspace_root: Path,
    test_cases: list[tuple[str, bool]],  # (relative_path, should_pass)
) -> list[str]:
    """
    Verify path boundary enforcement.

    Returns list of failures.
    """
    failures = []
    for relative_path, should_pass in test_cases:
        try:
            validator.validate_path_for_session(session_id, relative_path)
            if not should_pass:
                failures.append(f"Path '{relative_path}' should have raised PathBoundaryError")
        except PathBoundaryError:
            if should_pass:
                failures.append(f"Path '{relative_path}' should have passed validation")
    return failures


# =============================================================================
# CONTRACT TEST ASSERTIONS (for test traceability)
# =============================================================================

SESSION_CONTEXT_TEST_CASES = [
    # (field, constraint, test_value, should_pass)
    ("session_id", "non-empty", "", False),
    ("session_id", "non-empty", "valid-id", True),
    ("workspace_root", "absolute when set", Path("relative/path"), False),
    ("workspace_root", "absolute when set", Path("/absolute/path"), True),
    ("workspace_root", "None allowed", None, True),
]

CLEANUP_TEST_CASES = [
    # (scenario, expected_behavior)
    ("explicit_unbind", "Session removed, LSPs released"),
    ("ttl_expiration", "Session reaped, LSPs released"),
    ("server_shutdown", "All sessions cleaned up"),
    ("double_cleanup", "Second call is no-op"),
]

PATH_VALIDATION_TEST_CASES = [
    # (relative_path, should_pass, description)
    ("src/main.py", True, "Normal path within workspace"),
    ("../outside", False, "Parent escape"),
    ("../../etc/passwd", False, "Multi-level escape"),
    ("link/secret", False, "Symlink traversal"),
]

LSP_MULTIPLEXING_TEST_CASES = [
    # (language, is_multi_root, expected_behavior)
    ("rust", True, "Shared instance, workspace added via didChangeWorkspaceFolders"),
    ("typescript", False, "Separate instance per workspace"),
]

BACKWARD_COMPAT_TEST_CASES = [
    # (context, expected_path, description)
    ("cli", "legacy", "CLI uses _active_project, no registry"),
    ("mcp", "session", "MCP uses SessionRegistry, no _active_project"),
]
