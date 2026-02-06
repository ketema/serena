# Constitutional Fix: LSP Capability Adapter (b4471d39)

**Date**: 2026-02-05
**Commit**: 0ae1b375
**Status**: COMPLETE - ZERO VIOLATIONS

## Violations Fixed (7 total)

### CL3/CL12 Stubs (2 violations)
- `add_workspace_root` was returning `True` without action
- `remove_workspace_root` was returning `True` without action
- **Fix**: Implemented real LSP `workspace/didChangeWorkspaceFolders` notifications

### CL12-E Missing Traceability (2 violations)
- Tests lacked clause IDs
- **Fix**: Added `"""Enforces: POST-3"""` docstrings

### Theater Tests (2 violations)
- Tests only checked return value, not behavior
- **Fix**: Added assertions for:
  - `did_change_workspace_folders.assert_called_once()`
  - Params contain correct uri/name
  - workspace_roots tracking updated

### CL10 Mock Verification (1 violation)
- Mock never asserted calls
- **Fix**: Behavioral assertions on mock method calls

## Technical Details

### LSP Notification Pattern
```python
workspace_folder: lsp_types.WorkspaceFolder = {"uri": root_uri, "name": root.name}
params: lsp_types.DidChangeWorkspaceFoldersParams = {
    "event": {"added": [workspace_folder], "removed": []}
}
ls.server.notify.did_change_workspace_folders(params)
```

### Files Modified
- src/serena/lsp_capability_adapter.py (add/remove_workspace_root)
- src/serena/global_lsp_pool.py (workspace_roots init)
- test/serena/test_lsp_capability_adapter.py (behavioral tests)

## Evidence
- T:test_lsp_capability_adapter::*=PASS (36/36)
- Constitutional audit: ZERO VIOLATIONS
- Ralph loop: Promise output confirmed
