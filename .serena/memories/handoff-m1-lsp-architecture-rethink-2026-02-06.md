# M1 Handoff: LSP Architecture Rethink

**Date**: 2026-02-06 (updated 2026-02-06 evening)
**Branch**: ketema (renamed from feature/multi-project-support → feature/polyglot-support → ketema)
**Prior Session**: Multi-project debug investigation → discovered fundamental architecture mismatch
**Next Macro**: /req-elicit Phase 1 (Phase 0 COMPLETE — user confirmed intent mirroring)

---

## /req-elicit Phase 0 — COMPLETE

**User confirmed** the following understanding is accurate:

The Serena HTTP server runs as a shared service — multiple MCP clients connect simultaneously, each activating one project. LSP instances (like Pyright) are shared resources: one Pyright serves all Python workspaces. The problem is authority mismatch: code still treats LSPs as client-owned (inherited from STDIO 1:1 model). Two proven failure modes:

1. **Cascade destruction** — Any client can nuke the entire LSP pool (via restart_language_server or auto error handler), destroying all other clients' in-flight operations.
2. **Indexing race** — After add_workspace_root, Pyright needs indexing time. During this window, tool calls may resolve against the wrong workspace.

**What we're building**: Server-centric LSP lifecycle manager where server exclusively owns LSP creation/health/recovery, clients request operations but cannot control lifecycle, new workspaces have indexing-aware readiness gates, and LSP crashes trigger surgical per-language restart.

**Phase 1 (Collaborative Extraction)** is the next step.

---

## Cleanup Done This Session

- Debug instrumentation removed from agent.py, global_lsp_pool.py, lsp_capability_adapter.py
- Debug pattern saved to memory: `debug-instrumentation-pattern`
- Branches consolidated: only `main` and `ketema` remain (local + remote)
- Branching model saved to memory: `branching-model`

---

## The Problem (Proven by Live Testing)

The current Serena HTTP server architecture treats LSPs as client-owned resources despite running as a shared server. The mental model is still `1 MCP client → 1 project → 1 LSP`, inherited from the original STDIO transport where each Claude Desktop window was its own Serena process.

In the HTTP multi-project reality:
- Multiple MCP clients connect to ONE server
- Each client activates ONE project (1:1 client→project mapping)
- LSPs are shared across projects (Pyright serves Python for all clients)
- But the server has NO authority over LSP lifecycle — clients can nuke the entire pool via `restart_language_server`, and the automatic error handler in `tools_base.py:282-286` does the same thing on any `LanguageServerTerminatedException`

### Cascade Failure (Observed)
Client A's tool fails → pool nuked → Client B's in-flight call fails → pool nuked → infinite loop. Each nuke replaces `GlobalLanguageServerPool()` entirely — all languages, all workspaces gone.

### First-Call Timing Window (Observed)
When a new project connects and `add_workspace_root` fires, the `workspace/didChangeWorkspaceFolders` notification is fire-and-forget. Pyright needs time to index the new workspace. First tool call may resolve paths against `repo_root` (the first session's workspace) instead of the new workspace. Subsequent calls succeed after indexing completes.

---

## The Architectural Shift Required

**FROM**: Client-centric (each client manages its own LSP lifecycle)
**TO**: Server-centric (server owns and manages the LSP pool as a shared resource)

### New Mental Model

```
SERVER (authority)
  └── LSP Pool (server-managed lifecycle)
       ├── Pyright (Python) — serves N workspaces
       ├── typescript-language-server — serves M workspaces  
       └── ... per language
            │
            ├── Workspace: /projects/serena (indexed ✓)
            ├── Workspace: /projects/OpenMemory (indexing...)
            └── Workspace: /projects/ramp (indexed ✓)
                 │
                 └── MCP Clients map 1:1 to active projects
                      ├── Client A → serena project
                      ├── Client B → OpenMemory project
                      └── Client C → ramp project
```

### Key Design Principles

1. **Server owns LSP lifecycle** — clients CANNOT restart, kill, or replace LSPs. The `restart_language_server` tool is already disabled via config, but the automatic restart in `tools_base.py` also needs to change.

2. **Pool is a shared resource** — LSP instances serve multiple workspaces. Pool management (creation, health monitoring, restart) is server-side responsibility.

3. **Indexing-aware request gating** — When a new workspace root is added to an LSP, the server MUST track indexing status. Tool calls targeting an unindexed workspace should either:
   - Block until indexing confirms readiness (synchronous wait with timeout)
   - Return a structured "resource not ready" / WAIT error that clients can understand and retry
   - The server should NOT silently serve stale/wrong results from a different workspace

4. **Surgical LSP recovery** — When an LSP crashes, server restarts ONLY that LSP instance, not the entire pool. Other languages and workspaces are unaffected.

---

## Specific Code Areas to Examine

- `src/serena/tools/tools_base.py:282-286` — automatic pool nuke on LSP termination (must become surgical per-LSP restart)
- `src/serena/agent.py:806-810` — `reset_language_server()` replaces entire pool (needs rethink or removal)
- `src/serena/global_lsp_pool.py` — pool acquire/release logic (needs indexing state tracking)
- `src/serena/lsp_capability_adapter.py:267` — `add_workspace_root` sends notification with no indexing wait (needs readiness gate)
- `src/serena/tools/symbol_tools.py:33-41` — `RestartLanguageServerTool` (already config-disabled, may need code-level removal for HTTP mode)

## Existing Contracts to Reference

- `contracts/global_lsp_pool_contract.py` — INV-3: multi-root keyed by language
- `contracts/lsp_workspace_multiplexing_contract.py` — INV-1: shared instances
- `contracts/solidlsp_path_resolution_contract.py` — workspace_root parameter contracts
- `contracts/session_context_contract.py` — session lifecycle
- `src/serena/session_registry.py` — inline contracts for session management

## Recent Commits (Context)

- `a9ac16ce` fix(session): Fail fast when session not registered (INV-06, ERRORS-2)
- `0ae1b375` fix(lsp): Implement real add/remove_workspace_root (CL3/CL12 fix)
- `071e7690` fix(session): Add idempotency to on_transport_session_created for POST-4 race
- Prior REQ-2026-003 (path resolution) and REQ-2026-004 (session isolation) work is GREEN

## Config Change Already Made

`~/.serena/serena_config.yml`: `restart_language_server` added to global `excluded_tools`. This is a stopgap — the real fix is architectural.

## CCABDD Workflow Entry Point

This needs full CCABDD treatment:
1. `/req-elicit` Phase 0 ✅ COMPLETE — Phase 1 next
2. `/design-by-contract` — contracts for pool lifecycle, indexing gates, surgical restart
3. `/adversarial-test-writer` → `/adversarial-coder` — TDD cycle
4. Live multi-project validation (3+ clients) as M4.6 execution gate

The debug server setup (PORT 9122, SERENA_DEBUG=1, PATH with .venv) is documented in `multi-project-debug-2026-02-06-findings` memory if needed for live testing.
