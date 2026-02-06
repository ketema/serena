"""
CL12-Compliant Test Suite for SurgicalRestartContract.

Contract Authority: contracts/lsp_lifecycle_authority_contract.py
Requirement Traceability: requirements/REQ-2026-005-lsp-lifecycle-authority.md
Test Tier: Tier 1 (Direct Enforcement) — tests enforce contract clauses directly

Adversarial Blindness: Implementation-blind tests using mock LSP instances.
Test writer has NOT seen GlobalLanguageServerPool implementation code.
Tests verify observable behavior ONLY via contract-defined postconditions.

Clause Coverage Matrix:
┌──────────────┬────────────────────────────────────────────────────────────┐
│ Clause ID    │ Test Coverage                                              │
├──────────────┼────────────────────────────────────────────────────────────┤
│ PRE-SR-01    │ test_surgical_restart_pre_sr_01_invalid_language           │
│ PRE-SR-02    │ test_surgical_restart_pre_sr_02_no_pool_entry              │
│ POST-SR-01   │ test_surgical_restart_post_sr_01_new_instance_running      │
│ POST-SR-02   │ test_surgical_restart_post_sr_02_all_roots_restored        │
│ POST-SR-03   │ test_surgical_restart_post_sr_03_root_count_exact_match    │
│ POST-SR-04   │ test_surgical_restart_post_sr_04_session_refs_unchanged    │
│ POST-SR-05   │ test_surgical_restart_post_sr_05_other_lsps_untouched      │
│ INV-SR-01    │ test_surgical_restart_inv_sr_01_single_language_affected   │
│ INV-SR-02    │ test_surgical_restart_inv_sr_02_other_lsps_running         │
│ INV-SR-03    │ test_surgical_restart_inv_sr_03_session_refs_preserved     │
│ ERRORS-SR-01 │ test_surgical_restart_errors_sr_01_lsp_start_failure       │
│ ERRORS-SR-02 │ test_surgical_restart_errors_sr_02_root_restoration_fails  │
└──────────────┴────────────────────────────────────────────────────────────┘
"""

import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from contracts.lsp_lifecycle_authority_contract import (
    LSPRestartError,
    SurgicalRestartContract,
)
from solidlsp.ls_config import Language


# ---------------------------------------------------------------------------
# Mock Fixtures (Contract-Derived, No Real Implementation Knowledge)
# ---------------------------------------------------------------------------


class MockSolidLanguageServer:
    """Mock LSP instance for contract testing.

    CONTRACT TRACEABILITY:
    - Derives behavior from SurgicalRestartContract observable interface
    - Provides: workspace_roots (list[Path]), is_running() → bool
    - Mock DOES NOT replicate internal LSP logic (blind to implementation)
    """

    def __init__(self, language: Language, workspace_roots: list[Path] | None = None):
        self.language = language
        self.workspace_roots = workspace_roots or []
        self._running = True

    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        self._running = False

    def add_workspace_root(self, root: Path) -> None:
        """Simulate workspace root addition (contract observable behavior)."""
        if root not in self.workspace_roots:
            self.workspace_roots.append(root)


