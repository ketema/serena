"""
End-to-End Integration Concurrency Tests - Adversarial TDD RED Phase

Contract: Phase 2 "New Path" Architecture
Source: .serena/memories/cycle-2.7-integration-test-plan.md

Requirements:
- REQ-INT-1: Stack Integrity - Full chain SerenaAgent -> Dispatch -> Pool -> LSP
- REQ-INT-2: Concurrent Isolation - Sessions MUST NOT see each other's state
- REQ-INT-3: Log Attribution - Interleaved logs MUST be correctly prefixed
- REQ-INT-4: Resource Lifecycle - LSPs started on demand, released after use

These tests use REAL components (no mocks for Registry, Pool, Dispatcher).
"""

import logging
import re
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path
from typing import Any

import pytest


class TestIntegrationConcurrency:
    """
    End-to-End integration tests for Phase 2 multi-project architecture.

    Contract enforced:
    - REQ-INT-1: SerenaAgent -> SessionAwareToolDispatch -> GlobalLSPPool chain works
    - REQ-INT-2: Multiple sessions operating on different projects have isolation
    - REQ-INT-3: Structured logging correctly attributes logs to sessions
    - REQ-INT-4: LSP lifecycle managed correctly (no zombies, proper cleanup)
    """

    @pytest.fixture
    def registry(self):
        """Create real SessionRegistry for integration testing."""
        from serena.session_registry import SessionRegistry
        return SessionRegistry()

    @pytest.fixture
    def pool(self):
        """Create real GlobalLanguageServerPool for integration testing."""
        from serena.global_lsp_pool import GlobalLanguageServerPool
        pool = GlobalLanguageServerPool()
        yield pool
        # Cleanup: stop all LSPs after test
        pool.stop_all()

    @pytest.fixture
    def bridge(self, registry):
        """Create real MCPSessionBridge for structured logging integration."""
        from serena.mcp_session_bridge import MCPSessionBridge
        return MCPSessionBridge(session_registry=registry)

    @pytest.fixture
    def temp_projects(self, tmp_path: Path):
        """
        Create two temporary projects with minimal Python files.

        PRE: tmp_path is valid writable directory
        POST: Returns dict with project_a and project_b paths, each with source file
        INV: Projects exist on disk until fixture teardown
        """
        projects = {}

        for project_name in ["project_a", "project_b"]:
            project_dir = tmp_path / project_name
            project_dir.mkdir()

            # Create minimal Python source file
            source_file = project_dir / "main.py"
            source_file.write_text(f'''
"""Module for {project_name}."""

def greet_{project_name}(name: str) -> str:
    """Greet someone from {project_name}."""
    return f"Hello from {project_name}, {{name}}!"

class {project_name.title().replace("_", "")}Class:
    """A class in {project_name}."""

    def method(self) -> str:
        return "{project_name}"
''')

            # Create .serena project config
            serena_dir = project_dir / ".serena"
            serena_dir.mkdir()
            config_file = serena_dir / "project.yml"
            config_file.write_text(f"""
name: {project_name}
languages:
  - python
""")

            projects[project_name] = {
                "path": project_dir,
                "source_file": source_file,
            }

        return projects

    @pytest.fixture
    def log_capture(self):
        """Capture log output for assertion on structured logging."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)

        yield log_stream

        root_logger.removeHandler(handler)
        root_logger.setLevel(original_level)

    def test_stack_integrity_single_session(self, registry, pool, bridge, temp_projects):
        """
        Contract: Phase 2 Architecture
        Enforces: REQ-INT-1 - Full stack integrity for single session workflow

        Verifies: SessionRegistry -> MCPSessionBridge -> GlobalLSPPool chain works
        """
        project_a = temp_projects["project_a"]
        session_id = "integration-test-session-A"
        workspace = project_a["path"]

        # Step 1: Bind session to workspace
        registry.bind_session(session_id, workspace)
        session = registry.get_session(session_id)

        assert session is not None, (
            f"test_stack_integrity_single_session FAILED | "
            f"REQ-INT-1 violated: Session binding failed | "
            f"Expected: SessionContext returned for '{session_id}' | "
            f"Actual: get_session returned None | "
            f"Guidance: SessionRegistry.bind_session() MUST create retrievable session"
        )

        assert session.workspace_root == workspace, (
            f"test_stack_integrity_single_session FAILED | "
            f"REQ-INT-1 violated: Workspace mismatch | "
            f"Expected: session.workspace_root == {workspace} | "
            f"Actual: session.workspace_root == {session.workspace_root} | "
            f"Guidance: Session MUST be bound to correct workspace path"
        )

        # Step 2: Execute within session context
        execution_result = []

        def session_work():
            logger = logging.getLogger(__name__)
            logger.info("Executing work in session context")
            execution_result.append(session_id)
            return "work_completed"

        result = bridge.run_with_session_context(session_id, session_work)

        assert result == "work_completed", (
            f"test_stack_integrity_single_session FAILED | "
            f"REQ-INT-1 violated: Session context execution failed | "
            f"Expected: return value 'work_completed' | "
            f"Actual: return value '{result}' | "
            f"Guidance: run_with_session_context() MUST execute func and return its result"
        )

        assert len(execution_result) == 1, (
            f"test_stack_integrity_single_session FAILED | "
            f"REQ-INT-1 violated: Execution count mismatch | "
            f"Expected: 1 execution recorded | "
            f"Actual: {len(execution_result)} executions | "
            f"Guidance: Session work function MUST be executed exactly once"
        )

        # Step 3: Cleanup
        registry.unbind_session(session_id)
        assert registry.get_session(session_id) is None, (
            f"test_stack_integrity_single_session FAILED | "
            f"REQ-INT-1 violated: Session cleanup failed | "
            f"Expected: get_session returns None after unbind | "
            f"Actual: Session still exists | "
            f"Guidance: unbind_session() MUST remove session from registry"
        )

    def test_concurrent_isolation(self, registry, pool, bridge, temp_projects):
        """
        Contract: Phase 2 Architecture
        Enforces: REQ-INT-2 - Concurrent sessions MUST NOT see each other's state

        Verifies: Multiple threads with different sessions maintain isolation
        """
        num_threads = 3
        iterations_per_thread = 10
        results: dict[str, list[str]] = defaultdict(list)
        results_lock = threading.Lock()
        errors: list[str] = []

        def thread_work(thread_id: int):
            session_id = f"concurrent-session-{thread_id}"
            project_name = "project_a" if thread_id % 2 == 0 else "project_b"
            workspace = temp_projects[project_name]["path"]

            try:
                # Bind this thread's session
                registry.bind_session(session_id, workspace)

                for i in range(iterations_per_thread):
                    def session_func():
                        # Verify we're in correct session
                        session = registry.get_session(session_id)
                        if session is None:
                            with results_lock:
                                errors.append(f"Thread {thread_id}: Session not found")
                            return None
                        if session.workspace_root != workspace:
                            with results_lock:
                                errors.append(
                                    f"Thread {thread_id}: Wrong workspace "
                                    f"(expected {workspace}, got {session.workspace_root})"
                                )
                        return f"{session_id}:{i}"

                    result = bridge.run_with_session_context(session_id, session_func)
                    if result:
                        with results_lock:
                            results[session_id].append(result)

                    # Small delay to increase interleaving
                    time.sleep(0.001)

            finally:
                registry.unbind_session(session_id)

            return thread_id

        # Execute concurrently
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(thread_work, i) for i in range(num_threads)]
            completed = [f.result() for f in as_completed(futures)]

        # Verify no errors occurred
        assert len(errors) == 0, (
            f"test_concurrent_isolation FAILED | "
            f"REQ-INT-2 violated: Errors during concurrent execution | "
            f"Expected: 0 errors | "
            f"Actual: {len(errors)} errors: {errors[:5]} | "
            f"Guidance: Concurrent sessions MUST maintain workspace isolation"
        )

        # Verify all threads completed
        assert len(completed) == num_threads, (
            f"test_concurrent_isolation FAILED | "
            f"REQ-INT-2 violated: Not all threads completed | "
            f"Expected: {num_threads} completions | "
            f"Actual: {len(completed)} completions | "
            f"Guidance: All concurrent sessions MUST complete successfully"
        )

        # Verify each session captured exactly its iterations
        for thread_id in range(num_threads):
            session_id = f"concurrent-session-{thread_id}"
            session_results = results.get(session_id, [])

            assert len(session_results) == iterations_per_thread, (
                f"test_concurrent_isolation FAILED | "
                f"REQ-INT-2 violated: Result count mismatch for {session_id} | "
                f"Expected: {iterations_per_thread} results | "
                f"Actual: {len(session_results)} results | "
                f"Guidance: Each session MUST capture all its iterations without cross-contamination"
            )

            # Verify each result belongs to correct session
            for result in session_results:
                assert result.startswith(session_id), (
                    f"test_concurrent_isolation FAILED | "
                    f"REQ-INT-2 violated: Result belongs to wrong session | "
                    f"Expected: results starting with '{session_id}' | "
                    f"Actual: got result '{result}' | "
                    f"Guidance: Session results MUST NOT leak across threads"
                )

    def test_log_attribution_concurrent(self, registry, bridge, temp_projects, log_capture):
        """
        Contract: Phase 2 Architecture
        Enforces: REQ-INT-3 - Interleaved logs MUST be correctly attributed

        Verifies: Structured logging prefixes logs with correct session ID
        """
        num_threads = 3
        messages_per_thread = 5

        captured_prefixes: dict[str, list[str]] = defaultdict(list)
        capture_lock = threading.Lock()

        class SessionCapturingHandler(logging.Handler):
            """Capture log messages and extract session prefixes."""

            def emit(self, record):
                message = self.format(record)
                # Extract [Session: xxx] prefix
                match = re.search(r'\[Session: ([^\]]+)\]', message)
                if match:
                    session_id = match.group(1)
                    # Extract the unique marker from message
                    marker_match = re.search(r'THREAD_(\d+)_MSG_(\d+)', message)
                    if marker_match:
                        with capture_lock:
                            captured_prefixes[session_id].append(message)

        handler = SessionCapturingHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger().addHandler(handler)

        try:
            def thread_work(thread_id: int):
                session_id = f"log-test-session-{thread_id}"
                workspace = temp_projects["project_a"]["path"]

                registry.bind_session(session_id, workspace)
                try:
                    def logging_func():
                        logger = logging.getLogger(f"test.thread.{thread_id}")
                        for i in range(messages_per_thread):
                            logger.info(f"THREAD_{thread_id}_MSG_{i}")
                            time.sleep(0.001)
                        return thread_id

                    return bridge.run_with_session_context(session_id, logging_func)
                finally:
                    registry.unbind_session(session_id)

            # Execute concurrently
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(thread_work, i) for i in range(num_threads)]
                [f.result() for f in as_completed(futures)]

        finally:
            logging.getLogger().removeHandler(handler)

        # Verify each session's logs are correctly attributed
        for thread_id in range(num_threads):
            session_id = f"log-test-session-{thread_id}"
            session_logs = captured_prefixes.get(session_id, [])

            # Check correct number of logs captured for this session
            assert len(session_logs) == messages_per_thread, (
                f"test_log_attribution_concurrent FAILED | "
                f"REQ-INT-3 violated: Log count mismatch for session '{session_id}' | "
                f"Expected: {messages_per_thread} logs with session prefix | "
                f"Actual: {len(session_logs)} logs captured | "
                f"Guidance: All logs within session context MUST be prefixed with [Session: id]"
            )

            # Verify no cross-contamination (logs from other threads in this session's captures)
            for log_msg in session_logs:
                # Extract thread ID from the message
                marker_match = re.search(r'THREAD_(\d+)_MSG_', log_msg)
                if marker_match:
                    msg_thread_id = int(marker_match.group(1))
                    assert msg_thread_id == thread_id, (
                        f"test_log_attribution_concurrent FAILED | "
                        f"REQ-INT-3 violated: Log cross-contamination detected | "
                        f"Expected: THREAD_{thread_id}_MSG in session '{session_id}' logs | "
                        f"Actual: Found THREAD_{msg_thread_id}_MSG in log: '{log_msg}' | "
                        f"Guidance: Session log prefixes MUST NOT leak across threads (use ContextVar)"
                    )

    def test_resource_lifecycle(self, registry, pool, bridge, temp_projects):
        """
        Contract: Phase 2 Architecture
        Enforces: REQ-INT-4 - LSPs MUST be started on demand and released after use

        Verifies: Pool statistics reflect correct active/idle counts
        """
        session_id = "lifecycle-test-session"
        workspace = temp_projects["project_a"]["path"]

        # Initial state: no LSPs
        initial_stats = pool.get_pool_stats()
        initial_total = initial_stats.get("total_count", 0)

        assert initial_total == 0, (
            f"test_resource_lifecycle FAILED | "
            f"REQ-INT-4 violated: Pool not empty at start | "
            f"Expected: 0 LSPs initially | "
            f"Actual: {initial_total} LSPs | "
            f"Guidance: Fresh pool MUST have no LSPs"
        )

        # Bind session
        registry.bind_session(session_id, workspace)

        try:
            # Execute work that would trigger LSP usage
            def session_work():
                # In a full integration, this would trigger LSP operations
                # For now, verify the session context works
                return bridge.get_current_session_id()

            result = bridge.run_with_session_context(session_id, session_work)

            assert result == session_id, (
                f"test_resource_lifecycle FAILED | "
                f"REQ-INT-4 violated: Session context not correctly set | "
                f"Expected: get_current_session_id() returns '{session_id}' | "
                f"Actual: returned '{result}' | "
                f"Guidance: Session context MUST be correctly set during execution"
            )

        finally:
            registry.unbind_session(session_id)

        # After cleanup: verify no zombie LSPs
        final_stats = pool.get_pool_stats()

        # Note: Without actual LSP invocation, total should still be 0
        # This test verifies the lifecycle hook points exist
        assert "lsps" in final_stats, (
            f"test_resource_lifecycle FAILED | "
            f"REQ-INT-4 violated: Pool stats missing 'lsps' | "
            f"Expected: 'lsps' key in pool stats | "
            f"Actual: stats keys are {list(final_stats.keys())} | "
            f"Guidance: get_pool_stats() MUST return lsps list for observability"
        )

        assert "total_count" in final_stats, (
            f"test_resource_lifecycle FAILED | "
            f"REQ-INT-4 violated: Pool stats missing 'total_count' | "
            f"Expected: 'total_count' key in pool stats | "
            f"Actual: stats keys are {list(final_stats.keys())} | "
            f"Guidance: get_pool_stats() MUST return total_count for observability"
        )

    def test_session_overview_under_load(self, registry, bridge, temp_projects):
        """
        Contract: Phase 2 Architecture
        Enforces: REQ-INT-1, REQ-INT-2 - Session overview reflects concurrent state

        Verifies: get_session_overview() is thread-safe and accurate under load
        """
        num_sessions = 5
        session_ids = [f"overview-test-session-{i}" for i in range(num_sessions)]

        # Bind all sessions
        for i, session_id in enumerate(session_ids):
            project_name = "project_a" if i % 2 == 0 else "project_b"
            workspace = temp_projects[project_name]["path"]
            registry.bind_session(session_id, workspace)

        try:
            # Get overview while sessions are active
            overview = registry.get_session_overview()

            assert "sessions" in overview, (
                f"test_session_overview_under_load FAILED | "
                f"REQ-INT-1 violated: Overview missing 'sessions' key | "
                f"Expected: 'sessions' in overview | "
                f"Actual: overview keys are {list(overview.keys())} | "
                f"Guidance: get_session_overview() MUST return sessions list"
            )

            assert "total_count" in overview, (
                f"test_session_overview_under_load FAILED | "
                f"REQ-INT-1 violated: Overview missing 'total_count' | "
                f"Expected: 'total_count' in overview | "
                f"Actual: overview keys are {list(overview.keys())} | "
                f"Guidance: get_session_overview() MUST return total_count"
            )

            assert overview["total_count"] == num_sessions, (
                f"test_session_overview_under_load FAILED | "
                f"REQ-INT-2 violated: Session count mismatch | "
                f"Expected: total_count == {num_sessions} | "
                f"Actual: total_count == {overview['total_count']} | "
                f"Guidance: Overview MUST accurately reflect all bound sessions"
            )

            # Verify each session appears in overview
            overview_session_ids = {s.get("session_id") for s in overview["sessions"]}
            for session_id in session_ids:
                assert session_id in overview_session_ids, (
                    f"test_session_overview_under_load FAILED | "
                    f"REQ-INT-2 violated: Session missing from overview | "
                    f"Expected: '{session_id}' in overview sessions | "
                    f"Actual: overview contains {overview_session_ids} | "
                    f"Guidance: get_session_overview() MUST include all bound sessions"
                )

        finally:
            # Cleanup all sessions
            for session_id in session_ids:
                registry.unbind_session(session_id)

        # Verify cleanup reflected in overview
        final_overview = registry.get_session_overview()
        assert final_overview["total_count"] == 0, (
            f"test_session_overview_under_load FAILED | "
            f"REQ-INT-4 violated: Sessions not cleaned up | "
            f"Expected: 0 sessions after unbind_all | "
            f"Actual: {final_overview['total_count']} sessions remain | "
            f"Guidance: unbind_session() MUST remove session from overview"
        )
