"""
Tool Dispatch Session Integration Tests - Adversarial TDD RED Phase

Contract: contracts/tool_dispatch_session_integration_contract.py
Version: 1.0
Constitutional Reference: CL10 (Mock Verification), CL12 (Design by Contract)

INTEGRATION vs MOCK:
- This test suite verifies REAL SerenaMCPFactory.make_mcp_tool behavior
- Uses inspection and behavioral verification (not mocks)
- Complements session_context_propagation_contract (mock-level interface tests)
- Marked @pytest.mark.integration for gating when needed

CONTRACT AUTHORITY RECORD:
- File: contracts/tool_dispatch_session_integration_contract.py
- Authority: "AUTHORITATIVE for verifying SerenaMCPFactory.make_mcp_tool session restoration"
- PRE clauses: 8 extracted
- POST clauses: 6 extracted
- INV clauses: 10 extracted (5-point checklist × 2 methods)
- ERRORS: 2 error mappings

EXPECTED FAILURES (RED Phase):
- Test I1: execute_fn source code does NOT call run_with_session_context
- Test I2: execute_fn source code does NOT read transport_session_id
- Test I3: execute_fn calls tool.apply_ex directly (no wrapping)

These tests MUST fail against current implementation where execute_fn
calls tool.apply_ex() directly without run_with_session_context().
"""

import inspect
from typing import Any
from unittest.mock import MagicMock

import pytest

from serena.mcp import SerenaMCPFactory
from serena.tools.tools_base import Tool


