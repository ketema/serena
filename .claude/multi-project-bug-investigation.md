# Multi-Project Path Resolution Bug Investigation

**Date**: 2026-02-05
**Branch**: fix/mcp-protocol-version-parsing (but bug is in feature/multi-project-support work)
**Status**: INVESTIGATION IN PROGRESS - Root cause not yet identified

## The Bug

**Symptom**: When multiple Claude Code instances share one HTTP MCP server, each working on different projects, path resolution uses the WRONG project's workspace.

**Evidence**:
- Session ID: `9691a4dbdbae4c95ba3ae462ca01874f`
- User activated OpenMemory project at `/Users/ketema/projects/OpenMemory`
- Tool call error: `File or directory not found: /Users/ketema/projects/serena/tools/backup_restore.py`
- The path was resolved against `serena` instead of `OpenMemory`

**User's Key Insight**:
> "it seems to me that possibly the http server root path is getting confused for the MCP root path"

The HTTP server runs from `/Users/ketema/projects/serena` (its CWD), and this path appears to leak into session workspaces.

## Architecture Summary

### Session Flow
```
HTTP Request with session_id header
    ↓
mcp.py: run_with_session_context(session_id, lambda: tool.apply_ex(...))
    ↓
mcp_session_bridge.py: set_session_context(session_id)
    - Looks up session from SessionRegistry
    - Sets ContextVar: _current_session_id
    - Sets ContextVar: _current_session (SessionContext object)
    ↓
tool.apply_ex() → issue_task(task)
    - copy_context() captures ContextVars
    - Task submitted to thread pool
    ↓
Thread: context.run(task)
    - task calls self.project → get_active_project_or_raise()
    - get_active_project_or_raise() calls get_current_session()
    - Returns Project.load(session.workspace_root)
```

### Key Files

| File | Purpose |
|------|---------|
| `src/serena/mcp.py` | MCP server, tool dispatch, session bridge wiring |
| `src/serena/mcp_session_bridge.py` | Bridges transport sessions to SessionRegistry |
| `src/serena/session_registry.py` | Stores session_id → SessionContext mapping |
| `src/serena/session_context.py` | ContextVar for current session |
| `src/serena/agent.py` | get_active_project_or_raise(), activate_session_project() |
| `src/serena/tools/tools_base.py` | Tool base class, project property, apply_ex() |
| `src/serena/task_executor.py` | Thread pool with copy_context() propagation |

### Two ContextVars
1. `session_context.py:12`: `_current_session: ContextVar[SessionContext]` - the session object
2. `mcp_session_bridge.py:42`: `_current_session_id: ContextVar[str]` - just the ID

## What I Verified Works Correctly

1. **SessionRegistry singleton**: mcp.py creates ONE registry, wires it to both agent and bridge
2. **copy_context() usage**: TaskExecutor calls `copy_context()` at line 206, `context.run()` at line 70
3. **No cached Project**: `self.project` is a property that calls `get_active_project_or_raise()` each time
4. **bind_session creates new SessionContext**: No mutation, creates fresh object
5. **activate_session_project flow**: Correctly unbinds old, binds new, calls set_current_session

## Hypotheses NOT Yet Ruled Out

### Hypothesis 1: on_transport_session_created Default Workspace
When HTTP transport creates a session, `on_transport_session_created` is called with `workspace_root=None`:
```python
# mcp_session_bridge.py:102-106
if workspace_root is None:
    workspace_root = Path.cwd()  # ← HTTP server's CWD = /Users/ketema/projects/serena
self._session_registry.bind_session(mcp_session_id, workspace_root)
```

Later, `activate_project` should update this. But maybe something prevents the update from being visible to tool dispatch?

### Hypothesis 2: ContextVar Not Propagated Correctly
Even though `copy_context()` is called, maybe the ContextVar value at that moment is wrong?

Sequence to verify:
1. `run_with_session_context` sets ContextVar (line 269)
2. `func()` is called synchronously (line 326)
3. Inside func, `apply_ex` calls `issue_task`
4. `issue_task` calls `copy_context()` (line 206)

At step 4, is the ContextVar from step 1 still visible?

