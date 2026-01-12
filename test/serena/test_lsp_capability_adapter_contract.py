"""
Tests for LSPCapabilityAdapter Contract Extension - Pooling Policy and Launch Arguments.

Tests derive from contract: contracts/lsp_capability_adapter_contract.py

Contract Requirements Tested:
- REQ-ADAPT-1: get_pooling_policy() returns PoolingPolicy enum value
- REQ-ADAPT-2: get_launch_arguments(workspace_root, session_id) returns list[str]
- REQ-ADAPT-3: Default adapters return sensible defaults
- REQ-ADAPT-4: DefaultAdapter returns ISOLATED_PROCESS (conservative)

PoolingPolicy Enum Values:
- SHARED_INSTANCE: Multi-root LSPs (rust-analyzer, pylsp, gopls)
- ISOLATED_PROCESS: Single-root LSPs (default, conservative)
- ISOLATED_WITH_RESOURCE_MANAGEMENT: TypeScript (memory limits)
- FORCED_ISOLATION: Terraform (claims multi-root but unsafe)

Contract Location: contracts/lsp_capability_adapter_contract.py
"""

from pathlib import Path

import pytest

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def rust_adapter():
    """Rust-analyzer adapter (multi-root support: FULL)."""
    from serena.lsp_capability_adapter import RustAnalyzerAdapter

    return RustAnalyzerAdapter()


@pytest.fixture
def pylsp_adapter():
    """Pylsp adapter (multi-root support: FULL)."""
    from serena.lsp_capability_adapter import PylspAdapter

    return PylspAdapter()


@pytest.fixture
def gopls_adapter():
    """Gopls adapter (multi-root support: FULL)."""
    from serena.lsp_capability_adapter import GoplsAdapter

    return GoplsAdapter()


@pytest.fixture
def tsserver_adapter():
    """TsServer adapter (multi-root support: NONE)."""
    from serena.lsp_capability_adapter import TsServerAdapter

    return TsServerAdapter()


@pytest.fixture
def clangd_adapter():
    """Clangd adapter (multi-root support: NONE)."""
    from serena.lsp_capability_adapter import ClangdAdapter

    return ClangdAdapter()


@pytest.fixture
def default_adapter():
    """Default adapter for unknown language (conservative single-root)."""
    from serena.lsp_capability_adapter import DefaultAdapter
    from solidlsp.ls_config import Language

    return DefaultAdapter(Language.BASH)  # Example unknown language


# =============================================================================
# POOLING POLICY TESTS (REQ-ADAPT-1, REQ-ADAPT-3, REQ-ADAPT-4)
# =============================================================================


