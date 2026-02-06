# REQ-2026-003: SolidLanguageServer Path Resolution Fix

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
  > "What does the constitution say? No to option A. one of the feature requirements is resource conservation. Option B is the correct answer."
  > "If the mandatory approach would produce reliable consistent correct behavior I think that is the right solution. We can use the ralph wiggum loop to ensure you update EVERY caller without exiting until finished."
  > "yes, update the plan and proceed to contracts"

- **Our Understanding**: Fix ~20 methods in `SolidLanguageServer` that resolve relative paths against `repository_root_path` (set at LSP creation time) instead of the current session's workspace root. Add mandatory `workspace_root: str` parameter to all affected public methods. Add 4 centralized helper methods. Update all callers in symbol.py, code_editor.py, and tests.

- **Ambiguity Score**: 1 (all key decisions resolved in dialogue)

## 2. The Actor Matrix

| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| Serena caller (symbol.py, code_editor.py) | MUST pass workspace_root to every LSP method call | MAY NOT omit workspace_root parameter |
| SolidLanguageServer public method | Resolves paths using workspace_root parameter | MAY NOT fall back to repository_root_path for path resolution |
| SolidLanguageServer helper (_resolve_path, etc.) | Validates and resolves paths | MAY NOT accept absolute relative_path (ValueError) |
| LSP subclass (_start_server methods) | Uses repository_root_path for LSP process init | NOT affected — ZERO changes required |
| Test code | MUST pass workspace_root explicitly in all calls | MAY NOT rely on default/fallback behavior |

## 3. The State Transition

- **Initial State ($S_0$)**: ~20 public methods in SolidLanguageServer use `self.repository_root_path` for path resolution. For shared multi-root LSPs (pool key = Language only), all sessions resolve paths against the first session's workspace root.
- **Transformation**: Add mandatory `workspace_root: str` parameter to all ~20 public methods. Add 4 centralized helper methods (`_resolve_path`, `_resolve_uri`, `_make_cache_key`, `_effective_root`). Update ALL callers (symbol.py, code_editor.py, tests) to pass workspace_root.
- **Terminal State ($S_1$)**: All path resolution uses caller-provided workspace_root. Shared multi-root LSPs correctly resolve paths per-session. Cache keys include workspace_root for isolation.

## 4. Hard Invariants (The "Never" List)

| ID | Category | Invariant |
|----|----------|-----------|
| INV-01 | Path Resolution | Path resolution MUST use workspace_root parameter, NEVER self.repository_root_path |
| INV-02 | Parameter Contract | workspace_root MUST be mandatory (not Optional) on ALL affected public methods |
| INV-03 | Absolute Path Rejection | _resolve_path MUST raise ValueError if relative_path is absolute |
| INV-04 | Cache Isolation | Cache keys MUST include workspace_root to prevent cross-workspace pollution |
| INV-05 | Subclass Safety | 35+ LSP subclass files MUST require ZERO changes |
| INV-06 | Resource Conservation | Multi-root LSPs MUST remain shared (one instance per language, per CON-3) |
| INV-07 | repository_root_path Scope | repository_root_path retained ONLY for: cache directory paths, LSP process initialization, subclass _start_server methods |

## 5. High-Entropy Zones (Adjudicated)

| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| Mandatory vs Optional | Should workspace_root be Optional with fallback to repository_root_path? | MANDATORY — eliminates silent fallback trap where callers forget parameter and get broken behavior that tests don't catch | User (verbatim: "If the mandatory approach would produce reliable consistent correct behavior I think that is the right solution") |
| Resource Conservation | Should we create per-workspace LSP instances? | NO — violates CON-3 resource conservation | User (verbatim: "No to option A. one of the feature requirements is resource conservation") |
| Subclass Impact | Do 35+ LSP subclass files need changes? | NO — subclasses implement _start_server, not the 20 path-resolving methods | AI analysis, User confirmed |
| Cache Key Design | Should cache keys include workspace_root? | YES — prevents cross-workspace cache pollution | AI Panel recommendation R3, accepted |
| repository_root_path Retention | Remove repository_root_path entirely? | NO — still needed for cache dirs, LSP init, subclass methods | AI analysis, User confirmed |

