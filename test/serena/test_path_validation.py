"""
Adversarial TDD tests for PathValidation component.

Contract: contracts/path_validation.contract.py (CL10 compliant)
Requirements: REQ-2 (Session file access isolation)
Security: SEC-1 to SEC-4 (path traversal prevention)

Test Writer: Blind to implementation (adversarial TDD)
Error Messages: 5-point standard (What/Why/Expected/Actual/Guidance)
"""

from pathlib import Path

import pytest

from contracts.path_validation_contract import (
    SECURITY_TEST_CASES,
    PathBoundaryError,
    create_symlink_attack_scenario,
    validate_path,
    verify_path_is_within_boundary,
)


class TestPathValidationPreconditions:
    """Test PRE-1 and PRE-2 preconditions."""

    def test_project_root_must_be_absolute(self, tmp_path):
        """
        REQUIREMENT: PRE-1 (project_root is absolute)
        CONTRACT: PathValidationContract
        SECURITY: SEC-2 (prevent symlink in root)

        5-POINT ERROR MESSAGE:
        1. What failed: Project root validation
        2. Why: Relative paths for project root allow symlink attacks
        3. Expected: ValueError raised with message mentioning "absolute"
        4. Actual: <exception type and message>
        5. Guidance: validate_path MUST reject relative project_root by raising
           ValueError. Check that project_root is converted to absolute BEFORE
           any path operations. Message should guide user to provide absolute path.
        """
        relative_root = Path("relative/path")
        test_file = "src/main.py"

        try:
            result = validate_path(test_file, relative_root)
            pytest.fail(
                f"FAILURE - PathValidation precondition enforcement\n"
                f"WHY: Relative project_root enables symlink attacks (SEC-2)\n"
                f"EXPECTED: ValueError raised with 'absolute' in message\n"
                f"ACTUAL: Function succeeded, returned {result}\n"
                f"GUIDANCE: Relative project_root MUST be rejected with ValueError. "
                f"Error message MUST guide user to provide absolute path. "
                f"Implementation free to choose: early validation, Path conversion, "
                f"or resolution - any approach that enforces absoluteness before path operations."
            )
        except ValueError as e:
            if "absolute" not in str(e).lower():
                pytest.fail(
                    f"FAILURE - PathValidation error message quality\n"
                    f"WHY: Error lacks guidance for fixing precondition violation\n"
                    f"EXPECTED: ValueError message contains 'absolute'\n"
                    f"ACTUAL: {e}\n"
                    f"GUIDANCE: Error message MUST contain 'absolute' to communicate "
                    f"the precondition violation. This helps users understand what went wrong "
                    f"and how to fix it (e.g., use absolute path instead of relative)."
                )
        except Exception as e:
            pytest.fail(
                f"FAILURE - PathValidation precondition exception type\n"
                f"WHY: Wrong exception type confuses error handling\n"
                f"EXPECTED: ValueError\n"
                f"ACTUAL: {type(e).__name__}: {e}\n"
                f"GUIDANCE: Precondition violations should raise ValueError, "
                f"not {type(e).__name__}. PathBoundaryError is for boundary violations."
            )

    def test_project_root_must_exist(self, tmp_path):
        """
        REQUIREMENT: PRE-1 (project_root is existing directory)
        CONTRACT: PathValidationContract
        SECURITY: Prevents confusion attacks with non-existent roots

        5-POINT ERROR MESSAGE:
        1. What failed: Project root existence check
        2. Why: Non-existent roots create security ambiguity
        3. Expected: ValueError or FileNotFoundError mentioning "exist"
        4. Actual: <exception type and message>
        5. Guidance: validate_path should verify project_root.exists() and
           project_root.is_dir() before processing. Raise descriptive error
           guiding user to create directory or fix path.
        """
        nonexistent_root = tmp_path / "does_not_exist"
        test_file = "src/main.py"

        try:
            result = validate_path(test_file, nonexistent_root)
            pytest.fail(
                f"FAILURE - PathValidation existence precondition\n"
                f"WHY: Non-existent project_root creates security ambiguity\n"
                f"EXPECTED: ValueError or FileNotFoundError with 'exist' in message\n"
                f"ACTUAL: Function succeeded, returned {result}\n"
                f"GUIDANCE: Non-existent project_root MUST be rejected before path operations. "
                f"Raise ValueError or FileNotFoundError with message indicating the directory "
                f"does not exist. Implementation free to choose validation approach."
            )
        except (ValueError, FileNotFoundError) as e:
            if "exist" not in str(e).lower() and "directory" not in str(e).lower():
                pytest.fail(
                    f"FAILURE - PathValidation existence error message\n"
                    f"WHY: Message doesn't guide user to fix the problem\n"
                    f"EXPECTED: Message contains 'exist' or 'directory'\n"
                    f"ACTUAL: {e}\n"
                    f"GUIDANCE: Include 'exist' or 'directory' in error to help "
                    f"user understand the precondition that failed"
                )
        except Exception as e:
            pytest.fail(
                f"FAILURE - PathValidation existence exception type\n"
                f"WHY: Unexpected exception type breaks error handling patterns\n"
                f"EXPECTED: ValueError or FileNotFoundError\n"
                f"ACTUAL: {type(e).__name__}: {e}\n"
                f"GUIDANCE: Use ValueError or FileNotFoundError for existence checks"
            )


