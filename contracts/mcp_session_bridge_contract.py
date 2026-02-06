"""
Contract: MCP Session Bridge

Defines the behavioral contract for bridging MCP transport sessions to Serena's
session isolation layer. This contract specifies WHAT behavior is required,
not HOW to implement it.

Component: MCPSessionBridge
Purpose: Bridge MCP transport layer session lifecycle to SessionRegistry

DESIGN PATTERN: Lifecycle Bridge
- Transport-to-application session mapping
- Context propagation across async/sync boundaries
- Anonymous session fallback for backward compatibility

REQUIREMENTS SATISFIED:
- REQ-1: Multiple MCP clients connect simultaneously with session isolation
- Backward compatibility: Single-client mode continues to work

INTEGRATION POINTS:
- SessionRegistry: Session storage and lookup
- ContextVar: Async-safe session propagation
- StreamableHTTPSessionManager: Transport session lifecycle

SYNC/ASYNC BOUNDARY:
- Transport lifecycle hooks are called from async context
- Tool execution may be sync (in thread pool)
- ContextVar propagation must use copy_context() for thread safety
"""

from abc import ABC, abstractmethod
from contextvars import ContextVar, Token
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from serena.session_registry import SessionContext


# =============================================================================
# CONSTANTS
# =============================================================================

# Anonymous session prefix
ANONYMOUS_SESSION_PREFIX = "anonymous-"

# Anonymous session TTL in seconds (5 minutes)
ANONYMOUS_SESSION_TTL_SECONDS = 300


# =============================================================================
# EXCEPTIONS (CL12 ERRORS clauses)
# =============================================================================


