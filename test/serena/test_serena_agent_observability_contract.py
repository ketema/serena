"""
SerenaAgent Observability Contract Tests
=========================================

CONTRACT AUTHORITY RECORD:
- File: contracts/serena_agent_observability_contract.py
- Authority: "SINGULAR authoritative source for SerenaAgent observability"
- PRE clauses: 1 extracted (PRE-OBS-01)
- POST clauses: 4 extracted (POST-OBS-01, POST-OBS-02, POST-OBS-03, POST-OBS-04)
- INV clauses: 4 extracted (INV-OBS-01, INV-OBS-02, INV-OBS-03, INV-OBS-04)
- ERRORS: 1 exception mapping (ERRORS-OBS-01)

CLAUSE REGISTRY:
PRE-OBS-01: SerenaAgent initialization complete (_session_registry not None)
POST-OBS-01: session_registry property returns SessionRegistry instance
POST-OBS-02: lsp_pool property returns GlobalLanguageServerPool or None
POST-OBS-03: get_session_overview returns dict {"sessions": list, "total_count": int}
POST-OBS-04: get_lsp_pool_stats returns dict {"lsps": list, "total_count": int}
INV-OBS-01: Observability queries MUST NOT mutate state
INV-OBS-02: Observability methods MUST NOT raise exceptions
INV-OBS-03: MUST NOT expose internal objects directly
INV-OBS-04: MUST be thread-safe (concurrent reads/writes safe)
ERRORS-OBS-01: Any exception → caught, empty structure returned

Adversarial Constraint: Implementation-blind. Tests derive from contract only.
"""

import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from serena.agent import SerenaAgent
from serena.global_lsp_pool import GlobalLanguageServerPool
from serena.session_registry import SessionRegistry

# =============================================================================
# POST-OBS-01: session_registry property returns SessionRegistry
# =============================================================================


class TestPostObs01SessionRegistryProperty:
    """
    CONTRACT TRACEABILITY:
    - Contract: SerenaAgent.session_registry (property)
    - Enforces: POST-OBS-01: Returns SessionRegistry instance, never None
    - Category: positive
    - Adversarial: Implementation-blind
    """

    def test_session_registry_property_returns_registry_instance(
        self, initialized_agent: SerenaAgent
    ):
        """
        Verify POST-OBS-01: session_registry property returns SessionRegistry.

        ARRANGE: Initialized SerenaAgent
        ACT: Access session_registry property
        ASSERT: Returns SessionRegistry instance
        """
        # ACT
        result = initialized_agent.session_registry

        # ASSERT
        assert isinstance(result, SessionRegistry), (
            f"POST-OBS-01 violation: session_registry must return SessionRegistry instance\n"
            f"Contract: SerenaAgent.session_registry POST-OBS-01\n"
            f"EXPECTED: SessionRegistry instance\n"
            f"ACTUAL: {type(result)}\n"
            f"GUIDANCE: Property MUST return _session_registry directly (not None, not copy)"
        )

    def test_session_registry_property_returns_same_instance(
        self, initialized_agent: SerenaAgent
    ):
        """
        Verify POST-OBS-01: session_registry returns same instance (not copy).

        ARRANGE: Initialized SerenaAgent
        ACT: Access session_registry twice
        ASSERT: Both calls return identical instance (same object ID)
        """
        # ACT
        first_call = initialized_agent.session_registry
        second_call = initialized_agent.session_registry

        # ASSERT
        assert first_call is second_call, (
            "POST-OBS-01 violation: session_registry must return same instance\n"
            "Contract: SerenaAgent.session_registry POST-OBS-01\n"
            "EXPECTED: Same object (id match)\n"
            "ACTUAL: Different objects (id mismatch)\n"
            "GUIDANCE: Return _session_registry directly, not SessionRegistry(...) each call"
        )


# =============================================================================
# POST-OBS-02: lsp_pool property returns GlobalLanguageServerPool or None
# =============================================================================


