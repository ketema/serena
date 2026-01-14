"""
Contract Tests: ProjectLanguageRoutingContract
Contract Reference: contracts/project_language_routing_contract.py

These tests enforce deterministic language routing based on project configuration.
"""

from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig
from serena.project import Project
from solidlsp.ls_config import Language


def _make_project(tmp_path: Path, languages: list[Language]) -> Project:
    config = ProjectConfig(
        project_name="routing_test_project",
        languages=languages,
    )
    return Project(project_root=str(tmp_path), project_config=config)


class TestProjectLanguageRoutingContract:
    """
    Tests for ProjectLanguageRoutingContract.
    """

    def test_post_returns_language_when_match(self, tmp_path: Path) -> None:
        """
        Contract: ProjectLanguageRoutingContract
        Enforces: POST-1 (returns Language when file matches configured matcher)
        """
        project = _make_project(tmp_path, [Language.PYTHON, Language.RUST])

        language = project.get_language_for_file("src/main.py")

        assert language == Language.PYTHON, (
            "POST-1 violation: file routing did not return expected Language\n"
            "Contract: ProjectLanguageRoutingContract POST-1\n"
            "EXPECTED: Language.PYTHON for file 'src/main.py'\n"
            f"ACTUAL: {language}\n"
            "Guidance: Match configured language by filename extension"
        )

    def test_post_returns_none_for_unknown_extension(self, tmp_path: Path) -> None:
        """
        Contract: ProjectLanguageRoutingContract
        Enforces: POST-2 (returns None when no configured language matches)
        """
        project = _make_project(tmp_path, [Language.PYTHON, Language.RUST])

        language = project.get_language_for_file("README.md")

        assert language is None, (
            "POST-2 violation: file routing returned Language for unsupported file\n"
            "Contract: ProjectLanguageRoutingContract POST-2\n"
            "EXPECTED: None for file 'README.md'\n"
            f"ACTUAL: {language}\n"
            "Guidance: Return None when no configured language matcher applies"
        )

    def test_post_returns_none_when_language_not_configured(self, tmp_path: Path) -> None:
        """
        Contract: ProjectLanguageRoutingContract
        Enforces: POST-2 (returns None when language not configured)
        """
        project = _make_project(tmp_path, [Language.PYTHON])

        language = project.get_language_for_file("src/main.rs")

        assert language is None, (
            "POST-2 violation: file routed to language not configured for project\n"
            "Contract: ProjectLanguageRoutingContract POST-2\n"
            "EXPECTED: None for file 'src/main.rs' when only Python configured\n"
            f"ACTUAL: {language}\n"
            "Guidance: Only configured languages may be returned"
        )

    def test_errors_empty_path_raises_valueerror(self, tmp_path: Path) -> None:
        """
        Contract: ProjectLanguageRoutingContract
        Enforces: ERRORS-1 (ValueError if file_path is empty)
        """
        project = _make_project(tmp_path, [Language.PYTHON])

        with pytest.raises(ValueError) as exc_info:
            project.get_language_for_file("")

        assert "file_path" in str(exc_info.value), (
            "ERRORS-1 violation: ValueError message should reference file_path\n"
            "Contract: ProjectLanguageRoutingContract ERRORS-1\n"
            "EXPECTED: Message containing 'file_path'\n"
            f"ACTUAL: '{exc_info.value}'\n"
            "Guidance: Error message must indicate empty file_path"
        )
