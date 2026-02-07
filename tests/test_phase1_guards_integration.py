"""
Integration tests for Phase 1 Guards (REQ-2026-005).

Tests the REAL production classes with minimal mocking.

Contract Authority: contracts/lsp_lifecycle_authority_contract.py
Enforces: RestartToolGuardContract, PoolIntegrityContract
"""

import unittest
from unittest.mock import MagicMock, patch

from contracts.lsp_lifecycle_authority_contract import PoolIntegrityError
from serena.agent import SerenaAgent
from serena.global_lsp_pool import GlobalLanguageServerPool
from serena.session_registry import SessionRegistry
from serena.tools.symbol_tools import RestartLanguageServerTool


class TestRestartToolGuard(unittest.TestCase):
    """
    Integration tests for RestartLanguageServerTool HTTP guard.

    Contract: RestartToolGuardContract
    File: contracts/lsp_lifecycle_authority_contract.py (lines 313-354)
    """

    def setUp(self):
        """Setup minimal agent with real RestartLanguageServerTool."""
        # Create a minimal agent mock (just what's needed for tool construction)
        self.mock_agent = MagicMock(spec=SerenaAgent)
        self.mock_agent.reset_language_server = MagicMock()

        # Create REAL RestartLanguageServerTool with real agent reference
        self.tool = RestartLanguageServerTool(agent=self.mock_agent)

    def test_post_rtg_01_http_mode_returns_error_message(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: RestartToolGuardContract.apply_restart_tool()
        - Enforces: POST-RTG-01: In HTTP mode, returns error message explaining tool is disabled
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Simulate HTTP mode by setting transport session ID
        with patch("serena.tools.symbol_tools.get_transport_session_id", create=True, return_value="test-session-123"):

            # ACT: Invoke tool in HTTP mode
            result = self.tool.apply()

            # ASSERT: POST-RTG-01 - returns error message
            assert isinstance(result, str), (
                f"POST-RTG-01 violation: Tool did not return string in HTTP mode\n"
                f"Contract: RestartToolGuardContract.apply_restart_tool() POST-RTG-01\n"
                f"EXPECTED: Error message string explaining tool is disabled\n"
                f"ACTUAL: {type(result).__name__}\n"
                f"GUIDANCE: In HTTP mode, tool MUST return descriptive error message. "
                f"Check get_transport_session_id() result - non-None indicates HTTP mode."
            )

            assert "disabled" in result.lower() or "http" in result.lower() or "not available" in result.lower(), (
                f"POST-RTG-01 violation: Error message does not explain HTTP mode restriction\n"
                f"Contract: RestartToolGuardContract.apply_restart_tool() POST-RTG-01\n"
                f"EXPECTED: Message explaining tool is disabled in HTTP mode\n"
                f"ACTUAL: {result}\n"
                f"GUIDANCE: Error message MUST explicitly mention HTTP mode or multi-client restriction. "
                f"User needs to understand WHY tool is unavailable."
            )

    def test_inv_rtg_01_http_mode_never_calls_reset(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: RestartToolGuardContract.apply_restart_tool()
        - Enforces: INV-RTG-01: In HTTP mode, tool NEVER calls reset_language_server()
        - Category: invariant
        - Adversarial: Implementation-blind
        """
        # ARRANGE: HTTP mode, reset_language_server is spy
        with patch("serena.tools.symbol_tools.get_transport_session_id", create=True, return_value="test-session-123"):

            # ACT: Invoke tool
            self.tool.apply()

            # ASSERT: INV-RTG-01 - reset_language_server NOT called
            assert not self.mock_agent.reset_language_server.called, (
                f"INV-RTG-01 violation: Tool called reset_language_server() in HTTP mode\n"
                f"Contract: RestartToolGuardContract.apply_restart_tool() INV-RTG-01\n"
                f"EXPECTED: reset_language_server() NOT called (call_count == 0)\n"
                f"ACTUAL: reset_language_server() called {self.mock_agent.reset_language_server.call_count} times\n"
                f"GUIDANCE: HTTP mode MUST guard against ANY call to reset_language_server(). "
                f"Pool-wide restart violates isolation in multi-client HTTP mode. "
                f"Implementation MUST detect HTTP mode before calling reset_language_server()."
            )

    def test_post_rtg_03_stdio_mode_preserves_restart_behavior(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: RestartToolGuardContract.apply_restart_tool()
        - Enforces: POST-RTG-03: In STDIO mode, existing restart behavior preserved
        - Category: positive (backward compatibility)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: STDIO mode (transport session ID is None)
        with patch("serena.tools.symbol_tools.get_transport_session_id", create=True, return_value=None):

            # ACT: Invoke tool
            result = self.tool.apply()

            # ASSERT: POST-RTG-03 - reset_language_server called in STDIO mode
            assert self.mock_agent.reset_language_server.called, (
                f"POST-RTG-03 violation: Tool did not call reset_language_server() in STDIO mode\n"
                f"Contract: RestartToolGuardContract.apply_restart_tool() POST-RTG-03\n"
                f"EXPECTED: reset_language_server() called (existing behavior preserved)\n"
                f"ACTUAL: reset_language_server() call_count == {self.mock_agent.reset_language_server.call_count}\n"
                f"GUIDANCE: STDIO mode (get_transport_session_id() == None) MUST preserve existing restart behavior. "
                f"Backward compatibility requires unconditional reset_language_server() call in STDIO."
            )

            # Also verify success result
            assert "success" in result.lower() or result == "Success", (
                f"POST-RTG-03 violation: STDIO mode did not return success result\n"
                f"Contract: RestartToolGuardContract.apply_restart_tool() POST-RTG-03\n"
                f"EXPECTED: Success message indicating restart completed\n"
                f"ACTUAL: {result}\n"
                f"GUIDANCE: STDIO mode MUST return success confirmation after reset_language_server() completes."
            )

    def test_errors_rtg_01_http_mode_returns_not_raises(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: RestartToolGuardContract.apply_restart_tool()
        - Enforces: ERRORS-RTG-01: Returns error string (does not raise) in HTTP mode
        - Category: error
        - Adversarial: Implementation-blind
        """
        # ARRANGE: HTTP mode
        with patch("serena.tools.symbol_tools.get_transport_session_id", create=True, return_value="test-session-456"):

            # ACT & ASSERT: Tool returns, does not raise
            try:
                result = self.tool.apply()
                assert isinstance(result, str), (
                    f"ERRORS-RTG-01 violation: Tool did not return string\n"
                    f"Contract: RestartToolGuardContract.apply_restart_tool() ERRORS-RTG-01\n"
                    f"EXPECTED: String error message (no exception)\n"
                    f"ACTUAL: {type(result).__name__}\n"
                    f"GUIDANCE: HTTP mode MUST return error string, NOT raise exception. "
                    f"MCP protocol expects tool result, not exception."
                )
            except Exception as e:
                self.fail(
                    f"ERRORS-RTG-01 violation: Tool raised exception in HTTP mode\n"
                    f"Contract: RestartToolGuardContract.apply_restart_tool() ERRORS-RTG-01\n"
                    f"EXPECTED: Error string returned (no exception)\n"
                    f"ACTUAL: {type(e).__name__}: {e}\n"
                    f"GUIDANCE: HTTP mode MUST NOT raise exceptions. "
                    f"Return descriptive error string instead."
                )


class TestPoolIntegrityGuard(unittest.TestCase):
    """
    Integration tests for reset_language_server() pool integrity guard.

    Contract: PoolIntegrityContract
    File: contracts/lsp_lifecycle_authority_contract.py (lines 363-410)
    """

    def setUp(self):
        """Setup minimal agent with real SessionRegistry, bypassing heavy __init__."""
        # Use object.__new__ to create SerenaAgent without calling __init__
        # This avoids the heavy constructor (config reading, ToolRegistry, GUI, logging)
        # while allowing us to test the REAL reset_language_server() method
        self.agent = object.__new__(SerenaAgent)
        self.agent._session_registry = SessionRegistry()
        self.agent._lsp_pool = MagicMock(spec=GlobalLanguageServerPool)

    def test_post_pi_01_http_mode_active_sessions_blocks_replacement(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: PoolIntegrityContract.guarded_reset_language_server()
        - Enforces: POST-PI-01: If active sessions exist → pool NOT replaced, error returned
        - Category: negative (guard enforcement)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: HTTP mode with active session
        with patch("serena.agent.get_transport_session_id", create=True, return_value="test-session-789"):
            # Create active session in REAL SessionRegistry
            # workspace_root=None is valid per INV-B1-02 (HTTP mode before activate_project)
            self.agent._session_registry.bind_session(
                session_id="test-session-789",
                workspace_root=None,
                source="explicit"
            )

            # Save original pool reference for verification
            original_pool_id = id(self.agent._lsp_pool)

            # ACT & ASSERT: reset_language_server raises PoolIntegrityError
            with self.assertRaises(PoolIntegrityError) as ctx:
                self.agent.reset_language_server()

            # ASSERT: POST-PI-01 - pool NOT replaced
            assert id(self.agent._lsp_pool) == original_pool_id, (
                f"POST-PI-01 violation: Pool replaced despite active sessions\n"
                f"Contract: PoolIntegrityContract.guarded_reset_language_server() POST-PI-01\n"
                f"EXPECTED: Pool reference unchanged (id == {original_pool_id})\n"
                f"ACTUAL: Pool reference changed (id == {id(self.agent._lsp_pool)})\n"
                f"GUIDANCE: HTTP mode with active sessions MUST NOT replace pool. "
                f"Check SessionRegistry.get_session_overview()['total_count'] before replacement. "
                f"Raise PoolIntegrityError if active_session_count > 0."
            )

            # Verify error message quality
            error_msg = str(ctx.exception)
            assert "active sessions" in error_msg.lower(), (
                f"ERRORS-PI-01 violation: Error message does not explain active sessions\n"
                f"Contract: PoolIntegrityContract.guarded_reset_language_server() ERRORS-PI-01\n"
                f"EXPECTED: Error explaining pool replacement blocked due to active sessions\n"
                f"ACTUAL: {error_msg}\n"
                f"GUIDANCE: PoolIntegrityError message MUST mention active session count and integrity violation."
            )

    def test_inv_pi_01_pool_never_replaced_while_sessions_active(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: PoolIntegrityContract.guarded_reset_language_server()
        - Enforces: INV-PI-01: Pool reference NEVER replaced while sessions active
        - Category: invariant
        - Adversarial: Implementation-blind
        """
        # ARRANGE: HTTP mode with 2 active sessions
        with patch("serena.agent.get_transport_session_id", create=True, return_value="test-session-multi"):
            # workspace_root=None is valid per INV-B1-02 (HTTP mode before activate_project)
            self.agent._session_registry.bind_session(
                session_id="session-1",
                workspace_root=None,
                source="explicit"
            )
            self.agent._session_registry.bind_session(
                session_id="session-2",
                workspace_root=None,
                source="explicit"
            )

            original_pool_id = id(self.agent._lsp_pool)

            # ACT: Attempt replacement
            try:
                self.agent.reset_language_server()
            except PoolIntegrityError:
                pass  # Expected

            # ASSERT: INV-PI-01 - pool reference unchanged
            assert id(self.agent._lsp_pool) == original_pool_id, (
                f"INV-PI-01 violation: Pool replaced while 2 sessions active\n"
                f"Contract: PoolIntegrityContract.guarded_reset_language_server() INV-PI-01\n"
                f"EXPECTED: Pool reference preserved (id == {original_pool_id})\n"
                f"ACTUAL: Pool replaced (id == {id(self.agent._lsp_pool)})\n"
                f"GUIDANCE: INV-PI-01 is ABSOLUTE - ANY active session count > 0 MUST prevent replacement. "
                f"This invariant protects multi-client HTTP mode from catastrophic session loss. "
                f"Implementation MUST check SessionRegistry.get_session_overview()['total_count'] == 0."
            )

    def test_post_pi_02_no_active_sessions_allows_replacement(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: PoolIntegrityContract.guarded_reset_language_server()
        - Enforces: POST-PI-02: If no active sessions → pool replacement proceeds
        - Category: positive (clean shutdown)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: HTTP mode with NO active sessions
        with patch("serena.agent.get_transport_session_id", create=True, return_value="test-session-clean"):
            # Ensure no sessions
            assert self.agent._session_registry.get_session_overview()["total_count"] == 0

            original_pool_id = id(self.agent._lsp_pool)

            # ACT: reset_language_server with no active sessions
            self.agent.reset_language_server()

            # ASSERT: POST-PI-02 - pool replaced (new reference)
            assert id(self.agent._lsp_pool) != original_pool_id, (
                f"POST-PI-02 violation: Pool NOT replaced despite no active sessions\n"
                f"Contract: PoolIntegrityContract.guarded_reset_language_server() POST-PI-02\n"
                f"EXPECTED: New pool reference (id != {original_pool_id})\n"
                f"ACTUAL: Pool reference unchanged (id == {id(self.agent._lsp_pool)})\n"
                f"GUIDANCE: When SessionRegistry.get_session_overview()['total_count'] == 0, "
                f"pool replacement MUST proceed. This enables clean shutdown and restart scenarios. "
                f"Verify no sessions exist before blocking replacement."
            )

    def test_errors_pi_02_stdio_mode_proceeds_with_warning(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: PoolIntegrityContract.guarded_reset_language_server()
        - Enforces: ERRORS-PI-02: STDIO mode proceeds with deprecation warning
        - Category: error (backward compatibility)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: STDIO mode (transport session ID is None)
        with patch("serena.agent.get_transport_session_id", create=True, return_value=None):
            original_pool_id = id(self.agent._lsp_pool)

            # Mock logger to verify warning
            with patch("serena.agent.log") as mock_logger:

                # ACT: reset_language_server in STDIO mode
                self.agent.reset_language_server()

                # ASSERT: Pool replaced (backward compat)
                assert id(self.agent._lsp_pool) != original_pool_id, (
                    f"ERRORS-PI-02 violation: Pool NOT replaced in STDIO mode\n"
                    f"Contract: PoolIntegrityContract.guarded_reset_language_server() ERRORS-PI-02\n"
                    f"EXPECTED: Pool replaced (backward compatibility)\n"
                    f"ACTUAL: Pool unchanged (id == {original_pool_id})\n"
                    f"GUIDANCE: STDIO mode (get_transport_session_id() == None) MUST proceed with pool replacement. "
                    f"Backward compatibility requires unconditional replacement in STDIO. "
                    f"Log deprecation warning at WARN level for monitoring."
                )

                # Verify deprecation warning logged
                assert mock_logger.warning.called, (
                    f"ERRORS-PI-02 violation: No deprecation warning logged in STDIO mode\n"
                    f"Contract: PoolIntegrityContract.guarded_reset_language_server() ERRORS-PI-02\n"
                    f"EXPECTED: logger.warning() called with deprecation message\n"
                    f"ACTUAL: logger.warning() call_count == {mock_logger.warning.call_count}\n"
                    f"GUIDANCE: STDIO mode MUST log deprecation warning. "
                    f"Warning enables monitoring and migration to HTTP mode. "
                    f"Log at WARN level with message explaining STDIO-specific behavior."
                )

    def test_post_pi_03_http_mode_active_sessions_no_replacement(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: PoolIntegrityContract.guarded_reset_language_server()
        - Enforces: POST-PI-03: If active sessions and HTTP mode → pool NOT replaced
        - Category: positive (combined condition)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: HTTP mode + 1 active session
        with patch("serena.agent.get_transport_session_id", create=True, return_value="test-session-combined"):
            # workspace_root=None is valid per INV-B1-02 (HTTP mode before activate_project)
            self.agent._session_registry.bind_session(
                session_id="test-session-combined",
                workspace_root=None,
                source="explicit"
            )

            original_pool_id = id(self.agent._lsp_pool)

            # ACT & ASSERT: Raises PoolIntegrityError
            with self.assertRaises(PoolIntegrityError):
                self.agent.reset_language_server()

            # ASSERT: POST-PI-03 - pool NOT replaced
            assert id(self.agent._lsp_pool) == original_pool_id, (
                f"POST-PI-03 violation: Pool replaced in HTTP mode with active sessions\n"
                f"Contract: PoolIntegrityContract.guarded_reset_language_server() POST-PI-03\n"
                f"EXPECTED: Pool unchanged (id == {original_pool_id})\n"
                f"ACTUAL: Pool replaced (id == {id(self.agent._lsp_pool)})\n"
                f"GUIDANCE: Combined condition (HTTP mode AND active_sessions > 0) MUST prevent replacement. "
                f"Check BOTH get_transport_session_id() != None AND "
                f"SessionRegistry.get_session_overview()['total_count'] > 0."
            )


if __name__ == "__main__":
    unittest.main()