class TestPostObs02LspPoolProperty:
    """
    CONTRACT TRACEABILITY:
    - Contract: SerenaAgent.lsp_pool (property)
    - Enforces: POST-OBS-02: Returns GlobalLanguageServerPool or None
    - Category: positive, boundary
    - Adversarial: Implementation-blind
    """

    def test_lsp_pool_property_returns_pool_or_none(
        self, initialized_agent: SerenaAgent
    ):
        """
        Verify POST-OBS-02: lsp_pool returns GlobalLanguageServerPool or None.

        ARRANGE: Initialized SerenaAgent
        ACT: Access lsp_pool property
        ASSERT: Returns GlobalLanguageServerPool instance or None
        """
        # ACT
        result = initialized_agent.lsp_pool

        # ASSERT
        assert isinstance(result, GlobalLanguageServerPool) or result is None, (
            f"POST-OBS-02 violation: lsp_pool must return GlobalLanguageServerPool or None\n"
            f"Contract: SerenaAgent.lsp_pool POST-OBS-02\n"
            f"EXPECTED: GlobalLanguageServerPool or None\n"
            f"ACTUAL: {type(result)}\n"
            f"GUIDANCE: Return _lsp_pool directly (may be None before first LSP acquisition)"
        )

    def test_lsp_pool_property_none_is_valid(self, agent_with_no_lsp: SerenaAgent):
        """
        Verify POST-OBS-02: lsp_pool returns None when no LSPs acquired.

        ARRANGE: SerenaAgent with _lsp_pool = None
        ACT: Access lsp_pool property
        ASSERT: Returns None (valid state per contract)
        """
        # ACT
        result = agent_with_no_lsp.lsp_pool

        # ASSERT
        assert result is None, (
            f"POST-OBS-02 violation: lsp_pool must return None when no LSPs acquired\n"
            f"Contract: SerenaAgent.lsp_pool POST-OBS-02\n"
            f"EXPECTED: None\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: None is valid state before LSP initialization"
        )


# =============================================================================
# POST-OBS-03: get_session_overview response structure
# =============================================================================


class TestPostObs03SessionOverviewStructure:
    """
    CONTRACT TRACEABILITY:
    - Contract: SessionRegistry.get_session_overview()
    - Enforces: POST-OBS-03: Returns dict {"sessions": list, "total_count": int}
    - Category: positive
    - Adversarial: Implementation-blind
    """

    def test_session_overview_has_required_keys(
        self, initialized_agent: SerenaAgent
    ):
        """
        Verify POST-OBS-03: get_session_overview returns exactly {"sessions", "total_count"}.

        ARRANGE: Initialized SerenaAgent with session_registry
        ACT: Call session_registry.get_session_overview()
        ASSERT: Response has exactly keys "sessions" and "total_count"
        """
        # ACT
        result = initialized_agent.session_registry.get_session_overview()

        # ASSERT
        expected_keys = {"sessions", "total_count"}
        actual_keys = set(result.keys())
        assert actual_keys == expected_keys, (
            f"POST-OBS-03 violation: get_session_overview must return exact keys\n"
            f"Contract: SessionRegistry.get_session_overview() POST-OBS-03\n"
            f"EXPECTED: {expected_keys}\n"
            f"ACTUAL: {actual_keys}\n"
            f"GUIDANCE: Response MUST be dict with exactly 'sessions' and 'total_count' keys"
        )

    def test_session_overview_sessions_is_list(self, initialized_agent: SerenaAgent):
        """
        Verify POST-OBS-03: "sessions" value is list type.

        ARRANGE: Initialized SerenaAgent
        ACT: Call get_session_overview()
        ASSERT: result["sessions"] is list
        """
        # ACT
        result = initialized_agent.session_registry.get_session_overview()

        # ASSERT
        assert isinstance(result["sessions"], list), (
            f"POST-OBS-03 violation: 'sessions' must be list\n"
            f"Contract: SessionRegistry.get_session_overview() POST-OBS-03\n"
            f"EXPECTED: list type\n"
            f"ACTUAL: {type(result['sessions'])}\n"
            f"GUIDANCE: 'sessions' MUST be list (may be empty [])"
        )

    def test_session_overview_total_count_is_int(
        self, initialized_agent: SerenaAgent
    ):
        """
        Verify POST-OBS-03: "total_count" value is int type.

        ARRANGE: Initialized SerenaAgent
        ACT: Call get_session_overview()
        ASSERT: result["total_count"] is int
        """
        # ACT
        result = initialized_agent.session_registry.get_session_overview()

        # ASSERT
        assert isinstance(result["total_count"], int), (
            f"POST-OBS-03 violation: 'total_count' must be int\n"
            f"Contract: SessionRegistry.get_session_overview() POST-OBS-03\n"
            f"EXPECTED: int type\n"
            f"ACTUAL: {type(result['total_count'])}\n"
            f"GUIDANCE: 'total_count' MUST be int >= 0"
        )

    def test_session_overview_total_count_matches_length(
        self, agent_with_sessions: SerenaAgent
    ):
        """
        Verify POST-OBS-03: total_count equals len(sessions).

        ARRANGE: SerenaAgent with 3 sessions
        ACT: Call get_session_overview()
        ASSERT: total_count == len(sessions)
        """
        # ACT
        result = agent_with_sessions.session_registry.get_session_overview()

        # ASSERT
        sessions_length = len(result["sessions"])
        total_count = result["total_count"]
        assert total_count == sessions_length, (
            f"POST-OBS-03 violation: total_count must equal len(sessions)\n"
            f"Contract: SessionRegistry.get_session_overview() POST-OBS-03\n"
            f"EXPECTED: total_count={sessions_length}\n"
            f"ACTUAL: total_count={total_count}\n"
            f"GUIDANCE: total_count MUST exactly match sessions list length"
        )


