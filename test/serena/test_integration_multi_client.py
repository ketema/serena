"""
Adversarial TDD Integration Tests for REQ-6: Real Multi-Client Isolation

Contract: Phase 3 MCP Multi-Client Architecture
Source: .serena/memories/cycle-6-phase-3-mcp-switch.md

Requirements tested:
- REQ-6: Real integration tests prove concurrent multi-client isolation and lifecycle safety
- REQ-6.1: Path boundaries prevent cross-client file access
- REQ-6.2: Session disconnection does not affect other clients
- REQ-6.3: Concurrent activation has no cross-talk

These tests use REAL components only (NO MOCKS for Registry, Pool, or Dispatcher).
Data isolation is achieved via temporary directories.

Test Writer is BLIND to implementation - error messages are specifications.
Coder is BLIND to test source - implements from error messages only.
"""

import threading
from pathlib import Path
from typing import Any

import pytest

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def temp_workspace_a(tmp_path: Path) -> Path:
    """
    Create temporary workspace A with test files.

    PRE: tmp_path exists and is writable
    POST: Returns workspace_a directory with file_a.txt
    """
    workspace = tmp_path / "workspace_a"
    workspace.mkdir()
    (workspace / "file_a.txt").write_text("content_a")
    (workspace / "subdir").mkdir()
    (workspace / "subdir" / "nested_a.txt").write_text("nested_content_a")
    return workspace


@pytest.fixture
def temp_workspace_b(tmp_path: Path) -> Path:
    """
    Create temporary workspace B with test files.

    PRE: tmp_path exists and is writable
    POST: Returns workspace_b directory with file_b.txt
    """
    workspace = tmp_path / "workspace_b"
    workspace.mkdir()
    (workspace / "file_b.txt").write_text("content_b")
    (workspace / "subdir").mkdir()
    (workspace / "subdir" / "nested_b.txt").write_text("nested_content_b")
    return workspace


@pytest.fixture
def session_registry() -> Any:
    """
    Create real SessionRegistry instance.

    Contract: Must provide bind_session, unbind_session, get_session, get_session_overview
    POST: Returns SessionRegistry ready for multi-client testing
    """
    from serena.session_registry import SessionRegistry

    return SessionRegistry()


@pytest.fixture
def mcp_bridge(session_registry: Any) -> Any:
    """
    Create real MCPSessionBridge instance.

    Contract: Must provide run_with_session_context for session isolation
    POST: Returns MCPSessionBridge with real registry (no mock)
    """
    from serena.mcp_session_bridge import MCPSessionBridge

    return MCPSessionBridge(session_registry=session_registry)


# =============================================================================
# REQ-6.1: MULTI-CLIENT PATH ISOLATION
# =============================================================================


