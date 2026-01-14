"""
Tool Dispatch Session Integration Contract - Real Provider Behavior Verification

Constitutional Reference: CL10 Mock Verification, CL12 Design by Contract
Domain: MCP tool dispatch session context integration
Version: 1.0

AUTHORITY: This contract is AUTHORITATIVE for verifying that SerenaMCPFactory.make_mcp_tool
actually restores session context during tool execution. This is the INTEGRATION contract
that complements the SESSION_CONTEXT_PROPAGATION contract (interface specification).

RELATIONSHIP TO OTHER CONTRACTS:
==========================================================================
| Contract                              | Purpose                         |
|---------------------------------------|--------------------------------|
| session_context_propagation_contract  | Interface specification (MOCK)  |
| tool_dispatch_session_integration     | Real behavior verification      |
==========================================================================

session_context_propagation_contract: Defines HOW wrap_tool_execution() SHOULD work
tool_dispatch_session_integration:    Verifies make_mcp_tool() ACTUALLY uses it

MOCK vs INTEGRATION (CL10 Requirement):
- Mock tests prove: Interface contract works as specified
- Integration tests prove: Real implementation uses the interface correctly
- We need BOTH: Mocks for fast iteration, integration for reality verification

PROBLEM STATEMENT (DISCONNECT MATRIX - INTEGRATION LEVEL):
==========================================================================
| ID | Integration Point           | EXPECTED                  | OBSERVED              | DELTA   |
|----|----------------------------|---------------------------|----------------------|---------|
| I1 | make_mcp_tool execute_fn   | Calls wrap_tool_execution | Calls tool.apply_ex  | BUG     |
|    |                            | before tool execution     | directly (no wrap)   |         |
| I2 | MCP tool invocation        | Session context available | Session context None  | BUG     |
|    |                            | during tool execution     | (ContextVar not set) |         |
| I3 | get_active_project() in    | Returns activated project | Raises "No active    | BUG     |
|    | tool                       |                           | session"             |         |
| I4 | HTTP mode tool sequence    | Session persists across   | Session lost between | BUG     |
|    |                            | tool calls                | calls                |         |
==========================================================================

ROOT CAUSE (from code analysis):
- SerenaMCPFactory.make_mcp_tool() creates execute_fn that calls tool.apply_ex() directly
- execute_fn does NOT read transport session ID
- execute_fn does NOT call wrap_tool_execution()
- Result: ContextVar never restored, session context unavailable

INTEGRATION TEST REQUIREMENTS:
These tests MUST use REAL components (not mocks):
- REAL SerenaMCPFactory
- REAL MCPTool instances
- REAL SessionRegistry
- REAL MCPSessionBridge
- REAL ContextVar state

GATING: Integration tests may be marked with @pytest.mark.integration
for conditional execution in CI when external dependencies unavailable.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from serena.mcp import SerenaMCPFactory
    from serena.session_registry import SessionRegistry


class ToolDispatchSessionIntegrationContract(ABC):
    """
    Contract for verifying SerenaMCPFactory.make_mcp_tool integration with session context.

    This contract specifies WHAT the real implementation MUST do, not the interface.
    Tests enforce this contract against REAL components, not mocks.
    """

    @abstractmethod
    def verify_execute_fn_restores_session_context(
        self,
        mcp_factory: "SerenaMCPFactory",
        session_registry: "SessionRegistry",
        session_id: str,
    ) -> bool:
        """
        Verify that execute_fn (created by make_mcp_tool) restores session context.

        PRE: mcp_factory is real SerenaMCPFactory instance (not mock)
        PRE: session_registry has session registered for session_id
        PRE: Transport session ID is set (simulating HTTP layer)

        POST: During tool execution, get_current_session() returns the session
        POST: After tool execution, get_current_session() returns None (cleaned up)

        INV (5-Point Checklist):
        1. State Invariance: SessionRegistry unchanged by verification
        2. Side Effect Prohibition: Only ContextVar modified (expected)
        3. Ordering Constraints: Must simulate real HTTP request flow
        4. Resource Invariants: No handles leaked
        5. Exception Safety: Cleanup on any failure

        ERRORS: Returns False if session context not available during execution

        VERIFICATION METHOD:
        1. Register session in SessionRegistry
        2. Set transport session ID (simulating HTTP layer)
        3. Create MCP tool via make_mcp_tool
        4. Invoke tool's execute_fn
        5. Capture get_current_session() result DURING execution
        6. Assert session context was available
        """
        ...

    @abstractmethod
    def verify_session_persists_across_tool_calls(
        self,
        mcp_factory: "SerenaMCPFactory",
        session_registry: "SessionRegistry",
        session_id: str,
    ) -> bool:
        """
        Verify session context available in subsequent tool calls (HTTP mode).

        PRE: mcp_factory is real SerenaMCPFactory instance
        PRE: First tool call (activate_project) completed successfully
        PRE: Same session_id used for subsequent tool calls

        POST: Second tool call has session context available
        POST: get_active_project() returns correct project in second tool

        INV (5-Point Checklist):
        1. State Invariance: Session remains in registry across calls
        2. Side Effect Prohibition: Only ContextVar modified per call
        3. Ordering Constraints: First tool sets up, second tool verifies
        4. Resource Invariants: No session leakage between calls
        5. Exception Safety: Both tools clean up properly

        ERRORS: Returns False if second tool cannot access session

        VERIFICATION METHOD:
        1. Simulate activate_project tool (binds session)
        2. Clear ContextVar (simulates new async context)
        3. Set transport session ID again (HTTP header)
        4. Invoke second tool via execute_fn
        5. Capture get_current_session() in second tool
        6. Assert session context was available
        """
        ...


# =============================================================================
# INTEGRATION TEST SPECIFICATION
# =============================================================================

INTEGRATION_TEST_SPECIFICATION = """
Integration Test Specification for Tool Dispatch Session Restoration

