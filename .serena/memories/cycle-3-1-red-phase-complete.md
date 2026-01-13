# Cycle 3.1 RED Phase Complete

**Date**: 2026-01-12
**Branch**: feature/multi-project-support
**Phase**: M4.2 RED - COMPLETE

## Test Results (2 FAIL, 2 PASS)

### FAILED Tests (Target for GREEN phase)

1. **test_mcp_factory_binds_session_on_agent_creation**
   - WHY: REQ-4b requires MCP factory to bind session via activate_session_project()
   - EXPECTED: Session bound to registry after MCP activation
   - ACTUAL: No session binding found

2. **test_mcp_factory_activate_session_project_method_exists**
   - WHY: REQ-4b requires MCP factory to have method for session-aware activation
   - EXPECTED: activate_project_for_mcp_session() or equivalent exists
   - ACTUAL: Method not found on SerenaMCPFactory

### PASSED Tests (Already Working)

1. `test_mcp_session_registry_accessible_via_factory` - Phase 2 work
2. `test_mcp_without_project_skips_session_binding` - Correct no-project behavior

## Error Messages for GREEN Phase Coder

```
=== FAILURE: test_mcp_factory_binds_session_on_agent_creation ===
WHAT FAILED: SessionRegistry.get_session(session_id) returned None
WHY: REQ-4b requires MCP factory to bind session via activate_session_project()
BEHAVIORAL GUIDANCE:
  - SerenaMCPFactory MUST call agent.activate_session_project() during startup
  - Session binding MUST occur after agent creation with session context
  - Registry binding MUST be observable via get_session(session_id)

=== FAILURE: test_mcp_factory_activate_session_project_method_exists ===
WHAT FAILED: No session activation method found on SerenaMCPFactory
BEHAVIORAL GUIDANCE:
  - Add method to SerenaMCPFactory that:
    1. Sets agent._current_session_id from MCP client session
    2. Calls agent.activate_session_project(project_name)
    3. Handles PRE violation (no session) gracefully
```

## Next Step

Proceed to Cycle 3.2 GREEN phase - implement MCP Switch in src/serena/mcp.py
