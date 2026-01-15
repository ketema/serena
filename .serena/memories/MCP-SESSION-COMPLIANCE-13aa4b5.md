# MCP Session Management Compliance

**Commit**: 13aa4b5e
**Date**: 2026-01-15
**Requirement**: REQ-SESSION-001

## Key Decisions

1. **Strict MCP Spec Adherence**: Chose Option A (follow spec strictly) over auto-recovery
   - Stale session ID → 404 Not Found (not auto-recovery)
   - Client responsibility to reinitialize per MCP spec

2. **Contract Traceability Chain**:
   ```
   MCP Spec 2025-03-26 (authority)
           ↓
   contracts/mcp_session_contract.py (PRE/POST/INV)
           ↓
   test/mocks/mcp_session_mock.py (contract-derived)
           ↓
   test/contracts/test_mcp_session_http_integration.py (verifies real)
   ```

3. **Response Codes** (per MCP spec):
   - 200: Valid session, continue
   - 400: Missing session ID (non-init request)
   - 404: Invalid/stale session ID (must reinitialize)

## Contract Clauses

### validate_session
- POST-1: Valid session → 200
- POST-2: Invalid/stale session → 404
- POST-3: Missing session (non-init) → 400
- INV-1: Only server-issued IDs valid
- INV-2: Stale sessions rejected
- INV-3: Fabricated sessions rejected

### create_session
- POST-1: InitializeRequest without ID → new session
- POST-2: Response contains Mcp-Session-Id header
- POST-3: Session ID cryptographically secure (UUID)
- POST-4: Session ID visible ASCII only
- POST-5: Response status 200
- POST-6: Response contains InitializeResult

## Theater Detection

**Question**: "Can mock behave differently from real and tests pass?"
**Answer**: NO - Mock derives behavior from contract PRE/POST/INV clauses

**Verification**: `verify_mock_matches_contract()` in mock module

## Files Created

- `contracts/mcp_session_contract.py` - CL12 behavioral contract
- `test/mocks/mcp_session_mock.py` - CL10 compliant mock
- `test/contracts/test_mcp_session_contract.py` - Contract tests (16 tests)
- `test/contracts/test_mcp_session_http_integration.py` - Integration tests (gated)
- `docs/requirements/REQ-SESSION-001-mcp-session-management.md` - Requirements manifest

## Run Integration Tests

Integration tests are gated. Run against live server:
```bash
pytest test/contracts/test_mcp_session_http_integration.py -m integration
```

Server must be running on localhost:9122.
