# MCP Session Flow Specification

**Status**: Draft for Review
**Date**: 2026-01-11
**Branch**: feature/multi-project-support

---

## 1. Overview

This specification defines the expected behavior for MCP session management in Serena, enabling multi-project and multi-session support with efficient LSP resource sharing.

### 1.1 Design Principles

1. **LSPs are global resources** - One LSP instance per language serves all sessions
2. **Sessions define access boundaries** - PathValidation enforces workspace isolation
3. **Serena orchestrates** - Routes calls, validates paths, manages LSP lifecycle
4. **Connection pooler pattern** - LSP management mirrors database connection pooling

### 1.2 Key Analogies

| Database Connection Pooler | Serena LSP Pool |
|---------------------------|-----------------|
| Connection pool | GlobalLanguageServerPool |
| Connection per backend type | LSP per language |
| Acquire/release connection | Touch/idle timeout |
| Max connections | Max LSP instances (optional) |
| Connection timeout | LSP idle timeout |
| Backend capabilities | LSP capabilities (multi-root, etc.) |

---

## 2. MCP Protocol Fundamentals

### 2.1 Protocol Version
- **Current**: MCP v1 (2024-11-05)
- **Negotiation**: Client sends `initialize` with `protocolVersion`, server responds with supported version
- **Serena**: MUST support MCP v1; MAY support future versions via version negotiation

### 2.2 Transport Types

| Transport | Connection Model | Session Lifecycle | Use Case |
|-----------|-----------------|-------------------|----------|
| **stdio** | Process-spawned | One session = one process lifetime | Claude Desktop, CLI tools |
| **SSE** | HTTP long-poll | Session = EventSource connection | Web clients, long-lived connections |
| **Streamable HTTP** | HTTP request/response | Session = request context OR persistent | API integrations, serverless |

### 2.3 Current vs Expected Behavior Summary

| Aspect | Current | Expected |
|--------|---------|----------|
| Session tracking | None (implicit) | Explicit SessionRegistry |
| Project scope | Global | Per-session |
| LSP ownership | Per-project | Global pool (shared) |
| LSP sharing | N/A (single session) | Automatic across sessions |
| Path validation | Basic | PathValidation with traversal prevention |
| LSP lifecycle | Manual | LSPTimeoutManager auto-reclaim |
| Multi-client | Not supported | Full support with isolation |
| Transport types | stdio only | stdio + SSE + streaming HTTP |

---

## 3. Architecture

### 3.1 Component Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    SerenaAgent (Global)                     │
├─────────────────────────────────────────────────────────────┤
│  SessionRegistry                                            │
│    session_a → workspace: /users/ketema/project-a           │
│    session_b → workspace: /users/ketema/project-b           │
├─────────────────────────────────────────────────────────────┤
│  GlobalLanguageServerPool                                   │
│    rust-analyzer (1 instance total)                         │
│    pylsp (1 instance total)                                 │
│    tsserver (1 instance total)                              │
│                                                             │
│    Acquisition tracking: {rust: [session_a, session_b],     │
│                          python: [session_a]}               │
├─────────────────────────────────────────────────────────────┤
│  LSPTimeoutManager (Global)                                 │
│    Tracks: last_used[language] across ALL sessions          │
│    Reclaims when: No session has used language > timeout    │
├─────────────────────────────────────────────────────────────┤
│  PathValidation (Session-scoped enforcement)                │
│    Before ANY LSP call:                                     │
│      validate_path(requested_path, session.workspace_root)  │
├─────────────────────────────────────────────────────────────┤
│  LSPCapabilityAdapters (Polymorphic per-LSP handling)       │
│    RustAnalyzerAdapter: supports multi-root workspaces      │
│    PylspAdapter: supports multi-root workspaces             │
│    TsServerAdapter: single project mode only                │
│    ... (per-LSP capability detection and adaptation)        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 LSP as Global Resources

**Critical architectural principle**: LSPs do not know about Serena sessions or projects. An LSP (e.g., rust-analyzer) operates on file paths. It can serve ANY Rust file it has access to.