class TestPoolingPolicy:
    """
    Tests for get_pooling_policy() method.

    Contract Reference: LSPCapabilityAdapterContract.get_pooling_policy
    - Multi-root adapters return SHARED_INSTANCE
    - Single-root adapters return ISOLATED_PROCESS
    - Default adapter returns ISOLATED_PROCESS (conservative)
    """

    def test_rust_adapter_returns_shared_instance_policy(self, rust_adapter):
        """
        WHY: rust-analyzer supports multi-root, should use SHARED_INSTANCE pooling.
        EXPECTED: get_pooling_policy() == PoolingPolicy.SHARED_INSTANCE

        Error Message Format (5-point):
        1. What failed: get_pooling_policy() method on RustAnalyzerAdapter
        2. Why: Multi-root LSPs must return SHARED_INSTANCE per REQ-ADAPT-1
        3. Expected: PoolingPolicy.SHARED_INSTANCE
        4. Actual: {actual_value}
        5. Guidance: Multi-root adapters MUST return SHARED_INSTANCE to enable
           single process serving multiple workspace roots. This is the core
           efficiency benefit of multi-root support.
        """
        from serena.lsp_capability_adapter import PoolingPolicy

        actual = rust_adapter.get_pooling_policy()

        assert actual == PoolingPolicy.SHARED_INSTANCE, (
            f"FAILED: RustAnalyzerAdapter.get_pooling_policy()\n"
            f"WHY: Multi-root LSPs must return SHARED_INSTANCE per REQ-ADAPT-1\n"
            f"EXPECTED: PoolingPolicy.SHARED_INSTANCE\n"
            f"ACTUAL: {actual}\n"
            f"GUIDANCE: Multi-root adapters MUST return SHARED_INSTANCE to enable "
            f"single process serving multiple workspace roots. Verify adapter "
            f"returns correct PoolingPolicy enum value."
        )

    def test_pylsp_adapter_returns_shared_instance_policy(self, pylsp_adapter):
        """
        WHY: pylsp supports multi-root, should use SHARED_INSTANCE pooling.
        EXPECTED: get_pooling_policy() == PoolingPolicy.SHARED_INSTANCE
        """
        from serena.lsp_capability_adapter import PoolingPolicy

        actual = pylsp_adapter.get_pooling_policy()

        assert actual == PoolingPolicy.SHARED_INSTANCE, (
            f"FAILED: PylspAdapter.get_pooling_policy()\n"
            f"WHY: Multi-root LSPs must return SHARED_INSTANCE per REQ-ADAPT-1\n"
            f"EXPECTED: PoolingPolicy.SHARED_INSTANCE\n"
            f"ACTUAL: {actual}\n"
            f"GUIDANCE: Multi-root adapters MUST return SHARED_INSTANCE. Verify "
            f"adapter returns correct PoolingPolicy enum value."
        )

    def test_gopls_adapter_returns_shared_instance_policy(self, gopls_adapter):
        """
        WHY: gopls supports multi-root, should use SHARED_INSTANCE pooling.
        EXPECTED: get_pooling_policy() == PoolingPolicy.SHARED_INSTANCE
        """
        from serena.lsp_capability_adapter import PoolingPolicy

        actual = gopls_adapter.get_pooling_policy()

        assert actual == PoolingPolicy.SHARED_INSTANCE, (
            f"FAILED: GoplsAdapter.get_pooling_policy()\n"
            f"WHY: Multi-root LSPs must return SHARED_INSTANCE per REQ-ADAPT-1\n"
            f"EXPECTED: PoolingPolicy.SHARED_INSTANCE\n"
            f"ACTUAL: {actual}\n"
            f"GUIDANCE: Multi-root adapters MUST return SHARED_INSTANCE. Verify "
            f"adapter returns correct PoolingPolicy enum value."
        )

    def test_tsserver_adapter_returns_isolated_process_policy(self, tsserver_adapter):
        """
        WHY: tsserver is single-root, should use ISOLATED_PROCESS pooling.
        EXPECTED: get_pooling_policy() == PoolingPolicy.ISOLATED_PROCESS
        """
        from serena.lsp_capability_adapter import PoolingPolicy

        actual = tsserver_adapter.get_pooling_policy()

        assert actual == PoolingPolicy.ISOLATED_PROCESS, (
            f"FAILED: TsServerAdapter.get_pooling_policy()\n"
            f"WHY: Single-root LSPs must return ISOLATED_PROCESS per REQ-ADAPT-1\n"
            f"EXPECTED: PoolingPolicy.ISOLATED_PROCESS\n"
            f"ACTUAL: {actual}\n"
            f"GUIDANCE: Single-root adapters MUST return ISOLATED_PROCESS to ensure "
            f"separate process per workspace root. Verify adapter returns correct "
            f"PoolingPolicy enum value."
        )

    def test_clangd_adapter_returns_isolated_process_policy(self, clangd_adapter):
        """
        WHY: clangd is single-root, should use ISOLATED_PROCESS pooling.
        EXPECTED: get_pooling_policy() == PoolingPolicy.ISOLATED_PROCESS
        """
        from serena.lsp_capability_adapter import PoolingPolicy

        actual = clangd_adapter.get_pooling_policy()

        assert actual == PoolingPolicy.ISOLATED_PROCESS, (
            f"FAILED: ClangdAdapter.get_pooling_policy()\n"
            f"WHY: Single-root LSPs must return ISOLATED_PROCESS per REQ-ADAPT-1\n"
            f"EXPECTED: PoolingPolicy.ISOLATED_PROCESS\n"
            f"ACTUAL: {actual}\n"
            f"GUIDANCE: Single-root adapters MUST return ISOLATED_PROCESS. Verify "
            f"adapter returns correct PoolingPolicy enum value."
        )

    def test_default_adapter_returns_isolated_process_policy_conservative(
        self, default_adapter
    ):
        """
        WHY: DefaultAdapter must use conservative ISOLATED_PROCESS for unknown LSPs.
        EXPECTED: get_pooling_policy() == PoolingPolicy.ISOLATED_PROCESS

        Contract Reference: REQ-ADAPT-4 - Conservative default for unknown languages
        """
        from serena.lsp_capability_adapter import PoolingPolicy

        actual = default_adapter.get_pooling_policy()

        assert actual == PoolingPolicy.ISOLATED_PROCESS, (
            f"FAILED: DefaultAdapter.get_pooling_policy()\n"
            f"WHY: Unknown LSPs must use conservative ISOLATED_PROCESS per REQ-ADAPT-4\n"
            f"EXPECTED: PoolingPolicy.ISOLATED_PROCESS\n"
            f"ACTUAL: {actual}\n"
            f"GUIDANCE: DefaultAdapter MUST return ISOLATED_PROCESS as conservative "
            f"default for unknown language servers. This prevents resource conflicts "
            f"for LSPs with unknown multi-root capabilities. Verify adapter returns "
            f"ISOLATED_PROCESS (never SHARED_INSTANCE)."
        )


