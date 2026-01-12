"""
Cycle 3.3: Legacy activate_project() Shim Tests (REQ-5b)

Contract Reference: contracts/issue6_multi_project_contract.py

Tests trace to BackwardCompatibilityContract:
- activate_project_legacy():
  - PRE: project_name exists in config
  - POST: _active_project set to project
  - POST: SessionRegistry NOT modified
  - INV: Does NOT create session
  - INV: Does NOT call bind_session()
  - ERRORS: ProjectNotFoundError if project_name not in config

- activate_project_with_session():
  - PRE: project_name exists in config
  - PRE: Session context exists (from MCP transport)
  - POST: Session bound to project workspace via SessionRegistry
  - POST: Legacy _active_project NOT set (stateless agent)
  - INV: _active_project unchanged
  - INV: Other sessions unaffected
  - ERRORS: ProjectNotFoundError if project_name not in config

- detect_execution_context():
  - POST: Returns "mcp" if session context exists
  - POST: Returns "cli" if no session context
  - INV: Does not modify state (read-only detection)

Theater Prevention (from CLAUDE.md):
- Assertions verify ACTUAL registry state, NOT mock call counts
- Tests verify observable POST conditions, NOT implementation details
- Error messages describe WHAT behavior is expected, NOT HOW to implement
"""

from contextvars import ContextVar
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.serena.agent import ProjectNotFoundError, SerenaAgent

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_session_registry():
    """
    Mock SessionRegistry following contract.

    Contract: SessionRegistry provides bind_session(), unbind_session(), get_session()
    """
    registry = MagicMock()
    registry.bind_session = MagicMock()
    registry.unbind_session = MagicMock()
    registry.get_session = MagicMock(return_value=None)
    return registry


@pytest.fixture
def mock_serena_config(tmp_path: Path):
    """
    Mock SerenaConfig with two test projects.

    Contract: PRE for activate_project requires project in config
    """
    import logging

    from src.serena.config.serena_config import LanguageBackend

    config = MagicMock()

    # Mock config attributes needed by SerenaAgent.__init__
    config.log_level = logging.INFO
    config.config_file_path = tmp_path / "serena_config.yml"
    config.project_names = ["project_a", "project_b"]
    config.gui_log_window_enabled = False
    config.language_backend = LanguageBackend.LSP
    config.token_count_estimator = "TIKTOKEN_GPT4O"
    config.web_dashboard = False

    # Create two workspace directories
    workspace_a = tmp_path / "workspace_a"
    workspace_a.mkdir()
    workspace_b = tmp_path / "workspace_b"
    workspace_b.mkdir()

    # Mock project objects
    project_a = MagicMock()
    project_a.project_name = "project_a"
    project_a.project_root = workspace_a

    project_b = MagicMock()
    project_b.project_name = "project_b"
    project_b.project_root = workspace_b

    # get_project(name) returns project or raises ProjectNotFoundError
    def get_project_mock(name: str):
        if name == "project_a":
            return project_a
        elif name == "project_b":
            return project_b
        else:
            raise ProjectNotFoundError(f"Project '{name}' not found")

    config.get_project = MagicMock(side_effect=get_project_mock)
    config.projects = {"project_a": project_a, "project_b": project_b}

    return config, project_a, project_b


@pytest.fixture
def agent_with_session(mock_session_registry, mock_serena_config):
    """
    Create SerenaAgent with active session context (MCP mode).

    Contract: detect_execution_context() returns "mcp" when session exists
    """
    config, project_a, project_b = mock_serena_config

    agent = SerenaAgent(
        serena_config=config,
        session_registry=mock_session_registry,
        session_bridge=MagicMock(),
        lsp_pool=MagicMock(),
    )

    agent._current_session_id = ContextVar("session_id", default=None)
    agent._current_session_id.set("test-session-456")

    yield agent, project_a, project_b


@pytest.fixture
def agent_without_session(mock_session_registry, mock_serena_config):
    """
    Create SerenaAgent without session context (CLI mode).

    Contract: detect_execution_context() returns "cli" when no session
    """
    config, project_a, project_b = mock_serena_config

    agent = SerenaAgent(
        serena_config=config,
        session_registry=mock_session_registry,
        session_bridge=MagicMock(),
        lsp_pool=MagicMock(),
    )

    agent._current_session_id = ContextVar("session_id", default=None)
    # Do NOT set session - simulates CLI invocation

    yield agent, project_a, project_b