**Implications**:
1. One rust-analyzer instance can serve `/project-a/src/main.rs` AND `/project-b/src/lib.rs`
2. Session isolation is Serena's responsibility, NOT the LSP's
3. PathValidation MUST run before ANY LSP call to enforce session boundaries

### 3.3 Connection Pooler Pattern

Inspired by database connection poolers (PgBouncer, ProxySQL):

```python
class GlobalLanguageServerPool:
    """
    Manages LSP instances like a database connection pool.

    Key behaviors:
    - Lazy instantiation: LSP started on first acquisition
    - Sharing: Multiple sessions share same LSP instance
    - Reference tracking: Know which sessions are using which LSPs
    - Graceful release: Idle timeout before shutdown
    - Capability awareness: Handle per-LSP differences
    """

    def acquire(self, language: Language, workspace_root: Path) -> SolidLanguageServer:
        """
        Acquire an LSP for the given language.

        If LSP already running:
          - If supports multi-root: add workspace_root via didChangeWorkspaceFolders
          - If single-root only: check if can serve this root, else start new instance
        If LSP not running:
          - Start new instance with workspace_root

        Returns the LSP instance (possibly shared).
        """
        ...

    def release(self, language: Language, session_id: str) -> None:
        """
        Release a session's claim on an LSP.

        Does NOT immediately stop the LSP.
        LSPTimeoutManager handles idle-based reclamation.
        """
        ...

    def get_adapter(self, language: Language) -> LSPCapabilityAdapter:
        """
        Get the capability adapter for this LSP type.
        Handles polymorphic behavior per-LSP.
        """
        ...
```

---

## 4. LSP Capability Adapters

### 4.1 The Problem

Different LSPs have different capabilities for handling multiple workspace roots:

| LSP | Multi-Root Support | Root Expansion Method |
|-----|-------------------|----------------------|
| rust-analyzer | Yes | `workspace/didChangeWorkspaceFolders` |
| pylsp/pyright | Yes | `workspace/didChangeWorkspaceFolders` |
| gopls | Yes | `workspace/didChangeWorkspaceFolders` |
| tsserver | Limited | Requires project references or restart |
| jdtls (Java) | Yes | `workspace/didChangeWorkspaceFolders` |
| clangd | Limited | Compilation database per-project |

### 4.2 Adapter Pattern

```python
from abc import ABC, abstractmethod

class LSPCapabilityAdapter(ABC):
    """
    Abstract adapter for LSP-specific capability handling.
    Implements polymorphic behavior for different LSP servers.
    """

    @abstractmethod
    def supports_multi_root(self) -> bool:
        """Whether this LSP can serve multiple workspace roots."""
        ...

    @abstractmethod
    def add_workspace_root(self, ls: SolidLanguageServer, root: Path) -> bool:
        """
        Add a workspace root to an existing LSP.
        Returns True if successful, False if LSP needs restart.
        """
        ...

    @abstractmethod
    def remove_workspace_root(self, ls: SolidLanguageServer, root: Path) -> bool:
        """Remove a workspace root from an existing LSP."""
        ...

    @abstractmethod
    def can_serve_path(self, ls: SolidLanguageServer, path: Path) -> bool:
        """Check if this LSP instance can serve the given path."""
        ...


class RustAnalyzerAdapter(LSPCapabilityAdapter):
    """Adapter for rust-analyzer with full multi-root support."""

    def supports_multi_root(self) -> bool:
        return True

    def add_workspace_root(self, ls: SolidLanguageServer, root: Path) -> bool:
        # Send workspace/didChangeWorkspaceFolders notification
        ls.notify("workspace/didChangeWorkspaceFolders", {
            "event": {
                "added": [{"uri": root.as_uri(), "name": root.name}],
                "removed": []
            }
        })
        return True

    def can_serve_path(self, ls: SolidLanguageServer, path: Path) -> bool:
        # rust-analyzer can serve any path in its workspace folders
        return any(path.is_relative_to(root) for root in ls.workspace_roots)


class TsServerAdapter(LSPCapabilityAdapter):
    """Adapter for tsserver with limited multi-root support."""

    def supports_multi_root(self) -> bool:
        # tsserver has limitations with multi-root
        return False  # Conservative: treat as single-root

    def add_workspace_root(self, ls: SolidLanguageServer, root: Path) -> bool:
        # Cannot dynamically add roots; need new instance
        return False

    def can_serve_path(self, ls: SolidLanguageServer, path: Path) -> bool:
        # Can only serve paths under original root
        return path.is_relative_to(ls.root_path)
```

