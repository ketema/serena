# Multi-Project Session Isolation - Implementation Plan v1

**Date**: 2026-01-11
**Branch**: feature/multi-project-support
**Status**: M3 PLAN - Awaiting AI Panel Critique

---

## Architectural Decisions (Q1-Q5)

### Q1: Path Resolution
**Decision**: Strict absolute paths, reject cross-boundary, helpful errors
- All tool operations require absolute paths
- Reject relative paths that escape project boundary
- Return helpful error: "Path /x/y escapes project boundary /z. Use absolute path or activate different project."

### Q2: Missing MCP Roots
**Decision**: Not implementing MCP roots for v1
- MCP roots is a new protocol feature with unknown client support
- Stick with explicit `activate_project(path)` - already works
- Log if roots detected but don't depend on it
- Can add roots support as future enhancement

### Q3: Async Safety
**Decision**: ContextVar with explicit token reset
- Use `contextvars.ContextVar` instead of `threading.local`
- ContextVar is async-safe - follows coroutine context across awaits
- Pattern:
  ```python
  from contextvars import ContextVar
  _session_id: ContextVar[str | None] = ContextVar('session_id', default=None)
  
  token = _session_id.set(session_id)
  try:
      await some_async_operation()
  finally:
      _session_id.reset(token)
  ```

### Q4: LSP Lifecycle
**Decision**: Lazy loading + configurable idle timeouts + isolated failures
- LSPs start on-demand (first symbol operation), not at project activation
- Individual idle timeouts per language (configurable in project.yml):
  ```yaml
  lsp_timeouts:
    # Heavy LSPs - reclaim faster
    rust: 1800        # 30 min
    java: 1800        # 30 min
    csharp: 1800      # 30 min
    
    # Medium LSPs
    typescript: 3600  # 1 hr
    go: 3600          # 1 hr
    haskell: 3600     # 1 hr
    
    # Light LSPs - keep longer
    python: 7200      # 2 hr
    ruby: 7200        # 2 hr
    php: 7200         # 2 hr
    
    default: 3600     # 1 hr
  ```
- Isolated failures: LSP crash logs error + marks language unavailable for session, doesn't crash server

### Q5: Nested Repo Handling
**Decision**: DEEPEST .serena/project.yml wins, explicit overrides implicit
- Auto-detection uses innermost .serena/project.yml (matches git behavior)
- Explicit `activate_project(path)` always overrides auto-detection
- Log which project was auto-detected for transparency
- Path validation (Q1) prevents boundary escape

---

## Implementation Components

### Phase 1: SessionContext Data Model

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from contextvars import ContextVar

@dataclass
class SessionContext:
    """Per-session isolation context."""
    session_id: str
    workspace_root: Path
    activation_source: Literal["explicit", "auto"]
    activation_time: datetime
    active_modes: list[str]
    lsp_references: dict[str, Any]  # language -> LSP instance ref
    
# Async-safe session context
_current_session: ContextVar[SessionContext | None] = ContextVar(
    'current_session', default=None
)

def get_current_session() -> SessionContext | None:
    return _current_session.get()

def set_current_session(ctx: SessionContext) -> contextvars.Token:
    return _current_session.set(ctx)
```

### Phase 2: SessionRegistry

```python
class SessionRegistry:
    """Thread-safe registry mapping MCP session_id → SessionContext."""
    
    def __init__(self):
        self._sessions: dict[str, SessionContext] = {}
        self._lock = asyncio.Lock()
    
    async def bind_session(
        self, 
        session_id: str, 
        workspace_root: Path,
        source: Literal["explicit", "auto"] = "explicit"
    ) -> SessionContext:
        """Bind session to workspace. Thread-safe."""
        async with self._lock:
            ctx = SessionContext(
                session_id=session_id,
                workspace_root=workspace_root,
                activation_source=source,
                activation_time=datetime.now(),
                active_modes=[],
                lsp_references={}
            )
            self._sessions[session_id] = ctx
            return ctx
    
    async def unbind_session(self, session_id: str) -> None:
        """Unbind session and cleanup LSPs if last session for project."""
        async with self._lock:
            ctx = self._sessions.pop(session_id, None)
            if ctx:
                await self._cleanup_if_last(ctx.workspace_root)
    
    async def _cleanup_if_last(self, workspace_root: Path) -> None:
        """Shutdown LSPs if no other sessions use this project."""
        remaining = [s for s in self._sessions.values() 
                     if s.workspace_root == workspace_root]
        if not remaining:
            # Trigger LSP idle timeout immediately
            await self._shutdown_project_lsps(workspace_root)
```

### Phase 3: Path Validation

```python
def validate_path(
    relative_path: str | Path, 
    session: SessionContext
) -> Path:
    """Validate and resolve path within project boundary.
    
    Raises:
        PathBoundaryError: If resolved path escapes project root
    """
    project_root = session.workspace_root
    resolved = (project_root / relative_path).resolve()
    
    try:
        resolved.relative_to(project_root)
    except ValueError:
        raise PathBoundaryError(
            f"Path '{resolved}' escapes project boundary '{project_root}'. "
            f"Use absolute path or activate different project."
        )
    
    return resolved