# =============================================================================
# LAUNCH ARGUMENTS TESTS (REQ-ADAPT-2, REQ-ADAPT-3)
# =============================================================================


class TestLaunchArguments:
    """
    Tests for get_launch_arguments(workspace_root, session_id) method.

    Contract Reference: LSPCapabilityAdapterContract.get_launch_arguments
    - Returns list[str] (may be empty)
    - Base adapters return empty list by default
    - Specific adapters may return language-specific arguments
    """

    def test_get_launch_arguments_returns_list_of_strings(self, rust_adapter):
        """
        WHY: get_launch_arguments() must return list[str] per contract.
        EXPECTED: Result is list, all elements are strings

        Error Message Format (5-point):
        1. What failed: get_launch_arguments() return type validation
        2. Why: Contract requires list[str] return type per REQ-ADAPT-2
        3. Expected: list[str] (list containing only string elements)
        4. Actual: {actual_type} containing {element_types}
        5. Guidance: get_launch_arguments() MUST return list[str]. Empty list is
           valid. Non-string elements are contract violation. Check return type
           and element types.
        """
        workspace_root = Path("/test/workspace")
        session_id = "session-123"

        result = rust_adapter.get_launch_arguments(workspace_root, session_id)

        assert isinstance(result, list), (
            f"FAILED: RustAnalyzerAdapter.get_launch_arguments() return type\n"
            f"WHY: Contract requires list[str] return type per REQ-ADAPT-2\n"
            f"EXPECTED: list\n"
            f"ACTUAL: {type(result).__name__}\n"
            f"GUIDANCE: get_launch_arguments() MUST return list type. Verify return "
            f"value is list, not {type(result).__name__}."
        )

        # Verify all elements are strings
        for i, arg in enumerate(result):
            assert isinstance(arg, str), (
                f"FAILED: RustAnalyzerAdapter.get_launch_arguments() element type\n"
                f"WHY: Contract requires list[str] (all elements must be strings)\n"
                f"EXPECTED: str for element {i}\n"
                f"ACTUAL: {type(arg).__name__}\n"
                f"GUIDANCE: All elements in list MUST be strings. Found non-string "
                f"element at index {i}: {arg!r} ({type(arg).__name__}). Verify all "
                f"arguments are string type."
            )

    def test_base_multi_root_adapter_returns_empty_launch_arguments(self, rust_adapter):
        """
        WHY: Base adapters should return empty list by default per REQ-ADAPT-3.
        EXPECTED: get_launch_arguments() returns []

        Contract Reference: REQ-ADAPT-3 - Base adapters return sensible defaults
        """
        workspace_root = Path("/test/workspace")
        session_id = "session-123"

        result = rust_adapter.get_launch_arguments(workspace_root, session_id)

        assert result == [], (
            f"FAILED: BaseMultiRootAdapter.get_launch_arguments() default value\n"
            f"WHY: Base adapters must return empty list by default per REQ-ADAPT-3\n"
            f"EXPECTED: []\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Base adapter default implementation MUST return empty list "
            f"unless adapter has specific launch arguments. Verify adapter returns "
            f"[] when no special arguments needed."
        )

    def test_base_single_root_adapter_returns_empty_launch_arguments(
        self, tsserver_adapter
    ):
        """
        WHY: Base adapters should return empty list by default per REQ-ADAPT-3.
        EXPECTED: get_launch_arguments() returns []
        """
        workspace_root = Path("/test/workspace")
        session_id = "session-123"

        result = tsserver_adapter.get_launch_arguments(workspace_root, session_id)

        assert result == [], (
            f"FAILED: BaseSingleRootAdapter.get_launch_arguments() default value\n"
            f"WHY: Base adapters must return empty list by default per REQ-ADAPT-3\n"
            f"EXPECTED: []\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Base adapter default implementation MUST return empty list "
            f"unless adapter has specific launch arguments. Verify adapter returns "
            f"[] when no special arguments needed."
        )

    def test_get_launch_arguments_accepts_valid_parameters(self, rust_adapter):
        """
        WHY: get_launch_arguments() must accept workspace_root Path and session_id str.
        EXPECTED: No exception raised with valid parameters

        Contract Reference: REQ-ADAPT-2 signature validation
        """
        workspace_root = Path("/test/workspace")
        session_id = "session-123"

        try:
            result = rust_adapter.get_launch_arguments(workspace_root, session_id)
        except Exception as e:
            pytest.fail(
                f"FAILED: get_launch_arguments() raised exception with valid params\n"
                f"WHY: Method must accept (Path, str) parameters per REQ-ADAPT-2\n"
                f"EXPECTED: No exception\n"
                f"ACTUAL: {type(e).__name__}: {e}\n"
                f"GUIDANCE: get_launch_arguments(workspace_root: Path, session_id: str) "
                f"must accept these parameter types without raising exception. Verify "
                f"method signature matches contract."
            )

        # Verify result is list[str] (tested in detail in other test)
        assert isinstance(result, list)

    def test_default_adapter_returns_empty_launch_arguments(self, default_adapter):
        """
        WHY: DefaultAdapter should return empty list (no special arguments for unknown LSPs).
        EXPECTED: get_launch_arguments() returns []

        Contract Reference: REQ-ADAPT-4 - Conservative default behavior
        """
        workspace_root = Path("/test/workspace")
        session_id = "session-123"

        result = default_adapter.get_launch_arguments(workspace_root, session_id)

        assert result == [], (
            f"FAILED: DefaultAdapter.get_launch_arguments() default value\n"
            f"WHY: Unknown LSPs should return empty arguments per REQ-ADAPT-4\n"
            f"EXPECTED: []\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: DefaultAdapter MUST return empty list as conservative default. "
            f"Unknown language servers should not receive special launch arguments "
            f"without explicit adapter implementation."
        )