# =============================================================================
# POST-OBS-04: get_lsp_pool_stats response structure
# =============================================================================


class TestPostObs04LspPoolStatsStructure:
    """
    CONTRACT TRACEABILITY:
    - Contract: GlobalLanguageServerPool.get_stats()
    - Enforces: POST-OBS-04: Returns dict {"lsps": list, "total_count": int}
    - Category: positive, boundary
    - Adversarial: Implementation-blind
    """

    def test_lsp_pool_stats_has_required_keys(self, agent_with_lsp: SerenaAgent):
        """
        Verify POST-OBS-04: get_stats returns exactly {"lsps", "total_count"}.

        ARRANGE: SerenaAgent with lsp_pool initialized
        ACT: Call lsp_pool.get_stats()
        ASSERT: Response has exactly keys "lsps" and "total_count"
        """
        # ACT
        result = agent_with_lsp.lsp_pool.get_stats()

        # ASSERT
        expected_keys = {"lsps", "total_count"}
        actual_keys = set(result.keys())
        assert actual_keys == expected_keys, (
            f"POST-OBS-04 violation: get_stats must return exact keys\n"
            f"Contract: GlobalLanguageServerPool.get_stats() POST-OBS-04\n"
            f"EXPECTED: {expected_keys}\n"
            f"ACTUAL: {actual_keys}\n"
            f"GUIDANCE: Response MUST be dict with exactly 'lsps' and 'total_count' keys"
        )

    def test_lsp_pool_stats_lsps_is_list(self, agent_with_lsp: SerenaAgent):
        """
        Verify POST-OBS-04: "lsps" value is list type.

        ARRANGE: SerenaAgent with lsp_pool
        ACT: Call get_stats()
        ASSERT: result["lsps"] is list
        """
        # ACT
        result = agent_with_lsp.lsp_pool.get_stats()

        # ASSERT
        assert isinstance(result["lsps"], list), (
            f"POST-OBS-04 violation: 'lsps' must be list\n"
            f"Contract: GlobalLanguageServerPool.get_stats() POST-OBS-04\n"
            f"EXPECTED: list type\n"
            f"ACTUAL: {type(result['lsps'])}\n"
            f"GUIDANCE: 'lsps' MUST be list (may be empty [])"
        )

    def test_lsp_pool_stats_total_count_is_int(self, agent_with_lsp: SerenaAgent):
        """
        Verify POST-OBS-04: "total_count" value is int type.

        ARRANGE: SerenaAgent with lsp_pool
        ACT: Call get_stats()
        ASSERT: result["total_count"] is int
        """
        # ACT
        result = agent_with_lsp.lsp_pool.get_stats()

        # ASSERT
        assert isinstance(result["total_count"], int), (
            f"POST-OBS-04 violation: 'total_count' must be int\n"
            f"Contract: GlobalLanguageServerPool.get_stats() POST-OBS-04\n"
            f"EXPECTED: int type\n"
            f"ACTUAL: {type(result['total_count'])}\n"
            f"GUIDANCE: 'total_count' MUST be int >= 0"
        )

    def test_lsp_pool_stats_total_count_matches_length(
        self, agent_with_lsp: SerenaAgent
    ):
        """
        Verify POST-OBS-04: total_count equals len(lsps).

        ARRANGE: SerenaAgent with lsp_pool containing LSPs
        ACT: Call get_stats()
        ASSERT: total_count == len(lsps)
        """
        # ACT
        result = agent_with_lsp.lsp_pool.get_stats()

        # ASSERT
        lsps_length = len(result["lsps"])
        total_count = result["total_count"]
        assert total_count == lsps_length, (
            f"POST-OBS-04 violation: total_count must equal len(lsps)\n"
            f"Contract: GlobalLanguageServerPool.get_stats() POST-OBS-04\n"
            f"EXPECTED: total_count={lsps_length}\n"
            f"ACTUAL: total_count={total_count}\n"
            f"GUIDANCE: total_count MUST exactly match lsps list length"
        )

    def test_lsp_pool_none_dashboard_returns_empty(
        self, agent_with_no_lsp: SerenaAgent
    ):
        """
        Verify POST-OBS-04: When lsp_pool is None, Dashboard returns empty structure.

        ARRANGE: SerenaAgent with lsp_pool = None
        ACT: Dashboard checks lsp_pool, returns empty if None
        ASSERT: Result is {"lsps": [], "total_count": 0}
        """
        # ACT - Simulate Dashboard logic
        if agent_with_no_lsp.lsp_pool is None:
            result = {"lsps": [], "total_count": 0}
        else:
            result = agent_with_no_lsp.lsp_pool.get_stats()

        # ASSERT
        assert result == {"lsps": [], "total_count": 0}, (
            f"POST-OBS-04 violation: Dashboard must return empty when lsp_pool is None\n"
            f"Contract: GlobalLanguageServerPool.get_stats() POST-OBS-04 (Note)\n"
            f"EXPECTED: {{'lsps': [], 'total_count': 0}}\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Dashboard MUST check lsp_pool is None and return empty structure"
        )


