"""
Graceful Shutdown Integration Contract (Tier 1.5)
==================================================

Source: REQ-GRACEFUL-SHUTDOWN-001
Authority: THIS FILE is the authoritative contract for graceful LSP shutdown.
Related: contracts/global_lsp_pool_contract.py (component contract for pool)
         contracts/logging_observability_contract.py (LOG-POOL-04, LOG-TMO-02 logging)
         contracts/timeout_wiring_contract.py (timeout monitoring wiring)
         contracts/lsp_timeout_contract.py (component contract for LSPTimeoutManager)

Traceability Chain:
    contracts/REQ-GRACEFUL-SHUTDOWN-001.md (requirements manifest)
        |
    contracts/graceful_shutdown_contract.py (THIS FILE -- integration contract)
        |
    tests/test_graceful_shutdown_contract.py (adversarial tests)
        |
    src/serena/agent.py (shutdown method)
    src/serena/global_lsp_pool.py (stop_all method)
    src/serena/cli.py (start_mcp_server signal/atexit registration)

Purpose:
    This is a Tier 1.5 Integration Contract. It specifies the CLEANUP CHAIN
    that must execute when the Serena MCP HTTP server receives SIGTERM (from launchd)
    or exits normally.

    The component contracts already specify:
    - SerenaAgent.shutdown() deactivates sessions (Tier 1)
    - GlobalLanguageServerPool.stop_all() stops LSPs and clears pool (Tier 1)
    - LSPTimeoutManager.stop_monitoring() stops the daemon thread (Tier 1)

    What is MISSING: the wiring that connects these components into a cleanup chain.
    Without this contract:
    - SIGTERM kills the process without cleanup
    - LSP subprocesses become orphaned zombies
    - Monitoring thread is not explicitly stopped
    - Cache is not saved on HTTP server restart

    For integration contracts, the HOW IS the WHAT.
    "shutdown() calls stop_all(save_cache=True)" is not an implementation detail --
    it is an architectural obligation.

User Design Decisions (CL13 adjudicated):
    Zone 1: Threading lock + flag for idempotency
        Decided By: User ("B is the honest choice. It ensures that even if a signal
        and an atexit fire in weirdly close proximity during a kernel context switch,
        you won't have a race condition on the lsp.stop() calls.")

    Zone 2: Signal handler in start_mcp_server() CLI entry point
        Decided By: User ("Option A is the only correct architectural choice.
        Signal handlers are a Process Concern, not a Domain Concern.")
"""

# No runtime imports needed -- this is a specification-only contract file.
# Types referenced in docstrings only:
#   SerenaAgent (src/serena/agent.py)
#   GlobalLanguageServerPool (src/serena/global_lsp_pool.py)
#   LSPTimeoutManager (src/serena/lsp_timeout.py)
#   start_mcp_server (src/serena/cli.py)


# =============================================================================
# SEQ CLAUSES -- Integration Sequencing Obligations (Cleanup Chain)
# =============================================================================

SEQ_SHUT_01 = """
SEQ-SHUT-01: start_mcp_server() MUST register a SIGTERM handler that calls
             agent.shutdown().

CALLER: start_mcp_server() in src/serena/cli.py
CALLEE: signal.signal(SIGTERM, handler) where handler invokes agent.shutdown()
TEMPORAL: DURING server startup, BEFORE entering the server event loop.
          The handler MUST be registered so that SIGTERM from launchd triggers
          the full cleanup chain.

SOURCE: REQ-GRACEFUL-SHUTDOWN-001, SEQ-SHUT-01, IP-1

OBSERVABLE:
  - After start_mcp_server() initializes: signal.getsignal(SIGTERM) returns
    a callable handler (not SIG_DFL and not SIG_IGN)
  - When SIGTERM is sent: agent.shutdown() is called
  - The handler MUST NOT start new work (INV-SHUT-03)

BREAKS IF MISSING:
  - SIGTERM kills process immediately (default handler)
  - No cleanup occurs
  - LSP subprocesses become orphaned zombies
  - launchd restarts server, orphans accumulate

TESTING DISCIPLINE:
  - Tests MUST verify signal handler registration in start_mcp_server()
  - Tests MUST verify the handler calls agent.shutdown()
  - Mocking agent.shutdown() is acceptable to verify the CALL was made
  - signal.getsignal() can verify registration without sending actual signals
"""

