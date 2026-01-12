"""
Adversarial TDD tests for SerenaAgent.activate_session_project().

Contract: REQ-4, REQ-STATELESS, REQ-IDEMPOTENCY, REQ-4b, REQ-CONFIG
Component: Session-project binding (stateless wrapper over SessionRegistry)

Test Writer is BLIND to implementation - error messages are specifications.
Coder is BLIND to test source - implements from error messages only.

Requirements tested:
- REQ-4: activate_session_project(project_name) binds CURRENT session
- REQ-STATELESS: Does NOT mutate self._active_project (legacy state)
- REQ-IDEMPOTENCY: Multiple calls for same project = no-op
- REQ-4b: Does NOT unbind other sessions
- REQ-CONFIG: Resolves project via self.serena_config.get_project()

Behavioral Contract:
    PRE: project_name exists in self.serena_config.projects
    PRE: Current session exists (from ContextVar) - raises ValueError if not

    POST: SessionRegistry.bind_session called with (session_id, project.root)
    POST: Legacy state (self._active_project) is UNTOUCHED
    POST: If session already bound to SAME workspace_root → no-op (idempotent)
    POST: If session bound to DIFFERENT workspace → unbind old, bind new

    INV: No side effects on other session_ids
    INV: Thread-safe via SessionRegistry lock

    ERRORS:
    - ValueError: No current session (PRE violation)
    - ProjectNotFoundError: project_name not registered
"""

import threading
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
    agent._current_session_id.set("test-session-123")

    yield agent, project_a, project_b


@pytest.fixture
def agent_without_session(mock_session_registry, mock_serena_config):
    """Create SerenaAgent without active session."""
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
# TESTS: activate_session_project() - 8 tests
# =============================================================================


def test_activate_session_project_binds_registry(agent_with_session):
    """
    Contract: activate_session_project()
    Enforces: POST: SessionRegistry.bind_session called with (session_id, project.root)
    Requirement: REQ-4 - Binds CURRENT session to project workspace
    """
    agent, project_a, _ = agent_with_session

    # ACTION: Activate project_a for current session
    agent.activate_session_project("project_a")

    # POST: SessionRegistry.bind_session was called EXACTLY ONCE
    assert agent._session_registry.bind_session.call_count == 1, (
        "POST violation: SessionRegistry.bind_session must be called exactly once "
        "when activating session-project binding (REQ-4). "
        "EXPECTED: bind_session called with (session_id, workspace_root, source). "
        f"ACTUAL: bind_session called {agent.session_registry.bind_session.call_count} times. "
        "GUIDANCE: Session-project binding MUST invoke registry exactly once with (session_id, workspace, source). "
        "Session ID from current context, workspace from project config, source='explicit' for user action."
    )

    # POST: bind_session called with correct arguments
    call_args = agent._session_registry.bind_session.call_args
    session_id_arg = call_args[0][0]
    workspace_arg = call_args[0][1]
    source_arg = call_args[1].get("source", call_args[0][2] if len(call_args[0]) > 2 else None)

    assert session_id_arg == "test-session-123", (
        "POST violation: bind_session must receive current session_id from ContextVar. "
        "EXPECTED: session_id = 'test-session-123' (from _current_session_id ContextVar). "
        f"ACTUAL: session_id = {session_id_arg!r}. "
        "GUIDANCE: Session ID MUST match current ContextVar value. "
        "Implementation free to choose: direct ContextVar access, wrapper method, session context manager."
    )

    assert workspace_arg == project_a.project_root, (
        "POST violation: bind_session must receive project's workspace_root. "
        f"EXPECTED: workspace_root = {project_a.project_root}. "
        f"ACTUAL: workspace_arg = {workspace_arg}. "
        "GUIDANCE: Workspace MUST be the absolute path from project config for given project_name. "
        "Implementation free to choose: config lookup, project cache, registry query."
    )

    assert source_arg == "explicit", (
        "POST violation: bind_session source must be 'explicit' for user-initiated activation. "
        f"EXPECTED: source = 'explicit'. "
        f"ACTUAL: source = {source_arg!r}. "
        "GUIDANCE: Source MUST be 'explicit' (user action) NOT 'auto' (system detection). "
        "Contract: activate_session_project is user-initiated, not auto-discovery."
    )