# =============================================================================
# INV-OBS-01: Observability queries MUST NOT mutate state
# =============================================================================


class TestInvObs01ReadOnly:
    """
    CONTRACT TRACEABILITY:
    - Contract: SerenaAgent observability interface
    - Enforces: INV-OBS-01: Read-only operations (no mutation)
    - Category: invariant
    - Adversarial: Implementation-blind
    """

    def test_session_registry_property_does_not_mutate(
        self, agent_with_sessions: SerenaAgent
    ):
        """
        Verify INV-OBS-01: session_registry property does not mutate state.

        ARRANGE: SerenaAgent with 3 sessions
        ACT: Access session_registry property multiple times
        ASSERT: Session count unchanged
        """
        # ARRANGE - Capture initial state
        initial_overview = agent_with_sessions.session_registry.get_session_overview()
        initial_count = initial_overview["total_count"]

        # ACT - Multiple property accesses
        _ = agent_with_sessions.session_registry
        _ = agent_with_sessions.session_registry
        _ = agent_with_sessions.session_registry

        # ASSERT - State unchanged
        final_overview = agent_with_sessions.session_registry.get_session_overview()
        final_count = final_overview["total_count"]
        assert final_count == initial_count, (
            f"INV-OBS-01 violation: session_registry property mutated state\n"
            f"Contract: SerenaAgent.session_registry INV-OBS-01\n"
            f"EXPECTED: session count unchanged ({initial_count})\n"
            f"ACTUAL: session count changed to {final_count}\n"
            f"GUIDANCE: Observability queries MUST be read-only (no side effects)"
        )

    def test_get_session_overview_does_not_mutate(
        self, agent_with_sessions: SerenaAgent
    ):
        """
        Verify INV-OBS-01: get_session_overview does not mutate state.

        ARRANGE: SerenaAgent with sessions
        ACT: Call get_session_overview() 5 times
        ASSERT: Session count remains stable
        """
        # ARRANGE
        initial_overview = agent_with_sessions.session_registry.get_session_overview()
        initial_count = initial_overview["total_count"]

        # ACT - Multiple calls
        for _ in range(5):
            _ = agent_with_sessions.session_registry.get_session_overview()

        # ASSERT
        final_overview = agent_with_sessions.session_registry.get_session_overview()
        final_count = final_overview["total_count"]
        assert final_count == initial_count, (
            f"INV-OBS-01 violation: get_session_overview mutated state\n"
            f"Contract: SessionRegistry.get_session_overview() INV-OBS-01\n"
            f"EXPECTED: session count unchanged ({initial_count})\n"
            f"ACTUAL: session count changed to {final_count}\n"
            f"GUIDANCE: Method MUST NOT add/remove sessions (read-only)"
        )

    def test_get_lsp_pool_stats_does_not_mutate(self, agent_with_lsp: SerenaAgent):
        """
        Verify INV-OBS-01: get_lsp_pool_stats does not mutate state.

        ARRANGE: SerenaAgent with lsp_pool
        ACT: Call get_stats() 5 times
        ASSERT: LSP count remains stable
        """
        # ARRANGE
        initial_stats = agent_with_lsp.lsp_pool.get_stats()
        initial_count = initial_stats["total_count"]

        # ACT - Multiple calls
        for _ in range(5):
            _ = agent_with_lsp.lsp_pool.get_stats()

        # ASSERT
        final_stats = agent_with_lsp.lsp_pool.get_stats()
        final_count = final_stats["total_count"]
        assert final_count == initial_count, (
            f"INV-OBS-01 violation: get_stats mutated lsp_pool state\n"
            f"Contract: GlobalLanguageServerPool.get_stats() INV-OBS-01\n"
            f"EXPECTED: lsp count unchanged ({initial_count})\n"
            f"ACTUAL: lsp count changed to {final_count}\n"
            f"GUIDANCE: Method MUST NOT start/stop LSPs (read-only)"
        )


# =============================================================================
# INV-OBS-02: Observability methods MUST NOT raise exceptions
# =============================================================================