### 4.3 Pool Behavior with Adapters

```python
def acquire(self, language: Language, workspace_root: Path) -> SolidLanguageServer:
    adapter = self.get_adapter(language)

    if language in self._running_lsps:
        ls = self._running_lsps[language]

        if adapter.can_serve_path(ls, workspace_root):
            # Existing LSP can serve this root
            return ls

        if adapter.supports_multi_root():
            # Try to add the new root dynamically
            if adapter.add_workspace_root(ls, workspace_root):
                return ls

        # Cannot extend existing LSP; need decision:
        # Option A: Start additional instance for this language
        # Option B: Restart with expanded roots
        # Option C: Reject (require projects under same root)

        # For now: Option A (additional instance)
        return self._start_new_instance(language, workspace_root)

    # No existing LSP; start fresh
    return self._start_new_instance(language, workspace_root)
```

---

## 5. Session Initialization Flow

### 5.1 Connection Phase

```
CLIENT                           SERENA MCP SERVER
   |                                    |
   |----[transport connect]------------>|  # TCP/stdin/HTTP
   |                                    |
   |                                    |  SESSION_CREATED:
   |                                    |    session_id = uuid4()
   |                                    |    SessionRegistry.bind_session(
   |                                    |      session_id,
   |                                    |      workspace_root=None,  # Not yet known
   |                                    |      source="mcp_connect"
   |                                    |    )
   |                                    |
```

### 5.2 MCP Initialize Phase

```
CLIENT                           SERENA MCP SERVER
   |                                    |
   |---[initialize]-------------------->|
   |   {                                |
   |     protocolVersion: "2024-11-05", |
   |     clientInfo: {...},             |
   |     capabilities: {...}            |
   |   }                                |
   |                                    |
   |                                    |  INITIALIZE:
   |                                    |    1. Validate protocol version
   |                                    |    2. Store client capabilities
   |                                    |    3. Determine workspace_root:
   |                                    |       - From clientInfo.workspaceRoot
   |                                    |       - OR from env (MCP_WORKSPACE_ROOT)
   |                                    |       - OR await explicit activation
   |                                    |    4. If workspace_root known:
   |                                    |       SessionRegistry.update_session(
   |                                    |         session_id, workspace_root
   |                                    |       )
   |                                    |
   |<--[initialize_result]--------------|
   |   {                                |
   |     protocolVersion: "2024-11-05", |
   |     serverInfo: {                  |
   |       name: "serena",              |
   |       version: "..."               |
   |     },                             |
   |     capabilities: {                |
   |       tools: { listChanged: true } |
   |     }                              |
   |   }                                |
```

### 5.3 Initialized Notification

```
CLIENT                           SERENA MCP SERVER
   |                                    |
   |---[initialized]------------------>|  # Client ready
   |                                    |
   |                                    |  SESSION_READY:
   |                                    |    SessionContext.state = ACTIVE
   |                                    |
```

---

## 6. Tool List Phase

### 6.1 Session-Aware Tool Filtering

```
CLIENT                           SERENA MCP SERVER
   |                                    |
   |---[tools/list]-------------------->|
   |                                    |
   |                                    |  EXPECTED:
   |                                    |    1. Get session from registry
   |                                    |    2. If no project activated:
   |                                    |       Return: config tools + activate_project
   |                                    |    3. If project activated:
   |                                    |       Return: config tools + project tools
   |                                    |       (filtered by modes/contexts)
   |                                    |
   |<--[tools]--------------------------|
   |   { tools: [...session-filtered...]}|
```

**Tool Categories**:
- **Config Tools** (always available): `activate_project`, `get_current_config`, `switch_modes`
- **Project Tools** (require active project): All symbol/file/memory tools
- **LSP Tools** (require active project + LSP): `find_symbol`, `get_symbols_overview`, etc.

