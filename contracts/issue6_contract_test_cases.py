"""
Issue #6 Contract Test Cases - Test Specifications

Constitutional Reference: CL12 Design by Contract
Domain: Test case specifications for Issue #6 contracts
Version: 1.0

These test cases specify what tests MUST verify for each contract.
Every assertion in a test MUST trace to one of these specifications.
"""

from pathlib import Path

# =============================================================================
# SESSION CONTEXT TEST CASES
# =============================================================================

SESSION_CONTEXT_TEST_CASES = [
    # (field, constraint, test_value, should_pass)
    ("session_id", "non-empty (INV-1)", "", False),
    ("session_id", "non-empty (INV-1)", "valid-id", True),
    ("workspace_root", "absolute when set (INV-2)", Path("relative/path"), False),
    ("workspace_root", "absolute when set (INV-2)", Path("/absolute/path"), True),
    ("workspace_root", "None allowed", None, True),
]

# =============================================================================
# CLEANUP TEST CASES
# =============================================================================

CLEANUP_TEST_CASES = [
    # (scenario, expected_behavior, contract_reference)
    ("explicit_unbind", "Session removed, LSPs released", "SessionCleanupContract.cleanup_session POST"),
    ("ttl_expiration", "Session reaped, LSPs released", "SessionCleanupContract.reap_expired_sessions POST"),
    ("server_shutdown", "All sessions cleaned up", "SessionCleanupContract.shutdown_all_sessions POST"),
    ("double_cleanup", "Second call is no-op", "SessionCleanupContract.cleanup_session INV-1"),
    ("other_sessions_unaffected", "Cleanup isolated", "SessionCleanupContract.cleanup_session INV-2"),
]

# =============================================================================
# PATH VALIDATION TEST CASES
# =============================================================================

PATH_VALIDATION_TEST_CASES = [
    # (relative_path, should_pass, description, contract_reference)
    ("src/main.py", True, "Normal path within workspace", "SessionPathValidationContract INV-1"),
    ("../outside", False, "Parent escape", "SessionPathValidationContract INV-3"),
    ("../../etc/passwd", False, "Multi-level escape", "SessionPathValidationContract INV-3"),
    ("link/secret", False, "Symlink traversal", "SessionPathValidationContract INV-2"),
    ("/etc/passwd", False, "Absolute outside workspace", "SessionPathValidationContract INV-4"),
]

# =============================================================================
# LSP MULTIPLEXING TEST CASES
# =============================================================================

LSP_MULTIPLEXING_TEST_CASES = [
    # (language, is_multi_root, expected_behavior, contract_reference)
    ("rust", True, "Shared instance, workspace added via didChangeWorkspaceFolders", "LSPWorkspaceMultiplexingContract INV-1"),
    ("typescript", False, "Separate instance per workspace", "LSPWorkspaceMultiplexingContract INV-2"),
    ("max_workspaces_exceeded", None, "RuntimeError raised", "LSPWorkspaceMultiplexingContract INV-3"),
]

# =============================================================================
# SESSION CREATION TRIGGER TEST CASES
# =============================================================================

SESSION_CREATION_TRIGGER_TEST_CASES = [
    # (trigger, expected_state, contract_reference)
    ("transport_connect", "Session created with state=CREATED", "SessionCreationTriggerContract.create_session_for_mcp_transport POST"),
    ("duplicate_transport", "Error or idempotent", "SessionCreationTriggerContract.create_session_for_mcp_transport INV"),
    ("bind_project", "workspace_root set, state=ACTIVE", "SessionCreationTriggerContract.bind_project_to_session POST"),
    ("anonymous_session", "session_id starts with 'anonymous-'", "SessionCreationTriggerContract.create_anonymous_session POST"),
]

# =============================================================================
# BACKWARD COMPATIBILITY TEST CASES
# =============================================================================