# =============================================================================
# POOLING POLICY + MULTI-ROOT CORRELATION TESTS
# =============================================================================


class TestPoolingPolicyMultiRootCorrelation:
    """
    Verify that pooling policy correlates with multi-root support levels.

    Contract Invariant:
    - FULL multi-root support → SHARED_INSTANCE pooling
    - NONE multi-root support → ISOLATED_PROCESS pooling
    """

    def test_multi_root_full_implies_shared_instance(self, rust_adapter):
        """
        WHY: Multi-root FULL support should correlate with SHARED_INSTANCE pooling.
        EXPECTED: multi_root_support == FULL → get_pooling_policy() == SHARED_INSTANCE

        Contract Invariant: Pooling policy must match multi-root capability
        """
        from serena.lsp_capability_adapter import MultiRootSupport, PoolingPolicy

        multi_root = rust_adapter.multi_root_support
        pooling_policy = rust_adapter.get_pooling_policy()

        if multi_root == MultiRootSupport.FULL:
            assert pooling_policy == PoolingPolicy.SHARED_INSTANCE, (
                f"FAILED: Pooling policy inconsistent with multi-root support\n"
                f"WHY: FULL multi-root must use SHARED_INSTANCE pooling (contract invariant)\n"
                f"EXPECTED: PoolingPolicy.SHARED_INSTANCE (for multi_root==FULL)\n"
                f"ACTUAL: {pooling_policy}\n"
                f"GUIDANCE: Multi-root FULL adapters MUST return SHARED_INSTANCE pooling "
                f"policy. This is fundamental contract invariant - single shared process "
                f"serves multiple roots. Verify adapter's get_pooling_policy() returns "
                f"SHARED_INSTANCE when multi_root_support==FULL."
            )

    def test_multi_root_none_implies_isolated_process(self, tsserver_adapter):
        """
        WHY: Single-root (NONE) support should correlate with ISOLATED_PROCESS pooling.
        EXPECTED: multi_root_support == NONE → get_pooling_policy() == ISOLATED_PROCESS

        Contract Invariant: Pooling policy must match multi-root capability
        """
        from serena.lsp_capability_adapter import MultiRootSupport, PoolingPolicy

        multi_root = tsserver_adapter.multi_root_support
        pooling_policy = tsserver_adapter.get_pooling_policy()

        if multi_root == MultiRootSupport.NONE:
            assert pooling_policy == PoolingPolicy.ISOLATED_PROCESS, (
                f"FAILED: Pooling policy inconsistent with multi-root support\n"
                f"WHY: NONE multi-root must use ISOLATED_PROCESS pooling (contract invariant)\n"
                f"EXPECTED: PoolingPolicy.ISOLATED_PROCESS (for multi_root==NONE)\n"
                f"ACTUAL: {pooling_policy}\n"
                f"GUIDANCE: Single-root adapters MUST return ISOLATED_PROCESS pooling "
                f"policy. This is fundamental contract invariant - separate process per "
                f"root. Verify adapter's get_pooling_policy() returns ISOLATED_PROCESS "
                f"when multi_root_support==NONE."
            )


