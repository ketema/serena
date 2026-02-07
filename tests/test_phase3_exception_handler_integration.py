"""
Integration tests for Phase 3 Exception Handler Rewiring (REQ-2026-005).

Tests the integration between Tool.apply_ex() exception handler and
SerenaAgent.handle_lsp_termination() for surgical LSP restart on termination.

Contract Authority: contracts/lsp_lifecycle_authority_contract.py
Enforces: ToolExceptionHandlerContract (SEQ-TEH-01, SEQ-TEH-02, all POST/INV/ERRORS)

NOTE: handle_lsp_termination() and apply_ex() rewiring DON'T EXIST YET (RED phase).
Tests will fail until implementation is complete. This is intentional - tests specify
the behavior.

Integration Test Strategy (Tier 1.5):
These tests verify WIRING between apply_ex() → handle_lsp_termination() → surgical_restart_lsp().
They test through actual lifecycle paths, not direct method calls.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, PropertyMock

from solidlsp.ls_handler import LanguageServerTerminatedException
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_config import Language

from serena.agent import SerenaAgent
from serena.global_lsp_pool import GlobalLanguageServerPool
from serena.tools.tools_base import Tool


class DummyTool(Tool):
    """
    Concrete Tool subclass for testing exception handler integration.

    Provides configurable apply behavior:
    - Can raise on first call, succeed on second (for retry tests)
    - Can raise specific exceptions (terminated, restart failure)
    """

    def __init__(self, agent, apply_fn=None):
        super().__init__(agent)
        self._apply_fn = apply_fn or (lambda: "success")
        self.call_count = 0

    def get_apply_fn(self):
        """Return the configured apply function."""
        def wrapped_apply():
            self.call_count += 1
            return self._apply_fn()
        return wrapped_apply

    def is_active(self):
        """Always active for tests."""
        return True


class TestExceptionHandlerIntegration(unittest.TestCase):
    """
    Integration tests for apply_ex() exception handler rewiring.

    Contract: ToolExceptionHandlerContract
    File: contracts/lsp_lifecycle_authority_contract.py (lines 230-303)

    These are Tier 1.5 integration tests - they verify WIRING, not just behavior.
    Tests must use actual construction/lifecycle paths per SEQ testing discipline.
    """

    def setUp(self):
        """
        Setup mock SerenaAgent with mock LSP pool for integration testing.

        NOTE: We mock the agent's dependencies but test the REAL wiring between
        apply_ex() and handle_lsp_termination() through actual execution paths.
        """
        # Mock agent with required attributes
        self.mock_agent = MagicMock(spec=SerenaAgent)
        self.mock_agent.serena_config = MagicMock()
        self.mock_agent.serena_config.tool_timeout = 30

        # Mock LSP pool
        self.mock_lsp_pool = MagicMock(spec=GlobalLanguageServerPool)
        self.mock_agent._lsp_pool = self.mock_lsp_pool

        # Mock project (required for apply_ex active project check)
        self.mock_project = MagicMock()
        self.mock_project.project_root = "/workspace"
        self.mock_agent.get_active_project.return_value = self.mock_project

        # Mock issue_task to execute synchronously (not async)
        def sync_issue_task(task_fn, name=None):
            future = MagicMock()
            future.result.return_value = task_fn()
            return future
        self.mock_agent.issue_task.side_effect = sync_issue_task

        # Mock record_tool_usage (called after successful tool execution)
        self.mock_agent.record_tool_usage = MagicMock()

        # Mock language_server property
        type(self.mock_agent).language_server = PropertyMock(return_value=None)

    def test_seq_teh_01_apply_ex_calls_handle_lsp_termination_on_terminated(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: SEQ-TEH-01: Tool.apply_ex() MUST call handle_lsp_termination()
                    when LanguageServerTerminatedException caught (NOT reset_language_server())
        - Category: integration (wiring)
        - Adversarial: Implementation-blind

        Test Strategy:
        Construct tool via normal lifecycle (DummyTool(agent)), configure apply_fn
        to raise terminated exception, call apply_ex(), verify handle_lsp_termination
        was invoked through actual exception handler path (not direct call).

        SEQ_TEST_SELF_CHECK:
        [✓] Test constructs PARENT object via __init__()? YES - DummyTool(agent)
        [✓] Test verifies SEQ behavior through parent state/side effects? YES - via mock assertion
        [✓] Test does NOT directly call the callee method? YES - no direct call to handle_lsp_termination
        [✓] If mock used, injected at construction time? YES - agent with handle_lsp_termination mocked
        """
        # ARRANGE: Setup apply_fn that raises terminated exception
        terminated_exc = LanguageServerTerminatedException(
            message="LSP crashed",
            language=Language.PYTHON
        )

        # Wrap in SolidLSPException (apply_ex catches this type)
        solid_exc = SolidLSPException(
            cause=terminated_exc,
            message="LSP exception occurred"
        )

        def raise_terminated():
            raise solid_exc

        # Configure agent to have handle_lsp_termination that succeeds
        self.mock_agent.handle_lsp_termination = MagicMock(return_value="retry_success")

        # Create tool through normal construction path
        tool = DummyTool(self.mock_agent, apply_fn=raise_terminated)

        # ACT: Execute tool through apply_ex() (actual lifecycle path)
        result = tool.apply_ex(log_call=False, catch_exceptions=True)

        # ASSERT: Verify SEQ-TEH-01 - handle_lsp_termination was called
        assert self.mock_agent.handle_lsp_termination.called, (
            "SEQ-TEH-01 violation: apply_ex() did not call handle_lsp_termination()\n"
            f"Contract: ToolExceptionHandlerContract SEQ-TEH-01\n"
            f"EXPECTED: handle_lsp_termination() called when LanguageServerTerminatedException caught\n"
            f"ACTUAL: handle_lsp_termination.called = {self.mock_agent.handle_lsp_termination.called}\n"
            f"GUIDANCE: apply_ex() MUST catch SolidLSPException with is_language_server_terminated() == True\n"
            f"           and invoke handle_lsp_termination(language, workspace_root, retry_fn).\n"
            f"           Extract language from exception.cause.language. Do NOT call reset_language_server()."
        )

        # Verify correct arguments passed (language from exception, workspace from project, retry callable)
        call_args = self.mock_agent.handle_lsp_termination.call_args
        assert call_args is not None, "handle_lsp_termination not called with arguments"

        called_language = call_args[0][0] if len(call_args[0]) > 0 else call_args[1].get('language')
        assert called_language == Language.PYTHON, (
            f"SEQ-TEH-01 violation: Wrong language passed to handle_lsp_termination\n"
            f"EXPECTED: Language.PYTHON (from exception.cause.language)\n"
            f"ACTUAL: {called_language}\n"
            f"GUIDANCE: Extract language from LanguageServerTerminatedException.language attribute"
        )

    def test_inv_teh_01_apply_ex_does_not_call_reset_language_server(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: INV-TEH-01: Exception handler SHALL NOT call reset_language_server()
                    (pool-wide replacement forbidden)
        - Category: invariant (negative test)
        - Adversarial: Implementation-blind

        Test Strategy:
        Configure apply_fn to raise terminated, verify reset_language_server is
        NEVER called. This is the critical invariant - old code called reset_language_server,
        new code must call handle_lsp_termination instead.

        SEQ_TEST_SELF_CHECK:
        [✓] Test constructs PARENT object via __init__()? YES - DummyTool(agent)
        [✓] Test verifies SEQ behavior through parent state/side effects? YES - via negative assertion
        [✓] Test does NOT directly call the callee method? N/A - this is invariant test
        [✓] If mock used, injected at construction time? YES - agent with reset_language_server mocked
        """
        # ARRANGE: Setup terminated exception
        terminated_exc = LanguageServerTerminatedException(
            message="LSP crashed",
            language=Language.PYTHON
        )
        solid_exc = SolidLSPException(
            cause=terminated_exc,
            message="LSP exception"
        )

        def raise_terminated():
            raise solid_exc

        # Mock both methods to track calls
        self.mock_agent.reset_language_server = MagicMock()
        self.mock_agent.handle_lsp_termination = MagicMock(return_value="handled")

        tool = DummyTool(self.mock_agent, apply_fn=raise_terminated)

        # ACT: Execute through apply_ex()
        result = tool.apply_ex(log_call=False, catch_exceptions=True)

        # ASSERT: Verify INV-TEH-01 - reset_language_server NEVER called
        assert not self.mock_agent.reset_language_server.called, (
            "INV-TEH-01 violation: apply_ex() called reset_language_server() on LSP termination\n"
            f"Contract: ToolExceptionHandlerContract INV-TEH-01\n"
            f"EXPECTED: reset_language_server() NEVER called (pool-wide nuke forbidden)\n"
            f"ACTUAL: reset_language_server.called = {self.mock_agent.reset_language_server.called}\n"
            f"GUIDANCE: On LanguageServerTerminatedException, MUST call handle_lsp_termination()\n"
            f"           for surgical restart. reset_language_server() nukes ALL LSPs (forbidden)."
        )

    def test_post_teh_03_successful_restart_retries_and_returns_result(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: POST-TEH-03: Tool call retried on restarted LSP, returns retry result
        - Category: positive (happy path)
        - Adversarial: Implementation-blind

        Test Strategy:
        First call raises terminated, retry (via handle_lsp_termination) succeeds.
        Verify final result is the retry success value.

        SEQ_TEST_SELF_CHECK:
        [✓] Test constructs PARENT object via __init__()? YES
        [✓] Test verifies SEQ behavior through parent state/side effects? YES - via return value
        [✓] Test does NOT directly call the callee method? YES - tested through apply_ex path
        [✓] If mock used, injected at construction time? YES
        """
        # ARRANGE: First call fails, second succeeds
        call_count = 0
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                terminated_exc = LanguageServerTerminatedException(
                    message="LSP crashed",
                    language=Language.PYTHON
                )
                raise SolidLSPException(cause=terminated_exc, message="LSP error")
            else:
                return "retry_succeeded"

        # Mock handle_lsp_termination to call the retry_fn
        def mock_handle_termination(language, workspace_root, retry_fn):
            # Simulate successful restart + retry
            return retry_fn()

        self.mock_agent.handle_lsp_termination = MagicMock(side_effect=mock_handle_termination)

        tool = DummyTool(self.mock_agent, apply_fn=fail_then_succeed)

        # ACT: Execute through apply_ex()
        result = tool.apply_ex(log_call=False, catch_exceptions=True)

        # ASSERT: Verify POST-TEH-03 - retry succeeded and result returned
        assert result == "retry_succeeded", (
            "POST-TEH-03 violation: apply_ex() did not return retry result after successful restart\n"
            f"Contract: ToolExceptionHandlerContract POST-TEH-03\n"
            f"EXPECTED: 'retry_succeeded' (result from retry after restart)\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: After handle_lsp_termination() completes, the retry_fn result MUST be returned\n"
            f"           to the client. This demonstrates the tool operation succeeded after restart."
        )

        # Verify handle_lsp_termination was called with retry_fn that works
        assert self.mock_agent.handle_lsp_termination.called, "handle_lsp_termination not called"

    def test_errors_teh_01_restart_failure_returns_error_no_retry(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: ERRORS-TEH-01: If surgical restart fails (LSPRestartError),
                    return error to client (do NOT retry)
        - Category: error (negative path)
        - Adversarial: Implementation-blind

        Test Strategy:
        Configure handle_lsp_termination to return error string (simulating restart failure).
        Verify apply_ex returns the error and does NOT retry the tool operation.

        SEQ_TEST_SELF_CHECK:
        [✓] Test constructs PARENT object via __init__()? YES
        [✓] Test verifies SEQ behavior through parent state/side effects? YES - via error return + no retry
        [✓] Test does NOT directly call the callee method? YES
        [✓] If mock used, injected at construction time? YES
        """
        # ARRANGE: Tool raises terminated
        terminated_exc = LanguageServerTerminatedException(
            message="LSP crashed",
            language=Language.PYTHON
        )
        solid_exc = SolidLSPException(cause=terminated_exc, message="LSP error")

        def raise_terminated():
            raise solid_exc

        # Mock handle_lsp_termination to return error (simulates restart failure)
        error_msg = "Error: LSP restart failed - LSPRestartError"
        self.mock_agent.handle_lsp_termination = MagicMock(return_value=error_msg)

        tool = DummyTool(self.mock_agent, apply_fn=raise_terminated)

        # ACT: Execute through apply_ex()
        result = tool.apply_ex(log_call=False, catch_exceptions=True)

        # ASSERT: Verify ERRORS-TEH-01 - error returned, no retry
        assert result == error_msg, (
            "ERRORS-TEH-01 violation: apply_ex() did not return error when restart failed\n"
            f"Contract: ToolExceptionHandlerContract ERRORS-TEH-01\n"
            f"EXPECTED: '{error_msg}' (error from handle_lsp_termination)\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: When handle_lsp_termination() returns an error string (restart failed),\n"
            f"           apply_ex() MUST return that error to the client immediately. Do NOT retry."
        )

        # Verify tool operation was NOT retried (call_count should be 1)
        assert tool.call_count == 1, (
            f"ERRORS-TEH-01 violation: Tool operation retried after restart failure\n"
            f"EXPECTED: call_count = 1 (original call only, no retry)\n"
            f"ACTUAL: call_count = {tool.call_count}\n"
            f"GUIDANCE: When restart fails, do NOT call retry_fn. Return error immediately."
        )

    def test_errors_teh_02_retry_failure_returns_error_no_infinite_loop(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: ERRORS-TEH-02: If retry after restart also raises
                    LanguageServerTerminatedException, return error (max 1 retry)
        - Category: error (prevent infinite loop)
        - Adversarial: Implementation-blind

        Test Strategy:
        Both first call AND retry raise terminated exception. Verify error returned
        (not infinite restart loop) and call count is exactly 2 (original + 1 retry).

        SEQ_TEST_SELF_CHECK:
        [✓] Test constructs PARENT object via __init__()? YES
        [✓] Test verifies SEQ behavior through parent state/side effects? YES - via call count + error
        [✓] Test does NOT directly call the callee method? YES
        [✓] If mock used, injected at construction time? YES
        """
        # ARRANGE: Tool always raises terminated
        def always_raise_terminated():
            terminated_exc = LanguageServerTerminatedException(
                message="LSP keeps crashing",
                language=Language.PYTHON
            )
            raise SolidLSPException(cause=terminated_exc, message="LSP error")

        # Mock handle_lsp_termination to simulate retry that also fails
        def mock_handle_with_retry_failure(language, workspace_root, retry_fn):
            try:
                # Attempt retry (will raise terminated again)
                return retry_fn()
            except SolidLSPException as e:
                if e.is_language_server_terminated():
                    # Retry failed with termination - return error per ERRORS-TEH-02
                    return "Error: Retry after restart also failed with LSP termination"
                raise

        self.mock_agent.handle_lsp_termination = MagicMock(side_effect=mock_handle_with_retry_failure)

        tool = DummyTool(self.mock_agent, apply_fn=always_raise_terminated)

        # ACT: Execute through apply_ex()
        result = tool.apply_ex(log_call=False, catch_exceptions=True)

        # ASSERT: Verify ERRORS-TEH-02 - error returned, no infinite retry
        assert "Error" in result and "Retry" in result, (
            "ERRORS-TEH-02 violation: apply_ex() did not return error when retry also failed\n"
            f"Contract: ToolExceptionHandlerContract ERRORS-TEH-02\n"
            f"EXPECTED: Error message about retry failure (no infinite restart loop)\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: When retry_fn() also raises LanguageServerTerminatedException,\n"
            f"           handle_lsp_termination() MUST return error string. Do NOT restart again."
        )

        # Verify exactly 2 calls: original + 1 retry (not infinite)
        assert tool.call_count == 2, (
            f"ERRORS-TEH-02 violation: Wrong number of tool calls (possible infinite retry)\n"
            f"Contract: ToolExceptionHandlerContract ERRORS-TEH-02\n"
            f"EXPECTED: call_count = 2 (original + 1 retry, then error)\n"
            f"ACTUAL: call_count = {tool.call_count}\n"
            f"GUIDANCE: Maximum 1 retry allowed. If retry also fails, return error (no infinite loop)."
        )

    def test_non_terminated_exception_re_raises(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract (implicit behavior)
        - Enforces: Non-terminated LSP exceptions should re-raise (existing behavior preserved)
        - Category: negative (non-terminated exception)
        - Adversarial: Implementation-blind

        Test Strategy:
        Raise SolidLSPException with is_language_server_terminated() == False.
        Verify exception is re-raised (not caught by termination handler).
        This ensures we only handle termination, not all LSP exceptions.
        """
        # ARRANGE: Non-terminated LSP exception
        non_terminated_exc = SolidLSPException(
            cause=Exception("Some other LSP error"),
            message="LSP error but not terminated"
        )
        # Mock is_language_server_terminated to return False
        non_terminated_exc.is_language_server_terminated = MagicMock(return_value=False)

        def raise_non_terminated():
            raise non_terminated_exc

        self.mock_agent.handle_lsp_termination = MagicMock()

        tool = DummyTool(self.mock_agent, apply_fn=raise_non_terminated)

        # ACT: Execute with catch_exceptions=True (should catch and return error string)
        result = tool.apply_ex(log_call=False, catch_exceptions=True)

        # ASSERT: Verify non-terminated exception was NOT handled by termination handler
        assert not self.mock_agent.handle_lsp_termination.called, (
            "Non-terminated LSP exception incorrectly handled by termination handler\n"
            f"EXPECTED: handle_lsp_termination() NOT called (only for terminated exceptions)\n"
            f"ACTUAL: handle_lsp_termination.called = {self.mock_agent.handle_lsp_termination.called}\n"
            f"GUIDANCE: Only catch SolidLSPException if is_language_server_terminated() == True.\n"
            f"           Other LSP exceptions should re-raise or be caught by outer handler."
        )

        # Verify error was caught by outer exception handler (catch_exceptions=True)
        assert "Error executing tool" in result, (
            f"Non-terminated exception handling incorrect\n"
            f"EXPECTED: Error string from outer catch handler\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Non-terminated exceptions should re-raise from inner handler,\n"
            f"           then be caught by outer catch_exceptions handler."
        )


if __name__ == "__main__":
    unittest.main()
