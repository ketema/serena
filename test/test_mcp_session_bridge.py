"""
Adversarial TDD Tests: MCPSessionBridge Contract

CONTRACT: contracts/mcp_session_bridge_contract.py
WRITER: test-writer (BLIND to implementation)
CONSTRAINTS:
  - All methods are synchronous except start_reaper/stop_reaper (async)
  - Tests use exact values (no ranges)
  - Error messages follow 5-point standard
  - Verify measurable effects (not just mock.called)

REQUIREMENTS COVERAGE:
  - REQ-1: on_transport_session_created() registers session
  - REQ-2: on_transport_session_closed() removes session (idempotent)
  - REQ-3: set_session_context()/reset_session_context() manage ContextVar
  - REQ-4: get_current_session_id() returns session_id or None
  - REQ-5: get_or_create_anonymous_session() creates anonymous-{uuid4}
  - REQ-6: is_anonymous_session() detects anonymous prefix
  - REQ-7: run_with_session_context() propagates to thread pool
  - REQ-8: start_reaper()/stop_reaper() manage TTL cleanup

INVARIANTS:
  - INV-1: Every MCP transport session maps to exactly one Serena session
  - INV-2: Session context accessible in async and sync contexts
  - INV-3: Anonymous sessions created on-demand
  - INV-4: Anonymous sessions have TTL <= 300 seconds
  - INV-5: Session cleanup on transport close or TTL expiration
  - INV-6: ContextVar propagation survives thread pool dispatch
"""

import asyncio
from contextvars import Token
from pathlib import Path
from unittest.mock import Mock

import pytest

# =============================================================================
# TEST: Lifecycle Hooks (REQ-1, REQ-2)
# =============================================================================


def test_on_transport_session_created_registers_session():
    """
    TEST CASE: on_transport_session_created() calls SessionRegistry.bind_session()

    REQUIREMENT: REQ-1 (session registration)
    INVARIANT: INV-1 (1:1 mapping)

    5-POINT ERROR MESSAGE:
    1. What failed: on_transport_session_created() did not register session
    2. Why: Contract POST-1 violated - SessionRegistry.bind_session() not called
    3. Expected: bind_session("session-123", Path("/workspace")) called exactly once
    4. Actual: bind_session() called {actual_call_count} times
    5. Guidance: After on_transport_session_created(session_id, workspace) completes,
       get_session(session_id) MUST return SessionContext with workspace_root matching
       workspace argument. Session MUST be registered exactly once (duplicate calls violate
       INV-1). Observable: get_session() returns non-None SessionContext object.
    """
    # Setup
    mock_registry = Mock()
    mock_registry.bind_session = Mock()
    bridge = create_bridge_implementation(session_registry=mock_registry)

    mcp_session_id = "session-123"
    workspace_root = Path("/workspace")

    # Execute
    bridge.on_transport_session_created(mcp_session_id, workspace_root)

    # Verify - use assert_called_once_with for exact argument matching
    try:
        mock_registry.bind_session.assert_called_once_with(mcp_session_id, workspace_root)
    except AssertionError as e:
        # Extract actual call details for 5-point error message
        actual_call_count = mock_registry.bind_session.call_count
        actual_calls = mock_registry.bind_session.call_args_list

        pytest.fail(
            f"on_transport_session_created() did not register session correctly\n"
            f"WHY: Contract POST-1 violated - bind_session() not called with exact arguments\n"
            f"EXPECTED: bind_session('session-123', Path('/workspace')) called exactly once\n"
            f"ACTUAL: Called {actual_call_count} times with {actual_calls}\n"
            f"GUIDANCE: After on_transport_session_created(session_id, workspace) completes, "
            f"get_session(session_id) MUST return SessionContext with workspace_root matching "
            f"workspace argument. Session MUST be registered exactly once (duplicate calls violate "
            f"INV-1). Observable: get_session() returns non-None SessionContext object."
        )