SEQ_SHUT_02 = """
SEQ-SHUT-02: SerenaAgent.shutdown() MUST call self._lsp_pool.stop_all(save_cache=True)
             AFTER session deactivation, BEFORE process exit.

CALLER: SerenaAgent.shutdown()
CALLEE: GlobalLanguageServerPool.stop_all(save_cache=True)
TEMPORAL: AFTER any active session is deactivated (existing behavior),
          BEFORE the method returns. The save_cache=True parameter ensures
          cache persistence across HTTP server restarts.

SOURCE: REQ-GRACEFUL-SHUTDOWN-001, SEQ-SHUT-02, IP-2

OBSERVABLE:
  - After shutdown() completes: all LSP subprocesses are terminated
  - After shutdown() completes: pool is empty (no entries in _pool dict)
  - LOG-POOL-04 is emitted ("Stopping all N language servers")
  - Cache is saved (save_cache=True passed to stop_all)

PRE:
  - self._lsp_pool may or may not exist (lazy initialization via get_lsp_pool())
  - If _lsp_pool is None: shutdown() MUST NOT crash (skip pool cleanup gracefully)
  - If _lsp_pool exists: stop_all(save_cache=True) MUST be called

BREAKS IF MISSING:
  - LSP subprocesses orphaned on every server restart
  - Cache lost on every restart (cold start penalty)
  - Zombie processes accumulate until system resource exhaustion

TESTING DISCIPLINE:
  - Tests MUST verify stop_all(save_cache=True) is called (not save_cache=False)
  - Tests MUST verify graceful handling when _lsp_pool is None
  - Tests MUST use the shutdown() entry point, not call stop_all() directly
"""

SEQ_SHUT_03 = """
SEQ-SHUT-03: GlobalLanguageServerPool.stop_all() MUST call
             self.timeout_manager.stop_monitoring() AFTER all LSPs are stopped.

CALLER: GlobalLanguageServerPool.stop_all()
CALLEE: LSPTimeoutManager.stop_monitoring()
TEMPORAL: AFTER all LSP instances are stopped (lsp.stop() for each),
          BEFORE stop_all() returns. This ensures the monitoring thread
          is explicitly stopped rather than relying on daemon thread cleanup.

SOURCE: REQ-GRACEFUL-SHUTDOWN-001, SEQ-SHUT-03, IP-3

OBSERVABLE:
  - After stop_all() completes: timeout_manager.is_monitoring() == False
  - LOG-TMO-02 is emitted ("[LSP-Timeout] Monitoring stopped")
  - Monitoring thread is joined (no dangling thread)

PRE:
  - timeout_manager always exists (created in __init__)
  - Monitoring may or may not be active (start_monitoring() may not have been called)
  - If not monitoring: stop_monitoring() is a safe no-op

BREAKS IF MISSING:
  - Monitoring thread continues running after pool is emptied
  - Thread may attempt to reclaim already-stopped LSPs
  - Not a critical failure (daemon thread dies with process) but unclean

TESTING DISCIPLINE:
  - Tests MUST verify stop_monitoring() is called during stop_all()
  - Tests MUST verify stop_monitoring() is called AFTER LSP stops (ordering)
  - Tests MUST handle the case where monitoring was never started
"""

SEQ_SHUT_04 = """
SEQ-SHUT-04: start_mcp_server() MUST register atexit.register(agent.shutdown)
             as a fallback cleanup path.

CALLER: start_mcp_server() in src/serena/cli.py
CALLEE: atexit.register(agent.shutdown)
TEMPORAL: DURING server startup, alongside SIGTERM handler registration.
          This ensures cleanup occurs even on non-signal exit paths
          (e.g., unhandled exception, sys.exit(), normal termination).

SOURCE: REQ-GRACEFUL-SHUTDOWN-001, SEQ-SHUT-04, IP-4

OBSERVABLE:
  - After start_mcp_server() initializes: agent.shutdown is in atexit registry
  - On normal process exit: agent.shutdown() is called (if signal handler didn't fire)
  - Combined with INV-SHUT-01: double invocation (signal + atexit) is safe

BREAKS IF MISSING:
  - Non-signal exit paths (exception, sys.exit) skip cleanup entirely
  - LSP subprocesses orphaned on crash-restart cycles

TESTING DISCIPLINE:
  - Tests MUST verify atexit.register() is called with agent.shutdown
  - Tests MAY mock atexit.register to verify registration without side effects
  - Combined with INV-SHUT-01 tests: verify idempotency when both fire
"""


# =============================================================================
# INV CLAUSES -- Invariants for the Cleanup Chain
# =============================================================================

