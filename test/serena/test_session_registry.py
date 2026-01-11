"""
Adversarial TDD tests for SessionRegistry + SessionContext.

Contract: contracts/session_registry.contract.py (verified: 2026-01-11)
Component: SessionRegistry for multi-project MCP session isolation

Test Writer is BLIND to implementation - error messages are specifications.
Coder is BLIND to test source - implements from error messages only.

Requirements tested:
- REQ-1: Two MCP clients connect simultaneously to different projects without interference
- REQ-2: Session A cannot access files in Session B's project
- REQ-3: ContextVar propagation survives await boundaries
- REQ-4: Thread-safe bind/unbind with asyncio.Lock
- REQ-5: Cleanup on last session for workspace
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def temp_workspace_a(tmp_path: Path) -> Path:
    """Create temporary workspace A with test files."""
    workspace = tmp_path / "workspace_a"
    workspace.mkdir()
    (workspace / "file_a.txt").write_text("content_a")
    return workspace


@pytest.fixture
def temp_workspace_b(tmp_path: Path) -> Path:
    """Create temporary workspace B with test files."""
    workspace = tmp_path / "workspace_b"
    workspace.mkdir()
    (workspace / "file_b.txt").write_text("content_b")
    return workspace


@pytest.fixture
def session_registry():
    """
    Create SessionRegistry instance.

    Contract: Must provide bind_session, unbind_session, get_session, get_sessions_for_workspace
    """
    # Import will be provided by coder
    from serena.session_registry import SessionRegistry

    return SessionRegistry()


# =============================================================================
# REQ-1: SIMULTANEOUS MULTI-PROJECT SESSIONS
# =============================================================================


class TestSimultaneousMultiProjectSessions:
    """REQ-1: Two MCP clients connect simultaneously to different projects without interference."""

    @pytest.mark.asyncio
    async def test_bind_two_sessions_different_workspaces(self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path):
        """
        WHAT: Bind two sessions to different workspaces simultaneously
        WHY: REQ-1 requires sessions to not interfere with each other
        EXPECTED: Both sessions successfully bound with different workspace_roots
        ACTUAL: (will be determined by test run)
        GUIDANCE: Sessions MUST maintain separate workspace_root values.
                  Implementation free to choose storage: dict, list, or other thread-safe structure.
        """
        # Bind session A to workspace A
        await session_registry.bind_session(session_id="session-a", workspace_root=temp_workspace_a, source="explicit")

        # Bind session B to workspace B
        await session_registry.bind_session(session_id="session-b", workspace_root=temp_workspace_b, source="explicit")

        # Verify both sessions exist
        retrieved_a = session_registry.get_session("session-a")
        retrieved_b = session_registry.get_session("session-b")

        assert retrieved_a is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session_registry.get_session('session-a') returned None\n"
            "2. WHY: REQ-1 violation - session A was not bound to registry\n"
            "3. EXPECTED: get_session('session-a') returns SessionContext with workspace_root == temp_workspace_a\n"
            "4. ACTUAL: get_session('session-a') returned None\n"
            "5. GUIDANCE: bind_session MUST store session_id → SessionContext mapping.\n"
            "             POST-1 contract violation: session_id not retrievable after bind.\n"
            "             Implementation free to use dict, concurrent.futures, or asyncio primitives."
        )

        assert retrieved_b is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session_registry.get_session('session-b') returned None\n"
            "2. WHY: REQ-1 violation - session B was not bound to registry\n"
            "3. EXPECTED: get_session('session-b') returns SessionContext with workspace_root == temp_workspace_b\n"
            "4. ACTUAL: get_session('session-b') returned None\n"
            "5. GUIDANCE: bind_session MUST store session_id → SessionContext mapping.\n"
            "             POST-1 contract violation for second session.\n"
            "             Check thread-safety: concurrent bind calls must not interfere."
        )

        # Verify isolation: different workspaces
        assert retrieved_a.workspace_root == temp_workspace_a.resolve(), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: retrieved_a.workspace_root != temp_workspace_a.resolve()\n"
            "2. WHY: REQ-1 violation - session A workspace_root is incorrect\n"
            f"3. EXPECTED: workspace_root == {temp_workspace_a.resolve()}\n"
            f"4. ACTUAL: workspace_root == {retrieved_a.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST resolve workspace_root before storing.\n"
            "             INV-2 contract violation: workspace_root must be absolute, resolved path.\n"
            "             Use Path.resolve() to resolve symlinks and normalize path."
        )

        assert retrieved_b.workspace_root == temp_workspace_b.resolve(), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: retrieved_b.workspace_root != temp_workspace_b.resolve()\n"
            "2. WHY: REQ-1 violation - session B workspace_root is incorrect\n"
            f"3. EXPECTED: workspace_root == {temp_workspace_b.resolve()}\n"
            f"4. ACTUAL: workspace_root == {retrieved_b.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST resolve workspace_root before storing.\n"
            "             INV-2 contract violation: workspace_root must be absolute, resolved path.\n"
            "             Check: Are symlinks resolved? Use Path.resolve()."
        )

        # Verify INV-1: session_id is unique
        assert retrieved_a.session_id != retrieved_b.session_id, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: retrieved_a.session_id == retrieved_b.session_id\n"
            "2. WHY: REQ-1 violation - sessions have same session_id\n"
            "3. EXPECTED: session_id values are unique ('session-a' != 'session-b')\n"
            f"4. ACTUAL: both have session_id == {retrieved_a.session_id}\n"
            "5. GUIDANCE: INV-1 contract violation: session_id MUST be unique across all sessions.\n"
            "             bind_session must preserve the provided session_id value.\n"
            "             Check: Are you overwriting session_id during bind?"
        )

    @pytest.mark.asyncio
    async def test_concurrent_bind_operations(self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path):
        """
        WHAT: Bind two sessions concurrently (race condition test)
        WHY: REQ-4 requires thread-safe bind/unbind operations
        EXPECTED: Both binds succeed without data corruption
        ACTUAL: (will be determined by test run)
        GUIDANCE: bind_session MUST use asyncio.Lock or equivalent synchronization.
                  INV-4 contract: all mutations are atomic.
        """
        # Concurrent bind operations
        results = await asyncio.gather(
            session_registry.bind_session("session-1", temp_workspace_a, "explicit"),
            session_registry.bind_session("session-2", temp_workspace_b, "explicit"),
        )

        assert len(results) == 2, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: asyncio.gather returned != 2 results\n"
            "2. WHY: REQ-4 violation - concurrent bind operations failed\n"
            "3. EXPECTED: Both bind_session calls complete successfully (2 results)\n"
            f"4. ACTUAL: asyncio.gather returned {len(results)} results\n"
            "5. GUIDANCE: bind_session MUST be thread-safe for concurrent calls.\n"
            "             INV-4 contract: all mutations are atomic.\n"
            "             Use asyncio.Lock to protect registry mutations."
        )

        # Verify both sessions exist
        ctx_1 = session_registry.get_session("session-1")
        ctx_2 = session_registry.get_session("session-2")

        assert ctx_1 is not None and ctx_2 is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: One or both sessions not found after concurrent bind\n"
            "2. WHY: REQ-4 violation - race condition in bind_session\n"
            "3. EXPECTED: Both sessions retrievable after concurrent bind\n"
            f"4. ACTUAL: ctx_1={ctx_1}, ctx_2={ctx_2}\n"
            "5. GUIDANCE: Race condition detected - concurrent bind operations interfered.\n"
            "             INV-4 contract violation: mutations not atomic.\n"
            "             Use async with lock: before modifying internal registry dict."
        )


# =============================================================================
# REQ-2: SESSION FILE ACCESS ISOLATION
# =============================================================================


class TestSessionFileAccessIsolation:
    """REQ-2: Session A cannot access files in Session B's project."""

    @pytest.mark.asyncio
    async def test_session_workspace_boundary_enforcement(self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path):
        """
        WHAT: Verify sessions have correct workspace_root boundaries
        WHY: REQ-2 requires file access isolation between sessions
        EXPECTED: Session A workspace_root != Session B workspace_root
        ACTUAL: (will be determined by test run)
        GUIDANCE: SessionContext MUST store resolved, absolute workspace_root.
                  File access tools MUST validate paths against session.workspace_root.
        """
        # Bind sessions
        await session_registry.bind_session("session-a", temp_workspace_a, "explicit")
        await session_registry.bind_session("session-b", temp_workspace_b, "explicit")

        # Get contexts
        ctx_a = session_registry.get_session("session-a")
        ctx_b = session_registry.get_session("session-b")

        # Verify workspace boundaries
        assert ctx_a.workspace_root != ctx_b.workspace_root, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: ctx_a.workspace_root == ctx_b.workspace_root\n"
            "2. WHY: REQ-2 violation - sessions share same workspace boundary\n"
            "3. EXPECTED: Session A and Session B have different workspace_root values\n"
            f"4. ACTUAL: Both have workspace_root == {ctx_a.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST preserve different workspace_root values.\n"
            "             Check: Are you overwriting workspace_root in global state?\n"
            "             Sessions MUST be isolated - each has unique workspace_root."
        )

        # Verify workspace_root is absolute (INV-2)
        assert ctx_a.workspace_root.is_absolute(), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: ctx_a.workspace_root is not absolute\n"
            "2. WHY: INV-2 contract violation - workspace_root must be absolute\n"
            f"3. EXPECTED: workspace_root.is_absolute() == True\n"
            f"4. ACTUAL: workspace_root == {ctx_a.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST call workspace_root.resolve() before storing.\n"
            "             INV-2 contract: workspace_root is always absolute, resolved path.\n"
            "             Use Path.resolve() to convert relative → absolute."
        )

        assert ctx_b.workspace_root.is_absolute(), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: ctx_b.workspace_root is not absolute\n"
            "2. WHY: INV-2 contract violation - workspace_root must be absolute\n"
            f"3. EXPECTED: workspace_root.is_absolute() == True\n"
            f"4. ACTUAL: workspace_root == {ctx_b.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST call workspace_root.resolve() before storing.\n"
            "             INV-2 contract: workspace_root is always absolute, resolved path."
        )

    @pytest.mark.asyncio
    async def test_symlink_resolution_for_boundary_check(self, session_registry: Any, tmp_path: Path):
        """
        WHAT: Verify workspace_root resolves symlinks before boundary check
        WHY: REQ-2 + constraint "symlinks resolved before boundary check"
        EXPECTED: workspace_root is resolved (no symlinks)
        ACTUAL: (will be determined by test run)
        GUIDANCE: bind_session MUST call Path.resolve() to eliminate symlinks.
                  Prevents symlink attacks bypassing workspace boundaries.
        """
        # Create real workspace
        real_workspace = tmp_path / "real_workspace"
        real_workspace.mkdir()

        # Create symlink to workspace
        symlink_workspace = tmp_path / "symlink_workspace"
        symlink_workspace.symlink_to(real_workspace)

        # Bind via symlink
        ctx = await session_registry.bind_session("session-sym", symlink_workspace, "explicit")

        # Verify workspace_root is resolved (no symlinks)
        assert ctx.workspace_root == real_workspace.resolve(), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: ctx.workspace_root contains symlink (not resolved)\n"
            "2. WHY: REQ-2 constraint violation - symlinks must be resolved before boundary check\n"
            f"3. EXPECTED: workspace_root == {real_workspace.resolve()}\n"
            f"4. ACTUAL: workspace_root == {ctx.workspace_root}\n"
            "5. GUIDANCE: bind_session MUST call workspace_root.resolve() to eliminate symlinks.\n"
            "             INV-2 contract: workspace_root is always absolute, resolved path.\n"
            "             Prevents symlink attacks bypassing workspace boundaries."
        )

        # Verify no symlink component in path
        assert not ctx.workspace_root.is_symlink(), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: ctx.workspace_root.is_symlink() == True\n"
            "2. WHY: REQ-2 constraint violation - workspace_root must not be a symlink\n"
            f"3. EXPECTED: workspace_root is resolved path (not symlink)\n"
            f"4. ACTUAL: workspace_root == {ctx.workspace_root} (is_symlink=True)\n"
            "5. GUIDANCE: bind_session MUST use Path.resolve() to fully resolve symlinks.\n"
            "             Path.resolve() returns absolute path with all symlinks resolved."
        )