---

## 7. Tool Call Phase

### 7.1 LSP Tool Call Flow (Detailed)

```
Session A (workspace: /project-a)
   |
   |---[find_symbol(relative_path="src/main.rs")]
   |
   |   SERENA TOOL DISPATCH:
   |     1. Resolve session_id from request context
   |     2. Get SessionContext from SessionRegistry
   |     3. Resolve full path: /project-a/src/main.rs
   |
   |   PATH VALIDATION:
   |     4. PathValidation.validate_path(
   |          /project-a/src/main.rs,
   |          /project-a  # Session A's workspace
   |        ) → PASS (or raise PathBoundaryError)
   |
   |   LSP ROUTING:
   |     5. Determine language from file extension: Rust
   |     6. GlobalLanguageServerPool.acquire("rust", /project-a)
   |        - rust-analyzer running?
   |          - YES: adapter.can_serve_path()? Return existing
   |          - NO: Start new instance
   |     7. LSPTimeoutManager.touch("rust")
   |
   |   LSP EXECUTION:
   |     8. Forward request to rust-analyzer
   |        (LSP doesn't know about sessions - just file path)
   |     9. Receive response
   |
   |   RESPONSE:
   |     10. Return result to Session A
   |
   |<--[result]
```

### 7.2 Non-LSP Tool Calls

```
   |---[tools/call]------------------->|
   |   { name: "read_memory", ... }     |
   |                                    |
   |                                    |  EXPECTED:
   |                                    |    1. Resolve session_id
   |                                    |    2. Get SessionContext
   |                                    |    3. Validate path (if applicable)
   |                                    |    4. Execute with session-scoped state
   |                                    |    5. Return result
   |                                    |
   |<--[result]------------------------|
```

### 7.3 Project Activation Tool Call

```
   |---[tools/call]------------------->|
   |   { name: "activate_project",      |
   |     arguments: { project: "foo" }  |
   |   }                                |
   |                                    |
   |                                    |  EXPECTED:
   |                                    |    1. Resolve session_id
   |                                    |    2. If session has existing project:
   |                                    |       a. Release LSPs for old project:
   |                                    |          GlobalLanguageServerPool.release(
   |                                    |            language, session_id
   |                                    |          ) for each language
   |                                    |       b. Update session workspace
   |                                    |    3. Load new project config
   |                                    |    4. Acquire LSPs for new project:
   |                                    |       GlobalLanguageServerPool.acquire(
   |                                    |         language, project.root
   |                                    |       ) for each required language
   |                                    |    5. Update SessionRegistry:
   |                                    |       bind_session(session_id, workspace=project.root)
   |                                    |    6. Emit tools/list_changed if tool set changes
   |                                    |
```

---

## 8. LSP Lifecycle Management

### 8.1 Acquisition and Sharing

```
PROJECT A ACTIVATES (Session A) - needs Rust, Python
   │
   ▼
GlobalLanguageServerPool.acquire("rust", /project-a)
  → rust-analyzer: START (sessions: [A])
GlobalLanguageServerPool.acquire("python", /project-a)
  → pylsp: START (sessions: [A])

PROJECT B ACTIVATES (Session B) - needs Rust, Go
   │
   ▼
GlobalLanguageServerPool.acquire("rust", /project-b)
  → rust-analyzer:
      adapter.can_serve_path(/project-b)?
        YES (multi-root): add workspace folder
        NO: start second instance
      sessions: [A, B]
GlobalLanguageServerPool.acquire("go", /project-b)
  → gopls: START (sessions: [B])

Current state:
  rust-analyzer: sessions [A, B], roots [/project-a, /project-b]
  pylsp: sessions [A], roots [/project-a]
  gopls: sessions [B], roots [/project-b]
```

### 8.2 Release and Reclamation

