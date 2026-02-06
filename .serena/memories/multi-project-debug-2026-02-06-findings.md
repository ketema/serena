# Multi-Project Debug Session Findings (2026-02-06)

## Problem Investigated
- OpenMemory session resolved paths against serena root
- `restart_language_server` was needed after reconnecting clients
- `restart_language_server` nukes entire GlobalLanguageServerPool for ALL clients

## Root Causes Identified

### 1. PATH Issue (Pyright crash)
- `PyrightServer.__init__` uses `cmd="python -m pyright.langserver --stdio"`
- System Python 3.14 (`/opt/homebrew/opt/python@3.14/libexec/bin/python`) doesn't have pyright
- Venv Python 3.11 (`.venv/bin/python`) DOES have pyright
- Neither debug server startup nor launchctl plist include `.venv/bin` in PATH
- **Fix**: Add `.venv/bin` to PATH in launchctl plist

### 2. Path Resolution (already fixed in REQ-2026-003)
- `repository_root_path` set at LSP creation time (first session's workspace)
- `workspace_root` parameter added to all 20+ path-resolving methods
- REQ-2026-003 commits already deployed on feature/multi-project-support

## Verified Working (with PATH fix)
- 3 concurrent Python sessions: serena, OpenMemory, Euler_Problems
- Single shared Pyright LSP with multi-root workspace
- `add_workspace_root` fires correctly for new workspaces
- `can_serve_path` returns False → triggers workspace addition
- Session isolation correct (each session has correct workspace_root)
- Pool key is `python` (multi_root=True, keyed by language only)

## Session IDs in Test
- 8da0de79 = serena (this debugging client)
- 0961f1c7 = OpenMemory
- ac75a4d8 = Euler_Problems

## Action Items
1. Update launchctl plist PATH to include .venv/bin
2. Consider making PyrightServer use sys.executable instead of bare "python"
3. Remove debug instrumentation from agent.py, global_lsp_pool.py, lsp_capability_adapter.py
