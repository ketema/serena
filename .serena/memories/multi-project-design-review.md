# Multi-Project Design Review - Devil's Advocate Analysis

**Date**: 2025-12-27
**Branch**: feature/multi-project-support
**Status**: PENDING USER REVIEW

---

## Design Flaws Found

| Issue | Severity | Impact |
|-------|----------|--------|
| Nested repos: ambiguous project selection | MEDIUM | Wrong project bound |
| Submodules: ownership unclear | MEDIUM | LSP confusion |
| **CWD+paths: shell vs tool state mismatch** | **HIGH** | Wrong file accessed |
| MCP roots: not all clients support | HIGH | No fallback path |
| MCP roots: empty response | MEDIUM | Undefined behavior |
| Race: concurrent project creation | HIGH | Duplicate LSP, corruption |
| Race: session cleanup vs new session | MEDIUM | Use-after-free potential |
| Context mixing: shared LSP, different permissions | MEDIUM | Security/isolation |
| Async/sync boundary: activation in async | MEDIUM | Blocking, complexity |
| Thread-local in async: wrong session ID | **HIGH** | Cross-session pollution |

---

## Issue 1: Nested Git Repos

### The Serena Situation
```
/ametek_chess/                    <- has .git/ AND .serena/project.yml
├── .git/
├── .serena/project.yml
└── submodules/
    └── serena/                   <- has .git/ (separate repo)
        ├── .git/
        ├── .serena/
        │   ├── project.yml       <- ALSO EXISTS!
        │   └── memories/
        └── src/
            └── agent.py          <- agent starts HERE
```

**Verified**: Both `/ametek_chess/.serena/project.yml` and `/ametek_chess/submodules/serena/.serena/project.yml` exist.

### Problem 1A: Ambiguous Intent
- Agent starts at `/ametek_chess/submodules/serena/src/`
- `find_project_root()` walks UP, finds `serena/.serena/project.yml` first (nearest)
- But what if agent WANTED to work on ametek_chess from this location?
- No mechanism to override automatic detection

### Problem 1B: Path Resolution Confusion
- Session binds to `/ametek_chess/submodules/serena/`
- Agent calls `read_file("../../CLAUDE.md")`
- Serena resolves: `os.path.join(project_root, relative_path)`
- Result: `/ametek_chess/submodules/serena/../../CLAUDE.md` = `/ametek_chess/CLAUDE.md`
- **This WORKS but violates project isolation!**
- Agent can read/write files OUTSIDE bound project via relative paths

### Question for User
- Should relative paths be constrained to project boundary?
- Or is escaping via `../` acceptable behavior?

---

## Issue 2: Submodules

### Git Submodule Structure
```
/myproject/
├── .git/
├── .gitmodules              # defines submodule
└── vendor/
    └── library/
        ├── .git             # FILE, not directory! Contains: gitdir: ../../.git/modules/library
        └── src/
```

### Problem 2A: Submodule Detection
- `find_project_root()` checks `(directory / ".git").exists()`
- Returns `True` for both files (submodule) and directories (real repo)
- Algorithm correctly DETECTS submodules
- But should submodule be its OWN project or part of parent?

### Problem 2B: LSP Confusion
- Parent project might have Python LSP
- Submodule might be TypeScript library
- If session bound to parent, which LSPManager handles submodule files?
- File routing exists for polyglot (multiple languages), but not for nested projects

### Question for User
- Should submodules be treated as separate projects?
- Or should they inherit parent's project context?

---

## Issue 3: CWD Changes + Relative Paths (HIGH SEVERITY)

### The Core Problem
12+ places in Serena resolve paths against `project_root`:
- `tools_base.py:325` - EditedFileContext
- `file_tools.py:114,140,443` - various file operations
- `symbol_tools.py:63` - symbol operations
- `code_editor.py:83,314,315,388` - code editing
- `project.py:196,289` - project operations

### Scenario: Shell vs Tool State Mismatch
```python
1. Session starts at /project-a/src/ -> binds to /project-a/
2. Agent runs: execute_shell_command("cd /project-b && ls")  # Works in shell!
3. Agent runs: read_file("main.py")  # Relative path
4. Serena resolves: os.path.join("/project-a/", "main.py")
5. Result: /project-a/main.py (NOT /project-b/main.py!)
```

