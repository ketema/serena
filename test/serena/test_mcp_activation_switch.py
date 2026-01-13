"""
Cycle 3.1: MCP Activation Switch Tests (REQ-4b)

Contract Reference: contracts/issue6_multi_project_contract.py

Tests trace to MCPFactoryActivationContract:
- PRE: agent is not None
- PRE: session_id is not None (session context exists)
- PRE: project_name is a string that exists in config OR valid path
- POST: SessionRegistry.bind_session(session_id, workspace_root) called
- POST: SessionRegistry.get_session(session_id) returns SessionContext
- POST: SessionContext.workspace_root == project.project_root.resolve()
- INV: Only one workspace bound per session at a time
- INV: Binding to same workspace is idempotent (no-op)
- INV: Binding to different workspace unbinds previous first
- INV: Other sessions unaffected by this activation

Theater Prevention (from CLAUDE.md):
- Assertions verify ACTUAL registry state, NOT mock call counts
- Tests verify observable POST conditions, NOT implementation details
- Error messages describe WHAT behavior is expected, NOT HOW to implement
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from serena.config.serena_config import LanguageBackend
from serena.mcp import SerenaMCPFactory
from serena.session_registry import SessionRegistry


def _make_mock_agent(registry: SessionRegistry, config: MagicMock, project_name: str) -> MagicMock:
    mock_agent = MagicMock()
    mock_agent._session_registry = registry
    mock_agent.serena_config = config

    def activate_session_project(session_id: str, workspace_root: Path, source: str = "explicit"):
        existing = registry.get_session(session_id)
        if existing is not None:
            if Path(existing.workspace_root).resolve() == Path(workspace_root).resolve():
                return config.get_project(project_name)
            registry.unbind_session(session_id)
        registry.bind_session(session_id, Path(workspace_root), source)
        return config.get_project(project_name)

    mock_agent.activate_session_project = activate_session_project
    return mock_agent


@pytest.fixture
def mock_serena_config(tmp_path: Path):
    """
    Mock SerenaConfig following established pattern.

    Contract: PRE for activate_project_for_mcp_session requires project in config
    """
    config = MagicMock()

    # Mock config attributes needed by SerenaAgent.__init__
    config.log_level = logging.INFO
    config.config_file_path = tmp_path / "serena_config.yml"
    config.project_names = ["test_project"]
    config.gui_log_window_enabled = False
    config.language_backend = LanguageBackend.LSP
    config.token_count_estimator = "CHAR_COUNT"
    config.web_dashboard = False
    config.modes = []

    # Create workspace directory
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()

    # Mock project object
    project = MagicMock()
    project.project_name = "test_project"
    project.project_root = workspace

    # get_project(name) returns project or raises
    def get_project_mock(name: str):
        if name == "test_project":
            return project
        from serena.agent import ProjectNotFoundError

        raise ProjectNotFoundError(f"Project '{name}' not found")

    config.get_project = MagicMock(side_effect=get_project_mock)

    return config, workspace


class TestMCPFactoryActivationContract:
    """
    Tests for MCPFactoryActivationContract.

    Contract Reference: contracts/issue6_multi_project_contract.py::MCPFactoryActivationContract
    REQ-4b: mcp.py uses activate_session_project() for MCP clients
    """

    def test_post_get_session_returns_context_after_activation(self, mock_serena_config):
        """
        Contract: MCPFactoryActivationContract
        Enforces: POST: SessionRegistry.get_session(session_id) returns SessionContext

        Theater Prevention:
        - Verifies ACTUAL registry state via get_session(), NOT mock.called
        - Cannot pass if bind_session() didn't actually update registry
        """
        config, workspace_path = mock_serena_config
        registry = SessionRegistry()
        session_id = "mcp-session-post-test"

        factory = SerenaMCPFactory(project="test_project")
        factory._session_registry = registry
        bridge = factory.get_session_bridge()
        token = bridge.set_session_context(session_id)

        try:
            with (
                patch.object(factory, "_create_default_serena_config", return_value=config),
                patch("serena.mcp.SerenaAgent", autospec=True) as MockAgent,
            ):
                mock_agent = _make_mock_agent(registry, config, "test_project")
                MockAgent.return_value = mock_agent

                factory._create_serena_agent(config, [])
                factory.agent = mock_agent
                factory._serena_config = config

                # ACT: Activate project for MCP session
                factory.activate_project_for_mcp_session("test_project")
        finally:
            bridge.reset_session_context(token)

        # POST ASSERTION: get_session(session_id) returns SessionContext
        session_ctx = registry.get_session(session_id)

        assert session_ctx is not None, (
            "POST violation: SessionRegistry.get_session(session_id) returned None\n"
            "Contract: MCPFactoryActivationContract POST\n"
            f"EXPECTED: SessionContext for session_id='{session_id}'\n"
            "ACTUAL: None returned\n"
            "Guidance: bind_session() MUST update registry so get_session() returns context"
        )

    def test_post_workspace_root_matches_project_root(self, mock_serena_config):
        """
        Contract: MCPFactoryActivationContract
        Enforces: POST: SessionContext.workspace_root == project.project_root.resolve()

        Theater Prevention:
        - Verifies EXACT workspace_root value, NOT just "something was set"
        - Cannot pass if wrong workspace bound
        """
        config, workspace_path = mock_serena_config
        registry = SessionRegistry()
        session_id = "mcp-session-workspace-test"

        factory = SerenaMCPFactory(project="test_project")
        factory._session_registry = registry
        bridge = factory.get_session_bridge()
        token = bridge.set_session_context(session_id)

        try:
            with (
                patch.object(factory, "_create_default_serena_config", return_value=config),
                patch("serena.mcp.SerenaAgent", autospec=True) as MockAgent,
            ):
                mock_agent = _make_mock_agent(registry, config, "test_project")
                MockAgent.return_value = mock_agent

                factory._create_serena_agent(config, [])
                factory.agent = mock_agent
                factory._serena_config = config

                factory.activate_project_for_mcp_session("test_project")
        finally:
            bridge.reset_session_context(token)

        session_ctx = registry.get_session(session_id)
        expected_workspace = workspace_path.resolve()
        actual_workspace = Path(session_ctx.workspace_root).resolve()

        assert actual_workspace == expected_workspace, (
            "POST violation: workspace_root != project.project_root.resolve()\n"
            "Contract: MCPFactoryActivationContract POST\n"
            f"EXPECTED: {expected_workspace}\n"
            f"ACTUAL: {actual_workspace}\n"
            "Guidance: workspace_root MUST be resolved project.project_root"
        )

    def test_pre_agent_none_raises_valueerror(self):
        """
        Contract: MCPFactoryActivationContract
        Enforces: PRE: self.agent is not None
        ERRORS: ValueError if agent is None

        Theater Prevention:
        - Cannot pass if PRE validation skipped
        - Verifies exact error type and message
        """
        factory = SerenaMCPFactory(project="test_project")
        factory.agent = None  # Explicitly violate PRE

        with pytest.raises(ValueError) as exc_info:
            factory.activate_project_for_mcp_session("test_project")

        assert "agent" in str(exc_info.value).lower(), (
            "ERRORS violation: ValueError message should mention 'agent'\n"
            "Contract: MCPFactoryActivationContract ERRORS\n"
            f"EXPECTED: Message containing 'agent'\n"
            f"ACTUAL: '{exc_info.value}'\n"
            "Guidance: Error message MUST indicate agent was None"
        )

    def test_pre_session_id_none_raises_valueerror(self, mock_serena_config):
        """
        Contract: MCPFactoryActivationContract
        Enforces: PRE: current session context exists via MCPSessionBridge
        ERRORS: ValueError if session_id is None

        Theater Prevention:
        - Cannot pass if session_id validation skipped
        - Verifies exact error type
        """
        config, _ = mock_serena_config
        factory = SerenaMCPFactory(project="test_project")

        registry = SessionRegistry()
        factory._session_registry = registry
        mock_agent = MagicMock()
        mock_agent.serena_config = config
        factory.agent = mock_agent
        factory._serena_config = config

        with pytest.raises(ValueError) as exc_info:
            factory.activate_project_for_mcp_session("test_project")

        assert "session" in str(exc_info.value).lower(), (
            "ERRORS violation: ValueError message should mention 'session'\n"
            "Contract: MCPFactoryActivationContract ERRORS\n"
            f"EXPECTED: Message containing 'session'\n"
            f"ACTUAL: '{exc_info.value}'\n"
            "Guidance: Error message MUST indicate session_id was None"
        )

    def test_pre_invalid_project_raises_projectnotfounderror(self, mock_serena_config):
        """
        Contract: MCPFactoryActivationContract
        Enforces: PRE: project_name exists in config
        ERRORS: ProjectNotFoundError if project_name not in config

        Theater Prevention:
        - Verifies exact exception type
        - Cannot pass if project validation skipped
        """
        from serena.agent import ProjectNotFoundError

        config, _ = mock_serena_config
        registry = SessionRegistry()
        factory = SerenaMCPFactory(project="test_project")
        factory._session_registry = registry
        bridge = factory.get_session_bridge()
        token = bridge.set_session_context("valid-session")

        try:
            mock_agent = _make_mock_agent(registry, config, "test_project")
            factory.agent = mock_agent
            factory._serena_config = config

            with pytest.raises(ProjectNotFoundError) as exc_info:
                factory.activate_project_for_mcp_session("nonexistent_project")
        finally:
            bridge.reset_session_context(token)

        assert "nonexistent_project" in str(exc_info.value), (
            "ERRORS violation: ProjectNotFoundError should contain project name\n"
            "Contract: MCPFactoryActivationContract ERRORS\n"
            f"EXPECTED: Message containing 'nonexistent_project'\n"
            f"ACTUAL: '{exc_info.value}'\n"
            "Guidance: Error message MUST include the invalid project_name"
        )

    def test_inv_binding_same_workspace_is_idempotent(self, mock_serena_config):
        """
        Contract: MCPFactoryActivationContract
        Enforces: INV: Binding to same workspace is idempotent (no-op)

        Theater Prevention:
        - Calls activation twice, verifies no side effects
        - Verifies registry state unchanged after second call
        """
        config, workspace_path = mock_serena_config
        registry = SessionRegistry()
        session_id = "mcp-session-idempotent-test"

        factory = SerenaMCPFactory(project="test_project")
        factory._session_registry = registry
        bridge = factory.get_session_bridge()
        token = bridge.set_session_context(session_id)

        try:
            with (
                patch.object(factory, "_create_default_serena_config", return_value=config),
                patch("serena.mcp.SerenaAgent", autospec=True) as MockAgent,
            ):
                mock_agent = _make_mock_agent(registry, config, "test_project")
                MockAgent.return_value = mock_agent

                factory._create_serena_agent(config, [])
                factory.agent = mock_agent
                factory._serena_config = config

                # First activation
                factory.activate_project_for_mcp_session("test_project")

                # Capture state after first
                session_after_first = registry.get_session(session_id)
                workspace_after_first = session_after_first.workspace_root

                # Second activation (should be no-op)
                factory.activate_project_for_mcp_session("test_project")

                # Capture state after second
                session_after_second = registry.get_session(session_id)
                workspace_after_second = session_after_second.workspace_root
        finally:
            bridge.reset_session_context(token)

        # INV ASSERTION: State unchanged
        assert workspace_after_first == workspace_after_second, (
            "INV violation: Binding same workspace changed state\n"
            "Contract: MCPFactoryActivationContract INV\n"
            f"EXPECTED: workspace unchanged = {workspace_after_first}\n"
            f"ACTUAL: workspace = {workspace_after_second}\n"
            "Guidance: Second bind to same workspace MUST be idempotent no-op"
        )

    def test_inv_other_sessions_unaffected(self, mock_serena_config, tmp_path):
        """
        Contract: MCPFactoryActivationContract
        Enforces: INV: Other sessions unaffected by this activation

        Theater Prevention:
        - Creates two sessions, activates project for one
        - Verifies other session unchanged
        """
        config, workspace_path = mock_serena_config
        registry = SessionRegistry()
        session_id_1 = "session-affected"
        session_id_2 = "session-bystander"

        # Pre-bind session_2 to registry with a different workspace (must exist)
        other_workspace = tmp_path / "other_workspace"
        other_workspace.mkdir()
        registry.bind_session(session_id_2, other_workspace, "explicit")

        factory = SerenaMCPFactory(project="test_project")
        factory._session_registry = registry
        bridge = factory.get_session_bridge()
        token = bridge.set_session_context(session_id_1)

        try:
            with (
                patch.object(factory, "_create_default_serena_config", return_value=config),
                patch("serena.mcp.SerenaAgent", autospec=True) as MockAgent,
            ):
                mock_agent = _make_mock_agent(registry, config, "test_project")
                MockAgent.return_value = mock_agent

                factory._create_serena_agent(config, [])
                factory.agent = mock_agent
                factory._serena_config = config

                # ACT: Activate project for session_1
                factory.activate_project_for_mcp_session("test_project")
        finally:
            bridge.reset_session_context(token)

        # INV ASSERTION: session_2 unchanged
        session_2_ctx = registry.get_session(session_id_2)
        assert session_2_ctx is not None, (
            "INV violation: Other session was removed\n"
            "Contract: MCPFactoryActivationContract INV\n"
            "EXPECTED: session_2 still in registry\n"
            "ACTUAL: session_2 removed\n"
            "Guidance: Operations on one session MUST NOT affect others"
        )

        assert Path(session_2_ctx.workspace_root).resolve() == other_workspace.resolve(), (
            "INV violation: Other session workspace was modified\n"
            "Contract: MCPFactoryActivationContract INV\n"
            f"EXPECTED: workspace = {other_workspace}\n"
            f"ACTUAL: workspace = {session_2_ctx.workspace_root}\n"
            "Guidance: Operations on one session MUST NOT modify other sessions"
        )


class TestMCPFactoryRegistryAccess:
    """
    Tests for factory registry access.

    Contract Reference: contracts/issue6_multi_project_contract.py
    Supports: Session binding verification
    """

    def test_get_session_registry_returns_sessionregistry(self):
        """
        Contract: SerenaMCPFactory provides registry access
        Enforces: get_session_registry() returns SessionRegistry instance

        Theater Prevention:
        - Verifies exact type, NOT just "truthy"
        - Cannot pass with wrong type
        """
        factory = SerenaMCPFactory(project="test_project")

        registry = factory.get_session_registry()

        assert registry is not None, (
            "Factory MUST provide session registry\n"
            "EXPECTED: SessionRegistry instance\n"
            "ACTUAL: None"
        )

        assert isinstance(registry, SessionRegistry), (
            "Factory MUST return actual SessionRegistry\n"
            f"EXPECTED: SessionRegistry type\n"
            f"ACTUAL: {type(registry).__name__}"
        )

    def test_factory_without_project_has_empty_registry(self):
        """
        Contract: Factory without project does not auto-bind sessions
        Enforces: Registry empty until explicit activation

        Theater Prevention:
        - Verifies registry state, NOT method call absence
        """
        factory = SerenaMCPFactory(project=None)

        registry = factory.get_session_registry()
        overview = registry.get_session_overview()

        assert overview["total_count"] == 0, (
            "Registry should be empty when no project specified\n"
            f"EXPECTED: total_count = 0\n"
            f"ACTUAL: total_count = {overview['total_count']}\n"
            "Guidance: No automatic binding without explicit project"
        )

    def test_activate_project_for_mcp_session_method_exists(self):
        """
        Contract: MCPFactoryActivationContract
        Enforces: Factory provides session-aware activation method

        Theater Prevention:
        - Verifies method existence AND is callable
        """
        factory = SerenaMCPFactory(project="test_project")

        assert hasattr(factory, "activate_project_for_mcp_session"), (
            "Factory MUST have activate_project_for_mcp_session method\n"
            "Contract: MCPFactoryActivationContract\n"
            "EXPECTED: Method exists\n"
            "ACTUAL: Method not found"
        )

        assert callable(getattr(factory, "activate_project_for_mcp_session")), (
            "activate_project_for_mcp_session MUST be callable\n"
            "Contract: MCPFactoryActivationContract\n"
            "EXPECTED: Callable method\n"
            f"ACTUAL: {type(getattr(factory, 'activate_project_for_mcp_session'))}"
        )