def test_activate_session_project_preserves_legacy_state(agent_with_session):
    """
    Contract: activate_session_project()
    Enforces: POST: Legacy state (self._active_project) is UNTOUCHED
    Requirement: REQ-STATELESS - Does NOT mutate self._active_project

    CRITICAL: This is stateless session binding. Legacy _active_project remains for backward compat.
    """
    agent, project_a, _ = agent_with_session

    # PRE: Set legacy state to a different project
    agent._active_project = MagicMock()
    agent._active_project.project_name = "legacy_project"
    original_active = agent._active_project

    # ACTION: Activate project_a for current session
    agent.activate_session_project("project_a")

    # POST: Legacy _active_project is UNCHANGED
    assert agent._active_project is original_active, (
        "POST violation: activate_session_project must NOT mutate self._active_project (REQ-STATELESS). "
        "EXPECTED: self._active_project unchanged (still 'legacy_project'). "
        f"ACTUAL: self._active_project changed to {agent._active_project}. "
        "GUIDANCE: Stateless binding contract - MUST NOT mutate legacy state (_active_project). "
        "Session binding is orthogonal to project activation. "
        "ONLY registry operations permitted, NO side effects on agent's project state."
    )

    assert agent._active_project.project_name == "legacy_project", (
        "POST violation: Legacy project state was modified during session activation. "
        "EXPECTED: _active_project.project_name = 'legacy_project' (unchanged). "
        f"ACTUAL: _active_project.project_name = {agent._active_project.project_name}. "
        "GUIDANCE: Session binding is orthogonal to legacy project activation. "
        "activate_session_project delegates to SessionRegistry, nothing else."
    )


def test_activate_session_project_idempotent(agent_with_session):
    """
    Contract: activate_session_project()
    Enforces: POST: If session already bound to SAME workspace_root → no-op (idempotent)
    Requirement: REQ-IDEMPOTENCY - Multiple calls for same project = no-op
    """
    agent, project_a, _ = agent_with_session

    # SETUP: Mock get_session to return existing binding to project_a
    mock_context = MagicMock()
    mock_context.workspace_root = project_a.project_root
    agent._session_registry.get_session.return_value = mock_context

    # ACTION: Activate same project twice
    agent.activate_session_project("project_a")
    agent.activate_session_project("project_a")

    # POST: bind_session called ONCE only (second call is no-op)
    # NOTE: First call creates binding, second call detects existing binding and skips
    assert agent._session_registry.bind_session.call_count <= 1, (
        "POST violation: Idempotency broken - session already bound to same workspace. "
        "EXPECTED: bind_session called at most once (second call should be no-op). "
        f"ACTUAL: bind_session called {agent._session_registry.bind_session.call_count} times. "
        "GUIDANCE: Idempotency contract - rebinding to SAME workspace MUST be no-op. "
        "Check existing binding before registry operation. "
        "If existing.workspace_root == target_workspace → SKIP operation. "
        "Implementation free to choose: query-then-bind, conditional binding, registry-level idempotency."
    )


def test_activate_session_project_isolation(agent_with_session):
    """
    Contract: activate_session_project()
    Enforces: INV: No side effects on other session_ids
    Requirement: REQ-4b - Does NOT unbind other sessions
    """
    agent, project_a, _ = agent_with_session

    # ACTION: Activate project_a for current session
    agent.activate_session_project("project_a")

    # INV: unbind_session was NEVER called (other sessions untouched)
    assert agent._session_registry.unbind_session.call_count == 0, (
        "INV violation: activate_session_project must NOT unbind other sessions (REQ-4b). "
        "EXPECTED: unbind_session never called (session isolation preserved). "
        f"ACTUAL: unbind_session called {agent.session_registry.unbind_session.call_count} times. "
        "GUIDANCE: Session activation MUST preserve isolation - NO unbinding of other sessions. "
        "Operation affects ONLY current session. Other sessions remain untouched. "
        "Exception: rebinding same session to different workspace (unbind old, bind new)."
    )