def test_on_transport_session_closed_removes_session():
    """
    TEST CASE: on_transport_session_closed() calls SessionRegistry.unbind_session()

    REQUIREMENT: REQ-2 (session removal)
    INVARIANT: INV-5 (cleanup on close)

    5-POINT ERROR MESSAGE:
    1. What failed: on_transport_session_closed() did not remove session
    2. Why: Contract POST-2 violated - SessionRegistry.unbind_session() not called
    3. Expected: unbind_session("session-123") called exactly once
    4. Actual: unbind_session() called {actual_call_count} times
    5. Guidance: After on_transport_session_closed(session_id) completes, get_session(session_id)
       MUST return None (session no longer exists). MUST be idempotent - second call with same
       session_id succeeds silently without error. Observable: get_session() returns None.
    """
    # Setup
    mock_registry = Mock()
    mock_registry.unbind_session = Mock()
    bridge = create_bridge_implementation(session_registry=mock_registry)

    mcp_session_id = "session-123"

    # Execute
    bridge.on_transport_session_closed(mcp_session_id)

    # Verify - use assert_called_once_with for exact argument matching
    try:
        mock_registry.unbind_session.assert_called_once_with(mcp_session_id)
    except AssertionError as e:
        # Extract actual call details for 5-point error message
        actual_call_count = mock_registry.unbind_session.call_count
        actual_calls = mock_registry.unbind_session.call_args_list

        pytest.fail(
            f"on_transport_session_closed() did not remove session correctly\n"
            f"WHY: Contract POST-2 violated - unbind_session() not called with exact arguments\n"
            f"EXPECTED: unbind_session('session-123') called exactly once\n"
            f"ACTUAL: Called {actual_call_count} times with {actual_calls}\n"
            f"GUIDANCE: After on_transport_session_closed(session_id) completes, get_session(session_id) "
            f"MUST return None (session no longer exists). MUST be idempotent - second call with same "
            f"session_id succeeds silently without error. Observable: get_session() returns None."
        )


def test_on_transport_session_closed_idempotent():
    """
    TEST CASE: on_transport_session_closed() is idempotent (silent no-op on double-close)

    REQUIREMENT: REQ-2 (idempotent removal)
    CONTRACT: Line 130 - "Silent no-op if session already closed"

    5-POINT ERROR MESSAGE:
    1. What failed: on_transport_session_closed() raised error on double-close
    2. Why: Contract behavior violated - MUST be idempotent
    3. Expected: No exception, silent no-op on second call
    4. Actual: {exception_type}: {exception_message}
    5. Guidance: Second call to on_transport_session_closed() with same session_id MUST
       succeed without exception. State after first call: get_session() returns None.
       State after second call: still None (no change). Observable: No exception raised.
    """
    # Setup
    mock_registry = Mock()
    mock_registry.unbind_session = Mock()
    bridge = create_bridge_implementation(session_registry=mock_registry)

    mcp_session_id = "session-123"

    # Execute - first close
    bridge.on_transport_session_closed(mcp_session_id)

    # Execute - second close (should be no-op)
    try:
        bridge.on_transport_session_closed(mcp_session_id)
    except Exception as e:
        pytest.fail(
            f"on_transport_session_closed() raised error on double-close\n"
            f"WHY: Contract behavior violated - MUST be idempotent\n"
            f"EXPECTED: No exception, silent no-op on second call\n"
            f"ACTUAL: {type(e).__name__}: {e}\n"
            f"GUIDANCE: Implementation MUST NOT raise exception if session already closed. "
            f"Check session existence before cleanup. If not found, return silently. "
            f"Observable effect: Second call succeeds without error, no state change."
        )


# =============================================================================
# TEST: Context Propagation (REQ-3, REQ-4)
# =============================================================================


def test_set_session_context_returns_token():
    """
    TEST CASE: set_session_context() returns Token for later reset

    REQUIREMENT: REQ-3 (ContextVar lifecycle)
    CONTRACT: POST-3 - "Returns Token for later reset"

    5-POINT ERROR MESSAGE:
    1. What failed: set_session_context() did not return Token
    2. Why: Contract POST-3 violated - Token required for reset
    3. Expected: Return value is Token instance from ContextVar.set()
    4. Actual: Return value is {actual_type}
    5. Guidance: Return value MUST be Token object that can be passed to reset_session_context().
       Observable: isinstance(return_value, Token) == True. Token enables cleanup pattern:
       token = set_session_context(id); try: work(); finally: reset_session_context(token).
    """
    # Setup
    bridge = create_bridge_implementation()
    session_id = "session-abc"

    # Execute
    token = bridge.set_session_context(session_id)

    # Verify
    if not isinstance(token, Token):
        pytest.fail(
            f"set_session_context() did not return Token\n"
            f"WHY: Contract POST-3 violated - Token required for reset\n"
            f"EXPECTED: Return value is Token instance from ContextVar.set()\n"
            f"ACTUAL: Return value is {type(token).__name__}\n"
            f"GUIDANCE: Implementation MUST return Token from ContextVar.set() call. "
            f"This Token is used by reset_session_context() to restore previous value. "
            f"Observable effect: isinstance(token, Token) == True."
        )


