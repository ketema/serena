"""
Contract: Multi-Session State Isolation (REQ-2026-004)

Defines the behavioral contract for isolating per-session state when multiple
MCP clients connect to a single SerenaAgent instance over HTTP transport.

AUTHORITY: This contract is AUTHORITATIVE for session isolation behavior.
Supersedes any contradicting behavior in serena_agent_stateless_contract.py
or mcp_session_bridge_contract.py for the specific behaviors defined here.

DISCOVERY: Built from DISCONNECT MATRIX (.claude/disconnect-matrix-session-contextvar.md)
- B1: Session creation workspace defaults to Path.cwd() instead of None
- B2: _update_active_tools() mutates shared Agent state
- B3: _activate_project rebinds session + mutates shared state
- B4: Last activate_project wins for all clients (consequence of B2)

CROSS-REFERENCES:
- requirements/REQ-2026-004-session-isolation.md (requirements)
- contracts/serena_agent_stateless_contract.py (ContextVar integration)
- contracts/mcp_session_bridge_contract.py (transport lifecycle)
- contracts/solidlsp_path_resolution_contract.py (LSP workspace_root)

Version: 1.0
Last Updated: 2026-02-06
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


# =============================================================================
# B1 FIX: SESSION CREATION WITHOUT WORKSPACE
# =============================================================================


class SessionCreationContract(ABC):
    """
    Contract for session creation in HTTP transport mode.

    DISCONNECT MATRIX REF: B1 (OVERRIDE)
    - EXPECTED: Each session bound to client's workspace
    - OBSERVED: All sessions bound to Path.cwd() (server's working dir)
    - FIX: Sessions created WITHOUT workspace binding; activate_project binds it

    INVARIANTS:
    - INV-B1-01: on_transport_session_created() MUST NOT use Path.cwd() as default
    - INV-B1-02: Sessions without workspace MUST be valid (workspace_root=None)
    - INV-B1-03: activate_project is the ONLY mechanism to bind workspace to session
    - INV-B1-04: STDIO mode backward compatibility preserved (anonymous sessions with cwd)

    PRECONDITIONS:
    - PRE-B1-01: mcp_session_id is non-empty string
    - PRE-B1-02: workspace_root is None at session creation (HTTP mode)

    POSTCONDITIONS:
    - POST-B1-01: Session registered with workspace_root=None
    - POST-B1-02: Session available via get_session(mcp_session_id)
    - POST-B1-03: get_session().workspace_root is None until activate_project called

    ERRORS:
    - ERRORS-B1-01: ValueError if mcp_session_id is empty (propagated)
    """

    @abstractmethod
    def on_transport_session_created(
        self,
        mcp_session_id: str,
        workspace_root: Optional[Path] = None,
    ) -> None:
        """
        Register MCP transport session WITHOUT workspace binding.

        PRE-B1-01: mcp_session_id is non-empty string
        PRE-B1-02: workspace_root is None (HTTP mode) or absolute Path

        POST-B1-01: Session registered with workspace_root=None if not provided
        POST-B1-02: Path.cwd() MUST NOT be used as fallback
        POST-B1-03: Session available via get_session(mcp_session_id)

        ERRORS-B1-01: ValueError if mcp_session_id is empty
        """
        ...


# =============================================================================
# B2/B4 FIX: SESSION-SCOPED TOOL AVAILABILITY
# =============================================================================


class SessionScopedToolsContract(ABC):
    """
    Contract for session-scoped tool availability.

    DISCONNECT MATRIX REF: B2 (OVERRIDE), B4 (OVERRIDE)
    - EXPECTED: Per-session tool set
    - OBSERVED: Mutates shared self._active_tools on single Agent
    - FIX: Tool availability computed dynamically from session context

    INVARIANTS:
    - INV-B2-01: _active_tools dict MUST NOT be mutated by activate_project
    - INV-B2-02: Tool availability MUST be derived from session's project config
    - INV-B2-03: Concurrent sessions with different projects see correct tool sets
    - INV-B2-04: Tool set computation MUST NOT have side effects on other sessions

    PRECONDITIONS:
    - PRE-B2-01: Session has active project (workspace_root is not None)
    - PRE-B2-02: Project config is loadable from workspace_root

    POSTCONDITIONS:
    - POST-B2-01: Returns tool set appropriate for session's project
    - POST-B2-02: Shared Agent state unchanged after call
    - POST-B2-03: Result is consistent with project config at session's workspace_root
    """

    @abstractmethod
    def get_active_tools_for_session(self) -> dict[type, Any]:
        """
        Compute active tool set for current session.

        PRE-B2-01: Current session has active project
        POST-B2-01: Returns tool dict for session's project
        POST-B2-02: Shared self._active_tools NOT mutated
        INV-B2-03: Concurrent calls with different sessions return different results
        """
        ...


# =============================================================================
# B3 FIX: SESSION-SCOPED PROJECT ACTIVATION
# =============================================================================


class SessionScopedActivationContract(ABC):
    """
    Contract for session-scoped project activation.

    DISCONNECT MATRIX REF: B3 (OVERRIDE)
    - EXPECTED: Rebinds only calling session
    - OBSERVED: Rebinds calling session + mutates shared Agent state
    - FIX: activate_project ONLY modifies session registry + session ContextVar

    INVARIANTS:
    - INV-B3-01: activate_project MUST NOT call _update_active_tools() on shared Agent
    - INV-B3-02: activate_project MUST NOT mutate any shared Agent fields
    - INV-B3-03: Only the calling session's registry entry is modified
    - INV-B3-04: Other sessions' tool availability MUST be unaffected

    PRECONDITIONS:
    - PRE-B3-01: session_id is non-empty string (from ContextVar)
    - PRE-B3-02: workspace_root exists and is absolute path
    - PRE-B3-03: Project loadable from workspace_root

    POSTCONDITIONS:
    - POST-B3-01: SessionRegistry updated for session_id only
    - POST-B3-02: ContextVar set to new SessionContext
    - POST-B3-03: Project loaded and LSP workspace roots added
    - POST-B3-04: No shared Agent state mutated

    ERRORS:
    - ERRORS-B3-01: ProjectNotFoundError if workspace invalid (propagated)
    - ERRORS-B3-02: ValueError if session_id empty (propagated)
    """

    @abstractmethod
    def activate_session_project(
        self,
        session_id: str,
        workspace_root: Path,
        source: str = "explicit",
    ) -> Any:  # Returns Project
        """
        Bind session to workspace without shared state mutation.

        PRE-B3-01: session_id is non-empty string
        PRE-B3-02: workspace_root exists and is absolute path

        POST-B3-01: SessionRegistry.bind_session() called for session_id
        POST-B3-02: set_current_session() called with new SessionContext
        POST-B3-03: Project loaded and returned
        POST-B3-04: self._active_tools NOT mutated
        POST-B3-05: self._project_activation_callback NOT called (or session-scoped)

        ERRORS-B3-01: ProjectNotFoundError if workspace invalid
        """
        ...


# =============================================================================
# GRACEFUL DEGRADATION: NO-PROJECT TOOL CALLS
# =============================================================================


class GracefulDegradationContract(ABC):
    """
    Contract for handling tool calls before activate_project.

    REQ-2026-004 INV-06: PROJECT/LSP tools MUST fail gracefully if no project activated.

    INVARIANTS:
    - INV-GD-01: CONFIG tools (activate_project, get_config) always available
    - INV-GD-02: PROJECT tools fail with clear error when no workspace bound
    - INV-GD-03: LSP tools fail with clear error when no workspace bound
    - INV-GD-04: Error message MUST instruct user to call activate_project

    POSTCONDITIONS:
    - POST-GD-01: CONFIG tools return normally regardless of project state
    - POST-GD-02: PROJECT/LSP tools raise NoProjectActivatedError when workspace is None
    - POST-GD-03: Error message includes session_id for debugging
    """

    @abstractmethod
    def dispatch_tool_with_session_check(
        self,
        session_id: str,
        tool_name: str,
    ) -> bool:
        """
        Check if tool can execute in current session state.

        PRE: session_id is registered
        POST-GD-01: Returns True for CONFIG tools regardless
        POST-GD-02: Returns False for PROJECT/LSP tools when no workspace
        """
        ...


# =============================================================================
# STDIO BACKWARD COMPATIBILITY
# =============================================================================


class STDIOCompatibilityContract(ABC):
    """
    Contract for STDIO mode backward compatibility.

    REQ-2026-004 INV-04: STDIO mode MUST continue to work unchanged.

    INVARIANTS:
    - INV-STDIO-01: STDIO mode creates anonymous session with cwd workspace
    - INV-STDIO-02: Single-session STDIO mode unaffected by isolation changes
    - INV-STDIO-03: _update_active_tools() safe in STDIO (only one session)

    POSTCONDITIONS:
    - POST-STDIO-01: Anonymous session created on first tool call
    - POST-STDIO-02: Tool set matches project at cwd
    """

    @abstractmethod
    def get_or_create_stdio_session(self) -> str:
        """
        Get or create session for STDIO transport mode.

        POST-STDIO-01: Returns valid session_id
        POST-STDIO-02: Session workspace_root = Path.cwd() (correct for STDIO)
        """
        ...


# =============================================================================
# INTEGRATION TEST CONTRACT
# =============================================================================

# These are the scenarios that MUST pass for completion promise:
#
# SCENARIO-1: Two Python sessions activate different projects concurrently
#   - Session A activates serena → get_symbols_overview resolves against /serena
#   - Session B activates OpenMemory → get_symbols_overview resolves against /OpenMemory
#   - Session A's next call STILL resolves against /serena (not OpenMemory)
#
# SCENARIO-2: Session creation before activate_project
#   - New session created → workspace_root is None
#   - get_symbols_overview called → fails with "activate_project first"
#   - activate_project("serena") → succeeds
#   - get_symbols_overview → resolves against /serena
#
# SCENARIO-3: Session tool isolation
#   - Session A activates read-only project → editing tools disabled for A
#   - Session B activates read-write project → editing tools enabled for B
#   - Session A STILL has editing tools disabled (not affected by B's activation)
#
# SCENARIO-4: STDIO backward compatibility
#   - STDIO transport (no HTTP session) → anonymous session with cwd
#   - All tools available as in pre-multi-project behavior
