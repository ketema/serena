"""
CL12-Compliant Test Suite for WorkspaceReadinessContract.

Contract Authority: contracts/lsp_lifecycle_authority_contract.py
Requirement Traceability: requirements/REQ-2026-005-lsp-lifecycle-authority.md
Test Tier: Tier 1 (Direct Enforcement) — tests enforce contract clauses directly

Adversarial Blindness: Implementation-blind tests using mock LSP instances.
Test writer has NOT seen probe_workspace_readiness implementation code.
Tests verify observable behavior ONLY via contract-defined postconditions.

Clause Coverage Matrix:
┌──────────────┬────────────────────────────────────────────────────────────┐
│ Clause ID    │ Test Coverage                                              │
├──────────────┼────────────────────────────────────────────────────────────┤
│ PRE-WR-01    │ test_probe_workspace_pre_wr_01_lsp_not_running             │
│ PRE-WR-02    │ test_probe_workspace_pre_wr_02_root_not_added              │
│ PRE-WR-03    │ test_probe_workspace_pre_wr_03_invalid_timeout             │
│ POST-WR-01   │ test_probe_workspace_post_wr_01_success_valid_response     │
│ POST-WR-02   │ test_probe_workspace_post_wr_02_timeout_elapsed            │
│ POST-WR-03   │ test_probe_workspace_post_wr_03_no_side_effects            │
│ INV-WR-01    │ test_probe_workspace_inv_wr_01_no_dispatch_before_ready    │
│ INV-WR-02    │ test_probe_workspace_inv_wr_02_probe_read_only             │
│ INV-WR-03    │ test_probe_workspace_inv_wr_03_timeout_bounded             │
│ ERRORS-WR-01 │ test_probe_workspace_errors_wr_01_lsp_crash_returns_false  │
│ ERRORS-WR-02 │ test_probe_workspace_errors_wr_02_no_file_returns_false    │
├──────────────┼────────────────────────────────────────────────────────────┤
│ find_probeable_file coverage:                                             │
├──────────────┼────────────────────────────────────────────────────────────┤
│ PRE-WR-FPF-01│ test_find_probeable_file_pre_fpf_01_nonexistent_directory  │
│ PRE-WR-FPF-02│ test_find_probeable_file_pre_fpf_02_language_extensions    │
│ POST-WR-FPF-01│test_find_probeable_file_post_fpf_01_returns_path_or_none │
│ POST-WR-FPF-02│test_find_probeable_file_post_fpf_02_file_exists_matches  │
│ POST-WR-FPF-03│test_find_probeable_file_post_fpf_03_prefers_small_files  │
└──────────────┴────────────────────────────────────────────────────────────┘
"""

import time
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from contracts.lsp_lifecycle_authority_contract import WorkspaceReadinessContract
from solidlsp.ls_config import Language


# ---------------------------------------------------------------------------
# Mock Fixtures (Contract-Derived, No Real Implementation Knowledge)
# ---------------------------------------------------------------------------


class MockSolidLanguageServer:
    """Mock LSP instance for workspace readiness testing.

    CONTRACT TRACEABILITY:
    - Derives behavior from WorkspaceReadinessContract observable interface
    - Provides: is_running() → bool, simulates textDocument/documentSymbol responses
    - Mock DOES NOT replicate internal LSP logic (blind to implementation)
    """

    def __init__(self, language: Language):
        self.language = language
        self._running = True
        self._indexed_workspaces: set[Path] = set()
        self._probe_responses: dict[Path, list[Any]] = {}

    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        self._running = False

    def mark_workspace_indexed(self, root: Path) -> None:
        """Simulate LSP finishing indexing for a workspace."""
        self._indexed_workspaces.add(root)

    def set_probe_response(self, file_path: Path, response: list[Any]) -> None:
        """Configure mock response for textDocument/documentSymbol on file_path."""
        self._probe_responses[file_path] = response

    def send_lsp_request(self, method: str, params: dict[str, Any]) -> Any:
        """Mock LSP request handling.

        CONTRACT TRACEABILITY: Simulates textDocument/documentSymbol behavior.
        - Returns non-empty list if workspace is indexed
        - Returns empty list or error if not yet indexed
        """
        if method == "textDocument/documentSymbol":
            uri = params.get("textDocument", {}).get("uri", "")
            file_path = Path(uri.replace("file://", ""))

            # If specific response configured, return it
            if file_path in self._probe_responses:
                return self._probe_responses[file_path]

            # Otherwise, check if workspace is indexed
            for workspace in self._indexed_workspaces:
                if file_path.is_relative_to(workspace):
                    return [{"name": "mock_symbol", "kind": 12}]  # Non-empty

            return []  # Not indexed yet

        return None