def test_get_current_session_id_returns_set_value():
    """
    TEST CASE: get_current_session_id() returns value set by set_session_context()

    REQUIREMENT: REQ-4 (get current session)
    CONTRACT: POST-4 - "Returns session_id or None"
    INVARIANT: INV-2 (context accessible in async/sync)

    5-POINT ERROR MESSAGE:
    1. What failed: get_current_session_id() did not return set session_id
    2. Why: Contract POST-4 violated - ContextVar not propagated
    3. Expected: get_current_session_id() == "session-abc" after set_session_context("session-abc")
    4. Actual: get_current_session_id() == {actual_value}
    5. Guidance: After set_session_context("session-abc"), get_current_session_id() MUST
       return exactly "session-abc" within same execution context. No transformation, truncation,
       or encoding. Observable: get_current_session_id() == "session-abc" (exact string match).
    """
    # Setup
    bridge = create_bridge_implementation()
    session_id = "session-abc"

    # Execute
    token = bridge.set_session_context(session_id)
    actual_value = bridge.get_current_session_id()

    # Verify
    if actual_value != session_id:
        pytest.fail(
            f"get_current_session_id() did not return set session_id\n"
            f"WHY: Contract POST-4 violated - ContextVar not propagated\n"
            f"EXPECTED: get_current_session_id() == 'session-abc' after set_session_context('session-abc')\n"
            f"ACTUAL: get_current_session_id() == {actual_value}\n"
            f"GUIDANCE: Implementation MUST store session_id in ContextVar via set_session_context, "
            f"then retrieve via get_current_session_id. Same execution context required. "
            f"Observable effect: Value set is value retrieved (no transformation)."
        )

    # Cleanup
    bridge.reset_session_context(token)


def test_reset_session_context_clears_value():
    """
    TEST CASE: reset_session_context(token) restores ContextVar to previous value

    REQUIREMENT: REQ-3 (ContextVar lifecycle)
    CONTRACT: POST in reset_session_context - "ContextVar restored to previous value"

    5-POINT ERROR MESSAGE:
    1. What failed: reset_session_context() did not restore previous value
    2. Why: Contract POST violated - ContextVar cleanup incomplete
    3. Expected: get_current_session_id() == None after reset_session_context(token)
    4. Actual: get_current_session_id() == {actual_value}
    5. Guidance: After reset_session_context(token), get_current_session_id() MUST return
       None (assuming no previous set_session_context). If nested contexts, returns previous
       session_id. Observable: get_current_session_id() == None after reset (non-nested case).
    """
    # Setup
    bridge = create_bridge_implementation()
    session_id = "session-abc"

    # Execute
    token = bridge.set_session_context(session_id)
    bridge.reset_session_context(token)
    actual_value = bridge.get_current_session_id()

    # Verify
    if actual_value is not None:
        pytest.fail(
            f"reset_session_context() did not restore previous value\n"
            f"WHY: Contract POST violated - ContextVar cleanup incomplete\n"
            f"EXPECTED: get_current_session_id() == None after reset_session_context(token)\n"
            f"ACTUAL: get_current_session_id() == {actual_value}\n"
            f"GUIDANCE: Implementation MUST call _current_session_id.reset(token) to restore "
            f"previous ContextVar state. Observable effect: After reset, get_current_session_id() "
            f"returns None (or previous value if nested set/reset)."
        )


# =============================================================================
# TEST: Anonymous Session Management (REQ-5, REQ-6)
# =============================================================================


