# Option C: Full Sync Refactor Plan

**Approved**: 2026-01-11
**AI Panel Conversation**: 2e0565e4-14ec-4ef3-87e0-e7bdbdc4f426
**Branch**: feature/multi-project-support

## Constitutional Workflow

### Phase 1: Contract Updates (CL10)
Update contracts to reflect sync interfaces:

1. **session_registry_contract.py**:
   - Remove async references
   - `threading.Lock` instead of `asyncio.Lock`
   - All methods sync signatures
   - Keep ContextVar (works in both contexts)

2. **lsp_timeout_contract.py**:
   - Remove async references
   - `threading.Thread` for background monitoring
   - `Callable[[str], None]` for reclaim_callback (sync)
   - `time.sleep` for check intervals

3. **contextvar_session_contract.py**:
   - No changes needed (ContextVar is sync-compatible)

4. **path_validation_contract.py**:
   - No changes needed (already sync)

### Phase 2: Adversarial Test Refactor (CL6 TDD)
↪ test-writer sub-agent | 🚫 impl | ✓ contracts + existing tests

- Refactor existing 36 async tests to sync
- Remove `async def`, `await`, `pytest.mark.asyncio`
- Update mock patterns for sync callbacks
- Maintain 5-point error message quality

### Phase 3: Adversarial Implementation Refactor (CL6 TDD)
↪ coder sub-agent | 🚫 test source | ✓ error messages only

- Refactor SessionRegistry: asyncio.Lock → threading.Lock
- Refactor LSPTimeoutManager: asyncio.Task → threading.Thread
- Make all methods sync
- Pass all tests

### Phase 4: Integration (After GREEN)
Wire refactored components into:
- Project.is_path_in_project
- SerenaAgent._activate_project / shutdown
- LanguageServerManager

## Key Contract Changes

### SessionRegistry Contract (BEFORE → AFTER)

```python
# BEFORE (async)
async def bind_session(self, session_id: str, ...) -> SessionContext:
    async with self._lock:  # asyncio.Lock
        ...

# AFTER (sync)
def bind_session(self, session_id: str, ...) -> SessionContext:
    with self._lock:  # threading.Lock
        ...
```

### LSPTimeoutManager Contract (BEFORE → AFTER)

```python
# BEFORE (async)
_monitoring_task: asyncio.Task | None
_reclaim_callback: Callable[[str], Awaitable[None]] | None
async def check_and_reclaim(self) -> list[str]: ...
async def start_monitoring(self) -> None: ...

# AFTER (sync)
_monitoring_thread: threading.Thread | None
_reclaim_callback: Callable[[str], None] | None
def check_and_reclaim(self) -> list[str]: ...
def start_monitoring(self) -> None: ...
```

## Evidence Requirements

- C:hash for each contract update
- T:module::test=FAIL (RED phase)
- T:module::test=PASS (GREEN phase)
- AI Panel conversation for contract validation
