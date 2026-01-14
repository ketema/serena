"""
SerenaAgent Observability Contract
==================================

Source: REQUIREMENT_MANIFEST REQ-2026-002 (Dashboard Multi-Project Observability Interface)

This contract defines behavioral requirements for SerenaAgent's observability interface,
enabling Dashboard consumers to query session and LSP pool state without mutation.

DISCONNECT MATRIX Reference:
| ID | Behavior | EXPECTED | OBSERVED | DELTA |
|----|----------|----------|----------|-------|
| B1 | session_registry property | Public property | Private _session_registry | OVERRIDE |
| B2 | lsp_pool property | Public property | Private _lsp_pool | OVERRIDE |
| B3 | get_session_overview delegation | Delegate to registry | N/A (no property) | NEW |
| B4 | get_lsp_pool_stats delegation | Delegate to pool | N/A (no property) | NEW |

Contract Authority: This file is the SINGULAR authoritative source for SerenaAgent
observability requirements. All tests and implementations MUST trace to these specs.

CL12-C Compliance: No other file may declare authority for SerenaAgent observability.
"""

from typing import TypedDict


# =============================================================================
# Response Type Definitions (POST condition structure enforcement)
# =============================================================================

class SessionOverviewResponse(TypedDict):
    """
    Response structure for get_session_overview().

    Keys are MANDATORY - implementation MUST return exactly these keys.
    """
    sessions: list[dict]  # List of session info dicts
    total_count: int      # Count of active sessions


class LspPoolStatsResponse(TypedDict):
    """
    Response structure for get_lsp_pool_stats().

    Keys are MANDATORY - implementation MUST return exactly these keys.
    """
    lsps: list[dict]      # List of LSP info dicts
    total_count: int      # Count of active LSPs


# =============================================================================
# INV (Invariants) - Properties that MUST remain true
# =============================================================================

INV_OBS_01 = """
INV-OBS-01: Read-Only Operations
    Observability queries MUST NOT mutate SerenaAgent state.

    Rationale: Dashboard consumers expect read-only access. Any mutation
    would violate the principle of least surprise and could cause race conditions.

    Enforcement: Test MUST verify agent state unchanged after observability calls.
    Verification: Compare _session_registry and _lsp_pool state before/after.
"""

INV_OBS_02 = """
INV-OBS-02: Availability (Never Raises)
    Observability methods MUST NOT raise exceptions.

    Rationale: Dashboard must always render, even during error conditions.
    A 500 error is worse than showing empty data.

    Enforcement: Methods use try/except returning empty structure on any error.
    Verification: Test with None registry, None pool, corrupted state - all return valid dict.
"""

INV_OBS_03 = """
INV-OBS-03: Encapsulation (No Internal Object Exposure)
    Observability interface MUST NOT expose internal implementation objects directly.

    Rationale: Returning internal objects allows consumers to mutate state,
    violating INV-OBS-01. Also couples consumers to implementation details.

    Enforcement: Return shallow copies (new dicts/lists), never internal objects.
    Verification: Modifying returned dict MUST NOT affect internal state.
"""

INV_OBS_04 = """
INV-OBS-04: Thread Safety
    Observability queries MUST be safe to call concurrently with mutations.

    Rationale: Dashboard may poll while agent processes requests.
    Race conditions could cause crashes or inconsistent data.

    Enforcement: Delegate to SessionRegistry's lock (INV-4 from session_registry_contract).
    Verification: Concurrent test with N readers + M writers shows no exceptions.
"""

# =============================================================================
# PRE (Preconditions) - What MUST be true before operations
# =============================================================================

PRE_OBS_01 = """
PRE-OBS-01: SerenaAgent initialization complete
    Before calling observability properties, SerenaAgent MUST be fully initialized.

    Verification: self._session_registry is not None
    Note: _lsp_pool MAY be None (valid state when no LSPs acquired yet)
"""

# =============================================================================
# POST (Postconditions) - What MUST be true after operations
# =============================================================================

POST_OBS_01 = """
POST-OBS-01: session_registry property returns SessionRegistry
    After calling session_registry property:
    - Return type MUST be SessionRegistry instance
    - MUST NOT return None (PRE-OBS-01 guarantees initialization)
    - MUST be the same instance as _session_registry (not a copy)

    Note: This property exposes the registry for delegation.
    The registry's own methods handle copy semantics per INV-OBS-03.
"""

POST_OBS_02 = """
POST-OBS-02: lsp_pool property returns GlobalLanguageServerPool or None
    After calling lsp_pool property:
    - Return type MUST be GlobalLanguageServerPool or None
    - None is valid when no LSPs have been acquired
    - MUST be the same instance as _lsp_pool (not a copy)

    Note: This property exposes the pool for delegation.
    The pool's own methods handle copy semantics per INV-OBS-03.
"""

POST_OBS_03 = """
POST-OBS-03: get_session_overview response structure
    When Dashboard calls agent.session_registry.get_session_overview():
    - Response MUST be dict with exactly keys: "sessions", "total_count"
    - "sessions" MUST be list (may be empty)
    - "total_count" MUST be int >= 0
    - "total_count" MUST equal len("sessions")

    Structure: SessionOverviewResponse TypedDict
"""

POST_OBS_04 = """
POST-OBS-04: get_lsp_pool_stats response structure
    When Dashboard calls agent.lsp_pool.get_stats() (if pool exists):
    - Response MUST be dict with exactly keys: "lsps", "total_count"
    - "lsps" MUST be list (may be empty)
    - "total_count" MUST be int >= 0
    - "total_count" MUST equal len("lsps")

    Structure: LspPoolStatsResponse TypedDict

    Note: If lsp_pool is None, Dashboard returns {"lsps": [], "total_count": 0}
"""

# =============================================================================
# ERRORS - Exception handling requirements
# =============================================================================

ERRORS_OBS_01 = """
ERRORS-OBS-01: Observability exception suppression
    If ANY exception occurs during observability operations:
    - Exception MUST be caught (not propagated)
    - Empty valid structure MUST be returned
    - Exception MAY be logged at WARNING level

    Rationale: INV-OBS-02 requires dashboard always renders.

    Implementation pattern:
        try:
            return self._session_registry.get_session_overview()
        except Exception:
            return {"sessions": [], "total_count": 0}
"""

# =============================================================================
# Test Traceability Map (CL12-E Compliance)
# =============================================================================

TRACEABILITY = """
Test-to-Contract Traceability:

| Test | Enforces |
|------|----------|
| test_session_registry_property_returns_registry | POST-OBS-01 |
| test_lsp_pool_property_returns_pool_or_none | POST-OBS-02 |
| test_session_overview_response_structure | POST-OBS-03 |
| test_lsp_pool_stats_response_structure | POST-OBS-04 |
| test_observability_read_only | INV-OBS-01 |
| test_observability_never_raises | INV-OBS-02 |
| test_observability_returns_copies | INV-OBS-03 |
| test_observability_thread_safe | INV-OBS-04 |
| test_exception_returns_empty_structure | ERRORS-OBS-01 |
"""