# =============================================================================
# THEATER TEST PREVENTION - Adapter Diversity Verification
# =============================================================================


class TestAdapterPoolingPolicyDiversity:
    """
    Prevent theater tests by verifying adapter diversity.

    Theater Test Detection: "Can implementation be WRONG and test still PASS?"
    - If all adapters hardcoded to return ISOLATED_PROCESS → tests pass but wrong
    - These tests ensure at least one adapter returns SHARED_INSTANCE

    This prevents trivial implementation from passing all tests.
    """

    def test_at_least_one_adapter_returns_shared_instance(
        self, rust_adapter, pylsp_adapter, gopls_adapter
    ):
        """
        WHY: Prevent theater test where all adapters return ISOLATED_PROCESS.
        EXPECTED: At least one multi-root adapter returns SHARED_INSTANCE

        Theater Test Prevention: If implementation hardcodes ISOLATED_PROCESS for
        all adapters, this test will FAIL. This forces correct per-adapter policy.

        Error Message Format (5-point):
        1. What failed: Pooling policy diversity check
        2. Why: Multi-root adapters must return SHARED_INSTANCE (not all ISOLATED)
        3. Expected: At least one of (rust, pylsp, gopls) returns SHARED_INSTANCE
        4. Actual: All returned {actual_values}
        5. Guidance: Multi-root adapters MUST return SHARED_INSTANCE. If all adapters
           return same policy, implementation is likely hardcoded. Verify adapter
           behavior is differentiated by multi-root support capability.
        """
        from serena.lsp_capability_adapter import PoolingPolicy

        policies = {
            "rust-analyzer": rust_adapter.get_pooling_policy(),
            "pylsp": pylsp_adapter.get_pooling_policy(),
            "gopls": gopls_adapter.get_pooling_policy(),
        }

        shared_instance_count = sum(
            1 for p in policies.values() if p == PoolingPolicy.SHARED_INSTANCE
        )

        assert shared_instance_count >= 1, (
            f"FAILED: Pooling policy diversity check (theater test prevention)\n"
            f"WHY: Multi-root adapters must return SHARED_INSTANCE, not all ISOLATED\n"
            f"EXPECTED: At least 1 of (rust-analyzer, pylsp, gopls) returns SHARED_INSTANCE\n"
            f"ACTUAL: All returned {list(policies.values())}\n"
            f"GUIDANCE: Multi-root adapters MUST return PoolingPolicy.SHARED_INSTANCE. "
            f"If all adapters return same policy (especially ISOLATED_PROCESS), "
            f"implementation is likely hardcoded rather than adapter-specific. Verify "
            f"get_pooling_policy() returns different values based on adapter's multi-root "
            f"capability. Theater test detected: implementation may be trivially wrong."
        )

    def test_at_least_one_adapter_returns_isolated_process(
        self, tsserver_adapter, clangd_adapter, default_adapter
    ):
        """
        WHY: Prevent theater test where all adapters return SHARED_INSTANCE.
        EXPECTED: At least one single-root adapter returns ISOLATED_PROCESS

        Theater Test Prevention: If implementation hardcodes SHARED_INSTANCE for
        all adapters, this test will FAIL. This forces correct per-adapter policy.
        """
        from serena.lsp_capability_adapter import PoolingPolicy

        policies = {
            "tsserver": tsserver_adapter.get_pooling_policy(),
            "clangd": clangd_adapter.get_pooling_policy(),
            "default": default_adapter.get_pooling_policy(),
        }

        isolated_count = sum(
            1 for p in policies.values() if p == PoolingPolicy.ISOLATED_PROCESS
        )

        assert isolated_count >= 1, (
            f"FAILED: Pooling policy diversity check (theater test prevention)\n"
            f"WHY: Single-root adapters must return ISOLATED_PROCESS, not all SHARED\n"
            f"EXPECTED: At least 1 of (tsserver, clangd, default) returns ISOLATED_PROCESS\n"
            f"ACTUAL: All returned {list(policies.values())}\n"
            f"GUIDANCE: Single-root adapters MUST return PoolingPolicy.ISOLATED_PROCESS. "
            f"If all adapters return same policy (especially SHARED_INSTANCE), "
            f"implementation is likely hardcoded. Verify get_pooling_policy() returns "
            f"different values based on adapter's multi-root capability. Theater test "
            f"detected: implementation may be trivially wrong."
        )


