# Option B: workspace_root Parameter Implementation Plan

**Date**: 2026-02-05
**AI Panel Conversation**: eb9de4b1-28bd-4229-ae67-3096df9ce924
**Branch**: feature/multi-project-support
**Status**: APPROVED (AI Board 2-iteration consensus)

## Architecture Decision Record

**CHOSEN**: Option B - _resolve_path helper + workspace_root parameters
**REJECTED**: Option A (per-method params only - no centralized logic)
**REJECTED**: Option C (ContextVar - session bleed risk in concurrent scenarios, HIGH/CRITICAL)

**Rationale**: Explicit parameters are stack-local (thread-safe), debuggable, backward compatible.
repository_root_path is NOT renamed (would break 35+ language server subclasses).

## Root Cause

`SolidLanguageServer.repository_root_path` is set at LSP creation time in `__init__` (line 272).
For shared multi-root LSPs (INV-3: keyed by language only), ~40 usages resolve relative paths
against this creation-time root instead of the current session's workspace root.

## Design Principles

1. `repository_root_path` STAYS as-is (used by 35+ subclass _start_server methods, cache dir)
2. `workspace_root` is an OPTIONAL parameter on public methods (None = use repository_root_path)
3. `_resolve_path`/`_resolve_uri` centralize ALL path resolution
4. Cache keys include workspace_root to prevent cross-session collisions
5. Zero behavioral change when workspace_root=None (backward compat)

## Usage Categorization

BUCKET 1 - MUST USE workspace_root (session-specific, ~30 usages):
Path resolution, URI construction, existence checks, relative<->absolute conversions

BUCKET 2 - MUST KEEP repository_root_path (LSP init, cache, ~5 usages):
cache_dir (line 283), _start_server methods in subclasses, start() log

## Implementation Phases

### PHASE 0: Contract (contracts/path_resolution_contract.py)
- _resolve_path(relative, workspace_root) -> absolute path
- _resolve_uri(relative, workspace_root) -> file:// URI
- _make_cache_key(relative_path, workspace_root) -> globally unique cache key
- _resolve_path MUST reject absolute paths (raise ValueError)
- workspace_root=None fallback to repository_root_path

### PHASE 1: Helper Methods (src/solidlsp/ls.py)
Add 4 methods to SolidLanguageServer:
```python
def _effective_root(self, workspace_root: str | None = None) -> str:
    return workspace_root if workspace_root is not None else self.repository_root_path

def _resolve_path(self, relative_path: str, workspace_root: str | None = None) -> str:
    if os.path.isabs(relative_path):
        raise ValueError(f"Expected relative path, got absolute: {relative_path}")
    return os.path.join(self._effective_root(workspace_root), relative_path)

def _resolve_uri(self, relative_path: str, workspace_root: str | None = None) -> str:
    return pathlib.Path(self._resolve_path(relative_path, workspace_root)).as_uri()

def _make_cache_key(self, relative_path: str, workspace_root: str | None = None) -> str:
    return str(Path(self._effective_root(workspace_root)) / relative_path)
```

### PHASE 2: Public Method Signatures (src/solidlsp/ls.py)
Add `workspace_root: str | None = None` to ~20 public methods:
- request_overview, request_document_symbols, open_file
- request_full_symbol_tree, request_referencing_symbols
- request_hover, rename_symbol, insert_text_at_position
- request_completions, request_diagnostics, request_definition
- is_ignored_path, retrieve_full_file_content, retrieve_content_around_line
- request_document_overview, request_dir_overview
- request_containing_symbol, request_defining_symbol
- request_rename_symbol_edit, request_references, request_workspace_symbol

Replace ~30 direct repository_root_path usages with _resolve_path/_resolve_uri calls.

### PHASE 3: Internal Method Threading (src/solidlsp/ls.py)
Thread workspace_root through call chains:
- request_overview -> request_document_overview -> request_document_symbols
- request_overview -> request_dir_overview -> request_document_symbols
- request_full_symbol_tree -> request_document_symbols
- request_referencing_symbols -> request_references, request_containing_symbol, request_document_symbols
Update cache keys with _make_cache_key()

### PHASE 4: Caller Updates (src/serena/symbol.py, src/serena/code_editor.py)
- LanguageServerSymbolRetriever methods pass workspace_root=self.get_root_path()
- LanguageServerCodeEditor constructor passes workspace_root
- THIS IS WHERE THE BUG FIX ACTIVATES

### PHASE 5: Integration Tests
- Two sessions, two workspace roots, same shared LSP
- request_overview resolves to correct workspace
- Single session backward compat (no workspace_root param)
- Cache isolation (same relative path, different workspaces)
- Cache cleanup on workspace removal

## Change Surface
- src/solidlsp/ls.py: ~80 lines changed
- src/serena/symbol.py: ~10 lines changed
- src/serena/code_editor.py: ~5 lines changed
- contracts/path_resolution_contract.py: NEW (~50 lines)
- Language server subclasses (35+ files): ZERO changes
- Total: ~145 lines

## Risks and Mitigations

### RISK 1: Cache Key Collision (MEDIUM)
Same relative path in different workspaces → cache poisoning
MITIGATION: _make_cache_key includes effective_root in key

### RISK 2: Cache Memory Leak (LOW)
Caches grow unbounded as sessions accumulate
MITIGATION: _clear_workspace_cache() called on workspace folder removal

### RISK 3: Absolute Path Passed as Relative (MEDIUM)
os.path.join silently ignores first arg if second is absolute
MITIGATION: _resolve_path validates and rejects absolute paths

### RISK 4: open_file_buffers Keying (LOW)
Different workspace_roots → different URIs → different buffer entries
ANALYSIS: This is CORRECT behavior (files in different workspaces ARE different files)

### RISK 5: Thread Safety (RESOLVED)
workspace_root as method parameter is stack-local, inherently thread-safe
No shared mutable state for path resolution

## AI Board Validation
- Provider A (Anthropic claude-sonnet-4-5): Score 6/10, structurally sound
- Provider B (same conv): Score 6/10, 4 critical gaps identified and addressed
- Both confirmed Option B as safest approach
- Both confirmed Option C rejection
- Both confirmed no-rename decision for repository_root_path
