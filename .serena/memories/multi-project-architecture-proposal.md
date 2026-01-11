# Multi-Project Architecture Proposal

**Date**: 2026-01-11
**Status**: DRAFT - Pending maintainer discussion
**Related Branch**: feature/multi-project-support

## Problem Statement

Serena's current architecture uses a **global active project** model:
- `SerenaAgent._active_project` is shared across all MCP clients
- `activate_project("/repo/A")` from Agent-1 switches Agent-2's workspace
- Not compatible with multi-agent, multi-worktree workflows

## Proposed Architecture

```
┌─────────────────────────────────────┐
│     SerenaMCPServer (HTTP)          │
│  ┌───────────────────────────────┐  │
│  │    SessionRegistry            │  │  ← NEW: Map session_id → SessionContext
│  │    {session_id: SessionCtx}   │  │
│  └───────────────────────────────┘  │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│         SessionContext              │  ← NEW: Per-client state
│  - session_id                       │
│  - workspace_root (project path)    │
│  - modes                            │
│  - lsp_workspace_folders[]          │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│      LSPProcessPool (SHARED)        │  ← NEW: One process per language
│  - python_lsp (shared)              │
│  - rust_lsp (shared)                │
│  - typescript_lsp (shared)          │
│  + workspace_folders tracking       │
└─────────────────────────────────────┘
```

## Key Insights

### LSP Already Supports Multi-Workspace

LSP is **inherently multi-client and multi-workspace**:
- Each connection has its own `rootUri` / `workspaceFolders`
- Documents are scoped by URI, not "project"
- Servers maintain per-workspace caches and indexes

### HTTP Sessions Provide Isolation

MCP streamable-http transport provides `Mcp-Session-Id` header:
```
Mcp-Session-Id: 550e8400-e29b-41d4-a716-446655440000
```

This IS the session boundary for isolation.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **One LSP process per language** | LSP natively supports `workspaceFolders[]` - no need for separate processes |
| **Session = MCP session_id** | MCP streamable-http already provides session header |
| **Lazy workspace registration** | Call `workspace/didChangeWorkspaceFolders` when new session activates project |
| **Path validation per session** | Tools reject paths outside session's workspace_root |

## Implementation Phases

### Phase 1: Session Isolation (No LSP Changes)

```python
# NEW: src/serena/session.py
@dataclass
class SessionContext:
    session_id: str
    workspace_root: Path
    modes: list[SerenaAgentMode]
    
class SessionRegistry:
    _sessions: dict[str, SessionContext]
    
    def get_or_create(self, session_id: str) -> SessionContext: ...
    def activate_project(self, session_id: str, path: Path) -> None: ...
```

### Phase 2: Session-Aware Tools

```python
# Modify tool dispatch to use session context
def execute_tool(self, tool_name: str, params: dict, session_id: str):
    session = self.registry.get_or_create(session_id)
    # Validate path is under session.workspace_root
    # Route to correct LSP workspace
```

### Phase 3: LSP Workspace Multiplexing

```python
# NEW: src/serena/lsp_pool.py
class LSPPool:
    """Shared LSP processes with multi-workspace support."""
    _processes: dict[Language, SolidLanguageServer]
    _workspace_registrations: dict[Language, set[Path]]
    
    async def ensure_workspace(self, lang: Language, root: Path):
        if root not in self._workspace_registrations[lang]:
            await self._processes[lang].add_workspace_folder(root)
            self._workspace_registrations[lang].add(root)
```

## Open Questions

1. **Session creation trigger**: First tool call? Explicit `activate_project`? MCP `initialize`?
2. **Session cleanup**: When does a session expire? LRU eviction? Explicit `shutdown`?
3. **LSP workspace limits**: Some LSPs may have limits on workspace folders. Need fallback?
4. **Backward compatibility**: Single-project mode should still work (default behavior).

## Current Serena Architecture (Reference)

```python
# src/serena/mcp.py - THE PROBLEM
@dataclass
class SerenaMCPRequestContext:
    agent: SerenaAgent  # ← ONE agent, global state

# src/serena/agent.py - GLOBAL STATE
class SerenaAgent:
    _active_project: Project | None  # ← Changes affect ALL clients
```

## Related Work

- **Polyglot PR #703**: Multi-language per project (closed, maintainer implemented simpler version)
- **Issue #895**: Auto-activate project based on MCP client working directory
- **Upstream mux branch**: Merged, but was development branch not multiplexer feature

## References

- LSP Specification: workspaceFolders capability
- MCP Specification: streamable-http transport, Mcp-Session-Id header
- ChatGPT architectural analysis (2026-01-11)