class SessionNotRegisteredError(Exception):
    """
    Raised when tool dispatch requires a session that is not registered.

    CONTRACT: run_with_session_context ERRORS-2
    INVARIANT: INV-06 (Tool execution MUST fail if session_id not registered)

    This is a fail-fast error - no silent fallback allowed.
    If you see this error, the transport-session bridge callback
    (on_transport_session_created) was not invoked before tool dispatch.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(
            f"Session '{session_id}' not registered in SessionRegistry. "
            f"Tool dispatch requires session to be registered first (INV-06). "
            f"Check that on_transport_session_created callback fired before tool execution."
        )

# Reaper interval in seconds
REAPER_INTERVAL_SECONDS = 60


# =============================================================================
# BEHAVIORAL CONTRACT
# =============================================================================


class MCPSessionBridgeContract(ABC):
    """
    Behavioral contract for MCP session bridging.

    INVARIANTS:
    - INV-1: Every MCP transport session maps to exactly one Serena session
    - INV-2: Session context is accessible in both async and sync execution contexts
    - INV-3: Anonymous sessions are created on-demand when session_id unavailable
    - INV-4: Anonymous sessions have TTL <= ANONYMOUS_SESSION_TTL_SECONDS
    - INV-5: Session cleanup occurs on transport close or TTL expiration
    - INV-6: ContextVar propagation survives thread pool dispatch
    - INV-7: HTTP mode (transport_session_id present) → No auto-registration with
             Path.cwd(); require explicit activate_project call
    - INV-8: STDIO mode (transport_session_id None) → CWD-based initialization
             acceptable since client process CWD matches project workspace

    PRECONDITIONS:
    - PRE-1 (on_transport_created): mcp_session_id is non-empty string
    - PRE-2 (set_session_context): session_id exists in SessionRegistry OR is anonymous
    - PRE-3 (get_current_session_id): May be called from any execution context

    POSTCONDITIONS:
    - POST-1 (on_transport_created): SessionRegistry.bind_session() called
    - POST-2 (on_transport_closed): SessionRegistry.unbind_session() called
    - POST-3 (set_session_context): ContextVar set, token returned for reset
    - POST-4 (get_current_session_id): Returns session_id or None
    - POST-5 (get_or_create_anonymous): Returns valid session_id, never None
    """

    # =========================================================================
    # LIFECYCLE HOOKS
    # =========================================================================

    @abstractmethod
    def on_transport_session_created(
        self,
        mcp_session_id: str,
        workspace_root: Path | None = None,
    ) -> None:
        """
        Called when MCP transport creates a new session.

        PRE: mcp_session_id is non-empty string
        PRE: workspace_root is None (no project yet) or absolute Path

        POST: Session registered in SessionRegistry
        POST: Session available via get_session(mcp_session_id)
        POST-IDEM: If session already registered, returns silently (idempotent)

        INV-IDEM: Method is idempotent - duplicate invocations are no-ops.
                  This handles the POST-4 retroactive registration race condition
                  where set_session_callbacks may be called multiple times.

        BEHAVIOR:
        1. Validate mcp_session_id format
        2. Check if session already exists in SessionRegistry
        3. If exists: Log at DEBUG level, return (no-op)
        4. If not exists: Call SessionRegistry.bind_session(mcp_session_id, workspace_root)
        5. Log session creation for monitoring

        RATIONALE (POST-IDEM):
        Transport layer's POST-4 retroactive registration may invoke this callback
        for sessions that were already registered. Rather than failing with PRE-1
        violation from SessionRegistry, the bridge handles this gracefully.

        CALLED FROM: Async context (StreamableHTTPSessionManager)
        """
        ...

    @abstractmethod
    def on_transport_session_closed(
        self,
        mcp_session_id: str,
    ) -> None:
        """
        Called when MCP transport session closes (graceful or crash).

        PRE: mcp_session_id was previously created via on_transport_session_created

        POST: Session removed from SessionRegistry
        POST: LSP references released via GlobalLanguageServerPool
        POST: get_session(mcp_session_id) returns None

        BEHAVIOR:
        1. Call SessionRegistry.unbind_session(mcp_session_id)
        2. Log session closure for monitoring
        3. Silent no-op if session already closed (idempotent)

        CALLED FROM: Async context (StreamableHTTPSessionManager cleanup)
        """
        ...

    # =========================================================================
    # CONTEXT PROPAGATION
    # =========================================================================

    @abstractmethod
    def set_session_context(
        self,
        session_id: str,
    ) -> Token | None:
        """
        Set session context for current execution context.

        PRE-4: session_id is non-empty string

        POST-6: If session found in registry: ContextVar set, returns Token
        POST-7: If session NOT found in registry: ContextVar unchanged, returns None
        POST-8: NO auto-registration with Path.cwd() per INV-7 (HTTP mode fix)

        ERRORS-1: If session_id is empty → raises ValueError (propagated)

        BEHAVIOR:
        1. Look up session_id in SessionRegistry
        2. If found: Set ContextVar, return Token
        3. If NOT found: Return None (caller must handle - typically means
           activate_project not called yet in HTTP mode)
        4. NEVER auto-register with Path.cwd() - this violates INV-7

        TRANSPORT MODE SEMANTICS (INV-7/INV-8):
        - HTTP mode: Session MUST be explicitly registered via activate_project
        - STDIO mode: N/A (transport_session_id is None, this path not taken)

        USAGE PATTERN (required per contextvar_session_contract.py):
            token = bridge.set_session_context(session_id)
            if token is None:
                # Session not found - prompt user to activate_project
                return error_response("Project not activated")
            try:
                await do_work()
            finally:
                bridge.reset_session_context(token)

        CALLED FROM: Async context (before tool dispatch)
        """
        ...

    @abstractmethod
    def reset_session_context(
        self,
        token: Token,
    ) -> None:
        """
        Reset session context to previous value.

        PRE: token from previous set_session_context() call

        POST: ContextVar restored to previous value

        BEHAVIOR:
        1. Call _current_session_id.reset(token)

        MUST be called in finally block per contextvar_session_contract.py

        CALLED FROM: Async context (after tool dispatch, in finally)
        """
        ...

    @abstractmethod
    def get_current_session_id(self) -> str | None:
        """
        Get current session ID from ContextVar.

        PRE: None (may be called from any context)

        POST: Returns session_id if set, None otherwise

        BEHAVIOR:
        1. Return _current_session_id.get(default=None)

        THREAD SAFETY:
        - Safe to call from sync code running in thread pool
        - ContextVar value inherited if copy_context() used at dispatch

        CALLED FROM: Any context (sync or async)
        """
        ...

    # =========================================================================
    # ANONYMOUS SESSION MANAGEMENT
    # =========================================================================

    @abstractmethod
    def get_or_create_anonymous_session(
        self,
        workspace_root: Path | None = None,
    ) -> str:
        """
        Get or create an anonymous session for backward compatibility.

        PRE: None

        POST: Returns valid session_id (never None)
        POST: Session exists in SessionRegistry
        POST: Session has TTL <= ANONYMOUS_SESSION_TTL_SECONDS

        BEHAVIOR:
        1. Generate UUID v4: f"{ANONYMOUS_SESSION_PREFIX}{uuid4()}"
        2. Call SessionRegistry.bind_session() with workspace_root
        3. Record creation time for TTL tracking
        4. Return session_id

        ANONYMOUS SESSION CONTRACT:
        - Format: "anonymous-{uuid4}"
        - Lifetime: Per bridge instance (not per-request)
        - TTL: ANONYMOUS_SESSION_TTL_SECONDS (300s = 5min)
        - Auto-cleanup: Reaper removes expired sessions

        CALLED FROM: Sync context (tool dispatch fallback)
        """
        ...

    @abstractmethod
    def is_anonymous_session(
        self,
        session_id: str,
    ) -> bool:
        """
        Check if session_id is an anonymous session.

        PRE: session_id is non-empty string

        POST: Returns True if session_id starts with ANONYMOUS_SESSION_PREFIX
        """
        ...

    # =========================================================================
    # THREAD POOL PROPAGATION
    # =========================================================================

    @abstractmethod
    def run_with_session_context(
        self,
        session_id: str,
        func: Callable[[], Any],
    ) -> Any:
        """
        Run a sync function with session context propagated.

        PRE-1: session_id is non-empty string
        PRE-2: func is callable taking no arguments
        PRE-3: session_id MUST be registered in SessionRegistry (INV-06)

        POST-1: func executed with session_id in ContextVar
        POST-2: ContextVar cleaned up after execution (success or failure)
        POST-3: LSP server has properly registered workspace path (INV-07)

        ERRORS-1: ValueError if session_id is empty
        ERRORS-2: SessionNotRegisteredError if session_id not in SessionRegistry
                  (fail fast per INV-06 - no silent fallback)

        BEHAVIOR:
        1. Validate session_id is registered in SessionRegistry
        2. If not registered: raise SessionNotRegisteredError (fail fast)
        3. Set session context via set_session_context()
        4. Execute func with context propagated
        5. Clean up context on exit (success or exception)
        6. Return func result

        THREAD POOL SAFETY:
        This method ensures ContextVar is visible in thread pool workers.
        Python ContextVars are per-execution-context. Thread pools don't
        inherit ContextVar state at call time - they inherit at thread
        creation. This method uses copy_context() to explicitly propagate.

        CALLED FROM: Async context (dispatching sync tool to thread pool)
        """
        ...

    # =========================================================================
    # SESSION REAPER
    # =========================================================================

    @abstractmethod
    def start_reaper(self) -> None:
        """
        Start the anonymous session reaper task.

        PRE: None

        POST: Background task running every REAPER_INTERVAL_SECONDS
        POST: Expired anonymous sessions removed from SessionRegistry

        BEHAVIOR:
        1. Create async task that runs every REAPER_INTERVAL_SECONDS
        2. For each anonymous session, check if TTL exceeded
        3. If expired: call on_transport_session_closed(session_id)
        4. Log reaping activity for monitoring

        CALLED FROM: Async context (server lifespan)
        """
        ...

    @abstractmethod
    def stop_reaper(self) -> None:
        """
        Stop the anonymous session reaper task.

        PRE: Reaper was started via start_reaper()

        POST: Background task cancelled
        POST: No more reaping occurs

        CALLED FROM: Async context (server shutdown)
        """
        ...


# =============================================================================
# ERROR CONTRACTS
# =============================================================================


class SessionContextNotSetError(Exception):
    """
    Raised when session context is required but not set.

    This indicates a programming error - all tool dispatch paths
    should ensure session context is set before tool execution.
    """

    def __init__(self, context: str = ""):
        self.context = context
        super().__init__(
            f"Session context not set{': ' + context if context else ''}. " "Ensure set_session_context() called before tool dispatch."
        )


class AnonymousSessionCreationError(Exception):
    """
    Raised when anonymous session creation fails.

    This is a critical error - backward compatibility requires
    anonymous session fallback to work.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Failed to create anonymous session: {reason}")