class TestPathValidationInvariantsAndSecurity:
    """Test INV-1, INV-2, INV-3 and SEC-1 to SEC-4."""

    def test_normal_path_within_boundary(self, tmp_path):
        """
        REQUIREMENT: POST-1, POST-2 (valid path returns absolute within boundary)
        CONTRACT: PathValidationContract
        INVARIANTS: INV-1 (absolute, resolved), INV-2 (within boundary)

        5-POINT ERROR MESSAGE:
        1. What failed: Normal path validation
        2. Why: Basic requirement - valid paths must work
        3. Expected: Absolute, resolved Path object within project_root
        4. Actual: <result type, value, and boundary check>
        5. Guidance: Algorithm per contract lines 74-79:
           Protocol: Resolve paths, join them, check boundary, return if valid.
           Implementation free to choose: Path operations, boundary verification,
           or any approach achieving INV-1 and INV-2 (absolute, resolved, within boundary).
        """
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "src").mkdir()
        (project_root / "src" / "main.py").write_text("# code")

        relative_path = "src/main.py"

        result = validate_path(relative_path, project_root)

        # INV-1: Must be absolute and resolved
        if not result.is_absolute():
            pytest.fail(
                f"FAILURE - PathValidation INV-1 (absolute path)\n"
                f"WHY: Requirement INV-1 - returned paths must be absolute\n"
                f"EXPECTED: result.is_absolute() == True\n"
                f"ACTUAL: result.is_absolute() == False, path={result}\n"
                f"GUIDANCE: Returned path MUST be absolute (INV-1). Any approach that "
                f"produces absolute paths is acceptable (resolution, conversion, validation)."
            )

        # INV-2: Must be within boundary
        resolved_root = project_root.resolve()
        if not verify_path_is_within_boundary(result, resolved_root):
            pytest.fail(
                f"FAILURE - PathValidation INV-2 (within boundary)\n"
                f"WHY: Requirement INV-2 - paths must not escape project_root\n"
                f"EXPECTED: result relative to project_root (using .relative_to())\n"
                f"ACTUAL: result={result}, project_root={resolved_root}\n"
                f"GUIDANCE: Paths outside boundary MUST raise PathBoundaryError (INV-2). "
                f"Implementation free to choose boundary verification method."
            )

        # Expected resolved path
        expected = (project_root / relative_path).resolve()
        if result != expected:
            pytest.fail(
                f"FAILURE - PathValidation path resolution\n"
                f"WHY: Resolved path must match canonical location\n"
                f"EXPECTED: {expected}\n"
                f"ACTUAL: {result}\n"
                f"GUIDANCE: Path must resolve to canonical location. Implementation "
                f"free to choose resolution strategy - any approach producing correct "
                f"canonical path satisfies requirement."
            )

    def test_dot_prefixed_relative_path(self, tmp_path):
        """
        REQUIREMENT: POST-1, POST-2 (./relative paths must work)
        CONTRACT: PathValidationContract
        SECURITY: SEC-3 (path components resolved before check)

        5-POINT ERROR MESSAGE:
        1. What failed: Dot-prefixed path validation
        2. Why: Common pattern - "./file" must be normalized
        3. Expected: Same as "file" - absolute, resolved, within boundary
        4. Actual: <result or exception>
        5. Guidance: Dot-prefixed paths MUST normalize to same result as
           non-prefixed. Implementation free to choose normalization approach.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "lib").mkdir()
        (project_root / "lib" / "utils.py").write_text("# utils")

        relative_path = "./lib/utils.py"

        result = validate_path(relative_path, project_root)

        expected = (project_root / "lib/utils.py").resolve()
        if result != expected:
            pytest.fail(
                f"FAILURE - PathValidation dot-prefix normalization\n"
                f"WHY: Dot-prefixed paths are common, must normalize correctly\n"
                f"EXPECTED: {expected}\n"
                f"ACTUAL: {result}\n"
                f"GUIDANCE: Dot-prefixed and non-prefixed paths must resolve to same "
                f"location. Implementation free to choose normalization strategy."
            )

    def test_simple_parent_escape_blocked(self, tmp_path):
        """
        REQUIREMENT: POST-3 (boundary violation raises PathBoundaryError)
        CONTRACT: PathValidationContract
        SECURITY: SEC-3 (.. components resolved before check)

        5-POINT ERROR MESSAGE:
        1. What failed: Simple parent escape prevention
        2. Why: Path traversal attack "../outside" must be blocked
        3. Expected: PathBoundaryError with resolved_path and project_root attributes
        4. Actual: <exception type, attributes, message>
        5. Guidance: Path traversal via ".." MUST be blocked by boundary check (SEC-3).
           WHAT: Canonicalize paths, verify boundary, raise PathBoundaryError if violated.
           HOW: Implementation free to choose canonicalization and verification methods.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        attack_path = "../outside"

        with pytest.raises(PathBoundaryError) as exc_info:
            validate_path(attack_path, project_root)

        error = exc_info.value

        # POST-4: Error must have resolved_path attribute
        if not hasattr(error, "resolved_path"):
            pytest.fail(
                "FAILURE - PathValidation PathBoundaryError.resolved_path missing\n"
                "WHY: POST-4 requires resolved_path attribute for debugging\n"
                "EXPECTED: error.resolved_path = <Path object>\n"
                "ACTUAL: AttributeError - resolved_path not set\n"
                "GUIDANCE: PathBoundaryError MUST have resolved_path attribute (POST-4). "
                "Contract defines signature. Implementation must store this attribute."
            )

        # POST-4: Error must have project_root attribute
        if not hasattr(error, "project_root"):
            pytest.fail(
                "FAILURE - PathValidation PathBoundaryError.project_root missing\n"
                "WHY: POST-4 requires project_root attribute for debugging\n"
                "EXPECTED: error.project_root = <Path object>\n"
                "ACTUAL: AttributeError - project_root not set\n"
                "GUIDANCE: PathBoundaryError MUST have project_root attribute (POST-4). "
                "Contract defines signature. Implementation must store this attribute."
            )

        # Verify resolved_path is actually outside boundary
        resolved_root = project_root.resolve()
        if verify_path_is_within_boundary(error.resolved_path, resolved_root):
            pytest.fail(
                f"FAILURE - PathValidation boundary check logic\n"
                f"WHY: Raised PathBoundaryError but path IS within boundary\n"
                f"EXPECTED: error.resolved_path outside project_root\n"
                f"ACTUAL: {error.resolved_path} is relative to {resolved_root}\n"
                f"GUIDANCE: Test logic error - raised PathBoundaryError but path is valid. "
                f"Boundary check must only reject paths that actually escape the boundary."
            )

    def test_multi_level_parent_escape_blocked(self, tmp_path):
        """
        REQUIREMENT: POST-3 (deep traversal attacks blocked)
        CONTRACT: PathValidationContract
        SECURITY: SEC-3 (multiple .. components resolved)

        5-POINT ERROR MESSAGE:
        1. What failed: Multi-level parent escape prevention
        2. Why: Deep traversal "../../etc/passwd" must be blocked
        3. Expected: PathBoundaryError raised
        4. Actual: <exception or successful return>
        5. Guidance: Multiple ".." components MUST be normalized during boundary check.
           WHAT: Canonicalize path, verify it doesn't escape boundary.
           HOW: Implementation free to choose normalization method.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()

        attack_path = "../../etc/passwd"

        try:
            result = validate_path(attack_path, project_root)
            pytest.fail(
                f"FAILURE - PathValidation multi-level traversal prevention\n"
                f"WHY: Security requirement - '../../' traversal must be blocked\n"
                f"EXPECTED: PathBoundaryError raised\n"
                f"ACTUAL: Function succeeded, returned {result}\n"
                f"GUIDANCE: Multi-level traversal MUST be blocked by boundary check. "
                f"Canonicalize paths, verify boundary. Don't manually parse components - "
                f"use path canonicalization to handle all '..' patterns."
            )
        except PathBoundaryError:
            # Expected - test passes
            pass
        except Exception as e:
            pytest.fail(
                f"FAILURE - PathValidation traversal exception type\n"
                f"WHY: Boundary violations must raise PathBoundaryError (POST-3)\n"
                f"EXPECTED: PathBoundaryError\n"
                f"ACTUAL: {type(e).__name__}: {e}\n"
                f"GUIDANCE: Raise PathBoundaryError for boundary escapes, not {type(e).__name__}"
            )

    def test_mixed_path_with_parent_escape_blocked(self, tmp_path):
        """
        REQUIREMENT: POST-3 (complex traversal patterns blocked)
        CONTRACT: PathValidationContract
        SECURITY: SEC-3 (path normalization before check)

        5-POINT ERROR MESSAGE:
        1. What failed: Mixed path traversal prevention
        2. Why: Attack "src/../../../etc/passwd" must be blocked
        3. Expected: PathBoundaryError raised (normalized path escapes)
        4. Actual: <exception or result>
        5. Guidance: resolve() normalizes entire path. "src/../../../etc"
           becomes "../../etc" which escapes. Boundary check detects this.
           Do NOT try to validate path components separately - resolve first.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "src").mkdir()

        attack_path = "src/../../../etc/passwd"

        try:
            result = validate_path(attack_path, project_root)
            pytest.fail(
                f"FAILURE - PathValidation mixed traversal prevention\n"
                f"WHY: Security - mixed paths like 'src/../../../' must be blocked\n"
                f"EXPECTED: PathBoundaryError raised\n"
                f"ACTUAL: Function succeeded, returned {result}\n"
                f"GUIDANCE: Mixed paths with traversal MUST be normalized and boundary checked. "
                f"WHAT: Canonicalize 'src/../../../etc' pattern, verify result within boundary. "
                f"HOW: Implementation free to choose canonicalization strategy."
            )
        except PathBoundaryError:
            # Expected - test passes
            pass
        except Exception as e:
            pytest.fail(
                f"FAILURE - PathValidation mixed path exception type\n"
                f"WHY: Boundary escapes must raise PathBoundaryError consistently\n"
                f"EXPECTED: PathBoundaryError\n"
                f"ACTUAL: {type(e).__name__}: {e}\n"
                f"GUIDANCE: All boundary violations → PathBoundaryError (not {type(e).__name__})"
            )

    def test_symlink_traversal_attack_blocked(self, tmp_path):
        """
        REQUIREMENT: INV-3, SEC-1 (symlinks resolved BEFORE boundary check)
        CONTRACT: PathValidationContract
        SECURITY: CRITICAL - symlink traversal is highest severity attack

        5-POINT ERROR MESSAGE:
        1. What failed: Symlink traversal prevention
        2. Why: AI Panel HIGH severity - attacker creates symlink inside project
           pointing outside, then accesses symlink target
        3. Expected: PathBoundaryError raised (resolved symlink target outside boundary)
        4. Actual: <exception or result>
        5. Guidance: resolve() follows symlinks (INV-3, SEC-1). If symlink points
           outside project, resolved path escapes boundary. Boundary check MUST
           use resolved paths for both target and project_root (SEC-2).

           Critical sequence:
           - resolved_root = project_root.resolve()  # SEC-2
           - resolved_path = (project_root / relative_path).resolve()  # SEC-1
           - check: resolved_path.is_relative_to(resolved_root)
           - If False: raise PathBoundaryError
        """
        # Create attack scenario using contract helper
        project_root, malicious_link, outside_dir = create_symlink_attack_scenario(tmp_path)

        # Attack: access file through symlink
        attack_path = "escape/secret.txt"

        try:
            result = validate_path(attack_path, project_root)
            pytest.fail(
                f"FAILURE - PathValidation symlink traversal prevention\n"
                f"WHY: CRITICAL SECURITY - AI Panel HIGH severity attack\n"
                f"     Symlink 'escape' inside project points to '{outside_dir}' outside.\n"
                f"     Accessing 'escape/secret.txt' must be blocked.\n"
                f"EXPECTED: PathBoundaryError raised (resolved symlink target escapes)\n"
                f"ACTUAL: Function succeeded, returned {result}\n"
                f"GUIDANCE: INV-3 and SEC-1 require symlink resolution BEFORE boundary check.\n"
                f"          WHAT: Resolve BOTH paths (target and boundary) to canonical form.\n"
                f"          WHAT: Verify resolved target is within resolved boundary.\n"
                f"          WHAT: If symlink target escapes boundary, raise PathBoundaryError.\n"
                f"          HOW: Implementation free to choose resolution and boundary verification methods."
            )
        except PathBoundaryError as e:
            # Verify error attributes (POST-4)
            if not hasattr(e, "resolved_path") or not hasattr(e, "project_root"):
                pytest.fail(
                    "FAILURE - PathValidation symlink error attributes\n"
                    "WHY: POST-4 - error must have resolved_path and project_root\n"
                    "EXPECTED: e.resolved_path and e.project_root attributes\n"
                    "ACTUAL: Missing attributes\n"
                    "GUIDANCE: PathBoundaryError MUST have both attributes (POST-4). "
                    "Contract defines required signature."
                )

            # Verify resolved_path is actually outside (critical validation)
            resolved_root = project_root.resolve()
            if verify_path_is_within_boundary(e.resolved_path, resolved_root):
                pytest.fail(
                    f"FAILURE - PathValidation symlink boundary check\n"
                    f"WHY: Raised error but resolved symlink target IS within boundary\n"
                    f"EXPECTED: e.resolved_path outside project_root\n"
                    f"ACTUAL: {e.resolved_path} is relative to {resolved_root}\n"
                    f"GUIDANCE: Test logic error - symlink target should resolve outside boundary. "
                    f"WHAT: Symlink resolution must follow link to actual target location. "
                    f"HOW: Implementation free to choose symlink resolution method."
                )
        except Exception as e:
            pytest.fail(
                f"FAILURE - PathValidation symlink exception type\n"
                f"WHY: Symlink boundary violations must raise PathBoundaryError\n"
                f"EXPECTED: PathBoundaryError\n"
                f"ACTUAL: {type(e).__name__}: {e}\n"
                f"GUIDANCE: Symlink escapes are boundary violations → PathBoundaryError"
            )


