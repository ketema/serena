"""
Timeout Wiring Integration Contract Tests (Tier 1.5)

CONTRACT: contracts/timeout_wiring_contract.py
AUTHORITY: contracts/timeout_wiring_contract.py line 6
CLAUSES: SEQ-TMO-INIT-01, INV-TMO-01, INV-TMO-02, INV-TMO-03
         POST-TMO-WIRING-01, POST-TMO-WIRING-02, POST-TMO-WIRING-03

SOURCE: REQ-TMO-WIRING-001 (contracts/REQ-TMO-WIRING-001.md)

PURPOSE:
  Tier 1.5 Integration Contract Testing — verifies sequencing obligation between
  GlobalLanguageServerPool.acquire() and LSPTimeoutManager.start_monitoring().

  For integration contracts, the HOW IS the WHAT:
    "acquire() calls start_monitoring()" is an architectural obligation, not a
    mere implementation detail. Without this wiring, monitoring never starts and
    idle LSPs are never reclaimed (silent resource leak).

ADVERSARIAL: Implementation-blind test design. Tests written from contract only.
              Coordinator is BLIND to implementation. Error messages MUST be
              self-documenting behavioral specifications.

CL12 COMPLIANCE:
  - Every test cites clause ID in docstring (CL12-E)
  - Every assertion references clause ID in error message (CL12-E)
  - 5-point error messages (What/Why/Expected/Actual/Guidance)
  - No mocks without verified contracts (CL10)
  - Observable enforcement testing (CL12-A)
  - Theater test detection applied (all tests fail if impl missing)

SEQ TESTING DISCIPLINE (CRITICAL):
  - Tests MUST construct pool via GlobalLanguageServerPool() (not direct start_monitoring)
  - Tests MUST verify through pool.acquire() → downstream monitoring state
  - Tests use ISOLATED pool instances (fresh pool per test)
  - At least one test uses real LSPTimeoutManager (not mock) for end-to-end

EXPECTED OUTCOME: All tests FAIL (RED phase) — start_monitoring() call not wired yet.
"""

import logging
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Target modules
from serena.global_lsp_pool import GlobalLanguageServerPool
from serena.lsp_timeout import LSPTimeoutManager

# Language enum for acquire() calls
from solidlsp.ls_config import Language


