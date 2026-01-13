"""
Project Config-Only Contract - Phase 4 Cycle 2

Constitutional Reference: CL12 Design by Contract
Domain: Project as pure configuration container (no LSP lifecycle ownership)
Version: 1.0
Last Updated: 2026-01-13

AUTHORITY: This contract is AUTHORITATIVE for Project configuration behavior.
Project SHALL be a pure configuration container exposing paths, settings, ignore patterns.
Project SHALL NOT own or manage LSP lifecycle (GlobalLanguageServerPool does).

Related Contracts:
- contracts/global_lsp_pool_contract.py (LSP lifecycle ownership)
- contracts/lsp_capability_adapter_contract.py (LSP configuration)
"""

from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

# =============================================================================
# LSP LIFECYCLE PROHIBITION
# =============================================================================

# These methods MUST NOT exist in Project after Phase 4 Cycle 2
# LSP lifecycle is owned by GlobalLanguageServerPool
PROHIBITED_LSP_METHODS = [
    "create_lsp_manager",      # Legacy: Creates LanguageServerManager
    "create_language_server",  # Legacy: Creates individual LSP
    "language_server_manager", # Legacy: Property returning LSP manager
]

# These methods MAY be removed or refactored (analysis-only, not hard prohibition)
LIFECYCLE_METHODS_TO_EVALUATE = [
    "add_language",    # May delegate to pool instead
    "remove_language", # May delegate to pool instead
    "shutdown",        # May need rework to not shut down LSPs
]

# These are ALLOWED (configuration-only)
ALLOWED_CONFIG_METHODS = [
    "project_name",           # Property: workspace name
    "language",               # Property: primary language
    "languages",              # Property: list of languages
    "load",                   # Class method: load Project from path
    "save_config",            # Save project.yml
    "path_to_serena_data_folder",  # Path to .serena/
    "path_to_project_yml",    # Path to project.yml
    "get_activation_message", # User-facing message
    "read_file",              # File content access
    "get_ignore_spec",        # Ignore patterns
    "is_ignored_path",        # Path filtering
    "is_path_in_project",     # Path validation
    "relative_path_exists",   # Path validation
    "validate_relative_path", # Path validation
    "gather_source_files",    # File discovery
    "search_source_files_for_pattern",  # Pattern matching
    "retrieve_content_around_line",     # Context retrieval
]


# =============================================================================
# PROJECT CONFIG DATA CONTRACT
# =============================================================================

class ProjectConfigContract:
    """
    Data contract for Project configuration values.

    PRE: project_root is absolute path to existing directory
    PRE: project.yml exists at project_root/.serena/project.yml (optional)

    POST: All configuration values are immutable after load
    POST: Configuration represents disk state at load time

    INV: Configuration does not change during Project lifetime
    INV: No LSP state stored in configuration

    ERRORS: None (data class - no methods that raise)
    """

    # Required configuration fields
    project_root: Path          # Absolute path to workspace root
    project_name: str           # Derived from project_root.name or config
    languages: list[str]        # Configured languages (strings, not LSP instances)
    ignored_paths: list[str]    # Glob patterns to ignore
    encoding: str               # File encoding (default: utf-8)

    # Optional configuration fields
    read_only: bool             # If True, editing tools disabled
    custom_settings: dict       # User-defined settings from project.yml


# =============================================================================
# PROJECT CONFIG-ONLY BEHAVIORAL CONTRACT
# =============================================================================

