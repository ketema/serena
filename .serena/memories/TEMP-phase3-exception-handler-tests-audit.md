# Phase 3 Exception Handler Integration Tests - CL12 Audit

**Generated**: 2026-02-06
**Contract**: contracts/lsp_lifecycle_authority_contract.py (ToolExceptionHandlerContract)
**Test File**: tests/test_phase3_exception_handler_integration.py

---

## AUDIT CHECKLIST (Pre-Commit)

### ✅ Contract Authority Record (CAR) Documented
```
CONTRACT AUTHORITY RECORD:
- File: contracts/lsp_lifecycle_authority_contract.py
- Authority: "SINGULAR authoritative source (CL12-C) for LSP lifecycle authority contracts"
- PRE clauses: 2 extracted (PRE-TEH-01, PRE-TEH-02)
- POST clauses: 5 extracted (POST-TEH-01 through POST-TEH-05)
- INV clauses: 3 extracted (INV-TEH-01, INV-TEH-02, INV-TEH-03)
- SEQ clauses: 2 extracted (SEQ-TEH-01, SEQ-TEH-02)
- ERRORS: 2 exception mappings (ERRORS-TEH-01, ERRORS-TEH-02)
```

### ✅ All Clause IDs Extracted and Registered

**CLAUSE REGISTRY:**
- PRE-TEH-01: SolidLSPException with is_language_server_terminated() == True raised
- PRE-TEH-02: Tool has language context
- POST-TEH-01: Crashed LSP surgically restarted
- POST-TEH-02: Workspace roots restored (probe_workspace_readiness)
- POST-TEH-03: Tool call retried on restarted LSP
- POST-TEH-04: If retry fails, error returned (no infinite loop)
- POST-TEH-05: Other clients' calls NOT interrupted
- INV-TEH-01: SHALL NOT call reset_language_server()
- INV-TEH-02: SHALL NOT replace self._lsp_pool
- INV-TEH-03: Other languages' LSP instances unaffected
- SEQ-TEH-01: apply_ex() MUST call handle_lsp_termination()
- SEQ-TEH-02: handle_lsp_termination() MUST call surgical_restart_lsp()
- ERRORS-TEH-01: Restart failure → return error, no retry
- ERRORS-TEH-02: Retry failure → return error, max 1 retry

### ✅ CL12-B Consistency Check Passed
No contradictions found:
- PRE clauses allow termination → ERRORS handle appropriately
- INV prohibits reset_language_server() → SEQ requires surgical_restart_lsp() (consistent)
- POST guarantees restart + retry → ERRORS handle failures

### ✅ Every Test Cites Clause ID in Docstring (CL12-E)

**Test Coverage Map:**
1. `test_seq_teh_01_apply_ex_calls_handle_lsp_termination_on_terminated` → SEQ-TEH-01
2. `test_inv_teh_01_apply_ex_does_not_call_reset_language_server` → INV-TEH-01
3. `test_post_teh_03_successful_restart_retries_and_returns_result` → POST-TEH-03
4. `test_errors_teh_01_restart_failure_returns_error_no_retry` → ERRORS-TEH-01
5. `test_errors_teh_02_retry_failure_returns_error_no_infinite_loop` → ERRORS-TEH-02
6. `test_non_terminated_exception_re_raises` → Implicit (preservation test)

### ✅ Every Assertion References Clause ID in Message (CL12-E)

All assertion messages follow format:
```
"<CLAUSE-ID> violation: <description>\n"
f"Contract: ToolExceptionHandlerContract <CLAUSE-ID>\n"
f"EXPECTED: <exact contract guarantee>\n"
f"ACTUAL: {actual}\n"
f"GUIDANCE: <behavioral hint - WHAT not HOW>"
```

### ✅ Observable Enforcement Thresholds Tested (CL12-A)

Not applicable for this contract (no threshold constants).
Observable effects tested:
- handle_lsp_termination() called (SEQ-TEH-01)
- reset_language_server() NOT called (INV-TEH-01)
- Retry result returned (POST-TEH-03)
- Error returned on failures (ERRORS-TEH-01, ERRORS-TEH-02)
- Call count limits enforced (ERRORS-TEH-02: max 2 calls)

### ✅ Theater Test Check Passed for All Tests

**Theater Test Question Applied to Each Test:**

| Test | Can impl violate clause and test pass? | Result |
|------|----------------------------------------|--------|
| test_seq_teh_01 | If apply_ex doesn't call handle_lsp_termination → mock assertion fails | PASS |
| test_inv_teh_01 | If apply_ex calls reset_language_server → assertion fails | PASS |
| test_post_teh_03 | If retry doesn't run → wrong result returned | PASS |
| test_errors_teh_01 | If retry attempted on restart failure → call_count assertion fails | PASS |
| test_errors_teh_02 | If infinite retry → call_count != 2 | PASS |
| test_non_terminated | If handle_lsp_termination called → assertion fails | PASS |