def test_activate_session_project_rebinds(agent_with_session):
    """
    Contract: activate_session_project()
    Enforces: POST: If session bound to DIFFERENT workspace → unbind old, bind new
    Requirement: Rebinding same session to different project
    """
    agent, project_a, project_b = agent_with_session

    # SETUP: Mock session already bound to project_b
    mock_context = MagicMock()
    mock_context.workspace_root = project_b.project_root
    agent._session_registry.get_session.return_value = mock_context

    # ACTION: Rebind to project_a (different workspace)
    agent.activate_session_project("project_a")

    # POST: unbind_session called to remove old binding
    assert agent._session_registry.unbind_session.call_count == 1, (
        "POST violation: Rebinding to different workspace requires unbinding old workspace. "
        "EXPECTED: unbind_session called once to remove old project_b binding. "
        f"ACTUAL: unbind_session called {agent.session_registry.unbind_session.call_count} times. "
        "GUIDANCE: Rebinding contract - DIFFERENT workspace requires unbind-then-bind sequence. "
        "If existing.workspace_root != target_workspace → unbind old BEFORE binding new. "
        "Implementation free to choose: conditional unbind, atomic rebind, registry-level rebind."
    )

    unbind_call_args = agent._session_registry.unbind_session.call_args
    unbind_session_id = unbind_call_args[0][0]

    assert unbind_session_id == "test-session-123", (
        "POST violation: unbind_session must receive current session_id. "
        "EXPECTED: unbind_session('test-session-123'). "
        f"ACTUAL: unbind_session({unbind_session_id!r}). "
        "GUIDANCE: Unbind MUST target current session only, not other sessions."
    )

    # POST: bind_session called with new workspace
    assert agent._session_registry.bind_session.call_count == 1, (
        "POST violation: After unbinding old workspace, must bind to new workspace. "
        "EXPECTED: bind_session called once with project_a.project_root. "
        f"ACTUAL: bind_session called {agent.session_registry.bind_session.call_count} times. "
        "GUIDANCE: Rebinding sequence - unbind old THEN bind new (atomic operation)."
    )

    bind_call_args = agent._session_registry.bind_session.call_args
    new_workspace = bind_call_args[0][1]

    assert new_workspace == project_a.project_root, (
        "POST violation: bind_session must receive NEW workspace (project_a). "
        f"EXPECTED: workspace_root = {project_a.project_root}. "
        f"ACTUAL: workspace_root = {new_workspace}. "
        "GUIDANCE: New binding MUST use target workspace, not old workspace."
    )


def test_raises_without_session(agent_without_session):
    """
    Contract: activate_session_project()
    Enforces: PRE: Current session exists (from ContextVar) - raises ValueError if not
    Requirement: Session required for activation
    """
    agent, project_a, _ = agent_without_session

    # PRE: No session set (ContextVar is None)
    assert agent._current_session_id.get() is None, (
        "Test setup error: _current_session_id should be None for this test. "
        "EXPECTED: agent._current_session_id.get() == None. "
        f"ACTUAL: {agent._current_session_id.get()}. "
        "FIX: Use agent_without_session fixture (does not set ContextVar)."
    )

    # ACTION + ASSERTION: Calling without session raises ValueError
    with pytest.raises(ValueError) as exc_info:
        agent.activate_session_project("project_a")

    # POST: ValueError message indicates missing session
    error_message = str(exc_info.value).lower()
    assert "session" in error_message, (
        "PRE violation: ValueError message must mention 'session' for clarity. "
        "EXPECTED: Error message contains 'session' keyword. "
        f"ACTUAL: {exc_info.value}. "
        "GUIDANCE: PRE violation - operation requires active session context. "
        "Error MUST clearly indicate missing session (not config error or network error). "
        "Message should mention 'session' keyword for diagnosability."
    )


