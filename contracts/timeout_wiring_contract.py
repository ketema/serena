"""
Timeout Wiring Integration Contract (Tier 1.5)
===============================================

Source: REQ-TMO-WIRING-001
Authority: THIS FILE is the authoritative contract for timeout monitoring wiring.
Related: contracts/global_lsp_pool_contract.py (component contract for acquire)
         contracts/logging_observability_contract.py (LOG-TMO-01/02/03 logging contract)
         contracts/lsp_timeout_contract.py (component contract for LSPTimeoutManager)

Traceability Chain:
    contracts/REQ-TMO-WIRING-001.md (requirements manifest)
        ↓
    contracts/timeout_wiring_contract.py (THIS FILE — integration contract)
        ↓
    tests/test_timeout_wiring_contract.py (adversarial tests)
        ↓
    src/serena/global_lsp_pool.py (implementation: acquire method)

Purpose:
    This is a Tier 1.5 Integration Contract. It specifies the SEQUENCING OBLIGATION
    between GlobalLanguageServerPool.acquire() and LSPTimeoutManager.start_monitoring().

    The component contracts already specify:
    - acquire() returns an LSP and records session refs (Tier 1)
    - start_monitoring() launches a daemon thread (Tier 1)
    - LOG-TMO-01 logs when monitoring starts (Tier 1)

    What was MISSING: the obligation that acquire() CALLS start_monitoring().
    Without this contract, the system compiles, tests pass, but idle LSPs are
    never reclaimed in production — a silent resource leak.

    For integration contracts, the HOW IS the WHAT.
    "acquire() calls start_monitoring()" is not an implementation detail —
    it is an architectural obligation.
"""

# No runtime imports needed — this is a specification-only contract file.
# Types referenced in docstrings only:
#   GlobalLanguageServerPool (src/serena/global_lsp_pool.py)
#   LSPTimeoutManager (src/serena/lsp_timeout.py)


# =============================================================================
# SEQ CLAUSES — Integration Sequencing Obligations
# =============================================================================

SEQ_TMO_INIT_01 = """
SEQ-TMO-INIT-01: GlobalLanguageServerPool.acquire() MUST call
                  self.timeout_manager.start_monitoring()
                  AFTER first successful LSP acquisition.

CALLER: GlobalLanguageServerPool.acquire()
CALLEE: LSPTimeoutManager.start_monitoring()
TEMPORAL: AFTER successful LSP creation or reuse, BEFORE returning LSP to caller.
          Called on EVERY acquire() — start_monitoring() is internally idempotent
          (returns early if already monitoring).

SOURCE: REQ-TMO-WIRING-001, SEQ-TMO-INIT-01, IP-1

OBSERVABLE:
  - After first acquire(): pool.timeout_manager.is_monitoring() == True
  - After first acquire(): LOG-TMO-01 emitted ("[LSP-Timeout] Monitoring started")
  - After second acquire(): NO additional LOG-TMO-01 (idempotent)
  - Before any acquire(): pool.timeout_manager.is_monitoring() == False

BREAKS IF MISSING:
  - Monitoring thread never starts
  - timeout_manager.touch() timestamps accumulate but nothing checks them
  - Idle LSPs are NEVER reclaimed
  - Silent resource leak in long-running server

TESTING DISCIPLINE:
  - Tests MUST use actual Pool construction path (not direct start_monitoring())
  - Tests MUST call pool.acquire() and verify downstream monitoring state
  - Mocking timeout_manager is acceptable to verify the CALL was made
  - But at least one test must use real timeout_manager to verify end-to-end
"""


# =============================================================================
# INV CLAUSES — Invariants for the Integration
# =============================================================================

INV_TMO_01 = """
INV-TMO-01: Idempotency — start_monitoring() is safe to call multiple times.

The acquire() method calls start_monitoring() on EVERY invocation.
The LSPTimeoutManager.start_monitoring() method MUST handle this gracefully:
  - If not monitoring: start thread, emit LOG-TMO-01 at INFO
  - If already monitoring: return immediately, emit LOG-TMO-01 at DEBUG (noop)

This invariant is ALREADY SATISFIED by the existing start_monitoring() implementation.
This contract documents the obligation for future maintainers.
"""