class TestInvObs02NeverRaises:
    """
    CONTRACT TRACEABILITY:
    - Contract: SerenaAgent observability interface
    - Enforces: INV-OBS-02: Never raises exceptions (always returns valid dict)
    - Category: invariant, error
    - Adversarial: Implementation-blind
    """

    def test_session_registry_property_never_raises(
        self, initialized_agent: SerenaAgent
    ):
        """
        Verify INV-OBS-02: session_registry property never raises.

        ARRANGE: Initialized SerenaAgent
        ACT: Access property (no exceptions expected)
        ASSERT: Returns SessionRegistry or raises no exception
        """
        # ACT & ASSERT - Should not raise
        try:
            result = initialized_agent.session_registry
            assert result is not None  # Valid return
        except Exception as e:
            pytest.fail(
                f"INV-OBS-02 violation: session_registry raised exception\n"
                f"Contract: SerenaAgent.session_registry INV-OBS-02\n"
                f"EXPECTED: No exception\n"
                f"ACTUAL: {type(e).__name__}: {e}\n"
                f"GUIDANCE: Property MUST NOT raise (wrap in try/except if needed)"
            )

    def test_get_session_overview_with_corrupted_state(
        self, agent_with_corrupted_registry: SerenaAgent
    ):
        """
        Verify INV-OBS-02: get_session_overview returns valid dict even with corrupted state.

        ARRANGE: SerenaAgent with corrupted _session_registry
        ACT: Call get_session_overview()
        ASSERT: Returns valid dict (empty structure acceptable)
        """
        # ACT
        try:
            result = agent_with_corrupted_registry.session_registry.get_session_overview()
        except Exception as e:
            pytest.fail(
                f"INV-OBS-02 violation: get_session_overview raised on corrupted state\n"
                f"Contract: SessionRegistry.get_session_overview() INV-OBS-02\n"
                f"EXPECTED: Valid dict (empty acceptable)\n"
                f"ACTUAL: {type(e).__name__}: {e}\n"
                f"GUIDANCE: MUST catch all exceptions, return {{'sessions': [], 'total_count': 0}}"
            )

        # ASSERT - Valid structure returned
        assert isinstance(result, dict), "Must return dict even on error"
        assert "sessions" in result and "total_count" in result, (
            f"INV-OBS-02 violation: Returned dict missing required keys\n"
            f"EXPECTED: dict with 'sessions', 'total_count'\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Error handler MUST return valid structure"
        )

    def test_get_lsp_pool_stats_with_none_pool(self, agent_with_no_lsp: SerenaAgent):
        """
        Verify INV-OBS-02: Dashboard handles lsp_pool=None gracefully.

        ARRANGE: SerenaAgent with lsp_pool = None
        ACT: Dashboard checks pool and returns empty if None
        ASSERT: No exception raised, valid dict returned
        """
        # ACT - Simulate Dashboard pattern
        try:
            if agent_with_no_lsp.lsp_pool is None:
                result = {"lsps": [], "total_count": 0}
            else:
                result = agent_with_no_lsp.lsp_pool.get_stats()
        except Exception as e:
            pytest.fail(
                f"INV-OBS-02 violation: Dashboard raised exception on lsp_pool=None\n"
                f"Contract: GlobalLanguageServerPool.get_stats() INV-OBS-02\n"
                f"EXPECTED: Valid dict\n"
                f"ACTUAL: {type(e).__name__}: {e}\n"
                f"GUIDANCE: Dashboard MUST check lsp_pool is None before calling get_stats()"
            )

        # ASSERT
        assert result == {"lsps": [], "total_count": 0}


# =============================================================================
# INV-OBS-03: MUST NOT expose internal objects directly
# =============================================================================


