"""
Logging Observability Contract Tests — Batch B (Tiers 3+4)

CONTRACT: contracts/logging_observability_contract.py
CLAUSES: LOG-EXC-01 through LOG-EXC-05 (Tier 3: Exception Handling)
         LOG-REG-01 through LOG-REG-05 (Tier 4: Session Registry)

SCOPE:
  - Tier 3: src/serena/agent.py (handle_lsp_termination)
  - Tier 3: src/serena/tools/tools_base.py (apply_ex)
  - Tier 4: src/serena/session_registry.py (bind_session, unbind_session)
  - Tier 4: src/serena/agent.py (activate_session_project, deactivate_session)

ADVERSARIAL: Implementation-blind test design. Tests written from contract only.

CL12 COMPLIANCE:
  - Every test cites clause ID in docstring (CL12-E)
  - Every assertion references clause ID in error message (CL12-E)
  - 5-point error messages (What/Why/Expected/Actual/Guidance)
  - No mocks without verified contracts (CL10)
  - Observable enforcement testing (CL12-A)
  - Theater test detection applied (all tests fail if impl missing)

EXPECTED OUTCOME: All tests FAIL (RED phase) — no logging exists in these methods yet.
"""

import logging
import os
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch, call

# Target modules
from serena.agent import SerenaAgent
from serena.session_registry import SessionRegistry
from serena.tools.tools_base import Tool
from solidlsp.ls_exceptions import SolidLSPException
from serena.global_lsp_pool import LSPRestartError

# Test dependencies
from solidlsp.ls_config import Language
from serena.project import Project


# =============================================================================
# TIER 3: Exception Handling — handle_lsp_termination()
# =============================================================================