OBJECTIVE: Verify SerenaMCPFactory.make_mcp_tool creates tools that restore
session context during execution.

TEST ENVIRONMENT:
- REAL SerenaMCPFactory (from src/serena/mcp.py)
- REAL SessionRegistry (from src/serena/session_registry.py)
- REAL MCPSessionBridge (from src/serena/mcp_session_bridge.py)
- REAL mcp_transport_context ContextVar (from src/serena/mcp_transport_context.py)

TEST MARKERS:
- @pytest.mark.integration - Marks as integration test (can be gated)
- @pytest.mark.slow - If test requires significant setup time

GATING CONDITIONS:
- Run by default in local development
- Can be skipped in CI with: pytest -m "not integration"
- Must pass before merge to main branch

TEST CASES:

Test Case I1: execute_fn Restores Session Context
-------------------------------------------------
GIVEN: SerenaMCPFactory with registered tool
AND: Session registered in SessionRegistry
AND: Transport session ID set (simulating HTTP header)

WHEN: Tool's execute_fn is invoked

THEN: get_current_session() returns SessionContext DURING execution
AND: SessionContext.session_id matches transport session ID
AND: get_current_session() returns None AFTER execution (cleanup)

EXPECTED FAILURE (Current Implementation):
execute_fn calls tool.apply_ex() directly without wrapping.
Transport session ID is never read.
ContextVar never restored.
get_current_session() returns None during execution.


Test Case I2: Session Persists Across HTTP Tool Calls
-----------------------------------------------------
GIVEN: HTTP mode session tracking enabled
AND: activate_project tool bound session to session_id

WHEN: Subsequent tool invoked with same session_id

THEN: Second tool has session context available
AND: get_active_project() returns activated project
AND: No "No active session" error

EXPECTED FAILURE (Current Implementation):
ContextVar set during activate_project
Second tool runs in new async context
ContextVar is empty (not restored)
get_active_project() raises "No active session"


Test Case I3: STDIO Mode Session Persistence
--------------------------------------------
GIVEN: STDIO transport (single process)
AND: Synthetic session ID used

WHEN: Multiple tools invoked in same process

THEN: Session context available in all tool calls
AND: No ContextVar loss between calls

NOTE: May behave differently from HTTP due to same async context.
Test verifies behavior matches expectations.


Test Case I4: Error Handling During Session Restoration
------------------------------------------------------
GIVEN: Tool execution raises exception

WHEN: execute_fn catches and handles exception

THEN: Session context cleaned up despite error
AND: ContextVar reset to previous state
AND: No session leakage

This tests ERROR-5 compliance at integration level.
"""

# =============================================================================
# VERIFICATION EVIDENCE REQUIREMENTS
# =============================================================================

EVIDENCE_REQUIREMENTS = """
Evidence Required for Integration Test Pass:

1. EXECUTION EVIDENCE:
   - Actual tool invocation (not mock)
   - Real ContextVar state captured
   - Real SessionRegistry query results

2. OBSERVABLE EFFECTS:
   - get_current_session() return value DURING execution
   - get_active_project() return value (if applicable)
   - Exception messages (if failure case)

3. STATE TRANSITIONS:
   - ContextVar BEFORE tool execution: None
   - ContextVar DURING tool execution: SessionContext
   - ContextVar AFTER tool execution: None (cleanup)

4. FAILURE EVIDENCE (for RED phase):
   - Current implementation: ContextVar DURING = None
   - Error: "No active session" from get_active_project()
   - Root cause: execute_fn doesn't call wrap_tool_execution

5. SUCCESS EVIDENCE (for GREEN phase):
   - Fixed implementation: ContextVar DURING = SessionContext
   - get_active_project() returns Project instance
   - Cleanup verified: ContextVar AFTER = None
"""
