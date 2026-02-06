# Debug Instrumentation Pattern for Serena HTTP Server

## When to Use
- Multi-client live debugging where you need to trace request flow across sessions
- LSP pool lifecycle investigation
- Path resolution debugging across workspaces

## Pattern (SERENA_DEBUG env-gated)

```python
# === DEBUG INSTRUMENTATION (remove after investigation) ===
import os as _os; import sys as _sys  # noqa: E702
if _os.environ.get('SERENA_DEBUG'):
    _sys.stderr.write(f"[DEBUG <location>] key=value, key2=value2\n"); _sys.stderr.flush()
    if _os.environ.get('SERENA_DEBUG') == 'pdb': breakpoint()
# === END DEBUG ===
```

## Key Principles
1. **Always gated by `SERENA_DEBUG` env var** — zero cost in production
2. **Write to stderr** (not stdout) — doesn't interfere with MCP JSON-RPC on stdout
3. **Always flush** — ensures output appears immediately in log tailing
4. **Use `_os`/`_sys` prefixed imports** — avoids shadowing module-level imports
5. **Optional `pdb` mode** — set `SERENA_DEBUG=pdb` to drop into debugger at that point
6. **Bracket with comment markers** — `=== DEBUG ... ===` / `=== END DEBUG ===` for easy grep/removal
7. **Module-level trace** — add at top of file to confirm module is loaded:
   ```python
   # === DEBUG: MODULE-LEVEL TRACE (fires on import) ===
   import os as _dbg_os, sys as _dbg_sys
   if _dbg_os.environ.get('SERENA_DEBUG'):
       _dbg_sys.stderr.write(f"[DEBUG MODULE LOAD] <file>.py loaded\n")
       _dbg_sys.stderr.flush()
   # === END MODULE-LEVEL TRACE ===
   ```

## Locations Used (2026-02-06 investigation)
- `agent.py`: module load, `get_language_server_for_file`, `language_server` property
- `global_lsp_pool.py`: `acquire()` method — pool key, can_serve_path check
- `lsp_capability_adapter.py`: `add_workspace_root` — root addition notification

## How to Start Debug Server
```bash
cd /Users/ketema/projects/serena
SERENA_DEBUG=1 PATH=".venv/bin:$PATH" PORT=9122 python -m serena.mcp_server
```

## How to Tail Debug Output
```bash
# If running via launchctl:
tail -f /tmp/serena-debug.log  # (redirect stderr to file in plist)

# If running in terminal:
# stderr appears inline
```

## Removal
```bash
grep -rn "=== DEBUG" src/serena/  # Find all debug blocks
git diff src/serena/              # Review before removing
git checkout -- src/serena/agent.py src/serena/global_lsp_pool.py src/serena/lsp_capability_adapter.py
```