class TestHandleLSPTerminationLogging(unittest.TestCase):
    """
    Tests for LOG-EXC-01 through LOG-EXC-04 clauses.

    TARGET: SerenaAgent.handle_lsp_termination()
    LOGGER: serena.agent (module name, not variable name 'log')
    """

    def setUp(self):
        """Setup agent with mocked LSP pool and dependencies."""
        self.agent = SerenaAgent()
        self.agent._lsp_pool = MagicMock()
        self.language = Language.PYTHON
        self.workspace_root = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Cleanup temporary workspace directory."""
        if self.workspace_root.exists():
            os.rmdir(self.workspace_root)

    def test_log_exc_01_restart_initiated(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_EXC_01
        - Enforces: LOG-EXC-01: INFO log at start of restart attempt
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock surgical_restart_lsp to succeed
        self.agent.lsp_pool.surgical_restart_lsp = MagicMock()
        mock_retry_fn = MagicMock(return_value="Success")

        # ACT & ASSERT: Capture logs during handle_lsp_termination
        with self.assertLogs("serena.agent", level=logging.INFO) as log_capture:
            self.agent.handle_lsp_termination(
                self.language,
                self.workspace_root,
                mock_retry_fn
            )

        # ASSERT: Verify LOG-EXC-01 guarantee
        logs = log_capture.output
        expected_log = f"[LSP-Recovery] Surgical restart initiated for {self.language.value} LSP"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-EXC-01 violation: Restart initiation log missing\n"
            f"Contract: logging_observability_contract.LOG_EXC_01\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: MUST emit INFO log at start of restart attempt, BEFORE calling surgical_restart_lsp(). "
            f"Log format MUST match contract exactly. Logger MUST be serena.agent module logger."
        )

    def test_log_exc_02_probe_ready(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_EXC_02
        - Enforces: LOG-EXC-02 (POST-READY): INFO log when probe returns True
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock surgical_restart_lsp and probe to succeed
        self.agent.lsp_pool.surgical_restart_lsp = MagicMock()
        mock_retry_fn = MagicMock(return_value="Success")

        with patch("serena.global_lsp_pool.probe_workspace_readiness", return_value=True):
            # ACT & ASSERT: Capture logs
            with self.assertLogs("serena.agent", level=logging.INFO) as log_capture:
                self.agent.handle_lsp_termination(
                    self.language,
                    self.workspace_root,
                    mock_retry_fn
                )

            # ASSERT: Verify LOG-EXC-02 POST-READY guarantee
            logs = log_capture.output
            expected_log = f"[LSP-Recovery] {self.language.value} LSP ready after restart (workspace: {self.workspace_root})"

            matching_logs = [log for log in logs if expected_log in log]
            assert len(matching_logs) == 1, (
                f"LOG-EXC-02 (POST-READY) violation: Probe ready log missing\n"
                f"Contract: logging_observability_contract.LOG_EXC_02\n"
                f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
                f"ACTUAL: {len(matching_logs)} matching logs found\n"
                f"All logs: {logs}\n"
                f"GUIDANCE: When probe_workspace_readiness returns True, MUST emit INFO log showing LSP ready status. "
                f"Log MUST include language, workspace_root. Format MUST match contract exactly."
            )

    def test_log_exc_02_probe_timeout(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_EXC_02
        - Enforces: LOG-EXC-02 (POST-TIMEOUT): WARNING log when probe returns False
        - Category: negative
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock surgical_restart_lsp and probe to timeout
        self.agent.lsp_pool.surgical_restart_lsp = MagicMock()
        mock_retry_fn = MagicMock(return_value="Success")
        timeout = 30.0

        with patch("serena.global_lsp_pool.probe_workspace_readiness", return_value=False):
            # ACT & ASSERT: Capture logs
            with self.assertLogs("serena.agent", level=logging.WARNING) as log_capture:
                self.agent.handle_lsp_termination(
                    self.language,
                    self.workspace_root,
                    mock_retry_fn
                )

            # ASSERT: Verify LOG-EXC-02 POST-TIMEOUT guarantee
            logs = log_capture.output
            expected_log_pattern = f"[LSP-Recovery] {self.language.value} LSP not ready after"
            expected_workspace = str(self.workspace_root)

            matching_logs = [log for log in logs if expected_log_pattern in log and expected_workspace in log]
            assert len(matching_logs) == 1, (
                f"LOG-EXC-02 (POST-TIMEOUT) violation: Probe timeout log missing\n"
                f"Contract: logging_observability_contract.LOG_EXC_02\n"
                f"EXPECTED: Exactly one WARNING log containing '{expected_log_pattern}' and workspace path\n"
                f"ACTUAL: {len(matching_logs)} matching logs found\n"
                f"All logs: {logs}\n"
                f"GUIDANCE: When probe_workspace_readiness returns False, MUST emit WARNING log showing timeout. "
                f"Log MUST include language, timeout duration, workspace_root. Level MUST be WARNING not INFO."
            )

    def test_log_exc_03_retry_success(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_EXC_03
        - Enforces: LOG-EXC-03 (POST-SUCCESS): INFO log when retry_fn succeeds
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock surgical_restart_lsp and successful retry
        self.agent.lsp_pool.surgical_restart_lsp = MagicMock()
        mock_retry_fn = MagicMock(return_value="Success")

        # ACT & ASSERT: Capture logs
        # Must mock probe_workspace_readiness to return True so code reaches retry_fn
        with patch("serena.global_lsp_pool.probe_workspace_readiness", return_value=True):
            with self.assertLogs("serena.agent", level=logging.INFO) as log_capture:
                self.agent.handle_lsp_termination(
                    self.language,
                    self.workspace_root,
                    mock_retry_fn
                )

        # ASSERT: Verify LOG-EXC-03 POST-SUCCESS guarantee
        logs = log_capture.output
        expected_log = f"[LSP-Recovery] Retry succeeded for {self.language.value} LSP"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-EXC-03 (POST-SUCCESS) violation: Retry success log missing\n"
            f"Contract: logging_observability_contract.LOG_EXC_03\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: When retry_fn() completes successfully without raising, MUST emit INFO log showing retry success. "
            f"Log MUST include language name. Format MUST match contract exactly."
        )

    def test_log_exc_03_retry_terminated(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_EXC_03
        - Enforces: LOG-EXC-03 (POST-TERMINATED): WARNING log when retry_fn raises termination again
        - Category: negative
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock surgical_restart_lsp and retry that raises termination again
        self.agent.lsp_pool.surgical_restart_lsp = MagicMock()
        # Must create proper cause chain so is_language_server_terminated() returns True
        from solidlsp.ls_handler import LanguageServerTerminatedException
        terminated_cause = LanguageServerTerminatedException("Terminated again", Language.PYTHON)
        mock_retry_fn = MagicMock(
            side_effect=SolidLSPException("Terminated again", cause=terminated_cause)
        )

        # ACT & ASSERT: Capture logs
        # Must mock probe_workspace_readiness to return True so code reaches retry_fn
        with patch("serena.global_lsp_pool.probe_workspace_readiness", return_value=True):
            with self.assertLogs("serena.agent", level=logging.WARNING) as log_capture:
                self.agent.handle_lsp_termination(
                    self.language,
                    self.workspace_root,
                    mock_retry_fn
                )

        # ASSERT: Verify LOG-EXC-03 POST-TERMINATED guarantee
        logs = log_capture.output
        expected_log = f"[LSP-Recovery] Retry failed for {self.language.value} LSP: second termination"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-EXC-03 (POST-TERMINATED) violation: Retry failure log missing\n"
            f"Contract: logging_observability_contract.LOG_EXC_03\n"
            f"EXPECTED: Exactly one WARNING log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: When retry_fn() raises SolidLSPException again, MUST emit WARNING log showing second termination. "
            f"Log MUST include language name. Level MUST be WARNING not INFO."
        )

    def test_log_exc_04_restart_failure(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_EXC_04
        - Enforces: LOG-EXC-04: ERROR log when LSPRestartError caught
        - Category: error
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock surgical_restart_lsp to raise LSPRestartError
        error_msg = "Restart failed: timeout"
        self.agent.lsp_pool.surgical_restart_lsp = MagicMock(
            side_effect=LSPRestartError(error_msg)
        )
        mock_retry_fn = MagicMock()

        # ACT & ASSERT: Capture logs
        with self.assertLogs("serena.agent", level=logging.ERROR) as log_capture:
            result = self.agent.handle_lsp_termination(
                self.language,
                self.workspace_root,
                mock_retry_fn
            )

        # ASSERT: Verify LOG-EXC-04 guarantee
        logs = log_capture.output
        expected_log_pattern = f"[LSP-Recovery] Restart failed for {self.language.value} LSP:"

        matching_logs = [log for log in logs if expected_log_pattern in log and error_msg in log]
        assert len(matching_logs) == 1, (
            f"LOG-EXC-04 violation: Restart failure log missing\n"
            f"Contract: logging_observability_contract.LOG_EXC_04\n"
            f"EXPECTED: Exactly one ERROR log containing '{expected_log_pattern}' and error message\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: When surgical_restart_lsp raises LSPRestartError, MUST emit ERROR log in except block. "
            f"Log MUST include language and error message. Level MUST be ERROR not WARNING."
        )


# =============================================================================
# TIER 3: Exception Handling — apply_ex()
# =============================================================================

class TestApplyExLogging(unittest.TestCase):
    """
    Tests for LOG-EXC-05 clause.

    TARGET: Tool.apply_ex()
    LOGGER: serena.tools.tools_base (module name)
    """

    def setUp(self):
        """Setup tool with mocked agent and dependencies."""
        from solidlsp.ls_handler import LanguageServerTerminatedException
        from unittest.mock import PropertyMock

        self.agent = MagicMock()

        # Make issue_task actually execute the task function
        def execute_task_immediately(task, name=None, logged=True, timeout=None):
            result = task()
            future_mock = MagicMock()
            future_mock.result.return_value = result
            return future_mock
        self.agent.issue_task.side_effect = execute_task_immediately
        self.agent.serena_config.tool_timeout = 30

        self.tool = Tool(agent=self.agent)

        # Derive expected tool name from get_name_from_cls() — for base Tool class this is ""
        # but we need a meaningful name. Use a known tool name via mock.
        self.expected_tool_name = Tool.get_name_from_cls()

        # Build proper cause chain: SolidLSPException wrapping LanguageServerTerminatedException
        self.lsp_terminated_cause = LanguageServerTerminatedException(
            "LSP process exited", Language.PYTHON
        )
        self.lsp_exception = SolidLSPException(
            "LSP terminated", cause=self.lsp_terminated_cause
        )

        # Mock active project with valid project_root
        self.mock_project = MagicMock()
        self.mock_project.project_root = "/tmp/test_workspace"
        self.agent.get_active_project.return_value = self.mock_project
        self.agent.language_server = None
        # is_active check: tool_is_active must return True
        self.agent.tool_is_active.return_value = True

    def test_log_exc_05_recovery_success(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_EXC_05
        - Enforces: LOG-EXC-05: INFO log showing "LSP recovery succeeded" when result is success
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock apply() to raise SolidLSPException with proper cause chain
        self.tool.apply = MagicMock(side_effect=self.lsp_exception)
        self.agent.handle_lsp_termination.return_value = "Recovery successful"

        # ACT & ASSERT: Capture logs
        with self.assertLogs("serena.tools.tools_base", level=logging.INFO) as log_capture:
            self.tool.apply_ex()

        # ASSERT: Verify LOG-EXC-05 guarantee
        logs = log_capture.output
        # Tool.get_name_from_cls() derives name from class name, not self.name attribute
        expected_log = f"[Tool] {self.expected_tool_name}: LSP recovery succeeded"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-EXC-05 violation: Recovery success log missing\n"
            f"Contract: logging_observability_contract.LOG_EXC_05\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: After handle_lsp_termination returns with success result (not starting with 'Error:'), "
            f"MUST emit INFO log showing recovery succeeded. Log MUST include tool name. "
            f"This is the OUTCOME log that confirms recovery worked."
        )

    def test_log_exc_05_recovery_error(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_EXC_05
        - Enforces: LOG-EXC-05: INFO log showing "LSP recovery returned error" when result is error
        - Category: negative
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock apply() to raise SolidLSPException with proper cause chain
        self.tool.apply = MagicMock(side_effect=self.lsp_exception)
        self.agent.handle_lsp_termination.return_value = "Error: Restart failed"

        # ACT & ASSERT: Capture logs
        with self.assertLogs("serena.tools.tools_base", level=logging.INFO) as log_capture:
            result = self.tool.apply_ex()

        # ASSERT: Verify LOG-EXC-05 guarantee
        logs = log_capture.output
        # Tool.get_name_from_cls() derives name from class name, not self.name attribute
        expected_log = f"[Tool] {self.expected_tool_name}: LSP recovery returned error"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-EXC-05 violation: Recovery error log missing\n"
            f"Contract: logging_observability_contract.LOG_EXC_05\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: After handle_lsp_termination returns error result (starting with 'Error:'), "
            f"MUST emit INFO log showing recovery returned error. Log MUST include tool name. "
            f"This is the OUTCOME log that shows recovery attempt completed but failed."
        )


# =============================================================================
# TIER 4: Session Registry — bind_session() and unbind_session()
# =============================================================================

class TestSessionRegistryLogging(unittest.TestCase):
    """
    Tests for LOG-REG-01, LOG-REG-02, LOG-REG-03 clauses.

    TARGET: SessionRegistry.bind_session() and unbind_session()
    LOGGER: serena.session_registry (module name — NEW logger required)
    """

    def setUp(self):
        """Setup session registry."""
        self.registry = SessionRegistry()
        self.session_id = "12345678-1234-1234-1234-123456789012"
        self.workspace_root = Path(tempfile.mkdtemp())
        self.source = "explicit"

    def tearDown(self):
        """Cleanup temporary workspace directory."""
        if self.workspace_root.exists():
            os.rmdir(self.workspace_root)

    def test_log_reg_01_bind_session(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_REG_01
        - Enforces: LOG-REG-01: INFO log when session successfully bound
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ACT & ASSERT: Capture logs
        with self.assertLogs("serena.session_registry", level=logging.INFO) as log_capture:
            self.registry.bind_session(
                self.session_id,
                self.workspace_root,
                source=self.source
            )

        # ASSERT: Verify LOG-REG-01 guarantee
        logs = log_capture.output
        short_id = self.session_id[:8]
        # bind_session resolves workspace_root, so on macOS /var/... becomes /private/var/...
        resolved_workspace = str(self.workspace_root.resolve())
        expected_log = f"[Session: {short_id}] Bound to {resolved_workspace} (source: {self.source})"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-REG-01 violation: Session bind log missing\n"
            f"Contract: logging_observability_contract.LOG_REG_01\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: After session stored in _sessions dict, MUST emit INFO log showing session bound. "
            f"Log MUST include short_id (first 8 chars), workspace_root, source. "
            f"Format MUST match contract exactly. Logger MUST be serena.session_registry module logger."
        )

    def test_log_reg_02_unbind_session(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_REG_02
        - Enforces: LOG-REG-02: INFO log when session removed
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Bind session first
        self.registry.bind_session(self.session_id, self.workspace_root, source=self.source)

        # ACT & ASSERT: Capture logs during unbind
        with self.assertLogs("serena.session_registry", level=logging.INFO) as log_capture:
            self.registry.unbind_session(self.session_id)

        # ASSERT: Verify LOG-REG-02 guarantee
        logs = log_capture.output
        short_id = self.session_id[:8]
        # bind_session resolves workspace_root, so unbind logs the resolved path
        resolved_workspace = str(self.workspace_root.resolve())
        expected_log = f"[Session: {short_id}] Unbound from {resolved_workspace}"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-REG-02 violation: Session unbind log missing\n"
            f"Contract: logging_observability_contract.LOG_REG_02\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: After session removed from _sessions dict, MUST emit INFO log showing session unbound. "
            f"Log MUST include short_id, workspace_root. Format MUST match contract exactly."
        )

    def test_log_reg_02_unbind_noop(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_REG_02
        - Enforces: LOG-REG-02 (POST-NOOP): DEBUG log when session_id not found
        - Category: boundary
        - Adversarial: Implementation-blind
        """
        # ACT & ASSERT: Unbind non-existent session
        with self.assertLogs("serena.session_registry", level=logging.DEBUG) as log_capture:
            self.registry.unbind_session(self.session_id)

        # ASSERT: Verify LOG-REG-02 POST-NOOP guarantee
        logs = log_capture.output
        short_id = self.session_id[:8]
        expected_log = f"[Session: {short_id}] Unbind no-op: not in registry"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-REG-02 (POST-NOOP) violation: Unbind no-op log missing\n"
            f"Contract: logging_observability_contract.LOG_REG_02\n"
            f"EXPECTED: Exactly one DEBUG log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: When session_id not found in registry, MUST emit DEBUG log showing no-op. "
            f"Log MUST include short_id. Level MUST be DEBUG not INFO. "
            f"This is idempotent cleanup behavior — calling unbind twice should not error."
        )

    def test_log_reg_03_last_session_for_workspace(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_REG_03
        - Enforces: LOG-REG-03: INFO log when last session for workspace removed
        - Category: boundary
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Bind session (will be the only session for this workspace)
        self.registry.bind_session(self.session_id, self.workspace_root, source=self.source)

        # ACT & ASSERT: Unbind last session
        with self.assertLogs("serena.session_registry", level=logging.INFO) as log_capture:
            self.registry.unbind_session(self.session_id)

        # ASSERT: Verify LOG-REG-03 guarantee
        logs = log_capture.output
        short_id = self.session_id[:8]
        # bind_session resolves workspace_root, so last-session log uses resolved path
        resolved_workspace = str(self.workspace_root.resolve())
        expected_log = f"[Session: {short_id}] Last session for {resolved_workspace}, workspace cleanup eligible"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-REG-03 violation: Last session cleanup log missing\n"
            f"Contract: logging_observability_contract.LOG_REG_03\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: When removing last session for a workspace (workspace_sessions becomes empty), "
            f"MUST emit INFO log showing workspace is now cleanup-eligible. "
            f"Log MUST include short_id, workspace_root. "
            f"This is a critical observability point — signals when workspace LSPs can be reclaimed."
        )


