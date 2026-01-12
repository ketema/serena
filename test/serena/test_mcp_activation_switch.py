"""
Cycle 3.1 RED: MCP Activation Switch Tests (REQ-4b)

Contract: SerenaMCPFactory activation MUST use activate_session_project()
Enforces: MCP clients use session-aware activation path

REQ-4b: mcp.py uses activate_session_project() for MCP clients instead of activate_project()

Theater Prevention:
- Assertions verify registry state after MCP lifecycle, not just method existence
- Tests go through MCP factory pathway, not direct agent method calls
- Real errors (ValueError) for missing session context in MCP path

Test Philosophy:
- Tests are BLIND to implementation - they specify WHAT should happen
- GREEN phase coder implements HOW to make tests pass
- Observable effects: SessionRegistry state, error messages
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from serena.config.serena_config import LanguageBackend
from serena.mcp import SerenaMCPFactory
from serena.session_registry import SessionRegistry


@pytest.fixture
def mock_serena_config(tmp_path: Path):
    """Mock SerenaConfig following established pattern."""
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


class TestMCPActivationSwitch:
    """
    REQ-4b: mcp.py uses activate_session_project() for MCP clients

    These tests verify the MCP PATHWAY calls activate_session_project(),
    not just that the method works (that's Phase 2).
    """

    def test_mcp_factory_binds_session_on_agent_creation(self, mock_serena_config):
        """
        Contract: SerenaMCPFactory with project and session binds to registry
        Enforces: POST: After agent created with session context, registry has binding

        Given: SerenaMCPFactory created with project AND session context
        When: SerenaAgent is created through factory
        Then: SessionRegistry.get_session(session_id) returns bound session

        Theater Check: Verify ACTUAL registry state after agent creation,
        NOT via mocked call counts
        """
        config, workspace_path = mock_serena_config

        # Create shared registry
        registry = SessionRegistry()
        session_id = "mcp-client-session-123"

        # Create MCP factory with project
        factory = SerenaMCPFactory(project="test_project")

        # Patch config loading and agent creation to use our mocks
        with (
            patch.object(factory, "_create_default_serena_config", return_value=config),
            patch(
                "serena.mcp.SerenaAgent",
                autospec=True,
            ) as MockAgent,
        ):
            # Configure mock agent
            mock_agent = MagicMock()
            mock_agent._session_registry = registry
            mock_agent._current_session_id = session_id
            MockAgent.return_value = mock_agent

            # Create agent through factory
            modes = []
            agent = factory._create_serena_agent(config, modes)

            # Factory should call activate_session_project on the agent
            # This is what REQ-4b requires
            factory.agent = agent

            # ACT: Factory should bind session after agent creation
            # Implementation: factory.activate_project_for_mcp_session(session_id)
            # or similar mechanism during startup

        # ASSERT: Registry should contain session binding
        # This will FAIL until implementation adds binding logic
        session_ctx = registry.get_session(session_id)

        assert session_ctx is not None, (
            "\n=== FAILURE: test_mcp_factory_binds_session_on_agent_creation ===\n"
            "WHAT FAILED: SessionRegistry.get_session(session_id) returned None\n"
            "WHY: REQ-4b requires MCP factory to bind session via activate_session_project()\n"
            f"EXPECTED: Session '{session_id}' bound to workspace {workspace_path}\n"
            "ACTUAL: No session binding found in registry\n"
            "BEHAVIORAL GUIDANCE:\n"
            "  - SerenaMCPFactory MUST call agent.activate_session_project() during startup\n"
            "  - Session binding MUST occur after agent creation with session context\n"
            "  - Registry binding MUST be observable via get_session(session_id)\n"
            "  Observable effects:\n"
            "    - SessionRegistry.get_session(session_id) returns SessionContext\n"
            "    - SessionContext.workspace_root == project.project_root\n"
            "  Implementation options:\n"
            "    - Add activate_project_for_mcp_session() to SerenaMCPFactory\n"
            "    - Call during server_lifespan or on first tool call\n"
            "    - Set agent._current_session_id before calling activate_session_project()\n"
        )

    def test_mcp_session_registry_accessible_via_factory(self, mock_serena_config):
        """
        Contract: SerenaMCPFactory exposes session registry for verification
        Enforces: POST: get_session_registry() returns the shared registry

        Given: SerenaMCPFactory instance
        When: get_session_registry() called
        Then: Returns SessionRegistry instance used for session binding

        Theater Check: Verify real registry instance is returned (already implemented in Phase 2)
        """
        factory = SerenaMCPFactory(project="test_project")

        # ACT: Get registry from factory
        registry = factory.get_session_registry()

        # ASSERT: Registry is valid SessionRegistry instance
        assert registry is not None, (
            "\n=== FAILURE: test_mcp_session_registry_accessible_via_factory ===\n"
            "WHAT FAILED: get_session_registry() returned None\n"
            "WHY: Factory MUST expose registry for session binding and verification\n"
            "EXPECTED: SessionRegistry instance\n"
            "ACTUAL: None\n"
            "BEHAVIORAL GUIDANCE:\n"
            "  - SerenaMCPFactory.get_session_registry() returns shared registry\n"
            "  - Same registry used for bind_session() and get_session()\n"
        )

        assert isinstance(registry, SessionRegistry), (
            "\n=== FAILURE: test_mcp_session_registry_accessible_via_factory (type) ===\n"
            "WHAT FAILED: get_session_registry() returned wrong type\n"
            f"EXPECTED: SessionRegistry instance\n"
            f"ACTUAL: {type(registry)}\n"
            "BEHAVIORAL GUIDANCE:\n"
            "  - Return the actual SessionRegistry, not a mock or wrapper\n"
        )

    def test_mcp_factory_activate_session_project_method_exists(self):
        """
        Contract: SerenaMCPFactory has method to activate project with session context
        Enforces: POST: Factory provides activate_project_for_mcp_session() or equivalent

        Given: SerenaMCPFactory instance
        When: Checking for activation method
        Then: Method exists that accepts session_id and project_name

        Theater Check: Verify method EXISTS (signature check, not mock.called)
        """
        factory = SerenaMCPFactory(project="test_project")

        # ACT: Check if activation method exists
        # Could be named: activate_project_for_mcp_session, _activate_session_project, etc.
        has_activation = (
            hasattr(factory, "activate_project_for_mcp_session")
            or hasattr(factory, "_activate_project_for_session")
            or hasattr(factory, "bind_session_to_project")
        )

        assert has_activation, (
            "\n=== FAILURE: test_mcp_factory_activate_session_project_method_exists ===\n"
            "WHAT FAILED: No session activation method found on SerenaMCPFactory\n"
            "WHY: REQ-4b requires MCP factory to have method for session-aware activation\n"
            "EXPECTED: One of these methods exists:\n"
            "  - activate_project_for_mcp_session(session_id, project_name)\n"
            "  - _activate_project_for_session()\n"
            "  - bind_session_to_project(session_id)\n"
            "ACTUAL: None of these methods found\n"
            "BEHAVIORAL GUIDANCE:\n"
            "  - Add method to SerenaMCPFactory that:\n"
            "    1. Sets agent._current_session_id from MCP client session\n"
            "    2. Calls agent.activate_session_project(project_name)\n"
            "    3. Handles PRE violation (no session) gracefully\n"
            "  Implementation:\n"
            "    def activate_project_for_mcp_session(self, session_id: str) -> None:\n"
            "        self.agent._current_session_id = session_id\n"
            "        self.agent.activate_session_project(self.project)\n"
        )

    def test_mcp_without_project_skips_session_binding(self):
        """
        Contract: SerenaMCPFactory without project does not bind session
        Enforces: POST: No registry pollution when project is None

        Given: SerenaMCPFactory created WITHOUT project
        When: MCP lifecycle starts
        Then: SessionRegistry remains empty (no binding attempt)

        Theater Check: Verify registry is empty, not just that method wasn't called
        """
        # Create MCP factory WITHOUT project
        factory = SerenaMCPFactory(project=None)

        # Get the factory's registry
        registry = factory.get_session_registry()

        # ASSERT: Registry remains empty (no automatic binding)
        sessions = registry.get_session_overview()["sessions"]
        assert len(sessions) == 0, (
            "\n=== FAILURE: test_mcp_without_project_skips_session_binding ===\n"
            "WHAT FAILED: Registry was modified even without project\n"
            "WHY: No-project MCP sessions should not pollute registry\n"
            f"EXPECTED: 0 sessions in registry\n"
            f"ACTUAL: {len(sessions)} sessions found\n"
            "BEHAVIORAL GUIDANCE:\n"
            "  - Check self.project is not None before binding\n"
            "  - No-project scenarios skip initial binding\n"
            "  - Registry should remain clean until explicit activation\n"
        )
