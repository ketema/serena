"""
Agent Session Activation Tests (REQ-4b)

Contract Reference: contracts/mcp_factory_activation_contract.py
Tests SerenaAgent._activate_project() session binding behavior.

CONTRACT TRACEABILITY:
- Contract: MCPFactoryActivationContract.activate_project_for_mcp_session()
- Note: Tests apply to SerenaAgent._activate_project() which shares session binding logic
- PRE-1: self.agent is not None (implicit - agent method)
- PRE-2: self.agent._current_session_id is not None (session exists) OR None (anonymous fallback)
- POST-1: SessionRegistry.bind_session(session_id, workspace_root) called
- POST-2: SessionRegistry.get_session(session_id) returns SessionContext
- POST-3: SessionContext.workspace_root == project.project_root.resolve()
- INV-1: Only one workspace bound per session at a time
- INV-2: Binding to same workspace is idempotent (no-op)
- INV-3: Binding to different workspace unbinds previous first
- INV-5: Other sessions unaffected by this activation

Theater Prevention (CL12 / CLAUDE.md):
- Assertions verify ACTUAL registry state, NOT mock call counts
- Tests verify observable POST conditions, NOT implementation details
- Error messages describe WHAT behavior is expected, NOT HOW to implement
- Exact session_id values verified (deterministic)
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from serena.agent import SerenaAgent
from serena.config.serena_config import LanguageBackend
from serena.session_registry import SessionRegistry


@pytest.fixture
def mock_serena_config(tmp_path: Path):
    """
    Mock SerenaConfig following established pattern.

    Contract: PRE for _activate_project requires valid project
    """
    config = MagicMock()

    # Mock config attributes needed by SerenaAgent.__init__
    config.log_level = logging.INFO
    config.config_file_path = tmp_path / "serena_config.yml"
    config.project_names = ["test_project", "other_project"]
    config.gui_log_window_enabled = False
    config.language_backend = LanguageBackend.LSP
    config.token_count_estimator = "CHAR_COUNT"
    config.web_dashboard = False
    config.modes = []

    # Create workspace directories
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()
    other_workspace = tmp_path / "other_workspace"
    other_workspace.mkdir()

    # Mock project objects
    project = MagicMock()
    project.project_name = "test_project"
    project.project_root = workspace

    other_project = MagicMock()
    other_project.project_name = "other_project"
    other_project.project_root = other_workspace

    # get_project(name) returns project or raises
    def get_project_mock(name: str):
        if name == "test_project":
            return project
        elif name == "other_project":
            return other_project
        from serena.agent import ProjectNotFoundError

        raise ProjectNotFoundError(f"Project '{name}' not found")

    config.get_project = MagicMock(side_effect=get_project_mock)

    return config, workspace, other_workspace


class TestAgentSessionActivation:
    """
    Tests for SerenaAgent._activate_project() session binding behavior.

    Contract Reference: contracts/mcp_factory_activation_contract.py::MCPFactoryActivationContract
    REQ-4b: Agent uses session-aware activation when MCP session exists
    """

    def test_post_mcp_session_uses_session_id_not_random_uuid(self, mock_serena_config):
        """
        CONTRACT TRACEABILITY:
        - Contract: MCPFactoryActivationContract._activate_project()
        - Enforces: POST-2: SessionRegistry.get_session(session_id) returns SessionContext
        - Category: positive
        - Adversarial: Implementation-blind

        REQ-4b: When MCP session exists, _activate_project() uses that session ID, not random UUID.

        Theater Prevention:
        - Verifies EXACT session_id value from registry, NOT just "something was bound"
        - Cannot pass if implementation generates random UUID instead of using MCP session_id
        """
        config, workspace_path, _ = mock_serena_config
        registry = SessionRegistry()
        mcp_session_id = "mcp-session-deterministic-test"

        # Mock session bridge to return MCP session ID
        mock_bridge = MagicMock()
        mock_bridge.get_current_session_id.return_value = mcp_session_id

        with (
            patch("serena.agent.GlobalLanguageServerPool") as MockPool,
            patch("serena.agent.logging"),
            patch("serena.agent.Project.load") as MockProjectLoad,
        ):
            MockPool.return_value = MagicMock()
            MockProjectLoad.return_value = MagicMock()  # Return mock project to avoid autogeneration
            agent = SerenaAgent(serena_config=config, session_bridge=mock_bridge)
            agent._session_registry = registry

            # ACT: Activate project (black-box - cannot see implementation)
            project = config.get_project("test_project")
            agent._activate_project(project)

        # POST ASSERTION: get_session(mcp_session_id) returns SessionContext
        session_ctx = registry.get_session(mcp_session_id)

        assert session_ctx is not None, (
            f"POST-2 violation: get_session('{mcp_session_id}') returned None\n"
            "Contract: MCPFactoryActivationContract POST-2\n"
            f"EXPECTED: SessionContext for session_id='{mcp_session_id}'\n"
            "ACTUAL: None returned\n"
            "GUIDANCE: When _current_session_id exists, bind_session() MUST use that exact session_id, NOT generate random UUID. "
            "Registry MUST be queryable via get_session() with the MCP session_id."
        )

        # Verify it's the EXACT session we set, not a random UUID
        assert session_ctx.session_id == mcp_session_id, (
            f"POST-2 violation: Bound session_id does not match MCP session_id\n"
            "Contract: MCPFactoryActivationContract POST-2\n"
            f"EXPECTED: session_id == '{mcp_session_id}'\n"
            f"ACTUAL: session_id == '{session_ctx.session_id}'\n"
            "GUIDANCE: MUST use _current_session_id when present, NOT generate random UUID. "
            "This is REQ-4b: MCP session binding behavior."
        )

    def test_post_no_session_uses_anonymous_fallback(self, mock_serena_config):
        """
        CONTRACT TRACEABILITY:
        - Contract: MCPFactoryActivationContract._activate_project()
        - Enforces: POST-1: SessionRegistry.bind_session(session_id, workspace_root) called
        - Category: positive (fallback behavior)
        - Adversarial: Implementation-blind

        REQ-4b: When no MCP session exists, _activate_project() falls back to anonymous session.

        Theater Prevention:
        - Verifies ACTUAL registry binding occurred via get_session()
        - Cannot pass if bind_session() not called
        - Accepts any session_id when _current_session_id is None (anonymous mode)
        """
        config, workspace_path, _ = mock_serena_config
        registry = SessionRegistry()

        with (
            patch("serena.agent.GlobalLanguageServerPool") as MockPool,
            patch("serena.agent.logging"),
            patch("serena.agent.Project.load") as MockProjectLoad,
        ):
            MockPool.return_value = MagicMock()
            MockProjectLoad.return_value = MagicMock()
            # No session bridge provided = no MCP session
            agent = SerenaAgent(serena_config=config)
            agent._session_registry = registry

            # ACT: Activate project
            project = config.get_project("test_project")
            agent._activate_project(project)

        # POST ASSERTION: SOME session was created (anonymous fallback)
        # Since _current_session_id is None, implementation may use UUID or "anonymous" or other strategy
        # What matters: registry.bind_session() was called with SOME session_id
        session_overview = registry.get_session_overview()
        all_sessions = session_overview["sessions"]

        assert len(all_sessions) > 0, (
            "POST-1 violation: No session bound when _current_session_id is None\n"
            "Contract: MCPFactoryActivationContract POST-1\n"
            "EXPECTED: At least one session created (anonymous fallback)\n"
            f"ACTUAL: {len(all_sessions)} sessions\n"
            "GUIDANCE: When _current_session_id is None, MUST still bind a session (anonymous mode). "
            "Implementation may use UUID, 'anonymous', or other session_id - any valid strategy accepted."
        )

        # Verify the session has correct workspace (POST-3)
        # Get session_id from overview and query registry
        first_session_id = all_sessions[0]["session_id"]
        session_ctx = registry.get_session(first_session_id)
        expected_workspace = workspace_path.resolve()
        actual_workspace = Path(session_ctx.workspace_root).resolve()

        assert actual_workspace == expected_workspace, (
            "POST-3 violation: workspace_root != project.project_root.resolve() (anonymous session)\n"
            "Contract: MCPFactoryActivationContract POST-3\n"
            f"EXPECTED: {expected_workspace}\n"
            f"ACTUAL: {actual_workspace}\n"
            "GUIDANCE: Even in anonymous mode, workspace_root MUST be resolved project.project_root"
        )

    def test_inv2_binding_same_workspace_is_idempotent(self, mock_serena_config):
        """
        CONTRACT TRACEABILITY:
        - Contract: MCPFactoryActivationContract._activate_project()
        - Enforces: INV-2: Binding to same workspace is idempotent (no-op)
        - Category: invariant
        - Adversarial: Implementation-blind

        REQ-4b: Session binding is idempotent - activating same project twice is no-op.

        Theater Prevention:
        - Verifies registry state unchanged after second activation
        - Cannot pass if second activation creates new session or changes workspace
        """
        config, workspace_path, _ = mock_serena_config
        registry = SessionRegistry()
        mcp_session_id = "mcp-session-idempotent-test"

        mock_bridge = MagicMock()
        mock_bridge.get_current_session_id.return_value = mcp_session_id

        with (
            patch("serena.agent.GlobalLanguageServerPool") as MockPool,
            patch("serena.agent.logging"),
            patch("serena.agent.Project.load") as MockProjectLoad,
        ):
            MockPool.return_value = MagicMock()
            MockProjectLoad.return_value = MagicMock()
            agent = SerenaAgent(serena_config=config, session_bridge=mock_bridge)
            agent._session_registry = registry

            project = config.get_project("test_project")

            # ACT 1: First activation
            agent._activate_project(project)
            first_session_ctx = registry.get_session(mcp_session_id)
            first_workspace = Path(first_session_ctx.workspace_root).resolve()

            # ACT 2: Second activation (same project)
            agent._activate_project(project)
            second_session_ctx = registry.get_session(mcp_session_id)
            second_workspace = Path(second_session_ctx.workspace_root).resolve()

        # INV-2 ASSERTION: Second activation is no-op (same workspace)
        assert second_workspace == first_workspace, (
            "INV-2 violation: Second activation changed workspace_root\n"
            "Contract: MCPFactoryActivationContract INV-2\n"
            f"EXPECTED: workspace_root unchanged ({first_workspace})\n"
            f"ACTUAL: workspace_root changed to {second_workspace}\n"
            "GUIDANCE: Binding to same workspace MUST be idempotent (no-op). "
            "Second activation should return immediately without modifying registry."
        )

        # Verify session_id unchanged (still bound to same session)
        assert second_session_ctx.session_id == mcp_session_id, (
            "INV-2 violation: Second activation created new session\n"
            "Contract: MCPFactoryActivationContract INV-2\n"
            f"EXPECTED: session_id == '{mcp_session_id}'\n"
            f"ACTUAL: session_id == '{second_session_ctx.session_id}'\n"
            "GUIDANCE: Idempotent activation MUST preserve session_id, NOT create new session."
        )

    def test_inv3_binding_different_workspace_unbinds_previous(self, mock_serena_config):
        """
        CONTRACT TRACEABILITY:
        - Contract: MCPFactoryActivationContract._activate_project()
        - Enforces: INV-3: Binding to different workspace unbinds previous first
        - Category: invariant
        - Adversarial: Implementation-blind

        REQ-4b: Switching projects unbinds previous workspace first.

        Theater Prevention:
        - Verifies EXACT workspace_root after switch (not just "changed")
        - Cannot pass if previous workspace still bound or both bound simultaneously
        """
        config, workspace_path, other_workspace_path = mock_serena_config
        registry = SessionRegistry()
        mcp_session_id = "mcp-session-switch-test"

        mock_bridge = MagicMock()
        mock_bridge.get_current_session_id.return_value = mcp_session_id

        with (
            patch("serena.agent.GlobalLanguageServerPool") as MockPool,
            patch("serena.agent.logging"),
            patch("serena.agent.Project.load") as MockProjectLoad,
        ):
            MockPool.return_value = MagicMock()
            MockProjectLoad.return_value = MagicMock()
            agent = SerenaAgent(serena_config=config, session_bridge=mock_bridge)
            agent._session_registry = registry

            # ACT 1: Activate first project
            project1 = config.get_project("test_project")
            agent._activate_project(project1)
            session_ctx = registry.get_session(mcp_session_id)
            first_workspace = Path(session_ctx.workspace_root).resolve()

            # Verify first workspace bound
            assert first_workspace == workspace_path.resolve(), (
                "Setup failed: First workspace not bound correctly"
            )

            # ACT 2: Switch to different project
            project2 = config.get_project("other_project")
            agent._activate_project(project2)
            session_ctx = registry.get_session(mcp_session_id)
            second_workspace = Path(session_ctx.workspace_root).resolve()

        # INV-3 ASSERTION: Previous workspace unbound, new workspace bound
        expected_workspace = other_workspace_path.resolve()
        assert second_workspace == expected_workspace, (
            "INV-3 violation: Switching to different workspace did not update binding\n"
            "Contract: MCPFactoryActivationContract INV-3\n"
            f"EXPECTED: workspace_root == {expected_workspace}\n"
            f"ACTUAL: workspace_root == {second_workspace}\n"
            "GUIDANCE: Binding to different workspace MUST unbind previous workspace first, then bind new workspace. "
            "Registry MUST reflect new workspace after activation."
        )

        # Verify previous workspace is NOT bound
        assert second_workspace != first_workspace, (
            "INV-3 violation: New workspace same as previous (no switch occurred)\n"
            "Contract: MCPFactoryActivationContract INV-3\n"
            f"EXPECTED: New workspace ({expected_workspace}) != old workspace ({first_workspace})\n"
            f"ACTUAL: Both resolve to {second_workspace}\n"
            "GUIDANCE: Test setup error - projects must have different workspace_roots"
        )

    def test_inv5_other_sessions_unaffected(self, mock_serena_config):
        """
        CONTRACT TRACEABILITY:
        - Contract: MCPFactoryActivationContract._activate_project()
        - Enforces: INV-5: Other sessions unaffected by this activation
        - Category: invariant
        - Adversarial: Implementation-blind

        REQ-4b: Activating project for one session does not affect other sessions.

        Theater Prevention:
        - Verifies EXACT session_id and workspace_root for other session (unchanged)
        - Cannot pass if activation modified unrelated session
        """
        config, workspace_path, other_workspace_path = mock_serena_config
        registry = SessionRegistry()
        mcp_session_id_1 = "mcp-session-isolation-1"
        mcp_session_id_2 = "mcp-session-isolation-2"

        mock_bridge1 = MagicMock()
        mock_bridge1.get_current_session_id.return_value = mcp_session_id_1

        mock_bridge2 = MagicMock()
        mock_bridge2.get_current_session_id.return_value = mcp_session_id_2

        with (
            patch("serena.agent.GlobalLanguageServerPool") as MockPool,
            patch("serena.agent.logging"),
            patch("serena.agent.Project.load") as MockProjectLoad,
        ):
            MockPool.return_value = MagicMock()
            MockProjectLoad.return_value = MagicMock()

            # Create two agents with different sessions
            agent1 = SerenaAgent(serena_config=config, session_bridge=mock_bridge1)
            agent1._session_registry = registry

            agent2 = SerenaAgent(serena_config=config, session_bridge=mock_bridge2)
            agent2._session_registry = registry

            # ACT 1: Agent 1 activates test_project
            project1 = config.get_project("test_project")
            agent1._activate_project(project1)

            # ACT 2: Agent 2 activates other_project
            project2 = config.get_project("other_project")
            agent2._activate_project(project2)

            # Capture session states
            session1_ctx = registry.get_session(mcp_session_id_1)
            session2_ctx = registry.get_session(mcp_session_id_2)

            # ACT 3: Agent 1 activates again (should not affect agent 2's session)
            agent1._activate_project(project1)

            # Verify session 2 unchanged
            session2_ctx_after = registry.get_session(mcp_session_id_2)

        # INV-5 ASSERTION: Session 2 unaffected by agent 1's activation
        workspace2_before = Path(session2_ctx.workspace_root).resolve()
        workspace2_after = Path(session2_ctx_after.workspace_root).resolve()

        assert workspace2_after == workspace2_before, (
            "INV-5 violation: Agent 1 activation modified agent 2's workspace\n"
            "Contract: MCPFactoryActivationContract INV-5\n"
            f"EXPECTED: session 2 workspace_root unchanged ({workspace2_before})\n"
            f"ACTUAL: session 2 workspace_root == {workspace2_after}\n"
            "GUIDANCE: Activating project for one session MUST NOT affect other sessions. "
            "Each session operates independently."
        )

        # Verify session 1 still has correct workspace
        workspace1_after = Path(registry.get_session(mcp_session_id_1).workspace_root).resolve()
        expected_workspace1 = workspace_path.resolve()

        assert workspace1_after == expected_workspace1, (
            "INV-5 violation: Agent 1's own workspace changed incorrectly\n"
            "Contract: MCPFactoryActivationContract INV-5\n"
            f"EXPECTED: session 1 workspace_root == {expected_workspace1}\n"
            f"ACTUAL: session 1 workspace_root == {workspace1_after}\n"
            "GUIDANCE: Session 1 should maintain its own workspace binding"
        )

    def test_inv1_only_one_workspace_per_session(self, mock_serena_config):
        """
        CONTRACT TRACEABILITY:
        - Contract: MCPFactoryActivationContract._activate_project()
        - Enforces: INV-1: Only one workspace bound per session at a time
        - Category: invariant
        - Adversarial: Implementation-blind

        REQ-4b: A session can only be bound to one workspace at a time.

        Theater Prevention:
        - Verifies registry returns single SessionContext for session_id
        - Cannot pass if multiple workspaces bound to same session
        """
        config, workspace_path, other_workspace_path = mock_serena_config
        registry = SessionRegistry()
        mcp_session_id = "mcp-session-single-workspace-test"

        mock_bridge = MagicMock()
        mock_bridge.get_current_session_id.return_value = mcp_session_id

        with (
            patch("serena.agent.GlobalLanguageServerPool") as MockPool,
            patch("serena.agent.logging"),
            patch("serena.agent.Project.load") as MockProjectLoad,
        ):
            MockPool.return_value = MagicMock()
            MockProjectLoad.return_value = MagicMock()
            agent = SerenaAgent(serena_config=config, session_bridge=mock_bridge)
            agent._session_registry = registry

            # ACT 1: Activate first project
            project1 = config.get_project("test_project")
            agent._activate_project(project1)

            # ACT 2: Switch to different project (same session)
            project2 = config.get_project("other_project")
            agent._activate_project(project2)

            # Query registry
            session_ctx = registry.get_session(mcp_session_id)

        # INV-1 ASSERTION: Only one workspace bound
        assert session_ctx is not None, (
            "INV-1 violation: Session not found after activation\n"
            "Contract: MCPFactoryActivationContract INV-1\n"
            f"EXPECTED: SessionContext for session_id='{mcp_session_id}'\n"
            "ACTUAL: None\n"
            "GUIDANCE: Session MUST be bound to exactly one workspace"
        )

        # Verify it's the LATEST workspace (project2), not both
        expected_workspace = other_workspace_path.resolve()
        actual_workspace = Path(session_ctx.workspace_root).resolve()

        assert actual_workspace == expected_workspace, (
            "INV-1 violation: Session not bound to latest workspace\n"
            "Contract: MCPFactoryActivationContract INV-1\n"
            f"EXPECTED: workspace_root == {expected_workspace} (latest activation)\n"
            f"ACTUAL: workspace_root == {actual_workspace}\n"
            "GUIDANCE: Session MUST be bound to exactly ONE workspace (the most recent). "
            "Previous workspace should be unbound automatically."
        )

        # Verify session count (should be exactly 1 session)
        session_overview = registry.get_session_overview()
        all_sessions = session_overview["sessions"]
        matching_sessions = [s for s in all_sessions if s["session_id"] == mcp_session_id]

        assert len(matching_sessions) == 1, (
            "INV-1 violation: Multiple SessionContexts for same session_id\n"
            "Contract: MCPFactoryActivationContract INV-1\n"
            f"EXPECTED: 1 SessionContext for session_id='{mcp_session_id}'\n"
            f"ACTUAL: {len(matching_sessions)} SessionContexts\n"
            "GUIDANCE: Registry MUST maintain exactly one SessionContext per session_id. "
            "No duplicates allowed."
        )