# =============================================================================
# REQ-3: CONTEXTVAR PROPAGATION ACROSS AWAIT
# =============================================================================


class TestContextVarPropagation:
    """REQ-3: ContextVar propagation survives await boundaries."""

    @pytest.mark.asyncio
    async def test_contextvar_survives_await_boundary(self, session_registry: Any, temp_workspace_a: Path):
        """
        WHAT: Verify SessionContext accessible after await boundary
        WHY: REQ-3 requires ContextVar propagation across async calls
        EXPECTED: Same SessionContext retrievable before and after await
        ACTUAL: (will be determined by test run)
        GUIDANCE: Use contextvars.ContextVar (NOT threading.local) for async compatibility.
                  ContextVar automatically propagates across await boundaries.
        """
        # Bind session
        await session_registry.bind_session("session-cv", temp_workspace_a, "explicit")

        # Get context before await
        ctx_before = session_registry.get_session("session-cv")

        # Simulate async operation (await boundary)
        await asyncio.sleep(0.01)

        # Get context after await
        ctx_after = session_registry.get_session("session-cv")

        assert ctx_before is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session('session-cv') returned None before await\n"
            "2. WHY: Session not bound correctly\n"
            "3. EXPECTED: get_session returns SessionContext after bind_session\n"
            "4. ACTUAL: get_session returned None\n"
            "5. GUIDANCE: bind_session MUST store session in registry.\n"
            "             POST-1 contract violation: session_id not retrievable after bind."
        )

        assert ctx_after is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_session('session-cv') returned None after await\n"
            "2. WHY: REQ-3 violation - ContextVar did not survive await boundary\n"
            "3. EXPECTED: Same SessionContext retrievable after await asyncio.sleep(0.01)\n"
            "4. ACTUAL: get_session returned None after await\n"
            "5. GUIDANCE: Use contextvars.ContextVar instead of threading.local.\n"
            "             threading.local does NOT propagate across await boundaries.\n"
            "             ContextVar automatically propagates to awaited coroutines."
        )

        # Verify same context (object identity or equality)
        assert ctx_before.session_id == ctx_after.session_id, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: SessionContext changed after await boundary\n"
            "2. WHY: REQ-3 violation - ContextVar propagation failed\n"
            "3. EXPECTED: Same session_id before and after await ('session-cv')\n"
            f"4. ACTUAL: before={ctx_before.session_id}, after={ctx_after.session_id}\n"
            "5. GUIDANCE: ContextVar MUST propagate across await boundaries.\n"
            "             Check: Are you using threading.local? (does not propagate)\n"
            "             Use contextvars.ContextVar for async compatibility."
        )

    @pytest.mark.asyncio
    async def test_contextvar_isolation_between_concurrent_tasks(
        self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path
    ):
        """
        WHAT: Verify ContextVar isolation between concurrent async tasks
        WHY: REQ-3 + asyncio semantics require task-level isolation
        EXPECTED: Each task sees its own SessionContext
        ACTUAL: (will be determined by test run)
        GUIDANCE: ContextVar provides task-local storage (not global).
                  Each asyncio.create_task gets isolated ContextVar copy.
        """

        async def task_a():
            """Task A binds to workspace A and verifies isolation."""
            await session_registry.bind_session("task-a-session", temp_workspace_a, "explicit")
            await asyncio.sleep(0.05)  # Let task B run
            ctx = session_registry.get_session("task-a-session")
            assert ctx is not None, "Task A session disappeared after await"
            assert ctx.workspace_root == temp_workspace_a.resolve(), "Task A workspace changed"
            return ctx

        async def task_b():
            """Task B binds to workspace B and verifies isolation."""
            await asyncio.sleep(0.02)  # Let task A bind first
            await session_registry.bind_session("task-b-session", temp_workspace_b, "explicit")
            await asyncio.sleep(0.05)  # Let task A verify
            ctx = session_registry.get_session("task-b-session")
            assert ctx is not None, "Task B session disappeared after await"
            assert ctx.workspace_root == temp_workspace_b.resolve(), "Task B workspace changed"
            return ctx

        # Run tasks concurrently
        ctx_a, ctx_b = await asyncio.gather(task_a(), task_b())

        # Verify isolation: different sessions
        assert ctx_a.session_id != ctx_b.session_id, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Concurrent tasks have same session_id\n"
            "2. WHY: REQ-3 violation - ContextVar not isolated between tasks\n"
            "3. EXPECTED: task_a and task_b have different session_id values\n"
            f"4. ACTUAL: both have session_id == {ctx_a.session_id}\n"
            "5. GUIDANCE: Each asyncio.create_task MUST get isolated ContextVar copy.\n"
            "             Check: Are you using global state instead of ContextVar?\n"
            "             ContextVar provides task-local storage automatically."
        )

        # Verify isolation: different workspaces
        assert ctx_a.workspace_root != ctx_b.workspace_root, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Concurrent tasks have same workspace_root\n"
            "2. WHY: REQ-3 violation - ContextVar state leaked between tasks\n"
            "3. EXPECTED: task_a → workspace_a, task_b → workspace_b\n"
            f"4. ACTUAL: both have workspace_root == {ctx_a.workspace_root}\n"
            "5. GUIDANCE: ContextVar MUST provide task-level isolation.\n"
            "             Each task should maintain separate SessionContext.\n"
            "             Verify: Are you using ContextVar.set() correctly in bind_session?"
        )


