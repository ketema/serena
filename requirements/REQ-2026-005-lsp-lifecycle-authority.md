# REQ-2026-005: Server-Centric LSP Lifecycle Authority

## CCABDD Governance

Human owns: intent (front) + reality judgment (back).
AI owns: enforcement (middle).
Neither crosses the boundary.

Human MUST confirm real-world effect matches intent.
AI MAY NOT infer success from metrics.

**INV-3**: No discretion. No judgment. Only state.
CONTRACT SHALL NOT execute unless ALL predicates evaluate to TRUE.

Full Actor Responsibility Model: →serena:ccabdd-manifesto

---

## 1. Intent Traceability

- **Source Prose**:
  > "this is not operationally sound. each AI mcp client is not aware of the other, so they
  > will call restart language server at the first sign of their call failing and this could
  > be right when another ai client is making a call so that will fail and back and forth it
  > will go. we need to ensure that restart language server is not called by an external client."
  >
  > (Confirmed cascade failure + indexing race via live multi-client testing, 2026-02-06)
  >
  > Phase 0 user confirmation: "The Serena HTTP server runs as a shared service — multiple MCP
  > clients connect simultaneously, each activating one project. LSP instances are shared
  > resources. The problem is authority mismatch: code still treats LSPs as client-owned."

- **Our Understanding**: The Serena HTTP server must shift from client-centric to server-centric
  LSP lifecycle management. The server exclusively owns LSP creation, health monitoring, and
  recovery. Clients request operations but cannot control LSP lifecycle. New workspaces have
  probe-based readiness gates with blocking timeout. LSP crashes trigger surgical per-language
  restart, not pool-wide destruction.

- **Ambiguity Score**: 2 (Ready for contracts)

## 2. The Actor Matrix

| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| **Server (LSP Lifecycle Manager)** | Create, restart (surgical), health-check, destroy LSPs | N/A — full authority over LSP lifecycle |
| **MCP Client (via SessionContext)** | Request tool operations, activate project, receive results | Restart LSPs, replace pool, trigger pool-wide operations |
| **GlobalLanguageServerPool** | Manage LSP instances, track refs, acquire/release | Self-destruct (wholesale replacement) while sessions active |
| **SerenaAgent** | Dispatch tool calls, own pool reference | Replace `_lsp_pool` while sessions active |
| **tools_base.py auto-handler** | Catch `LanguageServerTerminatedException`, request surgical restart | Trigger pool nuke (`reset_language_server()`) |

## 3. The State Transition

- **Initial State ($S_0$)**: Client-centric model where any client can nuke the LSP pool
  via `RestartLanguageServerTool` or automatic error handler in `apply_ex`. No indexing
  awareness. `reset_language_server()` replaces entire `GlobalLanguageServerPool()`.

- **Transformation**: Implement server-centric LSP lifecycle authority with surgical
  restart, probe-based readiness gates, and client isolation.

- **Terminal State ($S_1$)**: Server owns LSP lifecycle exclusively. Clients cannot trigger
  restarts. LSP crashes cause surgical per-language restart with workspace root restoration.
  New workspaces block until probe-based readiness confirms indexing complete. Cross-client
  isolation guaranteed during recovery.

## 4. Hard Invariants (The "Never" List)

| ID | Category | Invariant |
|----|----------|-----------|
| INV-01 | Isolation | No single client operation SHALL destroy another client's LSP session |
| INV-02 | Pool Integrity | Pool SHALL NOT be replaced wholesale (`GlobalLanguageServerPool()`) while any session is active |
| INV-03 | Surgical Recovery | LSP restart SHALL affect ONLY the crashed language's LSP instance, not the entire pool |
| INV-04 | Workspace Accounting | Every tracked workspace root SHALL have at least one active session referencing it |
| INV-05 | Readiness | No tool call SHALL be dispatched to an LSP for a workspace that has not passed the readiness probe |
| INV-06 | Authority | In HTTP mode, clients SHALL NOT have any mechanism (tool or automatic) to trigger pool-wide or LSP-wide restart |

## 5. High-Entropy Zones (Adjudicated)

| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| Indexing gate behavior | Block, return error, or best-effort? | Block with timeout | User |
| Readiness detection method | Time-based, probe-based, or hybrid? | Probe-based (send test request, retry until valid or timeout) | User |
| Scope boundary | Health monitoring daemon in this cycle? | OUT — deferred to future cycle | User |
| Client notifications | Notify clients of LSP state changes? | OUT — deferred to future cycle | User |
| Same-project clients | Two clients activate same project? | Reference counting — root removed when LAST client disconnects | User+AI |
| Pool nuke paths | Which reset paths exist? | Both: explicit tool + automatic `apply_ex` handler. Both must change. | AI (confirmed by user) |