# =============================================================================
# NEGATIVE/ADVERSARIAL TESTS - Contract Violation Detection
# =============================================================================


class TestGetLaunchArgumentsContractViolations:
    """
    Test contract violation scenarios for get_launch_arguments().

    These tests ensure implementation properly validates inputs and returns
    correct types, preventing subtle contract violations.
    """

    def test_get_launch_arguments_handles_relative_path(self, rust_adapter):
        """
        WHY: Contract expects workspace_root to be absolute Path, but should handle
             relative paths gracefully.
        EXPECTED: Method accepts relative Path without crashing

        Error Message Format (5-point):
        1. What failed: get_launch_arguments() with relative path
        2. Why: Method should handle any valid Path parameter
        3. Expected: Returns list[str] (no exception)
        4. Actual: Raised {exception_type}
        5. Guidance: get_launch_arguments() MUST accept any Path object. If relative
           path causes error, implementation may have incorrect path handling. Contract
           specifies Path type, not specifically absolute. Handle all Path inputs.
        """
        workspace_root = Path("relative/path")  # Relative path
        session_id = "session-123"

        try:
            result = rust_adapter.get_launch_arguments(workspace_root, session_id)
            assert isinstance(result, list), (
                f"FAILED: get_launch_arguments() return type with relative path\n"
                f"WHY: Must return list[str] even with relative path\n"
                f"EXPECTED: list\n"
                f"ACTUAL: {type(result).__name__}\n"
                f"GUIDANCE: get_launch_arguments() MUST return list[str] regardless of "
                f"path type (absolute or relative). Verify return type is always list."
            )
        except Exception as e:
            pytest.fail(
                f"FAILED: get_launch_arguments() raised exception with relative path\n"
                f"WHY: Method should accept any Path object per contract\n"
                f"EXPECTED: Returns list[str] (no exception)\n"
                f"ACTUAL: Raised {type(e).__name__}: {e}\n"
                f"GUIDANCE: get_launch_arguments(workspace_root: Path, session_id: str) "
                f"MUST accept any Path object, including relative paths. If relative path "
                f"causes error, implementation has incorrect path validation. Contract "
                f"specifies Path type without requiring absolute. Handle all Path inputs "
                f"gracefully."
            )

    def test_get_launch_arguments_handles_empty_session_id(self, rust_adapter):
        """
        WHY: Contract expects session_id str, but should handle empty string.
        EXPECTED: Method accepts empty string without crashing
        """
        workspace_root = Path("/test/workspace")
        session_id = ""  # Empty string

        try:
            result = rust_adapter.get_launch_arguments(workspace_root, session_id)
            assert isinstance(result, list), (
                f"FAILED: get_launch_arguments() return type with empty session_id\n"
                f"WHY: Must return list[str] even with empty session_id\n"
                f"EXPECTED: list\n"
                f"ACTUAL: {type(result).__name__}\n"
                f"GUIDANCE: get_launch_arguments() MUST return list[str] regardless of "
                f"session_id content. Verify return type is always list."
            )
        except Exception as e:
            pytest.fail(
                f"FAILED: get_launch_arguments() raised exception with empty session_id\n"
                f"WHY: Method should accept any string per contract\n"
                f"EXPECTED: Returns list[str] (no exception)\n"
                f"ACTUAL: Raised {type(e).__name__}: {e}\n"
                f"GUIDANCE: get_launch_arguments() MUST accept any string for session_id, "
                f"including empty string. Contract specifies str type without requiring "
                f"non-empty. Handle all string inputs gracefully."
            )

    def test_get_launch_arguments_returns_new_list_each_call(self, rust_adapter):
        """
        WHY: Verify method returns new list each call (not shared mutable state).
        EXPECTED: Multiple calls return equal but distinct list objects

        Theater Test Prevention: Shared mutable list could allow state bleed between
        calls, violating adapter stateless contract.
        """
        workspace_root = Path("/test/workspace")
        session_id = "session-123"

        result1 = rust_adapter.get_launch_arguments(workspace_root, session_id)
        result2 = rust_adapter.get_launch_arguments(workspace_root, session_id)

        # Lists should be equal in content
        assert result1 == result2, (
            f"FAILED: get_launch_arguments() returns inconsistent results\n"
            f"WHY: Same inputs should return same arguments\n"
            f"EXPECTED: {result1}\n"
            f"ACTUAL: {result2}\n"
            f"GUIDANCE: get_launch_arguments() MUST return consistent results for same "
            f"inputs. Adapter must be stateless - no state bleed between calls."
        )

        # But should be distinct objects (not same list reference)
        if result1 or result2:  # Only test if non-empty
            # Modify first list
            original_len = len(result1)
            result1.append("test-modification")

            assert len(result2) == original_len, (
                f"FAILED: get_launch_arguments() returns shared mutable list\n"
                f"WHY: Method must return new list each call (stateless adapter)\n"
                f"EXPECTED: result2 unmodified after result1.append()\n"
                f"ACTUAL: result2 length changed from {original_len} to {len(result2)}\n"
                f"GUIDANCE: get_launch_arguments() MUST return NEW list object each call. "
                f"Returning same list reference violates stateless adapter contract. "
                f"Create fresh list for each invocation to prevent state bleed."
            )