@runtime_checkable
class ProjectConfigOnlyContract(Protocol):
    """
    Contract for Project as pure configuration container.

    CLASS INVARIANTS:
    - INV-1: NO create_lsp_manager method exists
    - INV-2: NO create_language_server method exists
    - INV-3: NO language_server_manager property exists
    - INV-4: Project stores ONLY configuration (no LSP instances)
    - INV-5: All LSP operations delegate to GlobalLanguageServerPool

    SEPARATION OF CONCERNS:
    - Project: Configuration, paths, ignore patterns, file access
    - GlobalLanguageServerPool: LSP lifecycle, acquire/release, pooling

    ENFORCEMENT (CL12-A):
    - Tests verify prohibited methods do not exist via hasattr() check
    - Static analysis can grep for prohibited patterns
    - Code review checklist includes LSP lifecycle separation
    """

    @property
    def project_root(self) -> Path:
        """
        Get project root directory.

        PRE: None (always callable after construction)

        POST-1: Returns absolute Path to project root
        POST-2: Path.exists() == True
        POST-3: Path.is_dir() == True

        INV (5-Point Checklist):
        1. State Invariance: No state modified (property read)
        2. Side Effect Prohibition: No I/O, no logging
        3. Ordering Constraints: None
        4. Resource Invariants: No allocations
        5. Exception Safety: Never raises

        ERRORS: None (never raises)
        """
        ...

    @property
    def project_name(self) -> str:
        """
        Get project name.

        PRE: None (always callable)

        POST-1: Returns non-empty string
        POST-2: Default is project_root.name if not configured

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: No I/O
        3. Ordering Constraints: None
        4. Resource Invariants: No allocations
        5. Exception Safety: Never raises

        ERRORS: None (never raises)
        """
        ...

    @property
    def languages(self) -> list[str]:
        """
        Get configured languages as strings (NOT LSP instances).

        PRE: None (always callable)

        POST-1: Returns list of language strings (e.g., ["python", "rust"])
        POST-2: May be empty list if no languages configured
        POST-3: Does NOT return LSP instances (config-only)

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: No I/O, no LSP creation
        3. Ordering Constraints: None
        4. Resource Invariants: No LSP instances held
        5. Exception Safety: Never raises

        ERRORS: None (never raises)
        """
        ...

    @property
    def project_config(self) -> Any:
        """
        Get full project configuration object.

        PRE: None (always callable)

        POST-1: Returns ProjectConfig with all settings
        POST-2: Includes ignored_paths, encoding, read_only, etc.

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: No I/O
        3. Ordering Constraints: None
        4. Resource Invariants: No allocations
        5. Exception Safety: Never raises

        ERRORS: None (never raises)
        """
        ...

    @classmethod
    def load(cls, project_root: Path, autogenerate: bool = False) -> "ProjectConfigOnlyContract":
        """
        Load Project configuration from disk.

        PRE: project_root is absolute path
        PRE: project_root.exists() and project_root.is_dir()

        POST-1: Returns Project with configuration loaded
        POST-2: If autogenerate=True and no project.yml, creates default
        POST-3: NO LSP instances created (config-only)

        INV (5-Point Checklist):
        1. State Invariance: N/A (factory method)
        2. Side Effect Prohibition: Reads project.yml (declared I/O),
           may create project.yml if autogenerate (declared)
        3. Ordering Constraints: None
        4. Resource Invariants: Opens/closes file handles properly
        5. Exception Safety: On error, no partial Project returned

        ERRORS:
        - ERRORS-1: FileNotFoundError if project_root does not exist
        - ERRORS-2: ValueError if project_root is not absolute
        - ERRORS-3: yaml.YAMLError if project.yml is malformed
        """
        ...

    def get_ignore_spec(self) -> Any:
        """
        Get pathspec for ignored paths.

        PRE: None (always callable)

        POST-1: Returns PathSpec object for filtering
        POST-2: Matches patterns from project.yml ignored_paths

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: No I/O
        3. Ordering Constraints: None
        4. Resource Invariants: May cache PathSpec
        5. Exception Safety: Never raises

        ERRORS: None (never raises)
        """
        ...

    def is_ignored_path(self, path: Path) -> bool:
        """
        Check if path should be ignored.

        PRE: path is Path object (relative or absolute)

        POST-1: Returns True if path matches ignore patterns
        POST-2: Returns False otherwise

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: No I/O
        3. Ordering Constraints: None
        4. Resource Invariants: No allocations
        5. Exception Safety: Never raises

        ERRORS: None (never raises)
        """
        ...

    def is_path_in_project(self, path: Path) -> bool:
        """
        Check if path is within project boundaries.

        PRE: path is Path object

        POST-1: Returns True if path is under project_root
        POST-2: Returns False if path escapes via .. or symlink

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: May resolve symlinks (declared I/O)
        3. Ordering Constraints: None
        4. Resource Invariants: No allocations
        5. Exception Safety: Never raises (returns False on error)

        ERRORS: None (never raises, returns False on any error)
        """
        ...

    def validate_relative_path(self, relative_path: str) -> Path:
        """
        Validate and resolve relative path within project.

        PRE: relative_path is string (may contain ..)

        POST-1: Returns absolute Path if valid and within project
        POST-2: Path is resolved (no symlink escapes)

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: May resolve symlinks (declared)
        3. Ordering Constraints: None
        4. Resource Invariants: No allocations
        5. Exception Safety: Raises on invalid path (declared)

        ERRORS:
        - ERRORS-1: ValueError if path escapes project boundaries
        - ERRORS-2: FileNotFoundError if resolved path does not exist
        """
        ...

    def gather_source_files(
        self,
        extensions: Optional[list[str]] = None,
        ignore_spec: Optional[Any] = None
    ) -> list[Path]:
        """
        Gather source files matching criteria.

        PRE: extensions is None or list of strings (e.g., [".py", ".rs"])

        POST-1: Returns list of absolute Paths to source files
        POST-2: Excludes ignored paths
        POST-3: Filters by extensions if provided

        INV (5-Point Checklist):
        1. State Invariance: No state modified
        2. Side Effect Prohibition: Reads filesystem (declared I/O)
        3. Ordering Constraints: None
        4. Resource Invariants: No file handles left open
        5. Exception Safety: Returns empty list on error

        ERRORS: None (returns empty list on any error)
        """
        ...


# =============================================================================
# TEST CASE SPECIFICATIONS (CL12-E Traceability)
# =============================================================================

