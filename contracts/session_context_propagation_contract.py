"""
Session Context Propagation Contract - MCP Tool Dispatch Context Restoration

Constitutional Reference: CL12 Design by Contract
Domain: MCP session context propagation to tool execution layer
Version: 1.0

AUTHORITY: This contract is AUTHORITATIVE for session context propagation.
All implementations MUST satisfy these specifications.

PROBLEM STATEMENT (DISCONNECT MATRIX):
==========================================================================
| ID | Behavior                  | EXPECTED                    | OBSERVED                      | DELTA   |
|----|---------------------------|-----------------------------|-------------------------------|---------|
| P1 | ContextVar at tool start  | Restored from MCP session   | Empty (default)               | BUG     |
| P2 | Session lookup in tool    | Returns active session      | Returns None                  | BUG     |
| P3 | get_active_project()      | Returns activated project   | Raises "No active session"    | BUG     |
| P4 | HTTP mode persistence     | Session persists across     | Session lost between calls    | BUG     |
|    |                           | tool calls                  |                               |         |
| P5 | STDIO mode persistence    | Session persists (same      | Session lost (new task)       | BUG     |
|    |                           | async context)              |                               |         |
==========================================================================

ROOT CAUSE:
- MCP tracks sessions at HTTP transport layer via `mcp-session-id` header
- Session state stored in ContextVar (_current_session_id, _current_session)
- ContextVar set during activate_project() in one async context
- Each MCP tool call dispatches in NEW async context (task)
- Nobody restores ContextVar at start of tool dispatch

SOLUTION:
- Store MCP session ID at request entry point (HTTP layer or tool dispatch)
- Before tool execution, restore session context from SessionRegistry
- Use MCPSessionBridge.set_session_context() / reset_session_context()
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable
from contextvars import Token

if TYPE_CHECKING:
    from serena.mcp_session_bridge import MCPSessionBridge


class SessionContextPropagationContract(ABC):
    """
    Contract for propagating MCP session context to tool execution layer.

    The MCP protocol tracks sessions via HTTP headers or transport state.
    When a tool is invoked, the session context must be restored so that:
    1. get_current_session() returns the correct session
    2. get_active_project() returns the project activated in that session
    3. SessionContextContract.INV-5 (touch on tool call) can be satisfied
    """

    @abstractmethod
    def get_mcp_session_id_for_request(self) -> str | None:
        """
        Get the MCP session ID for the current request.

        PRE: Called within MCP request handling context

        POST: Returns MCP session ID if available, None if anonymous/stateless
        POST: For HTTP mode, extracted from mcp-session-id header
        POST: For STDIO mode, may be synthetic (single session per process)

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: No I/O, no logging
        3. Ordering Constraints: May be called at any point during request
        4. Resource Invariants: No handles opened
        5. Exception Safety: Never raises, returns None on failure

        ERRORS: None (returns None on any failure)
        """
        ...

    @abstractmethod
    def restore_session_context_for_tool(
        self,
        mcp_session_id: str,
    ) -> Token | None:
        """
        Restore session context from MCP session ID before tool execution.

        PRE: mcp_session_id is non-empty string
        PRE: Session registered in SessionRegistry (via activate_project)

        POST: If session found: ContextVar set, returns token for reset
        POST: If session not found: ContextVar unchanged, returns None
        POST: After this call, get_current_session() returns the session

        INV (5-Point Checklist):
        1. State Invariance: SessionRegistry unchanged, only ContextVar modified
        2. Side Effect Prohibition: No logging, no I/O (ContextVar is in-memory)
        3. Ordering Constraints: MUST be called BEFORE tool execution
        4. Resource Invariants: Token MUST be used for reset (RAII pattern)
        5. Exception Safety: On any error, ContextVar unchanged, returns None

        ERRORS: None (fails silently, returns None)

        IMPLEMENTATION NOTES:
        - Delegates to MCPSessionBridge.set_session_context()
        - Caller MUST call reset_session_context(token) after tool completes
        - Token captures previous ContextVar state for restoration
        """
        ...

    @abstractmethod
    def reset_session_context_after_tool(
        self,
        token: Token | None,
    ) -> None:
        """
        Reset session context to previous state after tool execution.

        PRE: token from restore_session_context_for_tool(), or None

        POST: If token provided: ContextVar restored to previous state
        POST: If token is None: No-op (nothing to restore)

        INV (5-Point Checklist):
        1. State Invariance: SessionRegistry unchanged, only ContextVar reset
        2. Side Effect Prohibition: No logging, no I/O
        3. Ordering Constraints: MUST be called AFTER tool execution (in finally)
        4. Resource Invariants: Token consumed, no longer valid
        5. Exception Safety: Never raises, safe to call in finally block

        ERRORS: None (never raises)

        IMPLEMENTATION NOTES:
        - Delegates to MCPSessionBridge.reset_session_context()
        - MUST be called in finally block to ensure cleanup
        - Idempotent - safe to call multiple times
        """
        ...

    @abstractmethod
    def wrap_tool_execution(
        self,
        mcp_session_id: str | None,
        tool_func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute tool function with proper session context.

        PRE: tool_func is callable
        PRE: mcp_session_id is non-empty string or None (for anonymous)

        POST: If mcp_session_id provided: session context set during execution
        POST: tool_func called with args/kwargs
        POST: Session context restored after completion (success or failure)

        INV (5-Point Checklist):
        1. State Invariance: Final ContextVar state equals initial state
        2. Side Effect Prohibition: Only side effects from tool_func itself
        3. Ordering Constraints: restore → tool → reset (RAII pattern)
        4. Resource Invariants: Token properly cleaned up
        5. Exception Safety: Reset called in finally, exceptions propagated

        ERRORS:
        - Propagates any exception from tool_func
        - Context always reset regardless of exceptions

        IMPLEMENTATION PATTERN:
        ```python
        def wrap_tool_execution(self, mcp_session_id, tool_func, *args, **kwargs):
            token = None
            try:
                if mcp_session_id:
                    token = self.restore_session_context_for_tool(mcp_session_id)
                return tool_func(*args, **kwargs)
            finally:
                self.reset_session_context_after_tool(token)
        ```
        """
        ...