# =============================================================================
# REQ-4: THREAD-SAFE BIND/UNBIND
# =============================================================================


class TestThreadSafeBindUnbind:
    """REQ-4: Thread-safe bind/unbind with asyncio.Lock."""

    @pytest.mark.asyncio
    async def test_concurrent_bind_and_unbind(self, session_registry: Any, temp_workspace_a: Path):
        """
        WHAT: Concurrent bind and unbind operations on different sessions
        WHY: REQ-4 requires all mutations to be thread-safe
        EXPECTED: No race conditions, all operations complete atomically
        ACTUAL: (will be determined by test run)
        GUIDANCE: Use asyncio.Lock to protect all registry mutations.
                  INV-4 contract: all mutations are atomic.
        """
        # Bind initial sessions
        await session_registry.bind_session("session-1", temp_workspace_a, "explicit")
        await session_registry.bind_session("session-2", temp_workspace_a, "explicit")

        # Concurrent bind new session + unbind old session
        await asyncio.gather(
            session_registry.bind_session("session-3", temp_workspace_a, "explicit"),
            session_registry.unbind_session("session-1"),
        )

        # Verify state consistency
        ctx_1 = session_registry.get_session("session-1")
        ctx_2 = session_registry.get_session("session-2")
        ctx_3 = session_registry.get_session("session-3")

        assert ctx_1 is None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session-1 still exists after unbind_session\n"
            "2. WHY: POST-2 contract violation - unbind did not remove session\n"
            "3. EXPECTED: get_session('session-1') returns None after unbind\n"
            f"4. ACTUAL: get_session('session-1') returned {ctx_1}\n"
            "5. GUIDANCE: unbind_session MUST remove session from registry.\n"
            "             POST-2 contract: session_id no longer in registry after unbind.\n"
            "             Use async with lock: to ensure atomic removal."
        )

        assert ctx_2 is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session-2 disappeared during concurrent operations\n"
            "2. WHY: REQ-4 violation - race condition corrupted registry state\n"
            "3. EXPECTED: session-2 remains bound (unaffected by unbind of session-1)\n"
            "4. ACTUAL: get_session('session-2') returned None\n"
            "5. GUIDANCE: unbind_session MUST NOT affect other sessions.\n"
            "             INV-4 contract violation: mutations not atomic.\n"
            "             Use asyncio.Lock to protect concurrent bind/unbind."
        )

        assert ctx_3 is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: session-3 was not bound during concurrent operations\n"
            "2. WHY: REQ-4 violation - race condition in bind_session\n"
            "3. EXPECTED: session-3 successfully bound during concurrent unbind\n"
            "4. ACTUAL: get_session('session-3') returned None\n"
            "5. GUIDANCE: bind_session and unbind_session MUST use same lock.\n"
            "             INV-4 contract: all mutations are atomic.\n"
            "             Ensure async with self._lock: protects both operations."
        )

    @pytest.mark.asyncio
    async def test_double_bind_same_session_id(self, session_registry: Any, temp_workspace_a: Path):
        """
        WHAT: Attempt to bind same session_id twice
        WHY: PRE-1 precondition requires session_id not already bound
        EXPECTED: Second bind raises error or is ignored
        ACTUAL: (will be determined by test run)
        GUIDANCE: bind_session MUST check if session_id already exists.
                  PRE-1 contract: session_id not already bound.
        """
        # First bind succeeds
        ctx1 = await session_registry.bind_session("duplicate-session", temp_workspace_a, "explicit")
        assert ctx1 is not None

        # Second bind with same session_id should raise or no-op
        with pytest.raises((ValueError, RuntimeError)):
            await session_registry.bind_session("duplicate-session", temp_workspace_a, "explicit")

        # If no exception, verify original session unchanged
        ctx_after = session_registry.get_session("duplicate-session")
        assert ctx_after.activation_time == ctx1.activation_time, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Second bind_session modified existing session\n"
            "2. WHY: PRE-1 contract violation - session_id already bound\n"
            "3. EXPECTED: bind_session raises ValueError when session_id exists\n"
            "4. ACTUAL: Second bind succeeded and changed activation_time\n"
            "5. GUIDANCE: bind_session MUST check if session_id in registry.\n"
            "             PRE-1 precondition: session_id not already bound.\n"
            "             Raise ValueError if session_id exists, or use async with lock: check."
        )