# =============================================================================
# MCP ERROR CODE MAPPING
# =============================================================================

MCP_SESSION_BRIDGE_ERROR_CODES = {
    "session_context_not_set": -32005,  # Programming error
    "anonymous_creation_failed": -32006,  # Resource error
}


def bridge_error_to_mcp_error(error: Exception) -> dict:
    """
    Convert bridge errors to MCP error format.

    PRE: error is SessionContextNotSetError or AnonymousSessionCreationError

    POST: Returns dict with 'code', 'message', 'data' keys
    """
    if isinstance(error, SessionContextNotSetError):
        return {
            "code": MCP_SESSION_BRIDGE_ERROR_CODES["session_context_not_set"],
            "message": "Session context not set",
            "data": {"context": error.context},
        }
    elif isinstance(error, AnonymousSessionCreationError):
        return {
            "code": MCP_SESSION_BRIDGE_ERROR_CODES["anonymous_creation_failed"],
            "message": "Failed to create anonymous session",
            "data": {"reason": error.reason},
        }
    else:
        return {
            "code": -32000,
            "message": str(error),
            "data": None,
        }


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================


def verify_session_id_format(session_id: str) -> bool:
    """Verify session_id is non-empty string."""
    return isinstance(session_id, str) and len(session_id) > 0


