"""
Perl LSP Timeout Contract
=========================

Source: REQUIREMENT_MANIFEST REQ-2026-001 (self-elicited from observed behavior)

This contract defines behavioral requirements for Perl Language Server timeout
handling to prevent test suite hangs and ensure CI stability.

DISCONNECT MATRIX Reference:
| ID | Behavior | EXPECTED | OBSERVED | DELTA |
|----|----------|----------|----------|-------|
| B1 | Request timeout | 60s timeout | None (infinite) | OVERRIDE |
| B2 | Cross-file definition | XFAIL + timeout | FAIL then hang | NEW |
| B3 | Cross-file references | XFAIL + timeout | Hangs forever | NEW |

Contract Authority: This file is the SINGULAR authoritative source for Perl LSP
timeout requirements. All tests and implementations MUST trace to these specs.
"""

# =============================================================================
# INV (Invariants) - Properties that MUST remain true
# =============================================================================

INV_PERL_01 = """
INV-PERL-01: Request timeout MUST be configured
    Every SolidLanguageServer subclass MUST call set_request_timeout() with a
    non-None value in __init__. Infinite wait (timeout=None) is PROHIBITED.

    Rationale: Unconfigured timeout causes test suite hangs (observed: 1:50:46 hang
    on test_find_references_across_files[perl]).

    Enforcement: Test MUST verify _request_timeout is not None after construction.
"""

INV_PERL_02 = """
INV-PERL-02: Tests MUST NOT block suite indefinitely
    All LSP tests MUST complete or fail within a bounded time. Hanging tests
    that block CI pipelines are PROHIBITED.

    Rationale: Hanging tests waste compute resources and block deployments.

    Enforcement: pytest.mark.timeout(60) on all LSP request tests.
"""

INV_PERL_03 = """
INV-PERL-03: Known unstable tests MUST be marked XFAIL
    Tests with known issues (e.g., LSP doesn't respond to certain requests)
    MUST use @pytest.mark.xfail(reason="...", strict=False).

    Rationale: Known issues should not block unrelated work. XFAIL documents
    the issue while allowing suite to complete.

    Enforcement: Unstable cross-file tests marked with XFAIL + timeout.
"""

# =============================================================================
# PRE (Preconditions) - What MUST be true before operations
# =============================================================================

PRE_PERL_01 = """
PRE-PERL-01: Perl Language Server availability
    Perl::LanguageServer MUST be installed and available in PATH before tests.

    Verification: `perl -MPerl::LanguageServer -e 1` succeeds.
"""

PRE_PERL_02 = """
PRE-PERL-02: Test repository structure
    Test repository at test/resources/repos/perl/test_repo MUST contain:
    - main.pl with greet() and use_helper_function()
    - helper.pl with helper_function() definition

    Verification: Files exist with expected symbols.
"""

# =============================================================================
# POST (Postconditions) - What MUST be true after operations
# =============================================================================

POST_PERL_01 = """
POST-PERL-01: Timeout configuration complete
    After PerlLanguageServer.__init__() completes:
    - self._request_timeout MUST be numeric (not None)
    - Value MUST be >= 30.0 seconds (allow for slow operations)
    - Value SHOULD be 60.0 seconds (consistent with other slow LSPs)

    Verification: assert instance._request_timeout == 60.0
"""

POST_PERL_02 = """
POST-PERL-02: Document symbols test stability
    test_document_symbols[perl] MUST:
    - Complete within 60 seconds
    - Return symbols for main.pl including greet, use_helper_function

    Verification: Test passes (already stable, no changes needed).
"""

POST_PERL_03 = """
POST-PERL-03: Cross-file tests documented instability
    test_find_definition_across_files[perl] and test_find_references_across_files[perl]
    MUST be marked with:
    - @pytest.mark.timeout(60) - prevent infinite hang
    - @pytest.mark.xfail(reason="Perl::LanguageServer cross-file support unstable", strict=False)

    Verification: Tests are marked, suite completes even if they fail/timeout.
"""

# =============================================================================
# ERRORS - Exception handling requirements
# =============================================================================

ERRORS_PERL_01 = """
ERRORS-PERL-01: Timeout exception handling
    When LSP request times out (TimeoutError from get_result()):
    - Exception MUST be raised (not swallowed)
    - Test framework captures timeout and marks test as failed/xfail
    - Suite continues to next test (not blocked)

    Rationale: Timeout is better than hang. Failed test can be investigated.
"""

# =============================================================================
# Test Traceability Map
# =============================================================================

TRACEABILITY = """
Test-to-Contract Traceability (CL12-E Compliance):

| Test | Enforces |
|------|----------|
| test_perl_timeout_configured | INV-PERL-01, POST-PERL-01 |
| test_document_symbols[perl] | POST-PERL-02 |
| test_find_definition_across_files[perl] | INV-PERL-02, INV-PERL-03, POST-PERL-03 |
| test_find_references_across_files[perl] | INV-PERL-02, INV-PERL-03, POST-PERL-03 |
"""
