"""
Contract: SessionAwareToolDispatch

Defines the behavioral contract for session-aware tool call routing.
Integrates PathValidation, SessionRegistry, and GlobalLanguageServerPool
to ensure session isolation during tool execution.

Component: SessionAwareToolDispatch
Purpose: Route tool calls through session context with path validation

REQUIREMENTS SATISFIED:
- REQ-1: Multiple MCP clients connect simultaneously with session isolation
- REQ-3: Session A cannot access files in Session B's workspace

DESIGN DECISIONS:
- CON-1: LSPs don't know sessions - Serena handles isolation
- DD-3: Lock hierarchy (session_lock -> pool_lock)

SYNC INTERFACE:
- All methods are synchronous (no async/await)
- Tool execution is synchronous
- PathValidation is synchronous
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer
    from solidlsp.ls_config import Language


# =============================================================================
# TOOL CATEGORIES
# =============================================================================

class ToolCategory:
    """Tool categories for dispatch routing."""

    CONFIG = "config"  # Always available: activate_project, get_config
    PROJECT = "project"  # Require active project: memory, file tools
    LSP = "lsp"  # Require active project + LSP: symbol tools


# =============================================================================
# BEHAVIORAL CONTRACTS
# =============================================================================

class SessionAwareToolDispatchContract(ABC):
    """
    Behavioral contract for session-aware tool dispatch.

    INVARIANTS:
    - INV-1: Every tool call has associated session_id
    - INV-2: LSP tools MUST pass PathValidation before execution
    - INV-3: Session context resolved before tool execution
    - INV-4: Lock hierarchy respected (session_lock -> pool_lock)

    PRECONDITIONS:
    - PRE-1 (dispatch): session_id is valid (exists in SessionRegistry)
    - PRE-2 (dispatch): tool_name is registered tool
    - PRE-3 (dispatch_lsp): session has active project with LSP support

    POSTCONDITIONS:
    - POST-1 (dispatch): Tool executed in session context
    - POST-2 (dispatch_lsp): Path validated before LSP call
    - POST-3 (dispatch_lsp): LSP timeout touched after successful call
    """

    @abstractmethod
    def get_session_context(
        self,
        session_id: str,
    ) -> "SessionContext":
        """
        Get the session context for a session ID.

        PRE: session_id is non-empty string

        POST: Returns SessionContext if session exists
        POST: Raises SessionNotFoundError if session not in registry

        Thread-safety: Acquires session_lock (read).
        """
        ...

    @abstractmethod
    def dispatch_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Dispatch a tool call in session context.

        PRE: session_id exists in SessionRegistry
        PRE: tool_name is registered tool

        POST: Tool executed with session-scoped state
        POST: Returns tool result

        BEHAVIOR:
        1. Resolve session context
        2. Determine tool category (CONFIG, PROJECT, LSP)
        3. Validate preconditions for category
        4. Execute tool in session context
        5. Return result

        ERROR CONDITIONS:
        - SessionNotFoundError: session_id not in registry
        - NoProjectActivatedError: PROJECT/LSP tool without active project
        - ToolNotFoundError: tool_name not registered
        """
        ...

    @abstractmethod
    def dispatch_lsp_tool(
        self,
        session_id: str,
        tool_name: str,
        relative_path: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Dispatch an LSP tool call with path validation.

        PRE: session_id exists and has active project
        PRE: tool_name is LSP tool (find_symbol, get_symbols_overview, etc.)
        PRE: relative_path is path relative to project root

        POST: Path validated against session workspace
        POST: LSP acquired from pool
        POST: Tool executed via LSP
        POST: LSP timeout touched
        POST: Returns tool result

        BEHAVIOR:
        1. Resolve session context
        2. Get session workspace_root
        3. Resolve full path: workspace_root / relative_path
        4. PathValidation.validate_path(full_path, workspace_root)
           - Raises PathBoundaryError if validation fails
        5. Determine language from file extension
        6. GlobalLanguageServerPool.acquire(language, workspace_root, session_id)
        7. Ensure LSP is functional (_ensure_functional_ls pattern)
        8. Execute LSP request
        9. LSPTimeoutManager.touch(language)
        10. Return result

        ERROR CONDITIONS:
        - SessionNotFoundError: session_id not in registry
        - NoProjectActivatedError: no active project for session
        - PathBoundaryError: path outside session workspace
        - LSPNotAvailableError: LSP could not be acquired
        """
        ...

    @abstractmethod
    def validate_path_for_session(
        self,
        session_id: str,
        path: str | Path,
    ) -> Path:
        """
        Validate and resolve a path for a session.

        PRE: session_id exists in SessionRegistry
        PRE: path is relative or absolute path string

        POST: Returns resolved absolute Path
        POST: Path is within session's workspace_root
        POST: Raises PathBoundaryError if outside workspace

        BEHAVIOR:
        1. Get session's workspace_root
        2. If path is relative: resolve against workspace_root
        3. Canonicalize path (resolve symlinks)
        4. Validate path is under workspace_root
        5. Return canonical absolute path

        Uses existing PathValidation.validate_path() implementation.
        """
        ...

    @abstractmethod
    def get_lsp_for_session(
        self,
        session_id: str,
        relative_path: str,
    ) -> "SolidLanguageServer":
        """
        Get appropriate LSP for a session and file path.

        PRE: session_id exists and has active project
        PRE: relative_path is valid file path

        POST: Returns LSP that can serve the file
        POST: LSP acquired via GlobalLanguageServerPool
        POST: Session reference recorded in pool

        BEHAVIOR:
        1. Resolve session context and workspace_root
        2. Validate path
        3. Determine language from extension
        4. Pool.acquire(language, workspace_root, session_id)
        5. Return LSP (ensured functional)
        """
        ...


# =============================================================================
# SESSION CONTEXT CONTRACT
# =============================================================================

class SessionContextContract(ABC):
    """
    Contract for session context data.

    Represents the state associated with an MCP session.
    """

    @property
    @abstractmethod
    def session_id(self) -> str:
        """Unique session identifier."""
        ...

    @property
    @abstractmethod
    def workspace_root(self) -> Path | None:
        """Session's workspace root (None if no project activated)."""
        ...

    @property
    @abstractmethod
    def project_name(self) -> str | None:
        """Active project name (None if no project activated)."""
        ...

    @property
    @abstractmethod
    def acquired_languages(self) -> set["Language"]:
        """Languages for which this session has acquired LSPs."""
        ...

    @abstractmethod
    def has_active_project(self) -> bool:
        """Whether session has an active project."""
        ...


# =============================================================================
# ERROR CONTRACTS
# =============================================================================

class SessionNotFoundError(Exception):
    """Raised when session_id not found in registry."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class NoProjectActivatedError(Exception):
    """Raised when tool requires active project but none activated."""

    def __init__(self, session_id: str, tool_name: str):
        self.session_id = session_id
        self.tool_name = tool_name
        super().__init__(
            f"No project activated for session {session_id}. "
            f"Tool '{tool_name}' requires an active project. "
            "Call activate_project first."
        )


class LSPNotAvailableError(Exception):
    """Raised when LSP cannot be acquired for session."""

    def __init__(
        self,
        session_id: str,
        language: "Language",
        reason: str,
    ):
        self.session_id = session_id
        self.language = language
        self.reason = reason
        super().__init__(
            f"LSP not available for session {session_id}, "
            f"language {language}: {reason}"
        )


# =============================================================================
# MCP ERROR CODE MAPPINGS
# =============================================================================

MCP_ERROR_CODES = {
    "invalid_params": -32602,  # Standard JSON-RPC
    "session_not_found": -32001,  # Custom
    "no_project": -32002,  # Custom
    "lsp_unavailable": -32003,  # Custom
    "path_boundary": -32004,  # Custom
}


def session_error_to_mcp_error(error: Exception) -> dict:
    """
    Convert session-related exceptions to MCP error format.

    PRE: error is one of the defined session error types

    POST: Returns dict with 'code', 'message', 'data' keys
    """
    if isinstance(error, SessionNotFoundError):
        return {
            "code": MCP_ERROR_CODES["session_not_found"],
            "message": "Session expired or not found",
            "data": {
                "session_id": error.session_id,
                "suggestion": "Re-initialize connection",
            },
        }
    elif isinstance(error, NoProjectActivatedError):
        return {
            "code": MCP_ERROR_CODES["no_project"],
            "message": "No project activated for this session",
            "data": {
                "tool": error.tool_name,
                "suggestion": "Call activate_project first",
            },
        }
    elif isinstance(error, LSPNotAvailableError):
        return {
            "code": MCP_ERROR_CODES["lsp_unavailable"],
            "message": "LSP cannot serve requested path",
            "data": {
                "language": str(error.language),
                "reason": error.reason,
            },
        }
    else:
        # PathBoundaryError handled separately (exists in path_validation)
        return {
            "code": MCP_ERROR_CODES["invalid_params"],
            "message": str(error),
            "data": None,
        }


# =============================================================================
# TOOL DISPATCH FLOW
# =============================================================================

"""
TOOL DISPATCH FLOW (for reference):

1. MCP Server receives tools/call request
2. Extract session_id from request context (transport-specific)
3. Call dispatch_tool(session_id, tool_name, arguments)

For LSP tools (find_symbol, get_symbols_overview, etc.):

4. dispatch_lsp_tool(session_id, tool_name, relative_path, arguments)
5. Validate path against session workspace (PathValidation)
6. Acquire LSP from GlobalLanguageServerPool
7. Execute LSP request
8. Touch LSPTimeoutManager
9. Return result

For non-LSP tools (read_memory, search_for_pattern, etc.):

4. Validate tool preconditions (active project if needed)
5. Execute tool with session context
6. Return result
"""


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================

def verify_tool_category(tool_name: str) -> str:
    """Verify tool categorization."""
    config_tools = {"activate_project", "get_current_config", "switch_modes"}
    lsp_tools = {
        "find_symbol",
        "get_symbols_overview",
        "find_referencing_symbols",
        "replace_symbol_body",
        "insert_after_symbol",
        "insert_before_symbol",
        "rename_symbol",
    }

    if tool_name in config_tools:
        return ToolCategory.CONFIG
    elif tool_name in lsp_tools:
        return ToolCategory.LSP
    else:
        return ToolCategory.PROJECT


# =============================================================================
# CONTRACT TEST ASSERTIONS
# =============================================================================

TOOL_CATEGORY_TEST_CASES = [
    # (tool_name, expected_category)
    ("activate_project", ToolCategory.CONFIG),
    ("get_current_config", ToolCategory.CONFIG),
    ("find_symbol", ToolCategory.LSP),
    ("get_symbols_overview", ToolCategory.LSP),
    ("read_memory", ToolCategory.PROJECT),
    ("search_for_pattern", ToolCategory.PROJECT),
]

PATH_VALIDATION_TEST_CASES = [
    # (workspace_root, relative_path, should_pass)
    (Path("/project-a"), "src/main.rs", True),
    (Path("/project-a"), "../project-b/src/main.rs", False),
    (Path("/project-a"), "../../etc/passwd", False),
]

DISPATCH_FLOW_TEST_CASES = [
    # (has_session, has_project, tool_category, expected_error)
    (False, False, ToolCategory.CONFIG, "SessionNotFoundError"),
    (True, False, ToolCategory.CONFIG, None),  # CONFIG tools always work
    (True, False, ToolCategory.PROJECT, "NoProjectActivatedError"),
    (True, False, ToolCategory.LSP, "NoProjectActivatedError"),
    (True, True, ToolCategory.LSP, None),
]