INV_SHUT_01 = """
INV-SHUT-01: Idempotency -- shutdown() MUST be safe to call multiple times.

SerenaAgent.shutdown() uses threading.Lock + boolean flag to ensure:
  - First call: acquires lock, sets flag, performs full cleanup
  - Subsequent calls: acquires lock, sees flag, returns immediately (no-op)

This is CRITICAL because both SIGTERM handler and atexit may fire during
the same process termination sequence. Without the lock+flag, a race
condition on lsp.stop() calls could occur during kernel context switch.

MECHANISM:
  - self._shutdown_lock = threading.Lock() (created in __init__)
  - self._shutdown_called = False (created in __init__)
  - shutdown() acquires lock, checks flag, sets flag, releases lock, then cleans up
  - OR: shutdown() acquires lock, checks flag (True), releases lock, returns

OBSERVABLE:
  - Calling shutdown() twice produces no errors
  - Second call is effectively a no-op
  - No race condition when called from two threads near-simultaneously

DECIDED BY: User ("B is the honest choice. It ensures that even if a signal
and an atexit fire in weirdly close proximity during a kernel context switch,
you won't have a race condition on the lsp.stop() calls.")
"""

INV_SHUT_02 = """
INV-SHUT-02: No Indefinite Blocking -- stop_all() MUST NOT block indefinitely.

Each LSP stop operation has an existing timeout (from SolidLanguageServer.stop()).
The cleanup chain MUST NOT introduce any new unbounded blocking:
  - Each lsp.stop() has its own timeout
  - stop_monitoring() joins the monitoring thread (which checks stop_event periodically)
  - No operation in the chain waits forever

OBSERVABLE:
  - shutdown() completes within a bounded time (sum of all LSP stop timeouts
    plus monitoring thread join timeout)
  - Process exits cleanly even if individual LSP stops timeout

NOTE: The exact timeout values are defined by the component contracts,
not by this integration contract. This invariant asserts that NO step
in the chain introduces an unbounded wait.
"""

INV_SHUT_03 = """
INV-SHUT-03: No New Work -- After shutdown begins, no new LSPs should be started.

Once shutdown() sets _shutdown_called = True, best-effort prevention of
new acquire() calls creating new LSP instances. This is best-effort because:
  - acquire() checks the flag but the window between check and create is not
    atomically locked against shutdown (different locks)
  - In practice, SIGTERM means the process is exiting and no new requests arrive

OBSERVABLE:
  - After shutdown() sets flag: acquire() raises or returns error if called
  - This is a DEFENSIVE measure, not a hard guarantee
  - Tests verify the flag is checked in acquire() path

NOTE: Full atomic acquire-vs-shutdown coordination would require a shared lock
between acquire() and shutdown(), which would add contention to the hot path.
The current design accepts the race window as acceptable for process shutdown.
"""

INV_SHUT_04 = """
INV-SHUT-04: Thread Safety -- shutdown() lock+flag mechanism is thread-safe.

The threading.Lock ensures that concurrent access from signal handler thread
and atexit callback (which may run on main thread or another thread) is safe:
  - Lock acquisition serializes access to _shutdown_called flag
  - Flag check and set are atomic within the lock
  - Only one caller proceeds past the flag check

This invariant is the IMPLEMENTATION of INV-SHUT-01 (idempotency).
INV-SHUT-01 describes WHAT (safe to call multiple times).
INV-SHUT-04 describes HOW (threading.Lock + flag).

OBSERVABLE:
  - _shutdown_lock is a threading.Lock instance
  - _shutdown_called is a boolean, accessed only under lock
  - Two concurrent shutdown() calls: exactly one performs cleanup
"""


# =============================================================================
# POST CLAUSES -- Observable End-States After Cleanup
# =============================================================================

POST_SHUT_01 = """
POST-SHUT-01: No orphaned LSP subprocesses after shutdown.

After shutdown() completes:
  - Every SolidLanguageServer instance that was in the pool has had stop() called
  - No LSP subprocesses remain running (they are terminated or killed)
  - The pool dict is empty

OBSERVABLE:
  - pool._pool == {} (empty after stop_all)
  - Each LSP's process is no longer running
  - LOG-POOL-04 emitted with count of stopped servers

VERIFICATION:
  - In tests: verify stop() was called on each LSP in pool
  - In production: verify no orphaned processes via ps/pgrep after restart
"""

POST_SHUT_02 = """
POST-SHUT-02: LOG-POOL-04 emitted during shutdown.

After shutdown() triggers stop_all():
  - Log message matching LOG-POOL-04 pattern is emitted:
    "[LSP-Pool] Stopping all N language servers (save_cache=True)"
  - N is the count of active LSP instances at time of stop_all() call

OBSERVABLE:
  - Log output contains the LOG-POOL-04 message
  - The save_cache parameter is True (per SEQ-SHUT-02)
"""

POST_SHUT_03 = """
POST-SHUT-03: LOG-TMO-02 emitted during shutdown (if monitoring was active).

After stop_all() triggers stop_monitoring():
  - If monitoring was active: LOG-TMO-02 emitted
    ("[LSP-Timeout] Monitoring stopped")
  - If monitoring was NOT active: no LOG-TMO-02 (stop_monitoring is no-op)

OBSERVABLE:
  - If monitoring was started: log contains LOG-TMO-02
  - timeout_manager.is_monitoring() == False after stop_all()
"""

