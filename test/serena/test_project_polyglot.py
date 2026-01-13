"""
Tests for Project class polyglot support - Phase 1.3 integration.

Following TDD approach: Tests written FIRST before implementation.
Issue: #221 - Enable Multi-Language (Polyglot) Support in Serena
"""

import shutil
import tempfile
from pathlib import Path

from serena.config.serena_config import ProjectConfig
from serena.project import Project
from solidlsp.ls_config import Language


class TestProjectPolyglotIntegration:
    """Test Project class integration with LSPManager."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        # Create a simple polyglot project config
        self.config = ProjectConfig(
            project_name="test_polyglot_project",
            languages=[Language.PYTHON, Language.RUST, Language.HASKELL],
        )

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_project_language_property_returns_first_language(self):
        """Test that language property returns first language (backward compat)."""
        project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

        # Should return first language for backward compatibility
        assert project.language == Language.PYTHON

    def test_project_languages_property_returns_all_languages(self):
        """Test that languages property returns all languages."""
        project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

        assert hasattr(project, "languages")
        assert project.languages == [Language.PYTHON, Language.RUST, Language.HASKELL]