## 5.5 Rejected Alternatives

| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Mandatory workspace_root (Option B) | Optional workspace_root with fallback | Silent fallback trap: callers who forget parameter silently get wrong behavior. Tests pass in single-project mode, fail only in multi-project production. AI Panel scored 6/10 due to R2 (silent fallback) and R4 (test masking) risks. |
| Shared multi-root LSPs (keep existing) | Per-workspace LSP instances (Option A) | Violates CON-3 resource conservation. Each new workspace = new LSP process = unbounded memory growth. |
| Caller-layer parameter (Option B) | Session-aware LSP (Option C) | Violates CON-1 (Serena owns isolation, LSPs don't know sessions). Over-engineering that couples LSP layer to session management. |

## 6. Tool/API Interface Summary

| Interface | Purpose | Mutates State? |
|-----------|---------|----------------|
| `_effective_root(workspace_root: str) -> Path` | Validate workspace_root, return Path | NO |
| `_resolve_path(workspace_root: str, relative_path: str) -> Path` | Central path resolution: workspace_root + relative_path | NO |
| `_resolve_uri(workspace_root: str, relative_path: str) -> str` | Build file:// URI from workspace_root + relative_path | NO |
| `_make_cache_key(workspace_root: str, *args) -> str` | Build cache key including workspace_root for isolation | NO |
| ~20 public methods (+ workspace_root: str param) | All path-resolving methods get mandatory parameter | EXISTING behavior unchanged |

### Affected Public Methods (SolidLanguageServer)

1. `request_overview(within_relative_path, workspace_root)`
2. `request_document_symbols(relative_path, workspace_root)`
3. `open_file(relative_path, workspace_root)`
4. `request_full_symbol_tree(within_relative_path, workspace_root)`
5. `request_referencing_symbols(file_path, position, workspace_root)`
6. `request_hover(file_path, position, workspace_root)`
7. `rename_symbol(file_path, position, new_name, workspace_root)`
8. `insert_text_at_position(file_path, position, text, workspace_root)`
9. `request_completions(file_path, position, workspace_root)`
10. `request_diagnostics(file_path, workspace_root)`
11. `request_definition(file_path, position, workspace_root)`
12. `is_ignored_path(path, workspace_root)`
13. Additional methods identified during implementation

### Callers to Update

1. `src/serena/symbol.py` — LanguageServerSymbolRetriever (primary)
2. `src/serena/code_editor.py` — LanguageServerCodeEditor (secondary)
3. `tests/` — All test files calling these methods

## 6.5 Blocking Dependencies

No blocking dependencies. All contracts and code are accessible.

## 7. Completion Promise (Ralph Loop Exit)

> "Two LSP sessions sharing one multi-root LSP instance, each with different workspace roots, BOTH resolve paths correctly to their own workspace. Verified by integration test with actual path resolution producing different absolute paths for the same relative path."

**Theater Prevention**: A test that only checks `result is not None` or `mock.called` is THEATER. The test MUST verify the actual resolved absolute path contains the correct workspace root prefix.

## 8. Contract Authority

**Authoritative Source**: `contracts/solidlsp_path_resolution_contract.py` (to be created)

```
REQ-2026-003 (this manifest)
    ↓
contracts/solidlsp_path_resolution_contract.py
    ↓
tests/test_solidlsp_path_resolution.py
    ↓
src/solidlsp/ls.py (implementation)
src/serena/symbol.py (caller updates)
src/serena/code_editor.py (caller updates)
```

## 9. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-05 | User + AI | Initial manifest from req-elicit dialogue |
| 2026-02-05 | User | Mandatory over Optional decision (CL3/CL7 correction) |

## 10. Cross-References

- **REQ-2026-002**: Multi-project session management (INV-06, INV-07)
- **contracts/global_lsp_pool_contract.py**: INV-3 (multi-root keyed by language), CON-3 (memory)
- **contracts/lsp_capability_adapter_contract.py**: add_workspace_root, can_serve_path
- **contracts/lsp_workspace_multiplexing_contract.py**: INV-1 (shared instances)
- **AI Panel conversation**: 45e62e2b-703a-4518-b1e2-db1baa565d79