BACKWARD_COMPAT_TEST_CASES = [
    # (context, expected_path, description, contract_reference)
    ("cli", "legacy", "CLI uses _active_project, no registry", "BackwardCompatibilityContract.activate_project_legacy POST"),
    ("mcp", "session", "MCP uses SessionRegistry, no _active_project", "BackwardCompatibilityContract.activate_project_with_session POST"),
    ("cli_no_bind", "registry not modified", "Legacy mode doesn't touch registry", "BackwardCompatibilityContract.activate_project_legacy INV"),
]

# =============================================================================
# MCP FACTORY ACTIVATION TEST CASES
# =============================================================================

MCP_FACTORY_ACTIVATION_TEST_CASES = [
    # (scenario, expected_behavior, contract_reference)
    ("agent_none", "ValueError raised", "MCPFactoryActivationContract.activate_project_for_mcp_session PRE"),
    ("session_none", "ValueError raised", "MCPFactoryActivationContract.activate_project_for_mcp_session PRE"),
    ("invalid_project", "ProjectNotFoundError", "MCPFactoryActivationContract.activate_project_for_mcp_session ERRORS"),
    ("successful_activation", "SessionContext returned by get_session", "MCPFactoryActivationContract.activate_project_for_mcp_session POST"),
    ("workspace_matches", "workspace_root == project.project_root.resolve()", "MCPFactoryActivationContract.activate_project_for_mcp_session POST"),
    ("idempotent_same", "Second call to same workspace is no-op", "MCPFactoryActivationContract.activate_project_for_mcp_session INV-2"),
    ("rebind_different", "Old workspace unbound first", "MCPFactoryActivationContract.activate_project_for_mcp_session INV-3"),
    ("other_sessions_unaffected", "Only current session modified", "MCPFactoryActivationContract.activate_project_for_mcp_session INV-5"),
]


# =============================================================================
# VERIFICATION HELPERS
# =============================================================================

def verify_session_context_invariants(ctx) -> list[str]:
    """
    Verify all SessionContext invariants.

    PRE: ctx is SessionContextContract instance
    POST: Returns list of violation messages (empty if all pass)
    INV: ctx unchanged

    Returns list of violation messages (empty if all pass).
    """
    violations = []

    # INV-1: session_id non-empty
    if not ctx.session_id:
        violations.append("INV-1: session_id is empty")

    # INV-2: workspace_root absolute when set
    if ctx.workspace_root is not None and not ctx.workspace_root.is_absolute():
        violations.append(f"INV-2: workspace_root is not absolute: {ctx.workspace_root}")

    # INV-5: last_activity_time >= activation_time
    if ctx.last_activity_time < ctx.activation_time:
        violations.append("INV-5: last_activity_time < activation_time (backdated)")

    return violations


def verify_cleanup_idempotent(cleanup_fn, session_id: str) -> bool:
    """
    Verify cleanup is idempotent.

    PRE: cleanup_fn is callable accepting session_id
    PRE: session_id is string
    POST: Returns True if cleanup is idempotent (no error on second call)
    POST: Returns False if second call raises
    INV: Session state after second call same as after first

    Calls cleanup twice, verifies no error on second call.
    """
    try:
        cleanup_fn(session_id)
        cleanup_fn(session_id)  # Second call should be no-op
        return True
    except Exception:
        return False


def verify_path_boundary_enforcement(
    validator,
    session_id: str,
    workspace_root: Path,
    test_cases: list[tuple[str, bool]],
) -> list[str]:
    """
    Verify path boundary enforcement.

    PRE: validator has validate_path_for_session method
    PRE: session_id exists in registry
    PRE: workspace_root is absolute Path
    PRE: test_cases is list of (relative_path, should_pass) tuples
    POST: Returns list of failures (empty if all pass)
    INV: Registry state unchanged

    Returns list of failures.
    """
    from .path_validation_contract import PathBoundaryError

    failures = []
    for relative_path, should_pass in test_cases:
        try:
            validator.validate_path_for_session(session_id, relative_path)
            if not should_pass:
                failures.append(f"Path '{relative_path}' should have raised PathBoundaryError")
        except PathBoundaryError:
            if should_pass:
                failures.append(f"Path '{relative_path}' should have passed validation")
    return failures