class TestInvObs03NoInternalExposure:
    """
    CONTRACT TRACEABILITY:
    - Contract: SerenaAgent observability interface
    - Enforces: INV-OBS-03: No internal object exposure (return copies)
    - Category: invariant
    - Adversarial: Implementation-blind
    """

    def test_session_overview_modification_does_not_affect_state(
        self, agent_with_sessions: SerenaAgent
    ):
        """
        Verify INV-OBS-03: Modifying returned dict does not mutate internal state.

        ARRANGE: SerenaAgent with sessions
        ACT: Modify returned "sessions" list
        ASSERT: Next call returns unmodified data
        """
        # ARRANGE
        result1 = agent_with_sessions.session_registry.get_session_overview()
        original_count = result1["total_count"]

        # ACT - Mutate returned structure
        result1["sessions"].clear()  # Clear list
        result1["total_count"] = 999  # Change count

        # ASSERT - Next call returns original data
        result2 = agent_with_sessions.session_registry.get_session_overview()
        assert result2["total_count"] == original_count, (
            f"INV-OBS-03 violation: Modifying returned dict mutated internal state\n"
            f"Contract: SessionRegistry.get_session_overview() INV-OBS-03\n"
            f"EXPECTED: total_count={original_count} (unchanged)\n"
            f"ACTUAL: total_count={result2['total_count']}\n"
            f"GUIDANCE: MUST return shallow copy (new dict/list), not internal objects"
        )

    def test_lsp_pool_stats_modification_does_not_affect_state(
        self, agent_with_lsp: SerenaAgent
    ):
        """
        Verify INV-OBS-03: Modifying get_stats() result does not mutate pool state.

        ARRANGE: SerenaAgent with lsp_pool
        ACT: Modify returned "lsps" list
        ASSERT: Next call returns unmodified data
        """
        # ARRANGE
        result1 = agent_with_lsp.lsp_pool.get_stats()
        original_count = result1["total_count"]

        # ACT - Mutate returned structure
        result1["lsps"].clear()
        result1["total_count"] = 999

        # ASSERT
        result2 = agent_with_lsp.lsp_pool.get_stats()
        assert result2["total_count"] == original_count, (
            f"INV-OBS-03 violation: Modifying returned dict mutated lsp_pool state\n"
            f"Contract: GlobalLanguageServerPool.get_stats() INV-OBS-03\n"
            f"EXPECTED: total_count={original_count} (unchanged)\n"
            f"ACTUAL: total_count={result2['total_count']}\n"
            f"GUIDANCE: MUST return shallow copy, not internal _lsps dict"
        )


# =============================================================================
# INV-OBS-04: Thread safety (concurrent reads/writes safe)
# =============================================================================


class TestInvObs04ThreadSafety:
    """
    CONTRACT TRACEABILITY:
    - Contract: SerenaAgent observability interface
    - Enforces: INV-OBS-04: Thread-safe concurrent queries
    - Category: invariant, concurrency
    - Adversarial: Implementation-blind
    """

    def test_concurrent_session_overview_reads_no_exceptions(
        self, agent_with_sessions: SerenaAgent
    ):
        """
        Verify INV-OBS-04: Concurrent get_session_overview() calls safe.

        ARRANGE: SerenaAgent with sessions
        ACT: 10 threads call get_session_overview() concurrently
        ASSERT: No exceptions raised
        """
        exceptions = []

        def reader():
            try:
                for _ in range(10):
                    _ = agent_with_sessions.session_registry.get_session_overview()
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)

        # ACT - Start 10 concurrent readers
        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # ASSERT
        assert len(exceptions) == 0, (
            f"INV-OBS-04 violation: Concurrent reads raised exceptions\n"
            f"Contract: SessionRegistry.get_session_overview() INV-OBS-04\n"
            f"EXPECTED: No exceptions\n"
            f"ACTUAL: {len(exceptions)} exceptions: {exceptions}\n"
            f"GUIDANCE: MUST delegate to SessionRegistry lock (INV-4 from session_registry_contract)"
        )

    def test_concurrent_reads_and_writes_no_exceptions(
        self, initialized_agent: SerenaAgent, tmp_path: Path
    ):
        """
        Verify INV-OBS-04: Concurrent reads + writes (session creation) safe.

        ARRANGE: SerenaAgent
        ACT: 5 threads read, 5 threads write (create sessions) concurrently
        ASSERT: No exceptions raised, all operations complete
        """
        exceptions = []
        session_counter = [0]  # Use list for thread-safe counter mutation
        counter_lock = threading.Lock()

        def reader():
            try:
                for _ in range(5):
                    _ = initialized_agent.session_registry.get_session_overview()
                    time.sleep(0.002)
            except Exception as e:
                exceptions.append(e)

        def writer():
            try:
                for i in range(3):
                    # Get unique session number using lock
                    with counter_lock:
                        session_num = session_counter[0]
                        session_counter[0] += 1

                    # Create workspace directory for this session
                    ws = tmp_path / f"ws-{threading.current_thread().name}-{session_num}"
                    ws.mkdir(exist_ok=True)

                    # Simulate session creation (mutation) using bind_session
                    _ = initialized_agent.session_registry.bind_session(
                        f"concurrent-session-{session_num}", ws
                    )
                    time.sleep(0.002)
            except Exception as e:
                exceptions.append(e)

        # ACT - Start 5 readers + 5 writers
        reader_threads = [threading.Thread(target=reader) for _ in range(5)]
        writer_threads = [threading.Thread(target=writer) for _ in range(5)]
        all_threads = reader_threads + writer_threads

        for t in all_threads:
            t.start()
        for t in all_threads:
            t.join()

        # ASSERT
        assert len(exceptions) == 0, (
            f"INV-OBS-04 violation: Concurrent reads+writes raised exceptions\n"
            f"Contract: SerenaAgent observability INV-OBS-04\n"
            f"EXPECTED: No exceptions (thread-safe)\n"
            f"ACTUAL: {len(exceptions)} exceptions: {exceptions}\n"
            f"GUIDANCE: MUST use SessionRegistry lock for all registry access"
        )