- Shell commands have their OWN CWD (ephemeral per command)
- Serena tools ALWAYS use `project_root` for path resolution
- Shell CWD changes are INVISIBLE to Serena tools
- **Agent expects /project-b/main.py, gets /project-a/main.py**

### Problem 3B: What IS "Agent CWD"?
- MCP roots sent at session INITIALIZATION only
- If Claude Code changes CWD after connecting, roots DON'T update
- No "CWD update" mechanism in MCP protocol
- Session binding is FIXED at creation time

### Problem 3C: MCP Roots Capability Not Universal
- Design requires `session.list_roots()` to get client working directory
- Serena currently has ZERO references to `list_roots` or `roots/list`
- Not all MCP clients support this capability
- What's the fallback for clients without roots support?

### Question for User
- Is fixed binding (initial CWD only) the CORRECT behavior?
- Should we require absolute paths to avoid confusion?
- What's the fallback when client doesn't support MCP roots?

---

## Issue 4: Single ACTIVE Project Enforcement

### Context Configuration
`claude-code.yml` context:
```yaml
description: Claude Code (CLI agent where file operations... single project mode)
single_project: true
```

This means:
- `activate_project` tool is DISABLED for this context
- Session can't switch projects mid-session
- Designed for single-project workflows

### Problem 4A: Interpretation Ambiguity
Does `single_project: true` mean:
- A) **This session** can only work on one project (per-session) ✓
- B) **The server** can only have one active project (global) ✗

Code analysis confirms (A) - it's per-session. But documentation is unclear.

### Problem 4B: Context Mixing
```
Session A: claude-code context, binds to /chess/, single_project=true
Session B: agent context, binds to /webapp/, single_project=false
Session B: calls activate_project("/chess/")  # Switches to chess!
```

Now Sessions A and B are BOTH on `/chess/`:
- They share the same LSPManager
- Session A can't switch (single_project=true)
- Session B CAN switch (single_project=false)
- What if Session B modifies code while Session A has a symbol reference?
- **LSP state is shared but session isolation is expected!**

### Question for User
- Is context mixing (different contexts, same project) acceptable?
- Should we prevent sessions with different single_project settings from sharing LSP?

---

## Issue 5: Race Conditions (HIGH SEVERITY)

### Problem 5A: Concurrent Project Creation
```python
# Thread 1 (Session A)               # Thread 2 (Session B)
project = projects.get("/chess/")    project = projects.get("/chess/")
if project is None:                  if project is None:
    project = create_project(...)        project = create_project(...)
    projects["/chess/"] = project        projects["/chess/"] = project  # RACE!
```

Two sessions simultaneously creating same project:
- Duplicate LSP instances created
- Wasted memory/resources
- Potential state corruption
- Last write wins, first LSP orphaned

### Problem 5B: Session Cleanup Race
```python
# Session A ends                     # Session B starts (same project)
unbind_session(session_a)            bind_session(session_b, "/chess/")
if not sessions_for_project("/chess/"):
    shutdown_lsp("/chess/")          # Session B tries to use dead LSP!
```

Cleanup and creation race:
- Session A ends, triggers cleanup check
- Session B starts before cleanup completes
- Cleanup sees no sessions, shuts down LSP
- Session B now has dead LSP reference

### Solution Required
- Lock-based synchronization for project creation/deletion
- Reference counting for project lifecycle
- Atomic bind/unbind operations

---

## Issue 6: MCP Roots Reality Check

### Problem 6A: No Capability Checking
Serena doesn't currently check MCP client capabilities:
```bash
$ grep -r "ClientCapabilities\|capabilities" src/serena/
# Only LSP capabilities, not MCP capabilities
```

We ASSUME `list_roots()` works, but:
- Claude Code: probably supports it (untested)
- Cursor: unknown
- Augment: unknown
- Custom clients: probably not

### Problem 6B: Empty Roots Response
```python
roots_result = await session.list_roots()
if roots_result.roots:  # What if empty list?
    project_path = uri_to_path(roots_result.roots[0].uri)
else:
    # ??? No fallback defined
    # Options:
    #   1. Refuse connection
    #   2. Use --project CLI flag
    #   3. Prompt user
    #   4. Use CWD of server process
```