### Hypothesis 3: Session Lookup Returns Wrong Session
When `set_session_context` calls `get_session(session_id)`, maybe it returns a session with the old workspace?

```python
# mcp_session_bridge.py:149-163
session = self._session_registry.get_session(session_id)
if session is None:
    return None
token = _current_session_id.set(session_id)
set_current_session(session)  # ← Is this the UPDATED session?
```

### Hypothesis 4: Multiple Agent Instances
The SerenaApp creates ONE agent. What if something about the agent's state is shared incorrectly?

## What To Do Next

### Step 1: Add Diagnostic Logging
Add logging to trace the exact session and workspace at each step:

```python
# In set_session_context:
logger.info(f"set_session_context: session_id={session_id}, workspace={session.workspace_root if session else 'None'}")

# In get_active_project_or_raise:
logger.info(f"get_active_project_or_raise: session={session.session_id if session else 'None'}, workspace={session.workspace_root if session else 'None'}")

# In apply_ex before issue_task:
logger.info(f"apply_ex: current_session={get_current_session()}")
```

### Step 2: Verify Registry State
Add a tool or endpoint to dump SessionRegistry contents:
- All session IDs
- Each session's workspace_root
- Verify the OpenMemory session has correct workspace AFTER activate_project

### Step 3: Trace Exact Failure
With logging, reproduce the bug:
1. Start serena HTTP server
2. Connect Session A, activate serena
3. Connect Session B, activate OpenMemory
4. From Session B, call get_symbols_overview
5. Check logs to see what workspace Session B gets

### Step 4: Check for Race Conditions
Maybe `on_transport_session_created` is called AFTER `activate_project` and overwrites the workspace?

Check order of operations:
- When does transport create session?
- When does activate_project update session?
- Are these racing?

## Code Snippets For Reference

### set_session_context (mcp_session_bridge.py:133-164)
```python
def set_session_context(self, session_id: str) -> Token | None:
    if not session_id:
        raise ValueError("session_id must be non-empty")
    session = self._session_registry.get_session(session_id)
    if session is None:
        logger.debug("Session %s not found in registry...", session_id)
        return None
    token = _current_session_id.set(session_id)
    set_current_session(session)
    return token
```

### get_active_project_or_raise (agent.py:442-452)
```python
def get_active_project_or_raise(self) -> Project:
    session = get_current_session()
    if session is None:
        raise ProjectNotFoundError("No active session...")
    try:
        return Project.load(session.workspace_root)
    except Exception as exc:
        raise ProjectNotFoundError("No active project...") from exc
```

### activate_session_project (agent.py:827-870)
```python
def activate_session_project(self, session_id: str, workspace_root: Path, source: str = "explicit") -> Project:
    # ... validation ...
    existing_session = self._session_registry.get_session(session_id)
    if existing_session is not None:
        if Path(existing_session.workspace_root).resolve() != workspace_root.resolve():
            self._session_registry.unbind_session(session_id)
        else:
            set_current_session(existing_session)
            return Project.load(workspace_root)

    session = self._session_registry.bind_session(session_id, workspace_root, source)
    set_current_session(session)
    # ... load project ...
```

## Session Bridge Wiring (mcp.py:370-391)
```python
if self.agent is not None:
    self.agent._session_bridge = self.get_session_bridge()
    self.agent._session_registry = self.get_session_registry()
    # ...

if hasattr(mcp_server, '_session_manager'):
    bridge = self.get_session_bridge()
    transport_manager = mcp_server._session_manager
    transport_manager.set_session_callbacks(
        on_session_created=lambda sid: bridge.on_transport_session_created(sid, workspace_root=None),
        on_session_closed=lambda sid: bridge.on_transport_session_closed(sid),
    )
```

## Related Files Read During Investigation
- mcp_session_bridge.py (full)
- contracts/mcp_session_bridge_contract.py (full)
- agent.py (key sections)
- tools_base.py (key sections)
- task_executor.py (key sections)
- session_registry.py (key sections)
- session_context.py (full - small file)
- mcp.py (key sections)

## Constitutional Notes
- This is an M2 DISCOVER CONTEXT investigation
- No code changes made yet
- Need to identify root cause before planning fix (M3)
- User approval required before any implementation