def test_raises_invalid_project(agent_with_session):
    """
    Contract: activate_session_project()
    Enforces: ProjectNotFoundError: project_name not registered
    Requirement: REQ-CONFIG - Resolves project via self.serena_config.get_project()
    """
    agent, _, _ = agent_with_session

    # ACTION + ASSERTION: Calling with invalid project raises ProjectNotFoundError
    with pytest.raises(ProjectNotFoundError) as exc_info:
        agent.activate_session_project("nonexistent_project")

    # POST: Error message mentions the invalid project name
    error_message = str(exc_info.value)
    assert "nonexistent_project" in error_message, (
        "PRE violation: ProjectNotFoundError message must include project_name. "
        "EXPECTED: Error message contains 'nonexistent_project'. "
        f"ACTUAL: {error_message}. "
        "GUIDANCE: Project resolution failure MUST raise ProjectNotFoundError with project_name. "
        "Error should propagate from config lookup (not be caught/translated). "
        "Implementation free to choose: direct config query, project cache lookup, registry check."
    )


def test_thread_safety(agent_with_session):
    """
    Contract: activate_session_project()
    Enforces: INV: Thread-safe via SessionRegistry lock
    Requirement: Concurrent activations must be atomic
    """
    agent, project_a, project_b = agent_with_session

    # SETUP: Track call order for bind_session
    bind_calls = []

    def track_bind_call(session_id, workspace_root, source="explicit"):
        bind_calls.append((session_id, workspace_root))

    agent._session_registry.bind_session.side_effect = track_bind_call

    # SETUP: Create two threads activating different projects
    def activate_a():
        agent._current_session_id.set("thread-a-session")
        agent.activate_session_project("project_a")

    def activate_b():
        agent._current_session_id.set("thread-b-session")
        agent.activate_session_project("project_b")

    thread_a = threading.Thread(target=activate_a)
    thread_b = threading.Thread(target=activate_b)

    # ACTION: Run both threads concurrently
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    # INV: Both bind_session calls completed (no data races)
    assert len(bind_calls) == 2, (
        "INV violation: Thread-safety broken - some activations were lost. "
        "EXPECTED: Both bind_session calls executed (2 total). "
        f"ACTUAL: {len(bind_calls)} calls recorded. "
        "GUIDANCE: Thread-safety guaranteed by SessionRegistry contract (threading.Lock). "
        "activate_session_project delegates to registry - NO additional locking required. "
        "Concurrent activations MUST NOT race, lose data, or corrupt state."
    )

    # INV: Both sessions bound to correct workspaces
    sessions_to_workspaces = dict(bind_calls)

    assert "thread-a-session" in sessions_to_workspaces, (
        "INV violation: Thread A session was not bound. "
        "EXPECTED: 'thread-a-session' in bind_calls. "
        f"ACTUAL: bind_calls = {bind_calls}. "
        "GUIDANCE: Each thread MUST bind its OWN session (from ContextVar), not other threads' sessions."
    )

    assert "thread-b-session" in sessions_to_workspaces, (
        "INV violation: Thread B session was not bound. "
        "EXPECTED: 'thread-b-session' in bind_calls. "
        f"ACTUAL: bind_calls = {bind_calls}. "
        "GUIDANCE: Each thread MUST bind its OWN session (from ContextVar), not other threads' sessions."
    )

    assert sessions_to_workspaces["thread-a-session"] == project_a.project_root, (
        "INV violation: Thread A bound to wrong workspace. "
        f"EXPECTED: thread-a-session → {project_a.project_root}. "
        f"ACTUAL: thread-a-session → {sessions_to_workspaces['thread-a-session']}. "
        "GUIDANCE: Each thread MUST resolve correct project (project_a vs project_b) from project_name arg."
    )

    assert sessions_to_workspaces["thread-b-session"] == project_b.project_root, (
        "INV violation: Thread B bound to wrong workspace. "
        f"EXPECTED: thread-b-session → {project_b.project_root}. "
        f"ACTUAL: thread-b-session → {sessions_to_workspaces['thread-b-session']}. "
        "GUIDANCE: Each thread MUST resolve correct project (project_a vs project_b) from project_name arg."
    )