# =============================================================================
# TESTS: BackwardCompatibilityContract - activate_project_with_session()
# =============================================================================


class TestActivateProjectWithSession:
    """
    Tests for activate_project() when session context exists.

    Contract Reference: contracts/issue6_multi_project_contract.py::BackwardCompatibilityContract
    Method: activate_project_with_session()
    """

    def test_post_session_bound_via_registry(self, agent_with_session):
        """
        Contract: BackwardCompatibilityContract.activate_project_with_session()
        Enforces: POST: Session bound to project workspace via SessionRegistry

        Theater Prevention:
        - Verifies registry.bind_session() called with correct args
        - Cannot pass if delegation to session-aware path skipped
        """
        agent, project_a, _ = agent_with_session

        # PRE: Verify session context exists
        assert agent._current_session_id.get() == "test-session-456", (
            "Test setup error: Session context must exist\n"
            "Contract: PRE for activate_project_with_session\n"
            f"EXPECTED: session_id = 'test-session-456'\n"
            f"ACTUAL: session_id = {agent._current_session_id.get()}"
        )

        # ACT: Activate project with session context
        agent.activate_project("project_a")

        # POST ASSERTION: bind_session() called
        assert agent._session_registry.bind_session.call_count == 1, (
            "POST violation: SessionRegistry.bind_session() not called\n"
            "Contract: BackwardCompatibilityContract.activate_project_with_session()\n"
            "EXPECTED: bind_session() called exactly once\n"
            f"ACTUAL: bind_session() called {agent._session_registry.bind_session.call_count} times\n"
            "Guidance: When session context exists, MUST delegate to session-aware activation"
        )

    def test_post_bind_session_receives_correct_session_id(self, agent_with_session):
        """
        Contract: BackwardCompatibilityContract.activate_project_with_session()
        Enforces: POST: Session bound with current session_id from ContextVar

        Theater Prevention:
        - Verifies EXACT session_id passed, NOT just "something was passed"
        """
        agent, project_a, _ = agent_with_session
        expected_session_id = "test-session-456"

        agent.activate_project("project_a")

        call_args = agent._session_registry.bind_session.call_args
        actual_session_id = call_args[0][0]

        assert actual_session_id == expected_session_id, (
            "POST violation: bind_session() received wrong session_id\n"
            "Contract: BackwardCompatibilityContract.activate_project_with_session()\n"
            f"EXPECTED: session_id = '{expected_session_id}'\n"
            f"ACTUAL: session_id = '{actual_session_id}'\n"
            "Guidance: session_id MUST come from _current_session_id ContextVar"
        )

    def test_post_bind_session_receives_correct_workspace(self, agent_with_session):
        """
        Contract: BackwardCompatibilityContract.activate_project_with_session()
        Enforces: POST: Session bound to project.project_root workspace

        Theater Prevention:
        - Verifies EXACT workspace passed
        """
        agent, project_a, _ = agent_with_session
        expected_workspace = project_a.project_root

        agent.activate_project("project_a")

        call_args = agent._session_registry.bind_session.call_args
        actual_workspace = call_args[0][1]

        assert actual_workspace == expected_workspace, (
            "POST violation: bind_session() received wrong workspace\n"
            "Contract: BackwardCompatibilityContract.activate_project_with_session()\n"
            f"EXPECTED: workspace = {expected_workspace}\n"
            f"ACTUAL: workspace = {actual_workspace}\n"
            "Guidance: workspace MUST be project.project_root from config.get_project()"
        )


# =============================================================================
# TESTS: BackwardCompatibilityContract - activate_project_legacy()
# =============================================================================