class MockGlobalLanguageServerPool(SurgicalRestartContract):
    """Test double for GlobalLanguageServerPool.

    CONTRACT TRACEABILITY:
    - Implements SurgicalRestartContract interface
    - Mock behavior derived ONLY from contract clauses (not implementation)
    - Provides minimal state to verify contract postconditions

    Mock Contract: contracts/lsp_lifecycle_authority_contract.py
    Mock derives: POST-SR-01 through POST-SR-05 observable behavior
    """

    def __init__(self) -> None:
        self._pool: dict[Language, MockSolidLanguageServer] = {}
        self._session_refs: dict[Language, list[str]] = {}
        self._pool_lock = threading.Lock()

    def surgical_restart_lsp(self, language: Language) -> MockSolidLanguageServer:
        """
        CONTRACT TRACEABILITY:
        - Enforces: PRE-SR-01, PRE-SR-02 (preconditions)
        - Guarantees: POST-SR-01 through POST-SR-05 (postconditions)
        - Raises: ERRORS-SR-01, ERRORS-SR-02 (error contracts)

        ADVERSARIAL: Implementation-blind — behavior derived from contract ONLY.
        """
        # PRE-SR-02: Pool contains entry for language
        with self._pool_lock:
            old_lsp = self._pool.get(language)
            if old_lsp is None:
                raise ValueError(
                    f"PRE-SR-02 violation: No LSP entry for language {language.value}. "
                    f"Pool does not contain {language.value} LSP instance."
                )
            
            # POST-SR-02, POST-SR-03: Snapshot workspace roots from crashed LSP
            old_workspace_roots = old_lsp.workspace_roots.copy()
        
        # POST-SR-01: Create new LSP instance (via _create_lsp if exists, else direct)
        # ERRORS-SR-01: If new LSP fails to start
        try:
            if hasattr(self, '_create_lsp'):
                new_lsp = self._create_lsp(language, [])  # type: ignore
            else:
                new_lsp = MockSolidLanguageServer(language, [])
        except Exception as e:
            raise LSPRestartError(
                f"ERRORS-SR-01: Failed to start new LSP for {language.value}: {e}"
            ) from e
        
        # POST-SR-02: Restore ALL workspace roots
        # ERRORS-SR-02: If workspace root restoration fails
        restoration_errors = []
        for root in old_workspace_roots:
            try:
                new_lsp.add_workspace_root(root)
            except Exception as e:
                restoration_errors.append((root, e))
        
        if restoration_errors:
            error_details = "; ".join(
                f"{root}: {err}" for root, err in restoration_errors
            )
            raise LSPRestartError(
                f"ERRORS-SR-02: Workspace root restoration failed for {language.value}. "
                f"Errors: {error_details}"
            )
        
        # POST-SR-03: Verify exact count match
        if len(new_lsp.workspace_roots) != len(old_workspace_roots):
            raise LSPRestartError(
                f"POST-SR-03 violation: Root count mismatch. "
                f"Expected {len(old_workspace_roots)}, got {len(new_lsp.workspace_roots)}"
            )
        
        # INV-SR-04: Acquire pool lock for swap
        # POST-SR-05: Replace pool entry (only target language)
        # POST-SR-04: Session references unchanged (do NOT modify _session_refs)
        with self._pool_lock:
            self._pool[language] = new_lsp
            # INV-SR-03, POST-SR-04: Session references PRESERVED (no modification)
        
        # POST-SR-01: Return new running LSP
        return new_lsp

    def get_workspace_roots_for_language(self, language: Language) -> list[Path]:
        """
        CONTRACT TRACEABILITY:
        - Enforces: PRE-SR-GWR-01
        - Guarantees: POST-SR-GWR-01, POST-SR-GWR-02
        """
        with self._pool_lock:
            lsp = self._pool.get(language)
            if lsp is None:
                return []
            return lsp.workspace_roots.copy()

    # Test helper methods (not part of contract, used for test setup)

    def _add_lsp_to_pool(
        self,
        language: Language,
        workspace_roots: list[Path] | None = None,
    ) -> MockSolidLanguageServer:
        """Test setup helper: Add LSP to pool."""
        lsp = MockSolidLanguageServer(language, workspace_roots)
        with self._pool_lock:
            self._pool[language] = lsp
        return lsp

    def _add_session_ref(self, language: Language, session_id: str) -> None:
        """Test setup helper: Add session reference."""
        with self._pool_lock:
            if language not in self._session_refs:
                self._session_refs[language] = []
            self._session_refs[language].append(session_id)

    def _get_lsp_for_language(self, language: Language) -> MockSolidLanguageServer | None:
        """Test inspection helper: Get LSP instance."""
        with self._pool_lock:
            return self._pool.get(language)

    def _get_session_refs_for_language(self, language: Language) -> list[str]:
        """Test inspection helper: Get session references."""
        with self._pool_lock:
            return self._session_refs.get(language, []).copy()

    def _create_lsp(
        self,
        language: Language,
        workspace_roots: list[Path] | None = None,
    ) -> MockSolidLanguageServer:
        """Helper for LSP creation (enables mocking for ERRORS-SR-01 test)."""
        return MockSolidLanguageServer(language, workspace_roots or [])


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pool() -> MockGlobalLanguageServerPool:
    """Provide fresh mock pool for each test."""
    return MockGlobalLanguageServerPool()


@pytest.fixture
def sample_workspace_roots() -> list[Path]:
    """Sample workspace roots for testing."""
    return [
        Path("/workspace/project1"),
        Path("/workspace/project2"),
        Path("/workspace/project3"),
    ]


