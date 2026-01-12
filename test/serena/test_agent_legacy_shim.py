"""
Adversarial TDD tests for SerenaAgent.activate_project() legacy shim.

Contract: REQ-5b
Component: Legacy activate_project() delegation layer

Test Writer is BLIND to implementation - error messages are specifications.
Coder is BLIND to test source - implements from error messages only.

Requirements tested:
- REQ-5b: Legacy activate_project() delegates to activate_session_project() when session exists
- REQ-BACKWARDS-COMPAT: Legacy API surface preserved (no breaking signature changes)
- REQ-FALLBACK: Without session context, legacy activate_project() works as before

Behavioral Contract:
    PRE: project_name exists in self.serena_config.projects

    POST: If session context exists → delegates to activate_session_project(project_name)
    POST: If no session context → legacy behavior (activates project globally)
    POST: Legacy state (self._active_project) mutated ONLY in legacy mode (no session)

    INV: No cross-session side effects
    INV: Session-based activation preserves stateless contract

    ERRORS:
    - ProjectNotFoundError: project_name not registered
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.serena.agent import ProjectNotFoundError, SerenaAgent

# =============================================================================
# TEST FIXTURES (reuse patterns from test_agent_session_activation.py)
# =============================================================================


@pytest.fixture
def mock_session_registry():
    """Mock SessionRegistry following contract."""
    registry = MagicMock()
    registry.bind_session = MagicMock()
    registry.unbind_session = MagicMock()
    registry.get_session = MagicMock(return_value=None)
    return registry


@pytest.fixture
def mock_serena_config(tmp_path: Path):
    """Mock SerenaConfig with two test projects."""
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
    """Create SerenaAgent with mocked dependencies and active session."""
    from contextvars import ContextVar

    config, project_a, project_b = mock_serena_config

    # Create agent with dependency injection (bypasses LanguageServerManager)
    agent = SerenaAgent(
        serena_config=config,
        session_registry=mock_session_registry,
        session_bridge=MagicMock(),  # Trigger multi-project path
        lsp_pool=MagicMock()         # Trigger multi-project path
    )

    # Set current session ID via ContextVar
    agent._current_session_id = ContextVar("session_id", default=None)
    agent._current_session_id.set("test-session-456")

    yield agent, project_a, project_b


@pytest.fixture
def agent_without_session(mock_session_registry, mock_serena_config):
    """Create SerenaAgent without active session (legacy mode)."""
    from contextvars import ContextVar

    config, project_a, project_b = mock_serena_config

    # Create agent with dependency injection (bypasses LanguageServerManager)
    agent = SerenaAgent(
        serena_config=config,
        session_registry=mock_session_registry,
        session_bridge=MagicMock(),  # Trigger multi-project path
        lsp_pool=MagicMock()         # Trigger multi-project path
    )

    # Initialize ContextVar but do NOT set a session
    agent._current_session_id = ContextVar("session_id", default=None)

    yield agent, project_a, project_b


# =============================================================================
# TESTS: activate_project() Legacy Shim - 3 tests
# =============================================================================


def test_activate_project_delegates_when_session_present(agent_with_session):
    """
    Contract: activate_project()
    Enforces: POST: Delegates to activate_session_project() when session context exists
    Requirement: REQ-5b - Legacy API delegates to new session-aware path

    CRITICAL: Delegation means registry state changes, NOT legacy state mutation.
    """
    agent, project_a, _ = agent_with_session

    # PRE: Verify session context exists
    assert agent._current_session_id.get() == "test-session-456", (
        "Test setup error: Session context must be present. "
        "EXPECTED: _current_session_id.get() == 'test-session-456'. "
        f"ACTUAL: {agent._current_session_id.get()}. "
        "FIX: Use agent_with_session fixture (sets ContextVar)."
    )

    # ACTION: Call legacy activate_project() API
    agent.activate_project("project_a")

    # POST: SessionRegistry.bind_session was called (delegation occurred)
    assert agent._session_registry.bind_session.call_count == 1, (
        "POST violation: Legacy activate_project() must delegate to session-aware path when session exists (REQ-5b). "
        "EXPECTED: SessionRegistry.bind_session called exactly once via activate_session_project(). "
        f"ACTUAL: bind_session called {agent._session_registry.bind_session.call_count} times. "
        "GUIDANCE: Delegation contract - when session context present, MUST invoke activate_session_project(). "
        "Check session context (ContextVar) and conditionally delegate. "
        "Session binding MUST go through SessionRegistry.bind_session. "
        "Implementation free to choose: if/else on session context, wrapper method, strategy pattern."
    )

    # POST: bind_session called with correct session_id and workspace
    call_args = agent._session_registry.bind_session.call_args
    session_id_arg = call_args[0][0]
    workspace_arg = call_args[0][1]

    assert session_id_arg == "test-session-456", (
        "POST violation: Delegated call must use current session_id from ContextVar. "
        "EXPECTED: session_id = 'test-session-456' (from _current_session_id). "
        f"ACTUAL: session_id = {session_id_arg!r}. "
        "GUIDANCE: Delegation MUST preserve session context - pass current session_id to registry. "
        "Session ID from ContextVar, NOT hardcoded or derived from project."
    )

    assert workspace_arg == project_a.project_root, (
        "POST violation: Delegated call must bind to correct workspace. "
        f"EXPECTED: workspace_root = {project_a.project_root}. "
        f"ACTUAL: workspace_arg = {workspace_arg}. "
        "GUIDANCE: Delegation MUST resolve project_name to workspace_root correctly. "
        "Use config.get_project(project_name).project_root for workspace resolution."
    )


def test_activate_project_backwards_compatible(agent_without_session):
    """
    Contract: activate_project()
    Enforces: POST: Legacy behavior when no session context (backward compatibility)
    Requirement: REQ-BACKWARDS-COMPAT, REQ-FALLBACK

    CRITICAL: Without session, legacy activate_project() operates in global mode (no registry).
    """
    agent, project_a, _ = agent_without_session

    # PRE: Verify no session context (legacy CLI mode)
    assert agent._current_session_id.get() is None, (
        "Test setup error: No session context should exist for legacy mode test. "
        "EXPECTED: _current_session_id.get() == None. "
        f"ACTUAL: {agent._current_session_id.get()}. "
        "FIX: Use agent_without_session fixture (no ContextVar set)."
    )

    # ACTION: Call legacy activate_project() without session
    agent.activate_project("project_a")

    # POST: SessionRegistry.bind_session was NOT called (legacy path, no delegation)
    assert agent._session_registry.bind_session.call_count == 0, (
        "POST violation: Legacy activate_project() without session MUST NOT invoke registry (REQ-FALLBACK). "
        "EXPECTED: bind_session never called (legacy global mode). "
        f"ACTUAL: bind_session called {agent._session_registry.bind_session.call_count} times. "
        "GUIDANCE: Backward compatibility contract - NO session context = global activation (no registry). "
        "Check session context (ContextVar) - if None, use legacy behavior (NO registry operations). "
        "Legacy path preserves pre-multi-project behavior. "
        "Implementation free to choose: conditional delegation, fallback path, mode switch."
    )

    # POST: Project was activated (some state change occurred, even if not registry)
    # NOTE: We cannot verify _active_project mutation because we're BLIND to implementation.
    # But we can verify no errors occurred and registry remains clean.
    assert agent._session_registry.unbind_session.call_count == 0, (
        "POST violation: Legacy mode should not unbind sessions (no sessions involved). "
        "EXPECTED: unbind_session never called. "
        f"ACTUAL: unbind_session called {agent._session_registry.unbind_session.call_count} times. "
        "GUIDANCE: Legacy path operates globally - NO registry operations (bind or unbind)."
    )


def test_activate_project_unknown_project_raises(agent_with_session):
    """
    Contract: activate_project()
    Enforces: ERRORS: ProjectNotFoundError for unknown project
    Requirement: REQ-CONFIG - Project validation before activation

    CRITICAL: Error handling must be consistent across delegation and legacy paths.
    """
    agent, _, _ = agent_with_session

    # ACTION + ASSERTION: Call with nonexistent project raises ProjectNotFoundError
    with pytest.raises(ProjectNotFoundError) as exc_info:
        agent.activate_project("nonexistent_project")

    # POST: Error message contains project_name
    error_message = str(exc_info.value)
    assert "nonexistent_project" in error_message, (
        "ERROR contract violation: ProjectNotFoundError message must include project_name. "
        "EXPECTED: Error message contains 'nonexistent_project'. "
        f"ACTUAL: {error_message}. "
        "GUIDANCE: Project validation MUST raise ProjectNotFoundError with project_name. "
        "Error propagation MUST work for both delegation path (with session) and legacy path (no session). "
        "Use config.get_project(project_name) for validation - it raises ProjectNotFoundError. "
        "Implementation free to choose: validate before delegation, validate in delegate, config-level validation."
    )

    # POST: No registry operations occurred (error before delegation)
    assert agent._session_registry.bind_session.call_count == 0, (
        "ERROR contract violation: Registry operations must NOT occur when project validation fails. "
        "EXPECTED: bind_session never called (error before delegation). "
        f"ACTUAL: bind_session called {agent._session_registry.bind_session.call_count} times. "
        "GUIDANCE: Validation-before-action contract - verify project exists BEFORE registry operations. "
        "Fail fast on invalid input to preserve system consistency."
    )