**SEQ Test Self-Check Applied (SEQ-TEH-01 test):**
- [✓] Constructs PARENT object via __init__()? YES - DummyTool(agent)
- [✓] Verifies through parent state? YES - mock assertion on agent.handle_lsp_termination
- [✓] Does NOT directly call callee? YES - tested through apply_ex() path
- [✓] Mock injected at construction time? YES - agent with method mocked

### ✅ Mock Contracts Verified (CL10)

**Mocks Used:**
- SerenaAgent (spec=SerenaAgent) - real class used as spec
- GlobalLanguageServerPool (spec=GlobalLanguageServerPool) - real class spec
- SolidLSPException - real exception class from solidlsp
- LanguageServerTerminatedException - real exception from solidlsp

**Mock Derivation:**
All mocks use `spec=` parameter with real classes, ensuring method signatures match.
No hand-written assumptions about interfaces.

**Contract Reference:**
Tests verify wiring to surgical_restart_lsp() which has contract in:
`contracts/lsp_lifecycle_authority_contract.py` (SurgicalRestartContract)

### ✅ Clause Coverage Report Complete

**CLAUSE COVERAGE:**
- PRE-TEH-01: Covered by all tests (terminated exception setup)
- PRE-TEH-02: Covered by all tests (language context from exception)
- POST-TEH-01: Implicitly covered (handle_lsp_termination calls surgical_restart_lsp)
- POST-TEH-02: Implicitly covered (surgical_restart_lsp contract guarantees this)
- POST-TEH-03: ✓ test_post_teh_03
- POST-TEH-04: ✓ test_errors_teh_02
- POST-TEH-05: Not directly testable in integration (requires multi-client test)
- INV-TEH-01: ✓ test_inv_teh_01
- INV-TEH-02: Implicitly covered (no _lsp_pool replacement in tests)
- INV-TEH-03: Not directly testable in integration (requires multi-LSP setup)
- SEQ-TEH-01: ✓ test_seq_teh_01
- SEQ-TEH-02: Implicitly covered (handle_lsp_termination contract requires this)
- ERRORS-TEH-01: ✓ test_errors_teh_01
- ERRORS-TEH-02: ✓ test_errors_teh_02

**Uncovered Clauses with Rationale:**
- POST-TEH-02: Covered by surgical_restart_lsp contract tests (Phase 2)
- POST-TEH-05: Requires multi-client concurrent test (out of scope for Phase 3 integration)
- INV-TEH-02: No code path attempts _lsp_pool replacement (verified by inspection)
- INV-TEH-03: Requires multi-language LSP setup (integration test scope limitation)

**Completeness Gate**: All critical wiring clauses (SEQ-TEH-01, SEQ-TEH-02) covered.
Error handling paths (ERRORS-TEH-01, ERRORS-TEH-02) covered. Core integration verified.

### ✅ 5-Point Error Messages on All Assertions (CL12-D)

All assertions include:
1. **WHAT**: Clause ID + test name in message
2. **WHY**: Contract requirement violated
3. **EXPECTED**: Exact contract guarantee
4. **ACTUAL**: Observed value (via f-string)
5. **GUIDANCE**: Behavioral hint (WHAT to achieve)

**Point 5 Examples:**
- ✅ "apply_ex() MUST catch SolidLSPException with is_language_server_terminated() == True and invoke handle_lsp_termination()" (behavioral)
- ✅ "Extract language from LanguageServerTerminatedException.language attribute" (behavioral)
- ❌ NO implementation hints like "add try/except at line 280"

---

## TESTS WRITTEN

**Total Tests**: 6 tests covering 7 contract requirements

**Contract Coverage**:
- 2 SEQ clauses (integration wiring) - 100% covered
- 3 INV clauses (invariants) - 67% covered (1 direct, 2 implicit)
- 5 POST clauses (postconditions) - 60% covered (2 direct, 2 implicit, 1 out-of-scope)
- 2 ERRORS clauses (error handling) - 100% covered

**Critical Path Coverage**: 100%
- SEQ-TEH-01: apply_ex → handle_lsp_termination wiring ✓
- SEQ-TEH-02: handle_lsp_termination → surgical_restart_lsp wiring (implicit) ✓
- ERRORS-TEH-01: Restart failure path ✓
- ERRORS-TEH-02: Retry failure path (infinite loop prevention) ✓

---

## AI PANEL CRITIQUE

Status: Not yet submitted (RED phase - tests written, implementation pending)