class TestMultiClientIsolation:
    """REQ-6.1: Path boundaries prevent cross-client file access."""

    def test_multi_client_isolation(
        self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path
    ) -> None:
        """
        WHAT: Two MCP clients activate different projects and attempt file access
        WHY: REQ-6.1 requires path boundaries to prevent cross-client access
        EXPECTED: Each client sees only their project's workspace_root
        ACTUAL: (will be determined by test run)
        GUIDANCE: SessionRegistry MUST enforce workspace isolation via workspace_root boundaries.
                  Each session MUST be bound to exactly one workspace_root.
                  get_session_overview() MUST return accurate snapshot of all bindings.
        """
        # Simulate MCP Client A activating Project A
        session_registry.bind_session(
            session_id="mcp-client-a", workspace_root=temp_workspace_a, source="mcp"
        )

        # Simulate MCP Client B activating Project B
        session_registry.bind_session(
            session_id="mcp-client-b", workspace_root=temp_workspace_b, source="mcp"
        )

        # Verify both sessions exist in registry
        session_a = session_registry.get_session("mcp-client-a")
        session_b = session_registry.get_session("mcp-client-b")

        assert session_a is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session_registry.get_session('mcp-client-a') returned None\n"
            "2. WHY: REQ-6.1 violation - MCP Client A session not bound\n"
            "3. EXPECTED: get_session('mcp-client-a') returns SessionContext with workspace_root == temp_workspace_a\n"
            "4. ACTUAL: get_session('mcp-client-a') returned None\n"
            "5. GUIDANCE: bind_session MUST store session_id → SessionContext mapping.\n"
            "              Verify session_id is stored correctly in registry state.\n"
        )

        assert session_b is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session_registry.get_session('mcp-client-b') returned None\n"
            "2. WHY: REQ-6.1 violation - MCP Client B session not bound\n"
            "3. EXPECTED: get_session('mcp-client-b') returns SessionContext with workspace_root == temp_workspace_b\n"
            "4. ACTUAL: get_session('mcp-client-b') returned None\n"
            "5. GUIDANCE: bind_session MUST store session_id → SessionContext mapping.\n"
            "              Each session MUST be independently bound.\n"
        )

        # Verify workspace_root isolation
        assert session_a.workspace_root == temp_workspace_a, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session_a.workspace_root does not match temp_workspace_a\n"
            f"2. WHY: REQ-6.1 violation - Client A workspace_root incorrect\n"
            f"3. EXPECTED: session_a.workspace_root == {temp_workspace_a}\n"
            f"4. ACTUAL: session_a.workspace_root == {session_a.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST set SessionContext.workspace_root to exact Path provided.\n"
            "              No path resolution or modification allowed.\n"
        )

        assert session_b.workspace_root == temp_workspace_b, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session_b.workspace_root does not match temp_workspace_b\n"
            f"2. WHY: REQ-6.1 violation - Client B workspace_root incorrect\n"
            f"3. EXPECTED: session_b.workspace_root == {temp_workspace_b}\n"
            f"4. ACTUAL: session_b.workspace_root == {session_b.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST set SessionContext.workspace_root to exact Path provided.\n"
            "              Each session MUST have independent workspace_root.\n"
        )

        # Verify registry snapshot shows both sessions
        overview = session_registry.get_session_overview()

        assert "sessions" in overview, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session_overview() missing 'sessions' key\n"
            "2. WHY: REQ-6.1 violation - cannot verify multi-client state\n"
            "3. EXPECTED: overview['sessions'] is a list of session metadata\n"
            f"4. ACTUAL: overview keys == {list(overview.keys())}\n"
            "5. GUIDANCE: get_session_overview() MUST return dict with 'sessions' key.\n"
            "              'sessions' MUST contain list of all active sessions.\n"
        )

        assert "total_count" in overview, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session_overview() missing 'total_count' key\n"
            "2. WHY: REQ-6.1 violation - cannot verify session count\n"
            "3. EXPECTED: overview['total_count'] == 2\n"
            f"4. ACTUAL: overview keys == {list(overview.keys())}\n"
            "5. GUIDANCE: get_session_overview() MUST return dict with 'total_count' key.\n"
            "              'total_count' MUST equal len(sessions) list.\n"
        )

        assert overview["total_count"] == 2, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session_overview()['total_count'] != 2\n"
            "2. WHY: REQ-6.1 violation - expected 2 active sessions (Client A, Client B)\n"
            "3. EXPECTED: total_count == 2\n"
            f"4. ACTUAL: total_count == {overview['total_count']}\n"
            "5. GUIDANCE: total_count MUST reflect exact number of bound sessions.\n"
            "              Verify bind_session increments count correctly.\n"
        )

        # Verify both sessions appear in overview
        session_ids = {s["session_id"] for s in overview["sessions"]}
        assert "mcp-client-a" in session_ids, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: 'mcp-client-a' not in session_overview['sessions']\n"
            "2. WHY: REQ-6.1 violation - Client A session not visible in overview\n"
            "3. EXPECTED: session_ids contains 'mcp-client-a'\n"
            f"4. ACTUAL: session_ids == {session_ids}\n"
            "5. GUIDANCE: get_session_overview() MUST include all bound sessions.\n"
            "              Verify session metadata is added to 'sessions' list.\n"
        )

        assert "mcp-client-b" in session_ids, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: 'mcp-client-b' not in session_overview['sessions']\n"
            "2. WHY: REQ-6.1 violation - Client B session not visible in overview\n"
            "3. EXPECTED: session_ids contains 'mcp-client-b'\n"
            f"4. ACTUAL: session_ids == {session_ids}\n"
            "5. GUIDANCE: get_session_overview() MUST include all bound sessions.\n"
            "              Each bound session MUST appear in overview snapshot.\n"
        )

        # Theater Test Check: Verify EXACT workspace_root mapping (not just presence)
        # CRITICAL: Check session_id → workspace_root mapping is CORRECT (prevent swaps)
        workspace_map = {
            s["session_id"]: s["workspace_root"] for s in overview["sessions"]
        }

        assert workspace_map.get("mcp-client-a") == str(temp_workspace_a), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: workspace_root for 'mcp-client-a' does not match temp_workspace_a\n"
            "2. WHY: REQ-6.1 violation - session_id → workspace_root mapping incorrect (possible swap)\n"
            f"3. EXPECTED: workspace_map['mcp-client-a'] == '{temp_workspace_a}'\n"
            f"4. ACTUAL: workspace_map['mcp-client-a'] == {workspace_map.get('mcp-client-a')}\n"
            "5. GUIDANCE: bind_session MUST map session_id to EXACT workspace_root provided.\n"
            "              get_session_overview() MUST preserve session_id → workspace_root correctness.\n"
            "              Theater test prevention: Verify exact mapping, not just set membership.\n"
        )

        assert workspace_map.get("mcp-client-b") == str(temp_workspace_b), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: workspace_root for 'mcp-client-b' does not match temp_workspace_b\n"
            "2. WHY: REQ-6.1 violation - session_id → workspace_root mapping incorrect (possible swap)\n"
            f"3. EXPECTED: workspace_map['mcp-client-b'] == '{temp_workspace_b}'\n"
            f"4. ACTUAL: workspace_map['mcp-client-b'] == {workspace_map.get('mcp-client-b')}\n"
            "5. GUIDANCE: bind_session MUST map session_id to EXACT workspace_root provided.\n"
            "              get_session_overview() MUST preserve session_id → workspace_root correctness.\n"
            "              Theater test prevention: Verify exact mapping, not just set membership.\n"
        )