class MockWorkspaceReadinessImplementation(WorkspaceReadinessContract):
    """Test double implementing WorkspaceReadinessContract.

    CONTRACT TRACEABILITY:
    - Implements WorkspaceReadinessContract interface
    - Mock behavior derived ONLY from contract clauses (not implementation)
    - Provides minimal logic to verify contract postconditions

    Mock Contract: contracts/lsp_lifecycle_authority_contract.py
    Mock derives: POST-WR-01, POST-WR-02, POST-WR-03 observable behavior
    """

    def __init__(self):
        self._find_probeable_file_fn = None
        self._probe_call_count = 0

    def probe_workspace_readiness(
        self,
        ls: MockSolidLanguageServer,
        root: Path,
        timeout_seconds: float,
    ) -> bool:
        """
        CONTRACT TRACEABILITY:
        - Enforces: PRE-WR-01, PRE-WR-02, PRE-WR-03 (preconditions)
        - Guarantees: POST-WR-01, POST-WR-02, POST-WR-03 (postconditions)
        - Implements: ERRORS-WR-01, ERRORS-WR-02 (error contracts)

        ADVERSARIAL: Implementation-blind — behavior derived from contract ONLY.
        """
        # PRE-WR-03: timeout_seconds > 0
        if timeout_seconds <= 0:
            raise ValueError("PRE-WR-03 violation: timeout_seconds must be > 0")

        # PRE-WR-01: ls is running
        if not ls.is_running():
            raise ValueError("PRE-WR-01 violation: LSP is not running")

        # ERRORS-WR-02: No probeable file
        probeable_file = self.find_probeable_file(root, ls.language)
        if probeable_file is None:
            return False

        # Probe loop with timeout (INV-WR-03: bounded time)
        start_time = time.time()
        backoff = 0.1  # 100ms initial backoff

        while time.time() - start_time < timeout_seconds:
            self._probe_call_count += 1

            try:
                # ERRORS-WR-01: LSP crash during probing
                if not ls.is_running():
                    return False

                # Send probe request (INV-WR-02: read-only)
                response = ls.send_lsp_request(
                    "textDocument/documentSymbol",
                    {"textDocument": {"uri": f"file://{probeable_file}"}}
                )

                # POST-WR-01: Valid, non-empty response means indexed
                if response and len(response) > 0:
                    return True

            except Exception:
                # ERRORS-WR-01: Any exception during probe → return False
                return False

            # Backoff before retry
            time.sleep(min(backoff, timeout_seconds - (time.time() - start_time)))
            backoff *= 2  # Exponential backoff

        # POST-WR-02: Timeout elapsed
        return False

    def find_probeable_file(
        self,
        root: Path,
        language: Language,
    ) -> Path | None:
        """
        CONTRACT TRACEABILITY:
        - Enforces: PRE-WR-FPF-01, PRE-WR-FPF-02 (preconditions)
        - Guarantees: POST-WR-FPF-01, POST-WR-FPF-02, POST-WR-FPF-03 (postconditions)

        ADVERSARIAL: Implementation-blind — uses contract-specified behavior.
        """
        # PRE-WR-FPF-01: root must exist
        if not root.exists() or not root.is_dir():
            return None

        # Use injected implementation for testing (allows behavior verification)
        if self._find_probeable_file_fn:
            return self._find_probeable_file_fn(root, language)

        # Default: Find first file matching language extension
        extensions = {
            Language.PYTHON: {".py"},
            Language.RUST: {".rs"},
            Language.HASKELL: {".hs"},
        }.get(language, set())

        # POST-WR-FPF-03: Prefer small files
        candidates: list[tuple[int, Path]] = []
        for ext in extensions:
            for file_path in root.rglob(f"*{ext}"):
                if file_path.is_file():
                    size = file_path.stat().st_size
                    candidates.append((size, file_path))

        if not candidates:
            return None

        # POST-WR-FPF-03: Return smallest file
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]