### Question for User
- What's the fallback when roots is empty or unsupported?
- Should we require `--project` flag as backup?

---

## Issue 7: Async/Sync Boundary

### Problem 7A: Async Session Creation -> Sync Project Activation
```python
# streamable_http_manager.py (ASYNC context)
async def _handle_stateful_request(...):
    new_session_id = uuid4().hex

    # Need to call list_roots() - ASYNC operation
    roots = await session.list_roots()

    # Need to activate project - Currently SYNC!
    agent._activate_project(project)  # SYNC call in ASYNC context

    # This works but is blocking
```

Current project activation is synchronous:
- `agent._activate_project()` - sync
- `agent.activate_project_from_path_or_name()` - sync

Calling sync from async blocks the event loop.

### Problem 7B: TaskExecutor is Single-Threaded
```python
# agent.py
self._task_executor = TaskExecutor(num_workers=1)  # SINGLE WORKER!
```

If project activation runs through task executor:
- It BLOCKS all other tool executions
- Session B can't run tools while Session A activates project
- Serialized project activation is slow

### Question for User
- Is blocking acceptable for project activation (rare operation)?
- Or should we make project activation async?

---

## Issue 8: Thread-Local Storage Gotcha (HIGH SEVERITY)

### Problem 8A: Async Context != Thread
```python
_session_context = threading.local()

# In async handler (e.g., streamable_http_manager.py)
def set_current_session(session_id):
    _session_context.session_id = session_id  # Sets in CURRENT thread

# But anyio/asyncio might switch threads for await!
await some_async_operation()  # Thread might change here

# After await, we might be in DIFFERENT thread
# _session_context.session_id could be WRONG or MISSING!
```

Thread-local storage doesn't work reliably in async code because:
- asyncio/anyio can migrate coroutines between threads
- Thread-local state doesn't follow the coroutine
- Session A's request could see Session B's session_id

### Problem 8B: ContextVar Alternative
```python
from contextvars import ContextVar

_session_id: ContextVar[str | None] = ContextVar('session_id', default=None)

# This IS async-safe
token = _session_id.set(session_id)
try:
    await some_async_operation()  # ContextVar follows coroutine!
    # Still has correct session_id
finally:
    _session_id.reset(token)
```

ContextVar is designed for async, but:
- Requires explicit propagation through async boundaries
- All async code must be aware of context
- More complex than thread-local

### Question for User
- Should we use ContextVar instead of threading.local?
- This affects the entire session propagation design

---

## Critical Questions Requiring User Input

### Q1: Path Resolution Behavior
When agent shell CWD differs from bound project, what's the CORRECT behavior?
- A) Always resolve against bound project (current design)
- B) Track shell CWD and resolve against that
- C) Require absolute paths only
- D) Error if relative path escapes project boundary

### Q2: Fallback for Missing Roots
If client doesn't support MCP roots capability:
- A) Refuse connection with error
- B) Require `--project` CLI flag
- C) Use server process CWD
- D) Prompt via MCP for project path

### Q3: Async Safety Pattern
For session ID propagation in async code:
- A) Use ContextVar (async-safe, more complex)
- B) Use threading.local (simpler, async-unsafe)
- C) Pass session_id explicitly through all calls
- D) Store in request object and thread through

### Q4: Project Lifecycle
When should project LSP be shut down?
- A) When last session unbinds (reference counting)
- B) Never (keep all projects alive)
- C) After timeout with no sessions
- D) Manual shutdown via tool

### Q5: Nested Repo Handling
For nested git repos like ametek_chess/submodules/serena:
- A) Use DEEPEST .serena/project.yml (current algorithm)
- B) Use SHALLOWEST (parent takes precedence)
- C) Require explicit --project flag for nested
- D) Let user configure via environment variable

---

## Next Steps

1. User reviews this document on larger screen
2. User provides answers to Q1-Q5
3. Revise design based on user decisions
4. Create implementation plan (M3)
5. Begin TDD implementation (M4)

---

## References

- Research document: `.serena/memories/multi-project-support-research.md`
- Git commits analyzed: 2e1e5e5, 19be1c4, e0ab4db, e2cd053, a193fcd, e91d66c, 51041e9
- Key files: `streamable_http_manager.py`, `agent.py`, `tools_base.py`, `cli.py`
