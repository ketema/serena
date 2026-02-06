# CONTRACT AUTHORITY RECORD

**File**: contracts/mcp_session_bridge_contract.py
**Authority**: AUTHORITATIVE for MCP Session Bridge behavioral contracts
**Component**: MCPSessionBridgeContract

## CLAUSE REGISTRY

### PRECONDITIONS
- PRE-1: (on_transport_created) mcp_session_id is non-empty string
- PRE-2: (set_session_context) session_id exists in SessionRegistry OR is anonymous
- PRE-3: (get_current_session_id) May be called from any execution context
- PRE-4: (set_session_context) session_id is non-empty string

### POSTCONDITIONS
- POST-1: (on_transport_created) SessionRegistry.bind_session() called
- POST-2: (on_transport_closed) SessionRegistry.unbind_session() called
- POST-3: (set_session_context) ContextVar set, token returned for reset
- POST-4: (get_current_session_id) Returns session_id or None
- POST-5: (get_or_create_anonymous) Returns valid session_id, never None
- POST-6: (set_session_context) If session found in registry: ContextVar set, returns Token
- POST-7: (set_session_context) If session NOT found in registry: ContextVar unchanged, returns None
- POST-8: (set_session_context) NO auto-registration with Path.cwd() per INV-7 (HTTP mode fix)

### INVARIANTS
- INV-1: Every MCP transport session maps to exactly one Serena session
- INV-2: Session context is accessible in both async and sync execution contexts
- INV-3: Anonymous sessions are created on-demand when session_id unavailable
- INV-4: Anonymous sessions have TTL <= ANONYMOUS_SESSION_TTL_SECONDS
- INV-5: Session cleanup occurs on transport close or TTL expiration
- INV-6: ContextVar propagation survives thread pool dispatch
- INV-7: HTTP mode (transport_session_id present) → No auto-registration with Path.cwd(); require explicit activate_project call
- INV-8: STDIO mode (transport_session_id None) → CWD-based initialization acceptable since client process CWD matches project workspace

### ERRORS
- ERROR-1: (set_session_context) Empty session_id → ValueError
- ERROR-2: (anonymous creation) Creation fails → AnonymousSessionCreationError

## TARGET CLAUSES FOR THIS TEST SUITE

Per test-writer invocation arguments:
- INV-7: HTTP mode no auto-registration
- POST-6: Session found returns Token
- POST-7: Session not found returns None
- POST-8: No Path.cwd() auto-registration

## TESTABLE BEHAVIORS

### set_session_context() Method Behaviors

1. **Session Found in Registry** (POST-6):
   - Observable: Returns Token (not None)
   - Observable: ContextVar set (get_current_session_id() returns session_id)

2. **Session NOT Found in Registry** (POST-7):
   - Observable: Returns None
   - Observable: ContextVar unchanged (get_current_session_id() returns previous value or None)

3. **NO Auto-Registration** (POST-8, INV-7):
   - Observable: If session not found, Path.cwd() NOT called
   - Observable: SessionRegistry.bind_session() NOT called
   - Observable: Only returns None (caller must handle)

## CONSISTENCY CHECK (CL12-B)

Checking for contradictions:
- POST-6 (returns Token if found) vs POST-7 (returns None if not found) → CONSISTENT (mutually exclusive conditions)
- POST-8 (no auto-registration) vs INV-7 (HTTP mode requires explicit activation) → CONSISTENT (same requirement)
- No contradictions found

## COVERAGE REQUIREMENTS

Minimum test cases:
1. Session found → verify POST-6 (Token returned, ContextVar set)
2. Session not found → verify POST-7 (None returned, ContextVar unchanged)
3. Session not found → verify POST-8 (no auto-registration, no Path.cwd() call)
4. Integration: Verify INV-7 enforcement (HTTP mode behavior)