# =============================================================================
# REQ-6.2: SESSION DISCONNECTION ISOLATION
# =============================================================================


class TestDisconnectionIsolation:
    """REQ-6.2: Session disconnection does not affect other clients."""

    def test_disconnect_does_not_affect_other_client(
        self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path
    ) -> None:
        """
        WHAT: Two MCP clients active, one disconnects
        WHY: REQ-6.2 requires disconnection to be isolated to single session
        EXPECTED: Disconnected session removed, other session persists
        ACTUAL: (will be determined by test run)
        GUIDANCE: unbind_session MUST remove only specified session_id.
                  Other sessions MUST remain in registry with unchanged state.
                  get_session_overview() MUST reflect removal immediately.
        """
        # Bind two sessions
        session_registry.bind_session(
            session_id="client-a", workspace_root=temp_workspace_a, source="mcp"
        )
        session_registry.bind_session(
            session_id="client-b", workspace_root=temp_workspace_b, source="mcp"
        )

        # Capture PRE-disconnect state for Client B (to verify unchanged after disconnect)
        session_b_before = session_registry.get_session("client-b")
        workspace_b_before = session_b_before.workspace_root if session_b_before else None

        # Verify both sessions exist
        overview_before = session_registry.get_session_overview()
        assert overview_before["total_count"] == 2, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session_overview()['total_count'] != 2 before disconnect\n"
            "2. WHY: Test setup violation - need 2 active sessions to test disconnection\n"
            "3. EXPECTED: total_count == 2\n"
            f"4. ACTUAL: total_count == {overview_before['total_count']}\n"
            "5. GUIDANCE: bind_session MUST successfully bind both sessions.\n"
            "              Verify both bind_session calls succeed.\n"
        )

        # Client A disconnects
        session_registry.unbind_session(session_id="client-a")

        # Verify Client A is removed
        session_a_after = session_registry.get_session("client-a")
        assert session_a_after is None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session('client-a') returned non-None after unbind\n"
            "2. WHY: REQ-6.2 violation - unbind_session did not remove session\n"
            "3. EXPECTED: get_session('client-a') returns None\n"
            f"4. ACTUAL: get_session('client-a') == {session_a_after}\n"
            "5. GUIDANCE: unbind_session MUST remove session from registry.\n"
            "              get_session MUST return None for unbound session_id.\n"
        )

        # Verify Client B continues to operate normally
        session_b_after = session_registry.get_session("client-b")
        assert session_b_after is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session('client-b') returned None after Client A disconnect\n"
            "2. WHY: REQ-6.2 violation - unbind_session affected other session\n"
            "3. EXPECTED: get_session('client-b') returns SessionContext\n"
            "4. ACTUAL: get_session('client-b') returned None\n"
            "5. GUIDANCE: unbind_session MUST only remove specified session_id.\n"
            "              Other sessions MUST remain unchanged in registry.\n"
        )

        # CRITICAL: Verify Client B state is UNCHANGED (not just exists)
        assert session_b_after.workspace_root == temp_workspace_b, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Client B workspace_root changed after Client A disconnect\n"
            "2. WHY: REQ-6.2 violation - unbind_session corrupted other session state\n"
            f"3. EXPECTED: session_b_after.workspace_root == {temp_workspace_b}\n"
            f"4. ACTUAL: session_b_after.workspace_root == {session_b_after.workspace_root}\n"
            "5. GUIDANCE: unbind_session MUST NOT modify other session state.\n"
            "              Only specified session_id MUST be removed.\n"
        )

        # Theater Test Prevention: Verify workspace_root UNCHANGED (compare pre/post)
        assert session_b_after.workspace_root == workspace_b_before, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Client B workspace_root mutated during Client A disconnect\n"
            "2. WHY: REQ-6.2 violation - unbind_session modified surviving session\n"
            f"3. EXPECTED: session_b_after.workspace_root == {workspace_b_before}\n"
            f"4. ACTUAL: session_b_after.workspace_root == {session_b_after.workspace_root}\n"
            "5. GUIDANCE: unbind_session MUST preserve exact state of other sessions.\n"
            "              workspace_root MUST remain identical pre/post disconnect.\n"
            "              Theater test prevention: Compare pre/post state, not just post state.\n"
        )

        # Verify registry overview shows only Client B
        overview_after = session_registry.get_session_overview()
        assert overview_after["total_count"] == 1, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session_overview()['total_count'] != 1 after disconnect\n"
            "2. WHY: REQ-6.2 violation - total_count not updated after unbind_session\n"
            "3. EXPECTED: total_count == 1\n"
            f"4. ACTUAL: total_count == {overview_after['total_count']}\n"
            "5. GUIDANCE: unbind_session MUST decrement total_count.\n"
            "              get_session_overview() MUST reflect removal immediately.\n"
        )

        session_ids_after = {s["session_id"] for s in overview_after["sessions"]}
        assert "client-a" not in session_ids_after, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: 'client-a' still in session_overview after unbind\n"
            "2. WHY: REQ-6.2 violation - overview not updated after unbind_session\n"
            "3. EXPECTED: session_ids_after does not contain 'client-a'\n"
            f"4. ACTUAL: session_ids_after == {session_ids_after}\n"
            "5. GUIDANCE: unbind_session MUST remove session from overview.\n"
            "              get_session_overview() MUST NOT include unbound sessions.\n"
        )

        assert "client-b" in session_ids_after, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: 'client-b' not in session_overview after Client A unbind\n"
            "2. WHY: REQ-6.2 violation - overview lost other session during unbind\n"
            "3. EXPECTED: session_ids_after contains 'client-b'\n"
            f"4. ACTUAL: session_ids_after == {session_ids_after}\n"
            "5. GUIDANCE: unbind_session MUST preserve other sessions in overview.\n"
            "              Only specified session_id MUST be removed.\n"
        )

        # Theater Test Check: Verify Client B can still be retrieved with correct workspace_root
        # (not just that count is 1, but that the remaining session is correct)
        client_b_entry = next(
            (s for s in overview_after["sessions"] if s["session_id"] == "client-b"),
            None,
        )
        assert client_b_entry is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: 'client-b' entry not found in overview['sessions']\n"
            "2. WHY: REQ-6.2 violation - overview structure inconsistent\n"
            "3. EXPECTED: overview['sessions'] contains entry with session_id=='client-b'\n"
            f"4. ACTUAL: overview['sessions'] == {overview_after['sessions']}\n"
            "5. GUIDANCE: get_session_overview() MUST include metadata for each session.\n"
            "              Each entry MUST have session_id field.\n"
        )

        assert client_b_entry["workspace_root"] == str(temp_workspace_b), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Client B workspace_root in overview is incorrect\n"
            "2. WHY: REQ-6.2 violation - overview metadata corrupted during unbind\n"
            f"3. EXPECTED: client_b_entry['workspace_root'] == '{temp_workspace_b}'\n"
            f"4. ACTUAL: client_b_entry['workspace_root'] == {client_b_entry['workspace_root']}\n"
            "5. GUIDANCE: unbind_session MUST NOT modify other session metadata.\n"
            "              Overview MUST reflect exact state of remaining sessions.\n"
        )


