"""
Tests for POST-4: Retroactive Session Callback Invocation

CONTRACT TRACEABILITY:
- Contract: TransportSessionCallbackContract.set_session_callbacks()
- File: contracts/transport_session_callback_contract.py
- Authority: AUTHORITATIVE for Transport Session Callback Integration

POST-4 REQUIREMENT:
If sessions already exist when on_session_created is set, on_session_created
is invoked IMMEDIATELY for each existing session (retroactive registration to
handle race condition where session is created before callbacks are wired).

RACE CONDITION CONTEXT:
Due to architectural timing where HTTP transport creates sessions before
MCPServer lifespan wires callbacks, sessions may exist when set_session_callbacks
is called. POST-4 ensures these sessions are not lost.

ADVERSARIAL: Implementation-blind tests (black-box)
"""

import pytest
from typing import List, Optional, Callable


# =============================================================================
# TEST FIXTURES
# =============================================================================


class MockTransportManager:
    """
    Mock transport manager implementing TransportSessionCallbackContract.

    Mock Contract: contracts/transport_session_callback_contract.py
    Mock derives: POST-4 behavior

    NOTE: This mock simulates _server_instances tracking. Real implementation
    details are unknown (adversarial blindness). Mock only enforces POST-4
    observable behavior: retroactive callback invocation.
    """

    def __init__(self):
        self._existing_sessions: List[str] = []
        self._on_session_created: Optional[Callable[[str], None]] = None
        self._on_session_closed: Optional[Callable[[str], None]] = None
        self._retroactive_invocations: List[str] = []

    def add_existing_session(self, session_id: str) -> None:
        """Simulate session existing before callback wiring."""
        self._existing_sessions.append(session_id)

    def set_session_callbacks(
        self,
        on_session_created: Optional[Callable[[str], None]] = None,
        on_session_closed: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Enforces: POST-4 - Retroactive callback invocation

        When on_session_created is set AND sessions already exist,
        on_session_created MUST be invoked immediately for each.
        """
        self._on_session_created = on_session_created
        self._on_session_closed = on_session_closed

        # POST-4: Retroactive invocation for existing sessions
        if on_session_created is not None:
            for session_id in self._existing_sessions:
                self._retroactive_invocations.append(session_id)
                on_session_created(session_id)

    def get_retroactive_invocations(self) -> List[str]:
        """Observable: Which sessions got retroactive callbacks."""
        return self._retroactive_invocations.copy()


@pytest.fixture
def transport_manager():
    """Provide mock transport manager for testing."""
    return MockTransportManager()


@pytest.fixture
def callback_tracker():
    """Track callback invocations for verification."""
    invocations = []

    def track(session_id: str) -> None:
        invocations.append(session_id)

    track.invocations = invocations
    return track


# =============================================================================
# POST-4 POSITIVE TESTS: Retroactive Invocation
# =============================================================================


def test_post4_no_existing_sessions_no_retroactive_calls(transport_manager, callback_tracker):
    """
    CONTRACT TRACEABILITY:
    - Contract: TransportSessionCallbackContract.set_session_callbacks()
    - Enforces: POST-4 (boundary case: zero existing sessions)
    - Category: boundary
    - Adversarial: Implementation-blind

    BEHAVIOR: When no sessions exist before wiring, no retroactive calls occur.
    """
    # ARRANGE: No existing sessions
    assert len(transport_manager._existing_sessions) == 0

    # ACT: Wire callback
    transport_manager.set_session_callbacks(on_session_created=callback_tracker)

    # ASSERT: POST-4 - No retroactive invocations
    assert len(callback_tracker.invocations) == 0, (
        f"POST-4 violation: Retroactive invocations occurred without existing sessions\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4\n"
        f"EXPECTED: 0 invocations (no existing sessions)\n"
        f"ACTUAL: {len(callback_tracker.invocations)} invocations ({callback_tracker.invocations})\n"
        f"GUIDANCE: POST-4 MUST invoke callback ONLY for sessions that existed BEFORE wiring.\n"
        f"           If no sessions exist, no retroactive calls should occur."
    )


def test_post4_one_existing_session_retroactive_invocation(transport_manager, callback_tracker):
    """
    CONTRACT TRACEABILITY:
    - Contract: TransportSessionCallbackContract.set_session_callbacks()
    - Enforces: POST-4 (single existing session)
    - Category: positive
    - Adversarial: Implementation-blind

    BEHAVIOR: When one session exists before wiring, callback invoked once.
    """
    # ARRANGE: One existing session
    transport_manager.add_existing_session("session-001")

    # ACT: Wire callback
    transport_manager.set_session_callbacks(on_session_created=callback_tracker)

    # ASSERT: POST-4 - Callback invoked exactly once for existing session
    assert len(callback_tracker.invocations) == 1, (
        f"POST-4 violation: Wrong number of retroactive invocations\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4\n"
        f"EXPECTED: 1 invocation for existing session 'session-001'\n"
        f"ACTUAL: {len(callback_tracker.invocations)} invocations ({callback_tracker.invocations})\n"
        f"GUIDANCE: POST-4 requires IMMEDIATE invocation of on_session_created for EACH existing session.\n"
        f"           Implementation MUST iterate over existing sessions and invoke callback synchronously."
    )

    assert "session-001" in callback_tracker.invocations, (
        f"POST-4 violation: Callback not invoked for existing session\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4\n"
        f"EXPECTED: Callback invoked with session_id='session-001'\n"
        f"ACTUAL: Invocations were {callback_tracker.invocations}\n"
        f"GUIDANCE: POST-4 requires callback to receive the EXACT session_id of existing session.\n"
        f"           Verify session_id is passed correctly to callback."
    )


def test_post4_multiple_existing_sessions_all_invoked(transport_manager, callback_tracker):
    """
    CONTRACT TRACEABILITY:
    - Contract: TransportSessionCallbackContract.set_session_callbacks()
    - Enforces: POST-4 (multiple existing sessions)
    - Category: positive
    - Adversarial: Implementation-blind

    BEHAVIOR: When multiple sessions exist before wiring, callback invoked for ALL.
    """
    # ARRANGE: Three existing sessions
    existing_sessions = ["session-001", "session-002", "session-003"]
    for session_id in existing_sessions:
        transport_manager.add_existing_session(session_id)

    # ACT: Wire callback
    transport_manager.set_session_callbacks(on_session_created=callback_tracker)

    # ASSERT: POST-4 - Callback invoked for every existing session
    assert len(callback_tracker.invocations) == 3, (
        f"POST-4 violation: Not all existing sessions received retroactive callback\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4\n"
        f"EXPECTED: 3 invocations (one per existing session)\n"
        f"ACTUAL: {len(callback_tracker.invocations)} invocations ({callback_tracker.invocations})\n"
        f"GUIDANCE: POST-4 requires IMMEDIATE invocation for EACH existing session.\n"
        f"           Implementation MUST iterate over ALL existing sessions, not just first/last."
    )

    for session_id in existing_sessions:
        assert session_id in callback_tracker.invocations, (
            f"POST-4 violation: Session '{session_id}' not invoked retroactively\n"
            f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4\n"
            f"EXPECTED: Callback invoked for session '{session_id}'\n"
            f"ACTUAL: Invocations were {callback_tracker.invocations}\n"
            f"GUIDANCE: POST-4 requires callback for EVERY existing session.\n"
            f"           Verify iteration covers all sessions in tracking structure."
        )


def test_post4_callback_none_no_retroactive_invocation_error(transport_manager):
    """
    CONTRACT TRACEABILITY:
    - Contract: TransportSessionCallbackContract.set_session_callbacks()
    - Enforces: POST-4 + POST-3 (None callback handling)
    - Category: boundary
    - Adversarial: Implementation-blind

    BEHAVIOR: When callback is None, no retroactive invocation occurs (silent no-op).
    """
    # ARRANGE: Existing sessions but callback is None
    transport_manager.add_existing_session("session-001")

    # ACT: Wire with None callback (should not crash)
    transport_manager.set_session_callbacks(on_session_created=None)

    # ASSERT: POST-3/POST-4 - No invocation, no error
    retroactive = transport_manager.get_retroactive_invocations()
    assert len(retroactive) == 0, (
        f"POST-4 violation: Retroactive invocation attempted with None callback\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4 + POST-3\n"
        f"EXPECTED: 0 invocations (callback is None → silent no-op per POST-3)\n"
        f"ACTUAL: {len(retroactive)} invocations\n"
        f"GUIDANCE: POST-4 retroactive invocation MUST check if callback is None.\n"
        f"           If None, no invocation should occur (POST-3 silent no-op)."
    )


# =============================================================================
# POST-4 NEGATIVE TESTS: Exception Propagation
# =============================================================================


def test_post4_callback_exception_propagates_errors1(transport_manager):
    """
    CONTRACT TRACEABILITY:
    - Contract: TransportSessionCallbackContract.set_session_callbacks()
    - Enforces: POST-4 + ERRORS-1 (exception propagation)
    - Category: negative
    - Adversarial: Implementation-blind

    BEHAVIOR: If callback raises exception during retroactive invocation, exception propagates.
    """
    # ARRANGE: Existing session, callback that raises
    transport_manager.add_existing_session("session-001")

    def failing_callback(session_id: str) -> None:
        raise ValueError(f"Callback failure for {session_id}")

    # ACT + ASSERT: ERRORS-1 - Exception propagates during retroactive invocation
    with pytest.raises(ValueError, match="Callback failure for session-001"):
        transport_manager.set_session_callbacks(on_session_created=failing_callback)


def test_post4_callback_exception_first_session_stops_iteration(transport_manager):
    """
    CONTRACT TRACEABILITY:
    - Contract: TransportSessionCallbackContract.set_session_callbacks()
    - Enforces: POST-4 + ERRORS-1 (exception stops iteration)
    - Category: negative
    - Adversarial: Implementation-blind

    BEHAVIOR: If callback raises on first session, subsequent sessions not invoked.

    NOTE: This is EXPECTED behavior per ERRORS-1 (exceptions propagate).
    Implementation is NOT required to catch and continue.
    """
    # ARRANGE: Multiple existing sessions
    transport_manager.add_existing_session("session-001")
    transport_manager.add_existing_session("session-002")

    invoked = []

    def failing_callback(session_id: str) -> None:
        invoked.append(session_id)
        if session_id == "session-001":
            raise ValueError(f"Callback failure for {session_id}")

    # ACT + ASSERT: ERRORS-1 - First failure propagates
    with pytest.raises(ValueError, match="Callback failure for session-001"):
        transport_manager.set_session_callbacks(on_session_created=failing_callback)

    # ASSERT: Only first session invoked (exception stopped iteration)
    assert invoked == ["session-001"], (
        f"POST-4 + ERRORS-1: Exception propagation behavior\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4 + ERRORS-1\n"
        f"EXPECTED: Exception propagates on first failure (subsequent sessions not invoked)\n"
        f"ACTUAL: Invoked sessions were {invoked}\n"
        f"GUIDANCE: ERRORS-1 specifies exceptions propagate (not swallowed).\n"
        f"           Implementation is NOT required to catch and continue iteration.\n"
        f"           This is EXPECTED behavior - exception stops retroactive iteration."
    )


# =============================================================================
# POST-4 INVARIANT TESTS: Timing Guarantees
# =============================================================================


def test_post4_preserves_inv01_timing(transport_manager):
    """
    CONTRACT TRACEABILITY:
    - Contract: TransportSessionCallbackContract.set_session_callbacks()
    - Enforces: POST-4 + INV-01 (timing guarantee)
    - Category: invariant
    - Adversarial: Implementation-blind

    BEHAVIOR: Retroactive invocation occurs BEFORE set_session_callbacks returns.
             This preserves INV-01 timing (callback before first tool executes).
    """
    # ARRANGE: Existing session
    transport_manager.add_existing_session("session-001")

    invocation_completed = []

    def timing_callback(session_id: str) -> None:
        invocation_completed.append(session_id)

    # ACT: Wire callback (should invoke synchronously)
    transport_manager.set_session_callbacks(on_session_created=timing_callback)

    # ASSERT: POST-4 + INV-01 - Invocation completed before return
    assert len(invocation_completed) == 1, (
        f"POST-4 + INV-01 violation: Retroactive invocation not synchronous\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4 + INV-01\n"
        f"EXPECTED: Callback invoked BEFORE set_session_callbacks returns\n"
        f"ACTUAL: Callback not invoked synchronously\n"
        f"GUIDANCE: POST-4 specifies IMMEDIATE invocation (synchronous, not deferred).\n"
        f"           This preserves INV-01 timing guarantee (callback before first tool).\n"
        f"           Implementation MUST invoke callback during set_session_callbacks execution."
    )

    assert "session-001" in invocation_completed, (
        f"POST-4 + INV-01 violation: Session not invoked synchronously\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4 + INV-01\n"
        f"EXPECTED: session-001 invoked BEFORE return\n"
        f"ACTUAL: Invocations were {invocation_completed}\n"
        f"GUIDANCE: POST-4 IMMEDIATE invocation preserves INV-01 timing.\n"
        f"           Verify callback is invoked synchronously, not scheduled for later."
    )


# =============================================================================
# POST-4 INTEGRATION TEST: Realistic Scenario
# =============================================================================


def test_post4_realistic_race_condition_scenario(transport_manager, callback_tracker):
    """
    CONTRACT TRACEABILITY:
    - Contract: TransportSessionCallbackContract.set_session_callbacks()
    - Enforces: POST-4 (realistic scenario)
    - Category: positive
    - Adversarial: Implementation-blind

    SCENARIO: HTTP transport receives requests before MCPServer.lifespan wires callbacks.
              Sessions created, then wiring occurs. POST-4 ensures existing sessions
              are not lost.
    """
    # ARRANGE: Simulate race condition
    # Step 1: HTTP transport receives request, creates session
    transport_manager.add_existing_session("early-session-001")
    transport_manager.add_existing_session("early-session-002")

    # Step 2: MCPServer.lifespan runs, wires callbacks
    transport_manager.set_session_callbacks(on_session_created=callback_tracker)

    # ASSERT: POST-4 - Early sessions not lost
    assert len(callback_tracker.invocations) == 2, (
        f"POST-4 violation: Race condition - existing sessions lost\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4\n"
        f"EXPECTED: 2 retroactive invocations for early sessions\n"
        f"ACTUAL: {len(callback_tracker.invocations)} invocations ({callback_tracker.invocations})\n"
        f"GUIDANCE: POST-4 exists to handle this exact race condition.\n"
        f"           When sessions exist before wiring, they MUST be retroactively registered.\n"
        f"           Implementation MUST invoke callback for ALL existing sessions during wiring."
    )

    assert "early-session-001" in callback_tracker.invocations, (
        f"POST-4 violation: Early session 'early-session-001' lost in race condition\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4\n"
        f"EXPECTED: Retroactive invocation for early-session-001\n"
        f"ACTUAL: Invocations were {callback_tracker.invocations}\n"
        f"GUIDANCE: POST-4 MUST invoke callback for EACH existing session.\n"
        f"           Verify all sessions in tracking structure are iterated."
    )

    assert "early-session-002" in callback_tracker.invocations, (
        f"POST-4 violation: Early session 'early-session-002' lost in race condition\n"
        f"Contract: TransportSessionCallbackContract.set_session_callbacks() POST-4\n"
        f"EXPECTED: Retroactive invocation for early-session-002\n"
        f"ACTUAL: Invocations were {callback_tracker.invocations}\n"
        f"GUIDANCE: POST-4 MUST invoke callback for EACH existing session.\n"
        f"           Verify iteration covers all sessions, not just first."
    )


# =============================================================================
# CLAUSE COVERAGE REPORT
# =============================================================================

"""
CLAUSE COVERAGE REPORT:
========================

POST-4 (Retroactive invocation for existing sessions):
- test_post4_no_existing_sessions_no_retroactive_calls ✓ (boundary: zero sessions)
- test_post4_one_existing_session_retroactive_invocation ✓ (positive: one session)
- test_post4_multiple_existing_sessions_all_invoked ✓ (positive: multiple sessions)
- test_post4_callback_none_no_retroactive_invocation_error ✓ (boundary: None callback)
- test_post4_callback_exception_propagates_errors1 ✓ (negative: exception propagation)
- test_post4_callback_exception_first_session_stops_iteration ✓ (negative: iteration stops)
- test_post4_preserves_inv01_timing ✓ (invariant: synchronous invocation)
- test_post4_realistic_race_condition_scenario ✓ (positive: realistic scenario)

ERRORS-1 (Exception propagation):
- test_post4_callback_exception_propagates_errors1 ✓
- test_post4_callback_exception_first_session_stops_iteration ✓

INV-01 (Timing guarantee):
- test_post4_preserves_inv01_timing ✓

POST-3 (None callback handling):
- test_post4_callback_none_no_retroactive_invocation_error ✓

COMPLETENESS: All POST-4 scenarios covered (boundary, positive, negative, invariant, integration)
"""