INV_TMO_02 = """
INV-TMO-02: Thread Safety — start_monitoring() call occurs within pool_lock scope.

The acquire() method holds self._pool_lock when calling start_monitoring().
This ensures that the monitoring state transition is atomic with respect to
the pool state transition (LSP creation/reuse + session ref recording).

RATIONALE: If start_monitoring() were called outside the lock, a race condition
could occur where two concurrent acquire() calls both see is_monitoring()==False
and both attempt to start threads. While start_monitoring() is internally
idempotent, the pool_lock ensures cleaner sequencing.
"""

INV_TMO_03 = """
INV-TMO-03: Daemon Thread — monitoring thread MUST be daemon=True.

The monitoring thread created by start_monitoring() is a daemon thread.
This means it will be killed when the main process exits, preventing
zombie threads. This is ALREADY SATISFIED by the existing implementation.

This invariant ensures the production wiring does not introduce thread
lifecycle issues.
"""


# =============================================================================
# POST CLAUSES — Observable End-States
# =============================================================================

POST_TMO_WIRING_01 = """
POST-TMO-WIRING-01: After acquire(), monitoring is active.

After any successful call to GlobalLanguageServerPool.acquire():
  pool.timeout_manager.is_monitoring() == True

This is the PRIMARY observable that proves the wiring is correct.
"""

POST_TMO_WIRING_02 = """
POST-TMO-WIRING-02: After acquire(), LOG-TMO-01 emitted (first call only).

After the FIRST successful acquire() on a fresh pool:
  Log output contains "[LSP-Timeout] Monitoring started (interval: {N}s)" at INFO level.
  Exactly ONE INFO-level LOG-TMO-01 message emitted.

After SUBSEQUENT acquire() calls on the SAME pool:
  Log output contains "[LSP-Timeout] Monitoring already active, skipping start" at DEBUG level.
  ZERO additional INFO-level LOG-TMO-01 messages.
  Total INFO-level LOG-TMO-01 count remains exactly 1 regardless of acquire() count.

IDEMPOTENCY VERIFICATION: Call acquire() N times (N >= 2). Assert exactly 1 INFO
LOG-TMO-01. This is the explicit test for INV-TMO-01 via the integration path.
"""

POST_TMO_WIRING_03 = """
POST-TMO-WIRING-03: Before any acquire(), monitoring is NOT active.

On a freshly constructed GlobalLanguageServerPool (after __init__, before any acquire):
  pool.timeout_manager.is_monitoring() == False

This proves that monitoring is lazy — started by acquire(), not by __init__().
"""


# =============================================================================
# INTEGRATION POINTS — Cross-Reference to REQ-TMO-WIRING-001
# =============================================================================

INTEGRATION_POINTS = """
Integration Points (from REQ-TMO-WIRING-001 Section 3.5):

IP-1: Pool.acquire() → timeout_manager.start_monitoring()
      Contract Clause: SEQ-TMO-INIT-01
      Status: TO BE WIRED (this is the gap)

IP-2: Pool.__init__() → timeout_manager.set_reclaim_callback()
      Contract Clause: (existing — already wired)
      Status: ALREADY WIRED

IP-3: Pool.acquire() → timeout_manager.touch()
      Contract Clause: (existing — already wired)
      Status: ALREADY WIRED
"""


# =============================================================================
# CONTRACT CLAUSE ID INDEX
# For CL12-E test traceability — tests MUST cite these IDs
# =============================================================================

CLAUSE_INDEX = {
    "SEQ-TMO-INIT-01": "acquire() MUST call start_monitoring() after successful acquisition",
    "INV-TMO-01": "start_monitoring() idempotent — safe to call multiple times",
    "INV-TMO-02": "start_monitoring() call within pool_lock scope",
    "INV-TMO-03": "Monitoring thread is daemon=True",
    "POST-TMO-WIRING-01": "After acquire(), is_monitoring() == True",
    "POST-TMO-WIRING-02": "After first acquire(), exactly 1 LOG-TMO-01 at INFO; subsequent acquires emit 0 additional",
    "POST-TMO-WIRING-03": "Before any acquire(), is_monitoring() == False",
}