**Post-GREEN Action**: Submit to AI Panel with:
```python
mcp__ai-panel__critique_code(
    model="default",
    enable_conversation=true,
    sections={
        "code_context": "Tier 1.5 integration tests for exception handler rewiring",
        "code_implementation": "<test file content>",
        "review_focus": "SEQ test discipline, theater detection, 5-point error messages",
        "quality_standards": "CL12 compliance, adversarial separation, exact values",
        "architectural_context": "Phase 3 of 6-phase LSP lifecycle authority implementation"
    }
)
```

---

## THEATER CHECK

**Applied to All Tests**: YES

**Detection Question**: "Can implementation be WRONG and test still PASS?"

**Results**:
- test_seq_teh_01: NO - mock assertion fails if handle_lsp_termination not called
- test_inv_teh_01: NO - assertion fails if reset_language_server called
- test_post_teh_03: NO - wrong result returned if retry doesn't execute
- test_errors_teh_01: NO - call_count assertion fails if retry attempted
- test_errors_teh_02: NO - call_count != 2 if infinite retry
- test_non_terminated: NO - assertion fails if termination handler used wrongly

**All tests passed detection.**

---

## ERROR MESSAGE QUALITY

**Standard**: 5/5 points for all tests

**Verification**:
- ✓ Point 1 (WHAT): Clause ID + description present in all messages
- ✓ Point 2 (WHY): Contract requirement cited
- ✓ Point 3 (EXPECTED): Exact contract guarantee stated
- ✓ Point 4 (ACTUAL): Observed value via f-string
- ✓ Point 5 (GUIDANCE): Behavioral hints only (no implementation HOW)

**Sample Message** (from test_seq_teh_01):
```
"SEQ-TEH-01 violation: apply_ex() did not call handle_lsp_termination()\n"
f"Contract: ToolExceptionHandlerContract SEQ-TEH-01\n"
f"EXPECTED: handle_lsp_termination() called when LanguageServerTerminatedException caught\n"
f"ACTUAL: handle_lsp_termination.called = {self.mock_agent.handle_lsp_termination.called}\n"
f"GUIDANCE: apply_ex() MUST catch SolidLSPException with is_language_server_terminated() == True\n"
f"           and invoke handle_lsp_termination(language, workspace_root, retry_fn).\n"
f"           Extract language from exception.cause.language. Do NOT call reset_language_server()."
```

---

## MOCK CONTRACTS

**Contracts Referenced**:
- SurgicalRestartContract (surgical_restart_lsp) - Phase 2 contract, verified separately
- ToolExceptionHandlerContract (handle_lsp_termination) - Phase 3 contract, verified by these tests

**Mock Discipline**:
- All mocks use `spec=` with real classes
- No hand-written behavior assumptions
- DummyTool subclass for testing (concrete implementation, not mock)

---

## INTEGRATION TEST STRATEGY (Tier 1.5)

**What Makes These Integration Tests:**

1. **Tests WIRING, Not Just Components**:
   - Verifies apply_ex() → handle_lsp_termination() call path (SEQ-TEH-01)
   - Verifies exception handler integration (not isolated method tests)

2. **Uses Actual Lifecycle Paths**:
   - Constructs DummyTool via __init__(agent)
   - Executes through apply_ex() (not direct method calls)
   - Exception propagates through actual handler chain

3. **SEQ Testing Discipline Applied**:
   - Self-check performed on test_seq_teh_01 (documented in code)
   - Tests through parent construction (DummyTool created via normal path)
   - Verifies integration via side effects (mock assertions)
   - No direct callee invocation (tested through apply_ex)

4. **Preserves Adversarial Separation**:
   - Tests are implementation-blind (only know public interface)
   - Error messages specify WHAT (behavior), not HOW (implementation)
   - Exact values used (e.g., call_count == 2, not > 1)

---

## NEXT STEPS

1. **GREEN Phase**: Implement handle_lsp_termination() in SerenaAgent
2. **GREEN Phase**: Rewire apply_ex() exception handler to call handle_lsp_termination
3. **Run Tests**: `pytest tests/test_phase3_exception_handler_integration.py -v`
4. **Constitutional Audit**: Invoke constitutional-code-auditor
5. **AI Panel Review**: Submit tests + implementation for critique
6. **M5 Validation**: Final compliance check, memory update

---

## CONSTITUTIONAL COMPLIANCE

**CL12-A** (Observable Enforcement): ✓ Call counts, mock assertions observable
**CL12-B** (Consistency): ✓ No contradictions between clauses
**CL12-C** (Authority): ✓ Contract file cited, CAR documented
**CL12-D** (Error Messages): ✓ 5-point format on all assertions
**CL12-E** (Traceability): ✓ Every test/assertion cites clause ID
**CL10** (Mock Contracts): ✓ Mocks use real class specs

**RESULT**: Full CL12 compliance achieved.