def verify_anonymous_session_format(session_id: str) -> bool:
    """Verify anonymous session_id format."""
    return session_id.startswith(ANONYMOUS_SESSION_PREFIX)


async def verify_contextvar_thread_propagation(
    bridge: MCPSessionBridgeContract,
    test_session_id: str,
) -> bool:
    """
    Verify ContextVar propagates to thread pool via run_with_session_context.

    This test validates the critical sync/async boundary crossing.
    """
    import asyncio

    result_holder: dict[str, str | None] = {"session_id": None}

    def sync_get_session() -> str | None:
        result_holder["session_id"] = bridge.get_current_session_id()
        return result_holder["session_id"]

    # Run sync function in thread pool with session context
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: bridge.run_with_session_context(test_session_id, sync_get_session))

    return result_holder["session_id"] == test_session_id


# =============================================================================
# CONTRACT TEST ASSERTIONS
# =============================================================================

LIFECYCLE_TEST_CASES = [
    # (action, mcp_session_id, expected_in_registry)
    ("create", "session-123", True),
    ("close", "session-123", False),
    ("close_twice", "session-123", False),  # Idempotent
]

ANONYMOUS_SESSION_TEST_CASES = [
    # (workspace_root, should_succeed)
    (Path("/project-a"), True),
    (None, True),  # No workspace initially
]

CONTEXT_PROPAGATION_TEST_CASES = [
    # (set_session_id, expected_get_result)
    ("session-abc", "session-abc"),
    ("anonymous-uuid", "anonymous-uuid"),
]

THREAD_POOL_TEST_CASES = [
    # (session_id, verify_in_thread_pool)
    ("session-xyz", True),
    ("anonymous-test", True),
]

TTL_REAPER_TEST_CASES = [
    # (session_age_seconds, should_be_reaped)
    (0, False),
    (ANONYMOUS_SESSION_TTL_SECONDS - 1, False),
    (ANONYMOUS_SESSION_TTL_SECONDS + 1, True),
]