POST_SHUT_04 = """
POST-SHUT-04: Signal handler and atexit hook are registered.

After start_mcp_server() initialization completes:
  - signal.getsignal(signal.SIGTERM) returns a callable (not SIG_DFL/SIG_IGN)
  - atexit registry contains agent.shutdown (or wrapper thereof)

OBSERVABLE:
  - signal.getsignal(SIGTERM) is not signal.SIG_DFL
  - signal.getsignal(SIGTERM) is not signal.SIG_IGN
  - atexit._exithandlers or equivalent contains shutdown reference
    (Note: atexit internals are CPython-specific; test via mock preferred)
"""


# =============================================================================
# ERRORS CLAUSES -- Exception Behavior During Cleanup
# =============================================================================

ERR_SHUT_01 = """
ERR-SHUT-01: shutdown() MUST NOT raise exceptions.

The shutdown path is a cleanup path. Exceptions during cleanup:
  - Must be caught and logged (not propagated)
  - Individual LSP stop failures must not prevent other LSPs from being stopped
  - Individual component failures must not prevent the chain from continuing

RATIONALE:
  - Signal handlers that raise cause undefined behavior
  - atexit handlers that raise print traceback but continue
  - Best practice: log errors, continue cleanup, exit cleanly

OBSERVABLE:
  - shutdown() returns normally even if individual stop() calls fail
  - Errors during cleanup are logged at WARNING or ERROR level
  - All reachable cleanup steps are attempted regardless of prior failures
"""

ERR_SHUT_02 = """
ERR-SHUT-02: shutdown() handles missing _lsp_pool gracefully.

If get_lsp_pool() was never called (pool never lazy-initialized):
  - _lsp_pool attribute may not exist or may be None
  - shutdown() MUST check for this and skip pool cleanup
  - This is NOT an error condition -- it means no LSPs were ever created

OBSERVABLE:
  - shutdown() on a fresh agent (no acquire() calls) completes without error
  - No LOG-POOL-04 emitted (no pool to stop)
"""


# =============================================================================
# INTEGRATION POINTS -- Cross-Reference to REQ-GRACEFUL-SHUTDOWN-001
# =============================================================================

INTEGRATION_POINTS = """
Integration Points (from REQ-GRACEFUL-SHUTDOWN-001 Section 3.5):

IP-1: SIGTERM handler in start_mcp_server() -> agent.shutdown()
      Contract Clause: SEQ-SHUT-01
      Status: TO BE WIRED (gap 1)

IP-2: SerenaAgent.shutdown() -> lsp_pool.stop_all(save_cache=True)
      Contract Clause: SEQ-SHUT-02
      Status: TO BE WIRED (gap 2)

IP-3: GlobalLanguageServerPool.stop_all() -> timeout_manager.stop_monitoring()
      Contract Clause: SEQ-SHUT-03
      Status: TO BE WIRED (gap 3)

IP-4: atexit.register() in start_mcp_server() -> agent.shutdown()
      Contract Clause: SEQ-SHUT-04
      Status: TO BE WIRED (gap 4)
"""


# =============================================================================
# CONTRACT CLAUSE ID INDEX
# For CL12-E test traceability -- tests MUST cite these IDs
# =============================================================================

CLAUSE_INDEX = {
    # SEQ clauses (integration wiring)
    "SEQ-SHUT-01": "SIGTERM handler in start_mcp_server() calls agent.shutdown()",
    "SEQ-SHUT-02": "shutdown() calls lsp_pool.stop_all(save_cache=True)",
    "SEQ-SHUT-03": "stop_all() calls timeout_manager.stop_monitoring()",
    "SEQ-SHUT-04": "atexit registers agent.shutdown() as fallback",

    # INV clauses (invariants)
    "INV-SHUT-01": "shutdown() idempotent -- safe to call multiple times",
    "INV-SHUT-02": "stop_all() does not block indefinitely",
    "INV-SHUT-03": "No new LSPs started after shutdown begins (best-effort)",
    "INV-SHUT-04": "shutdown() lock+flag mechanism is thread-safe",

    # POST clauses (observable end-states)
    "POST-SHUT-01": "No orphaned LSP subprocesses after shutdown",
    "POST-SHUT-02": "LOG-POOL-04 emitted during shutdown",
    "POST-SHUT-03": "LOG-TMO-02 emitted if monitoring was active",
    "POST-SHUT-04": "Signal handler and atexit hook are registered in start_mcp_server()",

    # ERR clauses (exception behavior)
    "ERR-SHUT-01": "shutdown() does not raise exceptions",
    "ERR-SHUT-02": "shutdown() handles missing _lsp_pool gracefully",
}