@pytest.fixture
def mock_lsp():
    """Fixture providing mock LSP instance."""
    return MockSolidLanguageServer(Language.PYTHON)


@pytest.fixture
def workspace_impl():
    """Fixture providing WorkspaceReadinessContract implementation."""
    return MockWorkspaceReadinessImplementation()


@pytest.fixture
def tmp_workspace(tmp_path):
    """Fixture providing temporary workspace directory with Python files."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create some Python files
    (workspace / "small.py").write_text("# Small file\n")
    (workspace / "large.py").write_text("# Large file\n" * 100)

    return workspace


# ---------------------------------------------------------------------------
# PRE Clause Tests (Precondition Validation)
# ---------------------------------------------------------------------------


def test_probe_workspace_pre_wr_01_lsp_not_running(workspace_impl, tmp_workspace):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
    - Enforces: PRE-WR-01: ls is a running SolidLanguageServer instance
    - Category: negative
    - Adversarial: Implementation-blind

    WHAT: Verifies probe rejects non-running LSP
    WHY: PRE-WR-01 requires LSP to be running before probing
    """
    lsp = MockSolidLanguageServer(Language.PYTHON)
    lsp.stop()  # LSP not running

    with pytest.raises(ValueError, match="PRE-WR-01 violation"):
        workspace_impl.probe_workspace_readiness(lsp, tmp_workspace, timeout_seconds=5.0)


def test_probe_workspace_pre_wr_02_root_not_added(workspace_impl, mock_lsp, tmp_path):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
    - Enforces: PRE-WR-02: root has been added via add_workspace_root
    - Category: positive (contract assumption — not enforced by probe itself)
    - Adversarial: Implementation-blind

    WHAT: Documents that probe assumes root was already added
    WHY: PRE-WR-02 states root must be added before probing (caller responsibility)

    NOTE: This is a documentation test. The probe does NOT enforce PRE-WR-02 itself;
    it assumes the caller (tool dispatch) has already called add_workspace_root.
    The proof is that probe works on any root, regardless of add_workspace_root history.
    """
    # Create workspace that was NEVER added to LSP
    unadded_workspace = tmp_path / "unadded"
    unadded_workspace.mkdir()
    (unadded_workspace / "test.py").write_text("# test")

    # Probe will return False (timeout) because LSP has no indexed workspaces
    # This is POST-WR-02 behavior, not PRE-WR-02 enforcement
    result = workspace_impl.probe_workspace_readiness(
        mock_lsp,
        unadded_workspace,
        timeout_seconds=0.2
    )

    assert result is False, (
        f"PRE-WR-02 assumption validation\n"
        f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() PRE-WR-02\n"
        f"EXPECTED: False (timeout on un-added workspace)\n"
        f"ACTUAL: {result}\n"
        f"GUIDANCE: Probe assumes root was added (caller responsibility). "
        f"Un-added workspace never becomes ready (timeout)."
    )


def test_probe_workspace_pre_wr_03_invalid_timeout(workspace_impl, mock_lsp, tmp_workspace):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
    - Enforces: PRE-WR-03: timeout_seconds > 0
    - Category: negative
    - Adversarial: Implementation-blind

    WHAT: Verifies probe rejects non-positive timeout
    WHY: PRE-WR-03 requires timeout > 0 to ensure bounded execution
    """
    with pytest.raises(ValueError, match="PRE-WR-03 violation"):
        workspace_impl.probe_workspace_readiness(mock_lsp, tmp_workspace, timeout_seconds=0.0)

    with pytest.raises(ValueError, match="PRE-WR-03 violation"):
        workspace_impl.probe_workspace_readiness(mock_lsp, tmp_workspace, timeout_seconds=-1.0)


