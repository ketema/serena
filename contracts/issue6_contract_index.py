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
    TOUCH_STALENESS_THRESHOLD_SECONDS,
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

# Phase 4 contracts (legacy removal / statelessness)
from .serena_agent_stateless_contract import (
    SerenaAgentStatelessContract,
    PROHIBITED_FIELDS as SERENA_AGENT_PROHIBITED_FIELDS,
    get_current_session,
    set_current_session,
    verify_no_legacy_state,
    verify_required_dependencies,
)
from .project_config_only_contract import (
    ProjectConfigOnlyContract,
    ProjectConfigContract,
    PROHIBITED_LSP_METHODS,
    verify_no_lsp_lifecycle_methods,
    verify_no_lsp_instances,
    verify_languages_are_strings,
)
from .project_language_routing_contract import ProjectLanguageRoutingContract

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
    "TOUCH_STALENESS_THRESHOLD_SECONDS",
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
    # Phase 4 contracts (legacy removal / statelessness)
    "SerenaAgentStatelessContract",
    "SERENA_AGENT_PROHIBITED_FIELDS",
    "get_current_session",
    "set_current_session",
    "verify_no_legacy_state",
    "verify_required_dependencies",
    "ProjectConfigOnlyContract",
    "ProjectConfigContract",
    "PROHIBITED_LSP_METHODS",
    "verify_no_lsp_lifecycle_methods",
    "verify_no_lsp_instances",
    "verify_languages_are_strings",
    "ProjectLanguageRoutingContract",
]


def audit_contract_coverage() -> dict:
    """
    Audit contract coverage across all Issue #6 contracts.

    PRE: All contract modules importable (imports already resolved at module load)

    POST: Returns dict mapping contract names to PRE/POST/INV counts
    POST: Each entry has keys: pre_count, post_count, inv_count, errors_count, has_all_sections
    POST: On introspection errors, entry has error_message key instead of counts

    INV (5-Point Checklist):
    1. State Invariance: No module or contract state modified
    2. Side Effect Prohibition: No I/O, no logging, no external state
    3. Ordering Constraints: None (pure function, stateless)
    4. Resource Invariants: No memory leaks, no handles opened
    5. Exception Safety: GUARANTEED never raises - all introspection errors caught and
       recorded in result dict with error_message key

    ERRORS: None (all exceptions caught internally, recorded in result dict)
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
        # Phase 4 contracts
        ("SerenaAgentStatelessContract", SerenaAgentStatelessContract),
        ("ProjectConfigOnlyContract", ProjectConfigOnlyContract),
        ("ProjectLanguageRoutingContract", ProjectLanguageRoutingContract),
    ]

    result = {}
    for name, contract in contracts:
        try:
            methods = [m for m in dir(contract) if not m.startswith("_") and callable(getattr(contract, m, None))]
        except Exception as e:
            result[f"{name}"] = {"error_message": f"Failed to inspect contract: {e}"}
            continue

        for method in methods:
            key = f"{name}.{method}"
            try:
                method_obj = getattr(contract, method, None)
                if method_obj is None:
                    continue
                doc = getattr(method_obj, "__doc__", None) or ""
                if not isinstance(doc, str):
                    doc = str(doc)
                result[key] = {
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
            except Exception as e:
                result[key] = {"error_message": f"Failed to inspect method: {e}"}
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
