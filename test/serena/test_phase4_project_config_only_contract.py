"""
Phase 4 Cycle 2 - Project Config-Only Contract Tests

Contract: contracts/project_config_only_contract.py
Focus: Project exposes configuration only, no LSP lifecycle ownership.
"""

from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig
from serena.project import Project
from solidlsp.ls_config import Language


@pytest.fixture
def project(tmp_path: Path) -> Project:
    project_root = tmp_path / "config_only_project"
    project_root.mkdir()
    config = ProjectConfig.autogenerate(project_root, languages=[Language.PYTHON], save_to_disk=True)
    return Project(project_root=str(project_root), project_config=config)


def test_project_has_no_lsp_lifecycle_methods(project: Project) -> None:
    assert not hasattr(project, "create_lsp_manager"), (
        "INV-1 violation: Project has create_lsp_manager method\n"
        "Contract: ProjectConfigOnlyContract\n"
        "EXPECTED: create_lsp_manager does NOT exist\n"
        "ACTUAL: method exists\n"
        "GUIDANCE: Remove LSP lifecycle from Project (GlobalLanguageServerPool owns it)."
    )
    assert not hasattr(project, "create_language_server"), (
        "INV-2 violation: Project has create_language_server method\n"
        "Contract: ProjectConfigOnlyContract\n"
        "EXPECTED: create_language_server does NOT exist\n"
        "ACTUAL: method exists\n"
        "GUIDANCE: Remove LSP lifecycle from Project."
    )
    assert not hasattr(project, "language_server_manager"), (
        "INV-3 violation: Project has language_server_manager attribute\n"
        "Contract: ProjectConfigOnlyContract\n"
        "EXPECTED: language_server_manager does NOT exist\n"
        "ACTUAL: attribute exists\n"
        "GUIDANCE: Project should not own LSP manager."
    )


def test_project_exposes_configuration_only(project: Project) -> None:
    assert project.project_root, "Project.project_root must be set"
    assert project.project_name, "Project.project_name must be set"
    assert isinstance(project.languages, list), "Project.languages must be a list"
    assert project.project_config is not None, "Project.project_config must exist"