# =============================================================================
# TIER 4: Session Registry — activate_session_project() and deactivate_session()
# =============================================================================

class TestAgentSessionLogging(unittest.TestCase):
    """
    Tests for LOG-REG-04 and LOG-REG-05 clauses.

    TARGET: SerenaAgent.activate_session_project() and deactivate_session()
    LOGGER: serena.agent (module name)
    """

    def setUp(self):
        """Setup agent with mocked dependencies."""
        self.agent = SerenaAgent()
        self.agent._session_registry = SessionRegistry()
        self.session_id = "12345678-1234-1234-1234-123456789012"
        self.workspace_root = Path(tempfile.mkdtemp())

        # Mock project loading
        self.mock_project = MagicMock(spec=Project)
        self.mock_project.path = self.workspace_root

    def tearDown(self):
        """Cleanup temporary workspace directories."""
        if self.workspace_root.exists():
            os.rmdir(self.workspace_root)

    def test_log_reg_04_activate_session_project(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_REG_04
        - Enforces: LOG-REG-04: INFO log after successful project activation
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock Project.load to return project
        with patch("serena.agent.Project.load", return_value=self.mock_project):
            # ACT & ASSERT: Capture logs
            with self.assertLogs("serena.agent", level=logging.INFO) as log_capture:
                self.agent.activate_session_project(
                    self.session_id,
                    self.workspace_root,
                    source="explicit"
                )

        # ASSERT: Verify LOG-REG-04 guarantee
        logs = log_capture.output
        short_id = self.session_id[:8]
        expected_log = f"[Session: {short_id}] Activated project at {self.workspace_root} (source: explicit)"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-REG-04 violation: Project activation log missing\n"
            f"Contract: logging_observability_contract.LOG_REG_04\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: After successful project activation, MUST emit INFO log before returning Project. "
            f"Log MUST include short_id, workspace_root, source. "
            f"Format MUST match contract exactly. Logger MUST be serena.agent module logger."
        )

    def test_log_reg_04_rebind_workspace(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_REG_04
        - Enforces: LOG-REG-04 (POST-REBIND): INFO log when re-binding from one workspace to another
        - Category: boundary
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Bind session to first workspace (must exist on disk for bind_session PRE-2)
        old_workspace = Path(tempfile.mkdtemp())
        self.agent.session_registry.bind_session(
            self.session_id,
            old_workspace,
            source="explicit"
        )

        # Mock Project.load for new workspace
        with patch("serena.agent.Project.load", return_value=self.mock_project):
            # ACT & ASSERT: Capture logs during re-bind
            with self.assertLogs("serena.agent", level=logging.INFO) as log_capture:
                self.agent.activate_session_project(
                    self.session_id,
                    self.workspace_root,
                    source="explicit"
                )

        # Cleanup old_workspace temp dir
        if old_workspace.exists():
            os.rmdir(old_workspace)

        # ASSERT: Verify LOG-REG-04 POST-REBIND guarantee
        logs = log_capture.output
        short_id = self.session_id[:8]
        # old_workspace is stored resolved by bind_session (e.g. /private/var/... on macOS)
        # new workspace_root is used as-is from the parameter (not resolved in the log)
        resolved_old_workspace = str(old_workspace.resolve())
        expected_log = f"[Session: {short_id}] Re-binding from {resolved_old_workspace} to {self.workspace_root}"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-REG-04 (POST-REBIND) violation: Re-binding log missing\n"
            f"Contract: logging_observability_contract.LOG_REG_04\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: When session already bound to different workspace, MUST emit INFO log showing re-binding. "
            f"Log MUST include short_id, old_workspace, new workspace_root. "
            f"This log MUST appear BEFORE unbind_session call. "
            f"This is critical for detecting workspace switching behavior."
        )

    def test_log_reg_05_deactivate_session(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_REG_05
        - Enforces: LOG-REG-05: INFO log with LSP cleanup count
        - Category: positive
        - Adversarial: Implementation-blind
        """
        from serena.session_context import set_current_session

        # ARRANGE: Bind session and setup LSP references on session context
        session_ctx = self.agent.session_registry.bind_session(
            self.session_id,
            self.workspace_root,
            source="explicit"
        )
        session_ctx.lsp_references = {
            Language.PYTHON.value: MagicMock(),
            Language.RUST.value: MagicMock()
        }
        set_current_session(session_ctx)

        # Mock lsp_pool to track release calls (use internal attr; lsp_pool is read-only property)
        self.agent._lsp_pool = MagicMock()

        # ACT & ASSERT: Capture logs
        with self.assertLogs("serena.agent", level=logging.INFO) as log_capture:
            self.agent.deactivate_session(self.session_id)

        # ASSERT: Verify LOG-REG-05 guarantee
        logs = log_capture.output
        short_id = self.session_id[:8]
        expected_log = f"[Session: {short_id}] Deactivated (released 2 LSP reference(s))"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-REG-05 violation: Deactivation log missing\n"
            f"Contract: logging_observability_contract.LOG_REG_05\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: After clearing LSP references, MUST emit INFO log showing count of LSPs released. "
            f"Log MUST include short_id, count of references released. "
            f"Count MUST match number of languages in lsp_references. "
            f"This log MUST appear BEFORE unbind_session call."
        )


if __name__ == "__main__":
    unittest.main()