```
SESSION A DISCONNECTS
   │
   ▼
GlobalLanguageServerPool.release("rust", session_a)
  → rust-analyzer: sessions [B] (still needed)
GlobalLanguageServerPool.release("python", session_a)
  → pylsp: sessions [] (none remaining)
     → LSPTimeoutManager starts idle timer

Current state:
  rust-analyzer: sessions [B]
  pylsp: sessions [], idle_since=now
  gopls: sessions [B]

IDLE TIMEOUT EXPIRES (pylsp)
   │
   ▼
LSPTimeoutManager.check_and_reclaim()
  → pylsp idle > threshold
  → reclaim_callback("python")
  → pylsp.stop(), save_cache()

Current state:
  rust-analyzer: sessions [B]
  gopls: sessions [B]
```

### 8.3 Timeout Configuration

```yaml
# Per-language idle timeouts
lsp_timeouts:
  # Heavy LSPs - reclaim faster (high memory footprint)
  rust: 1800      # 30 min - rust-analyzer: 500MB-1.5GB
  java: 1800      # 30 min - jdtls: 400MB-1GB
  csharp: 1800    # 30 min - omnisharp: 300-800MB

  # Medium LSPs - balanced
  typescript: 3600  # 1 hr - tsserver: 150-400MB
  go: 3600          # 1 hr - gopls: 100-300MB
  haskell: 3600     # 1 hr - hls: 200-500MB

  # Light LSPs - keep longer
  python: 3600    # 1 hr - pylsp: 50-150MB
  ruby: 3600      # 1 hr - solargraph: 50-100MB

  default: 3600   # 1 hr
```

---

## 9. Session Termination

### 9.1 Graceful Disconnect

```
CLIENT                           SERENA MCP SERVER
   |                                    |
   |---[transport close]--------------->|
   |                                    |
   |                                    |  DISCONNECT:
   |                                    |    1. Get session's acquired LSPs
   |                                    |    2. For each language:
   |                                    |       GlobalLanguageServerPool.release(
   |                                    |         language, session_id
   |                                    |       )
   |                                    |    3. SessionRegistry.unbind_session(session_id)
   |                                    |    4. Clean up session state
   |                                    |
```

### 9.2 Session Timeout (Streaming HTTP)

```
   |                                    |
   |                                    |  BACKGROUND (optional):
   |                                    |    For streaming HTTP only:
   |                                    |      If session.last_activity > session_timeout:
   |                                    |        Treat as disconnect
   |                                    |
```

---

## 10. Error Handling

### 10.1 Path Validation Errors

```python
{
    "error": {
        "code": -32602,  # Invalid params
        "message": "Path outside workspace boundary",
        "data": {
            "path": "../../../etc/passwd",
            "workspace_root": "/home/user/project",
            "violation": "traversal_attempt"
        }
    }
}
```

### 10.2 Session Errors

```python
# Session not found:
{
    "error": {
        "code": -32001,
        "message": "Session expired or not found",
        "data": {
            "session_id": "abc-123",
            "suggestion": "Re-initialize connection"
        }
    }
}

# No project activated:
{
    "error": {
        "code": -32002,
        "message": "No project activated for this session",
        "data": {
            "tool": "find_symbol",
            "suggestion": "Call activate_project first"
        }
    }
}
```

### 10.3 LSP Errors

```python
# LSP cannot serve path (single-root LSP, different project):
{
    "error": {
        "code": -32003,
        "message": "LSP cannot serve requested path",
        "data": {
            "language": "typescript",
            "path": "/other-project/src/index.ts",
            "reason": "tsserver_single_root_limitation",
            "suggestion": "LSP initialized for different project root"
        }
    }
}
```

---

## 11. Multi-Session Scenarios

### 11.1 Same Project, Multiple Sessions

```
Session A (Claude Desktop)     Session B (Web IDE)
         |                            |
         |---activate_project("foo")--|---activate_project("foo")
         |                            |
         |      SERENA SERVER         |
         |  ┌──────────────────────┐  |
         |  │ rust-analyzer        │  |
         |  │   roots: [/foo]      │  |
         |  │   sessions: [A, B]   │  |
         |  └──────────────────────┘  |
         |                            |
         |  Both share SAME LSP       |
         |                            |
```

### 11.2 Different Projects, Shared LSP (Multi-Root)