```

### Phase 4: LSP Timeout Manager

```python
class LSPTimeoutManager:
    """Manage per-language idle timeouts for LSP reclamation."""
    
    DEFAULT_TIMEOUTS = {
        "rust": 1800, "java": 1800, "csharp": 1800,
        "typescript": 3600, "go": 3600, "haskell": 3600,
        "python": 7200, "ruby": 7200, "php": 7200,
        "default": 3600
    }
    
    def __init__(self, custom_timeouts: dict[str, int] | None = None):
        self._timeouts = {**self.DEFAULT_TIMEOUTS, **(custom_timeouts or {})}
        self._last_used: dict[str, datetime] = {}
        self._check_task: asyncio.Task | None = None
    
    def touch(self, language: str) -> None:
        """Mark language as recently used."""
        self._last_used[language] = datetime.now()
    
    def get_timeout(self, language: str) -> int:
        """Get timeout for language in seconds."""
        return self._timeouts.get(language, self._timeouts["default"])
    
    async def start_monitoring(self) -> None:
        """Start background task to check idle timeouts."""
        self._check_task = asyncio.create_task(self._monitor_loop())
    
    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(60)  # Check every minute
            now = datetime.now()
            for lang, last_used in list(self._last_used.items()):
                timeout = self.get_timeout(lang)
                if (now - last_used).total_seconds() > timeout:
                    await self._reclaim_lsp(lang)
```

### Phase 5: Session-Aware Tool Dispatch

```python
# In tools_base.py
class Tool:
    def apply(self, *args, **kwargs):
        session = get_current_session()
        if session is None:
            raise NoActiveSessionError("No active session. Call activate_project first.")
        
        # Validate paths if present
        if 'relative_path' in kwargs:
            kwargs['relative_path'] = validate_path(
                kwargs['relative_path'], session
            )
        
        return self._apply_impl(*args, session=session, **kwargs)
```

---

## Test Cases Required

### Session Isolation
1. `test_session_binds_to_project` - Session binds to correct workspace
2. `test_session_isolation_prevents_cross_project` - Session A can't access Session B's files
3. `test_concurrent_sessions_different_projects` - Two sessions, different projects, no interference
4. `test_session_cleanup_on_disconnect` - Unbind triggers LSP cleanup if last session

### Path Validation
5. `test_absolute_path_accepted` - Absolute paths within project work
6. `test_relative_path_within_boundary` - Relative paths resolved correctly
7. `test_boundary_escape_rejected` - `../../../etc/passwd` rejected with helpful error
8. `test_symlink_boundary_check` - Symlinks can't escape boundary

### LSP Lifecycle
9. `test_lsp_lazy_start` - LSP only starts on first symbol operation
10. `test_lsp_idle_timeout` - LSP shuts down after idle timeout
11. `test_lsp_failure_isolated` - One LSP crash doesn't affect others
12. `test_custom_timeout_per_language` - project.yml timeouts respected

### Nested Projects
13. `test_deepest_project_yml_wins` - Innermost .serena/project.yml used
14. `test_explicit_activation_overrides` - activate_project(path) overrides auto-detection
15. `test_worktree_isolation` - Git worktrees treated as separate projects

### ContextVar Safety
16. `test_contextvar_survives_await` - Session context preserved across async operations
17. `test_contextvar_isolates_concurrent_requests` - No session leakage between concurrent requests

---

## Integration Points

### Existing Code to Modify

1. **`src/serena/agent.py`**
   - Add SessionRegistry instance
   - Modify `_activate_project` to use SessionContext
   - Add session binding on MCP connection

2. **`src/serena/tools/tools_base.py`**
   - Add `validate_path()` call in Tool base class
   - Add session context injection

3. **`src/serena/lsp_manager.py`** (already exists, 21KB)
   - Integrate with LSPTimeoutManager
   - Add per-language timeout configuration

4. **`src/serena/mcp.py`**
   - Bind session_id → SessionContext on connection
   - Unbind on disconnect

5. **`src/serena/config/`**
   - Add `lsp_timeouts` to project.yml schema

---

## Success Criteria

1. ✅ Two MCP clients can connect simultaneously to different projects
2. ✅ Session A cannot access files in Session B's project
3. ✅ LSPs start on-demand, not at activation
4. ✅ LSPs shut down after configurable idle timeout
5. ✅ One LSP failure doesn't crash server
6. ✅ Nested projects resolved to deepest .serena/project.yml
7. ✅ Explicit activation overrides auto-detection
8. ✅ All 17+ test cases passing

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Race condition in SessionRegistry | Use asyncio.Lock for all mutations |
| ContextVar not propagating | Explicit token management with try/finally |
| LSP timeout too aggressive | Start conservative (1hr), make configurable |
| Memory leak from orphaned sessions | Periodic cleanup check, unbind on disconnect |
| Breaking existing single-session workflows | Backward compatible - single session works unchanged |

---

## Not In Scope (v1)

- MCP roots protocol support (future enhancement)
- Dynamic project switching within session
- Cross-project symbol search
- Shared LSP instances across sessions

---

## References

- Design review: `.serena/memories/multi-project-design-review.md`
- Architecture proposal: `.serena/memories/multi-project-architecture-proposal.md`
- Existing LSP Manager: `src/serena/lsp_manager.py` (21KB, lazy loading implemented)
- GitHub issue: ketema/serena#6