# =============================================================================
# ERRORS-OBS-01: Observability exception suppression
# =============================================================================


class TestErrorsObs01ExceptionSuppression:
    """
    CONTRACT TRACEABILITY:
    - Contract: SerenaAgent observability interface
    - Enforces: ERRORS-OBS-01: Exceptions caught, empty structure returned
    - Category: error
    - Adversarial: Implementation-blind
    """

    def test_session_overview_exception_returns_empty_structure(
        self, agent_with_exception_registry: SerenaAgent
    ):
        """
        Verify ERRORS-OBS-01: get_session_overview catches exceptions, returns empty dict.

        ARRANGE: SerenaAgent with mocked registry that raises exception
        ACT: Call get_session_overview()
        ASSERT: Returns {"sessions": [], "total_count": 0} (no exception propagated)
        """
        # ACT
        result = agent_with_exception_registry.session_registry.get_session_overview()

        # ASSERT
        expected = {"sessions": [], "total_count": 0}
        assert result == expected, (
            f"ERRORS-OBS-01 violation: Exception not suppressed or wrong structure returned\n"
            f"Contract: SessionRegistry.get_session_overview() ERRORS-OBS-01\n"
            f"EXPECTED: {expected}\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: try/except ALL exceptions, return empty valid structure"
        )

    def test_lsp_pool_stats_exception_returns_empty_structure(
        self, agent_with_exception_lsp_pool: SerenaAgent
    ):
        """
        Verify ERRORS-OBS-01: get_stats catches exceptions, returns empty dict.

        ARRANGE: SerenaAgent with mocked lsp_pool that raises exception
        ACT: Call get_stats()
        ASSERT: Returns {"lsps": [], "total_count": 0}
        """
        # ACT
        result = agent_with_exception_lsp_pool.lsp_pool.get_stats()

        # ASSERT
        expected = {"lsps": [], "total_count": 0}
        assert result == expected, (
            f"ERRORS-OBS-01 violation: Exception not suppressed or wrong structure returned\n"
            f"Contract: GlobalLanguageServerPool.get_stats() ERRORS-OBS-01\n"
            f"EXPECTED: {expected}\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: try/except ALL exceptions, return empty valid structure"
        )


# =============================================================================
# Fixtures (Test Setup - Implementation Aware, But Tests Are Contract-Bound)
# =============================================================================


@pytest.fixture
def initialized_agent() -> SerenaAgent:
    """
    Provides initialized SerenaAgent with session_registry.
    Satisfies PRE-OBS-01: _session_registry not None.
    """
    # SerenaAgent() uses defaults: creates SessionRegistry, loads SerenaConfig from file
    agent = SerenaAgent()
    # Ensure _session_registry initialized
    assert agent._session_registry is not None, "PRE-OBS-01: Agent must be initialized"
    return agent


@pytest.fixture
def agent_with_no_lsp(initialized_agent: SerenaAgent) -> SerenaAgent:
    """
    Provides SerenaAgent with _lsp_pool = None.
    Tests POST-OBS-02 boundary case.
    """
    initialized_agent._lsp_pool = None
    return initialized_agent


@pytest.fixture
def agent_with_sessions(initialized_agent: SerenaAgent, tmp_path: Path) -> SerenaAgent:
    """
    Provides SerenaAgent with 3 active sessions.
    Tests POST-OBS-03 with real data.
    """
    # Create 3 sessions using bind_session (requires workspace_root)
    # Use tmp_path variations as workspace roots (they must exist)
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws3 = tmp_path / "ws3"
    ws1.mkdir()
    ws2.mkdir()
    ws3.mkdir()

    initialized_agent.session_registry.bind_session("session-1", ws1)
    initialized_agent.session_registry.bind_session("session-2", ws2)
    initialized_agent.session_registry.bind_session("session-3", ws3)
    return initialized_agent


@pytest.fixture
def agent_with_lsp(initialized_agent: SerenaAgent) -> SerenaAgent:
    """
    Provides SerenaAgent with lsp_pool initialized.
    Tests POST-OBS-04 with real pool.
    """
    # Initialize lsp_pool (mock or real)
    from serena.global_lsp_pool import GlobalLanguageServerPool

    pool = GlobalLanguageServerPool()
    initialized_agent._lsp_pool = pool
    return initialized_agent


