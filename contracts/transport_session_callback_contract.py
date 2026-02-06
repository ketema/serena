"""
Contract: Transport Session Callback Integration

Defines the behavioral contract for callback-based session lifecycle management
between the HTTP transport layer and the SessionRegistry.

Component: StreamableHTTPSessionManager ↔ MCPSessionBridge integration
Purpose: Wire HTTP transport session lifecycle to SessionRegistry via callbacks

REQUIREMENTS SATISFIED:
- REQ-2026-002: Transport-session bridge integration
- INV-7/INV-8: HTTP mode explicit activation, STDIO mode CWD-based

DESIGN PATTERN: Callback Injection
- Transport layer accepts callbacks at construction
- Application layer (mcp.py) provides callbacks that invoke session_bridge methods
- Maintains separation: transport doesn't know about SessionRegistry

INTEGRATION POINTS:
- StreamableHTTPSessionManager: Accepts and invokes callbacks
- MCPSessionBridge: Provides on_transport_session_created/closed methods
- mcp.py: Wires callbacks during server initialization
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional
from pathlib import Path


# =============================================================================
# TYPE ALIASES
# =============================================================================

# Callback type for session creation
# Called when HTTP transport creates a new session
# Parameter: session_id (non-empty string)
SessionCreatedCallback = Callable[[str], None]

# Callback type for session closure
# Called when HTTP transport session closes (graceful or crash)
# Parameter: session_id (non-empty string)
SessionClosedCallback = Callable[[str], None]


# =============================================================================
# BEHAVIORAL CONTRACT
# =============================================================================


class TransportSessionCallbackContract(ABC):
    """
    Behavioral contract for transport-layer session lifecycle callbacks.

    INVARIANTS (from REQ-2026-002):
    - INV-01: Transport MUST call on_session_created before first tool executes
    - INV-02: Transport MUST call on_session_closed when connection terminates
    - INV-03: Transport layer SHALL NOT directly access SessionRegistry
    - INV-04: Transport layer SHALL NOT know about MCPSessionBridge internals
    - INV-05: Session starts with workspace=None; activate_project required to bind

    PRECONDITIONS:
    - PRE-1: Callbacks provided at construction are callable or None
    - PRE-2: session_id passed to callbacks is non-empty string

    POSTCONDITIONS:
    - POST-1: After session creation, on_session_created callback invoked with session_id
    - POST-2: After session closure, on_session_closed callback invoked with session_id
    - POST-3: If callback is None, no invocation occurs (silent no-op)
    - POST-4: Session appears in SessionRegistry after on_session_created (if wired to bridge)
    - POST-5: Session removed from SessionRegistry after on_session_closed (if wired to bridge)

    ERRORS:
    - ERRORS-1: Callback exceptions propagate (not swallowed)
    - ERRORS-2: Invalid session_id (empty string) → undefined behavior (caller responsibility)
    """

    @abstractmethod
    def set_session_callbacks(
        self,
        on_session_created: Optional[SessionCreatedCallback] = None,
        on_session_closed: Optional[SessionClosedCallback] = None,
    ) -> None:
        """
        Set callbacks for session lifecycle events.

        PRE-1: on_session_created is callable or None
        PRE-2: on_session_closed is callable or None

        POST-1: Subsequent session creations invoke on_session_created
        POST-2: Subsequent session closures invoke on_session_closed
        POST-3: Replaces any previously set callbacks
        POST-4: If sessions already exist when on_session_created is set,
                on_session_created is invoked IMMEDIATELY for each existing session
                (retroactive registration to handle race condition where session
                is created before callbacks are wired)

        CALLED FROM: mcp.py server initialization (before first request)

        RACE CONDITION MITIGATION (POST-4):
        Due to architectural timing where HTTP transport creates sessions before
        MCPServer lifespan wires callbacks, sessions may exist when this method
        is called. POST-4 ensures these sessions are not lost.
        """
        ...

    @abstractmethod
    def _invoke_session_created(self, session_id: str) -> None:
        """
        Invoke the on_session_created callback.

        PRE-1: session_id is non-empty string
        PRE-2: Called after session_id is generated but before first tool executes

        POST-1: If callback is set → callback(session_id) invoked
        POST-2: If callback is None → silent no-op
        POST-3: INV-01 satisfied (called before first tool)

        ERRORS-1: Callback exceptions propagate

        CALLED FROM: Transport layer after creating new session
        TIMING: After session_id generated, before task starts
        """
        ...

    @abstractmethod
    def _invoke_session_closed(self, session_id: str) -> None:
        """
        Invoke the on_session_closed callback.

        PRE-1: session_id is non-empty string
        PRE-2: session_id was previously created via this transport

        POST-1: If callback is set → callback(session_id) invoked
        POST-2: If callback is None → silent no-op
        POST-3: INV-02 satisfied (called on termination)

        ERRORS-1: Callback exceptions propagate (but should be logged, not crash server)

        CALLED FROM: Transport layer when session terminates
        TIMING: After connection closes (graceful) or crashes
        """
        ...


# =============================================================================
# WIRING CONTRACT
# =============================================================================


class SessionCallbackWiringContract(ABC):
    """
    Contract for wiring callbacks in mcp.py.

    This contract specifies HOW the application layer wires
    the transport callbacks to the session bridge.

    INVARIANTS:
    - INV-W1: Wiring MUST occur before first HTTP request is processed
    - INV-W2: Callbacks MUST delegate to MCPSessionBridge methods
    - INV-W3: Wiring is idempotent (calling twice has same effect as once)

    PRECONDITIONS:
    - PRE-W1: session_bridge is initialized before wiring
    - PRE-W2: transport_manager is accessible during server setup

    POSTCONDITIONS:
    - POST-W1: After wiring, transport session creation → bridge.on_transport_session_created
    - POST-W2: After wiring, transport session closure → bridge.on_transport_session_closed
    """

    @abstractmethod
    def wire_session_callbacks(self) -> None:
        """
        Wire transport callbacks to session bridge.

        PRE-W1: self.get_session_bridge() returns initialized bridge
        PRE-W2: Transport manager is accessible

        POST-W1: Transport session_created → bridge.on_transport_session_created(session_id, workspace_root=None)
        POST-W2: Transport session_closed → bridge.on_transport_session_closed(session_id)

        IMPLEMENTATION PATTERN:
            bridge = self.get_session_bridge()
            transport_manager.set_session_callbacks(
                on_session_created=lambda sid: bridge.on_transport_session_created(sid, workspace_root=None),
                on_session_closed=lambda sid: bridge.on_transport_session_closed(sid),
            )

        CALLED FROM: server_lifespan (before first request)
        """
        ...


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================


def verify_callback_invocation_order(
    events: list[tuple[str, str]],
) -> bool:
    """
    Verify callbacks are invoked in correct order.

    PRE: events is list of (event_type, session_id) tuples
         event_type is "created" or "closed"

    POST: Returns True iff:
          - Every "closed" event has a preceding "created" event with same session_id
          - No "created" event for same session_id after "closed"
    """
    active_sessions: set[str] = set()

    for event_type, session_id in events:
        if event_type == "created":
            if session_id in active_sessions:
                return False  # Duplicate creation
            active_sessions.add(session_id)
        elif event_type == "closed":
            if session_id not in active_sessions:
                return False  # Closed without creation
            active_sessions.remove(session_id)

    return True


# =============================================================================
# CONTRACT TEST CASES
# =============================================================================

CALLBACK_INVOCATION_TEST_CASES = [
    # (session_id, callback_set, expected_invoked)
    ("session-123", True, True),
    ("session-456", False, False),  # No callback set
    ("", True, False),  # Empty session_id (undefined, but should not crash)
]

RETROACTIVE_REGISTRATION_TEST_CASES = [
    # (existing_sessions_before_wiring, expected_callback_invocations)
    # POST-4: Existing sessions get retroactive callback invocation
    ([], []),  # No existing sessions → no retroactive calls
    (["s1"], ["s1"]),  # One existing session → one retroactive call
    (["s1", "s2", "s3"], ["s1", "s2", "s3"]),  # Multiple → all called
]

WIRING_TEST_CASES = [
    # (bridge_initialized, expected_wiring_success)
    (True, True),
    (False, False),  # Bridge not ready
]

LIFECYCLE_ORDER_TEST_CASES = [
    # (events, expected_valid)
    ([("created", "s1"), ("closed", "s1")], True),
    ([("closed", "s1")], False),  # Closed without created
    ([("created", "s1"), ("created", "s1")], False),  # Duplicate creation
    ([("created", "s1"), ("created", "s2"), ("closed", "s1"), ("closed", "s2")], True),
]
