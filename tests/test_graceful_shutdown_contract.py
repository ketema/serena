"""
Graceful Shutdown Integration Contract Tests (Tier 1.5)

CONTRACT: contracts/graceful_shutdown_contract.py
AUTHORITY: contracts/graceful_shutdown_contract.py line 6
CLAUSES: SEQ-SHUT-01, SEQ-SHUT-02, SEQ-SHUT-03, SEQ-SHUT-04,
         INV-SHUT-01, INV-SHUT-02, INV-SHUT-03, INV-SHUT-04,
         POST-SHUT-01, POST-SHUT-02, POST-SHUT-03, POST-SHUT-04,
         ERR-SHUT-01, ERR-SHUT-02

SOURCE: REQ-GRACEFUL-SHUTDOWN-001 (contracts/REQ-GRACEFUL-SHUTDOWN-001.md)

PURPOSE:
  Tier 1.5 Integration Contract Testing — verifies the cleanup chain wiring:
    SIGTERM → agent.shutdown() → stop_all(save_cache=True) → stop_monitoring()

  For integration contracts, the HOW IS the WHAT:
    "shutdown() calls stop_all()" is an architectural obligation, not a mere
    implementation detail. Without this wiring, LSP subprocesses orphan on restart.

ADVERSARIAL: Implementation-blind test design. Tests written from contract only.
              Coordinator is BLIND to implementation. Error messages MUST be
              self-documenting behavioral specifications.

CL12 COMPLIANCE:
  - Every test cites clause ID in docstring (CL12-E)
  - Every assertion references clause ID in error message (CL12-E)
  - 5-point error messages (What/Why/Expected/Actual/Guidance)
  - No mocks without verified contracts (CL10)
  - Observable enforcement testing (CL12-A)
  - Theater test detection applied (all tests fail if wiring missing)

SEQ TESTING DISCIPLINE (CRITICAL):
  - SEQ-SHUT-01/04: Test through start_mcp_server() → verify signal/atexit registration
  - SEQ-SHUT-02: Test through agent.shutdown() → verify stop_all() called
  - SEQ-SHUT-03: Test through pool.stop_all() → verify stop_monitoring() called
  - Use constructor injection for dependencies (pool, timeout_manager)
  - NO post-construction replacement of dependencies (theater test characteristic #5)
  - NO direct component calls bypassing integration paths (theater test characteristic #6)

EXPECTED OUTCOME: All tests FAIL (RED phase) — cleanup chain not wired yet.
"""

import logging
import signal
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Target modules
from serena.agent import SerenaAgent
from serena.global_lsp_pool import GlobalLanguageServerPool
from serena.lsp_timeout import LSPTimeoutManager

# Language enum for pool key construction
from solidlsp.ls_config import Language