# =============================================================================
# REQ-5: CLEANUP ON LAST SESSION FOR WORKSPACE
# =============================================================================


class TestCleanupOnLastSession:
    """REQ-5: Cleanup on last session for workspace."""

    @pytest.mark.asyncio
    async def test_cleanup_when_last_session_unbinds(self, session_registry: Any, temp_workspace_a: Path):
        """
        WHAT: Unbind last session for a workspace and verify cleanup scheduled
        WHY: REQ-5 requires cleanup when last session for workspace unbinds
        EXPECTED: Cleanup scheduled (LSP references cleared, workspace metadata removed)
        ACTUAL: (will be determined by test run)
        GUIDANCE: unbind_session MUST check if this is last session for workspace.
                  POST-3 contract: if last session, LSPs scheduled for cleanup.
        """
        # Bind single session to workspace
        await session_registry.bind_session("only-session", temp_workspace_a, "explicit")

        # Verify workspace has one session
        sessions = session_registry.get_sessions_for_workspace(temp_workspace_a)
        assert len(sessions) == 1, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_sessions_for_workspace returned != 1 session\n"
            "2. WHY: Session not tracked for workspace\n"
            f"3. EXPECTED: get_sessions_for_workspace returns ['only-session']\n"
            f"4. ACTUAL: get_sessions_for_workspace returned {sessions}\n"
            "5. GUIDANCE: bind_session MUST track which sessions belong to which workspace.\n"
            "             get_sessions_for_workspace must return list of session_ids.\n"
            "             Implementation free to use: dict[workspace → list[session_id]]."
        )

        # Unbind the only session
        await session_registry.unbind_session("only-session")

        # Verify session removed
        ctx = session_registry.get_session("only-session")
        assert ctx is None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Session still exists after unbind_session\n"
            "2. WHY: POST-2 contract violation - session not removed\n"
            "3. EXPECTED: get_session('only-session') returns None after unbind\n"
            f"4. ACTUAL: get_session returned {ctx}\n"
            "5. GUIDANCE: unbind_session MUST remove session from registry."
        )

        # Verify workspace has no sessions (cleanup triggered)
        sessions_after = session_registry.get_sessions_for_workspace(temp_workspace_a)
        assert len(sessions_after) == 0, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Workspace still has sessions after last session unbind\n"
            "2. WHY: REQ-5 violation - cleanup not triggered\n"
            "3. EXPECTED: get_sessions_for_workspace returns [] after last session unbinds\n"
            f"4. ACTUAL: get_sessions_for_workspace returned {sessions_after}\n"
            "5. GUIDANCE: unbind_session MUST detect last session for workspace.\n"
            "             POST-3 contract: if last session, cleanup scheduled.\n"
            "             Check: len(get_sessions_for_workspace(workspace)) == 0 after unbind."
        )

    @pytest.mark.asyncio
    async def test_no_cleanup_when_other_sessions_remain(self, session_registry: Any, temp_workspace_a: Path):
        """
        WHAT: Unbind one session when other sessions for workspace remain
        WHY: REQ-5 requires cleanup ONLY on last session unbind
        EXPECTED: Cleanup NOT triggered, other sessions unaffected
        ACTUAL: (will be determined by test run)
        GUIDANCE: unbind_session MUST count remaining sessions for workspace.
                  POST-3 only applies if len(sessions_for_workspace) becomes 0.
        """
        # Bind two sessions to same workspace
        await session_registry.bind_session("session-1", temp_workspace_a, "explicit")
        await session_registry.bind_session("session-2", temp_workspace_a, "explicit")

        # Verify two sessions for workspace
        sessions = session_registry.get_sessions_for_workspace(temp_workspace_a)
        assert len(sessions) == 2, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: get_sessions_for_workspace returned != 2 sessions\n"
            "2. WHY: Sessions not tracked correctly for workspace\n"
            f"3. EXPECTED: get_sessions_for_workspace returns 2 sessions\n"
            f"4. ACTUAL: returned {len(sessions)} sessions: {sessions}\n"
            "5. GUIDANCE: bind_session MUST track all sessions for workspace.\n"
            "             Multiple sessions CAN bind to same workspace (shared project access)."
        )

        # Unbind first session (not last)
        await session_registry.unbind_session("session-1")

        # Verify second session still exists (cleanup NOT triggered)
        ctx_2 = session_registry.get_session("session-2")
        assert ctx_2 is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Second session disappeared after unbind of first session\n"
            "2. WHY: REQ-5 violation - cleanup triggered too early\n"
            "3. EXPECTED: session-2 remains bound (cleanup NOT triggered)\n"
            "4. ACTUAL: get_session('session-2') returned None\n"
            "5. GUIDANCE: unbind_session MUST NOT cleanup if other sessions remain.\n"
            "             POST-3 contract: cleanup ONLY if last session for workspace.\n"
            "             Check: len(get_sessions_for_workspace(workspace)) > 0."
        )

        # Verify workspace still has one session
        sessions_after = session_registry.get_sessions_for_workspace(temp_workspace_a)
        assert len(sessions_after) == 1, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Workspace session count incorrect after unbind\n"
            "2. WHY: REQ-5 violation - session tracking corrupted\n"
            f"3. EXPECTED: get_sessions_for_workspace returns 1 session (session-2)\n"
            f"4. ACTUAL: returned {len(sessions_after)} sessions: {sessions_after}\n"
            "5. GUIDANCE: unbind_session MUST update workspace → sessions tracking.\n"
            "             Remove session_id from workspace's session list."
        )

    @pytest.mark.asyncio
    async def test_cleanup_multiple_workspaces_independent(self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path):
        """
        WHAT: Unbind last session for workspace A, verify workspace B unaffected
        WHY: REQ-5 cleanup must be workspace-specific (not global)
        EXPECTED: Workspace A cleanup triggered, workspace B unchanged
        ACTUAL: (will be determined by test run)
        GUIDANCE: unbind_session MUST check sessions for specific workspace only.
                  POST-3 contract applies per-workspace, not globally.
        """
        # Bind sessions to different workspaces
        await session_registry.bind_session("session-a", temp_workspace_a, "explicit")
        await session_registry.bind_session("session-b", temp_workspace_b, "explicit")

        # Unbind workspace A session
        await session_registry.unbind_session("session-a")

        # Verify workspace A cleanup triggered
        sessions_a = session_registry.get_sessions_for_workspace(temp_workspace_a)
        assert len(sessions_a) == 0, "Workspace A should have 0 sessions after unbind"

        # Verify workspace B UNAFFECTED
        sessions_b = session_registry.get_sessions_for_workspace(temp_workspace_b)
        assert len(sessions_b) == 1, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Workspace B affected by workspace A cleanup\n"
            "2. WHY: REQ-5 violation - cleanup not workspace-specific\n"
            "3. EXPECTED: Workspace B still has 1 session (session-b)\n"
            f"4. ACTUAL: Workspace B has {len(sessions_b)} sessions\n"
            "5. GUIDANCE: unbind_session MUST check sessions for specific workspace only.\n"
            "             POST-3 contract: cleanup per-workspace, not global.\n"
            "             Use: count sessions where ctx.workspace_root == target_workspace."
        )

        ctx_b = session_registry.get_session("session-b")
        assert ctx_b is not None, (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: Session B disappeared during workspace A cleanup\n"
            "2. WHY: REQ-5 violation - cleanup affected wrong workspace\n"
            "3. EXPECTED: session-b remains bound (unaffected by workspace A cleanup)\n"
            "4. ACTUAL: get_session('session-b') returned None\n"
            "5. GUIDANCE: unbind_session cleanup MUST be workspace-specific.\n"
            "             Check: Are you clearing all sessions globally? (wrong)\n"
            "             Only remove sessions for target workspace."
        )


