"""
Contract: PathValidation

Defines the behavioral contract for secure path validation.
Critical security component - prevents path traversal attacks.
Mocks for tests MUST derive from this contract (CL10).

Component: PathValidation
Purpose: Validate and resolve paths within project boundary
Security: Prevents symlink traversal, boundary escape attacks
"""

from pathlib import Path
from typing import Any


# =============================================================================
# EXCEPTIONS (imported from implementation)
# =============================================================================

from src.serena.path_validation import PathBoundaryError


# =============================================================================
# BEHAVIORAL CONTRACTS
# =============================================================================

class PathValidationContract:
    """
    Behavioral contract for secure path validation.

    INVARIANTS:
    - INV-1: All returned paths are absolute and resolved (no symlinks in path)
    - INV-2: All returned paths are within project_root boundary
    - INV-3: Symlinks are resolved BEFORE boundary check (security critical)

    PRECONDITIONS:
    - PRE-1 (validate): project_root is absolute, resolved, existing directory
    - PRE-2 (validate): relative_path is a string or Path

    POSTCONDITIONS:
    - POST-1 (validate/success): returned path is absolute
    - POST-2 (validate/success): returned path resolves to location within project_root
    - POST-3 (validate/failure): PathBoundaryError raised with helpful message
    - POST-4 (validate/failure): Error includes resolved path and project root

    SECURITY REQUIREMENTS:
    - SEC-1: Symlinks MUST be resolved before boundary check
    - SEC-2: Project root MUST also be resolved (to prevent symlink in root)
    - SEC-3: Path components like ".." MUST be resolved before check
    - SEC-4: Error messages MUST NOT reveal sensitive path information beyond project
    """


def validate_path(relative_path: str | Path, project_root: Path) -> Path:
    """
    Validate and resolve a path within project boundary.

    SECURITY CRITICAL: This function prevents path traversal attacks.

    PRE: relative_path is str or Path (relative to project root or absolute within project)
    PRE: project_root is absolute Path (enforced by ValueError)

    POST: Returns resolved absolute Path within project boundary
    POST: Returned path has no unresolved symlinks or ".." components
    POST: Returned path starts with resolved project_root

    INV (5-Point Checklist):
    1. State Invariance: No file system state modified (read-only resolution)
    2. Side Effect Prohibition: No I/O beyond Path.resolve(), no logging
    3. Ordering Constraints: Symlinks resolved BEFORE boundary check (SEC-1)
    4. Resource Invariants: No file handles opened/left open
    5. Exception Safety: On error, raises immediately with no partial state

    ERRORS:
    - PathBoundaryError: If resolved path escapes project boundary
    - ValueError: If project_root is not absolute

    Algorithm:
    1. Resolve project_root to canonical form (resolves symlinks)
    2. Join relative_path to project_root
    3. Resolve the combined path (resolves .. and symlinks)
    4. Verify resolved path starts with resolved project_root
    5. Return resolved path or raise PathBoundaryError

    Examples:
        validate_path("src/main.py", Path("/project")) -> Path("/project/src/main.py")
        validate_path("../outside", Path("/project")) -> raises PathBoundaryError
    """
    # Contract forwards to implementation (adversarial TDD architecture)
    from src.serena.path_validation import validate_path as _validate_path_impl
    return _validate_path_impl(relative_path, project_root)


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================

def verify_path_is_within_boundary(path: Path, boundary: Path) -> bool:
    """
    Verify a path is within the specified boundary.

    PRE: path is resolved absolute Path (caller must resolve before calling)
    PRE: boundary is resolved absolute Path (caller must resolve before calling)

    POST: Returns True if path is within or equal to boundary
    POST: Returns False if path is outside boundary

    INV (5-Point Checklist):
    1. State Invariance: path and boundary unchanged (pure query)
    2. Side Effect Prohibition: No I/O, no logging, no external state
    3. Ordering Constraints: None (pure function)
    4. Resource Invariants: No memory allocation beyond bool
    5. Exception Safety: Never raises (catches ValueError internally)

    ERRORS: None (catches ValueError from relative_to, returns False)
    """
    try:
        path.relative_to(boundary)
        return True
    except ValueError:
        return False


def create_symlink_attack_scenario(test_dir: Path) -> tuple[Path, Path, Path]:
    """
    Create a test scenario for symlink traversal attack.

    PRE: test_dir is absolute Path to existing directory with write permissions
    PRE: test_dir/project does not exist OR is empty
    PRE: test_dir/outside does not exist OR is empty

    POST: Returns tuple (project_root, malicious_symlink, target_outside)
    POST: project_root is test_dir/project (created)
    POST: target_outside is test_dir/outside (created with secret.txt)
    POST: malicious_symlink is project_root/escape -> target_outside

    INV (5-Point Checklist):
    1. State Invariance: test_dir itself unchanged, only subdirs created
    2. Side Effect Prohibition: DECLARED - creates directories and files (test fixture)
    3. Ordering Constraints: Directories created before symlink
    4. Resource Invariants: All file handles closed after write
    5. Exception Safety: Partial state on error (directories may exist)

    ERRORS:
    - OSError: If directory creation fails (permissions, disk full)
    - OSError: If symlink creation fails (permissions, symlinks not supported)
    - FileExistsError: If malicious_link already exists and is not a symlink

    Usage in tests:
        project, link, target = create_symlink_attack_scenario(tmp_path)
        # link is inside project but points to target outside
        # validate_path(link.name / "secret", project) should raise PathBoundaryError
    """
    project_root = test_dir / "project"
    project_root.mkdir(exist_ok=True)

    outside_dir = test_dir / "outside"
    outside_dir.mkdir(exist_ok=True)
    (outside_dir / "secret.txt").write_text("sensitive data")

    malicious_link = project_root / "escape"
    malicious_link.symlink_to(outside_dir)

    return project_root, malicious_link, outside_dir


# =============================================================================
# CONTRACT TEST ASSERTIONS
# =============================================================================

SECURITY_TEST_CASES = [
    # (relative_path, should_raise, description)
    ("src/main.py", False, "Normal relative path within project"),
    ("./lib/utils.py", False, "Dot-prefixed relative path"),
    ("../outside", True, "Simple parent escape"),
    ("../../etc/passwd", True, "Multi-level parent escape"),
    ("src/../../../etc/passwd", True, "Mixed path with parent escape"),
    ("escape/secret.txt", True, "Symlink traversal (requires symlink setup)"),
]

BOUNDARY_ERROR_REQUIREMENTS = [
    "resolved_path attribute must be set",
    "project_root attribute must be set",
    "message must contain helpful remediation suggestion",
    "message should mention 'absolute path' or 'activate different project'",
]
