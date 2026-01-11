"""
Contract: ContextVar Session Propagation

Defines the behavioral contract for async-safe session context propagation.
Critical for multi-session isolation in async MCP handlers.
Mocks for tests MUST derive from this contract (CL10).

Component: ContextVar Session Management
Purpose: Async-safe session context propagation across await boundaries
"""

from contextvars import ContextVar, Token
from typing import Any, TypeVar, Generic

T = TypeVar("T")


# =============================================================================
# BEHAVIORAL CONTRACTS
# =============================================================================

class ContextVarSessionContract(Generic[T]):
    """
    Behavioral contract for async-safe session context.

    INVARIANTS:
    - INV-1: ContextVar value persists across await boundaries within same task
    - INV-2: ContextVar value is isolated between concurrent tasks
    - INV-3: Token-based reset ensures proper cleanup in all code paths

    PRECONDITIONS:
    - PRE-1 (set): value is not None (use explicit None type if needed)
    - PRE-2 (reset): token was obtained from previous set() call
    - PRE-3 (get): none (may return default)

    POSTCONDITIONS:
    - POST-1 (set): returns Token for later reset
    - POST-2 (set): get() returns the set value until reset
    - POST-3 (reset): get() returns previous value or default
    - POST-4 (get): returns current value or default if not set
    """

    def set(self, value: T) -> Token:
        """
        Set the context variable value.

        MUST be paired with reset() in try/finally block.

        Example:
            token = ctx.set(session)
            try:
                await do_work()
            finally:
                ctx.reset(token)
        """
        ...

    def reset(self, token: Token) -> None:
        """
        Reset the context variable to previous value.

        PRE: token from previous set() call on this ContextVar
        POST: value restored to what it was before corresponding set()
        """
        ...

    def get(self, default: T | None = None) -> T | None:
        """
        Get current value or default.

        POST: returns current value if set, otherwise default
        """
        ...


# =============================================================================
# ENTRY POINT PATTERN CONTRACT
# =============================================================================

async def mcp_request_handler_pattern(
    session_context: Any,
    handler_fn: Any,
    context_var: ContextVar
) -> Any:
    """
    Canonical pattern for MCP request handling with ContextVar.

    This pattern MUST be used at the entry point of all MCP requests.
    It ensures:
    1. Session context is set before any handler code runs
    2. Context is available across all await boundaries in handler
    3. Context is always cleaned up, even on exceptions
    4. Error logging has correct session context

    Pattern:
        async def handle_mcp_request(request):
            session = registry.get_session(request.session_id)
            if session is None:
                raise NoActiveSessionError()

            token = _current_session.set(session)
            try:
                return await dispatch_tool(request)
            except Exception as e:
                # Error path ALSO has correct session context
                logger.error(f"Session {session.session_id}: {e}")
                raise
            finally:
                _current_session.reset(token)  # ALWAYS reset

    CRITICAL: The finally block MUST execute reset() even on:
    - Normal completion
    - Exception raised
    - Cancellation (asyncio.CancelledError)
    """
    token = context_var.set(session_context)
    try:
        return await handler_fn()
    except Exception:
        # Error path still has correct context
        raise
    finally:
        context_var.reset(token)


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================

async def verify_contextvar_survives_await(
    context_var: ContextVar,
    test_value: Any
) -> bool:
    """
    Verify ContextVar value persists across await boundaries.

    Sets value, awaits a coroutine, verifies value still accessible.
    """
    import asyncio

    token = context_var.set(test_value)
    try:
        # Simulate async work
        await asyncio.sleep(0.01)

        # Value should still be accessible
        retrieved = context_var.get()
        return retrieved == test_value
    finally:
        context_var.reset(token)


async def verify_contextvar_isolation(
    context_var: ContextVar,
    value_a: Any,
    value_b: Any
) -> bool:
    """
    Verify ContextVar values are isolated between concurrent tasks.

    Two concurrent tasks set different values, each should see own value.
    """
    import asyncio

    results = {"task_a": None, "task_b": None}

    async def task_a():
        token = context_var.set(value_a)
        try:
            await asyncio.sleep(0.02)  # Longer delay
            results["task_a"] = context_var.get()
        finally:
            context_var.reset(token)

    async def task_b():
        token = context_var.set(value_b)
        try:
            await asyncio.sleep(0.01)  # Shorter delay
            results["task_b"] = context_var.get()
        finally:
            context_var.reset(token)

    await asyncio.gather(task_a(), task_b())

    # Each task should see its own value, not the other's
    return results["task_a"] == value_a and results["task_b"] == value_b


async def verify_error_path_has_context(
    context_var: ContextVar,
    test_value: Any
) -> bool:
    """
    Verify ContextVar is accessible in error handling path.
    """
    token = context_var.set(test_value)
    try:
        # Simulate error
        raise ValueError("Test error")
    except ValueError:
        # Error handling should have access to context
        retrieved = context_var.get()
        return retrieved == test_value
    finally:
        context_var.reset(token)


# =============================================================================
# CONTRACT TEST ASSERTIONS
# =============================================================================

CONTEXTVAR_TEST_CASES = [
    ("survives_single_await", "Value persists after one await"),
    ("survives_multiple_awaits", "Value persists after multiple awaits"),
    ("isolated_between_tasks", "Concurrent tasks have isolated values"),
    ("cleanup_on_exception", "Reset called even when exception raised"),
    ("cleanup_on_cancellation", "Reset called even when task cancelled"),
    ("nested_set_reset", "Nested set/reset works correctly"),
]

ANTI_PATTERNS = [
    "Using threading.local instead of ContextVar",
    "Forgetting to reset in finally block",
    "Setting context after first await in handler",
    "Not checking for None before using context",
]
