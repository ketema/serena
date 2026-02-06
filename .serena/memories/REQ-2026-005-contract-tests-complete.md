# REQ-2026-005: Contract Tests Complete (M4 TDD Cycle)

## Status: ALL 5 CONTRACT TEST SUITES GREEN

### Test Files & Coverage
| File | Tests | Contract | Status |
|------|-------|----------|--------|
| tests/test_lsp_lifecycle_authority.py | 12 | SurgicalRestartContract | GREEN |
| tests/test_workspace_readiness.py | 16 | WorkspaceReadinessContract | GREEN |
| tests/test_lsp_lifecycle_guards.py | 15 | RestartToolGuard + PoolIntegrity | GREEN |
| tests/test_tool_exception_handler.py | 12 | ToolExceptionHandlerContract | GREEN |
| **Total** | **55** | **5 contracts, 30+ clause IDs** | **GREEN** |

### Contract Authority
- contracts/lsp_lifecycle_authority_contract.py (singular source, CL12-C)
- 5 ABC contract classes, 3 custom exceptions
- Requirements: REQ-2026-005-lsp-lifecycle-authority.md

### Commits (ketema branch)
- bdcd0fde: SurgicalRestartContract tests + mock implementation
- f1976903: PoolIntegrity fix (return str not None for POST-PI-02)
- c609b714: ToolExceptionHandlerContract tests (with hasattr→call_count fix)

### AI Panel Review
- conversation_id: 6700ada8-ba0f-4a18-80a0-99ab9bfb748d
- Verdict: SOUND CONTRACT TESTING PATTERN (not theater)
- Risk noted: Mock drift when real API changes (Medium, mitigated at integration)

### Key Fix During TDD
- INV-TEH-01 test used `hasattr(Mock(), "reset_language_server")` — always True on Mock
- Fixed to `mock_agent.reset_language_server.call_count == 0` (correct Mock assertion)

### Next Steps (Implementation Integration)
Real implementation in src/ files still needed:
1. src/serena/global_lsp_pool.py — surgical_restart_lsp(), workspace root snapshot/restore
2. src/serena/tools/tools_base.py — apply_ex handler change (pool nuke → surgical restart)
3. src/serena/agent.py — guarded_reset_language_server()
4. src/serena/tools/symbol_tools.py — RestartLanguageServerTool HTTP guard
5. src/serena/lsp_capability_adapter.py — probe_workspace_readiness after add_workspace_root