```
Session A                      Session B
         |                            |
         |---activate("foo")----------|---activate("bar")
         |                            |
         |      SERENA SERVER         |
         |  ┌──────────────────────┐  |
         |  │ rust-analyzer        │  |
         |  │   roots: [/foo, /bar]│  |
         |  │   sessions: [A, B]   │  |
         |  └──────────────────────┘  |
         |                            |
         |  SHARED LSP (multi-root)   |
         |  PathValidation enforces   |
         |  session boundaries        |
         |                            |
```

### 11.3 Different Projects, Separate LSPs (Single-Root)

```
Session A                      Session B
         |                            |
         |---activate("foo")----------|---activate("bar")
         |  (TypeScript project)      |  (TypeScript project)
         |                            |
         |      SERENA SERVER         |
         |  ┌───────────┬───────────┐ |
         |  │tsserver-1 │tsserver-2 │ |
         |  │root: /foo │root: /bar │ |
         |  │sess: [A]  │sess: [B]  │ |
         |  └───────────┴───────────┘ |
         |                            |
         |  SEPARATE LSPs             |
         |  (tsserver single-root)    |
         |                            |
```

---

## 12. Configuration

### 12.1 Session Configuration

```yaml
# serena_config.yml
session:
  # Session timeout for streaming HTTP (0 = no timeout)
  streaming_session_timeout_seconds: 3600  # 1 hour

multi_instance_policy:
  # Policy when LSP cannot serve new project:
  # - "start_new": Start additional LSP instance (default)
  # - "reject": Reject activation, require compatible root
  # - "restart": Restart LSP with new root (loses other sessions)
  default: "start_new"

  # Per-language overrides
  typescript: "start_new"  # tsserver needs separate instances
  rust: "expand_roots"     # rust-analyzer can expand
```

### 12.2 LSP Capability Registry

```yaml
# Built-in capability definitions (can be overridden)
lsp_capabilities:
  rust-analyzer:
    multi_root: true
    root_expansion_method: "didChangeWorkspaceFolders"

  pylsp:
    multi_root: true
    root_expansion_method: "didChangeWorkspaceFolders"

  gopls:
    multi_root: true
    root_expansion_method: "didChangeWorkspaceFolders"

  tsserver:
    multi_root: false
    root_expansion_method: null
    notes: "Requires separate instance per project"

  jdtls:
    multi_root: true
    root_expansion_method: "didChangeWorkspaceFolders"

  clangd:
    multi_root: false
    root_expansion_method: null
    notes: "Uses compilation database per project"
```

---

## 13. AI Panel Findings (Resolved)

**AI Panel Conversation ID**: `e9c3ec5e-6d3a-438b-9469-6f07eb5b4dcf`

### 13.1 Multi-Root LSP State Corruption Risk

**Finding**: rust-analyzer may have state bleed between workspace folders with conflicting `Cargo.toml` configurations.

**Resolution**: USER RESPONSIBILITY. Projects with interdependencies would exhibit this behavior with or without Serena. Users should organize their projects correctly. This is standard module/dependency behavior.

**Action**: Note the risk. Perform PoC after implementation to observe behavior.

### 13.2 Response Filtering

**AI Panel Concern**: LSP responses (`textDocument/references`, `workspace/symbol`) can return results from other workspace folders.

**Resolution**: NOT A SERENA CONCERN. This is standard language behavior (modules, dependency injection, libraries). The LSP returns symbols; Serena manages its session scope. If an AI agent tries to physically follow a symbol leading outside its invocation scope, that is handled by agent configuration, not Serena.

### 13.3 LSP Capability Detection Sequence

**Finding**: Must probe LSP capabilities BEFORE first session activates workspace.

**Resolution**: ACCEPTED. Required initialization sequence:
1. Start LSP
2. Send initialize request
3. Parse ServerCapabilities
4. Cache for adapter routing
5. Only then allow session workspace registration

### 13.4 Single-Root LSP Pool Key Strategy

**Finding**: Single-root LSPs (tsserver, clangd) cannot share instances across different roots.

**Resolution**: ACCEPTED. Pool key must be:
- Multi-root LSPs: `language` (can share)
- Single-root LSPs: `(language, rootUri)` (per-root instances)