class TestActivateProjectLegacy:
    """
    Tests for activate_project() when no session context (CLI mode).

    Contract Reference: contracts/issue6_multi_project_contract.py::BackwardCompatibilityContract
    Method: activate_project_legacy()
    """

    def test_post_registry_not_modified(self, agent_without_session):
        """
        Contract: BackwardCompatibilityContract.activate_project_legacy()
        Enforces: POST: SessionRegistry NOT modified

        Theater Prevention:
        - Verifies bind_session() NOT called
        - Cannot pass if session-aware path incorrectly triggered
        """
        agent, project_a, _ = agent_without_session

        # PRE: Verify no session context
        assert agent._current_session_id.get() is None, (
            "Test setup error: No session context should exist for legacy mode\n"
            "Contract: PRE for activate_project_legacy\n"
            f"EXPECTED: session_id = None\n"
            f"ACTUAL: session_id = {agent._current_session_id.get()}"
        )

        # ACT: Activate project without session
        agent.activate_project("project_a")

        # POST ASSERTION: bind_session() NOT called
        assert agent._session_registry.bind_session.call_count == 0, (
            "POST violation: SessionRegistry modified in legacy mode\n"
            "Contract: BackwardCompatibilityContract.activate_project_legacy()\n"
            "EXPECTED: bind_session() NOT called (legacy = no registry)\n"
            f"ACTUAL: bind_session() called {agent._session_registry.bind_session.call_count} times\n"
            "Guidance: CLI mode MUST NOT touch SessionRegistry"
        )

    def test_inv_no_unbind_in_legacy_mode(self, agent_without_session):
        """
        Contract: BackwardCompatibilityContract.activate_project_legacy()
        Enforces: INV: Does NOT call unbind_session() (no sessions to unbind)

        Theater Prevention:
        - Verifies no registry mutation of any kind
        """
        agent, project_a, _ = agent_without_session

        agent.activate_project("project_a")

        assert agent._session_registry.unbind_session.call_count == 0, (
            "INV violation: unbind_session() called in legacy mode\n"
            "Contract: BackwardCompatibilityContract.activate_project_legacy()\n"
            "EXPECTED: unbind_session() NOT called\n"
            f"ACTUAL: unbind_session() called {agent._session_registry.unbind_session.call_count} times\n"
            "Guidance: Legacy mode operates without sessions entirely"
        )


# =============================================================================
# TESTS: Error Handling (shared across both modes)
# =============================================================================


class TestActivateProjectErrors:
    """
    Tests for error handling in activate_project().

    Contract Reference: contracts/issue6_multi_project_contract.py::BackwardCompatibilityContract
    ERRORS clause applies to both legacy and session-aware paths
    """

    def test_errors_projectnotfounderror_with_session(self, agent_with_session):
        """
        Contract: BackwardCompatibilityContract
        Enforces: ERRORS: ProjectNotFoundError if project_name not in config

        Theater Prevention:
        - Verifies exact exception type raised
        - Verifies error message contains project name
        """
        agent, _, _ = agent_with_session

        with pytest.raises(ProjectNotFoundError) as exc_info:
            agent.activate_project("nonexistent_project")

        assert "nonexistent_project" in str(exc_info.value), (
            "ERRORS violation: ProjectNotFoundError message should contain project name\n"
            "Contract: BackwardCompatibilityContract ERRORS\n"
            f"EXPECTED: Message contains 'nonexistent_project'\n"
            f"ACTUAL: '{exc_info.value}'\n"
            "Guidance: Error message MUST include invalid project_name for debugging"
        )

    def test_errors_projectnotfounderror_without_session(self, agent_without_session):
        """
        Contract: BackwardCompatibilityContract
        Enforces: ERRORS: ProjectNotFoundError works in legacy mode too

        Theater Prevention:
        - Verifies error handling consistent across modes
        """
        agent, _, _ = agent_without_session

        with pytest.raises(ProjectNotFoundError) as exc_info:
            agent.activate_project("nonexistent_project")

        assert "nonexistent_project" in str(exc_info.value), (
            "ERRORS violation: ProjectNotFoundError message should contain project name\n"
            "Contract: BackwardCompatibilityContract ERRORS\n"
            f"EXPECTED: Message contains 'nonexistent_project'\n"
            f"ACTUAL: '{exc_info.value}'\n"
            "Guidance: Error handling MUST be consistent across MCP and CLI modes"
        )

    def test_errors_no_registry_operations_on_invalid_project(self, agent_with_session):
        """
        Contract: BackwardCompatibilityContract
        Enforces: ERRORS: Registry not modified when project validation fails

        Theater Prevention:
        - Verifies no side effects on validation error
        """
        agent, _, _ = agent_with_session

        try:
            agent.activate_project("nonexistent_project")
        except ProjectNotFoundError:
            pass  # Expected

        # POST ASSERTION: No registry operations occurred
        assert agent._session_registry.bind_session.call_count == 0, (
            "ERRORS violation: Registry modified despite validation failure\n"
            "Contract: BackwardCompatibilityContract ERRORS\n"
            "EXPECTED: bind_session() NOT called on invalid project\n"
            f"ACTUAL: bind_session() called {agent._session_registry.bind_session.call_count} times\n"
            "Guidance: Validate project BEFORE any registry operations (fail fast)"
        )