class TestPathBoundaryErrorQuality:
    """Test POST-3, POST-4 and SEC-4 (error message quality)."""

    def test_boundary_error_has_helpful_message(self, tmp_path):
        """
        REQUIREMENT: POST-3 (helpful error messages)
        CONTRACT: BOUNDARY_ERROR_REQUIREMENTS
        SECURITY: SEC-4 (no sensitive path leakage)

        5-POINT ERROR MESSAGE:
        1. What failed: Error message quality for boundary violations
        2. Why: Users need actionable guidance to fix boundary errors
        3. Expected: Message mentions "absolute path" or "activate different project"
        4. Actual: <error message>
        5. Guidance: Error message should guide user to solutions:
           - "Use absolute path outside session workspace", OR
           - "Activate project containing this file"

           DO NOT reveal sensitive paths from resolved_path (SEC-4).
           Only show project_root (user's own boundary).
        """
        project_root = tmp_path / "project"
        project_root.mkdir()

        attack_path = "../outside"

        with pytest.raises(PathBoundaryError) as exc_info:
            validate_path(attack_path, project_root)

        error_message = str(exc_info.value)

        # Check for remediation guidance
        has_absolute_hint = "absolute path" in error_message.lower()
        has_project_hint = "activate" in error_message.lower() and "project" in error_message.lower()

        if not (has_absolute_hint or has_project_hint):
            pytest.fail(
                f"FAILURE - PathValidation error message helpfulness\n"
                f"WHY: POST-3 requires helpful remediation suggestions\n"
                f"EXPECTED: Message contains 'absolute path' OR 'activate project'\n"
                f"ACTUAL: {error_message}\n"
                f"GUIDANCE: Help user fix the problem with actionable suggestions:\n"
                f"          - 'Use absolute path for files outside workspace', OR\n"
                f"          - 'Activate project containing this file'\n"
                f"          Include project_root in message for context."
            )

        # SEC-4: Verify no sensitive path leakage
        # This is BEHAVIORAL guidance - not dictating implementation
        # Message should NOT expose system paths beyond project_root
        if "/etc/passwd" in error_message or "/root/" in error_message:
            pytest.fail(
                f"FAILURE - PathValidation error message security (SEC-4)\n"
                f"WHY: Error messages must not reveal sensitive system paths\n"
                f"EXPECTED: Message excludes paths outside user's project\n"
                f"ACTUAL: {error_message}\n"
                f"GUIDANCE: SEC-4 behavioral requirement - error messages should "
                f"NOT expose resolved_path if it's outside project (attacker info leakage). "
                f"WHAT to achieve: Hide sensitive paths. "
                f"HOW is free: truncate, redact, or omit resolved_path in message. "
                f"Attributes resolved_path/project_root are for programmatic use (POST-4), "
                f"but message string should be safe for logging."
            )

    def test_boundary_error_attributes_set_correctly(self, tmp_path):
        """
        REQUIREMENT: POST-4 (error attributes for programmatic handling)
        CONTRACT: PathValidationContract

        5-POINT ERROR MESSAGE:
        1. What failed: PathBoundaryError attribute validation
        2. Why: POST-4 requires resolved_path and project_root for error handling
        3. Expected: error.resolved_path = Path, error.project_root = Path
        4. Actual: <attribute types and values>
        5. Guidance: PathBoundaryError.__init__(resolved_path, project_root, message)
           Store both as attributes. resolved_path should be the RESOLVED target
           (symlinks followed), not the input relative_path.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        attack_path = "../outside"

        with pytest.raises(PathBoundaryError) as exc_info:
            validate_path(attack_path, project_root)

        error = exc_info.value

        # Check resolved_path is Path object
        if not isinstance(error.resolved_path, Path):
            pytest.fail(
                f"FAILURE - PathValidation resolved_path attribute type\n"
                f"WHY: POST-4 requires Path object for programmatic use\n"
                f"EXPECTED: isinstance(error.resolved_path, Path) == True\n"
                f"ACTUAL: type={type(error.resolved_path)}, value={error.resolved_path}\n"
                f"GUIDANCE: Store resolved_path as Path object (not str). "
                f"Use: PathBoundaryError(resolved_path: Path, ...)"
            )

        # Check project_root is Path object
        if not isinstance(error.project_root, Path):
            pytest.fail(
                f"FAILURE - PathValidation project_root attribute type\n"
                f"WHY: POST-4 requires Path object for programmatic use\n"
                f"EXPECTED: isinstance(error.project_root, Path) == True\n"
                f"ACTUAL: type={type(error.project_root)}, value={error.project_root}\n"
                f"GUIDANCE: Store project_root as Path object (not str). "
                f"Use: PathBoundaryError(..., project_root: Path, ...)"
            )

        # Check resolved_path is absolute
        if not error.resolved_path.is_absolute():
            pytest.fail(
                f"FAILURE - PathValidation resolved_path absoluteness\n"
                f"WHY: INV-1 requires resolved paths (absolute + symlinks followed)\n"
                f"EXPECTED: error.resolved_path.is_absolute() == True\n"
                f"ACTUAL: {error.resolved_path}\n"
                f"GUIDANCE: Error.resolved_path MUST be the canonical, absolute path "
                f"(not the input relative path). Implementation free to choose resolution method."
            )

        # Check project_root is absolute
        if not error.project_root.is_absolute():
            pytest.fail(
                f"FAILURE - PathValidation project_root absoluteness\n"
                f"WHY: PRE-1 and SEC-2 require absolute, resolved project_root\n"
                f"EXPECTED: error.project_root.is_absolute() == True\n"
                f"ACTUAL: {error.project_root}\n"
                f"GUIDANCE: Error.project_root MUST be absolute and canonical (SEC-2 "
                f"prevents symlink attacks). Implementation free to choose resolution method."
            )

        # Verify resolved_path is actually outside boundary (correctness)
        resolved_root = project_root.resolve()
        if verify_path_is_within_boundary(error.resolved_path, resolved_root):
            pytest.fail(
                f"FAILURE - PathValidation error correctness\n"
                f"WHY: Raised PathBoundaryError but path is actually within boundary\n"
                f"EXPECTED: error.resolved_path outside error.project_root\n"
                f"ACTUAL: {error.resolved_path} is relative to {resolved_root}\n"
                f"GUIDANCE: Test logic error - only raise PathBoundaryError for actual violations. "
                f"Boundary check must distinguish valid paths from boundary escapes."
            )


class TestContractComplianceMatrix:
    """
    Verify all SECURITY_TEST_CASES from contract.

    This matrix test ensures comprehensive coverage of contract requirements.
    """

    @pytest.mark.parametrize("relative_path,should_raise,description", SECURITY_TEST_CASES)
    def test_security_matrix(self, tmp_path, relative_path, should_raise, description):
        """
        REQUIREMENT: All SECURITY_TEST_CASES from contract
        CONTRACT: PathValidationContract, SECURITY_TEST_CASES
        SECURITY: Comprehensive attack vector coverage

        5-POINT ERROR MESSAGE:
        1. What failed: Security matrix test for "<description>"
        2. Why: Contract requires all test cases pass
        3. Expected: should_raise=<bool> determines PathBoundaryError vs success
        4. Actual: <exception or result>
        5. Guidance: This is a PARAMETRIZED test covering all contract cases.
           Each case verifies algorithm: resolve → boundary check → raise/return.
           If symlink case fails, ensure you created symlink using contract helper.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "src").mkdir()
        (project_root / "lib").mkdir()
        (project_root / "src" / "main.py").write_text("# main")
        (project_root / "lib" / "utils.py").write_text("# utils")

        # Special setup for symlink case
        if "symlink" in description.lower():
            _, malicious_link, _ = create_symlink_attack_scenario(tmp_path)
            # relative_path is "escape/secret.txt" from SECURITY_TEST_CASES

        if should_raise:
            try:
                result = validate_path(relative_path, project_root)
                pytest.fail(
                    f"FAILURE - PathValidation security matrix: {description}\n"
                    f"WHY: Contract SECURITY_TEST_CASES requires this to raise\n"
                    f"EXPECTED: PathBoundaryError raised\n"
                    f"ACTUAL: Function succeeded, returned {result}\n"
                    f"GUIDANCE: Test case '{description}' must raise PathBoundaryError. "
                    f"Canonicalize path, verify boundary, raise if violation detected."
                )
            except PathBoundaryError:
                # Expected - test passes
                pass
            except Exception as e:
                pytest.fail(
                    f"FAILURE - PathValidation security matrix exception: {description}\n"
                    f"WHY: Wrong exception type for boundary violation\n"
                    f"EXPECTED: PathBoundaryError\n"
                    f"ACTUAL: {type(e).__name__}: {e}\n"
                    f"GUIDANCE: Boundary violations → PathBoundaryError (not {type(e).__name__})"
                )
        else:
            # Should succeed - verify INV-1, INV-2
            result = validate_path(relative_path, project_root)

            if not result.is_absolute():
                pytest.fail(
                    f"FAILURE - PathValidation security matrix INV-1: {description}\n"
                    f"WHY: Valid paths must be absolute (INV-1)\n"
                    f"EXPECTED: result.is_absolute() == True\n"
                    f"ACTUAL: {result}\n"
                    f"GUIDANCE: Returned path MUST be absolute (INV-1). Implementation "
                    f"free to choose absoluteness strategy."
                )

            resolved_root = project_root.resolve()
            if not verify_path_is_within_boundary(result, resolved_root):
                pytest.fail(
                    f"FAILURE - PathValidation security matrix INV-2: {description}\n"
                    f"WHY: Valid paths must be within boundary (INV-2)\n"
                    f"EXPECTED: result relative to project_root\n"
                    f"ACTUAL: result={result}, project_root={resolved_root}\n"
                    f"GUIDANCE: Test logic error - valid path returned outside boundary. "
                    f"Boundary verification must accept valid paths within project_root."
                )
