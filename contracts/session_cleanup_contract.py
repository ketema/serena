"""
Session Cleanup Contract - Session Lifecycle Management

Constitutional Reference: CL12 Design by Contract
Domain: Session cleanup, expiration, and resource release
Version: 1.0

AUTHORITY: This contract is AUTHORITATIVE for session cleanup behavior.
"""

from abc import ABC, abstractmethod


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
    4. Log session cleanup for monitoring (LOG-2) - DECLARED SIDE EFFECT

    INVARIANTS:
    - INV-1: Cleanup is idempotent (calling twice has no additional effect)
    - INV-2: Cleanup does NOT affect other sessions (session isolation)
    - INV-3: LSP cleanup happens BEFORE registry removal (correct order)

    DECLARED SIDE EFFECTS (Strict Constructionism):
    - SIDE-1: Logging at INFO level for successful cleanup (monitoring)
    - SIDE-2: Logging at WARNING level for partial failures (diagnostics)
    - SIDE-3: LSP didChangeWorkspaceFolders notifications (required by LSP protocol)
    """

    @abstractmethod
    def cleanup_session(self, session_id: str) -> None:
        """
        Clean up a session and all its resources.

        PRE: session_id is valid string (may or may not exist in registry)

        POST: Session removed from SessionRegistry
        POST: All LSP references released via GlobalLanguageServerPool
        POST: For multi-root LSPs, workspace folders removed via didChangeWorkspaceFolders
        POST: get_session(session_id) returns None
        POST: Cleanup logged at INFO level (SIDE-1)

        INV (5-Point Checklist):
        1. State Invariance: Other sessions unaffected (INV-2), registry consistent
        2. Side Effect Prohibition: EXCEPTION - logging IS permitted (SIDE-1, SIDE-2),
           LSP notifications ARE permitted (SIDE-3); no other side effects
        3. Ordering Constraints: LSP cleanup BEFORE registry removal (INV-3),
           thread-safe (holds registry lock), idempotent (INV-1)
        4. Resource Invariants: All LSP handles released, no dangling references,
           registry entry fully removed
        5. Exception Safety: Partial failures logged at WARNING (SIDE-2) but do not
           propagate; if LSP cleanup fails, registry removal still attempted;
           implementation MUST use try/finally

        ERRORS:
        - Does NOT raise for non-existent session_id (idempotent)
        - Does NOT propagate LSP cleanup failures (logged at WARNING only)
        - Does NOT propagate registry failures (logged at WARNING only)
        """
        ...

    @abstractmethod
    def reap_expired_sessions(self) -> list[str]:
        """
        Find and clean up all expired sessions.

        PRE: none (always safe to call, typically called by background reaper)

        POST: All sessions where is_expired() == True are cleaned up
        POST: Returns list of successfully reaped session_ids
        POST: Each cleanup logged at INFO level (SIDE-1)

        INV (5-Point Checklist):
        1. State Invariance: Non-expired sessions unaffected, registry consistent
        2. Side Effect Prohibition: EXCEPTION - logging IS permitted (SIDE-1, SIDE-2),
           LSP notifications ARE permitted (SIDE-3); no other side effects
        3. Ordering Constraints: Thread-safe (holds registry lock during iteration),
           cleanup order does not affect correctness
        4. Resource Invariants: All LSP handles for expired sessions released,
           no dangling references after completion
        5. Exception Safety: Best-effort - individual session failures logged at WARNING
           (SIDE-2) but do not block others; returns partial list on failures

        ERRORS:
        - Does NOT raise - failures logged at WARNING, cleanup continues
        - Returns partial list if some cleanups fail
        - Implementation SHOULD delegate to cleanup_session() for each
        """
        ...

    @abstractmethod
    def shutdown_all_sessions(self) -> None:
        """
        Clean up all sessions (server shutdown).

        PRE: none (always safe to call, typically called during graceful shutdown)

        POST: All sessions cleaned up (best-effort)
        POST: SessionRegistry is empty after completion
        POST: All LSP references released (best-effort)
        POST: Each cleanup logged at INFO level (SIDE-1)

        INV (5-Point Checklist):
        1. State Invariance: Registry empty after completion (no partial state)
        2. Side Effect Prohibition: EXCEPTION - logging IS permitted (SIDE-1, SIDE-2),
           LSP notifications ARE permitted (SIDE-3); no other side effects
        3. Ordering Constraints: Called only during graceful shutdown,
           cleanup order does not affect correctness, idempotent (safe to call multiple times)
        4. Resource Invariants: ALL LSP handles released, ALL registry entries removed,
           no dangling references after completion
        5. Exception Safety: Best-effort - individual failures logged at WARNING (SIDE-2),
           shutdown continues; callers MUST check logs for partial failure diagnostics

        ERRORS:
        - Does NOT raise - failures logged at WARNING, shutdown continues
        - Individual session cleanup failures do not block other cleanups
        - Implementation SHOULD delegate to cleanup_session() for each
        - Callers MUST NOT assume all cleanups succeeded (check logs)
        """
        ...