class TestGracefulShutdownContract(unittest.TestCase):
    """
    Integration contract tests for graceful LSP shutdown on server restart.

    Tests verify the cleanup chain sequencing obligations:
      SEQ-SHUT-01: SIGTERM handler → agent.shutdown()
      SEQ-SHUT-02: shutdown() → lsp_pool.stop_all(save_cache=True)
      SEQ-SHUT-03: stop_all() → timeout_manager.stop_monitoring()
      SEQ-SHUT-04: atexit.register() → agent.shutdown()
    """

    def setUp(self):
        """
        Arrange: Create fresh components for each test.

        ISOLATION: Each test gets new agent, pool, timeout_manager instances
        to ensure clean state and prevent cross-test contamination.
        """
        # Create ephemeral workspace for LSP acquisition
        self.workspace_dir = tempfile.mkdtemp(prefix="test_graceful_shutdown_")
        self.workspace_path = Path(self.workspace_dir)

        # Session ID for acquire() calls
        self.session_id = "test-shutdown-session"

    def tearDown(self):
        """Clean up resources."""
        import shutil

        # Clean up temp workspace
        if hasattr(self, 'workspace_dir'):
            shutil.rmtree(self.workspace_dir, ignore_errors=True)


    # =========================================================================
    # SEQ-SHUT-01 — SIGTERM handler in start_mcp_server() → agent.shutdown()
    # =========================================================================

    def test_seq_shut_01_sigterm_handler_calls_shutdown(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: SEQ-SHUT-01: start_mcp_server() MUST register SIGTERM handler
                    that calls agent.shutdown()
        - Category: positive (signal handler registration)
        - Adversarial: Implementation-blind

        OBSERVABLE: After start_mcp_server() initialization:
                    - signal.getsignal(SIGTERM) returns a callable (not SIG_DFL)
                    - Handler invokes agent.shutdown() when triggered

        TESTING DISCIPLINE:
          - Mock agent.shutdown to verify CALL was made
          - Use signal.getsignal() to verify registration
          - DO NOT send actual signals (use handler introspection)
        """
        # Import here to avoid premature module loading
        from click.testing import CliRunner
        from serena.cli import TopLevelCommands

        # ARRANGE: Save original SIGTERM handler to restore later
        original_handler = signal.getsignal(signal.SIGTERM)

        # Mock the server factory and run to prevent actual server startup
        mock_agent = MagicMock(spec=SerenaAgent)
        mock_agent.shutdown = MagicMock()
        mock_server = MagicMock()

        mock_factory = MagicMock()
        mock_factory.create_mcp_server.return_value = mock_server
        mock_factory.agent = mock_agent

        with patch('serena.cli.SerenaMCPFactory', return_value=mock_factory):
            # ACT: Invoke start_mcp_server via CliRunner
            runner = CliRunner()
            result = runner.invoke(TopLevelCommands(), ['start-mcp-server'])
            # Note: server.run() is mocked, so it returns immediately

            # ASSERT 1: Signal handler is registered (not default)
            current_handler = signal.getsignal(signal.SIGTERM)
            self.assertNotEqual(
                current_handler, signal.SIG_DFL,
                (
                    "SEQ-SHUT-01 violation: SIGTERM handler not registered\n"
                    "Contract: graceful_shutdown_contract.py SEQ-SHUT-01\n"
                    f"EXPECTED: signal.getsignal(SIGTERM) != SIG_DFL (custom handler)\n"
                    f"ACTUAL: signal.getsignal(SIGTERM) == {current_handler}\n"
                    "GUIDANCE: start_mcp_server() MUST register a SIGTERM handler using "
                    "signal.signal(signal.SIGTERM, handler_function) BEFORE entering the "
                    "server event loop. The handler MUST call agent.shutdown(). "
                    "Implementation is free to use lambda or named function, but registration "
                    "MUST occur during server initialization."
                )
            )

            self.assertNotEqual(
                current_handler, signal.SIG_IGN,
                (
                    "SEQ-SHUT-01 violation: SIGTERM handler is SIG_IGN (ignored)\n"
                    "Contract: graceful_shutdown_contract.py SEQ-SHUT-01\n"
                    f"EXPECTED: signal.getsignal(SIGTERM) to be a callable handler\n"
                    f"ACTUAL: signal.getsignal(SIGTERM) == SIG_IGN (signal ignored)\n"
                    "GUIDANCE: SIGTERM must NOT be ignored. A callable handler is required."
                )
            )

            self.assertTrue(
                callable(current_handler),
                (
                    "SEQ-SHUT-01 violation: SIGTERM handler not callable\n"
                    "Contract: graceful_shutdown_contract.py SEQ-SHUT-01\n"
                    f"EXPECTED: signal.getsignal(SIGTERM) to be a callable function\n"
                    f"ACTUAL: {type(current_handler)}\n"
                    "GUIDANCE: The SIGTERM handler MUST be a callable (function or lambda)."
                )
            )

            # ASSERT 2: Handler invokes agent.shutdown() when called
            # Simulate signal delivery by calling the handler directly
            if callable(current_handler):
                try:
                    current_handler(signal.SIGTERM, None)  # signum, frame
                except Exception:
                    # Handler may raise during test (e.g., missing context)
                    # We care only whether it ATTEMPTED to call shutdown()
                    pass

                # Verify shutdown() was called
                self.assertTrue(
                    mock_agent.shutdown.called,
                    (
                        "SEQ-SHUT-01 violation: SIGTERM handler does not call agent.shutdown()\n"
                        "Contract: graceful_shutdown_contract.py SEQ-SHUT-01\n"
                        f"EXPECTED: Handler invokes agent.shutdown()\n"
                        f"ACTUAL: shutdown() called {mock_agent.shutdown.call_count} times\n"
                        "GUIDANCE: The SIGTERM signal handler MUST invoke agent.shutdown() "
                        "to trigger the cleanup chain. Implementation is free to use "
                        "lambda or named function, but shutdown() MUST be called."
                    )
                )

        # Restore original signal handler
        signal.signal(signal.SIGTERM, original_handler)


    # =========================================================================
    # SEQ-SHUT-04 — atexit.register() in start_mcp_server() → agent.shutdown()
    # =========================================================================

    def test_seq_shut_04_atexit_registers_shutdown(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: SEQ-SHUT-04: start_mcp_server() MUST register
                    atexit.register(agent.shutdown) as fallback cleanup
        - Category: positive (atexit registration)
        - Adversarial: Implementation-blind

        OBSERVABLE: After start_mcp_server() initialization:
                    - atexit registry contains agent.shutdown
                    - On process exit, shutdown() is called (if signal didn't fire)

        TESTING DISCIPLINE:
          - Mock atexit.register to verify registration call
          - Verify shutdown function is passed to atexit.register
        """
        from click.testing import CliRunner
        from serena.cli import TopLevelCommands

        # ARRANGE: Mock components
        mock_agent = MagicMock(spec=SerenaAgent)
        mock_agent.shutdown = MagicMock()
        mock_server = MagicMock()

        mock_factory = MagicMock()
        mock_factory.create_mcp_server.return_value = mock_server
        mock_factory.agent = mock_agent

        with patch('serena.cli.SerenaMCPFactory', return_value=mock_factory), \
             patch('atexit.register') as mock_atexit_register:

            # ACT: Invoke start_mcp_server via CliRunner
            runner = CliRunner()
            runner.invoke(TopLevelCommands(), ['start-mcp-server'])

            # ASSERT: atexit.register was called with agent.shutdown
            # Find the call where shutdown was registered
            shutdown_registered = False
            for call_args in mock_atexit_register.call_args_list:
                args, _ = call_args
                if args and hasattr(args[0], '__self__') and args[0].__self__ == mock_agent:
                    # Found a bound method call to shutdown
                    if args[0].__name__ == 'shutdown':
                        shutdown_registered = True
                        break
                elif args and args[0] == mock_agent.shutdown:
                    # Direct reference to shutdown method
                    shutdown_registered = True
                    break

            self.assertTrue(
                shutdown_registered,
                (
                    "SEQ-SHUT-04 violation: atexit.register(agent.shutdown) not called\n"
                    "Contract: graceful_shutdown_contract.py SEQ-SHUT-04\n"
                    f"EXPECTED: atexit.register() called with agent.shutdown\n"
                    f"ACTUAL: atexit.register() calls: {mock_atexit_register.call_args_list}\n"
                    "GUIDANCE: start_mcp_server() MUST call atexit.register(agent.shutdown) "
                    "during initialization, alongside SIGTERM handler registration. This ensures "
                    "cleanup occurs on non-signal exit paths (exception, sys.exit, normal termination). "
                    "Implementation is free to use atexit.register(agent.shutdown) or "
                    "atexit.register(lambda: agent.shutdown()), but registration MUST occur."
                )
            )


    # =========================================================================
    # SEQ-SHUT-02 — shutdown() calls lsp_pool.stop_all(save_cache=True)
    # =========================================================================

    def test_seq_shut_02_shutdown_calls_stop_all_with_save_cache(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: SEQ-SHUT-02: SerenaAgent.shutdown() MUST call
                    self._lsp_pool.stop_all(save_cache=True)
        - Category: positive (shutdown → stop_all wiring)
        - Adversarial: Implementation-blind

        OBSERVABLE: After agent.shutdown() completes:
                    - pool.stop_all(save_cache=True) was called
                    - save_cache parameter is True (cache persistence)

        TESTING DISCIPLINE:
          - Inject mock pool via agent constructor
          - Call agent.shutdown()
          - Verify stop_all(save_cache=True) was called
        """
        # ARRANGE: Create agent with mock pool (injected at construction)
        mock_pool = MagicMock(spec=GlobalLanguageServerPool)
        mock_pool.stop_all = MagicMock()

        agent = SerenaAgent(lsp_pool=mock_pool)

        # ACT: Call shutdown() — should trigger stop_all(save_cache=True)
        agent.shutdown()

        # ASSERT: stop_all(save_cache=True) was called
        mock_pool.stop_all.assert_called_once_with(save_cache=True)

        if not mock_pool.stop_all.called:
            self.fail(
                (
                    "SEQ-SHUT-02 violation: stop_all() not called during shutdown()\n"
                    "Contract: graceful_shutdown_contract.py SEQ-SHUT-02\n"
                    f"EXPECTED: lsp_pool.stop_all(save_cache=True) called during shutdown()\n"
                    f"ACTUAL: stop_all() called {mock_pool.stop_all.call_count} times\n"
                    "GUIDANCE: SerenaAgent.shutdown() MUST call self._lsp_pool.stop_all(save_cache=True) "
                    "AFTER session deactivation, BEFORE method returns. The save_cache=True parameter "
                    "ensures cache persistence across HTTP server restarts. Implementation is free to "
                    "choose call placement within shutdown() as long as stop_all is invoked."
                )
            )

        # ASSERT: save_cache parameter is True
        call_args = mock_pool.stop_all.call_args
        if call_args:
            args, kwargs = call_args
            save_cache_value = kwargs.get('save_cache', args[0] if args else None)
            self.assertTrue(
                save_cache_value,
                (
                    "SEQ-SHUT-02 violation: stop_all() called with save_cache=False\n"
                    "Contract: graceful_shutdown_contract.py SEQ-SHUT-02\n"
                    f"EXPECTED: stop_all(save_cache=True)\n"
                    f"ACTUAL: stop_all(save_cache={save_cache_value})\n"
                    "GUIDANCE: The save_cache parameter MUST be True to persist LSP cache "
                    "across server restarts, avoiding cold-start penalty."
                )
            )


    def test_err_shut_02_shutdown_handles_missing_lsp_pool(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: ERR-SHUT-02: shutdown() handles missing _lsp_pool gracefully
        - Category: error (missing pool handling)
        - Adversarial: Implementation-blind

        OBSERVABLE: agent.shutdown() on fresh agent (no acquire() calls) completes
                    without error, no stop_all() call, no LOG-POOL-04 emitted.

        TESTING DISCIPLINE:
          - Create agent with lsp_pool=None (lazy initialization not triggered)
          - Call shutdown()
          - Verify no exceptions raised
        """
        # ARRANGE: Create agent with no pool
        agent = SerenaAgent(lsp_pool=None)

        # ACT + ASSERT: shutdown() must not raise
        try:
            agent.shutdown()
        except Exception as e:
            self.fail(
                (
                    "ERR-SHUT-02 violation: shutdown() raised exception with missing pool\n"
                    "Contract: graceful_shutdown_contract.py ERR-SHUT-02\n"
                    f"EXPECTED: shutdown() completes without error when _lsp_pool is None\n"
                    f"ACTUAL: shutdown() raised {type(e).__name__}: {e}\n"
                    "GUIDANCE: shutdown() MUST check whether _lsp_pool exists or is None. "
                    "If None or nonexistent, skip pool cleanup gracefully. This is NOT an error "
                    "condition — it means no LSPs were ever created. Use hasattr(self, '_lsp_pool') "
                    "or 'if self._lsp_pool is not None' to guard the stop_all() call."
                )
            )


    # =========================================================================
    # SEQ-SHUT-03 — stop_all() calls timeout_manager.stop_monitoring()
    # =========================================================================

    def test_seq_shut_03_stop_all_calls_stop_monitoring(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: SEQ-SHUT-03: GlobalLanguageServerPool.stop_all() MUST call
                    self.timeout_manager.stop_monitoring()
        - Category: positive (stop_all → stop_monitoring wiring)
        - Adversarial: Implementation-blind

        OBSERVABLE: After pool.stop_all() completes:
                    - timeout_manager.stop_monitoring() was called
                    - Call occurs AFTER all LSPs are stopped (ordering)

        TESTING DISCIPLINE:
          - Inject mock timeout_manager via pool constructor
          - Call pool.stop_all()
          - Verify stop_monitoring() was called
        """
        # ARRANGE: Create pool with mock timeout_manager (injected at construction)
        mock_timeout_manager = MagicMock(spec=LSPTimeoutManager)
        mock_timeout_manager.stop_monitoring = MagicMock()
        mock_timeout_manager.is_monitoring.return_value = False

        pool = GlobalLanguageServerPool(timeout_manager=mock_timeout_manager)

        # ACT: Call stop_all() — should trigger stop_monitoring()
        pool.stop_all(save_cache=False)

        # ASSERT: stop_monitoring() was called
        mock_timeout_manager.stop_monitoring.assert_called_once_with()

        if not mock_timeout_manager.stop_monitoring.called:
            self.fail(
                (
                    "SEQ-SHUT-03 violation: stop_monitoring() not called during stop_all()\n"
                    "Contract: graceful_shutdown_contract.py SEQ-SHUT-03\n"
                    f"EXPECTED: timeout_manager.stop_monitoring() called during stop_all()\n"
                    f"ACTUAL: stop_monitoring() called {mock_timeout_manager.stop_monitoring.call_count} times\n"
                    "GUIDANCE: GlobalLanguageServerPool.stop_all() MUST call "
                    "self.timeout_manager.stop_monitoring() AFTER all LSP instances are stopped, "
                    "BEFORE stop_all() returns. This ensures the monitoring thread is explicitly "
                    "stopped rather than relying on daemon thread cleanup. Implementation is free to "
                    "choose call placement as long as stop_monitoring() is invoked."
                )
            )


    # =========================================================================
    # INV-SHUT-01 + INV-SHUT-04 — Idempotency via lock+flag
    # =========================================================================

    def test_inv_shut_01_shutdown_idempotent(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: INV-SHUT-01: shutdown() MUST be safe to call multiple times
        - Enforces: INV-SHUT-04: shutdown() lock+flag mechanism is thread-safe
        - Category: invariant (idempotency + thread safety)
        - Adversarial: Implementation-blind

        OBSERVABLE: Calling shutdown() twice produces no errors, second call is no-op,
                    pool.stop_all() called only once.

        TESTING DISCIPLINE:
          - Inject mock pool to count stop_all() calls
          - Call shutdown() twice sequentially
          - Verify no exceptions and stop_all() called exactly once
        """
        # ARRANGE: Create agent with mock pool
        mock_pool = MagicMock(spec=GlobalLanguageServerPool)
        mock_pool.stop_all = MagicMock()

        agent = SerenaAgent(lsp_pool=mock_pool)

        # ACT: Call shutdown() twice
        try:
            agent.shutdown()
            agent.shutdown()  # Second call should be no-op
        except Exception as e:
            self.fail(
                (
                    "INV-SHUT-01 violation: shutdown() raised exception on second call\n"
                    "Contract: graceful_shutdown_contract.py INV-SHUT-01\n"
                    f"EXPECTED: shutdown() safe to call multiple times\n"
                    f"ACTUAL: Second shutdown() raised {type(e).__name__}: {e}\n"
                    "GUIDANCE: shutdown() MUST use threading.Lock + boolean flag to ensure "
                    "idempotency. First call acquires lock, sets flag, performs cleanup. "
                    "Subsequent calls acquire lock, see flag=True, return immediately (no-op)."
                )
            )

        # ASSERT: stop_all() called exactly once (not twice)
        self.assertEqual(
            mock_pool.stop_all.call_count, 1,
            (
                "INV-SHUT-01 violation: stop_all() called multiple times on repeated shutdown()\n"
                "Contract: graceful_shutdown_contract.py INV-SHUT-01\n"
                f"EXPECTED: stop_all() called exactly 1 time (idempotency)\n"
                f"ACTUAL: stop_all() called {mock_pool.stop_all.call_count} times\n"
                "GUIDANCE: The idempotency mechanism (lock+flag) MUST ensure that cleanup "
                "(stop_all call) occurs only on the FIRST shutdown() invocation. Subsequent "
                "calls should return early without re-executing cleanup."
            )
        )


    def test_inv_shut_04_concurrent_shutdown_thread_safety(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: INV-SHUT-04: shutdown() lock+flag mechanism is thread-safe
        - Enforces: INV-SHUT-01: shutdown() idempotent under concurrency
        - Category: invariant (thread safety verification)
        - Adversarial: Implementation-blind

        OBSERVABLE: Under concurrent shutdown() calls from two threads,
                    stop_all() called exactly once (atomicity proof).

        TESTING DISCIPLINE:
          - Inject mock pool to count stop_all() calls
          - Launch 2 concurrent threads calling shutdown()
          - Verify stop_all() called exactly once (not twice)
        """
        # ARRANGE: Create agent with mock pool
        mock_pool = MagicMock(spec=GlobalLanguageServerPool)
        mock_pool.stop_all = MagicMock()

        agent = SerenaAgent(lsp_pool=mock_pool)

        # ACT: Launch 2 concurrent shutdown() calls
        def concurrent_shutdown():
            agent.shutdown()

        thread1 = threading.Thread(target=concurrent_shutdown)
        thread2 = threading.Thread(target=concurrent_shutdown)

        thread1.start()
        thread2.start()

        thread1.join(timeout=5)
        thread2.join(timeout=5)

        # ASSERT: stop_all() called exactly once (atomicity proof)
        self.assertEqual(
            mock_pool.stop_all.call_count, 1,
            (
                "INV-SHUT-04 violation: Thread safety not maintained\n"
                "Contract: graceful_shutdown_contract.py INV-SHUT-04\n"
                f"EXPECTED: stop_all() called exactly 1 time under concurrent shutdown()\n"
                f"ACTUAL: stop_all() called {mock_pool.stop_all.call_count} times\n"
                "GUIDANCE: The threading.Lock ensures that concurrent access from signal handler "
                "thread and atexit callback is safe. Lock acquisition serializes access to "
                "_shutdown_called flag. Only one caller proceeds past the flag check. "
                "Implementation MUST use threading.Lock to protect flag check+set+cleanup sequence."
            )
        )


    # =========================================================================
    # POST-SHUT-01 — No orphaned LSP subprocesses after shutdown
    # =========================================================================

    def test_post_shut_01_no_orphaned_lsps_after_shutdown(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: POST-SHUT-01: No orphaned LSP subprocesses after shutdown
        - Category: positive (observable end-state)
        - Adversarial: Implementation-blind

        OBSERVABLE: After shutdown() completes:
                    - Every LSP in pool has had stop() called
                    - Pool dict is empty

        TESTING DISCIPLINE:
          - Create pool with mock LSPs
          - Populate pool with mock LSPs
          - Call agent.shutdown() (via injected pool)
          - Verify each LSP.stop() was called
          - Verify pool is empty
        """
        # ARRANGE: Create mock LSPs with is_running() returning True
        mock_lsp1 = MagicMock()
        mock_lsp1.is_running.return_value = True
        mock_lsp1.stop = MagicMock()
        mock_lsp1.save_cache = MagicMock()
        mock_lsp2 = MagicMock()
        mock_lsp2.is_running.return_value = True
        mock_lsp2.stop = MagicMock()
        mock_lsp2.save_cache = MagicMock()

        # Create pool and manually populate (simulating acquire() calls)
        pool = GlobalLanguageServerPool()
        pool._pool[(Language.PYTHON, Path('/workspace1'))] = mock_lsp1
        pool._pool[(Language.PYTHON, Path('/workspace2'))] = mock_lsp2

        # Create agent with this pool
        agent = SerenaAgent(lsp_pool=pool)

        # ACT: Call shutdown() — should stop all LSPs and clear pool
        agent.shutdown()

        # ASSERT 1: Each LSP.stop() was called
        mock_lsp1.stop.assert_called_once()
        mock_lsp2.stop.assert_called_once()

        if not mock_lsp1.stop.called:
            self.fail(
                (
                    "POST-SHUT-01 violation: LSP.stop() not called for all LSPs\n"
                    "Contract: graceful_shutdown_contract.py POST-SHUT-01\n"
                    f"EXPECTED: stop() called on every LSP in pool\n"
                    f"ACTUAL: mock_lsp1.stop() called {mock_lsp1.stop.call_count} times\n"
                    "GUIDANCE: stop_all() MUST iterate over all LSPs in the pool dict "
                    "and call stop() on each. Verify the loop covers all entries."
                )
            )

        # ASSERT 2: Pool is empty
        self.assertEqual(
            len(pool._pool), 0,
            (
                "POST-SHUT-01 violation: Pool not empty after shutdown\n"
                "Contract: graceful_shutdown_contract.py POST-SHUT-01\n"
                f"EXPECTED: pool._pool == {{}} (empty dict)\n"
                f"ACTUAL: pool._pool has {len(pool._pool)} entries\n"
                "GUIDANCE: stop_all() MUST clear the pool dict after stopping all LSPs. "
                "Use pool._pool.clear() or equivalent after the stop loop."
            )
        )


    # =========================================================================
    # POST-SHUT-02 — LOG-POOL-04 emitted during shutdown
    # =========================================================================

    def test_post_shut_02_log_pool_04_emitted(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: POST-SHUT-02: LOG-POOL-04 emitted during shutdown
        - Category: positive (logging observability)
        - Adversarial: Implementation-blind

        OBSERVABLE: After shutdown() triggers stop_all():
                    - Log message matching LOG-POOL-04 pattern is emitted:
                      "[LSP-Pool] Stopping all N language servers (save_cache=True)"

        TESTING DISCIPLINE:
          - Capture log output at INFO level
          - Call agent.shutdown()
          - Verify LOG-POOL-04 message present
          - Verify save_cache=True in message
        """
        # ARRANGE: Create pool with mock LSPs
        pool = GlobalLanguageServerPool()
        mock_lsp = MagicMock()
        mock_lsp.is_running.return_value = True
        mock_lsp.stop = MagicMock()
        mock_lsp.save_cache = MagicMock()
        pool._pool[(Language.PYTHON, Path('/workspace'))] = mock_lsp

        agent = SerenaAgent(lsp_pool=pool)

        # ACT: Call shutdown() and capture logs
        with self.assertLogs('serena.global_lsp_pool', level=logging.INFO) as log_capture:
            agent.shutdown()

        # ASSERT: LOG-POOL-04 present
        log_pool_04_messages = [
            log for log in log_capture.records
            if "[LSP-Pool] Stopping all" in log.getMessage()
        ]

        self.assertGreater(
            len(log_pool_04_messages), 0,
            (
                "POST-SHUT-02 violation: LOG-POOL-04 not emitted\n"
                "Contract: graceful_shutdown_contract.py POST-SHUT-02\n"
                f"EXPECTED: LOG-POOL-04 '[LSP-Pool] Stopping all N language servers (save_cache=True)'\n"
                f"ACTUAL: No LOG-POOL-04 found in logs\n"
                f"All log messages: {[log.getMessage() for log in log_capture.records]}\n"
                "GUIDANCE: stop_all() MUST emit LOG-POOL-04 at INFO level when stopping servers. "
                "Use logger.info() with the prescribed format."
            )
        )

        # ASSERT: save_cache=True in message
        log_message = log_pool_04_messages[0].getMessage()
        self.assertIn(
            "save_cache=True", log_message,
            (
                "POST-SHUT-02 violation: LOG-POOL-04 missing save_cache=True\n"
                "Contract: graceful_shutdown_contract.py POST-SHUT-02\n"
                f"EXPECTED: 'save_cache=True' in LOG-POOL-04 message\n"
                f"ACTUAL: '{log_message}'\n"
                "GUIDANCE: The log message MUST include save_cache parameter value "
                "for observability. Use f-string: f'Stopping all {n} language servers (save_cache={save_cache})'"
            )
        )


    # =========================================================================
    # POST-SHUT-03 — LOG-TMO-02 emitted if monitoring was active
    # =========================================================================

    def test_post_shut_03_log_tmo_02_emitted_if_monitoring_active(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: POST-SHUT-03: LOG-TMO-02 emitted during shutdown
                    if monitoring was active
        - Category: positive (logging observability)
        - Adversarial: Implementation-blind

        OBSERVABLE: After stop_all() triggers stop_monitoring():
                    - If monitoring was active: LOG-TMO-02 emitted
                      ("[LSP-Timeout] Monitoring stopped")
                    - timeout_manager.is_monitoring() == False after stop_all()

        TESTING DISCIPLINE:
          - Create pool with real timeout_manager
          - Start monitoring manually
          - Call pool.stop_all()
          - Verify LOG-TMO-02 emitted
        """
        # ARRANGE: Create pool with real timeout_manager
        pool = GlobalLanguageServerPool()

        # Start monitoring manually (simulating acquire() call)
        pool.timeout_manager.start_monitoring()
        time.sleep(0.1)  # Allow thread startup

        # Verify monitoring is active
        self.assertTrue(
            pool.timeout_manager.is_monitoring(),
            "Precondition failed: monitoring should be active before stop_all()"
        )

        # ACT: Call stop_all() and capture logs
        with self.assertLogs('serena.lsp_timeout', level=logging.INFO) as log_capture:
            pool.stop_all(save_cache=False)

        # ASSERT 1: LOG-TMO-02 present
        log_tmo_02_messages = [
            log for log in log_capture.records
            if "[LSP-Timeout] Monitoring stopped" in log.getMessage()
        ]

        self.assertGreater(
            len(log_tmo_02_messages), 0,
            (
                "POST-SHUT-03 violation: LOG-TMO-02 not emitted when monitoring was active\n"
                "Contract: graceful_shutdown_contract.py POST-SHUT-03\n"
                f"EXPECTED: LOG-TMO-02 '[LSP-Timeout] Monitoring stopped'\n"
                f"ACTUAL: No LOG-TMO-02 found in logs\n"
                f"All log messages: {[log.getMessage() for log in log_capture.records]}\n"
                "GUIDANCE: stop_monitoring() MUST emit LOG-TMO-02 at INFO level when "
                "monitoring thread is stopped. Use logger.info() with prescribed format."
            )
        )

        # ASSERT 2: Monitoring is stopped
        is_monitoring_after = pool.timeout_manager.is_monitoring()
        self.assertFalse(
            is_monitoring_after,
            (
                "POST-SHUT-03 violation: Monitoring still active after stop_all()\n"
                "Contract: graceful_shutdown_contract.py POST-SHUT-03\n"
                f"EXPECTED: is_monitoring() == False after stop_all()\n"
                f"ACTUAL: is_monitoring() == {is_monitoring_after}\n"
                "GUIDANCE: stop_all() MUST call timeout_manager.stop_monitoring(), "
                "which MUST set is_monitoring() to False. Verify the call is made."
            )
        )


    def test_post_shut_03_no_log_tmo_02_if_monitoring_not_active(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: POST-SHUT-03: LOG-TMO-02 NOT emitted if monitoring was NOT active
        - Category: negative (no-op case)
        - Adversarial: Implementation-blind

        OBSERVABLE: If monitoring was never started:
                    - stop_monitoring() is no-op
                    - No LOG-TMO-02 at INFO level (may be DEBUG)

        TESTING DISCIPLINE:
          - Create pool without starting monitoring
          - Call pool.stop_all()
          - Verify no INFO-level LOG-TMO-02
        """
        # ARRANGE: Create pool with real timeout_manager (monitoring NOT started)
        pool = GlobalLanguageServerPool()

        # Verify monitoring is NOT active
        self.assertFalse(
            pool.timeout_manager.is_monitoring(),
            "Precondition failed: monitoring should NOT be active"
        )

        # ACT: Call stop_all()
        # Note: Cannot use assertLogs here because we expect NO INFO logs
        # We'll manually check logger instead
        import logging as log_module
        logger = log_module.getLogger('serena.lsp_timeout')
        handler = log_module.StreamHandler()
        handler.setLevel(log_module.INFO)
        logger.addHandler(handler)

        # Capture log output
        from io import StringIO
        log_stream = StringIO()
        stream_handler = log_module.StreamHandler(log_stream)
        stream_handler.setLevel(log_module.INFO)
        logger.addHandler(stream_handler)

        pool.stop_all(save_cache=False)

        log_output = log_stream.getvalue()

        # ASSERT: No INFO-level LOG-TMO-02
        self.assertNotIn(
            "[LSP-Timeout] Monitoring stopped", log_output,
            (
                "POST-SHUT-03 violation: LOG-TMO-02 emitted when monitoring was NOT active\n"
                "Contract: graceful_shutdown_contract.py POST-SHUT-03\n"
                f"EXPECTED: No INFO-level LOG-TMO-02 when monitoring was never started\n"
                f"ACTUAL: LOG-TMO-02 found in logs: {log_output}\n"
                "GUIDANCE: stop_monitoring() is a safe no-op if monitoring was never started. "
                "It should NOT emit INFO-level LOG-TMO-02 in this case (DEBUG acceptable). "
                "Check is_monitoring() before logging at INFO level."
            )
        )

        # Clean up handlers
        logger.removeHandler(stream_handler)
        logger.removeHandler(handler)


    # =========================================================================
    # POST-SHUT-04 — Signal handler and atexit hook registered
    # =========================================================================

    def test_post_shut_04_signal_and_atexit_registered(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: POST-SHUT-04: Signal handler and atexit hook are registered
        - Category: positive (initialization verification)
        - Adversarial: Implementation-blind

        OBSERVABLE: After start_mcp_server() initialization:
                    - signal.getsignal(SIGTERM) returns a callable
                    - atexit registry contains agent.shutdown

        TESTING DISCIPLINE:
          - This is a COMBINED verification of SEQ-SHUT-01 + SEQ-SHUT-04
          - Already covered by individual tests
          - This test verifies BOTH are registered (integration check)
        """
        from click.testing import CliRunner
        from serena.cli import TopLevelCommands

        # ARRANGE: Save original SIGTERM handler
        original_handler = signal.getsignal(signal.SIGTERM)

        mock_agent = MagicMock(spec=SerenaAgent)
        mock_server = MagicMock()

        mock_factory = MagicMock()
        mock_factory.create_mcp_server.return_value = mock_server
        mock_factory.agent = mock_agent

        with patch('serena.cli.SerenaMCPFactory', return_value=mock_factory), \
             patch('atexit.register') as mock_atexit_register:

            # ACT: Invoke start_mcp_server via CliRunner
            runner = CliRunner()
            runner.invoke(TopLevelCommands(), ['start-mcp-server'])

            # ASSERT 1: SIGTERM handler registered
            current_handler = signal.getsignal(signal.SIGTERM)
            self.assertTrue(
                callable(current_handler) and current_handler not in (signal.SIG_DFL, signal.SIG_IGN),
                (
                    "POST-SHUT-04 violation: SIGTERM handler not properly registered\n"
                    "Contract: graceful_shutdown_contract.py POST-SHUT-04\n"
                    f"EXPECTED: signal.getsignal(SIGTERM) to be a callable\n"
                    f"ACTUAL: {current_handler}\n"
                    "GUIDANCE: start_mcp_server() MUST register both SIGTERM handler AND atexit hook. "
                    "This test verifies the combined initialization."
                )
            )

            # ASSERT 2: atexit registered
            shutdown_registered = False
            for call_args in mock_atexit_register.call_args_list:
                args, _ = call_args
                if args and hasattr(args[0], '__self__') and args[0].__self__ == mock_agent:
                    if args[0].__name__ == 'shutdown':
                        shutdown_registered = True
                        break
                elif args and args[0] == mock_agent.shutdown:
                    shutdown_registered = True
                    break

            self.assertTrue(
                shutdown_registered,
                (
                    "POST-SHUT-04 violation: atexit.register not called\n"
                    "Contract: graceful_shutdown_contract.py POST-SHUT-04\n"
                    f"EXPECTED: Both SIGTERM handler AND atexit hook registered\n"
                    f"ACTUAL: atexit calls: {mock_atexit_register.call_args_list}\n"
                    "GUIDANCE: start_mcp_server() MUST register BOTH signal handler AND atexit hook."
                )
            )

        # Restore original handler
        signal.signal(signal.SIGTERM, original_handler)


    # =========================================================================
    # ERR-SHUT-01 — shutdown() does not raise exceptions
    # =========================================================================

    def test_err_shut_01_shutdown_does_not_raise_exceptions(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: graceful_shutdown_contract.py
        - Enforces: ERR-SHUT-01: shutdown() MUST NOT raise exceptions
        - Category: error (exception handling in cleanup path)
        - Adversarial: Implementation-blind

        OBSERVABLE: shutdown() returns normally even if individual stop() calls fail.

        TESTING DISCIPLINE:
          - Inject mock pool where stop_all() raises exception
          - Call agent.shutdown()
          - Verify no exception propagates (caught and logged)
        """
        # ARRANGE: Create mock pool that raises exception
        mock_pool = MagicMock(spec=GlobalLanguageServerPool)
        mock_pool.stop_all.side_effect = RuntimeError("Simulated stop_all failure")

        agent = SerenaAgent(lsp_pool=mock_pool)

        # ACT + ASSERT: shutdown() must not raise
        try:
            agent.shutdown()
        except Exception as e:
            self.fail(
                (
                    "ERR-SHUT-01 violation: shutdown() raised exception\n"
                    "Contract: graceful_shutdown_contract.py ERR-SHUT-01\n"
                    f"EXPECTED: shutdown() returns normally despite stop_all() failure\n"
                    f"ACTUAL: shutdown() raised {type(e).__name__}: {e}\n"
                    "GUIDANCE: The shutdown path is a cleanup path. Exceptions during cleanup "
                    "MUST be caught and logged (not propagated). Use try/except around stop_all() "
                    "call, log at WARNING or ERROR level, continue cleanup. Signal handlers that "
                    "raise cause undefined behavior. atexit handlers that raise print traceback "
                    "but continue. Best practice: log errors, continue cleanup, exit cleanly."
                )
            )


if __name__ == '__main__':
    unittest.main()
