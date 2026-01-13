"""
Phase 4 Cycle 1 - SerenaAgent Statelessness Contract Tests

Contract: contracts/serena_agent_stateless_contract.py
Focus: ContextVar session resolution, no legacy state, safe activation/deactivation.
"""

import logging
from contextvars import copy_context
from pathlib import Path

import pytest

from serena.agent import ProjectNotFoundError, SerenaAgent
from serena.config.serena_config import LanguageBackend, ProjectConfig, SerenaConfig
from serena.session_context import get_current_session, set_current_session
from serena.session_registry import SessionRegistry
from solidlsp.ls_config import Language


@pytest.fixture
def serena_config() -> SerenaConfig:
    return SerenaConfig(
        projects=[],
        gui_log_window_enabled=False,
        web_dashboard=False,
        web_dashboard_open_on_launch=False,
        web_dashboard_listen_address="127.0.0.1",
        log_level=logging.INFO,
        language_backend=LanguageBackend.LSP,
    )


@pytest.fixture
def session_registry() -> SessionRegistry:
    return SessionRegistry()


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ProjectConfig.autogenerate(workspace, languages=[Language.PYTHON], save_to_disk=True)
    return workspace


def test_inv1_no_active_project_field(serena_config: SerenaConfig, session_registry: SessionRegistry) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    assert not hasattr(agent, "_active_project"), (
        "INV-1 violation: SerenaAgent has prohibited legacy field '_active_project'\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: _active_project does not exist\n"
        "ACTUAL: _active_project present on instance\n"
        "GUIDANCE: Remove legacy instance state and resolve via SessionRegistry + ContextVar."
    )


def test_inv2_no_current_session_id_field(serena_config: SerenaConfig, session_registry: SessionRegistry) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    assert not hasattr(agent, "_current_session_id"), (
        "INV-2 violation: SerenaAgent has prohibited legacy field '_current_session_id'\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: _current_session_id does not exist\n"
        "ACTUAL: _current_session_id present on instance\n"
        "GUIDANCE: Use ContextVar session context, not instance state."
    )


def test_inv3_session_via_contextvar(
    serena_config: SerenaConfig,
    session_registry: SessionRegistry,
    workspace_root: Path,
) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    session_id = "sess-1"

    session = session_registry.bind_session(session_id, workspace_root, source="explicit")
    set_current_session(session)

    current = agent.get_current_session_context()
    assert current is not None and current.session_id == session_id, (
        "INV-3 violation: Session not retrievable via ContextVar\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: get_current_session_context() returns SessionContext with session_id 'sess-1'\n"
        f"ACTUAL: {current}\n"
        "GUIDANCE: Agent must read current session from ContextVar, not instance state."
    )


def test_inv5_request_scoped_binding_isolated_between_contexts(
    serena_config: SerenaConfig,
    session_registry: SessionRegistry,
    workspace_root: Path,
) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    session = session_registry.bind_session("sess-ctx", workspace_root, source="explicit")
    set_current_session(session)

    other_context = copy_context()
    other_value = other_context.run(get_current_session)

    assert other_value is None, (
        "INV-5 violation: ContextVar leaked across async contexts\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: other async context sees None\n"
        f"ACTUAL: {other_value}\n"
        "GUIDANCE: ContextVar provides per-context isolation; no cross-context leakage."
    )


def test_get_active_project_returns_project_when_session_bound(
    serena_config: SerenaConfig,
    session_registry: SessionRegistry,
    workspace_root: Path,
) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    session = session_registry.bind_session("sess-project", workspace_root, source="explicit")
    set_current_session(session)

    project = agent.get_active_project()
    assert project is not None and Path(project.project_root) == workspace_root, (
        "POST-1 violation: get_active_project() did not return Project for bound session\n"
        "Contract: SerenaAgentStatelessContract\n"
        f"EXPECTED: Project.project_root == {workspace_root}\n"
        f"ACTUAL: {getattr(project, 'project_root', None)}\n"
        "GUIDANCE: Resolve Project from SessionRegistry workspace_root via Project.load()."
    )


