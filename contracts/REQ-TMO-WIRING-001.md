# REQ-TMO-WIRING-001: Wire LSPTimeoutManager.start_monitoring() Into Production Path

## CCABDD Governance

Human owns: intent (front) + reality judgment (back).
AI owns: enforcement (middle).
Neither crosses the boundary.

Human MUST confirm real-world effect matches intent.
AI MAY NOT infer success from metrics.

**INV-3**: No discretion. No judgment. Only state.
CONTRACT SHALL NOT execute unless ALL predicates evaluate to TRUE.

---

## 1. Intent Traceability
- **Source Prose**:
  > "wire it up. start_monitoring should be called after the first acquire
  > this is also a test of CL12 we should have SEQ tests that describe this so follow full CCABDD to ensure we have proper requirements -> contracts -> tests -> implementation"
- **Our Understanding**: Wire `LSPTimeoutManager.start_monitoring()` into `GlobalLanguageServerPool.acquire()` so that after the first successful LSP acquisition, the idle monitoring daemon thread is started. This is a production wiring gap — all components exist but the integration call is missing.
- **Ambiguity Score**: 1

## 2. The Actor Matrix
| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| GlobalLanguageServerPool | Owns timeout_manager, calls start_monitoring | Must not start monitoring before first acquire |
| LSPTimeoutManager | Manages monitoring thread lifecycle | Must not auto-start without explicit call |
| MCP Session (external) | Triggers acquire via project activation | No direct timeout_manager access |

## 3. The State Transition
- **Initial State ($S_0$)**: Pool initialized, timeout_manager exists with callback wired, `is_monitoring() == False`, no daemon thread
- **Transformation**: First `acquire()` call completes successfully (LSP created or shared)
- **Terminal State ($S_1$)**: `is_monitoring() == True`, daemon thread running, LOG-TMO-01 emitted, subsequent acquires do not re-trigger start

## 3.5 Integration Specification

### Dependency Graph
- GlobalLanguageServerPool DEPENDS ON LSPTimeoutManager for idle LSP detection
- LSPTimeoutManager._monitor_loop DEPENDS ON start_monitoring() being called to launch thread
- Pool._on_idle_timeout DEPENDS ON monitor_loop detecting idle languages

### Control Flow Requirements (Sequencing Specs)
| ID | Caller | Must Invoke | Temporal Constraint | Breaks If Missing |
|----|--------|-------------|---------------------|-------------------|
| SEQ-TMO-INIT-01 | `GlobalLanguageServerPool.acquire()` | `self.timeout_manager.start_monitoring()` | AFTER first successful LSP acquisition (before returning LSP to caller) | Monitoring thread never starts → idle LSPs never reclaimed → resource leak |

### Integration Points Checklist
| ID | Source (class.method) | Target (class.method) | Handoff Data | Contract Clause |
|----|----------------------|----------------------|-------------|-----------------|
| IP-1 | `Pool.acquire()` (first success) | `timeout_manager.start_monitoring()` | None (void) | SEQ-TMO-INIT-01 |
| IP-2 | `Pool.__init__()` | `timeout_manager.set_reclaim_callback()` | `_on_idle_timeout` | Already wired |
| IP-3 | `Pool.acquire()` (every call) | `timeout_manager.touch()` | language string | Already wired |

### Lifecycle Paths
| Component | INIT (created/started by) | CLEANUP (stopped/released by) |
|-----------|--------------------------|-------------------------------|
| LSPTimeoutManager | Created in Pool.__init__, monitoring started after first acquire() | stop_monitoring() during Pool.stop_all() |
| Monitoring thread | Launched by start_monitoring() as daemon=True | Dies with process OR stop_monitoring() sets stop_event |

## 4. Hard Invariants (The "Never" List)
| ID | Category | Invariant |
|----|----------|-----------|
| INV-TMO-01 | Idempotency | start_monitoring() MUST be safe to call multiple times (internal guard) |
| INV-TMO-02 | Thread safety | start_monitoring() call MUST occur within pool_lock scope |
| INV-TMO-03 | Resource | Monitoring thread MUST be daemon (no zombie threads) |

## 5. High-Entropy Zones (Adjudicated)
| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| Call location | Inside pool_lock or after? | Inside pool_lock for atomicity | User (implicit: "after the first acquire" = within acquire method) |
| Idempotency | start_monitoring has internal guard — rely on it? | Yes, but contract tests verify first-acquire semantics | AI recommendation, consistent with existing code |

## 5.5 Rejected Alternatives
| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Call in acquire() after first success | Call in __init__() | __init__ is too early — no LSP exists yet, monitoring pointless |
| Call in acquire() after first success | Call in a separate init_monitoring() method | Over-engineering — acquire is the natural trigger |
| Inside pool_lock | Outside pool_lock | Pool_lock ensures atomicity of acquire + monitoring start |

## 6. Tool/API Interface Summary
| Interface | Purpose | Mutates State? | Called By | Triggered When |
|-----------|---------|----------------|----------|---------------|
| start_monitoring() | Launch daemon thread for idle checking | YES (creates thread) | Pool.acquire() | First successful acquisition |
| is_monitoring() | Query monitoring status | NO | Tests, diagnostics | Verification |
| touch(language) | Update last-used timestamp | YES (dict update) | Pool.acquire() | Every acquisition |

## 6.5 Blocking Dependencies
| Unresolved Zone | Blocks |
|-----------------|--------|
| None | — |

## 7. Completion Promise (Ralph Loop Exit)
> After calling `pool.acquire(language, workspace, session_id)` on a real `GlobalLanguageServerPool` instance, `pool.timeout_manager.is_monitoring()` MUST return `True`, AND the `LOG-TMO-01` log message ("[LSP-Timeout] Monitoring started") MUST have been emitted. This cannot be satisfied by mocks. Subsequent acquire() calls must NOT emit LOG-TMO-01 again.

## 8. Contract Authority
**Authoritative Source**: `contracts/timeout_wiring_contract.py`

```
REQ-TMO-WIRING-001.md (this file)
        ↓
contracts/timeout_wiring_contract.py
        ↓
tests/test_timeout_wiring_contract.py
        ↓
src/serena/global_lsp_pool.py (acquire method)
```

## 9. Revision History
| Date | Author | Change |
|------|--------|--------|
| 2026-02-07 | User + AI | Initial manifest from req-elicit |
