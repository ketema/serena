# Contract Authority Record (CAR)

**Contract File**: contracts/transport_session_callback_contract.py
**Authority**: AUTHORITATIVE for Transport Session Callback Integration
**Generated**: 2026-02-05

## Extracted Clauses

### INVARIANTS
- INV-01: Transport MUST call on_session_created before first tool executes
- INV-02: Transport MUST call on_session_closed when connection terminates
- INV-03: Transport layer SHALL NOT directly access SessionRegistry
- INV-04: Transport layer SHALL NOT know about MCPSessionBridge internals
- INV-05: Session starts with workspace=None; activate_project required to bind

### PRECONDITIONS (set_session_callbacks)
- PRE-1: on_session_created is callable or None
- PRE-2: on_session_closed is callable or None

### POSTCONDITIONS (set_session_callbacks)
- POST-1: Subsequent session creations invoke on_session_created
- POST-2: Subsequent session closures invoke on_session_closed
- POST-3: Replaces any previously set callbacks
- **POST-4: If sessions already exist when on_session_created is set, on_session_created is invoked IMMEDIATELY for each existing session (retroactive registration to handle race condition)**

### ERRORS
- ERRORS-1: Callback exceptions propagate (not swallowed)
- ERRORS-2: Invalid session_id (empty string) → undefined behavior (caller responsibility)

## POST-4 Behavioral Requirements

**WHAT**: Retroactive callback invocation for existing sessions
**WHY**: Mitigate race condition where HTTP transport creates sessions before MCPServer lifespan wires callbacks
**OBSERVABLE**: Callback must be invoked synchronously during set_session_callbacks call for each existing session

**Test Categories**:
1. **Positive**: Existing sessions trigger retroactive callbacks
2. **Boundary**: Zero sessions, one session, multiple sessions
3. **Negative**: Callback exceptions during retroactive invocation
4. **Invariant**: Retroactive calls preserve INV-01 timing guarantees
