"""
RED Phase Tests for CALLER-INV-1 Contract Violation Fix

Contract Under Test: SymbolRetrieverCallerContract (lines 694-723)
System Under Test: LanguageServerSymbolRetriever.get_root_path()

This test validates that the caller contract invariant CALLER-INV-1 is satisfied:
"Every call to a path-resolving SolidLanguageServer method MUST pass the
current session's workspace_root (from get_active_project_or_raise().project_root),
NEVER the LSP's repository_root_path."

The test is BLIND to implementation — it validates behavior from contract only.
"""

import unittest
from unittest.mock import MagicMock
from serena.symbol import LanguageServerSymbolRetriever


class TestCallerInv1GetRootPath(unittest.TestCase):
    """
    Test suite validating SymbolRetrieverCallerContract.get_workspace_root()
    implementation in LanguageServerSymbolRetriever.get_root_path().
    """

    def test_returns_session_workspace_not_lsp_root_with_explicit_lsp(self):
        """
        REQ-1 (CALLER-INV-1): get_root_path() MUST return session's workspace_root,
        NOT the LSP's repository_root_path.

        Contract: CALLER-INV-1 (lines 698-701)
        """
        # ARRANGE: Mock agent with session workspace = "/project-B"
        mock_agent = MagicMock()
        mock_project = MagicMock()
        mock_project.project_root = "/project-B"
        mock_agent.get_active_project_or_raise.return_value = mock_project

        # ARRANGE: Mock LSP with different repository_root_path = "/project-A"
        mock_lsp = MagicMock()
        mock_lsp.repository_root_path = "/project-A"

        # ARRANGE: Create retriever with explicit LSP (the critical scenario)
        retriever = LanguageServerSymbolRetriever(
            agent=mock_agent,
            language_server=mock_lsp
        )

        # ACT: Call get_root_path()
        actual_root = retriever.get_root_path()

        # ASSERT: MUST return session's workspace, NOT LSP's frozen root
        expected_root = "/project-B"

        assert actual_root == expected_root, (
            f"CALLER-INV-1 VIOLATION DETECTED\n"
            f"\n"
            f"TEST: test_returns_session_workspace_not_lsp_root_with_explicit_lsp\n"
            f"WHY: Contract clause CALLER-INV-1 requires get_root_path() to return "
            f"the session's workspace_root (from agent.get_active_project_or_raise().project_root), "
            f"NEVER the LSP's repository_root_path.\n"
            f"\n"
            f"EXPECTED: get_root_path() returns session's workspace_root = '/project-B'\n"
            f"ACTUAL: get_root_path() returned '{actual_root}'\n"
            f"\n"
            f"GUIDANCE (BEHAVIORAL):\n"
            f"- get_root_path() MUST call agent.get_active_project_or_raise().project_root\n"
            f"- get_root_path() MUST return that exact string value\n"
            f"- get_root_path() MUST NOT use language_server.repository_root_path\n"
            f"- This ensures all 5 call sites (symbol.py:537,583,646,669 + code_editor.py:247) "
            f"pass the CURRENT session's workspace to LSP methods, not a frozen historical root.\n"
            f"\n"
            f"Contract Reference: contracts/solidlsp_path_resolution_contract.py:698-701"
        )

    def test_return_value_equals_project_root_postcondition(self):
        """
        REQ-2 (POST-CW-2): get_root_path() return value MUST ALWAYS equal
        agent.get_active_project_or_raise().project_root.

        Contract: POST-CW-2 (line 712)
        """
        # ARRANGE: Mock agent with session workspace = "/workspace/myproject"
        mock_agent = MagicMock()
        mock_project = MagicMock()
        mock_project.project_root = "/workspace/myproject"
        mock_agent.get_active_project_or_raise.return_value = mock_project

        # ARRANGE: Mock LSP with different root (should be ignored)
        mock_lsp = MagicMock()
        mock_lsp.repository_root_path = "/some/other/path"

        # ARRANGE: Create retriever
        retriever = LanguageServerSymbolRetriever(
            agent=mock_agent,
            language_server=mock_lsp
        )

        # ACT: Call get_root_path()
        actual_root = retriever.get_root_path()

        # ASSERT: Return value MUST exactly equal project_root
        expected_root = "/workspace/myproject"

        assert actual_root == expected_root, (
            f"POST-CW-2 VIOLATION DETECTED\n"
            f"\n"
            f"TEST: test_return_value_equals_project_root_postcondition\n"
            f"WHY: Contract postcondition POST-CW-2 requires get_root_path() return value "
            f"to ALWAYS equal agent.get_active_project_or_raise().project_root.\n"
            f"\n"
            f"EXPECTED: get_root_path() returns '/workspace/myproject' "
            f"(exact value from agent.get_active_project_or_raise().project_root)\n"
            f"ACTUAL: get_root_path() returned '{actual_root}'\n"
            f"\n"
            f"GUIDANCE (BEHAVIORAL):\n"
            f"- get_root_path() MUST delegate to agent.get_active_project_or_raise().project_root\n"
            f"- get_root_path() MUST return that value UNCHANGED (no transformations)\n"
            f"- This postcondition applies regardless of whether language_server is provided or None\n"
            f"\n"
            f"Contract Reference: contracts/solidlsp_path_resolution_contract.py:712"
        )

    def test_returns_project_root_when_no_explicit_lsp_provided(self):
        """
        REQ-3 (Consistency): When NO explicit language_server is provided
        (language_server=None), get_root_path() MUST still return
        agent.get_active_project_or_raise().project_root.

        Contract: INV CALLER-INV-1 (line 714) — session's workspace, always
        """
        # ARRANGE: Mock agent with session workspace = "/home/user/project"
        mock_agent = MagicMock()
        mock_project = MagicMock()
        mock_project.project_root = "/home/user/project"
        mock_agent.get_active_project_or_raise.return_value = mock_project

        # ARRANGE: Create retriever with NO explicit language_server
        retriever = LanguageServerSymbolRetriever(
            agent=mock_agent,
            language_server=None  # No explicit LSP provided
        )

        # ACT: Call get_root_path()
        actual_root = retriever.get_root_path()

        # ASSERT: MUST return session's workspace_root
        expected_root = "/home/user/project"

        assert actual_root == expected_root, (
            f"CONSISTENCY VIOLATION (CALLER-INV-1 via POST-CW-2)\n"
            f"\n"
            f"TEST: test_returns_project_root_when_no_explicit_lsp_provided\n"
            f"WHY: Contract invariant CALLER-INV-1 requires get_root_path() to ALWAYS "
            f"return session's workspace_root, regardless of whether an explicit language_server "
            f"is provided. Postcondition POST-CW-2 requires return value to equal "
            f"agent.get_active_project_or_raise().project_root.\n"
            f"\n"
            f"EXPECTED: get_root_path() returns '/home/user/project' "
            f"(from agent.get_active_project_or_raise().project_root)\n"
            f"ACTUAL: get_root_path() returned '{actual_root}'\n"
            f"\n"
            f"GUIDANCE (BEHAVIORAL):\n"
            f"- get_root_path() behavior MUST be identical whether language_server is "
            f"provided or None\n"
            f"- ALWAYS delegate to agent.get_active_project_or_raise().project_root\n"
            f"- NEVER use language_server.repository_root_path, even if language_server exists\n"
            f"- This ensures consistent session-aware path resolution across all call sites\n"
            f"\n"
            f"Contract Reference: contracts/solidlsp_path_resolution_contract.py:698-701,712,714"
        )

    def test_multiple_calls_reflect_current_session_not_cached_value(self):
        """
        REQ-1 (CALLER-INV-1 + Dynamic Behavior): get_root_path() MUST return
        the CURRENT session's workspace_root on EVERY call, not a cached value.

        Contract: CALLER-INV-1 (line 700) — "current session's workspace_root"

        This validates that get_root_path() is session-aware and dynamic.
        """
        # ARRANGE: Mock agent with initial workspace = "/project-A"
        mock_agent = MagicMock()
        mock_project_a = MagicMock()
        mock_project_a.project_root = "/project-A"
        mock_agent.get_active_project_or_raise.return_value = mock_project_a

        # ARRANGE: Mock LSP (should be ignored)
        mock_lsp = MagicMock()
        mock_lsp.repository_root_path = "/lsp-root"

        # ARRANGE: Create retriever
        retriever = LanguageServerSymbolRetriever(
            agent=mock_agent,
            language_server=mock_lsp
        )

        # ACT: First call
        first_call_root = retriever.get_root_path()

        # ASSERT: First call returns current session's workspace
        assert first_call_root == "/project-A", (
            f"CALLER-INV-1 VIOLATION (First Call)\n"
            f"\n"
            f"TEST: test_multiple_calls_reflect_current_session_not_cached_value\n"
            f"WHY: First call to get_root_path() must return current session's workspace_root.\n"
            f"\n"
            f"EXPECTED: '/project-A'\n"
            f"ACTUAL: '{first_call_root}'\n"
            f"\n"
            f"Contract Reference: contracts/solidlsp_path_resolution_contract.py:700"
        )

        # ARRANGE: Simulate session change — agent now points to different project
        mock_project_b = MagicMock()
        mock_project_b.project_root = "/project-B"
        mock_agent.get_active_project_or_raise.return_value = mock_project_b

        # ACT: Second call (after session change)
        second_call_root = retriever.get_root_path()

        # ASSERT: Second call MUST reflect NEW session's workspace (not cached)
        assert second_call_root == "/project-B", (
            f"CALLER-INV-1 VIOLATION (Dynamic Behavior)\n"
            f"\n"
            f"TEST: test_multiple_calls_reflect_current_session_not_cached_value\n"
            f"WHY: Contract clause CALLER-INV-1 requires get_root_path() to return "
            f"the 'CURRENT session's workspace_root'. After session changes from "
            f"project-A to project-B, get_root_path() MUST reflect the NEW session, "
            f"not return a cached value from the old session.\n"
            f"\n"
            f"EXPECTED: get_root_path() returns NEW session's workspace = '/project-B'\n"
            f"ACTUAL: get_root_path() returned '{second_call_root}' "
            f"(appears to be returning cached value or LSP root)\n"
            f"\n"
            f"GUIDANCE (BEHAVIORAL):\n"
            f"- get_root_path() MUST call agent.get_active_project_or_raise().project_root "
            f"on EVERY invocation\n"
            f"- get_root_path() MUST NOT cache the workspace_root value in instance state\n"
            f"- get_root_path() MUST NOT use language_server.repository_root_path\n"
            f"- This ensures all 5 call sites always use the CURRENT session's workspace, "
            f"supporting multi-project workflows where sessions switch between projects.\n"
            f"\n"
            f"Contract Reference: contracts/solidlsp_path_resolution_contract.py:700 "
            f"('current session's workspace_root')"
        )


if __name__ == "__main__":
    unittest.main()
