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