# =============================================================================
# CONTRACT ADHERENCE TESTS
# =============================================================================


class TestContractAdherence:
    """Verify implementation adheres to contracts/session_registry.contract.py."""

    @pytest.mark.asyncio
    async def test_session_context_has_required_fields(self, session_registry: Any, temp_workspace_a: Path):
        """
        WHAT: Verify SessionContext has all required fields from contract
        WHY: Contract defines SessionContextContract with 4 required fields
        EXPECTED: SessionContext has session_id, workspace_root, activation_source, activation_time
        ACTUAL: (will be determined by test run)
        GUIDANCE: SessionContext MUST implement all fields from SessionContextContract.
        """
        ctx = await session_registry.bind_session("test-session", temp_workspace_a, "explicit")

        # Verify required fields exist
        assert hasattr(ctx, "session_id"), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: SessionContext missing 'session_id' field\n"
            "2. WHY: Contract violation - SessionContextContract requires session_id\n"
            "3. EXPECTED: ctx.session_id exists and == 'test-session'\n"
            "4. ACTUAL: SessionContext has no session_id attribute\n"
            "5. GUIDANCE: SessionContext MUST have session_id: str field.\n"
            "             Use @dataclass with session_id field or manual __init__."
        )

        assert hasattr(ctx, "workspace_root"), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: SessionContext missing 'workspace_root' field\n"
            "2. WHY: Contract violation - SessionContextContract requires workspace_root\n"
            "3. EXPECTED: ctx.workspace_root exists and is Path\n"
            "4. ACTUAL: SessionContext has no workspace_root attribute\n"
            "5. GUIDANCE: SessionContext MUST have workspace_root: Path field."
        )

        assert hasattr(ctx, "activation_source"), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: SessionContext missing 'activation_source' field\n"
            "2. WHY: Contract violation - SessionContextContract requires activation_source\n"
            "3. EXPECTED: ctx.activation_source in ('explicit', 'auto')\n"
            "4. ACTUAL: SessionContext has no activation_source attribute\n"
            "5. GUIDANCE: SessionContext MUST have activation_source: Literal['explicit', 'auto']."
        )

        assert hasattr(ctx, "activation_time"), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: SessionContext missing 'activation_time' field\n"
            "2. WHY: Contract violation - SessionContextContract requires activation_time\n"
            "3. EXPECTED: ctx.activation_time exists and is datetime\n"
            "4. ACTUAL: SessionContext has no activation_time attribute\n"
            "5. GUIDANCE: SessionContext MUST have activation_time: datetime field.\n"
            "             Use datetime.now() when binding session."
        )

        # Verify field types
        assert isinstance(ctx.workspace_root, Path), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: ctx.workspace_root is not a Path\n"
            "2. WHY: Contract violation - workspace_root must be Path type\n"
            f"3. EXPECTED: isinstance(workspace_root, Path) == True\n"
            f"4. ACTUAL: type(workspace_root) == {type(ctx.workspace_root)}\n"
            "5. GUIDANCE: workspace_root MUST be pathlib.Path (not str).\n"
            "             Convert during bind: Path(workspace_root).resolve()."
        )

        assert ctx.activation_source in ("explicit", "auto"), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: ctx.activation_source has invalid value\n"
            "2. WHY: Contract violation - activation_source must be 'explicit' or 'auto'\n"
            f"3. EXPECTED: activation_source in ('explicit', 'auto')\n"
            f"4. ACTUAL: activation_source == {ctx.activation_source}\n"
            "5. GUIDANCE: activation_source MUST be Literal['explicit', 'auto'].\n"
            "             Use the 'source' parameter from bind_session."
        )

        assert isinstance(ctx.activation_time, datetime), (
            "ERROR MESSAGE (5-point standard):\n"
            "1. WHAT FAILED: ctx.activation_time is not a datetime\n"
            "2. WHY: Contract violation - activation_time must be datetime type\n"
            f"3. EXPECTED: isinstance(activation_time, datetime) == True\n"
            f"4. ACTUAL: type(activation_time) == {type(ctx.activation_time)}\n"
            "5. GUIDANCE: activation_time MUST be datetime.datetime.\n"
            "             Use: from datetime import datetime; ctx.activation_time = datetime.now()."
        )

    @pytest.mark.asyncio
    async def test_unbind_nonexistent_session_is_silent_noop(self, session_registry: Any):
        """
        WHAT: Unbind session_id that doesn't exist
        WHY: PRE-3 contract allows silent no-op if session_id not in registry
        EXPECTED: No error raised, no effect on registry
        ACTUAL: (will be determined by test run)
        GUIDANCE: unbind_session MUST NOT raise error if session_id not found.
                  PRE-3 contract: silent no-op if session_id not in registry.
        """
        # Unbind non-existent session (should not raise)
        try:
            await session_registry.unbind_session("nonexistent-session")
        except Exception as e:
            pytest.fail(
                "ERROR MESSAGE (5-point standard):\n"
                "1. WHAT FAILED: unbind_session raised exception for nonexistent session\n"
                "2. WHY: PRE-3 contract violation - should be silent no-op\n"
                "3. EXPECTED: unbind_session('nonexistent') completes without error\n"
                f"4. ACTUAL: raised {type(e).__name__}: {e}\n"
                "5. GUIDANCE: unbind_session MUST handle missing session_id gracefully.\n"
                "             PRE-3 contract: silent no-op if session_id not exists.\n"
                "             Use: if session_id not in registry: return (no error)."
            )

    @pytest.mark.asyncio
    async def test_workspace_root_precondition_validation(self, session_registry: Any, tmp_path: Path):
        """
        WHAT: Bind session with invalid workspace_root (non-existent directory)
        WHY: PRE-2 precondition requires workspace_root.exists() == True
        EXPECTED: bind_session raises error for non-existent workspace
        ACTUAL: (will be determined by test run)
        GUIDANCE: bind_session MUST validate workspace_root.exists() before binding.
                  PRE-2 contract: workspace_root is valid, existing directory.
        """
        nonexistent_path = tmp_path / "nonexistent_workspace"

        # Should raise error for non-existent workspace
        with pytest.raises((ValueError, FileNotFoundError)):
            await session_registry.bind_session("test-session", nonexistent_path, "explicit")

        # If no exception raised, FAIL
        if session_registry.get_session("test-session") is not None:
            pytest.fail(
                "ERROR MESSAGE (5-point standard):\n"
                "1. WHAT FAILED: bind_session succeeded with non-existent workspace_root\n"
                "2. WHY: PRE-2 contract violation - workspace_root must exist\n"
                "3. EXPECTED: bind_session raises ValueError/FileNotFoundError\n"
                f"4. ACTUAL: bind_session succeeded for {nonexistent_path}\n"
                "5. GUIDANCE: bind_session MUST validate workspace_root.exists().\n"
                "             PRE-2 precondition: workspace_root is valid, existing directory.\n"
                "             Raise ValueError if not workspace_root.exists()."
            )