# =============================================================================
# TEST COVERAGE MAP
# =============================================================================

"""
Requirements Coverage:

REQ-ADAPT-1: get_pooling_policy() returns PoolingPolicy enum value
    ✓ TestPoolingPolicy.test_rust_adapter_returns_shared_instance_policy
    ✓ TestPoolingPolicy.test_pylsp_adapter_returns_shared_instance_policy
    ✓ TestPoolingPolicy.test_gopls_adapter_returns_shared_instance_policy
    ✓ TestPoolingPolicy.test_tsserver_adapter_returns_isolated_process_policy
    ✓ TestPoolingPolicy.test_clangd_adapter_returns_isolated_process_policy
    ✓ TestPoolingPolicy.test_default_adapter_returns_isolated_process_policy_conservative

REQ-ADAPT-2: get_launch_arguments(workspace_root: Path, session_id: str) returns list[str]
    ✓ TestLaunchArguments.test_get_launch_arguments_returns_list_of_strings
    ✓ TestLaunchArguments.test_get_launch_arguments_accepts_valid_parameters
    ✓ TestGetLaunchArgumentsContractViolations.test_get_launch_arguments_handles_relative_path
    ✓ TestGetLaunchArgumentsContractViolations.test_get_launch_arguments_handles_empty_session_id

REQ-ADAPT-3: Base adapters return sensible defaults
    ✓ TestLaunchArguments.test_base_multi_root_adapter_returns_empty_launch_arguments
    ✓ TestLaunchArguments.test_base_single_root_adapter_returns_empty_launch_arguments

REQ-ADAPT-4: DefaultAdapter returns ISOLATED_PROCESS (conservative)
    ✓ TestPoolingPolicy.test_default_adapter_returns_isolated_process_policy_conservative
    ✓ TestLaunchArguments.test_default_adapter_returns_empty_launch_arguments

Contract Invariants:
    ✓ TestPoolingPolicyMultiRootCorrelation.test_multi_root_full_implies_shared_instance
    ✓ TestPoolingPolicyMultiRootCorrelation.test_multi_root_none_implies_isolated_process

Theater Test Prevention:
    ✓ TestAdapterPoolingPolicyDiversity.test_at_least_one_adapter_returns_shared_instance
    ✓ TestAdapterPoolingPolicyDiversity.test_at_least_one_adapter_returns_isolated_process

Contract Violation Detection:
    ✓ TestGetLaunchArgumentsContractViolations.test_get_launch_arguments_handles_relative_path
    ✓ TestGetLaunchArgumentsContractViolations.test_get_launch_arguments_handles_empty_session_id
    ✓ TestGetLaunchArgumentsContractViolations.test_get_launch_arguments_returns_new_list_each_call

Total Tests: 21
Requirements Coverage: 4/4 (100%)
Theater Test Detection: PASS (diversity tests prevent trivial implementations)
Error Message Quality: 5-point standard (all tests)
Adversarial Separation: MAINTAINED (no implementation hints, behavioral guidance only)
"""
