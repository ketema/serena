# Theater Test Detection Audit

## Test 1: test_set_session_context_session_found_returns_token

**Question**: Can implementation violate POST-6 and test still pass?
- Implementation returns None when session found → Test FAILS ✓
- Implementation returns string instead of Token → Test FAILS ✓
- Implementation returns Token correctly → Test PASSES ✓

**Exact values**: isinstance(result, Token) == True (exact type check)
**Observable effect**: Type check + Token cleanup capability verified
**Theater test**: NO - Implementation must return Token or test fails

## Test 2: test_set_session_context_session_not_found_returns_none

**Question**: Can implementation violate POST-7 and test still pass?
- Implementation returns Token when session not found → Test FAILS ✓
- Implementation returns None correctly → Test PASSES ✓
- Implementation sets ContextVar when should not → Caught by test 4 ✓

**Exact values**: result == None (exact None check)
**Observable effect**: None return verified
**Theater test**: NO - Implementation must return None or test fails

## Test 3: test_set_session_context_session_not_found_no_auto_registration

**Question**: Can implementation violate POST-8/INV-7 and test still pass?
- Implementation calls bind_session() with Path.cwd() → Test FAILS (call_count > 0) ✓
- Implementation calls bind_session() with any args → Test FAILS ✓
- Implementation returns None without registration → Test PASSES ✓

**Exact values**: bind_session.call_count == 0 (exact count)
**Observable effect**: Mock call tracking verifies no registration
**Theater test**: NO - Implementation must skip registration or test fails

**Critical behavior**: This test prevents the bug that caused HTTP mode to use server CWD instead of requiring explicit activate_project.

## Test 4: test_set_session_context_session_not_found_contextvar_unchanged

**Question**: Can implementation violate POST-7 (ContextVar unchanged) and test still pass?
- Implementation modifies ContextVar despite returning None → Test FAILS ✓
- Implementation leaves ContextVar unchanged → Test PASSES ✓

**Exact values**: get_current_session_id() == initial_value (exact match)
**Observable effect**: ContextVar state comparison before/after
**Theater test**: NO - Implementation must preserve ContextVar or test fails

## Summary

All 4 tests pass theater detection:
- ✓ All use exact values (isinstance check, None check, call_count == 0)
- ✓ All verify measurable effects (type, return value, mock calls, ContextVar state)
- ✓ All cite specific clause IDs (POST-6, POST-7, POST-8, INV-7)
- ✓ None can pass with wrong implementation

**Critical coverage**: Test 3 specifically addresses the HTTP mode bug (INV-7 violation) by verifying NO auto-registration occurs.