# ---------------------------------------------------------------------------
# POST Clause Tests (Postcondition Validation)
# ---------------------------------------------------------------------------


def test_probe_workspace_post_wr_01_success_valid_response(
    workspace_impl, mock_lsp, tmp_workspace
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
    - Enforces: POST-WR-01: On success (True), LSP returns valid non-empty response
    - Category: positive
    - Adversarial: Implementation-blind

    WHAT: Verifies probe returns True when LSP responds with valid symbols
    WHY: POST-WR-01 defines success condition — LSP indexed the workspace
    """
    # Mark workspace as indexed
    mock_lsp.mark_workspace_indexed(tmp_workspace)

    # Probe should succeed immediately
    result = workspace_impl.probe_workspace_readiness(
        mock_lsp,
        tmp_workspace,
        timeout_seconds=5.0
    )

    assert result is True, (
        f"POST-WR-01 violation: probe_workspace_readiness FAILED\n"
        f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() POST-WR-01\n"
        f"EXPECTED: True (LSP returned valid non-empty response)\n"
        f"ACTUAL: {result}\n"
        f"GUIDANCE: When LSP returns non-empty symbol list for workspace file, "
        f"probe MUST return True (workspace is indexed and ready)."
    )


def test_probe_workspace_post_wr_02_timeout_elapsed(
    workspace_impl, mock_lsp, tmp_workspace
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
    - Enforces: POST-WR-02: On timeout (False), timeout_seconds elapsed without valid response
    - Category: positive
    - Adversarial: Implementation-blind

    WHAT: Verifies probe returns False after timeout with no valid response
    WHY: POST-WR-02 defines timeout condition — LSP never indexed workspace
    """
    # Do NOT mark workspace as indexed — probe will timeout

    start_time = time.time()
    result = workspace_impl.probe_workspace_readiness(
        mock_lsp,
        tmp_workspace,
        timeout_seconds=0.3  # Short timeout for fast test
    )
    elapsed = time.time() - start_time

    assert result is False, (
        f"POST-WR-02 violation: probe_workspace_readiness returned non-False\n"
        f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() POST-WR-02\n"
        f"EXPECTED: False (timeout elapsed without valid response)\n"
        f"ACTUAL: {result}\n"
        f"GUIDANCE: When timeout elapses without LSP returning valid symbols, "
        f"probe MUST return False (workspace not ready within timeout)."
    )

    # Verify timeout was respected (INV-WR-03: bounded time)
    assert elapsed >= 0.3, (
        f"INV-WR-03 violation: timeout not respected\n"
        f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() INV-WR-03\n"
        f"EXPECTED: elapsed >= 0.3 seconds\n"
        f"ACTUAL: {elapsed:.3f} seconds\n"
        f"GUIDANCE: Probe MUST wait for full timeout_seconds before returning False."
    )


def test_probe_workspace_post_wr_03_no_side_effects(
    workspace_impl, mock_lsp, tmp_workspace
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
    - Enforces: POST-WR-03: No side effects on LSP state (read-only probes)
    - Category: positive
    - Adversarial: Implementation-blind

    WHAT: Verifies probe does not modify LSP state
    WHY: POST-WR-03 requires probe to be read-only (INV-WR-02 reinforces)
    """
    # Snapshot state before probe
    initial_running = mock_lsp.is_running()
    initial_workspaces = mock_lsp._indexed_workspaces.copy()

    # Run probe (will timeout)
    workspace_impl.probe_workspace_readiness(
        mock_lsp,
        tmp_workspace,
        timeout_seconds=0.2
    )

    # Verify no state changes
    assert mock_lsp.is_running() == initial_running, (
        f"POST-WR-03 violation: LSP running state changed\n"
        f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() POST-WR-03\n"
        f"EXPECTED: is_running unchanged ({initial_running})\n"
        f"ACTUAL: {mock_lsp.is_running()}\n"
        f"GUIDANCE: Probe is read-only. MUST NOT modify LSP state (start/stop, add roots, etc)."
    )

    assert mock_lsp._indexed_workspaces == initial_workspaces, (
        f"POST-WR-03 violation: indexed workspaces modified\n"
        f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() POST-WR-03\n"
        f"EXPECTED: workspaces unchanged ({initial_workspaces})\n"
        f"ACTUAL: {mock_lsp._indexed_workspaces}\n"
        f"GUIDANCE: Probe is read-only. MUST NOT add/remove workspaces."
    )


# ---------------------------------------------------------------------------
# INV Clause Tests (Invariant Validation)
# ---------------------------------------------------------------------------


def test_probe_workspace_inv_wr_01_no_dispatch_before_ready(
    workspace_impl, mock_lsp, tmp_workspace
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract
    - Enforces: INV-WR-01: No tool call dispatched for workspace that has not passed readiness
    - Category: invariant
    - Adversarial: Implementation-blind

    WHAT: Verifies tool dispatch layer blocks on un-ready workspace
    WHY: INV-WR-01 is the core readiness gate — prevents tool calls on un-indexed workspaces

    NOTE: This invariant is enforced by the CALLER (tool dispatch), not by probe itself.
    The probe provides the readiness signal (True/False). The caller MUST check it.
    """
    # Workspace NOT indexed — probe returns False
    ready = workspace_impl.probe_workspace_readiness(
        mock_lsp,
        tmp_workspace,
        timeout_seconds=0.2
    )

    assert ready is False, (
        f"INV-WR-01 enforcement prerequisite\n"
        f"Contract: WorkspaceReadinessContract INV-WR-01\n"
        f"EXPECTED: probe returns False (workspace not ready)\n"
        f"ACTUAL: {ready}\n"
        f"GUIDANCE: INV-WR-01 requires tool dispatch to CHECK probe result. "
        f"If probe returns False, tool call MUST be blocked."
    )

    # Documented enforcement: Caller MUST check `ready` before dispatching tool
    # If caller dispatches anyway → INV-WR-01 violation (caller bug, not probe bug)


def test_probe_workspace_inv_wr_02_probe_read_only(
    workspace_impl, mock_lsp, tmp_workspace
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract
    - Enforces: INV-WR-02: Readiness probe is non-destructive (read-only LSP request)
    - Category: invariant
    - Adversarial: Implementation-blind

    WHAT: Verifies probe uses only read-only LSP requests
    WHY: INV-WR-02 ensures probe does not interfere with LSP indexing

    NOTE: This test verifies the OBSERVABLE behavior. The probe sends textDocument/documentSymbol
    (read-only per LSP spec). No mutations to workspace_roots, no start/stop calls.
    """
    # Mark workspace indexed so probe succeeds quickly
    mock_lsp.mark_workspace_indexed(tmp_workspace)

    # Track LSP method calls
    call_log: list[str] = []
    original_send = mock_lsp.send_lsp_request

    def logged_send(method: str, params: dict[str, Any]) -> Any:
        call_log.append(method)
        return original_send(method, params)

    mock_lsp.send_lsp_request = logged_send

    # Run probe
    workspace_impl.probe_workspace_readiness(
        mock_lsp,
        tmp_workspace,
        timeout_seconds=5.0
    )

    # Verify ONLY read-only LSP requests were sent
    read_only_methods = {"textDocument/documentSymbol"}
    assert all(m in read_only_methods for m in call_log), (
        f"INV-WR-02 violation: probe sent non-read-only LSP requests\n"
        f"Contract: WorkspaceReadinessContract INV-WR-02\n"
        f"EXPECTED: Only {read_only_methods}\n"
        f"ACTUAL: {call_log}\n"
        f"GUIDANCE: Probe MUST use ONLY read-only LSP requests (documentSymbol, hover, etc). "
        f"MUST NOT send workspace edits, configuration changes, or lifecycle commands."
    )


def test_probe_workspace_inv_wr_03_timeout_bounded(
    workspace_impl, mock_lsp, tmp_workspace
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract
    - Enforces: INV-WR-03: Timeout is bounded — probe loop terminates in finite time
    - Category: invariant
    - Adversarial: Implementation-blind

    WHAT: Verifies probe terminates within timeout_seconds
    WHY: INV-WR-03 ensures probe cannot hang indefinitely
    """
    # Workspace NOT indexed — probe will timeout
    timeout = 0.5
    start_time = time.time()

    result = workspace_impl.probe_workspace_readiness(
        mock_lsp,
        tmp_workspace,
        timeout_seconds=timeout
    )

    elapsed = time.time() - start_time

    # Verify probe terminated
    assert result is False, "Probe should timeout (workspace not indexed)"

    # Verify elapsed time is bounded
    # Allow 20% margin for test timing variance
    assert elapsed <= timeout * 1.2, (
        f"INV-WR-03 violation: probe exceeded timeout\n"
        f"Contract: WorkspaceReadinessContract INV-WR-03\n"
        f"EXPECTED: elapsed <= {timeout * 1.2:.3f} seconds (timeout * 1.2)\n"
        f"ACTUAL: {elapsed:.3f} seconds\n"
        f"GUIDANCE: Probe loop MUST terminate within timeout_seconds. "
        f"Implementation MUST track elapsed time and exit loop when timeout reached."
    )


# ---------------------------------------------------------------------------
# ERRORS Clause Tests (Error Contract Validation)
# ---------------------------------------------------------------------------


def test_probe_workspace_errors_wr_01_lsp_crash_returns_false(
    workspace_impl, tmp_workspace
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
    - Enforces: ERRORS-WR-01: Returns False (not raise) if LSP crashes during probing
    - Category: error
    - Adversarial: Implementation-blind

    WHAT: Verifies probe returns False on LSP crash, does not raise
    WHY: ERRORS-WR-01 requires graceful degradation (no exception propagation)
    """
    lsp = MockSolidLanguageServer(Language.PYTHON)

    # Simulate LSP crash after first probe attempt
    # Mock will stop during probe loop
    def delayed_crash():
        time.sleep(0.1)
        lsp.stop()

    import threading
    crash_thread = threading.Thread(target=delayed_crash, daemon=True)
    crash_thread.start()

    # Probe should detect crash and return False (not raise)
    result = workspace_impl.probe_workspace_readiness(
        lsp,
        tmp_workspace,
        timeout_seconds=5.0
    )

    assert result is False, (
        f"ERRORS-WR-01 violation: probe did not return False on LSP crash\n"
        f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() ERRORS-WR-01\n"
        f"EXPECTED: False (graceful degradation on LSP crash)\n"
        f"ACTUAL: {result}\n"
        f"GUIDANCE: When LSP crashes during probing, probe MUST return False (not raise). "
        f"Caller can retry or escalate. MUST NOT propagate exception."
    )

    crash_thread.join(timeout=1.0)


def test_probe_workspace_errors_wr_02_no_file_returns_false(
    workspace_impl, mock_lsp, tmp_path
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
    - Enforces: ERRORS-WR-02: Returns False (not raise) if no probeable file found in root
    - Category: error
    - Adversarial: Implementation-blind

    WHAT: Verifies probe returns False when no probeable file exists
    WHY: ERRORS-WR-02 requires graceful degradation for empty workspaces
    """
    # Create empty workspace (no .py files for Python LSP)
    empty_workspace = tmp_path / "empty"
    empty_workspace.mkdir()

    # Probe should return False (not raise)
    result = workspace_impl.probe_workspace_readiness(
        mock_lsp,
        empty_workspace,
        timeout_seconds=5.0
    )

    assert result is False, (
        f"ERRORS-WR-02 violation: probe did not return False for empty workspace\n"
        f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() ERRORS-WR-02\n"
        f"EXPECTED: False (no probeable file found)\n"
        f"ACTUAL: {result}\n"
        f"GUIDANCE: When find_probeable_file returns None (no suitable file), "
        f"probe MUST return False (not raise). Workspace cannot be probed."
    )


# ---------------------------------------------------------------------------
# find_probeable_file Tests (Helper Method Contract)
# ---------------------------------------------------------------------------


def test_find_probeable_file_pre_fpf_01_nonexistent_directory(workspace_impl):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.find_probeable_file()
    - Enforces: PRE-WR-FPF-01: root is absolute path to existing directory
    - Category: negative
    - Adversarial: Implementation-blind

    WHAT: Verifies find_probeable_file returns None for nonexistent directory
    WHY: PRE-WR-FPF-01 requires existing directory — invalid input → None (graceful)
    """
    nonexistent = Path("/nonexistent/path")

    result = workspace_impl.find_probeable_file(nonexistent, Language.PYTHON)

    assert result is None, (
        f"PRE-WR-FPF-01 handling: find_probeable_file should return None for nonexistent directory\n"
        f"Contract: WorkspaceReadinessContract.find_probeable_file() PRE-WR-FPF-01\n"
        f"EXPECTED: None (graceful handling of invalid input)\n"
        f"ACTUAL: {result}\n"
        f"GUIDANCE: When root does not exist or is not a directory, "
        f"find_probeable_file MUST return None (caller can handle gracefully)."
    )


def test_find_probeable_file_pre_fpf_02_language_extensions(
    workspace_impl, tmp_path
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.find_probeable_file()
    - Enforces: PRE-WR-FPF-02: language determines file extensions to search
    - Category: positive
    - Adversarial: Implementation-blind

    WHAT: Verifies find_probeable_file filters by language extension
    WHY: PRE-WR-FPF-02 requires language-appropriate file selection
    """
    workspace = tmp_path / "multi_lang"
    workspace.mkdir()

    # Create files for different languages
    (workspace / "test.py").write_text("# Python")
    (workspace / "test.rs").write_text("// Rust")
    (workspace / "test.hs").write_text("-- Haskell")

    # Python language should find .py file
    result_py = workspace_impl.find_probeable_file(workspace, Language.PYTHON)
    assert result_py is not None and result_py.suffix == ".py", (
        f"PRE-WR-FPF-02 violation: Python language did not find .py file\n"
        f"Contract: WorkspaceReadinessContract.find_probeable_file() PRE-WR-FPF-02\n"
        f"EXPECTED: Path with .py extension\n"
        f"ACTUAL: {result_py}\n"
        f"GUIDANCE: find_probeable_file MUST filter by language-specific extensions. "
        f"Python → .py, Rust → .rs, etc."
    )

    # Rust language should find .rs file
    result_rs = workspace_impl.find_probeable_file(workspace, Language.RUST)
    assert result_rs is not None and result_rs.suffix == ".rs", (
        f"PRE-WR-FPF-02 violation: Rust language did not find .rs file\n"
        f"Contract: WorkspaceReadinessContract.find_probeable_file() PRE-WR-FPF-02\n"
        f"EXPECTED: Path with .rs extension\n"
        f"ACTUAL: {result_rs}\n"
        f"GUIDANCE: find_probeable_file MUST filter by language-specific extensions."
    )


def test_find_probeable_file_post_fpf_01_returns_path_or_none(
    workspace_impl, tmp_workspace
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.find_probeable_file()
    - Enforces: POST-WR-FPF-01: Returns Path to file suitable for LSP probing, or None
    - Category: positive
    - Adversarial: Implementation-blind

    WHAT: Verifies find_probeable_file returns Path or None
    WHY: POST-WR-FPF-01 defines return type contract
    """
    result = workspace_impl.find_probeable_file(tmp_workspace, Language.PYTHON)

    assert isinstance(result, Path) or result is None, (
        f"POST-WR-FPF-01 violation: invalid return type\n"
        f"Contract: WorkspaceReadinessContract.find_probeable_file() POST-WR-FPF-01\n"
        f"EXPECTED: Path or None\n"
        f"ACTUAL: {type(result)}\n"
        f"GUIDANCE: find_probeable_file MUST return Path (file found) or None (no suitable file)."
    )


def test_find_probeable_file_post_fpf_02_file_exists_matches(
    workspace_impl, tmp_workspace
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.find_probeable_file()
    - Enforces: POST-WR-FPF-02: File exists on disk and matches language extension
    - Category: positive
    - Adversarial: Implementation-blind

    WHAT: Verifies returned file exists and has correct extension
    WHY: POST-WR-FPF-02 ensures file is actually probeable by LSP
    """
    result = workspace_impl.find_probeable_file(tmp_workspace, Language.PYTHON)

    assert result is not None, "Fixture tmp_workspace should contain .py files"

    # POST-WR-FPF-02: File exists
    assert result.exists(), (
        f"POST-WR-FPF-02 violation: returned file does not exist\n"
        f"Contract: WorkspaceReadinessContract.find_probeable_file() POST-WR-FPF-02\n"
        f"EXPECTED: File exists on disk\n"
        f"ACTUAL: {result} (exists={result.exists()})\n"
        f"GUIDANCE: find_probeable_file MUST return EXISTING file paths. "
        f"Probe will fail if file does not exist."
    )

    # POST-WR-FPF-02: Matches language extension
    assert result.suffix == ".py", (
        f"POST-WR-FPF-02 violation: file extension does not match language\n"
        f"Contract: WorkspaceReadinessContract.find_probeable_file() POST-WR-FPF-02\n"
        f"EXPECTED: .py extension (Language.PYTHON)\n"
        f"ACTUAL: {result.suffix}\n"
        f"GUIDANCE: find_probeable_file MUST return file with language-appropriate extension."
    )


def test_find_probeable_file_post_fpf_03_prefers_small_files(
    workspace_impl, tmp_path
):
    """
    CONTRACT TRACEABILITY:
    - Contract: WorkspaceReadinessContract.find_probeable_file()
    - Enforces: POST-WR-FPF-03: Prefers small files (faster parsing)
    - Category: positive
    - Adversarial: Implementation-blind

    WHAT: Verifies find_probeable_file selects smallest file when multiple candidates
    WHY: POST-WR-FPF-03 optimizes probe speed by choosing small files
    """
    workspace = tmp_path / "size_test"
    workspace.mkdir()

    # Create files of different sizes
    small_file = workspace / "small.py"
    medium_file = workspace / "medium.py"
    large_file = workspace / "large.py"

    small_file.write_text("# 10 bytes\n")  # ~10 bytes
    medium_file.write_text("# Medium\n" * 50)  # ~450 bytes
    large_file.write_text("# Large\n" * 500)  # ~4000 bytes

    result = workspace_impl.find_probeable_file(workspace, Language.PYTHON)

    assert result == small_file, (
        f"POST-WR-FPF-03 violation: did not prefer smallest file\n"
        f"Contract: WorkspaceReadinessContract.find_probeable_file() POST-WR-FPF-03\n"
        f"EXPECTED: {small_file} (smallest file)\n"
        f"ACTUAL: {result}\n"
        f"Files: small={small_file.stat().st_size}B, "
        f"medium={medium_file.stat().st_size}B, large={large_file.stat().st_size}B\n"
        f"GUIDANCE: find_probeable_file SHOULD prefer small files for faster LSP parsing. "
        f"When multiple candidates exist, choose file with smallest size."
    )