def test_get_or_create_anonymous_session_returns_valid_session_id():
    """
    TEST CASE: get_or_create_anonymous_session() returns non-None session_id

    REQUIREMENT: REQ-5 (anonymous session creation)
    CONTRACT: POST-5 - "Returns valid session_id (never None)"

    5-POINT ERROR MESSAGE:
    1. What failed: get_or_create_anonymous_session() returned None
    2. Why: Contract POST-5 violated - MUST return valid session_id
    3. Expected: Return value is non-None string starting with "anonymous-"
    4. Actual: Return value is None
    5. Guidance: Return value MUST be non-None string with format "anonymous-{uuid}".
       Observable: result != None, isinstance(result, str) == True, len(result) > len("anonymous-").
       Session immediately usable - get_session(result) returns SessionContext.
    """
    # Setup
    mock_registry = Mock()
    mock_registry.bind_session = Mock()
    bridge = create_bridge_implementation(session_registry=mock_registry)

    # Execute
    session_id = bridge.get_or_create_anonymous_session()

    # Verify
    if session_id is None:
        pytest.fail(
            "get_or_create_anonymous_session() returned None\n"
            "WHY: Contract POST-5 violated - MUST return valid session_id\n"
            "EXPECTED: Return value is non-None string starting with 'anonymous-'\n"
            "ACTUAL: Return value is None\n"
            "GUIDANCE: Implementation MUST generate UUID v4 and return "
            "f'{ANONYMOUS_SESSION_PREFIX}{uuid4()}' format. Cannot return None, empty string, "
            "or invalid format. Observable effect: Result is non-None string, can be used "
            "as session_id immediately."
        )


def test_get_or_create_anonymous_session_has_anonymous_prefix():
    """
    TEST CASE: get_or_create_anonymous_session() returns session_id with "anonymous-" prefix

    REQUIREMENT: REQ-5 (anonymous session format)
    CONTRACT: BEHAVIOR line 229 - "Generate UUID v4: f'{ANONYMOUS_SESSION_PREFIX}{uuid4()}'"

    5-POINT ERROR MESSAGE:
    1. What failed: Anonymous session_id missing "anonymous-" prefix
    2. Why: Contract BEHAVIOR violated - format must be "anonymous-{uuid4}"
    3. Expected: session_id.startswith("anonymous-") == True
    4. Actual: session_id = "{actual_session_id}", startswith check = False
    5. Guidance: Session ID MUST start with "anonymous-" prefix. Observable:
       result.startswith("anonymous-") == True, is_anonymous_session(result) == True.
       Format enables detection of anonymous vs regular sessions.
    """
    # Setup
    mock_registry = Mock()
    mock_registry.bind_session = Mock()
    bridge = create_bridge_implementation(session_registry=mock_registry)

    # Execute
    session_id = bridge.get_or_create_anonymous_session()

    # Verify
    if not session_id.startswith("anonymous-"):
        pytest.fail(
            f"Anonymous session_id missing 'anonymous-' prefix\n"
            f"WHY: Contract BEHAVIOR violated - format must be 'anonymous-{{uuid4}}'\n"
            f"EXPECTED: session_id.startswith('anonymous-') == True\n"
            f"ACTUAL: session_id = '{session_id}', startswith check = False\n"
            f"GUIDANCE: Implementation MUST use ANONYMOUS_SESSION_PREFIX constant ('anonymous-') "
            f"as prefix. Format MUST be exactly f'{{ANONYMOUS_SESSION_PREFIX}}{{uuid4()}}'. "
            f"Observable effect: is_anonymous_session(result) returns True."
        )