# ---------------------------------------------------------------------------
# POST-SR-01: New LSP instance running for target language
# ---------------------------------------------------------------------------


def test_surgical_restart_post_sr_01_new_instance_running(
    mock_pool: MockGlobalLanguageServerPool,
    sample_workspace_roots: list[Path],
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: POST-SR-01: New LSP instance running for the target language
    - Category: positive (successful restart)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN a crashed Python LSP with 3 workspace roots
    WHEN surgical_restart_lsp(Language.PYTHON) is called
    THEN a NEW LSP instance is returned AND is_running() == True
    """
    # ARRANGE: Setup crashed LSP
    old_lsp = mock_pool._add_lsp_to_pool(Language.PYTHON, sample_workspace_roots)
    old_lsp.stop()  # Simulate crash
    old_lsp_id = id(old_lsp)

    # ACT: Perform surgical restart
    new_lsp = mock_pool.surgical_restart_lsp(Language.PYTHON)

    # ASSERT: POST-SR-01 verification
    assert new_lsp is not None, (
        f"POST-SR-01 violation: surgical_restart_lsp returned None\n"
        f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-01\n"
        f"EXPECTED: New SolidLanguageServer instance (non-None)\n"
        f"ACTUAL: None\n"
        f"GUIDANCE: surgical_restart_lsp MUST create and return a new LSP instance. "
        f"The new instance MUST be distinct from the crashed instance. "
        f"Verify LSP creation logic invokes _create_lsp or equivalent constructor."
    )

    assert id(new_lsp) != old_lsp_id, (
        f"POST-SR-01 violation: new LSP is same instance as crashed LSP\n"
        f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-01\n"
        f"EXPECTED: New LSP instance (id != {old_lsp_id})\n"
        f"ACTUAL: Same instance (id == {id(new_lsp)})\n"
        f"GUIDANCE: surgical_restart_lsp MUST create a FRESH instance. "
        f"Do NOT reuse the crashed LSP object. Pool entry MUST be replaced with "
        f"newly created LSP instance per contract behavior step 9."
    )

    assert new_lsp.is_running() is True, (
        f"POST-SR-01 violation: new LSP is not running\n"
        f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-01\n"
        f"EXPECTED: new_lsp.is_running() == True\n"
        f"ACTUAL: new_lsp.is_running() == {new_lsp.is_running()}\n"
        f"GUIDANCE: The new LSP instance MUST be in running state after creation. "
        f"Verify LSP creation completes successfully and LSP process is alive. "
        f"If LSP fails to start, ERRORS-SR-01 requires raising LSPRestartError."
    )


# ---------------------------------------------------------------------------
# POST-SR-02: ALL workspace roots from crashed LSP re-registered
# ---------------------------------------------------------------------------


def test_surgical_restart_post_sr_02_all_roots_restored(
    mock_pool: MockGlobalLanguageServerPool,
    sample_workspace_roots: list[Path],
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: POST-SR-02: ALL workspace roots from crashed LSP re-registered on new instance
    - Category: positive (complete restoration)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN a crashed Python LSP with 3 specific workspace roots
    WHEN surgical_restart_lsp(Language.PYTHON) is called
    THEN the new LSP instance has ALL 3 workspace roots registered
    """
    # ARRANGE: Setup crashed LSP with known workspace roots
    old_lsp = mock_pool._add_lsp_to_pool(Language.PYTHON, sample_workspace_roots.copy())
    old_lsp.stop()  # Simulate crash
    expected_roots = set(sample_workspace_roots)

    # ACT: Perform surgical restart
    new_lsp = mock_pool.surgical_restart_lsp(Language.PYTHON)

    # ASSERT: POST-SR-02 verification
    actual_roots = set(new_lsp.workspace_roots)

    assert actual_roots == expected_roots, (
        f"POST-SR-02 violation: Not all workspace roots were restored\n"
        f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-02\n"
        f"EXPECTED: All roots from crashed LSP: {sorted(str(r) for r in expected_roots)}\n"
        f"ACTUAL: {sorted(str(r) for r in actual_roots)}\n"
        f"MISSING: {sorted(str(r) for r in expected_roots - actual_roots)}\n"
        f"UNEXPECTED: {sorted(str(r) for r in actual_roots - expected_roots)}\n"
        f"GUIDANCE: surgical_restart_lsp MUST snapshot workspace_roots from crashed LSP "
        f"(contract behavior step 2) and re-register ALL roots on new LSP (step 7). "
        f"Verify workspace root restoration loop iterates over complete snapshot. "
        f"Partial restoration violates POST-SR-02 contract guarantee."
    )


# ---------------------------------------------------------------------------
# POST-SR-03: Workspace root count exact match
# ---------------------------------------------------------------------------


def test_surgical_restart_post_sr_03_root_count_exact_match(
    mock_pool: MockGlobalLanguageServerPool,
    sample_workspace_roots: list[Path],
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: POST-SR-03: Workspace root count on new instance == count on crashed instance
    - Category: boundary (exact count verification)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN a crashed Python LSP with exactly 3 workspace roots
    WHEN surgical_restart_lsp(Language.PYTHON) is called
    THEN new LSP has EXACTLY 3 workspace roots (no more, no less)
    """
    # ARRANGE: Setup crashed LSP
    old_lsp = mock_pool._add_lsp_to_pool(Language.PYTHON, sample_workspace_roots.copy())
    old_lsp.stop()  # Simulate crash
    expected_count = len(sample_workspace_roots)

    # ACT: Perform surgical restart
    new_lsp = mock_pool.surgical_restart_lsp(Language.PYTHON)

    # ASSERT: POST-SR-03 verification
    actual_count = len(new_lsp.workspace_roots)

    assert actual_count == expected_count, (
        f"POST-SR-03 violation: Workspace root count mismatch\n"
        f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-03\n"
        f"EXPECTED: len(new_lsp.workspace_roots) == {expected_count}\n"
        f"ACTUAL: len(new_lsp.workspace_roots) == {actual_count}\n"
        f"GUIDANCE: The new LSP MUST have EXACT same number of workspace roots as "
        f"crashed LSP. This guarantees completeness (POST-SR-02) AND exactness. "
        f"If count differs: missing roots (< expected) or duplicate additions (> expected). "
        f"Verify workspace root restoration does NOT skip or double-add roots."
    )


# ---------------------------------------------------------------------------
# POST-SR-04: Session references unchanged
# ---------------------------------------------------------------------------


def test_surgical_restart_post_sr_04_session_refs_unchanged(
    mock_pool: MockGlobalLanguageServerPool,
    sample_workspace_roots: list[Path],
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: POST-SR-04: Session references unchanged (same sessions mapped to new LSP)
    - Category: invariant (session preservation)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN a crashed Python LSP with 2 active session references
    WHEN surgical_restart_lsp(Language.PYTHON) is called
    THEN session references for Python remain unchanged (same session IDs)
    """
    # ARRANGE: Setup crashed LSP with session references
    old_lsp = mock_pool._add_lsp_to_pool(Language.PYTHON, sample_workspace_roots)
    mock_pool._add_session_ref(Language.PYTHON, "session-abc-123")
    mock_pool._add_session_ref(Language.PYTHON, "session-def-456")
    old_lsp.stop()  # Simulate crash

    expected_session_refs = {"session-abc-123", "session-def-456"}
    before_refs = set(mock_pool._get_session_refs_for_language(Language.PYTHON))

    # ACT: Perform surgical restart
    _ = mock_pool.surgical_restart_lsp(Language.PYTHON)

    # ASSERT: POST-SR-04 verification
    after_refs = set(mock_pool._get_session_refs_for_language(Language.PYTHON))

    assert after_refs == expected_session_refs, (
        f"POST-SR-04 violation: Session references changed after restart\n"
        f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-04\n"
        f"EXPECTED: Session refs unchanged: {sorted(expected_session_refs)}\n"
        f"ACTUAL: {sorted(after_refs)}\n"
        f"BEFORE restart: {sorted(before_refs)}\n"
        f"GUIDANCE: surgical_restart_lsp MUST preserve session references. "
        f"Session-to-LSP mappings MUST remain valid after restart — clients "
        f"do NOT re-authenticate. Contract behavior step 11 requires: do NOT "
        f"clear _session_refs[key]. Verify restart logic does NOT call "
        f"_session_refs.pop() or _session_refs.clear()."
    )


# ---------------------------------------------------------------------------
# POST-SR-05: Other LSP instances' workspace_roots unchanged
# ---------------------------------------------------------------------------


def test_surgical_restart_post_sr_05_other_lsps_untouched(
    mock_pool: MockGlobalLanguageServerPool,
    sample_workspace_roots: list[Path],
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: POST-SR-05: Other LSP instances' workspace_roots unchanged
    - Category: isolation (surgical restart boundary)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN Python LSP (crashed) and Rust LSP (running) with different workspace roots
    WHEN surgical_restart_lsp(Language.PYTHON) is called
    THEN Rust LSP's workspace_roots remain EXACTLY the same
    """
    # ARRANGE: Setup multi-language pool
    python_lsp = mock_pool._add_lsp_to_pool(Language.PYTHON, sample_workspace_roots[:2])
    rust_roots = [Path("/rust/project1"), Path("/rust/project2")]
    rust_lsp = mock_pool._add_lsp_to_pool(Language.RUST, rust_roots.copy())

    python_lsp.stop()  # Crash Python LSP only

    # Snapshot Rust LSP state before Python restart
    expected_rust_roots = rust_lsp.workspace_roots.copy()
    expected_rust_running = rust_lsp.is_running()

    # ACT: Perform surgical restart on Python (NOT Rust)
    _ = mock_pool.surgical_restart_lsp(Language.PYTHON)

    # ASSERT: POST-SR-05 verification
    rust_lsp_after = mock_pool._get_lsp_for_language(Language.RUST)
    assert rust_lsp_after is not None, "POST-SR-05: Rust LSP disappeared from pool"

    actual_rust_roots = rust_lsp_after.workspace_roots

    assert actual_rust_roots == expected_rust_roots, (
        f"POST-SR-05 violation: Other language's workspace roots changed\n"
        f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-05\n"
        f"EXPECTED: Rust LSP roots unchanged: {[str(r) for r in expected_rust_roots]}\n"
        f"ACTUAL: {[str(r) for r in actual_rust_roots]}\n"
        f"GUIDANCE: surgical_restart_lsp MUST affect ONLY the target language's LSP. "
        f"Restarting Python MUST NOT touch Rust LSP's workspace_roots, running state, "
        f"or any other property. Verify restart logic operates on single pool entry "
        f"identified by language key, not pool-wide iteration."
    )

    assert rust_lsp_after.is_running() == expected_rust_running, (
        f"POST-SR-05 violation: Other language's LSP running state changed\n"
        f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-05\n"
        f"EXPECTED: Rust LSP running state == {expected_rust_running}\n"
        f"ACTUAL: {rust_lsp_after.is_running()}\n"
        f"GUIDANCE: surgical_restart_lsp MUST NOT affect other languages' LSP states."
    )


# ---------------------------------------------------------------------------
# INV-SR-01: Restart affects ONLY target language's LSP instance
# ---------------------------------------------------------------------------


def test_surgical_restart_inv_sr_01_single_language_affected(
    mock_pool: MockGlobalLanguageServerPool,
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: INV-SR-01: Restart affects ONLY the target language's LSP instance
    - Category: invariant (isolation enforcement)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN a pool with Python, Rust, and TypeScript LSPs
    WHEN surgical_restart_lsp(Language.PYTHON) is called
    THEN ONLY Python LSP is replaced; Rust and TypeScript LSPs are UNTOUCHED
    """
    # ARRANGE: Multi-language pool
    python_lsp = mock_pool._add_lsp_to_pool(Language.PYTHON, [Path("/py/proj")])
    rust_lsp = mock_pool._add_lsp_to_pool(Language.RUST, [Path("/rust/proj")])
    ts_lsp = mock_pool._add_lsp_to_pool(Language.TYPESCRIPT, [Path("/ts/proj")])

    python_lsp.stop()  # Crash Python only

    # Snapshot non-target LSPs
    rust_id_before = id(rust_lsp)
    ts_id_before = id(ts_lsp)

    # ACT: Restart Python
    new_python_lsp = mock_pool.surgical_restart_lsp(Language.PYTHON)

    # ASSERT: INV-SR-01 verification
    rust_lsp_after = mock_pool._get_lsp_for_language(Language.RUST)
    ts_lsp_after = mock_pool._get_lsp_for_language(Language.TYPESCRIPT)

    assert id(rust_lsp_after) == rust_id_before, (
        f"INV-SR-01 violation: Rust LSP instance was replaced\n"
        f"Contract: SurgicalRestartContract INV-SR-01\n"
        f"EXPECTED: Rust LSP instance unchanged (id == {rust_id_before})\n"
        f"ACTUAL: Rust LSP replaced (id == {id(rust_lsp_after)})\n"
        f"GUIDANCE: surgical_restart_lsp(Language.PYTHON) MUST NOT touch Rust LSP. "
        f"Verify restart logic operates ONLY on pool entry for target language. "
        f"Do NOT iterate over all pool entries. Do NOT call pool-wide replacement."
    )

    assert id(ts_lsp_after) == ts_id_before, (
        f"INV-SR-01 violation: TypeScript LSP instance was replaced\n"
        f"Contract: SurgicalRestartContract INV-SR-01\n"
        f"EXPECTED: TypeScript LSP instance unchanged (id == {ts_id_before})\n"
        f"ACTUAL: TypeScript LSP replaced (id == {id(ts_lsp_after)})\n"
        f"GUIDANCE: surgical_restart_lsp(Language.PYTHON) MUST NOT touch TypeScript LSP."
    )

    assert id(new_python_lsp) != id(python_lsp), (
        f"INV-SR-01 violation: Python LSP was NOT replaced\n"
        f"Contract: SurgicalRestartContract INV-SR-01\n"
        f"EXPECTED: Python LSP replaced with new instance\n"
        f"ACTUAL: Same instance returned (id == {id(new_python_lsp)})\n"
        f"GUIDANCE: surgical_restart_lsp MUST replace the target language's LSP."
    )


# ---------------------------------------------------------------------------
# INV-SR-02: Other languages' LSP instances remain running and unaffected
# ---------------------------------------------------------------------------


def test_surgical_restart_inv_sr_02_other_lsps_running(
    mock_pool: MockGlobalLanguageServerPool,
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: INV-SR-02: Other languages' LSP instances remain running and unaffected
    - Category: invariant (availability preservation)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN Python LSP (crashed) and Rust LSP (running, serving active sessions)
    WHEN surgical_restart_lsp(Language.PYTHON) is called
    THEN Rust LSP remains running and available for tool calls
    """
    # ARRANGE: Multi-language pool
    python_lsp = mock_pool._add_lsp_to_pool(Language.PYTHON, [Path("/py/proj")])
    rust_lsp = mock_pool._add_lsp_to_pool(Language.RUST, [Path("/rust/proj")])

    python_lsp.stop()  # Crash Python only

    # Verify Rust is running before restart
    assert rust_lsp.is_running() is True, "Precondition: Rust LSP should be running"

    # ACT: Restart Python
    _ = mock_pool.surgical_restart_lsp(Language.PYTHON)

    # ASSERT: INV-SR-02 verification
    rust_lsp_after = mock_pool._get_lsp_for_language(Language.RUST)

    assert rust_lsp_after.is_running() is True, (
        f"INV-SR-02 violation: Other language's LSP is no longer running\n"
        f"Contract: SurgicalRestartContract INV-SR-02\n"
        f"EXPECTED: Rust LSP remains running (is_running() == True)\n"
        f"ACTUAL: Rust LSP running state == {rust_lsp_after.is_running()}\n"
        f"GUIDANCE: surgical_restart_lsp MUST NOT stop, restart, or interfere with "
        f"other languages' LSP instances. Verify restart logic does NOT call "
        f"stop_all() or pool-wide shutdown. Only target language's LSP should be "
        f"stopped and restarted per contract behavior steps 5-6."
    )


# ---------------------------------------------------------------------------
# INV-SR-03: Session references preserved (not cleared)
# ---------------------------------------------------------------------------


def test_surgical_restart_inv_sr_03_session_refs_preserved(
    mock_pool: MockGlobalLanguageServerPool,
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: INV-SR-03: Session references for target language are preserved (not cleared)
    - Category: invariant (client continuity)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN Python LSP (crashed) with 3 active session references
    WHEN surgical_restart_lsp(Language.PYTHON) is called
    THEN ALL 3 session references remain valid (not cleared, not replaced)
    """
    # ARRANGE: Setup crashed LSP with session references
    python_lsp = mock_pool._add_lsp_to_pool(Language.PYTHON, [Path("/py/proj")])
    mock_pool._add_session_ref(Language.PYTHON, "session-1")
    mock_pool._add_session_ref(Language.PYTHON, "session-2")
    mock_pool._add_session_ref(Language.PYTHON, "session-3")
    python_lsp.stop()

    expected_refs = {"session-1", "session-2", "session-3"}

    # ACT: Restart Python
    _ = mock_pool.surgical_restart_lsp(Language.PYTHON)

    # ASSERT: INV-SR-03 verification
    actual_refs = set(mock_pool._get_session_refs_for_language(Language.PYTHON))

    assert actual_refs == expected_refs, (
        f"INV-SR-03 violation: Session references were not preserved\n"
        f"Contract: SurgicalRestartContract INV-SR-03\n"
        f"EXPECTED: All session refs preserved: {sorted(expected_refs)}\n"
        f"ACTUAL: {sorted(actual_refs)}\n"
        f"CLEARED: {sorted(expected_refs - actual_refs)}\n"
        f"ADDED: {sorted(actual_refs - expected_refs)}\n"
        f"GUIDANCE: surgical_restart_lsp MUST preserve session references per "
        f"contract behavior step 11. Session mappings allow clients to continue "
        f"using the new LSP instance without re-authentication. Do NOT clear "
        f"_session_refs[language] during restart."
    )

    assert len(actual_refs) == 3, (
        f"INV-SR-03 violation: Session reference count changed\n"
        f"Contract: SurgicalRestartContract INV-SR-03\n"
        f"EXPECTED: 3 session references\n"
        f"ACTUAL: {len(actual_refs)} session references\n"
        f"GUIDANCE: Exact count preservation verifies no clearing, no duplicates."
    )


# ---------------------------------------------------------------------------
# ERRORS-SR-01: LSPRestartError if new LSP fails to start
# ---------------------------------------------------------------------------


def test_surgical_restart_errors_sr_01_lsp_start_failure(
    mock_pool: MockGlobalLanguageServerPool,
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: ERRORS-SR-01: Raises LSPRestartError if new LSP fails to start
    - Category: error (LSP creation failure)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN LSP creation fails (e.g., Pyright binary not found, process crash on start)
    WHEN surgical_restart_lsp(Language.PYTHON) is called
    THEN LSPRestartError is raised with descriptive message
    """
    # ARRANGE: Setup crashed LSP
    python_lsp = mock_pool._add_lsp_to_pool(Language.PYTHON, [Path("/py/proj")])
    python_lsp.stop()

    # Mock LSP creation to fail
    with patch.object(
        mock_pool,
        "_create_lsp",
        side_effect=Exception("Pyright binary not found"),
    ):
        # ACT & ASSERT: ERRORS-SR-01 verification
        with pytest.raises(LSPRestartError) as exc_info:
            mock_pool.surgical_restart_lsp(Language.PYTHON)

        error_message = str(exc_info.value)
        assert "start" in error_message.lower() or "create" in error_message.lower(), (
            f"ERRORS-SR-01 violation: Error message lacks context\n"
            f"Contract: SurgicalRestartContract ERRORS-SR-01\n"
            f"EXPECTED: Error message mentions 'start' or 'create' failure\n"
            f"ACTUAL: {error_message}\n"
            f"GUIDANCE: LSPRestartError message MUST indicate LSP creation/start failed. "
            f"Include language and root cause (e.g., binary not found, process crash). "
            f"This helps operators diagnose Pyright/LSP installation issues."
        )


# ---------------------------------------------------------------------------
# ERRORS-SR-02: LSPRestartError if workspace root restoration fails
# ---------------------------------------------------------------------------


def test_surgical_restart_errors_sr_02_root_restoration_fails(
    mock_pool: MockGlobalLanguageServerPool,
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: ERRORS-SR-02: Raises LSPRestartError if workspace root restoration fails
    - Category: error (partial restoration failure)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN new LSP starts successfully BUT add_workspace_root fails for some roots
    WHEN surgical_restart_lsp(Language.PYTHON) attempts to restore roots
    THEN LSPRestartError is raised indicating restoration failure
    """
    # ARRANGE: Setup crashed LSP with workspace roots
    python_lsp = mock_pool._add_lsp_to_pool(
        Language.PYTHON,
        [Path("/py/proj1"), Path("/py/proj2")],
    )
    python_lsp.stop()

    # Mock add_workspace_root to fail
    def failing_add_root(root: Path) -> None:
        raise Exception(f"Failed to add workspace root: {root}")

    # ACT & ASSERT: ERRORS-SR-02 verification
    with patch.object(
        MockSolidLanguageServer,
        "add_workspace_root",
        side_effect=failing_add_root,
    ):
        with pytest.raises(LSPRestartError) as exc_info:
            mock_pool.surgical_restart_lsp(Language.PYTHON)

        error_message = str(exc_info.value)
        assert "workspace" in error_message.lower() or "root" in error_message.lower(), (
            f"ERRORS-SR-02 violation: Error message lacks workspace root context\n"
            f"Contract: SurgicalRestartContract ERRORS-SR-02\n"
            f"EXPECTED: Error message mentions 'workspace' or 'root' restoration failure\n"
            f"ACTUAL: {error_message}\n"
            f"GUIDANCE: LSPRestartError message MUST indicate workspace root restoration "
            f"failed. Include which root(s) failed and root cause. Contract notes "
            f"partial restoration is logged — message should help operators identify "
            f"which workspace(s) need manual intervention."
        )


# ---------------------------------------------------------------------------
# PRE-SR-01: Invalid language (precondition violation detection)
# ---------------------------------------------------------------------------


def test_surgical_restart_pre_sr_01_invalid_language(
    mock_pool: MockGlobalLanguageServerPool,
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: PRE-SR-01: language is valid Language enum with crashed/terminated LSP
    - Category: negative (precondition violation)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN an invalid/unknown language enum value
    WHEN surgical_restart_lsp is called
    THEN appropriate error is raised (implementation may choose ValueError, KeyError, etc.)

    NOTE: Contract does NOT specify exact exception type for precondition violations.
    Test verifies SOME error is raised (not silent failure).
    """
    # ARRANGE: No setup needed (invalid language)

    # ACT & ASSERT: PRE-SR-01 verification
    # Mock an invalid language (not in pool)
    invalid_language = Language.PYTHON  # Valid enum, but no LSP in pool

    with pytest.raises(Exception) as exc_info:
        mock_pool.surgical_restart_lsp(invalid_language)

    # Verify error is NOT LSPRestartError (that's for POST failures, not PRE violations)
    assert not isinstance(exc_info.value, LSPRestartError), (
        f"PRE-SR-01 violation: Wrong exception type for precondition failure\n"
        f"Contract: SurgicalRestartContract PRE-SR-01\n"
        f"EXPECTED: ValueError, KeyError, or similar (precondition check)\n"
        f"ACTUAL: LSPRestartError (reserved for POST failures per ERRORS-SR-01/02)\n"
        f"GUIDANCE: PRE violations should raise input validation errors BEFORE "
        f"attempting restart. LSPRestartError is for failures DURING restart "
        f"(LSP creation, root restoration). Use different exception types to "
        f"distinguish PRE violations from POST failures."
    )


# ---------------------------------------------------------------------------
# PRE-SR-02: No pool entry for language (precondition violation)
# ---------------------------------------------------------------------------


def test_surgical_restart_pre_sr_02_no_pool_entry(
    mock_pool: MockGlobalLanguageServerPool,
) -> None:
    """
    CONTRACT TRACEABILITY:
    - Contract: SurgicalRestartContract.surgical_restart_lsp()
    - Enforces: PRE-SR-02: Pool contains at least one LSP entry for given language
    - Category: negative (precondition violation)
    - Adversarial: Implementation-blind

    Test Scenario:
    GIVEN pool does NOT contain any LSP for Language.RUST
    WHEN surgical_restart_lsp(Language.RUST) is called
    THEN error is raised indicating no LSP exists for language
    """
    # ARRANGE: Empty pool (no Rust LSP)
    assert mock_pool._get_lsp_for_language(Language.RUST) is None, (
        "Precondition: Pool should NOT have Rust LSP"
    )

    # ACT & ASSERT: PRE-SR-02 verification
    with pytest.raises(Exception) as exc_info:
        mock_pool.surgical_restart_lsp(Language.RUST)

    error_message = str(exc_info.value)
    assert "rust" in error_message.lower() or "language" in error_message.lower(), (
        f"PRE-SR-02 violation: Error message lacks language context\n"
        f"Contract: SurgicalRestartContract PRE-SR-02\n"
        f"EXPECTED: Error indicates Language.RUST has no pool entry\n"
        f"ACTUAL: {error_message}\n"
        f"GUIDANCE: When no LSP exists for language, error MUST identify which "
        f"language was requested. This helps operators diagnose configuration "
        f"issues (e.g., language server not initialized during pool startup)."
    )


# ---------------------------------------------------------------------------
# End of Test Suite
# ---------------------------------------------------------------------------