def test_get_active_project_returns_none_without_session(
    serena_config: SerenaConfig,
    session_registry: SessionRegistry,
) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    assert agent.get_active_project() is None, (
        "POST-2 violation: get_active_project() must return None when no session\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: None\n"
        "ACTUAL: non-None project returned\n"
        "GUIDANCE: No session bound => no active project."
    )


def test_get_active_project_or_raise_raises_without_session(
    serena_config: SerenaConfig,
    session_registry: SessionRegistry,
) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    with pytest.raises(ProjectNotFoundError):
        agent.get_active_project_or_raise()


def test_activate_session_project_binds_and_sets_context(
    serena_config: SerenaConfig,
    session_registry: SessionRegistry,
    workspace_root: Path,
) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    session_id = "sess-activate"

    project = agent.activate_session_project(session_id, workspace_root, source="explicit")

    assert session_registry.get_session(session_id) is not None, (
        "POST-1 violation: SessionRegistry.bind_session() not called\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: registry has session after activation\n"
        "ACTUAL: session missing\n"
        "GUIDANCE: activate_session_project must bind session via registry."
    )
    assert get_current_session() is not None and get_current_session().session_id == session_id, (
        "POST-2 violation: ContextVar not set to new SessionContext\n"
        "Contract: SerenaAgentStatelessContract\n"
        f"EXPECTED: get_current_session().session_id == '{session_id}'\n"
        f"ACTUAL: {get_current_session()}\n"
        "GUIDANCE: set_current_session must be called with bound SessionContext."
    )
    assert project.project_root == str(workspace_root), (
        "POST-3 violation: Project loaded from wrong workspace_root\n"
        "Contract: SerenaAgentStatelessContract\n"
        f"EXPECTED: {workspace_root}\n"
        f"ACTUAL: {project.project_root}\n"
        "GUIDANCE: Project.load must use workspace_root from SessionContext."
    )


def test_activate_session_project_exception_safety_unbinds_and_clears(
    serena_config: SerenaConfig,
    session_registry: SessionRegistry,
    workspace_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)

    def _raise_load(_: Path, autogenerate: bool = True):
        raise RuntimeError("boom")

    monkeypatch.setattr("serena.project.Project.load", _raise_load)

    with pytest.raises(ProjectNotFoundError):
        agent.activate_session_project("sess-error", workspace_root, source="explicit")

    assert session_registry.get_session("sess-error") is None, (
        "INV (Exception Safety) violation: session was not unbound on error\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: session removed from registry\n"
        "ACTUAL: session still present\n"
        "GUIDANCE: On error, unbind session before returning/raising."
    )
    assert get_current_session() is None, (
        "INV (Exception Safety) violation: ContextVar not cleared on error\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: get_current_session() returns None\n"
        f"ACTUAL: {get_current_session()}\n"
        "GUIDANCE: Clear ContextVar on error path."
    )


def test_deactivate_session_unbinds_and_clears(
    serena_config: SerenaConfig,
    session_registry: SessionRegistry,
    workspace_root: Path,
) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    session = session_registry.bind_session("sess-deactivate", workspace_root, source="explicit")
    set_current_session(session)

    agent.deactivate_session("sess-deactivate")

    assert session_registry.get_session("sess-deactivate") is None, (
        "POST-1 violation: SessionRegistry.unbind_session() not called\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: session removed from registry\n"
        "ACTUAL: session still present\n"
        "GUIDANCE: deactivate_session must unbind from registry."
    )
    assert get_current_session() is None, (
        "POST-2 violation: ContextVar not cleared for current session\n"
        "Contract: SerenaAgentStatelessContract\n"
        "EXPECTED: get_current_session() returns None after deactivate_session\n"
        f"ACTUAL: {get_current_session()}\n"
        "GUIDANCE: Clear ContextVar when deactivating current session."
    )


def test_deactivate_session_idempotent_no_raise(
    serena_config: SerenaConfig,
    session_registry: SessionRegistry,
) -> None:
    agent = SerenaAgent(serena_config=serena_config, session_registry=session_registry)
    agent.deactivate_session("non-existent")