def test_get_or_create_anonymous_session_calls_bind_session():
    """
    TEST CASE: get_or_create_anonymous_session() registers session in SessionRegistry

    REQUIREMENT: REQ-5 (session registration)
    CONTRACT: POST-2 - "Session exists in SessionRegistry"

    5-POINT ERROR MESSAGE:
    1. What failed: get_or_create_anonymous_session() did not register session
    2. Why: Contract POST-2 violated - SessionRegistry.bind_session() not called
    3. Expected: bind_session(session_id, workspace_root) called exactly once
    4. Actual: bind_session() called {actual_call_count} times
    5. Guidance: After get_or_create_anonymous_session(workspace) completes, get_session(session_id)
       MUST return SessionContext with workspace_root == workspace. Observable: Session registered
       and retrievable, workspace_root property matches input.
    """
    # Setup
    mock_registry = Mock()
    mock_registry.bind_session = Mock()
    bridge = create_bridge_implementation(session_registry=mock_registry)
    workspace_root = Path("/workspace")

    # Execute
    session_id = bridge.get_or_create_anonymous_session(workspace_root)

    # Verify - session_id is dynamic (UUID), so check call_count and workspace_root only
    actual_call_count = mock_registry.bind_session.call_count
    if actual_call_count != 1:
        pytest.fail(
            f"get_or_create_anonymous_session() did not register session\n"
            f"WHY: Contract POST-2 violated - SessionRegistry.bind_session() not called\n"
            f"EXPECTED: bind_session(session_id, workspace_root) called exactly once\n"
            f"ACTUAL: bind_session() called {actual_call_count} times\n"
            f"GUIDANCE: After get_or_create_anonymous_session(workspace) completes, get_session(session_id) "
            f"MUST return SessionContext with workspace_root == workspace. Observable: Session registered "
            f"and retrievable, workspace_root property matches input."
        )

    # Verify workspace_root propagated (session_id is UUID, can't predict exact value)
    call_args = mock_registry.bind_session.call_args
    actual_workspace = call_args[0][1] if call_args and len(call_args[0]) > 1 else None
    if actual_workspace != workspace_root:
        pytest.fail(
            f"get_or_create_anonymous_session() passed wrong workspace_root\n"
            f"WHY: Contract POST-2 violated - workspace_root not propagated\n"
            f"EXPECTED: bind_session(..., Path('/workspace'))\n"
            f"ACTUAL: bind_session(..., {actual_workspace})\n"
            f"GUIDANCE: Workspace propagation MUST be exact. Observable: get_session(session_id) "
            f"returns SessionContext with workspace_root == Path('/workspace')."
        )


def test_is_anonymous_session_detects_anonymous_prefix():
    """
    TEST CASE: is_anonymous_session() returns True for "anonymous-" prefix

    REQUIREMENT: REQ-6 (anonymous detection)
    CONTRACT: POST - "Returns True if session_id starts with ANONYMOUS_SESSION_PREFIX"

    5-POINT ERROR MESSAGE:
    1. What failed: is_anonymous_session("anonymous-123") returned False
    2. Why: Contract POST violated - prefix detection logic incorrect
    3. Expected: is_anonymous_session("anonymous-123") == True
    4. Actual: is_anonymous_session("anonymous-123") == {actual_result}
    5. Guidance: is_anonymous_session("anonymous-{anything}") MUST return True.
       Prefix check: exact match on "anonymous-" at start of string.
       Observable: All anonymous sessions (created by get_or_create_anonymous) return True.
    """
    # Setup
    bridge = create_bridge_implementation()

    # Execute
    actual_result = bridge.is_anonymous_session("anonymous-123")

    # Verify
    if actual_result is not True:
        pytest.fail(
            f"is_anonymous_session('anonymous-123') returned False\n"
            f"WHY: Contract POST violated - prefix detection logic incorrect\n"
            f"EXPECTED: is_anonymous_session('anonymous-123') == True\n"
            f"ACTUAL: is_anonymous_session('anonymous-123') == {actual_result}\n"
            f"GUIDANCE: Implementation MUST check session_id.startswith(ANONYMOUS_SESSION_PREFIX). "
            f"ANONYMOUS_SESSION_PREFIX == 'anonymous-' (contract line 46). "
            f"Observable effect: Any session_id starting with 'anonymous-' returns True."
        )


def test_is_anonymous_session_rejects_non_anonymous():
    """
    TEST CASE: is_anonymous_session() returns False for non-anonymous session_id

    REQUIREMENT: REQ-6 (anonymous detection)
    CONTRACT: POST - "Returns True if session_id starts with ANONYMOUS_SESSION_PREFIX"

    5-POINT ERROR MESSAGE:
    1. What failed: is_anonymous_session("session-123") returned True
    2. Why: Contract POST violated - false positive on regular session
    3. Expected: is_anonymous_session("session-123") == False
    4. Actual: is_anonymous_session("session-123") == {actual_result}
    5. Guidance: is_anonymous_session("session-123") MUST return False. Only "anonymous-"
       prefix returns True. Exact prefix match at string start, not substring anywhere.
       Observable: Regular sessions (any format except "anonymous-*") return False.
    """
    # Setup
    bridge = create_bridge_implementation()

    # Execute
    actual_result = bridge.is_anonymous_session("session-123")

    # Verify
    if actual_result is not False:
        pytest.fail(
            f"is_anonymous_session('session-123') returned True\n"
            f"WHY: Contract POST violated - false positive on regular session\n"
            f"EXPECTED: is_anonymous_session('session-123') == False\n"
            f"ACTUAL: is_anonymous_session('session-123') == {actual_result}\n"
            f"GUIDANCE: Implementation MUST return False for any session_id NOT starting with "
            f"'anonymous-' prefix. Check must be exact prefix match, not substring search. "
            f"Observable effect: Regular sessions (not starting with 'anonymous-') return False."
        )