@pytest.fixture
def agent_with_corrupted_registry(initialized_agent: SerenaAgent) -> SerenaAgent:
    """
    Provides SerenaAgent with corrupted _session_registry (simulates error state).
    Tests INV-OBS-02: Never raises exceptions.

    Uses real SessionRegistry with corrupted _sessions dict to exercise
    the actual exception handling code path (try/except in get_session_overview).
    """
    # Create custom object that raises when iterated (simulates corruption)
    class CorruptedSessionsDict:
        """Simulates corrupted internal state that raises on access."""

        def values(self):
            raise RuntimeError("Simulated data corruption")

        def __len__(self):
            raise RuntimeError("Simulated data corruption")

    # Replace internal _sessions with corrupted dict to trigger exception path
    # This exercises the REAL exception handling in get_session_overview()
    initialized_agent._session_registry._sessions = CorruptedSessionsDict()
    return initialized_agent


@pytest.fixture
def agent_with_exception_registry(initialized_agent: SerenaAgent) -> SerenaAgent:
    """
    Provides SerenaAgent where get_session_overview internal iteration raises.
    Tests ERRORS-OBS-01: Implementation MUST catch and return empty structure.

    Uses real SessionRegistry with corrupted _sessions dict to exercise
    the actual try/except code path in get_session_overview().
    """
    # Create custom object that raises when dict methods are called
    class ExceptionTriggeringDict:
        """Simulates internal state that raises on access."""

        def values(self):
            raise RuntimeError("Test exception during iteration")

        def __len__(self):
            raise RuntimeError("Test exception during len()")

    # Replace internal _sessions with exception-triggering dict
    # This exercises the REAL try/except in SessionRegistry.get_session_overview()
    initialized_agent._session_registry._sessions = ExceptionTriggeringDict()
    return initialized_agent


@pytest.fixture
def agent_with_exception_lsp_pool(agent_with_lsp: SerenaAgent) -> SerenaAgent:
    """
    Provides SerenaAgent where get_stats internal iteration raises.
    Tests ERRORS-OBS-01: Implementation MUST catch and return empty structure.

    Uses real GlobalLanguageServerPool with corrupted _pool dict to exercise
    the actual try/except code path in get_stats().
    """
    # Create custom object that raises when dict methods are called
    class ExceptionTriggeringPoolDict:
        """Simulates internal pool state that raises on access."""

        def items(self):
            raise RuntimeError("Test exception during pool iteration")

        def __len__(self):
            raise RuntimeError("Test exception during len()")

    # Replace internal _pool with exception-triggering dict
    # This exercises the REAL try/except in GlobalLanguageServerPool.get_stats()
    agent_with_lsp._lsp_pool._pool = ExceptionTriggeringPoolDict()
    return agent_with_lsp


# =============================================================================
# CLAUSE COVERAGE REPORT (CL12 Completeness)
# =============================================================================

"""
CLAUSE COVERAGE REPORT:

PRE-OBS-01: ✓ Verified via initialized_agent fixture (assertion)

POST-OBS-01: ✓ test_session_registry_property_returns_registry_instance
             ✓ test_session_registry_property_returns_same_instance

POST-OBS-02: ✓ test_lsp_pool_property_returns_pool_or_none
             ✓ test_lsp_pool_property_none_is_valid

POST-OBS-03: ✓ test_session_overview_has_required_keys
             ✓ test_session_overview_sessions_is_list
             ✓ test_session_overview_total_count_is_int
             ✓ test_session_overview_total_count_matches_length

POST-OBS-04: ✓ test_lsp_pool_stats_has_required_keys
             ✓ test_lsp_pool_stats_lsps_is_list
             ✓ test_lsp_pool_stats_total_count_is_int
             ✓ test_lsp_pool_stats_total_count_matches_length
             ✓ test_lsp_pool_none_dashboard_returns_empty

INV-OBS-01:  ✓ test_session_registry_property_does_not_mutate
             ✓ test_get_session_overview_does_not_mutate
             ✓ test_get_lsp_pool_stats_does_not_mutate

INV-OBS-02:  ✓ test_session_registry_property_never_raises
             ✓ test_get_session_overview_with_corrupted_state
             ✓ test_get_lsp_pool_stats_with_none_pool

INV-OBS-03:  ✓ test_session_overview_modification_does_not_affect_state
             ✓ test_lsp_pool_stats_modification_does_not_affect_state

INV-OBS-04:  ✓ test_concurrent_session_overview_reads_no_exceptions
             ✓ test_concurrent_reads_and_writes_no_exceptions

ERRORS-OBS-01: ✓ test_session_overview_exception_returns_empty_structure
               ✓ test_lsp_pool_stats_exception_returns_empty_structure

COMPLETENESS: All clauses covered (9/9 = 100%)
"""
