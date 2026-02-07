# REQ-GRACEFUL-SHUTDOWN-001: Graceful LSP Shutdown on Server Restart

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
  > "what happens to lsp resource when we restart the host http server?"
  >
  > "yes, wire up the shutdown path. follow full CCABDD with /constitutional-orchestrator
  > fix all gaps. I expect that our version of serena will clean up after itself"
- **Our Understanding**: When the Serena MCP HTTP server is restarted (SIGTERM from launchd),
  LSP subprocesses become orphaned zombies because no shutdown hook exists. Four gaps:
  (1) No SIGTERM handler, (2) shutdown() doesn't call stop_all(), (3) stop_all() doesn't call
  stop_monitoring(), (4) No cache save on HTTP server shutdown. Wire up the full cleanup chain
  so Serena cleans up after itself.
- **Ambiguity Score**: 1

## 2. The Actor Matrix
| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| launchd | Sends SIGTERM to server process | Cannot SIGKILL without waiting |
| Signal handler (SIGTERM) | Calls agent.shutdown() | Must not start new work |
| SerenaAgent.shutdown() | Stops pool, deactivates sessions | Must not replace pool (INV-PI-01) |
| GlobalLanguageServerPool.stop_all() | Stops all LSPs, clears pool | Must not leave orphaned processes |
| LSPTimeoutManager.stop_monitoring() | Stops monitoring thread | Must not block indefinitely |
| atexit hook | Calls agent.shutdown() as fallback | Same constraints as signal handler |

## 3. The State Transition
- **Initial State ($S_0$)**: Server running, N LSP subprocesses alive, monitoring thread active,
  M active sessions, pool populated with LSP instances
- **Transformation**: SIGTERM received → cleanup chain executes
- **Terminal State ($S_1$)**: All LSP subprocesses terminated, monitoring thread stopped,
  caches saved, pool empty, process exits cleanly

## 3.5 Integration Specification

### Dependency Graph
- Signal handler DEPENDS ON SerenaAgent.shutdown() for orchestrating cleanup
- SerenaAgent.shutdown() DEPENDS ON GlobalLanguageServerPool.stop_all() for LSP cleanup
- GlobalLanguageServerPool.stop_all() DEPENDS ON LSPTimeoutManager.stop_monitoring() for thread cleanup
- GlobalLanguageServerPool.stop_all() DEPENDS ON SolidLanguageServer.stop() for subprocess cleanup
- atexit hook DEPENDS ON SerenaAgent.shutdown() as fallback path

### Control Flow Requirements (Sequencing Specs)
| ID | Caller | Must Invoke | Temporal Constraint | Breaks If Missing |
|----|--------|-------------|---------------------|-------------------|
| SEQ-SHUT-01 | Signal handler (SIGTERM) in start_mcp_server() | `agent.shutdown()` | IMMEDIATELY on SIGTERM receipt | Agent never shuts down, LSPs orphaned |
| SEQ-SHUT-02 | `SerenaAgent.shutdown()` | `self._lsp_pool.stop_all(save_cache=True)` | AFTER session deactivation, BEFORE process exit | LSP subprocesses orphaned, cache lost |
| SEQ-SHUT-03 | `GlobalLanguageServerPool.stop_all()` | `self.timeout_manager.stop_monitoring()` | AFTER all LSPs stopped, BEFORE returning | Monitoring thread not explicitly stopped |
| SEQ-SHUT-04 | `atexit.register()` in start_mcp_server() | `agent.shutdown()` | As fallback if signal handler didn't fire | No cleanup on non-signal exit paths |

### Integration Points Checklist
| ID | Source (class.method) | Target (class.method) | Handoff Data | Contract Clause |
|----|----------------------|----------------------|-------------|-----------------|
| IP-1 | SIGTERM handler in start_mcp_server() | SerenaAgent.shutdown() | None (void) | SEQ-SHUT-01 |
| IP-2 | SerenaAgent.shutdown() | lsp_pool.stop_all(save_cache=True) | save_cache=True | SEQ-SHUT-02 |
| IP-3 | GlobalLanguageServerPool.stop_all() | timeout_manager.stop_monitoring() | None (void) | SEQ-SHUT-03 |
| IP-4 | atexit.register() in start_mcp_server() | SerenaAgent.shutdown() | None (void) | SEQ-SHUT-04 |