## 5.5 Rejected Alternatives

| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Block with timeout (indexing) | Return immediate WAIT error | Clients (AI agents) may not handle retry elegantly; blocking is simpler |
| Block with timeout (indexing) | Best-effort + warning | Risk of returning wrong-workspace results; violates correctness |
| Probe-based readiness | Time-based delay | Brittle — large projects need more time, small projects waste time |
| Probe-based readiness | Hybrid (delay then probe) | Unnecessary complexity; probe alone with retry loop achieves same result |
| Surgical restart | Keep pool-wide restart | Violates INV-01, INV-03 — proven cascade failure in live testing |

## 5.6 Phase 2.5: Dependency Edge Enumeration (Integration Wiring)

### Component Dependency Graph

**Nodes** (components):
- `GlobalLanguageServerPool` — LSP instance management with pooling
- `LSPTimeoutManager` — Idle timeout monitoring + reclamation
- `LSPCapabilityAdapter` (via `LSPAdapterRegistry`) — Multi/single-root routing + workspace management
- `McpSessionBridge` — MCP transport session lifecycle
- `Tool.apply_ex()` — Tool dispatch with exception handling
- `SerenaAgent` — Agent lifecycle, pool ownership
- `probe_workspace_readiness()` — Readiness gate for new workspaces
- `surgical_restart_lsp()` — Per-language surgical restart

**Edges** (dependency relationships — each is a potential wiring failure point):

| Edge ID | Caller | Callee | When | Category |
|---------|--------|--------|------|----------|
| E-1 | `GlobalLanguageServerPool.__init__()` | `LSPTimeoutManager.set_reclaim_callback()` | Pool construction | INIT |
| E-2 | `GlobalLanguageServerPool.acquire()` | `LSPAdapterRegistry.get_adapter()` | Session needs LSP | OPERATION |
| E-3 | `GlobalLanguageServerPool.acquire()` | `adapter.add_workspace_root(lsp, root)` | Multi-root, new workspace | OPERATION |
| E-4 | `GlobalLanguageServerPool.acquire()` | `LSPTimeoutManager.touch(language)` | LSP accessed | OPERATION |
| E-5 | `GlobalLanguageServerPool.release()` | `LSPTimeoutManager.touch(language)` | Session releases LSP | CLEANUP |
| E-6 | `McpSessionBridge.on_transport_session_closed()` | `GlobalLanguageServerPool.release()` | Transport disconnects | CLEANUP |
| E-7 | `Tool.apply_ex()` | `handle_lsp_termination()` | LSP crashed during tool | ERROR |
| E-8 | `handle_lsp_termination()` | `surgical_restart_lsp(language)` | Restarting crashed LSP | ERROR |
| E-9 | `surgical_restart_lsp()` | `adapter.add_workspace_root(new_lsp, root)` | Restoring roots after restart | ERROR |
| E-10 | `acquire()` (new workspace) | `probe_workspace_readiness(lsp, root)` | Readiness gate | OPERATION |

### Integration Points (IP)

| IP ID | Integration Point | Components Involved | Failure Mode if Unwired |
|-------|-------------------|---------------------|------------------------|
| IP-1 | Pool init → timeout setup | Pool, TimeoutManager | Idle LSPs never reclaimed (memory leak) |
| IP-2 | Acquire → workspace routing | Pool, AdapterRegistry | Wrong LSP serves workspace |
| IP-3 | Acquire → readiness gate | Pool, probe_workspace_readiness | Tool calls dispatched to un-indexed workspace |
| IP-4 | Session close → pool release | McpSessionBridge, Pool | Ref count leak, LSPs never reclaimed |
| IP-5 | Tool exception → surgical restart | apply_ex, handle_lsp_termination, surgical_restart_lsp | Pool nuke instead of surgical restart |
| IP-6 | Surgical restart → root restoration | surgical_restart_lsp, adapter.add_workspace_root | Workspaces lost after restart |

### Sequencing Chains

**INIT_CHAIN** (Pool construction):
```
GlobalLanguageServerPool.__init__()
  → LSPTimeoutManager() (create)
  → timeout_manager.set_reclaim_callback(self._on_idle_timeout)  [E-1]
```

**ACQUIRE_CHAIN** (Session requests LSP):
```
GlobalLanguageServerPool.acquire(language, workspace_root, session_id)
  → capability_registry.get_adapter(language)  [E-2]
  → adapter.add_workspace_root(lsp, root)  [E-3, if multi-root + new root]
  → timeout_manager.touch(language)  [E-4]
  → probe_workspace_readiness(lsp, root)  [E-10, if new workspace]
```