```python
# Multi-root (rust-analyzer, pylsp, gopls):
_running_lsps[Language.RUST] = rust_analyzer_instance

# Single-root (tsserver, clangd):
_running_lsps[(Language.TYPESCRIPT, Path("/project-a"))] = tsserver_a
_running_lsps[(Language.TYPESCRIPT, Path("/project-b"))] = tsserver_b
```

### 13.5 Lock Hierarchy

**Finding**: Risk of deadlock if pool_lock and session_lock acquired in inconsistent order.

**Resolution**: ACCEPTED. Define strict lock hierarchy:
```
session_lock → pool_lock (always acquire in this order)
```

Never hold pool_lock while calling session methods that might acquire session_lock.

### 13.6 LSP Crash Recovery

**Finding**: Plan doesn't address LSP crashes or unresponsiveness.

**Resolution**: ALREADY EXISTS. Serena has `_ensure_functional_ls()` pattern:
- Checks `is_running()` before every LSP access
- Auto-restarts via `restart_language_server()` if crashed
- No additional implementation needed

```python
# Existing pattern in ls_manager.py:
def _ensure_functional_ls(self, ls: SolidLanguageServer) -> SolidLanguageServer:
    if not ls.is_running():
        log.warning(f"Language server for language {ls.language} is not running; restarting ...")
        ls = self.restart_language_server(ls.language)
    return ls
```

### 13.7 Workspace Folder Removal on Disconnect

**Finding**: Leaving folders registered → inotify handle accumulation, memory leaks.

**Resolution**: ACCEPTED. Send `workspace/didChangeWorkspaceFolders(removed=[...])` on session disconnect for multi-root LSPs. Terminate instance for single-root LSPs if last session disconnects.

### 13.8 REQ-2 Qualification

**Finding**: "LSP instances are shared" needs qualification for single-root LSPs.

**Resolution**: ACCEPTED. Update requirement:

> **REQ-2 (Revised)**: LSP instances are shared across sessions **where possible and correct**. Multi-root LSPs share a single instance across compatible sessions. Single-root LSPs require per-root instances.

---

## 14. Resolved Design Decisions

### 14.1 Reference Counting + Idle Timeout (Hybrid)

**Decision**: Use hybrid approach:
- Track session references per LSP
- When `ref_count == 0`: Start idle timer
- When `idle_time > timeout`: Reclaim LSP
- If new session acquires before timeout: Cancel timer, increment ref_count

### 14.2 Workspace Folder Management

**Decision**:
- On session disconnect: Remove workspace folder from LSP (multi-root) or terminate (single-root)
- On LSP idle timeout: Save cache, then shutdown
- On LSP crash: Auto-restart on next access (existing behavior)

---

## 14. Implementation Phases

### Phase 1: GlobalLanguageServerPool
- Refactor `LanguageServerManager` to global scope
- Add session tracking (which sessions acquired which LSPs)
- Implement acquire/release semantics

### Phase 2: LSP Capability Adapters
- Define `LSPCapabilityAdapter` interface
- Implement adapters for each supported language
- Handle multi-root vs. single-root differences

### Phase 3: Session-Aware Tool Dispatch
- Integrate PathValidation into tool dispatch
- Route LSP calls through GlobalLanguageServerPool
- Add session context to all tool executions

### Phase 4: MCP Transport Integration
- stdio: Session = process lifetime
- SSE: Session = EventSource connection
- Streaming HTTP: Session header management

---

## Appendix A: Existing Components

These components already exist and will be integrated:

- **SessionRegistry** (`src/serena/session_registry.py`): Thread-safe session tracking
- **LSPTimeoutManager** (`src/serena/lsp_timeout.py`): Per-language idle timeout
- **PathValidation** (`src/serena/path_validation.py`): Workspace boundary enforcement

## Appendix B: References

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [LSP Specification - workspace/didChangeWorkspaceFolders](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_didChangeWorkspaceFolders)
- [Database Connection Pooling Patterns](https://en.wikipedia.org/wiki/Connection_pool)