### Lifecycle Paths
| Component | INIT (created/started by) | CLEANUP (stopped/released by) |
|-----------|--------------------------|-------------------------------|
| SerenaAgent | Created in start_mcp_server() | SIGTERM handler or atexit calls shutdown() |
| GlobalLanguageServerPool | Lazy-created by SerenaAgent.get_lsp_pool() | shutdown() calls stop_all(save_cache=True) |
| LSPTimeoutManager | Created in Pool.__init__(), monitoring started after first acquire() | stop_all() calls stop_monitoring() |
| SolidLanguageServer | Created by Pool._create_lsp() during acquire() | stop_all() calls lsp.stop() for each |

## 4. Hard Invariants (The "Never" List)
| ID | Category | Invariant |
|----|----------|-----------|
| INV-SHUT-01 | Idempotency | shutdown() MUST be safe to call multiple times (signal + atexit may both fire). Uses threading.Lock + boolean flag. |
| INV-SHUT-02 | Timeout | stop_all() MUST NOT block indefinitely — each LSP stop has existing timeout |
| INV-SHUT-03 | No new work | After shutdown begins, best-effort prevention of new acquire() starting new LSPs |
| INV-SHUT-04 | Thread safety | shutdown() uses threading.Lock + flag for safe concurrent access from signal handler and atexit |

## 5. High-Entropy Zones (Adjudicated)
| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| Idempotency mechanism | Boolean guard vs threading lock vs Event? | Threading lock + flag — ensures no race condition if signal and atexit fire in close proximity during kernel context switch | User: "B is the honest choice" |
| Signal handler location | Agent __init__ vs CLI entry point vs standalone function? | start_mcp_server() CLI entry point — signal handlers are a Process Concern, not a Domain Concern | User: "Option A is the only correct architectural choice" |

## 5.5 Rejected Alternatives
| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Threading lock + flag | Simple boolean `_shutdown_called` | Race condition possible if signal and atexit fire near-simultaneously during context switch |
| Threading lock + flag | threading.Event | Overkill for this use case |
| Handler in start_mcp_server() | Handler in SerenaAgent.__init__() | Signal handling is Process Concern, not Domain Concern. Agent used in tests without wanting signal handlers |
| Handler in start_mcp_server() | Standalone register_shutdown_hooks() | Unnecessary indirection for a single registration site |

## 6. Tool/API Interface Summary
| Interface | Purpose | Mutates State? | Called By | Triggered When |
|-----------|---------|----------------|----------|---------------|
| signal.signal(SIGTERM, handler) | Register cleanup handler | YES (process signal table) | start_mcp_server() | Server startup |
| atexit.register(fn) | Register fallback cleanup | YES (atexit registry) | start_mcp_server() | Server startup |
| SerenaAgent.shutdown() | Orchestrate full cleanup | YES (stops pool, sessions) | Signal handler, atexit | SIGTERM or process exit |
| GlobalLanguageServerPool.stop_all(save_cache) | Stop all LSPs | YES (empties pool) | shutdown() | During cleanup |
| LSPTimeoutManager.stop_monitoring() | Stop monitor thread | YES (joins thread) | stop_all() | During pool cleanup |

## 6.5 Blocking Dependencies
| Unresolved Zone | Blocks |
|-----------------|--------|
| None | — |

## 7. Completion Promise (Ralph Loop Exit)
> After sending SIGTERM to the Serena server process, ALL of the following MUST be true:
> 1. `lsp_pool.stop_all()` was called (evidenced by LOG-POOL-04 in logs)
> 2. `timeout_manager.stop_monitoring()` was called (evidenced by LOG-TMO-02 in logs)
> 3. shutdown() is idempotent — calling it twice produces no errors
> 4. Process exits cleanly
>
> Unit-testable observables:
> - shutdown() calls stop_all(save_cache=True) on the pool
> - stop_all() calls stop_monitoring() on the timeout manager
> - shutdown() with lock+flag is idempotent (second call is no-op)
> - SIGTERM handler and atexit hook are registered in start_mcp_server()

## 8. Contract Authority
**Authoritative Source**: `contracts/graceful_shutdown_contract.py`

```
contracts/REQ-GRACEFUL-SHUTDOWN-001.md (this file)
        ↓
contracts/graceful_shutdown_contract.py
        ↓
tests/test_graceful_shutdown_contract.py
        ↓
src/serena/agent.py (shutdown method)
src/serena/global_lsp_pool.py (stop_all method)
src/serena/cli.py (start_mcp_server signal/atexit registration)
```

## 9. Revision History
| Date | Author | Change |
|------|--------|--------|
| 2026-02-07 | User + AI | Initial manifest from req-elicit |
