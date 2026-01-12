# Phase 1 Foundation - COMPLETE

**Date**: 2026-01-12
**Branch**: feature/multi-project-support

## Summary

Phase 1 Foundation implementation is COMPLETE. All 68 tests pass.

## Completed TDD Cycles

### TDD Cycle 1: Contract Evolution (REQ-ADAPT-1 to REQ-ADAPT-4)
- **Commits**: 721b1e9, 2111838, 21fac9e
- **Tests**: 60/60 adapter tests passing
- **Implementation**:
  - PoolingPolicy enum (SHARED_INSTANCE, ISOLATED_PROCESS, ISOLATED_WITH_RESOURCE_MANAGEMENT, FORCED_ISOLATION)
  - get_pooling_policy() and get_launch_arguments() added to LSPCapabilityAdapterContract
  - ClangdAdapter: --cache-path with session_id + workspace_root hash for isolation
  - TsServerAdapter: Empty list (future memory limit args)
  - DefaultAdapter: Empty list (conservative - no assumptions about unknown LSPs)

### TDD Cycle 2: Global Service Initialization (REQ-3)
- **Commits**: 4c35d68, 02ca672, b0a67e8
- **Tests**: 20/20 tests passing (12 factory + 8 DI)
- **Implementation**:
  - SerenaMCPFactory singleton accessors: get_session_registry(), get_session_bridge(), get_lsp_pool()
  - Thread-safe lazy initialization with RLock (not Lock - prevents deadlock with nested calls)
  - SerenaAgent DI params: session_registry, session_bridge, lsp_pool (all optional, default None)
  - Strangler Fig pattern: Old path when ALL DI params None, new path when ANY DI param provided

### TDD Cycle 3: GlobalLanguageServerPool (REQ-7)
- **Tests**: 24/24 pool tests passing
- **Implementation** (already existed):
  - acquire/release with reference counting
  - Multi-root language sharing (Rust, Python keyed by language only)
  - Single-root language isolation (TypeScript keyed by language + workspace_root)
  - Thread-safe locking with pool_lock
  - LSPTimeoutManager integration for idle reclamation
  - Reclaim callback support

## Test Evidence

```
T:test_lsp_capability_adapter_contract::18=PASS
T:test_lsp_capability_adapter_pooling::6=PASS
T:test_mcp_factory_initialization::12=PASS
T:test_serena_agent_di::8=PASS
T:test_global_lsp_pool::24=PASS
Total: 68/68 PASS
```

## Key Files Modified

- `src/serena/lsp_capability_adapter.py` - PoolingPolicy enum, contract methods
- `src/serena/mcp.py` - Singleton accessor methods
- `src/serena/agent.py` - DI params for Strangler Fig
- `src/serena/global_lsp_pool.py` - Pool implementation (pre-existing)
- `contracts/global_lsp_pool_contract.py` - Pool contract

## Next Phase

Phase 2: SessionRegistry and MCPSessionBridge implementation
- REQ-1: SessionRegistry with session_id -> project_path mapping
- REQ-4: MCPSessionBridge tool dispatching
- REQ-5: Idle timeout management via LSPTimeoutManager