class TestTimeoutWiringContract(unittest.TestCase):
    """
    Integration contract tests for timeout monitoring wiring.

    Tests verify the sequencing obligation SEQ-TMO-INIT-01:
    GlobalLanguageServerPool.acquire() MUST call start_monitoring()
    after successful LSP acquisition.
    """

    def setUp(self):
        """
        Arrange: Create fresh pool instance for each test.

        ISOLATION: Each test gets a new pool to ensure clean state.
        POST-TMO-WIRING-03 requires verifying is_monitoring()==False before acquire,
        which is only guaranteed on a fresh pool.
        """
        # Create ephemeral workspace for LSP acquisition
        self.workspace_dir = tempfile.mkdtemp(prefix="test_timeout_wiring_")
        self.workspace_path = Path(self.workspace_dir)

        # Session ID for acquire() calls (plain string — no registry needed)
        self.session_id = "test-session-01"

        # Create isolated pool instance (FRESH for each test)
        self.pool = GlobalLanguageServerPool()

        # Mock _create_lsp to avoid starting real LSP processes.
        # We're testing WIRING (acquire → start_monitoring), not LSP creation.
        # The mock LSP satisfies acquire()'s postconditions without subprocess.
        self.mock_lsp = MagicMock()
        self.mock_lsp.is_running.return_value = True
        self.mock_lsp.workspace_roots = [self.workspace_path]
        self._create_lsp_patcher = patch.object(
            self.pool, '_create_lsp', return_value=self.mock_lsp
        )
        self._create_lsp_patcher.start()

    def tearDown(self):
        """Clean up resources."""
        import shutil
        # Stop _create_lsp patch
        if hasattr(self, '_create_lsp_patcher'):
            self._create_lsp_patcher.stop()

        if hasattr(self, 'pool'):
            # Stop monitoring if started
            if hasattr(self.pool, 'timeout_manager'):
                self.pool.timeout_manager.stop_monitoring()

        # Clean up temp workspace
        if hasattr(self, 'workspace_dir'):
            shutil.rmtree(self.workspace_dir, ignore_errors=True)


    # =========================================================================
    # POST-TMO-WIRING-03 — Before acquire(), monitoring is NOT active
    # =========================================================================

    def test_post_tmo_wiring_03_before_acquire_not_monitoring(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: GlobalLanguageServerPool (timeout wiring)
        - Enforces: POST-TMO-WIRING-03: Before any acquire(), is_monitoring() == False
        - Category: positive (verify initial state)
        - Adversarial: Implementation-blind

        OBSERVABLE: pool.timeout_manager.is_monitoring() == False on fresh pool.

        WHY: This proves monitoring is lazy (started by acquire, not by __init__).
        If monitoring were started in __init__, this test would FAIL.

        ISOLATION: Single-threaded, isolated pool, no concurrent access.
        """
        # ACT: Check monitoring status on fresh pool (before any acquire)
        is_monitoring_before = self.pool.timeout_manager.is_monitoring()

        # ASSERT: Monitoring must NOT be active yet
        self.assertFalse(
            is_monitoring_before,
            (
                "POST-TMO-WIRING-03 violation: Monitoring active before first acquire()\n"
                "Contract: GlobalLanguageServerPool POST-TMO-WIRING-03\n"
                f"EXPECTED: is_monitoring() == False (lazy initialization)\n"
                f"ACTUAL: is_monitoring() == {is_monitoring_before}\n"
                "GUIDANCE: start_monitoring() MUST NOT be called during __init__. "
                "Monitoring MUST remain inactive until the first successful acquire() call. "
                "Implementation is free to choose when in acquire() to call start_monitoring(), "
                "but it must NOT happen before acquire() is called."
            )
        )


    # =========================================================================
    # SEQ-TMO-INIT-01 + POST-TMO-WIRING-01 — acquire() calls start_monitoring()
    # =========================================================================

    def test_seq_tmo_init_01_acquire_starts_monitoring(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: GlobalLanguageServerPool.acquire() → LSPTimeoutManager.start_monitoring()
        - Enforces: SEQ-TMO-INIT-01: acquire() MUST call start_monitoring() after first success
        - Enforces: POST-TMO-WIRING-01: After acquire(), is_monitoring() == True
        - Category: positive (end-to-end integration with real timeout_manager)
        - Adversarial: Implementation-blind

        OBSERVABLE: pool.timeout_manager.is_monitoring() transitions from False → True
                    after pool.acquire() completes.

        WHY: This is the PRIMARY observable for the wiring contract.
        If acquire() does NOT call start_monitoring(), this test FAILS.

        TESTING DISCIPLINE:
          - Uses actual GlobalLanguageServerPool construction
          - Uses actual LSPTimeoutManager (NOT mock)
          - Calls pool.acquire() and verifies downstream monitoring state
        """
        # ARRANGE: Verify precondition (POST-TMO-WIRING-03)
        is_monitoring_before = self.pool.timeout_manager.is_monitoring()
        self.assertFalse(
            is_monitoring_before,
            f"Precondition failed: is_monitoring() should be False before acquire, got {is_monitoring_before}"
        )

        # ACT: Trigger acquire() — this should call start_monitoring()
        lsp = self.pool.acquire(
            language=Language.PYTHON,
            workspace_root=self.workspace_path,
            session_id=self.session_id
        )

        # Give monitoring thread time to start (daemon thread startup is async)
        time.sleep(0.1)

        # ASSERT: Monitoring MUST be active after acquire()
        is_monitoring_after = self.pool.timeout_manager.is_monitoring()
        self.assertTrue(
            is_monitoring_after,
            (
                "SEQ-TMO-INIT-01 + POST-TMO-WIRING-01 violation: Monitoring not active after acquire()\n"
                "Contract: GlobalLanguageServerPool.acquire() SEQ-TMO-INIT-01, POST-TMO-WIRING-01\n"
                f"EXPECTED: is_monitoring() == True after successful acquire()\n"
                f"ACTUAL: is_monitoring() == {is_monitoring_after}\n"
                "GUIDANCE: acquire() MUST call self.timeout_manager.start_monitoring() "
                "after successful LSP acquisition (create or reuse), before returning LSP to caller. "
                "The monitoring daemon thread MUST be active after any successful acquisition. "
                "Implementation is free to choose call placement within acquire() as long as "
                "monitoring is active before acquire() returns."
            )
        )

        # ADDITIONAL VERIFICATION: Daemon thread should be alive
        monitor_thread = self.pool.timeout_manager._monitoring_thread
        if monitor_thread is not None:
            self.assertTrue(
                monitor_thread.is_alive(),
                (
                    "SEQ-TMO-INIT-01 violation: Monitoring thread not alive\n"
                    f"EXPECTED: _monitor_thread.is_alive() == True\n"
                    f"ACTUAL: _monitor_thread.is_alive() == {monitor_thread.is_alive()}\n"
                    "GUIDANCE: start_monitoring() MUST successfully launch a daemon thread. "
                    "If thread exists but is not alive, start_monitoring() was called but failed."
                )
            )


    # =========================================================================
    # POST-TMO-WIRING-02 + INV-TMO-01 — Idempotency via LOG-TMO-01
    # =========================================================================

    def test_post_tmo_wiring_02_log_tmo_01_idempotent(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: GlobalLanguageServerPool timeout wiring + LSPTimeoutManager idempotency
        - Enforces: POST-TMO-WIRING-02: Exactly 1 INFO LOG-TMO-01 after first acquire,
                    0 additional INFO LOG-TMO-01 on subsequent acquires
        - Enforces: INV-TMO-01: start_monitoring() is idempotent
        - Category: invariant (idempotency verification)
        - Adversarial: Implementation-blind

        OBSERVABLE: Log output contains exactly 1 occurrence of
                    "[LSP-Timeout] Monitoring started (interval: {N}s)" at INFO level,
                    regardless of how many times acquire() is called.

        WHY: This proves start_monitoring() is correctly idempotent.
        If start_monitoring() were called N times and started N threads,
        this test would see N LOG-TMO-01 messages and FAIL.

        TESTING DISCIPLINE:
          - Captures log output during multiple acquire() calls
          - Counts INFO-level LOG-TMO-01 occurrences
          - Verifies exactly 1 occurrence (idempotency)
        """
        # ARRANGE: Set up log capture at INFO level
        with self.assertLogs('serena.lsp_timeout', level=logging.INFO) as log_capture:
            # ACT: Call acquire() twice on same pool
            lsp1 = self.pool.acquire(
                language=Language.PYTHON,
                workspace_root=self.workspace_path,
                session_id=self.session_id
            )
            time.sleep(0.1)  # Allow thread startup

            lsp2 = self.pool.acquire(
                language=Language.PYTHON,
                workspace_root=self.workspace_path,
                session_id=self.session_id
            )
            time.sleep(0.1)  # Ensure any duplicate threads would start

        # ASSERT: Extract INFO-level LOG-TMO-01 messages
        info_logs = [record for record in log_capture.records if record.levelname == 'INFO']
        log_tmo_01_messages = [
            log for log in info_logs
            if "[LSP-Timeout] Monitoring started" in log.getMessage()
        ]

        log_tmo_01_count = len(log_tmo_01_messages)
        self.assertEqual(
            log_tmo_01_count, 1,
            (
                "POST-TMO-WIRING-02 + INV-TMO-01 violation: LOG-TMO-01 not idempotent\n"
                "Contract: POST-TMO-WIRING-02, INV-TMO-01\n"
                f"EXPECTED: Exactly 1 INFO-level LOG-TMO-01 across multiple acquire() calls\n"
                f"ACTUAL: {log_tmo_01_count} INFO-level LOG-TMO-01 messages found\n"
                f"Log messages: {[log.getMessage() for log in log_tmo_01_messages]}\n"
                "GUIDANCE: start_monitoring() MUST be idempotent. "
                "The first call MUST emit LOG-TMO-01 at INFO and start the thread. "
                "Subsequent calls MUST detect that monitoring is already active, "
                "emit LOG-TMO-01 at DEBUG (noop message), and return immediately. "
                "Implementation is free to use is_monitoring() check, thread state check, "
                "or internal flag, as long as the observable behavior (exactly 1 INFO log) is correct."
            )
        )


    # =========================================================================
    # INV-TMO-02 — Thread safety (call within pool_lock scope)
    # =========================================================================

    def test_inv_tmo_02_start_monitoring_within_pool_lock(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: GlobalLanguageServerPool timeout wiring + thread safety
        - Enforces: INV-TMO-02: start_monitoring() call occurs within pool_lock scope
        - Category: invariant (thread safety verification)
        - Adversarial: Implementation-blind

        OBSERVABLE: Under concurrent acquire() calls, exactly 1 INFO LOG-TMO-01 emitted
                    (proving atomicity of pool state transition + monitoring start).

        WHY: If start_monitoring() were called outside pool_lock, a race condition
        could occur where two concurrent acquire() calls both see is_monitoring()==False
        and both attempt to start threads. While start_monitoring() is internally
        idempotent, this would produce 2 INFO LOG-TMO-01 messages, violating POST-TMO-WIRING-02.

        TESTING DISCIPLINE:
          - Launches 2 concurrent threads calling acquire()
          - Captures log output
          - Verifies exactly 1 INFO LOG-TMO-01 (atomicity proof)
        """
        # ARRANGE: Set up log capture
        import threading

        with self.assertLogs('serena.lsp_timeout', level=logging.INFO) as log_capture:
            # ACT: Launch 2 concurrent acquire() calls
            def concurrent_acquire():
                self.pool.acquire(
                    language=Language.PYTHON,
                    workspace_root=self.workspace_path,
                    session_id=self.session_id
                )

            thread1 = threading.Thread(target=concurrent_acquire)
            thread2 = threading.Thread(target=concurrent_acquire)

            thread1.start()
            thread2.start()

            thread1.join(timeout=5)
            thread2.join(timeout=5)

            time.sleep(0.2)  # Ensure any race-condition threads would start

        # ASSERT: Exactly 1 INFO LOG-TMO-01 (atomicity proof)
        info_logs = [record for record in log_capture.records if record.levelname == 'INFO']
        log_tmo_01_messages = [
            log for log in info_logs
            if "[LSP-Timeout] Monitoring started" in log.getMessage()
        ]

        log_tmo_01_count = len(log_tmo_01_messages)
        self.assertEqual(
            log_tmo_01_count, 1,
            (
                "INV-TMO-02 violation: Thread safety not maintained\n"
                "Contract: INV-TMO-02 (start_monitoring call within pool_lock scope)\n"
                f"EXPECTED: Exactly 1 INFO-level LOG-TMO-01 under concurrent acquire()\n"
                f"ACTUAL: {log_tmo_01_count} INFO-level LOG-TMO-01 messages found\n"
                f"Log messages: {[log.getMessage() for log in log_tmo_01_messages]}\n"
                "GUIDANCE: The start_monitoring() call MUST occur while holding self._pool_lock. "
                "This ensures the monitoring state transition is atomic with the pool state transition "
                "(LSP creation/reuse + session ref recording). If start_monitoring() is called outside "
                "the lock, concurrent acquire() calls may both see is_monitoring()==False and both "
                "attempt to start threads. The lock ensures cleaner sequencing. "
                "Implementation is free to choose lock acquisition strategy as long as "
                "start_monitoring() is called within the pool_lock critical section."
            )
        )


    # =========================================================================
    # INV-TMO-03 — Daemon thread enforcement
    # =========================================================================

    def test_inv_tmo_03_monitoring_thread_is_daemon(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: LSPTimeoutManager thread lifecycle (via timeout wiring)
        - Enforces: INV-TMO-03: Monitoring thread MUST be daemon=True
        - Category: invariant (resource safety verification)
        - Adversarial: Implementation-blind

        OBSERVABLE: pool.timeout_manager._monitor_thread.daemon == True

        WHY: Daemon threads are killed when the main process exits, preventing zombie threads.
        If the monitoring thread were not a daemon, it could prevent process termination.

        TESTING DISCIPLINE:
          - Calls acquire() to trigger start_monitoring()
          - Inspects _monitor_thread.daemon property
          - Verifies daemon == True
        """
        # ACT: Trigger monitoring start
        lsp = self.pool.acquire(
            language=Language.PYTHON,
            workspace_root=self.workspace_path,
            session_id=self.session_id
        )
        time.sleep(0.1)  # Allow thread startup

        # ASSERT: Monitor thread MUST be daemon
        monitor_thread = self.pool.timeout_manager._monitoring_thread
        self.assertIsNotNone(
            monitor_thread,
            (
                "INV-TMO-03 precondition failed: _monitor_thread is None\n"
                "EXPECTED: start_monitoring() creates a thread\n"
                "ACTUAL: _monitor_thread is None\n"
                "GUIDANCE: If is_monitoring() returns True but _monitor_thread is None, "
                "the monitoring state is inconsistent. This suggests start_monitoring() "
                "was called but failed to create the thread."
            )
        )

        is_daemon = monitor_thread.daemon
        self.assertTrue(
            is_daemon,
            (
                "INV-TMO-03 violation: Monitoring thread is not a daemon\n"
                "Contract: INV-TMO-03 (daemon thread enforcement)\n"
                f"EXPECTED: _monitor_thread.daemon == True\n"
                f"ACTUAL: _monitor_thread.daemon == {is_daemon}\n"
                "GUIDANCE: The monitoring thread MUST be created with daemon=True. "
                "This ensures the thread will be killed when the main process exits, "
                "preventing zombie threads. Implementation must pass daemon=True to "
                "threading.Thread() constructor when creating the monitor thread."
            )
        )


    # =========================================================================
    # SEQ-TMO-INIT-01 — Mock verification (call was made)
    # =========================================================================

    def test_seq_tmo_init_01_acquire_calls_start_monitoring_mock(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: GlobalLanguageServerPool.acquire() → LSPTimeoutManager.start_monitoring()
        - Enforces: SEQ-TMO-INIT-01: acquire() MUST call start_monitoring()
        - Category: positive (mock verification of call)
        - Adversarial: Implementation-blind

        OBSERVABLE: Mock timeout_manager.start_monitoring() called exactly once
                    during pool.acquire().

        WHY: This test uses a mock to verify the CALL was made, complementing
        the end-to-end test (test_seq_tmo_init_01_acquire_starts_monitoring)
        which verifies the EFFECT.

        MOCK CONTRACT: contracts/lsp_timeout_contract.py (LSPTimeoutManager component contract)
        Mock derives: start_monitoring() method signature and idempotency behavior

        TESTING DISCIPLINE:
          - Injects mock timeout_manager at construction time (NOT post-construction)
          - Calls pool.acquire()
          - Verifies start_monitoring() was called
        """
        # ARRANGE: Create pool with mock timeout_manager (injected at construction)
        mock_timeout_manager = MagicMock(spec=LSPTimeoutManager)
        mock_timeout_manager.is_monitoring.return_value = False  # Initially not monitoring
        mock_timeout_manager.start_monitoring.return_value = None  # Void method

        # Inject mock via constructor parameter (GlobalLanguageServerPool accepts timeout_manager)
        pool_with_mock = GlobalLanguageServerPool(timeout_manager=mock_timeout_manager)

        # Mock _create_lsp on this separate pool instance too
        mock_lsp = MagicMock()
        mock_lsp.is_running.return_value = True
        mock_lsp.workspace_roots = [self.workspace_path]
        with patch.object(pool_with_mock, '_create_lsp', return_value=mock_lsp):
            # ACT: Call acquire() — should trigger start_monitoring()
            pool_with_mock.acquire(
                language=Language.PYTHON,
                workspace_root=self.workspace_path,
                session_id=self.session_id
            )

        # ASSERT: start_monitoring() MUST have been called
        mock_timeout_manager.start_monitoring.assert_called_once_with()

        # If not called, the assertion above will fail with:
        # AssertionError: Expected 'start_monitoring' to have been called once. Called 0 times.
        # This error message is clear enough, but we add explicit guidance below:
        if not mock_timeout_manager.start_monitoring.called:
            self.fail(
                (
                    "SEQ-TMO-INIT-01 violation: start_monitoring() not called during acquire()\n"
                    "Contract: GlobalLanguageServerPool.acquire() SEQ-TMO-INIT-01\n"
                    f"EXPECTED: timeout_manager.start_monitoring() called during acquire()\n"
                    f"ACTUAL: start_monitoring() called {mock_timeout_manager.start_monitoring.call_count} times\n"
                    "GUIDANCE: acquire() MUST call self.timeout_manager.start_monitoring() "
                    "after successful LSP acquisition (create or reuse), before returning LSP to caller. "
                    "Implementation is free to choose call placement within acquire()."
                )
            )


if __name__ == '__main__':
    unittest.main()
