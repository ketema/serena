# Multi-Project Support Research

## Problem Statement

Serena runs as a system service HTTP server but does not support multiple instances of Claude or other AI agents working in different folder trees (projects) concurrently. When multiple AI assistants connect to the same Serena MCP server, they all share one agent with one active project.

## Upstream Research Summary

### Existing Issues

1. **[Issue #458](https://github.com/oraios/serena/issues/458)**: "Use multiple projects with serena"
   - Status: CLOSED (answered with documentation reference)
   - Resolution: Users directed to README for project activation/switching
   - Key limitation: "one server is connected to (at most) one project at a time"

2. **[Issue #474](https://github.com/oraios/serena/issues/474)**: "Support for multi projects - when attaching directories to IDE"
   - Status: CLOSED
   - User request: "a multi project in a single session example"
   - Maintainer response: "Not currently, no" (simultaneous multi-project)
   - Workaround: Sequential switching via `activate_project` tool
   - Future: "native multiproject support" planned for JetBrains extension

3. **[Discussion #445](https://github.com/oraios/serena/discussions/445)**: SSE Mode and Multi-Agent Setup
   - Recommendation: "for multi-agent setups, the SSE mode should be used"
   - Clarification: SSE mode doesn't solve concurrent multi-project - it's for performance

### Related PRs

1. **[PR #305](https://github.com/oraios/serena/pull/305)**: "Add multi-instance support for JetBrains mode" (MERGED Jul 19, 2025)
   - Implementation: Port-based discovery with project root matching
   - Pattern: `JetBrainsPluginClient.from_project()` factory method
   - Key insight: Port scanning + project path matching for instance routing

2. **[PR #704](https://github.com/oraios/serena/pull/704)**: "Add LanguageServerManager, adding simultaneous multi-language support" (MERGED Oct 29, 2025)
   - This is for multiple languages, not multiple projects
   - But shows pattern for managing multiple concurrent LSP instances

### MCP Protocol Session Isolation

**Source**: [MCP Issue #1087](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1087)

Key findings from MCP protocol maintainers:
- "Session isolation mechanics are left to individual Server developers"
- "The Session ID is sufficient for isolating by MCP Client connection"
- Protocol uses `Mcp-Session-Id` HTTP header for session tracking
- No certification process exists for verifying proper data isolation
- **Session isolation is an implementation responsibility, NOT protocol-enforced**

### Forks

- Repository has 1.2k+ forks
- No specific fork found with concurrent multi-project support implemented
- Some specialized forks exist (serena-haskell, serena-mcp variants) but not for multi-project

## Current Architecture Analysis

### Key Files
- `src/serena/agent.py:93` - `_active_project: Project | None` (SINGLE project)
- `src/serena/agent.py:402` - `_activate_project()` method (REPLACES project)
- `src/serena/mcp.py:334` - Single `SerenaAgent` instance in factory
- `src/serena/tools/tools_base.py:82` - `get_active_project_or_raise()`
- `src/serena/patches/mcp/server/streamable_http_manager.py` - Session management

### Session Infrastructure (Already Exists!)

Serena already has session tracking at the transport level:

```python
# streamable_http_manager.py
class StreamableHTTPSessionManager:
    self._server_instances: dict[str, StreamableHTTPServerTransport] = {}

    # Line 233: Extract session ID from request
    request_mcp_session_id = request.headers.get(MCP_SESSION_ID_HEADER)

    # Line 236-239: Route to existing session
    if request_mcp_session_id in self._server_instances:
        transport = self._server_instances[request_mcp_session_id]
        await transport.handle_request(scope, receive, send)

    # Line 246-256: Create new session
    new_session_id = uuid4().hex
    self._server_instances[new_session_id] = http_transport
```

### The Gap

Session management exists at transport level, BUT:
- All sessions share the same MCP server app (`self.app`)
- The MCP server app uses one `SerenaAgent` instance
- `SerenaAgent` has single `_active_project`
- **Result: All sessions share the same active project**

## Design Approaches

### Option 1: Session-Aware Project Mapping (Recommended)

Add session-to-project mapping in SerenaAgent:

```python
class SerenaAgent:
    _active_projects: dict[str, Project] = {}  # project_name → Project
    _session_projects: dict[str, str] = {}     # session_id → project_name
    _default_project_name: str | None = None   # backward compat

    def get_project_for_session(self, session_id: str | None) -> Project | None:
        if session_id and session_id in self._session_projects:
            project_name = self._session_projects[session_id]
            return self._active_projects.get(project_name)
        return self._active_projects.get(self._default_project_name)
```

**Challenges:**
- Thread tool execution context to carry session ID
- Modify tools to use session-aware project resolution
- Pass session ID from transport layer to tool execution

### Option 2: Agent Per Session

Create separate `SerenaAgent` instance per session:

```python
class StreamableHTTPSessionManager:
    _session_agents: dict[str, SerenaAgent] = {}  # session_id → agent
```

**Challenges:**
- Memory overhead (each agent has LSP manager, caches, etc.)
- Need to share configuration across agents
- Agent lifecycle management

### Option 3: Agent Per Project

Create `SerenaAgent` instance per activated project, route by project context:

```python
class MultiProjectManager:
    _project_agents: dict[str, SerenaAgent] = {}  # project_path → agent
```

**Challenges:**
- How to determine which project a tool call targets?
- Explicit project parameter on tools, or file-path-based routing?

## Protocol Architecture (Clarified)

### Key Insight: MCP Session = HTTP Session

MCP sessions piggyback on HTTP using the `mcp-session-id` header:
```
HTTP Request
├── Headers
│   └── mcp-session-id: "abc123..."  ← MCP session ID
├── Body
│   └── JSON-RPC message (tool call, etc.)
```

The session ID is:
- Generated server-side on first request (no header present)
- Returned in response header
- Client includes in subsequent requests
- **Same ID for both HTTP and MCP** (no separate session systems)

### MCP Roots Capability (Key Discovery!)

MCP protocol has built-in support for clients to declare their working directories:

```python
class Root(BaseModel):
    uri: FileUrl      # file:///path/to/project
    name: str | None  # "my-project" (optional)

# Server can REQUEST roots from client:
session.list_roots() → ListRootsResult(roots=[Root(...), ...])
```

**This is exactly what we need!** When a session is created:
1. Server queries client: `roots/list`
2. Client responds with working directory(ies)
3. Server maps session → project based on root

### LSP Architecture (Should Be Shared)

Current: LSPManager per project, manages multiple language LSPs
```
Project A
└── LSPManager
    ├── Python LSP
    ├── TypeScript LSP
    └── Rust LSP
```

**LSP should NOT be per-session** because:
- LSP communicates over its own protocol (stdio/tcp)
- LSP state is project-scoped (symbols, diagnostics)
- Multiple sessions on same project should share LSP
- Memory efficient

### Proposed Architecture

```
                    ┌─────────────────────────────────────────┐
                    │         Serena HTTP Server              │
                    │  StreamableHTTPSessionManager           │
                    │  _server_instances: {session_id: transport}
                    └─────────────────┬───────────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
    Session A                    Session B                    Session C
    (Agent on                    (Agent on                    (Agent on
     /proj/chess)                 /proj/webapp)                /proj/chess)
         │                            │                            │
         │                            │                            │
         └──────────┬─────────────────┴──────────┬─────────────────┘
                    │                            │
              ┌─────▼─────┐                ┌─────▼─────┐
              │ Project:  │                │ Project:  │
              │ /chess    │                │ /webapp   │
              │           │                │           │
              │ LSPManager│                │ LSPManager│
              │ ├─Python  │                │ ├─Python  │
              │ └─Haskell │                │ └─TypeScript
              └───────────┘                └───────────┘

Session A & C share same project/LSPManager
Session B has its own project/LSPManager
```

### Session-to-Project Binding

**Binding happens at session creation, stays fixed:**
1. New session created (first request without mcp-session-id)
2. Server calls `session.list_roots()` to get client's cwd
3. First root URI → project path
4. Bind: `session_id → project_path` (immutable for session lifetime)
5. Even if agent changes cwd during session, binding stays

## Session ID Flow Analysis (Deep Dive)

### MCP Stack Layers

```
┌─────────────────────────────────────────────────────────────┐
│ StreamableHTTPSessionManager                                │
│   _server_instances: dict[str, StreamableHTTPServerTransport]│
│   mcp_session_id from HTTP header → uuid                    │
├─────────────────────────────────────────────────────────────┤
│ StreamableHTTPServerTransport                               │
│   mcp_session_id: str (stored here)                         │
├─────────────────────────────────────────────────────────────┤
│ MCPServer.run(read_stream, write_stream, ...)               │
│   Creates ServerSession                                     │
├─────────────────────────────────────────────────────────────┤
│ ServerSession                                               │
│   NO mcp_session_id (not propagated!)                       │
├─────────────────────────────────────────────────────────────┤
│ FastMCP Context (available in tools)                        │
│   request_id: str                                           │
│   client_id: str | None (from meta, often None)             │
│   session: ServerSession (no session_id)                    │
└─────────────────────────────────────────────────────────────┘
```

### Key Finding: Session ID Not Available in Tools

**The Problem**:
- `mcp_session_id` is stored in `StreamableHTTPServerTransport`
- `ServerSession` does not receive or store the session ID
- FastMCP `Context` can access `session` but session has no ID
- Tools currently cannot identify which client/session is calling them

### Available Identifiers in Tools

Via FastMCP `Context` (if tools used `context_kwarg`):
1. `ctx.request_id` - Unique per request (not per session)
2. `ctx.client_id` - From meta, often None (client-controlled)
3. `ctx.session.client_params` - Client info from initialization

**Note**: Serena currently sets `context_kwarg=None` in mcp.py:227, meaning
tools don't receive context at all.

### Implementation Path for Multi-Project

**Option 1A: Propagate Session ID Through Stack** (Cleanest but invasive)
- Modify MCP SDK to pass session ID to ServerSession
- Requires upstream MCP changes or monkey-patching

**Option 1B: Thread-Local Storage** (Pragmatic)
- Store session ID in thread-local before tool execution
- StreamableHTTPServerTransport knows session ID at request time
- Patch request handling to set thread-local before calling MCPServer

**Option 1C: Request ID Mapping** (Workaround)
- Map request_id → session_id at transport layer
- Tools query mapping using ctx.request_id
- Requires coordination between transport and agent

## Implementation Strategy (Refined)

### Key Components to Build

**1. ProjectManager (new class)**
```python
class ProjectManager:
    """Manages multiple active projects and their LSP instances."""

    _projects: dict[str, Project] = {}          # project_path → Project
    _session_bindings: dict[str, str] = {}      # session_id → project_path
    _project_lock: threading.RLock              # Thread safety

    def get_or_create_project(self, path: str) -> Project:
        """Get existing project or create + activate new one."""

    def bind_session(self, session_id: str, project_path: str) -> None:
        """Bind session to project (called once at session creation)."""

    def get_project_for_session(self, session_id: str) -> Project | None:
        """Get project bound to session."""

    def unbind_session(self, session_id: str) -> None:
        """Clean up when session ends."""
```

**2. Session Initialization Hook**

Intercept session creation in StreamableHTTPSessionManager:
```python
# After session created, before first tool call:
async def on_session_initialized(session_id: str, session: ServerSession):
    # Check if client supports roots
    if session.client_params.capabilities.roots:
        roots_result = await session.list_roots()
        if roots_result.roots:
            project_path = uri_to_path(roots_result.roots[0].uri)
            project_manager.get_or_create_project(project_path)
            project_manager.bind_session(session_id, project_path)
```

**3. Tool Context Resolution**

Thread session ID through to tools:
```python
# Option A: Thread-local storage
_session_context = threading.local()

def set_current_session(session_id: str):
    _session_context.session_id = session_id

def get_current_session() -> str | None:
    return getattr(_session_context, 'session_id', None)

# In tool execution:
class Tool(Component):
    @property
    def project(self) -> Project:
        session_id = get_current_session()
        if session_id:
            return self.agent.project_manager.get_project_for_session(session_id)
        return self.agent._default_project  # backward compat
```

### Changes Required

| File | Change |
|------|--------|
| `src/serena/project_manager.py` | NEW: ProjectManager class |
| `src/serena/agent.py` | Add ProjectManager, modify get_active_project() |
| `src/serena/patches/.../streamable_http_manager.py` | Hook session init, set thread-local |
| `src/serena/tools/tools_base.py` | Use session-aware project resolution |
| `src/serena/mcp.py` | Pass project_manager to agent |

### Backward Compatibility

1. **Single-session mode unchanged**: First session's project becomes default
2. **No session ID available**: Falls back to default project
3. **Client without roots capability**: Uses explicit activate_project tool
4. **Existing tools unchanged**: Property-based project resolution handles routing

### LSP Sharing

- LSPManager stays project-scoped (current behavior)
- Multiple sessions on same project share same LSPManager
- ProjectManager.get_or_create_project() returns existing project if path matches

## Next Steps

1. ~~Examine protocol relationships~~ ✓ (MCP over HTTP, single session ID)
2. ~~Confirm LSP sharing strategy~~ ✓ (per-project, not per-session)
3. ~~Identify session-to-project binding mechanism~~ ✓ (MCP roots capability)
4. **Design ProjectManager class** (ready for implementation)
5. **Prototype session initialization hook**
6. **Test with multiple Claude Code instances**

## Git Temporal Analysis

### Chronological Evolution of Key Features

**April 2025** - `2e1e5e5` - Project Activation Foundation
- Author: Dominik Jain
- First introduction of `activate_project` tool
- Serena-wide config file `serena_config.yml` with project list
- Sequential project switching (one at a time)
- Key: `enable_project_activation` setting

**November 2025** - `19be1c4` - Single-Project Context Concept
- Author: Dominik Jain
- Added `single_project: bool` to `SerenaAgentContext`
- IDE-assistant context uses `single_project: true`
- Disables `activate_project` tool when in single-project mode
- Key insight: Some contexts are *intentionally* single-project

**October 2025** - `e0ab4db` - LanguageServerManager for Polyglot
- Author: Dominik Jain
- Added `LSPManager` for multi-language support within ONE project
- Pattern: `_language_servers: dict[Language, Optional[SolidLanguageServer]]`
- Key insight: LSP instances are per-project, not per-session

**October 2025** - `e2cd053` - LSPManager Integration (My Commit)
- Author: Ketema Harris
- Integrated `LSPManager` into `SerenaAgent`
- Added file routing: `get_language_server_for_file()`
- Polyglot detection: `len(project.languages) > 1`
- Pattern we can reuse for multi-project routing

**October 2025** - `a193fcd` - Session Handling Patch (My Commit)
- Author: Ketema Harris
- Created `src/serena/patches/mcp/server/streamable_http_manager.py`
- Handles invalid/expired session IDs gracefully
- Key: `_server_instances: dict[str, StreamableHTTPServerTransport]`
- Session tracking already exists at transport level!

**October 2025** - `e91d66c` - Session Patch Enhancement (My Commit)
- Author: Ketema Harris
- Extended session handling for Augment client caching issues
- New sessions created instead of 400 errors
- Pattern: Session ID → Transport → MCPServer

**December 2025** - `51041e9` - Project-from-CWD Feature
- Author: Robin Breathe
- Added `--project-from-cwd` CLI flag
- `find_project_root()` searches up for `.serena/project.yml` or `.git`
- Key: Auto-detection at **startup time**, not per-session

### Patterns to Reuse

1. **LSPManager Pattern** (from `e0ab4db`)
   - Per-project manager for multiple instances
   - Factory method `get_or_create_language_server()`
   - File routing based on extension/language

2. **Session Patch Architecture** (from `a193fcd`)
   - Already have session tracking at transport level
   - `_server_instances` dict maps session_id → transport
   - Need to extend to map session_id → project

3. **Project Detection** (from `51041e9`)
   - `find_project_root()` algorithm exists
   - Searches up directory tree for markers
   - Can reuse for MCP roots URI → project path

### Key Architectural Decisions in Git History

**Decision 1**: LSP is per-project, not per-session
- Evidence: `LSPManager` in `Project` class
- Rationale: LSP state is project-scoped (symbols, diagnostics)
- Implication: Sessions on same project share LSPManager

**Decision 2**: Single-project contexts exist intentionally
- Evidence: `single_project: bool` in context config
- Rationale: Some use cases (IDE integration) want project switching disabled
- Implication: Multi-project is additive, not replacement

**Decision 3**: Session ID stops at transport layer
- Evidence: `streamable_http_manager.py` has session_id
- Evidence: `ServerSession` does NOT have session_id
- Evidence: Serena sets `context_kwarg=None` in mcp.py
- Implication: Need thread-local or patching to propagate session ID

### Implementation Insights from History

1. **Follow LSPManager pattern** for `ProjectManager`:
   ```python
   # Like LSPManager manages languages, ProjectManager manages projects
   class ProjectManager:
       _projects: dict[str, Project] = {}  # path → Project (like LSPManager._language_servers)
       _session_bindings: dict[str, str] = {}  # session_id → path (NEW)
   ```

2. **Extend session patch** in `streamable_http_manager.py`:
   - Session creation already captured (line 246-256)
   - Add hook after session created to query MCP roots
   - Bind session to project path

3. **Reuse find_project_root** algorithm:
   - Already handles `.serena/project.yml` detection
   - Already handles `.git` fallback
   - Convert MCP `file://` URI to path, use same algorithm

## References

- [MCP Security Best Practices](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices)
- [MCP Session Isolation Discussion](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1087)
- [Serena Multi-Project Issue #474](https://github.com/oraios/serena/issues/474)
- [JetBrains Multi-Instance PR #305](https://github.com/oraios/serena/pull/305)

### Git Commits Referenced
- `2e1e5e5` - Project activation introduction
- `19be1c4` - Single-project context
- `e0ab4db` - LanguageServerManager
- `e2cd053` - LSPManager integration to agent
- `a193fcd` - Session handling patch
- `e91d66c` - Session patch enhancement
- `51041e9` - Project-from-cwd feature
