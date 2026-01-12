"""
Structured Logging Tests - Adversarial TDD RED Phase

Contract: MCPSessionBridge.run_with_session_context()
Source: .serena/memories/CONSTITUTIONAL-PLAN-cycle-2.6.md

These tests are BLIND to implementation. They test BEHAVIOR only.
"""

import logging
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import pytest


class TestStructuredLogging:
    """
    Tests for session-aware structured logging.

    Contract enforced:
    - POST: All LogRecords emitted by func MUST contain 'session_id' attribute
    - POST: Log format MUST include "[Session: {session_id}]" prefix
    - POST: On exit, logging context MUST be restored (Leak Prevention)
    - INV: Concurrency Safety - prefixes MUST NOT leak across threads/tasks
    - INV: Zero Side Effects - code outside context unprefixed
    """

    @pytest.fixture
    def bridge(self):
        """Create MCPSessionBridge instance for testing."""
        from serena.mcp_session_bridge import MCPSessionBridge
        from serena.session_registry import SessionRegistry

        # Create real SessionRegistry for integration testing
        registry = SessionRegistry()
        return MCPSessionBridge(session_registry=registry)

    @pytest.fixture
    def log_capture(self):
        """Capture log output for assertion."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        # Use a format that shows the session prefix if present
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)

        # Get root logger and add handler
        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)

        yield log_stream

        # Cleanup
        root_logger.removeHandler(handler)
        root_logger.setLevel(original_level)

    def test_logs_prefixed_for_session(self, bridge, log_capture):
        """
        Contract: MCPSessionBridge.run_with_session_context()
        Enforces: POST: Log format MUST include "[Session: {session_id}]" prefix
        """
        session_id = "test-session-ABC123"
        test_message = "Operation completed successfully"

        def logging_func():
            logger = logging.getLogger(__name__)
            logger.info(test_message)
            return "success"

        result = bridge.run_with_session_context(session_id, logging_func)

        log_output = log_capture.getvalue()
        expected_prefix = f"[Session: {session_id}]"

        assert expected_prefix in log_output, (
            f"test_logs_prefixed_for_session FAILED | "
            f"POST violation: Log format MUST include session prefix | "
            f"Expected: '{expected_prefix}' in log output | "
            f"Actual: log output was '{log_output.strip()}' | "
            f"Guidance: Logs emitted within session context MUST be prefixed with [Session: session_id]"
        )

        assert test_message in log_output, (
            f"test_logs_prefixed_for_session FAILED | "
            f"POST violation: Original message must be preserved | "
            f"Expected: '{test_message}' in log output | "
            f"Actual: log output was '{log_output.strip()}' | "
            f"Guidance: Session prefix MUST be added without losing original message content"
        )

    def test_logs_unprefixed_outside_session(self, bridge, log_capture):
        """
        Contract: MCPSessionBridge.run_with_session_context()
        Enforces: INV: Zero Side Effects - code outside context unprefixed
        """
        session_id = "test-session-XYZ789"
        outside_message_before = "Log BEFORE session context"
        outside_message_after = "Log AFTER session context"
        inside_message = "Log INSIDE session context"

        logger = logging.getLogger(__name__)

        # Log BEFORE entering session context
        logger.info(outside_message_before)
        before_output = log_capture.getvalue()
        log_capture.seek(0)
        log_capture.truncate(0)

        # Log INSIDE session context
        def logging_func():
            logger.info(inside_message)
            return "done"

        bridge.run_with_session_context(session_id, logging_func)
        inside_output = log_capture.getvalue()
        log_capture.seek(0)
        log_capture.truncate(0)

        # Log AFTER exiting session context
        logger.info(outside_message_after)
        after_output = log_capture.getvalue()

        session_prefix = f"[Session: {session_id}]"

        # BEFORE: Must NOT have session prefix
        assert session_prefix not in before_output, (
            f"test_logs_unprefixed_outside_session FAILED | "
            f"INV violation: Zero Side Effects - logs before context must be unprefixed | "
            f"Expected: No '{session_prefix}' in before-context logs | "
            f"Actual: before-context log was '{before_output.strip()}' | "
            f"Guidance: Session context MUST NOT affect logs emitted before entering context"
        )

        # INSIDE: MUST have session prefix
        assert session_prefix in inside_output, (
            f"test_logs_unprefixed_outside_session FAILED | "
            f"POST violation: Logs inside context MUST be prefixed | "
            f"Expected: '{session_prefix}' in inside-context logs | "
            f"Actual: inside-context log was '{inside_output.strip()}' | "
            f"Guidance: Logs emitted within session context MUST include session prefix"
        )

        # AFTER: Must NOT have session prefix
        assert session_prefix not in after_output, (
            f"test_logs_unprefixed_outside_session FAILED | "
            f"INV violation: Zero Side Effects - logs after context must be unprefixed | "
            f"Expected: No '{session_prefix}' in after-context logs | "
            f"Actual: after-context log was '{after_output.strip()}' | "
            f"Guidance: Session context MUST be fully restored on exit - no prefix leakage"
        )

    def test_cleanup_on_failure(self, bridge, log_capture):
        """
        Contract: MCPSessionBridge.run_with_session_context()
        Enforces: POST: On exit (success or failure), logging context MUST be restored
        """
        session_id = "test-session-FAIL456"
        after_failure_message = "Log AFTER exception was raised"

        logger = logging.getLogger(__name__)

        def failing_func():
            logger.info("About to fail")
            raise RuntimeError("Intentional test failure")

        # Execute and expect exception
        with pytest.raises(RuntimeError):
            bridge.run_with_session_context(session_id, failing_func)

        # Clear captured logs from inside context
        log_capture.seek(0)
        log_capture.truncate(0)

        # Log AFTER the failed context - MUST be unprefixed
        logger.info(after_failure_message)
        after_output = log_capture.getvalue()

        session_prefix = f"[Session: {session_id}]"

        assert session_prefix not in after_output, (
            f"test_cleanup_on_failure FAILED | "
            f"POST violation: Logging context MUST be restored even on exception | "
            f"Expected: No '{session_prefix}' in post-exception logs | "
            f"Actual: post-exception log was '{after_output.strip()}' | "
            f"Guidance: Implementation MUST use try...finally to ensure context cleanup on exception"
        )

    def test_concurrent_independence(self, bridge):
        """
        Contract: MCPSessionBridge.run_with_session_context()
        Enforces: INV: Concurrency Safety - prefixes MUST NOT leak across threads
        """
        num_threads = 3
        messages_per_thread = 10

        # Mapping: session_id -> list of captured log messages
        captured_logs: dict[str, list[str]] = defaultdict(list)
        capture_lock = threading.Lock()

        class ThreadCapturingHandler(logging.Handler):
            """Custom handler to capture logs with their session context."""

            def emit(self, record):
                # Extract session_id from the formatted message or record
                message = self.format(record)
                session_match = re.search(r'\[Session: ([^\]]+)\]', message)
                if session_match:
                    session_id = session_match.group(1)
                    with capture_lock:
                        captured_logs[session_id].append(message)

        # Setup capturing handler
        handler = ThreadCapturingHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter('%(message)s'))
        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)

        try:
            def thread_work(thread_id: int):
                session_id = f"thread-{thread_id}-session"
                logger = logging.getLogger(f"thread.{thread_id}")

                def logging_func():
                    for i in range(messages_per_thread):
                        unique_marker = f"THREAD_{thread_id}_MSG_{i}"
                        logger.info(unique_marker)
                        # Small delay to increase chance of interleaving
                        time.sleep(0.001)
                    return thread_id

                return bridge.run_with_session_context(session_id, logging_func)

            # Execute concurrently
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(thread_work, i) for i in range(num_threads)]
                results = [f.result() for f in futures]

            # Verify all threads completed
            assert len(results) == num_threads, (
                f"test_concurrent_independence FAILED | "
                f"Execution error: Not all threads completed | "
                f"Expected: {num_threads} results | "
                f"Actual: {len(results)} results | "
                f"Guidance: All concurrent session contexts must complete successfully"
            )

            # Verify each session captured exactly its own messages
            for thread_id in range(num_threads):
                session_id = f"thread-{thread_id}-session"
                session_logs = captured_logs.get(session_id, [])

                # Check count
                assert len(session_logs) == messages_per_thread, (
                    f"test_concurrent_independence FAILED | "
                    f"INV violation: Concurrency Safety - message count mismatch | "
                    f"Expected: {messages_per_thread} logs for session '{session_id}' | "
                    f"Actual: {len(session_logs)} logs captured | "
                    f"Guidance: Each session context MUST capture exactly its own messages, no cross-contamination"
                )

                # Check that each message belongs to correct thread
                for i in range(messages_per_thread):
                    expected_marker = f"THREAD_{thread_id}_MSG_{i}"
                    found = any(expected_marker in log for log in session_logs)
                    assert found, (
                        f"test_concurrent_independence FAILED | "
                        f"INV violation: Concurrency Safety - message attribution error | "
                        f"Expected: '{expected_marker}' in session '{session_id}' logs | "
                        f"Actual: Message not found in session logs | "
                        f"Guidance: Session prefixes MUST NOT leak across threads - use ContextVar not threading.local"
                    )

                # Check NO messages from other threads leaked into this session
                for other_thread_id in range(num_threads):
                    if other_thread_id != thread_id:
                        for log in session_logs:
                            other_marker = f"THREAD_{other_thread_id}_MSG_"
                            assert other_marker not in log, (
                                f"test_concurrent_independence FAILED | "
                                f"INV violation: Concurrency Safety - cross-thread contamination | "
                                f"Expected: No THREAD_{other_thread_id} messages in session '{session_id}' | "
                                f"Actual: Found '{log}' containing other thread's marker | "
                                f"Guidance: ContextVar isolation MUST prevent cross-thread prefix leakage"
                            )

        finally:
            # Cleanup
            root_logger.removeHandler(handler)
            root_logger.setLevel(original_level)

    def test_nested_session_restoration(self, bridge, log_capture):
        """
        Contract: MCPSessionBridge.run_with_session_context()
        Enforces: POST: Logging context MUST be restored to previous state on exit
        """
        session_a = "outer-session-A"
        session_b = "inner-session-B"

        logger = logging.getLogger(__name__)

        logs_in_a_before_b: list[str] = []
        logs_in_b: list[str] = []
        logs_in_a_after_b: list[str] = []

        def outer_func():
            # Log in session A (before entering B)
            logger.info("MSG_A_BEFORE_B")
            logs_in_a_before_b.append(log_capture.getvalue())
            log_capture.seek(0)
            log_capture.truncate(0)

            # Enter nested session B
            def inner_func():
                logger.info("MSG_B_INSIDE")
                logs_in_b.append(log_capture.getvalue())
                log_capture.seek(0)
                log_capture.truncate(0)
                return "inner_done"

            bridge.run_with_session_context(session_b, inner_func)

            # Log in session A (after exiting B) - MUST be back to A's prefix
            logger.info("MSG_A_AFTER_B")
            logs_in_a_after_b.append(log_capture.getvalue())

            return "outer_done"

        result = bridge.run_with_session_context(session_a, outer_func)

        prefix_a = f"[Session: {session_a}]"
        prefix_b = f"[Session: {session_b}]"

        # Logs in A (before B): MUST have prefix A, NOT prefix B
        assert len(logs_in_a_before_b) == 1, "Expected one log capture before B"
        log_a_before = logs_in_a_before_b[0]
        assert prefix_a in log_a_before, (
            f"test_nested_session_restoration FAILED | "
            f"POST violation: Outer session logs must have outer prefix | "
            f"Expected: '{prefix_a}' in log before entering inner session | "
            f"Actual: log was '{log_a_before.strip()}' | "
            f"Guidance: Outer session context MUST be active before entering nested session"
        )
        assert prefix_b not in log_a_before, (
            f"test_nested_session_restoration FAILED | "
            f"POST violation: Outer session logs must NOT have inner prefix | "
            f"Expected: No '{prefix_b}' in log before entering inner session | "
            f"Actual: log was '{log_a_before.strip()}' | "
            f"Guidance: Inner session prefix MUST NOT leak backwards in time"
        )

        # Logs in B: MUST have prefix B, NOT prefix A
        assert len(logs_in_b) == 1, "Expected one log capture in B"
        log_b = logs_in_b[0]
        assert prefix_b in log_b, (
            f"test_nested_session_restoration FAILED | "
            f"POST violation: Inner session logs must have inner prefix | "
            f"Expected: '{prefix_b}' in log inside inner session | "
            f"Actual: log was '{log_b.strip()}' | "
            f"Guidance: Nested session context MUST override outer session prefix"
        )

        # Logs in A (after B): MUST have prefix A, NOT prefix B
        assert len(logs_in_a_after_b) == 1, "Expected one log capture after B"
        log_a_after = logs_in_a_after_b[0]
        assert prefix_a in log_a_after, (
            f"test_nested_session_restoration FAILED | "
            f"POST violation: Outer session prefix MUST be restored after inner session exit | "
            f"Expected: '{prefix_a}' in log after exiting inner session | "
            f"Actual: log was '{log_a_after.strip()}' | "
            f"Guidance: Implementation MUST use token.reset() to restore previous ContextVar state"
        )
        assert prefix_b not in log_a_after, (
            f"test_nested_session_restoration FAILED | "
            f"POST violation: Inner session prefix MUST NOT persist after exit | "
            f"Expected: No '{prefix_b}' in log after exiting inner session | "
            f"Actual: log was '{log_a_after.strip()}' | "
            f"Guidance: Nested session context MUST be fully cleaned up on exit"
        )
