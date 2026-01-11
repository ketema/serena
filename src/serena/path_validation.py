"""
PathValidation - Secure path validation within project boundaries.

This module implements the PathValidationContract to prevent path traversal attacks.
Critical security component - all paths must be validated before file operations.

Contract: contracts/path_validation_contract.py
"""

from pathlib import Path


class PathBoundaryError(Exception):
    """
    Raised when a path escapes the project boundary.

    MUST include:
    - The resolved path that violated the boundary
    - The project root that was escaped
    - A helpful suggestion for remediation
    """

    def __init__(self, resolved_path: Path, project_root: Path, message: str) -> None:
        self.resolved_path = resolved_path
        self.project_root = project_root
        super().__init__(message)


def validate_path(relative_path: str | Path, project_root: Path) -> Path:
    """
    Validate and resolve a path within project boundary.

    SECURITY CRITICAL: This function prevents path traversal attacks.

    Security Guarantees:
    - Prevents directory traversal via '..' components
    - Prevents symlink-based boundary escapes
    - Resolves all symlinks before boundary validation

    Limitation:
    - TOCTOU (Time-Of-Check-To-Time-Of-Use) race condition: symlinks/files
      may change between validation and actual use. Always use returned
      path immediately and prefer atomic file operations.

    Algorithm (from contract):
    1. Resolve project_root to canonical form (resolves symlinks)
    2. Join relative_path to project_root
    3. Resolve the combined path (resolves .. and symlinks)
    4. Verify resolved path starts with resolved project_root
    5. Return resolved path or raise PathBoundaryError

    Args:
        relative_path: Path relative to project root (or absolute within project)
        project_root: Absolute path to project root directory

    Returns:
        Resolved absolute path within project boundary

    Raises:
        PathBoundaryError: If resolved path escapes project boundary or cannot be resolved
        ValueError: If project_root is not absolute or doesn't exist

    """
    # PRE-1: Validate project_root is absolute (SEC-2 from error messages)
    if not project_root.is_absolute():
        raise ValueError(f"project_root must be absolute path, got: {project_root}")

    # PRE-1: Validate project_root exists (from error message 2)
    if not project_root.exists():
        raise ValueError(f"project_root must exist, got: {project_root}")

    # Step 1: Resolve project_root to canonical form (SEC-2)
    # This resolves symlinks in the project root itself
    resolved_project_root = project_root.resolve()

    # Step 2: Join relative_path to project_root
    # Convert to Path if string
    if isinstance(relative_path, str):
        relative_path = Path(relative_path)

    combined_path = resolved_project_root / relative_path

    # Step 3: Resolve the combined path (SEC-1, SEC-3)
    # This resolves:
    # - Symlinks in the path (SEC-1)
    # - Parent components like ".." (SEC-3)
    # - Other path components
    try:
        resolved_path = combined_path.resolve()
    except (OSError, RuntimeError) as e:
        # OSError: filesystem issues (permissions, broken symlinks, etc.)
        # RuntimeError: raised on some platforms for symlink loops exceeding depth limit
        # Handle cases where resolution fails (broken symlinks, etc.)
        raise PathBoundaryError(
            resolved_path=combined_path,
            project_root=resolved_project_root,
            message=(f"Cannot resolve path '{relative_path}': {e}. Ensure the path is valid or activate a different project."),
        ) from e

    # Step 4: Verify resolved path is within boundary (INV-2)
    # Use relative_to to check if resolved_path starts with resolved_project_root
    try:
        resolved_path.relative_to(resolved_project_root)
    except ValueError:
        # Path escapes the boundary
        # POST-3, POST-4: Raise with helpful message and attributes
        raise PathBoundaryError(
            resolved_path=resolved_path,
            project_root=resolved_project_root,
            message=(
                f"Path '{relative_path}' resolves to '{resolved_path}' "
                f"which is outside project root '{resolved_project_root}'. "
                "Use an absolute path within the project or activate a different project."
            ),
        )

    # Step 5: Return resolved path (POST-1, POST-2)
    # INV-1: Returned path is absolute and resolved
    return resolved_path