@pytest.mark.integration
class TestToolDispatchSessionIntegration:
    """
    Integration tests for SerenaMCPFactory.make_mcp_tool session context restoration.

    CONTRACT TRACEABILITY:
    - Contract: ToolDispatchSessionIntegrationContract
    - Category: Integration (code inspection + behavioral)
    - Adversarial: Implementation-blind (verifies structure via inspection)

    NOTE: These tests use source code inspection to verify contract compliance.
    This is acceptable for integration tests because:
    1. Contract specifies WHAT execute_fn must do (call run_with_session_context)
    2. Inspection verifies structural requirements
    3. Observable behavior (session restoration) follows from structure
    """

    @pytest.fixture
    def mcp_factory(self, tmp_path):
        """Create real SerenaMCPFactory with temporary project."""
        # Create minimal project directory
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create factory with project
        factory = SerenaMCPFactory(project=str(project_dir))
        return factory

    @pytest.fixture
    def minimal_tool(self):
        """
        Create minimal tool for testing make_mcp_tool.

        This tool has minimal implementation to avoid agent dependencies.
        """

        class MinimalTool(Tool):
            """Minimal tool for structural testing."""

            def __init__(self):
                # Mock agent with minimal interface
                mock_agent = MagicMock()
                mock_agent.get_context.return_value = MagicMock(
                    tool_description_overrides={}
                )
                super().__init__(agent=mock_agent)

            def get_name(self) -> str:
                return "minimal_tool"

            def can_edit(self) -> bool:
                return False

            def apply(self) -> dict[str, Any]:
                """Minimal apply implementation."""
                return {"result": "executed"}

        return MinimalTool()

    def test_execute_fn_calls_run_with_session_context(
        self,
        mcp_factory: SerenaMCPFactory,
        minimal_tool: Tool,
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolDispatchSessionIntegrationContract.verify_execute_fn_restores_session_context
        - Enforces: POST-1 (execute_fn MUST call run_with_session_context)
        - Category: integration
        - Adversarial: Implementation-blind

        Verify execute_fn source code calls run_with_session_context.

        CURRENT IMPLEMENTATION BUG (Integration Level I1):
        execute_fn is defined as:
            def execute_fn(**kwargs):
                return tool.apply_ex(log_call=True, catch_exceptions=True, **kwargs)

        This calls tool.apply_ex directly WITHOUT wrapping.
        Result: Session context never restored.

        This test MUST FAIL in RED phase.
        """
        # ARRANGE: Create MCP tool wrapper
        mcp_tool_wrapper = mcp_factory.make_mcp_tool(minimal_tool)
        execute_fn = mcp_tool_wrapper.fn

        # ACT: Inspect execute_fn source code
        execute_fn_source = inspect.getsource(execute_fn)

        # ASSERT: Verify execute_fn calls run_with_session_context
        assert "run_with_session_context" in execute_fn_source, (
            f"POST-1 violation: execute_fn does NOT call run_with_session_context\n"
            f"Contract: ToolDispatchSessionIntegrationContract (Integration I1) POST-1\n"
            f"EXPECTED: execute_fn source contains 'run_with_session_context' call\n"
            f"ACTUAL: execute_fn source = {execute_fn_source}\n"
            f"GUIDANCE: execute_fn MUST call MCPSessionBridge.run_with_session_context() to restore session context. "
            f"Current implementation calls tool.apply_ex() directly. "
            f"Expected pattern: bridge.run_with_session_context(session_id, lambda: tool.apply_ex(...)). "
            f"Observable requirement: Source code MUST contain 'run_with_session_context' string."
        )

    def test_execute_fn_reads_transport_session_id(
        self,
        mcp_factory: SerenaMCPFactory,
        minimal_tool: Tool,
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolDispatchSessionIntegrationContract.verify_execute_fn_restores_session_context
        - Enforces: PRE-3, POST-1 (execute_fn MUST read transport session ID)
        - Category: integration
        - Adversarial: Implementation-blind

        Verify execute_fn reads transport session ID from context.

        CURRENT IMPLEMENTATION BUG (Integration Level I2):
        execute_fn does NOT call get_transport_session_id().
        Transport session ID from HTTP layer is never read.
        Result: No session ID to pass to run_with_session_context.

        This test MUST FAIL in RED phase.
        """
        # ARRANGE: Create MCP tool wrapper
        mcp_tool_wrapper = mcp_factory.make_mcp_tool(minimal_tool)
        execute_fn = mcp_tool_wrapper.fn

        # ACT: Inspect execute_fn source code
        execute_fn_source = inspect.getsource(execute_fn)

        # ASSERT: Verify execute_fn reads transport session ID
        assert "get_transport_session_id" in execute_fn_source or "mcp_transport" in execute_fn_source, (
            f"PRE-3/POST-1 violation: execute_fn does NOT read transport session ID\n"
            f"Contract: ToolDispatchSessionIntegrationContract (Integration I2) PRE-3, POST-1\n"
            f"EXPECTED: execute_fn source contains 'get_transport_session_id' or 'mcp_transport' reference\n"
            f"ACTUAL: execute_fn source = {execute_fn_source}\n"
            f"GUIDANCE: execute_fn MUST read transport session ID before calling run_with_session_context. "
            f"Transport session ID is set by HTTP layer via set_transport_session_id(). "
            f"Expected pattern: session_id = get_transport_session_id(); run_with_session_context(session_id, ...). "
            f"Observable requirement: Source code MUST reference transport session ID."
        )

    def test_execute_fn_structure_includes_session_restoration(
        self,
        mcp_factory: SerenaMCPFactory,
        minimal_tool: Tool,
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolDispatchSessionIntegrationContract.verify_execute_fn_restores_session_context
        - Enforces: POST-1, POST-2, INV-5 (complete session restoration flow)
        - Category: integration
        - Adversarial: Implementation-blind

        Verify execute_fn has complete session restoration structure.

        CURRENT IMPLEMENTATION BUG (Integration Level I3):
        execute_fn returns tool.apply_ex() directly.
        No session restoration code at all.

        Expected structure:
        ```python
        def execute_fn(**kwargs):
            session_id = get_transport_session_id()
            if session_id:
                return run_with_session_context(session_id, lambda: tool.apply_ex(..., **kwargs))
            else:
                return tool.apply_ex(..., **kwargs)  # STDIO fallback
        ```

        This test MUST FAIL in RED phase.
        """
        # ARRANGE: Create MCP tool wrapper
        mcp_tool_wrapper = mcp_factory.make_mcp_tool(minimal_tool)
        execute_fn = mcp_tool_wrapper.fn

        # ACT: Inspect execute_fn source code
        execute_fn_source = inspect.getsource(execute_fn)

        # ASSERT: Verify execute_fn has session restoration structure
        has_transport_read = "get_transport_session_id" in execute_fn_source or "mcp_transport" in execute_fn_source
        has_wrap_call = "run_with_session_context" in execute_fn_source
        has_conditional = "if" in execute_fn_source  # Session ID conditional

        complete_structure = has_transport_read and has_wrap_call and has_conditional

        assert complete_structure, (
            f"POST-1/POST-2/INV-5 violation: execute_fn missing session restoration structure\n"
            f"Contract: ToolDispatchSessionIntegrationContract (Integration I3) POST-1, POST-2, INV-5\n"
            f"EXPECTED: execute_fn contains all elements:\n"
            f"  1. Read transport session ID: {has_transport_read}\n"
            f"  2. Call run_with_session_context: {has_wrap_call}\n"
            f"  3. Conditional for session ID: {has_conditional}\n"
            f"ACTUAL: execute_fn source = {execute_fn_source}\n"
            f"GUIDANCE: execute_fn MUST implement complete session restoration flow. "
            f"Required elements: (1) Read transport session ID, (2) Call run_with_session_context if present, "
            f"(3) Fallback to direct call for STDIO mode. "
            f"Observable requirement: All three structural elements must be present in source code."
        )


# =============================================================================
# BEHAVIORAL INTEGRATION TESTS (Cannot Be Faked)
# =============================================================================


@pytest.mark.integration
class TestToolDispatchSessionBehavioral:
    """
    BEHAVIORAL integration tests - verify ACTUAL session restoration during execution.

    These tests complement the structural tests (I1, I2, I3) by verifying
    that session context is ACTUALLY restored during tool execution.

    THEATER TEST PREVENTION:
    - Structural tests verify string presence (can be faked with comments)
    - Behavioral tests verify runtime state (CANNOT be faked)
    - Both are needed: structural for RED phase, behavioral for GREEN validation

    CONTRACT TRACEABILITY:
    - Contract: ToolDispatchSessionIntegrationContract
    - Enforces: POST-1, POST-2 (behavioral verification)
    - Category: integration (behavioral)
    - Adversarial: Implementation-blind
    """

    @pytest.fixture
    def session_registry(self):
        """Create real SessionRegistry."""
        from serena.session_registry import SessionRegistry
        return SessionRegistry()

    @pytest.fixture
    def mcp_session_bridge(self, session_registry):
        """Create real MCPSessionBridge."""
        from serena.mcp_session_bridge import MCPSessionBridge
        return MCPSessionBridge(session_registry=session_registry)

    @pytest.fixture
    def workspace_root(self, tmp_path):
        """Create temporary workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace

    @pytest.fixture(autouse=True)
    def _clear_contexts(self):
        """Clear all context vars before and after each test."""
        from serena.mcp_transport_context import reset_transport_session_id, set_transport_session_id
        from serena.session_context import set_current_session

        # Clear before
        set_current_session(None)
        token = set_transport_session_id(None)

        yield

        # Clear after
        set_current_session(None)
        reset_transport_session_id(token)

    def test_session_context_restored_during_tool_execution(
        self,
        session_registry,
        mcp_session_bridge,
        workspace_root,
        tmp_path,
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolDispatchSessionIntegrationContract.verify_execute_fn_restores_session_context
        - Enforces: POST-1, POST-2 (session context available DURING execution)
        - Category: integration (behavioral)
        - Adversarial: Implementation-blind

        BEHAVIORAL verification that session context is ACTUALLY restored.

        This test CANNOT be faked:
        - Captures get_current_session() DURING tool execution
        - Verifies actual SessionContext instance (not just strings)
        - Verifies exact session_id match

        EXPECTED FAILURE (Current Implementation):
        execute_fn does NOT call run_with_session_context.
        get_current_session() returns None during tool execution.
        captured_session will be None.

        This is the ULTIMATE integration test - proves behavioral correctness.
        """
        from typing import Any
        from unittest.mock import MagicMock

        from serena.mcp import SerenaMCPFactory
        from serena.mcp_transport_context import set_transport_session_id
        from serena.session_context import get_current_session
        from serena.tools.tools_base import Tool

        # ARRANGE: Create session and set transport context
        session_id = "behavioral-test-session-123"
        session = session_registry.bind_session(session_id, workspace_root, source="http")

        # Set transport session ID (simulates HTTP layer setting it)
        set_transport_session_id(session_id)

        # Create minimal tool that captures session during execution
        captured_session = None
        captured_session_id = None

        class SessionCaptureTool(Tool):
            """Tool that captures session context during apply()."""

            def __init__(self, session_bridge):
                mock_agent = MagicMock()
                mock_agent.get_context.return_value = MagicMock(
                    tool_description_overrides={}
                )
                # Wire session bridge for HTTP mode session restoration
                mock_agent._session_bridge = session_bridge
                # Make issue_task execute synchronously
                def execute_task(task, name=None):
                    """Execute task synchronously and return result wrapped in mock future."""
                    result = task()
                    mock_future = MagicMock()
                    mock_future.result.return_value = result
                    return mock_future
                mock_agent.issue_task = execute_task
                super().__init__(agent=mock_agent)

            def get_name(self) -> str:
                return "session_capture_tool"

            def can_edit(self) -> bool:
                return False

            def apply(self) -> dict[str, Any]:
                """Capture session context DURING execution."""
                nonlocal captured_session, captured_session_id
                captured_session = get_current_session()
                if captured_session:
                    captured_session_id = captured_session.session_id
                return {"captured": True}

        # Create factory and tool
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        factory = SerenaMCPFactory(project=str(project_dir))
        tool = SessionCaptureTool(mcp_session_bridge)

        # ACT: Create MCP tool and invoke execute_fn
        mcp_tool_wrapper = factory.make_mcp_tool(tool)
        execute_fn = mcp_tool_wrapper.fn

        # Invoke the tool (this should restore session context internally)
        result = execute_fn()

        # ASSERT: BEHAVIORAL verification - session was available DURING execution
        assert captured_session is not None, (
            "POST-1/POST-2 BEHAVIORAL violation: Session context NOT restored during tool execution\n"
            "Contract: ToolDispatchSessionIntegrationContract (Behavioral) POST-1, POST-2\n"
            "EXPECTED: get_current_session() returns SessionContext DURING tool.apply()\n"
            "ACTUAL: get_current_session() returned None during execution\n"
            "GUIDANCE: execute_fn MUST restore session context BEFORE calling tool.apply_ex(). "
            "Use run_with_session_context(session_id, lambda: tool.apply_ex(...)). "
            "Observable requirement: get_current_session() returns non-None SessionContext "
            "when called from within tool's apply() method."
        )

        assert captured_session_id == session_id, (
            f"POST-2 BEHAVIORAL violation: Wrong session restored during tool execution\n"
            f"Contract: ToolDispatchSessionIntegrationContract (Behavioral) POST-2\n"
            f"EXPECTED: session_id = '{session_id}'\n"
            f"ACTUAL: session_id = '{captured_session_id}'\n"
            f"GUIDANCE: The SessionContext restored during tool execution MUST match the "
            f"transport session ID set by HTTP layer. Observable requirement: "
            f"captured_session.session_id == transport_session_id exactly."
        )

    def test_session_context_cleaned_up_after_tool_execution(
        self,
        session_registry,
        mcp_session_bridge,
        workspace_root,
        tmp_path,
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolDispatchSessionIntegrationContract.verify_execute_fn_restores_session_context
        - Enforces: POST-2, INV-1 (cleanup after execution)
        - Category: integration (behavioral)
        - Adversarial: Implementation-blind

        BEHAVIORAL verification that session context is cleaned up after execution.

        This test verifies the RAII pattern:
        1. Context restored BEFORE tool execution
        2. Context cleaned up AFTER tool execution (even on success)

        EXPECTED FAILURE (Current Implementation):
        No session context restoration means no cleanup needed.
        But after fix, this test verifies proper cleanup.
        """
        from typing import Any
        from unittest.mock import MagicMock

        from serena.mcp import SerenaMCPFactory
        from serena.mcp_transport_context import set_transport_session_id
        from serena.session_context import get_current_session
        from serena.tools.tools_base import Tool

        # ARRANGE
        session_id = "cleanup-test-session-456"
        session = session_registry.bind_session(session_id, workspace_root, source="http")
        set_transport_session_id(session_id)

        # Verify precondition: no session context before
        assert get_current_session() is None, "Precondition: session context should be None before test"

        class SimpleTool(Tool):
            def __init__(self):
                mock_agent = MagicMock()
                mock_agent.get_context.return_value = MagicMock(tool_description_overrides={})
                super().__init__(agent=mock_agent)

            def get_name(self) -> str:
                return "simple_tool"

            def can_edit(self) -> bool:
                return False

            def apply(self) -> dict[str, Any]:
                """Execute simple tool that returns done."""
                return {"result": "done"}

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        factory = SerenaMCPFactory(project=str(project_dir))
        tool = SimpleTool()

        # ACT
        mcp_tool_wrapper = factory.make_mcp_tool(tool)
        execute_fn = mcp_tool_wrapper.fn
        result = execute_fn()

        # ASSERT: Session context cleaned up after execution
        session_after = get_current_session()
        assert session_after is None, (
            f"INV-1 BEHAVIORAL violation: Session context NOT cleaned up after tool execution\n"
            f"Contract: ToolDispatchSessionIntegrationContract (Behavioral) INV-1\n"
            f"EXPECTED: get_current_session() returns None AFTER tool execution\n"
            f"ACTUAL: get_current_session() returned {session_after}\n"
            f"GUIDANCE: execute_fn MUST reset session context after tool.apply_ex() completes. "
            f"Use run_with_session_context() which handles cleanup in finally block. "
            f"Observable requirement: get_current_session() returns None after execute_fn returns."
        )

    def test_session_context_cleaned_up_on_tool_exception(
        self,
        session_registry,
        mcp_session_bridge,
        workspace_root,
        tmp_path,
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolDispatchSessionIntegrationContract.verify_execute_fn_restores_session_context
        - Enforces: ERROR-5, INV-1 (cleanup on exception)
        - Category: integration (behavioral)
        - Adversarial: Implementation-blind

        BEHAVIORAL verification that session context is cleaned up even when tool raises.

        This is CRITICAL for resource safety - context must not leak on exceptions.

        EXPECTED FAILURE (Current Implementation):
        No cleanup logic at all, but since no context is set, this may pass.
        After fix, this test verifies proper exception cleanup.
        """
        from typing import Any
        from unittest.mock import MagicMock

        from serena.mcp import SerenaMCPFactory
        from serena.mcp_transport_context import set_transport_session_id
        from serena.session_context import get_current_session
        from serena.tools.tools_base import Tool

        # ARRANGE
        session_id = "exception-test-session-789"
        session = session_registry.bind_session(session_id, workspace_root, source="http")
        set_transport_session_id(session_id)

        class ExceptionTool(Tool):
            def __init__(self):
                mock_agent = MagicMock()
                mock_agent.get_context.return_value = MagicMock(tool_description_overrides={})
                super().__init__(agent=mock_agent)

            def get_name(self) -> str:
                return "exception_tool"

            def can_edit(self) -> bool:
                return False

            def apply(self) -> dict[str, Any]:
                """Execute tool that raises exception for testing cleanup."""
                raise ValueError("Intentional test exception")

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        factory = SerenaMCPFactory(project=str(project_dir))
        tool = ExceptionTool()

        # ACT
        mcp_tool_wrapper = factory.make_mcp_tool(tool)
        execute_fn = mcp_tool_wrapper.fn

        # Note: apply_ex catches exceptions by default, so we check cleanup regardless
        result = execute_fn()  # Won't raise due to catch_exceptions=True

        # ASSERT: Session context cleaned up despite exception
        session_after = get_current_session()
        assert session_after is None, (
            f"ERROR-5/INV-1 BEHAVIORAL violation: Session context NOT cleaned up after tool exception\n"
            f"Contract: ToolDispatchSessionIntegrationContract (Behavioral) ERROR-5, INV-1\n"
            f"EXPECTED: get_current_session() returns None AFTER tool exception\n"
            f"ACTUAL: get_current_session() returned {session_after}\n"
            f"GUIDANCE: execute_fn MUST reset session context in finally block, ensuring cleanup "
            f"even when tool.apply_ex() catches an exception. Observable requirement: "
            f"get_current_session() returns None regardless of tool success or failure."
        )


# =============================================================================
# INTEGRATION TEST DOCUMENTATION
# =============================================================================

"""
INTEGRATION TEST COVERAGE SUMMARY:

Test I1: execute_fn_calls_run_with_session_context
- Enforces: POST-1
- Verifies: Source code contains 'run_with_session_context' call
- Observable: String inspection of execute_fn source
- Expected failure: Current implementation has NO run_with_session_context call

Test I2: execute_fn_reads_transport_session_id
- Enforces: PRE-3, POST-1
- Verifies: Source code reads transport session ID
- Observable: String inspection for get_transport_session_id
- Expected failure: Current implementation does NOT read transport ID

Test I3: execute_fn_structure_includes_session_restoration
- Enforces: POST-1, POST-2, INV-5
- Verifies: Complete session restoration structure present
- Observable: All required elements in source code
- Expected failure: Current implementation missing ALL elements

CLAUSE COVERAGE REPORT:
PRE-1: Implicit (real SerenaMCPFactory used) ✓
PRE-2: Deferred (requires SessionRegistry setup)
PRE-3: test_I2 ✓
POST-1: test_I1, test_I2, test_I3 ✓
POST-2: test_I3 ✓
INV-5: test_I3 ✓

RATIONALE FOR INSPECTION-BASED TESTING:
1. Contract specifies WHAT execute_fn must do (structural requirement)
2. Observable behavior (session restoration) follows from structure
3. Inspection is deterministic and doesn't require complex runtime setup
4. RED phase demonstrates violation at source code level
5. GREEN phase will show structural fix in source code

This approach is valid per CL12-E (Test-Contract Traceability):
- Tests verify structural contracts (must call specific functions)
- Observable effect: Source code contains required calls
- Deterministic: No runtime variability
"""