**CLEANUP_CHAIN** (Session disconnects):
```
McpSessionBridge.on_transport_session_closed(session_id)
  → GlobalLanguageServerPool.release(language, root, session_id)  [E-6]
  → timeout_manager.touch(language)  [E-5]
  → (if ref_count == 0) idle timer starts → _on_idle_timeout → reclaim
```

**ERROR_CHAIN** (LSP crashes during tool):
```
Tool.apply_ex(**kwargs)
  → catches LanguageServerTerminatedException
  → handle_lsp_termination(language, root, retry_fn)  [E-7]
  → surgical_restart_lsp(language)  [E-8]
  → adapter.add_workspace_root(new_lsp, root) for each root  [E-9]
  → probe_workspace_readiness(new_lsp, root)
  → retry_fn() (retry original tool call)
```

### Phase 2.5 Completeness Checklist

- [x] All component dependencies graphed (8 nodes, 10 edges)
- [x] Every dependency edge has a SEQ clause placeholder (E-1 through E-10)
- [x] Sequencing chains documented (INIT_CHAIN, ACQUIRE_CHAIN, CLEANUP_CHAIN, ERROR_CHAIN)
- [x] Integration points enumerated with IDs (IP-1 through IP-6)
- [x] Every IP has corresponding SEQ-N placeholder for /design-by-contract
- [x] Lifecycle paths complete for ALL components (INIT + CLEANUP minimum)

---

## 6. Tool/API Interface Summary

| Interface | Purpose | Mutates State? | Change Required |
|-----------|---------|----------------|-----------------|
| `GlobalLanguageServerPool.acquire()` | Get/create LSP for session | YES (creates LSP, adds ref) | Add readiness gate after workspace root addition |
| `GlobalLanguageServerPool.release()` | Release session's LSP ref | YES (decrements ref, may remove workspace) | No change needed |
| `SerenaAgent.reset_language_server()` | Replace entire pool | YES (destroys all LSPs) | Replace with surgical per-language restart |
| `Tool.apply_ex()` auto-handler | Catch LSP termination, nuke+retry | YES (replaces pool) | Change to surgical restart of crashed LSP only |
| `RestartLanguageServerTool.apply()` | Client-triggered pool nuke | YES (replaces pool) | Disable at code level for HTTP mode (return error) |
| `BaseMultiRootAdapter.add_workspace_root()` | Add workspace to LSP | YES (sends LSP notification) | Add probe-based readiness gate after notification |
| NEW: `surgical_restart_lsp(language)` | Restart single LSP, restore roots | YES (stops/starts one LSP) | New method on pool or lifecycle manager |
| NEW: `probe_workspace_readiness(ls, root, timeout)` | Block until LSP indexes workspace | NO (read-only probes) | New function |

## 6.5 Blocking Dependencies

| Unresolved Zone | Blocks |
|-----------------|--------|
| None | All zones adjudicated |

## 7. Completion Promise (Ralph Loop Exit)

> Three MCP clients connected simultaneously to different Python projects. Client B's LSP
> operation triggers a `LanguageServerTerminatedException`. After recovery:
>
> 1. Client A's next tool call succeeds without re-activation, without error, and returns
>    correct workspace-scoped results.
> 2. Client C's next tool call succeeds without re-activation, without error, and returns
>    correct workspace-scoped results.
> 3. Client B's retry succeeds after the surgical restart completes.
> 4. All three clients' workspace roots are present in the restarted Pyright instance.
>
> Additionally: A new client D connects and activates a fourth Python project. Client D's
> first tool call blocks until the probe confirms Pyright has indexed the new workspace,
> then returns correct results.

## 8. Contract Authority

**Authoritative Source**: `contracts/lsp_lifecycle_authority_contract.py`

```
requirements/REQ-2026-005-lsp-lifecycle-authority.md (this file)
        ↓
contracts/lsp_lifecycle_authority_contract.py
        ↓
tests/test_lsp_lifecycle_authority_contract.py
        ↓
src/serena/global_lsp_pool.py (surgical restart, readiness gate)
src/serena/tools/tools_base.py (apply_ex handler change)
src/serena/agent.py (reset_language_server replacement)
src/serena/lsp_capability_adapter.py (readiness probe after add_workspace_root)
src/serena/tools/symbol_tools.py (RestartLanguageServerTool HTTP guard)
```

## 9. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-06 | ketema + AI | Initial manifest from /req-elicit (Phases 0-6) |
| 2026-02-06 | AI (constitutional-fix) | Added Phase 2.5 completeness: dependency edges, IPs, sequencing chains |
