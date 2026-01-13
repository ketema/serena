"""
Issue #6 Contract Index - AUTHORITATIVE Source

Constitutional Reference: CL12 Design by Contract
Domain: Unified access to all Issue #6 contracts
Version: 1.1

AUTHORITY: This is the SINGULAR AUTHORITATIVE source for Issue #6 contracts.
There SHALL be NO other authoritative contract source for Issue #6.
The deprecated issue6_multi_project_contract.py is FROZEN and non-authoritative.

This module provides:
1. Single import point for all Issue #6 contracts (AUTHORITATIVE)
2. Contract coverage audit capability
3. Path validation contracts (security-critical)
4. Session registry contracts (thread-safe)
"""

# =============================================================================
# MODULAR CONTRACTS (AUTHORITATIVE)
# =============================================================================

from .issue6_constants import (
    LSP_IDLE_TIMEOUT_SECONDS,
    LSP_MAX_WORKSPACES_PER_INSTANCE,
    SESSION_ANONYMOUS_TTL_SECONDS,
    SESSION_DEFAULT_TTL_SECONDS,
    SESSION_MAX_IDLE_SECONDS,
    SESSION_REAPER_INTERVAL_SECONDS,
)
from .session_context_contract import (
    SessionContextBehaviorContract,
    SessionContextContract,
    SessionState,
)
from .session_cleanup_contract import SessionCleanupContract
from .session_creation_trigger_contract import (
    SessionCreationTrigger,
    SessionCreationTriggerContract,
)
from .lsp_workspace_multiplexing_contract import LSPWorkspaceMultiplexingContract
from .backward_compat_contract import BackwardCompatibilityContract
from .mcp_factory_activation_contract import MCPFactoryActivationContract

# Session registry contract (thread-safe session_id → SessionContext mapping)
from .session_registry_contract import (
    SessionRegistryContract,
    verify_session_context,
    verify_isolation,
)

# Path validation contract (security-critical boundary enforcement)
from .path_validation_contract import (
    PathBoundaryError,
    PathValidationContract,
    validate_path,
    verify_path_is_within_boundary,
    create_symlink_attack_scenario,
    SECURITY_TEST_CASES,
    BOUNDARY_ERROR_REQUIREMENTS,
)

from .issue6_contract_test_cases import (
    BACKWARD_COMPAT_TEST_CASES,
    CLEANUP_TEST_CASES,
    LSP_MULTIPLEXING_TEST_CASES,
    MCP_FACTORY_ACTIVATION_TEST_CASES,
    PATH_VALIDATION_TEST_CASES,
    SESSION_CONTEXT_TEST_CASES,
    SESSION_CREATION_TRIGGER_TEST_CASES,
    verify_cleanup_idempotent,
    verify_path_boundary_enforcement,
    verify_session_context_invariants,
)

__all__ = [
    # Constants
    "SESSION_DEFAULT_TTL_SECONDS",
    "SESSION_ANONYMOUS_TTL_SECONDS",
    "SESSION_REAPER_INTERVAL_SECONDS",
    "SESSION_MAX_IDLE_SECONDS",
    "LSP_IDLE_TIMEOUT_SECONDS",
    "LSP_MAX_WORKSPACES_PER_INSTANCE",
    # Enums
    "SessionState",
    "SessionCreationTrigger",
    # Data contracts
    "SessionContextContract",
    # Behavioral contracts
    "SessionContextBehaviorContract",
    "SessionCleanupContract",
    "SessionCreationTriggerContract",
    "LSPWorkspaceMultiplexingContract",
    "BackwardCompatibilityContract",
    "MCPFactoryActivationContract",
    "SessionRegistryContract",  # Added: thread-safe session registry
    "PathValidationContract",  # Added: path boundary security
    # Exceptions
    "PathBoundaryError",
    # Path validation utilities
    "validate_path",
    "verify_path_is_within_boundary",
    "create_symlink_attack_scenario",
    "SECURITY_TEST_CASES",
    "BOUNDARY_ERROR_REQUIREMENTS",
    # Session registry utilities
    "verify_session_context",
    "verify_isolation",
    # Test cases
    "SESSION_CONTEXT_TEST_CASES",
    "CLEANUP_TEST_CASES",
    "PATH_VALIDATION_TEST_CASES",
    "LSP_MULTIPLEXING_TEST_CASES",
    "SESSION_CREATION_TRIGGER_TEST_CASES",
    "BACKWARD_COMPAT_TEST_CASES",
    "MCP_FACTORY_ACTIVATION_TEST_CASES",
    # Verification helpers
    "verify_session_context_invariants",
    "verify_cleanup_idempotent",
    "verify_path_boundary_enforcement",
]


def audit_contract_coverage() -> dict:
    """
    Audit contract coverage across all Issue #6 contracts.

    PRE: All contract modules importable
    POST: Returns dict mapping contract names to PRE/POST/INV counts
    INV: Does not modify any state

    Returns dict mapping contract names to their PRE/POST/INV counts.
    """
    contracts = [
        ("SessionContextContract", SessionContextContract),
        ("SessionContextBehaviorContract", SessionContextBehaviorContract),
        ("SessionCleanupContract", SessionCleanupContract),
        ("SessionCreationTriggerContract", SessionCreationTriggerContract),
        ("LSPWorkspaceMultiplexingContract", LSPWorkspaceMultiplexingContract),
        ("BackwardCompatibilityContract", BackwardCompatibilityContract),
        ("MCPFactoryActivationContract", MCPFactoryActivationContract),
        ("SessionRegistryContract", SessionRegistryContract),
        ("PathValidationContract", PathValidationContract),
    ]

    result = {}
    for name, contract in contracts:
        methods = [m for m in dir(contract) if not m.startswith("_") and callable(getattr(contract, m, None))]
        for method in methods:
            method_obj = getattr(contract, method, None)
            if method_obj is None:
                continue
            doc = method_obj.__doc__ or ""
            result[f"{name}.{method}"] = {
                "pre_count": doc.count("PRE:"),
                "post_count": doc.count("POST:"),
                "inv_count": doc.count("INV:"),
                "errors_count": doc.count("ERRORS:"),
                "has_all_sections": (
                    doc.count("PRE:") > 0 and
                    doc.count("POST:") > 0 and
                    doc.count("INV:") > 0
                ),
            }
    return result


# =============================================================================
# DEPRECATION NOTICE
# =============================================================================

DEPRECATION_NOTICE = """
DEPRECATION WARNING: issue6_multi_project_contract.py is DEPRECATED.

Use modular contracts from issue6_contract_index.py instead:

    from contracts.issue6_contract_index import (
        SessionContextContract,
        SessionCleanupContract,
        MCPFactoryActivationContract,
        # ... etc
    )

The monolithic file will be removed in a future version.
"""