# =============================================================================
# INTEGRATION POINTS
# =============================================================================

INTEGRATION_POINT_HTTP = """
HTTP Mode Integration:

In StreamableHTTPSessionManager._handle_stateful_request():
1. Extract mcp_session_id from request headers
2. Pass mcp_session_id to tool execution context
3. Tool dispatch wrapper calls restore_session_context_for_tool()

CHALLENGE: The patched MCP code shouldn't have Serena imports.
SOLUTION: Use ContextVar set at HTTP layer, read by tool dispatch.
"""

INTEGRATION_POINT_STDIO = """
STDIO Mode Integration:

In STDIO mode, each message is a separate request in the same process:
1. Single MCP session per process (or synthetic session ID)
2. Session context should persist across tool calls (same async loop)
3. BUT: ContextVar may be lost if using thread pool executor

SOLUTION: Track session at process level for STDIO mode.
"""

INTEGRATION_POINT_TOOL_DISPATCH = """
Tool Dispatch Integration (SerenaMCPFactory.make_mcp_tool):

Current:
```python
def execute_fn(**kwargs) -> str:
    return tool.apply_ex(log_call=True, catch_exceptions=True, **kwargs)
```

Required:
```python
def execute_fn(**kwargs) -> str:
    mcp_session_id = get_mcp_session_id_for_current_request()  # NEW
    return wrap_tool_execution(
        mcp_session_id,
        lambda: tool.apply_ex(log_call=True, catch_exceptions=True, **kwargs)
    )
```

ALTERNATIVE: Use MCP's context_kwarg to inject Context, extract session info.
"""

# =============================================================================
# TEST REQUIREMENTS
# =============================================================================

TEST_CASES = """
Test Case: HTTP Mode Session Persistence
-----------------------------------------
GIVEN: HTTP server with session tracking enabled
AND: Client activates project with session ID "abc123"
AND: ContextVar set during activation

WHEN: Subsequent tool call with same session ID

THEN: get_current_session() returns the same session
AND: get_active_project() returns the activated project
AND: Session touch() is called (INV-5 satisfied)


Test Case: STDIO Mode Session Persistence
------------------------------------------
GIVEN: STDIO transport in same process
AND: Project activated in first tool call

WHEN: Second tool call in same process

THEN: Session context available
AND: Activated project accessible


Test Case: Context Cleanup on Tool Error
-----------------------------------------
GIVEN: Session context restored before tool

WHEN: Tool raises exception

THEN: Session context reset in finally block
AND: ContextVar returned to previous state
AND: Exception propagates to caller
"""