# =============================================================================
# TEST: Thread Pool Propagation (REQ-7)
# =============================================================================


def test_run_with_session_context_propagates_to_sync_function():
    """
    TEST CASE: run_with_session_context() makes session_id available in sync function

    REQUIREMENT: REQ-7 (thread pool propagation)
    CONTRACT: POST - "func executed with session_id in ContextVar"
    INVARIANT: INV-6 (ContextVar propagation survives thread pool dispatch)

    5-POINT ERROR MESSAGE:
    1. What failed: Sync function could not retrieve session_id via get_current_session_id()
    2. Why: Contract POST violated - ContextVar not propagated to sync execution context
    3. Expected: get_current_session_id() returns "session-xyz" inside sync function
    4. Actual: get_current_session_id() returned {actual_value}
    5. Guidance: run_with_session_context("session-xyz", func) MUST make "session-xyz"
       available inside func via get_current_session_id(). Works across async/sync boundary.
       Observable: Inside sync function, get_current_session_id() == "session-xyz".
    """
    # Setup
    bridge = create_bridge_implementation()
    session_id = "session-xyz"
    result_holder = {"retrieved_session_id": None}

    def sync_get_session():
        result_holder["retrieved_session_id"] = bridge.get_current_session_id()

    # Execute
    bridge.run_with_session_context(session_id, sync_get_session)

    # Verify
    actual_value = result_holder["retrieved_session_id"]
    if actual_value != session_id:
        pytest.fail(
            f"Sync function could not retrieve session_id via get_current_session_id()\n"
            f"WHY: Contract POST violated - ContextVar not propagated to sync execution context\n"
            f"EXPECTED: get_current_session_id() returns 'session-xyz' inside sync function\n"
            f"ACTUAL: get_current_session_id() returned {actual_value}\n"
            f"GUIDANCE: Implementation MUST use copy_context() to capture current ContextVar state, "
            f"then use context.run(func) to execute sync function with copied context. "
            f"Observable effect: Sync function sees same session_id as async caller. "
            f"Thread pool workers don't inherit ContextVar by default - explicit copy required."
        )


def test_run_with_session_context_returns_function_result():
    """
    TEST CASE: run_with_session_context() returns sync function's return value

    REQUIREMENT: REQ-7 (thread pool propagation)
    CONTRACT: POST - "Return func result"

    5-POINT ERROR MESSAGE:
    1. What failed: run_with_session_context() did not return sync function result
    2. Why: Contract POST violated - return value not propagated
    3. Expected: run_with_session_context() returns 42 (sync function result)
    4. Actual: run_with_session_context() returned {actual_result}
    5. Guidance: Return value from sync function MUST propagate unchanged.
       Observable: run_with_session_context(..., func) returns same value func returns.
    """
    # Setup
    bridge = create_bridge_implementation()
    session_id = "session-xyz"

    def sync_return_value():
        return 42

    # Execute
    actual_result = bridge.run_with_session_context(session_id, sync_return_value)

    # Verify
    if actual_result != 42:
        pytest.fail(
            f"run_with_session_context() did not return sync function result\n"
            f"WHY: Contract POST violated - return value not propagated\n"
            f"EXPECTED: run_with_session_context() returns 42 (sync function result)\n"
            f"ACTUAL: run_with_session_context() returned {actual_result}\n"
            f"GUIDANCE: Implementation MUST return result from context.run(func). "
            f"Observable effect: Return value from sync function propagates to caller."
        )


# =============================================================================
# TEST: Session Reaper (REQ-8)
# =============================================================================