TEST_CASES = {
    "prohibited_lsp_methods": [
        {
            "name": "test_inv1_no_create_lsp_manager",
            "contract": "INV-1: NO create_lsp_manager method exists",
            "assertion": "not hasattr(project, 'create_lsp_manager')",
            "guidance": "Project MUST NOT have create_lsp_manager - use GlobalLanguageServerPool",
        },
        {
            "name": "test_inv2_no_create_language_server",
            "contract": "INV-2: NO create_language_server method exists",
            "assertion": "not hasattr(project, 'create_language_server')",
            "guidance": "Project MUST NOT have create_language_server - use GlobalLanguageServerPool",
        },
        {
            "name": "test_inv3_no_language_server_manager_property",
            "contract": "INV-3: NO language_server_manager property exists",
            "assertion": "not hasattr(project, 'language_server_manager')",
            "guidance": "Project MUST NOT have language_server_manager - use GlobalLanguageServerPool",
        },
    ],
    "config_only": [
        {
            "name": "test_inv4_no_lsp_instances_stored",
            "contract": "INV-4: Project stores ONLY configuration (no LSP instances)",
            "assertion": "no attribute of type SolidLanguageServer or LanguageServerManager",
            "guidance": "Verify no LSP instances in project.__dict__",
        },
        {
            "name": "test_languages_returns_strings_not_lsp",
            "contract": "POST-3: Does NOT return LSP instances (config-only)",
            "setup": "project with languages configured",
            "assertion": "all(isinstance(lang, str) for lang in project.languages)",
            "guidance": "languages property returns strings, not LSP instances",
        },
    ],
    "load": [
        {
            "name": "test_post_no_lsp_created_on_load",
            "contract": "POST-3: NO LSP instances created (config-only)",
            "setup": "Project.load(valid_path)",
            "assertion": "no LSP instances exist after load",
            "guidance": "Loading Project MUST NOT start any LSP processes",
        },
    ],
    "path_validation": [
        {
            "name": "test_validate_relative_path_escapes",
            "contract": "ERRORS-1: ValueError if path escapes project boundaries",
            "input": "../../../etc/passwd",
            "assertion": "raises ValueError",
        },
        {
            "name": "test_is_path_in_project_returns_false_on_escape",
            "contract": "POST-2: Returns False if path escapes via .. or symlink",
            "input": "Path('/etc/passwd')",
            "assertion": "returns False",
        },
    ],
}


# =============================================================================
# VERIFICATION HELPERS
# =============================================================================

def verify_no_lsp_lifecycle_methods(project: Any) -> None:
    """
    Verify Project has no LSP lifecycle methods.

    PRE: project is Project instance
    POST: No return value (raises on violation)
    INV: project unchanged

    ERRORS:
    - ERRORS-1: AssertionError if any prohibited method exists
    - ERRORS-2: TypeError if project lacks __dict__ (non-inspectable object)
    """
    for method in PROHIBITED_LSP_METHODS:
        assert not hasattr(project, method), (
            f"INV-{PROHIBITED_LSP_METHODS.index(method) + 1} violation: "
            f"Project has prohibited LSP lifecycle method '{method}'\n"
            f"Contract: ProjectConfigOnlyContract\n"
            f"EXPECTED: Method '{method}' does not exist\n"
            f"ACTUAL: Method exists\n"
            f"GUIDANCE: Remove LSP lifecycle from Project, use GlobalLanguageServerPool"
        )


def verify_no_lsp_instances(project: Any) -> None:
    """
    Verify Project does not store any LSP instances.

    PRE: project is Project instance
    POST: No return value (raises on violation)
    INV: project unchanged

    ERRORS:
    - ERRORS-1: AssertionError if any LSP instance found in project attributes
    - ERRORS-2: TypeError if project lacks __dict__ (non-inspectable object)
    """
    lsp_type_names = [
        "SolidLanguageServer",
        "LanguageServerManager",
        "LanguageServer",
    ]

    for attr_name in dir(project):
        if attr_name.startswith("_"):
            continue
        try:
            attr_value = getattr(project, attr_name)
            attr_type_name = type(attr_value).__name__
            assert attr_type_name not in lsp_type_names, (
                f"INV-4 violation: Project stores LSP instance\n"
                f"Contract: ProjectConfigOnlyContract\n"
                f"EXPECTED: No LSP instances in Project\n"
                f"ACTUAL: '{attr_name}' is {attr_type_name}\n"
                f"GUIDANCE: Remove LSP state, use GlobalLanguageServerPool"
            )
        except Exception:
            # Skip properties that raise exceptions
            pass


def verify_languages_are_strings(project: Any) -> None:
    """
    Verify languages property returns strings, not LSP instances.

    PRE: project is Project instance
    POST: No return value (raises on violation)
    INV: project unchanged

    ERRORS:
    - ERRORS-1: AssertionError if languages contains non-string values
    - ERRORS-2: TypeError if project lacks __dict__ (non-inspectable object)
    - ERRORS-3: AttributeError if project lacks languages property
    """
    languages = project.languages
    for i, lang in enumerate(languages):
        assert isinstance(lang, str), (
            f"Contract violation: languages[{i}] is not string\n"
            f"Contract: ProjectConfigOnlyContract.languages\n"
            f"EXPECTED: All elements are str\n"
            f"ACTUAL: languages[{i}] is {type(lang).__name__}\n"
            f"GUIDANCE: languages property must return list of strings"
        )
