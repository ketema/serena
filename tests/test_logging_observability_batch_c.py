"""
Logging Observability Contract Tests — Batch C (Tiers 5+6+7)

CONTRACT: contracts/logging_observability_contract.py
CLAUSES: LOG-DISP-01 through LOG-DISP-02 (Tier 5: Tool Dispatch)
         LOG-SEC-01 through LOG-SEC-02 (Tier 6: Security Boundary)
         LOG-TMO-01 through LOG-TMO-03 (Tier 7: Infrastructure)
         LOG-RST-01 through LOG-RST-02 (Tier 7: RestartTool)

SCOPE:
  - Tier 5: src/serena/session_tool_dispatch.py (dispatch_tool, validate_path_for_session)
  - Tier 6: src/serena/path_validation.py (validate_path)
  - Tier 7: src/serena/lsp_timeout.py (LSPTimeoutManager)
  - Tier 7: src/serena/tools/symbol_tools.py (RestartLanguageServerTool)

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
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Target modules
from serena.session_tool_dispatch import SessionAwareToolDispatch, ToolCategory, SessionContextWrapper
from serena.path_validation import validate_path, PathBoundaryError
from serena.lsp_timeout import LSPTimeoutManager
from serena.tools.symbol_tools import RestartLanguageServerTool

# Test dependencies
from serena.session_registry import SessionRegistry
from serena.agent import SerenaAgent
from serena.project import Project


# =============================================================================
# TIER 5: Tool Dispatch — dispatch_tool()
# =============================================================================

class TestDispatchToolLogging(unittest.TestCase):
    """
    Tests for LOG-DISP-01 clause.

    TARGET: SessionAwareToolDispatch.dispatch_tool()
    LOGGER: serena.session_tool_dispatch
    """

    def setUp(self):
        """Setup dispatcher with mocked registry and dependencies."""
        self.registry = SessionRegistry()
        self.dispatcher = SessionAwareToolDispatch(self.registry)
        self.session_id = "test-session-12345678"
        self.workspace_root = Path(tempfile.mkdtemp())

        # Register session
        self.registry.bind_session(
            self.session_id,
            self.workspace_root,
            source="explicit"
        )

    def tearDown(self):
        """Cleanup temporary workspace directory."""
        if self.workspace_root.exists():
            os.rmdir(self.workspace_root)

    @patch("serena.session_tool_dispatch.determine_tool_category")
    @patch.object(SessionAwareToolDispatch, "_execute_tool")
    @patch.object(SessionAwareToolDispatch, "get_session_context")
    def test_log_disp_01_tool_dispatched(self, mock_get_ctx, mock_execute, mock_category):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_DISP_01
        - Enforces: LOG-DISP-01: DEBUG log with session/tool_name/category
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Setup mock context and category
        mock_ctx = MagicMock(spec=SessionContextWrapper)
        mock_ctx.has_active_project.return_value = True
        mock_get_ctx.return_value = mock_ctx
        mock_category.return_value = ToolCategory.PROJECT
        mock_execute.return_value = "success"

        tool_name = "find_symbol"
        short_id = self.session_id[:8]

        # ACT & ASSERT: Capture logs during dispatch_tool
        with self.assertLogs("serena.session_tool_dispatch", level=logging.DEBUG) as log_capture:
            self.dispatcher.dispatch_tool(
                self.session_id,
                tool_name,
                {"name_path": "test"}
            )

        # ASSERT: Verify LOG-DISP-01 guarantee
        logs = log_capture.output
        expected_log = (
            f"[Session: {short_id}] Dispatching tool '{tool_name}' "
            f"(category: {ToolCategory.PROJECT.value})"
        )

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-DISP-01 violation: Tool dispatch log missing\n"
            f"Contract: logging_observability_contract.LOG_DISP_01\n"
            f"EXPECTED: Exactly one DEBUG log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: dispatch_tool() MUST emit DEBUG log AFTER category determined, "
            f"BEFORE _execute_tool call. Format: "
            f"'[Session: {{short_id}}] Dispatching tool '{{tool_name}}' (category: {{category}})'"
        )

        # Verify log level is DEBUG
        matching_log = matching_logs[0]
        assert "DEBUG" in matching_log, (
            f"LOG-DISP-01 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_DISP_01\n"
            f"EXPECTED: DEBUG level\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.debug(), not logger.info() or logger.warning()"
        )


# =============================================================================
# TIER 5: Tool Dispatch — validate_path_for_session()
# =============================================================================

class TestValidatePathForSessionLogging(unittest.TestCase):
    """
    Tests for LOG-DISP-02 clause.

    TARGET: SessionAwareToolDispatch.validate_path_for_session()
    LOGGER: serena.session_tool_dispatch
    """

    def setUp(self):
        """Setup dispatcher with session and project."""
        self.registry = SessionRegistry()
        self.dispatcher = SessionAwareToolDispatch(self.registry)
        self.session_id = "test-session-abcdef12"
        self.workspace_root = Path(tempfile.mkdtemp())

        # Create a test file for validation
        self.test_file = self.workspace_root / "test.py"
        self.test_file.touch()

        # Register session with project
        self.registry.bind_session(
            self.session_id,
            self.workspace_root,
            source="explicit"
        )

    def tearDown(self):
        """Cleanup temporary workspace directory."""
        if self.test_file.exists():
            self.test_file.unlink()
        if self.workspace_root.exists():
            os.rmdir(self.workspace_root)

    @patch.object(SessionAwareToolDispatch, "get_session_context")
    def test_log_disp_02_path_validated(self, mock_get_ctx):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_DISP_02
        - Enforces: LOG-DISP-02: DEBUG log on successful validation
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Setup mock context with workspace_root
        mock_ctx = MagicMock(spec=SessionContextWrapper)
        mock_ctx.has_active_project.return_value = True
        mock_ctx.workspace_root = self.workspace_root
        mock_get_ctx.return_value = mock_ctx

        short_id = self.session_id[:8]

        # ACT & ASSERT: Capture logs during validate_path_for_session
        with self.assertLogs("serena.session_tool_dispatch", level=logging.DEBUG) as log_capture:
            resolved_path = self.dispatcher.validate_path_for_session(
                self.session_id,
                "test.py"
            )

        # ASSERT: Verify LOG-DISP-02 guarantee
        logs = log_capture.output
        # macOS path resolution: use str(resolved_path.resolve()) for comparison
        resolved_str = str(resolved_path.resolve())
        expected_log = f"[Session: {short_id}] Path validated: {resolved_str}"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-DISP-02 violation: Path validation log missing\n"
            f"Contract: logging_observability_contract.LOG_DISP_02\n"
            f"EXPECTED: Exactly one DEBUG log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: validate_path_for_session() MUST emit DEBUG log AFTER "
            f"validate_path() returns successfully. Format: "
            f"'[Session: {{short_id}}] Path validated: {{resolved_path}}'"
        )

        # Verify log level is DEBUG
        matching_log = matching_logs[0]
        assert "DEBUG" in matching_log, (
            f"LOG-DISP-02 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_DISP_02\n"
            f"EXPECTED: DEBUG level\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.debug(), not logger.info() or logger.warning()"
        )


# =============================================================================
# TIER 6: Security Boundary — validate_path()
# =============================================================================

class TestValidatePathLogging(unittest.TestCase):
    """
    Tests for LOG-SEC-01 and LOG-SEC-02 clauses.

    TARGET: validate_path()
    LOGGER: serena.path_validation
    """

    def setUp(self):
        """Setup workspace root and test paths."""
        self.workspace_root = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Cleanup temporary workspace directory."""
        # Cleanup may fail if broken symlink still exists - ignore
        import shutil
        if self.workspace_root.exists():
            try:
                shutil.rmtree(self.workspace_root)
            except OSError:
                pass

    def test_log_sec_01_boundary_violation(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_SEC_01
        - Enforces: LOG-SEC-01: WARNING on path boundary violation
        - Category: negative
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Path that escapes boundary via ..
        malicious_path = "../etc/passwd"

        # ACT & ASSERT: Capture logs during validate_path
        with self.assertLogs("serena.path_validation", level=logging.WARNING) as log_capture:
            with self.assertRaises(PathBoundaryError):
                validate_path(malicious_path, self.workspace_root)

        # ASSERT: Verify LOG-SEC-01 guarantee
        logs = log_capture.output
        expected_log = (
            f"[Security] Path boundary violation: '{malicious_path}' resolves outside "
            f"project root '{self.workspace_root.resolve()}'"
        )

        matching_logs = [log for log in logs if "[Security] Path boundary violation" in log]
        assert len(matching_logs) == 1, (
            f"LOG-SEC-01 violation: Boundary violation log missing\n"
            f"Contract: logging_observability_contract.LOG_SEC_01\n"
            f"EXPECTED: Exactly one WARNING log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: validate_path() MUST emit WARNING log BEFORE raising "
            f"PathBoundaryError when path escapes boundary. Format: "
            f"'[Security] Path boundary violation: '{{relative_path}}' resolves outside "
            f"project root '{{project_root}}'"
        )

        # Verify log level is WARNING
        matching_log = matching_logs[0]
        assert "WARNING" in matching_log, (
            f"LOG-SEC-01 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_SEC_01\n"
            f"EXPECTED: WARNING level\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.warning(), not logger.error() or logger.info()"
        )

    def test_log_sec_02_resolution_failure(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_SEC_02
        - Enforces: LOG-SEC-02: WARNING on path resolution failure
        - Category: negative
        - Adversarial: Implementation-blind

        NOTE: Uses mock to trigger OSError in Path.resolve() because macOS
        resolves broken symlinks without error (unlike Linux). Mocking the
        second resolve() call (on combined_path) is the only cross-platform
        way to exercise the except (OSError, RuntimeError) block.
        """
        # ARRANGE: Mock Path.resolve so the first call (project_root.resolve())
        # succeeds but the second call (combined_path.resolve()) raises OSError.
        # This reliably triggers the except block on all platforms.
        original_resolve = Path.resolve
        call_count = 0

        def mock_resolve(path_self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise OSError("Permission denied")
            return original_resolve(path_self, *args, **kwargs)

        # ACT & ASSERT: Capture logs during validate_path
        with patch.object(Path, 'resolve', new=mock_resolve):
            with self.assertLogs("serena.path_validation", level=logging.WARNING) as log_capture:
                with self.assertRaises(PathBoundaryError):
                    validate_path("some_file.py", self.workspace_root)

        # ASSERT: Verify LOG-SEC-02 guarantee
        logs = log_capture.output
        expected_prefix = "[Security] Path resolution failed: 'some_file.py'"

        matching_logs = [log for log in logs if expected_prefix in log]
        assert len(matching_logs) == 1, (
            f"LOG-SEC-02 violation: Resolution failure log missing\n"
            f"Contract: logging_observability_contract.LOG_SEC_02\n"
            f"EXPECTED: Exactly one WARNING log starting with '{expected_prefix}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: validate_path() MUST emit WARNING log BEFORE raising "
            f"PathBoundaryError when resolution fails (OSError/RuntimeError). Format: "
            f"'[Security] Path resolution failed: '{{relative_path}}' — {{error}}'"
        )

        # Verify log level is WARNING
        matching_log = matching_logs[0]
        assert "WARNING" in matching_log, (
            f"LOG-SEC-02 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_SEC_02\n"
            f"EXPECTED: WARNING level\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.warning(), not logger.error() or logger.info()"
        )


# =============================================================================
# TIER 7: Infrastructure — LSPTimeoutManager.start_monitoring()
# =============================================================================

class TestLSPTimeoutStartMonitoringLogging(unittest.TestCase):
    """
    Tests for LOG-TMO-01 clause.

    TARGET: LSPTimeoutManager.start_monitoring()
    LOGGER: serena.lsp_timeout
    """

    def setUp(self):
        """Setup timeout manager."""
        self.manager = LSPTimeoutManager(check_interval=1)

    def tearDown(self):
        """Cleanup: stop monitoring if active."""
        if self.manager.is_monitoring():
            self.manager.stop_monitoring()

    def test_log_tmo_01_monitor_started(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_TMO_01
        - Enforces: LOG-TMO-01: INFO log when monitoring starts
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ACT & ASSERT: Capture logs during start_monitoring
        with self.assertLogs("serena.lsp_timeout", level=logging.INFO) as log_capture:
            self.manager.start_monitoring()

        # ASSERT: Verify LOG-TMO-01 guarantee (INFO on start)
        logs = log_capture.output
        expected_log = "[LSP-Timeout] Monitoring started (interval: 1s)"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-TMO-01 violation: Monitor started log missing\n"
            f"Contract: logging_observability_contract.LOG_TMO_01\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: start_monitoring() MUST emit INFO log AFTER thread.start() "
            f"when monitoring actually starts. Format: "
            f"'[LSP-Timeout] Monitoring started (interval: {{interval}}s)'"
        )

        # Verify log level is INFO
        matching_log = matching_logs[0]
        assert "INFO" in matching_log, (
            f"LOG-TMO-01 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_TMO_01\n"
            f"EXPECTED: INFO level\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.info() for actual start, not logger.debug()"
        )

    def test_log_tmo_01_already_active(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_TMO_01
        - Enforces: LOG-TMO-01: DEBUG log when already monitoring
        - Category: boundary (idempotent)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Start monitoring first time
        self.manager.start_monitoring()

        # ACT & ASSERT: Capture logs during second start_monitoring
        with self.assertLogs("serena.lsp_timeout", level=logging.DEBUG) as log_capture:
            self.manager.start_monitoring()

        # ASSERT: Verify LOG-TMO-01 guarantee (DEBUG on no-op)
        logs = log_capture.output
        expected_log = "[LSP-Timeout] Monitoring already active, skipping start"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-TMO-01 violation: Already active log missing\n"
            f"Contract: logging_observability_contract.LOG_TMO_01\n"
            f"EXPECTED: Exactly one DEBUG log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: start_monitoring() MUST emit DEBUG log when already monitoring "
            f"(early return path). Format: "
            f"'[LSP-Timeout] Monitoring already active, skipping start'"
        )

        # Verify log level is DEBUG
        matching_log = matching_logs[0]
        assert "DEBUG" in matching_log, (
            f"LOG-TMO-01 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_TMO_01\n"
            f"EXPECTED: DEBUG level for no-op\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.debug() for no-op, not logger.info()"
        )


# =============================================================================
# TIER 7: Infrastructure — LSPTimeoutManager.stop_monitoring()
# =============================================================================

class TestLSPTimeoutStopMonitoringLogging(unittest.TestCase):
    """
    Tests for LOG-TMO-02 clause.

    TARGET: LSPTimeoutManager.stop_monitoring()
    LOGGER: serena.lsp_timeout
    """

    def setUp(self):
        """Setup timeout manager."""
        self.manager = LSPTimeoutManager(check_interval=1)

    def tearDown(self):
        """Cleanup: stop monitoring if active."""
        if self.manager.is_monitoring():
            self.manager.stop_monitoring()

    def test_log_tmo_02_monitor_stopped(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_TMO_02
        - Enforces: LOG-TMO-02: INFO log when monitoring stops
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Start monitoring first
        self.manager.start_monitoring()

        # ACT & ASSERT: Capture logs during stop_monitoring
        with self.assertLogs("serena.lsp_timeout", level=logging.INFO) as log_capture:
            self.manager.stop_monitoring()

        # ASSERT: Verify LOG-TMO-02 guarantee (INFO on stop)
        logs = log_capture.output
        expected_log = "[LSP-Timeout] Monitoring stopped"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-TMO-02 violation: Monitor stopped log missing\n"
            f"Contract: logging_observability_contract.LOG_TMO_02\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: stop_monitoring() MUST emit INFO log AFTER thread.join() "
            f"when monitoring actually stops. Format: "
            f"'[LSP-Timeout] Monitoring stopped'"
        )

        # Verify log level is INFO
        matching_log = matching_logs[0]
        assert "INFO" in matching_log, (
            f"LOG-TMO-02 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_TMO_02\n"
            f"EXPECTED: INFO level\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.info() for actual stop, not logger.debug()"
        )

    def test_log_tmo_02_not_active(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_TMO_02
        - Enforces: LOG-TMO-02: DEBUG log when not monitoring
        - Category: boundary (idempotent)
        - Adversarial: Implementation-blind
        """
        # ACT & ASSERT: Capture logs during stop_monitoring (never started)
        with self.assertLogs("serena.lsp_timeout", level=logging.DEBUG) as log_capture:
            self.manager.stop_monitoring()

        # ASSERT: Verify LOG-TMO-02 guarantee (DEBUG on no-op)
        logs = log_capture.output
        expected_log = "[LSP-Timeout] Monitoring not active, skipping stop"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-TMO-02 violation: Not active log missing\n"
            f"Contract: logging_observability_contract.LOG_TMO_02\n"
            f"EXPECTED: Exactly one DEBUG log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: stop_monitoring() MUST emit DEBUG log when not monitoring "
            f"(thread is None or not alive). Format: "
            f"'[LSP-Timeout] Monitoring not active, skipping stop'"
        )

        # Verify log level is DEBUG
        matching_log = matching_logs[0]
        assert "DEBUG" in matching_log, (
            f"LOG-TMO-02 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_TMO_02\n"
            f"EXPECTED: DEBUG level for no-op\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.debug() for no-op, not logger.info()"
        )


# =============================================================================
# TIER 7: Infrastructure — LSPTimeoutManager.check_and_reclaim()
# =============================================================================

class TestLSPTimeoutCheckAndReclaimLogging(unittest.TestCase):
    """
    Tests for LOG-TMO-03 clause.

    TARGET: LSPTimeoutManager.check_and_reclaim()
    LOGGER: serena.lsp_timeout
    """

    def setUp(self):
        """Setup timeout manager with mock callback."""
        self.manager = LSPTimeoutManager(check_interval=1)
        self.reclaimed_languages = []

        def mock_reclaim_callback(language: str):
            self.reclaimed_languages.append(language)

        self.manager.set_reclaim_callback(mock_reclaim_callback)

    def test_log_tmo_03_reclamation_logs(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_TMO_03
        - Enforces: LOG-TMO-03: INFO per reclaimed language + summary
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Touch languages in the past to make them idle
        past_time = datetime.now() - timedelta(seconds=10)
        self.manager.touch("python")
        self.manager.touch("typescript")

        # Manipulate last_used times directly to simulate idle
        # (accessing private attribute for test only)
        self.manager._last_used["python"] = past_time
        self.manager._last_used["typescript"] = past_time

        # Set timeouts to 5 seconds (so 10 seconds idle > 5 second timeout)
        self.manager._timeout_config["python"] = 5
        self.manager._timeout_config["typescript"] = 5

        # ACT & ASSERT: Capture logs during check_and_reclaim
        with self.assertLogs("serena.lsp_timeout", level=logging.INFO) as log_capture:
            reclaimed = self.manager.check_and_reclaim()

        # ASSERT: Verify both languages were reclaimed
        assert set(reclaimed) == {"python", "typescript"}, (
            f"Test setup failed: expected both languages reclaimed\n"
            f"ACTUAL: {reclaimed}"
        )

        logs = log_capture.output

        # ASSERT: Verify LOG-TMO-03 guarantee (per-language logs)
        for language in ["python", "typescript"]:
            expected_log_prefix = f"[LSP-Timeout] Reclaiming idle {language} LSP (idle:"
            matching_logs = [log for log in logs if expected_log_prefix in log]
            assert len(matching_logs) == 1, (
                f"LOG-TMO-03 violation: Per-language reclamation log missing for {language}\n"
                f"Contract: logging_observability_contract.LOG_TMO_03\n"
                f"EXPECTED: Exactly one INFO log starting with '{expected_log_prefix}'\n"
                f"ACTUAL: {len(matching_logs)} matching logs found\n"
                f"All logs: {logs}\n"
                f"GUIDANCE: check_and_reclaim() MUST emit INFO log BEFORE reclaim_callback "
                f"for each reclaimed language. Format: "
                f"'[LSP-Timeout] Reclaiming idle {{language}} LSP (idle: {{idle_time:.0f}}s, timeout: {{timeout}}s)'"
            )

        # ASSERT: Verify LOG-TMO-03 guarantee (summary log)
        expected_summary_prefix = "[LSP-Timeout] Reclaimed 2 idle LSP(s):"
        matching_summary = [log for log in logs if expected_summary_prefix in log]
        assert len(matching_summary) == 1, (
            f"LOG-TMO-03 violation: Summary log missing\n"
            f"Contract: logging_observability_contract.LOG_TMO_03\n"
            f"EXPECTED: Exactly one INFO summary log starting with '{expected_summary_prefix}'\n"
            f"ACTUAL: {len(matching_summary)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: check_and_reclaim() MUST emit INFO summary BEFORE returning reclaimed list. "
            f"Format: '[LSP-Timeout] Reclaimed {{count}} idle LSP(s): {{languages}}'"
        )

        # Verify summary contains both languages
        summary_log = matching_summary[0]
        assert "python" in summary_log and "typescript" in summary_log, (
            f"LOG-TMO-03 violation: Summary missing language names\n"
            f"Contract: logging_observability_contract.LOG_TMO_03\n"
            f"EXPECTED: Summary containing 'python' and 'typescript'\n"
            f"ACTUAL: {summary_log}\n"
            f"GUIDANCE: Summary log must list all reclaimed language names"
        )


# =============================================================================
# TIER 7: Infrastructure — RestartLanguageServerTool.apply() HTTP Mode
# =============================================================================

class TestRestartToolHTTPModeLogging(unittest.TestCase):
    """
    Tests for LOG-RST-01 clause.

    TARGET: RestartLanguageServerTool.apply()
    LOGGER: serena.tools.symbol_tools
    """

    def setUp(self):
        """Setup restart tool with mocked agent."""
        self.agent = MagicMock(spec=SerenaAgent)
        self.tool = RestartLanguageServerTool(self.agent)

    @patch("serena.tools.symbol_tools.get_transport_session_id")
    def test_log_rst_01_http_mode_blocked(self, mock_get_session_id):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_RST_01
        - Enforces: LOG-RST-01: INFO when blocked in HTTP mode
        - Category: negative (guard behavior)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: HTTP mode (session_id is not None)
        session_id = "http-session-12345678"
        mock_get_session_id.return_value = session_id
        short_id = session_id[:8]

        # ACT & ASSERT: Capture logs during apply
        with self.assertLogs("serena.tools.symbol_tools", level=logging.INFO) as log_capture:
            result = self.tool.apply()

        # ASSERT: Verify error message returned
        assert "disabled in HTTP mode" in result, (
            f"Test setup failed: expected HTTP mode error message\n"
            f"ACTUAL: {result}"
        )

        # ASSERT: Verify LOG-RST-01 guarantee
        logs = log_capture.output
        expected_log = f"[Tool] RestartLanguageServerTool: blocked in HTTP mode (session: {short_id})"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-RST-01 violation: HTTP mode block log missing\n"
            f"Contract: logging_observability_contract.LOG_RST_01\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: apply() MUST emit INFO log BEFORE returning error message "
            f"when HTTP mode detected. Format: "
            f"'[Tool] RestartLanguageServerTool: blocked in HTTP mode (session: {{short_id}})'"
        )

        # Verify log level is INFO
        matching_log = matching_logs[0]
        assert "INFO" in matching_log, (
            f"LOG-RST-01 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_RST_01\n"
            f"EXPECTED: INFO level\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.info(), not logger.warning() (guard working is expected behavior)"
        )

        # Verify reset_language_server was NOT called (HTTP mode guard worked)
        self.agent.reset_language_server.assert_not_called()


# =============================================================================
# TIER 7: Infrastructure — RestartLanguageServerTool.apply() STDIO Mode
# =============================================================================

class TestRestartToolSTDIOModeLogging(unittest.TestCase):
    """
    Tests for LOG-RST-02 clause.

    TARGET: RestartLanguageServerTool.apply()
    LOGGER: serena.tools.symbol_tools
    """

    def setUp(self):
        """Setup restart tool with mocked agent."""
        self.agent = MagicMock(spec=SerenaAgent)
        self.tool = RestartLanguageServerTool(self.agent)

    @patch("serena.tools.symbol_tools.get_transport_session_id")
    def test_log_rst_02_stdio_restart(self, mock_get_session_id):
        """
        CONTRACT TRACEABILITY:
        - Contract: logging_observability_contract.LOG_RST_02
        - Enforces: LOG-RST-02: INFO before STDIO restart
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: STDIO mode (session_id is None)
        mock_get_session_id.return_value = None

        # ACT & ASSERT: Capture logs during apply
        with self.assertLogs("serena.tools.symbol_tools", level=logging.INFO) as log_capture:
            result = self.tool.apply()

        # ASSERT: Verify success message returned
        assert "successfully restarted" in result, (
            f"Test setup failed: expected success message\n"
            f"ACTUAL: {result}"
        )

        # ASSERT: Verify LOG-RST-02 guarantee
        logs = log_capture.output
        expected_log = "[Tool] RestartLanguageServerTool: restarting LSP (STDIO mode)"

        matching_logs = [log for log in logs if expected_log in log]
        assert len(matching_logs) == 1, (
            f"LOG-RST-02 violation: STDIO restart log missing\n"
            f"Contract: logging_observability_contract.LOG_RST_02\n"
            f"EXPECTED: Exactly one INFO log containing '{expected_log}'\n"
            f"ACTUAL: {len(matching_logs)} matching logs found\n"
            f"All logs: {logs}\n"
            f"GUIDANCE: apply() MUST emit INFO log BEFORE calling reset_language_server() "
            f"when STDIO mode detected. Format: "
            f"'[Tool] RestartLanguageServerTool: restarting LSP (STDIO mode)'"
        )

        # Verify log level is INFO
        matching_log = matching_logs[0]
        assert "INFO" in matching_log, (
            f"LOG-RST-02 violation: Incorrect log level\n"
            f"Contract: logging_observability_contract.LOG_RST_02\n"
            f"EXPECTED: INFO level\n"
            f"ACTUAL: {matching_log}\n"
            f"GUIDANCE: Use logger.info(), not logger.debug()"
        )

        # Verify reset_language_server WAS called (STDIO mode allows restart)
        self.agent.reset_language_server.assert_called_once()


if __name__ == "__main__":
    unittest.main()