@pytest.mark.anyio
async def test_start_reaper_creates_background_task():
    """
    TEST CASE: start_reaper() creates async task that runs periodically

    REQUIREMENT: REQ-8 (reaper lifecycle)
    CONTRACT: POST - "Background task running every REAPER_INTERVAL_SECONDS"

    5-POINT ERROR MESSAGE:
    1. What failed: start_reaper() did not create background task
    2. Why: Contract POST violated - no periodic cleanup task running
    3. Expected: asyncio.Task created and tracked in bridge._reaper_task attribute
    4. Actual: bridge._reaper_task is {actual_task_state}
    5. Guidance: After start_reaper(), background task MUST be running. Observable:
       bridge has task reference (non-None), task periodically checks anonymous session TTL.
       Expired sessions (age > 300s) get removed automatically.
    """
    # Setup
    bridge = create_bridge_implementation()

    # Execute
    bridge.start_reaper()

    # Verify
    actual_task_state = getattr(bridge, "_reaper_task", None)
    if actual_task_state is None:
        pytest.fail(
            "start_reaper() did not create background task\n"
            "WHY: Contract POST violated - no periodic cleanup task running\n"
            "EXPECTED: asyncio.Task created and tracked in bridge._reaper_task attribute\n"
            "ACTUAL: bridge._reaper_task is None\n"
            "GUIDANCE: Implementation MUST create asyncio.Task via asyncio.create_task() and "
            "store reference in instance variable. Task must run periodic loop checking TTL. "
            "Observable effect: bridge._reaper_task is not None after start_reaper() call."
        )

    # Cleanup
    bridge.stop_reaper()


@pytest.mark.anyio
async def test_stop_reaper_cancels_background_task():
    """
    TEST CASE: stop_reaper() cancels async task created by start_reaper()

    REQUIREMENT: REQ-8 (reaper lifecycle)
    CONTRACT: POST - "Background task cancelled"

    5-POINT ERROR MESSAGE:
    1. What failed: stop_reaper() did not cancel background task
    2. Why: Contract POST violated - task still running after stop_reaper()
    3. Expected: bridge._reaper_task.cancelled() == True after stop_reaper()
    4. Actual: bridge._reaper_task.cancelled() == {actual_cancelled_state}
    5. Guidance: After stop_reaper(), background task MUST be cancelled. Observable:
       Task state is cancelled (task.cancelled() == True) or done (task.done() == True).
       No more TTL checks occur after stop_reaper() completes.
    """
    # Setup
    bridge = create_bridge_implementation()
    bridge.start_reaper()

    # Execute
    bridge.stop_reaper()

    # Give task time to process cancellation
    await asyncio.sleep(0.1)

    # Verify
    reaper_task = getattr(bridge, "_reaper_task", None)
    actual_cancelled_state = reaper_task.cancelled() if reaper_task else None
    if actual_cancelled_state is not True:
        pytest.fail(
            f"stop_reaper() did not cancel background task\n"
            f"WHY: Contract POST violated - task still running after stop_reaper()\n"
            f"EXPECTED: bridge._reaper_task.cancelled() == True after stop_reaper()\n"
            f"ACTUAL: bridge._reaper_task.cancelled() == {actual_cancelled_state}\n"
            f"GUIDANCE: Implementation MUST call _reaper_task.cancel() and optionally await "
            f"cancellation. Observable effect: Task is cancelled, no more reaping occurs. "
            f"Check task state via task.cancelled() or task.done()."
        )


# =============================================================================
# MOCK IMPLEMENTATION FACTORY
# =============================================================================


def create_bridge_implementation(session_registry=None):
    """
    Factory to create MCPSessionBridge implementation for testing.

    This is a PLACEHOLDER for the actual implementation.
    The test-writer is BLIND to implementation details.

    Tests will initially FAIL with ImportError until coder implements.
    """
    # Import will fail until implementation exists - this is expected in RED phase
    from serena.mcp_session_bridge import MCPSessionBridge

    if session_registry:
        return MCPSessionBridge(session_registry=session_registry)
    else:
        # Use mock registry for tests that don't care about registry details
        mock_registry = Mock()
        mock_registry.bind_session = Mock()
        mock_registry.unbind_session = Mock()
        return MCPSessionBridge(session_registry=mock_registry)