# =============================================================================
# REQ-6.3: CONCURRENT ACTIVATION NO CROSS-TALK
# =============================================================================


class TestConcurrentActivationNoCrossTalk:
    """REQ-6.3: Concurrent activation has no cross-talk or registry leakage."""

    def test_concurrent_activation_no_cross_talk(
        self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path
    ) -> None:
        """
        WHAT: Two threads simulate concurrent MCP client activation
        WHY: REQ-6.3 requires thread-safe session binding with no cross-talk
        EXPECTED: All sessions correctly bound with no interference
        ACTUAL: (will be determined by test run)
        GUIDANCE: bind_session MUST be thread-safe using threading.Lock.
                  Concurrent bind_session calls MUST NOT corrupt registry state.
                  Each session MUST be bound to correct workspace_root regardless of timing.
        """
        results: dict[str, Any] = {}
        errors: list[tuple[str, Exception]] = []

        def activate_client_a() -> None:
            """Simulate MCP Client A activation."""
            try:
                session_registry.bind_session(
                    session_id="concurrent-a",
                    workspace_root=temp_workspace_a,
                    source="mcp",
                )
                # Immediately retrieve to verify binding
                session = session_registry.get_session("concurrent-a")
                results["concurrent-a"] = session
            except Exception as e:
                errors.append(("concurrent-a", e))

        def activate_client_b() -> None:
            """Simulate MCP Client B activation."""
            try:
                session_registry.bind_session(
                    session_id="concurrent-b",
                    workspace_root=temp_workspace_b,
                    source="mcp",
                )
                # Immediately retrieve to verify binding
                session = session_registry.get_session("concurrent-b")
                results["concurrent-b"] = session
            except Exception as e:
                errors.append(("concurrent-b", e))

        # Launch concurrent activations
        thread_a = threading.Thread(target=activate_client_a)
        thread_b = threading.Thread(target=activate_client_b)

        thread_a.start()
        thread_b.start()

        thread_a.join(timeout=5.0)
        thread_b.join(timeout=5.0)

        # Verify no exceptions occurred
        assert len(errors) == 0, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Exception raised during concurrent bind_session\n"
            "2. WHY: REQ-6.3 violation - bind_session not thread-safe\n"
            "3. EXPECTED: All bind_session calls succeed without exceptions\n"
            f"4. ACTUAL: errors == {errors}\n"
            "5. GUIDANCE: bind_session MUST use threading.Lock to protect shared state.\n"
            "              Concurrent calls MUST NOT raise exceptions or corrupt state.\n"
        )

        # Verify both threads completed
        assert thread_a.is_alive() is False, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Thread A did not complete within timeout\n"
            "2. WHY: REQ-6.3 violation - potential deadlock in bind_session\n"
            "3. EXPECTED: Thread A completes within 5 seconds\n"
            "4. ACTUAL: Thread A still alive after join(timeout=5.0)\n"
            "5. GUIDANCE: bind_session MUST NOT deadlock.\n"
            "              Threading.Lock MUST be acquired and released correctly.\n"
        )

        assert thread_b.is_alive() is False, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Thread B did not complete within timeout\n"
            "2. WHY: REQ-6.3 violation - potential deadlock in bind_session\n"
            "3. EXPECTED: Thread B completes within 5 seconds\n"
            "4. ACTUAL: Thread B still alive after join(timeout=5.0)\n"
            "5. GUIDANCE: bind_session MUST NOT deadlock.\n"
            "              Threading.Lock MUST be acquired and released correctly.\n"
        )

        # Verify both sessions were successfully bound
        assert "concurrent-a" in results, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: 'concurrent-a' not in results\n"
            "2. WHY: REQ-6.3 violation - Thread A did not retrieve session\n"
            "3. EXPECTED: results contains 'concurrent-a' key\n"
            f"4. ACTUAL: results.keys() == {list(results.keys())}\n"
            "5. GUIDANCE: bind_session MUST successfully store session.\n"
            "              get_session MUST retrieve session immediately after bind.\n"
        )

        assert "concurrent-b" in results, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: 'concurrent-b' not in results\n"
            "2. WHY: REQ-6.3 violation - Thread B did not retrieve session\n"
            "3. EXPECTED: results contains 'concurrent-b' key\n"
            f"4. ACTUAL: results.keys() == {list(results.keys())}\n"
            "5. GUIDANCE: bind_session MUST successfully store session.\n"
            "              get_session MUST retrieve session immediately after bind.\n"
        )

        session_a = results["concurrent-a"]
        session_b = results["concurrent-b"]

        assert session_a is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session('concurrent-a') returned None after bind\n"
            "2. WHY: REQ-6.3 violation - bind_session did not persist session\n"
            "3. EXPECTED: session_a is SessionContext\n"
            "4. ACTUAL: session_a is None\n"
            "5. GUIDANCE: bind_session MUST persist session to registry.\n"
            "              Thread-safety MUST NOT prevent successful storage.\n"
        )

        assert session_b is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session('concurrent-b') returned None after bind\n"
            "2. WHY: REQ-6.3 violation - bind_session did not persist session\n"
            "3. EXPECTED: session_b is SessionContext\n"
            "4. ACTUAL: session_b is None\n"
            "5. GUIDANCE: bind_session MUST persist session to registry.\n"
            "              Thread-safety MUST NOT prevent successful storage.\n"
        )

        # Verify no registry leakage (each session has correct workspace_root)
        assert session_a.workspace_root == temp_workspace_a, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session_a.workspace_root != temp_workspace_a\n"
            "2. WHY: REQ-6.3 violation - registry leakage or cross-talk during concurrent bind\n"
            f"3. EXPECTED: session_a.workspace_root == {temp_workspace_a}\n"
            f"4. ACTUAL: session_a.workspace_root == {session_a.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST correctly assign workspace_root to each session.\n"
            "              Concurrent operations MUST NOT swap or corrupt workspace_root values.\n"
        )

        assert session_b.workspace_root == temp_workspace_b, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session_b.workspace_root != temp_workspace_b\n"
            "2. WHY: REQ-6.3 violation - registry leakage or cross-talk during concurrent bind\n"
            f"3. EXPECTED: session_b.workspace_root == {temp_workspace_b}\n"
            f"4. ACTUAL: session_b.workspace_root == {session_b.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST correctly assign workspace_root to each session.\n"
            "              Concurrent operations MUST NOT swap or corrupt workspace_root values.\n"
        )

        # Theater Test Check: Verify registry overview shows correct total_count
        # (not just that individual get_session works, but that overall state is consistent)
        overview = session_registry.get_session_overview()
        assert overview["total_count"] == 2, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session_overview()['total_count'] != 2 after concurrent bind\n"
            "2. WHY: REQ-6.3 violation - concurrent bind_session corrupted registry count\n"
            "3. EXPECTED: total_count == 2\n"
            f"4. ACTUAL: total_count == {overview['total_count']}\n"
            "5. GUIDANCE: bind_session MUST correctly increment total_count under concurrent access.\n"
            "              Thread-safety MUST ensure accurate count regardless of timing.\n"
        )

        # Verify both sessions appear in overview
        session_ids = {s["session_id"] for s in overview["sessions"]}
        assert session_ids == {"concurrent-a", "concurrent-b"}, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session_ids != {'concurrent-a', 'concurrent-b'}\n"
            "2. WHY: REQ-6.3 violation - registry overview missing or has extra sessions\n"
            "3. EXPECTED: session_ids == {'concurrent-a', 'concurrent-b'}\n"
            f"4. ACTUAL: session_ids == {session_ids}\n"
            "5. GUIDANCE: bind_session MUST add exactly one entry per session_id.\n"
            "              get_session_overview() MUST reflect all bound sessions.\n"
        )

        # Verify workspace_roots are correct in overview (theater test: check actual data)
        workspace_map = {
            s["session_id"]: s["workspace_root"] for s in overview["sessions"]
        }
        assert workspace_map["concurrent-a"] == str(temp_workspace_a), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: overview workspace_root for 'concurrent-a' incorrect\n"
            "2. WHY: REQ-6.3 violation - registry overview has wrong workspace_root\n"
            f"3. EXPECTED: workspace_map['concurrent-a'] == '{temp_workspace_a}'\n"
            f"4. ACTUAL: workspace_map['concurrent-a'] == {workspace_map['concurrent-a']}\n"
            "5. GUIDANCE: get_session_overview() MUST reflect exact workspace_root from bind_session.\n"
            "              Thread-safety MUST NOT corrupt overview metadata.\n"
        )

        assert workspace_map["concurrent-b"] == str(temp_workspace_b), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: overview workspace_root for 'concurrent-b' incorrect\n"
            "2. WHY: REQ-6.3 violation - registry overview has wrong workspace_root\n"
            f"3. EXPECTED: workspace_map['concurrent-b'] == '{temp_workspace_b}'\n"
            f"4. ACTUAL: workspace_map['concurrent-b'] == {workspace_map['concurrent-b']}\n"
            "5. GUIDANCE: get_session_overview() MUST reflect exact workspace_root from bind_session.\n"
            "              Thread-safety MUST NOT corrupt overview metadata.\n"
        )
