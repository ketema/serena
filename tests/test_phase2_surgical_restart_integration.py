"""
Integration tests for Phase 2 Surgical Restart (REQ-2026-005).

Tests the REAL GlobalLanguageServerPool methods with mocked LSP instances.

Contract Authority: contracts/lsp_lifecycle_authority_contract.py
Enforces: SurgicalRestartContract, WorkspaceReadinessContract

NOTE: These methods DON'T EXIST YET (RED phase). Tests will AttributeError until
implementation is complete. This is intentional - tests specify the behavior.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from contracts.global_lsp_pool_contract import PoolKey
from serena.global_lsp_pool import GlobalLanguageServerPool


class TestSurgicalRestartIntegration(unittest.TestCase):
    """
    Integration tests for surgical_restart_lsp() method.

    Contract: SurgicalRestartContract
    File: contracts/lsp_lifecycle_authority_contract.py (lines 35-114)
    """

    def setUp(self):
        """
        Setup real GlobalLanguageServerPool with mocked dependencies.

        NOTE: Direct manipulation of _pool and _session_refs is a test-only hack
        to simulate crashed LSP state without requiring full LSP lifecycle.
        """
        # Mock the adapter registry to control pool key generation
        self.mock_adapter_registry = MagicMock()
        self.mock_adapter_registry.get_pool_key = MagicMock()
        self.mock_adapter_registry.add_workspace_root = MagicMock()

        # Mock adapter returned by get_adapter() - implementation calls
        # adapter = self.capability_registry.get_adapter(language) then
        # adapter.add_workspace_root(new_lsp, root), so we must wire the
        # child mock that get_adapter() returns.
        self.mock_adapter = MagicMock()
        self.mock_adapter_registry.get_adapter.return_value = self.mock_adapter

        # Mock timeout manager
        self.mock_timeout_manager = MagicMock()

        # Create REAL pool with mocked dependencies
        self.pool = GlobalLanguageServerPool(
            adapter_registry=self.mock_adapter_registry,
            timeout_manager=self.mock_timeout_manager
        )

    @patch("serena.global_lsp_pool.Language", create=True)
    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_post_sr_01_returns_new_running_lsp(self, MockSolidLSP, MockLanguage):
        """
        CONTRACT TRACEABILITY:
        - Contract: SurgicalRestartContract.surgical_restart_lsp()
        - Enforces: POST-SR-01: Returns new running SolidLanguageServer instance
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Setup crashed LSP in pool
        language = MockLanguage.PYTHON
        crashed_lsp = MagicMock()
        crashed_lsp.workspace_roots = [Path("/workspace1"), Path("/workspace2")]

        # Configure adapter to return Language as pool key (multi-root LSP)
        self.mock_adapter_registry.get_pool_key.return_value = language

        # Add crashed LSP to pool's internal state (test-only hack)
        self.pool._pool[language] = crashed_lsp
        self.pool._session_refs[language] = {"session-1", "session-2"}

        # Mock _create_lsp to return new LSP
        new_lsp = MagicMock()
        new_lsp.workspace_roots = []  # Will be populated by add_workspace_root

        with patch.object(self.pool, "_create_lsp", return_value=new_lsp):
            # ACT: Call surgical_restart_lsp (method doesn't exist yet - will AttributeError)
            result = self.pool.surgical_restart_lsp(language)

            # ASSERT: POST-SR-01 - returns new SolidLanguageServer instance
            assert result is not crashed_lsp, (
                f"POST-SR-01 violation: Returned crashed LSP instead of new instance\n"
                f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-01\n"
                f"EXPECTED: New SolidLanguageServer instance (different from crashed_lsp)\n"
                f"ACTUAL: Same instance as crashed LSP (id={id(result)})\n"
                f"GUIDANCE: Method MUST return the newly created LSP instance, not the crashed one. "
                f"Call _create_lsp(language, workspace_root) to create new instance, then return it."
            )

            assert result is not None, (
                f"POST-SR-01 violation: Did not return LSP instance\n"
                f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-01\n"
                f"EXPECTED: New SolidLanguageServer instance\n"
                f"ACTUAL: None\n"
                f"GUIDANCE: Method MUST return the newly created LSP. "
                f"Ensure _create_lsp() return value is propagated to caller."
            )

    @patch("serena.global_lsp_pool.Language", create=True)
    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_post_sr_03_workspace_root_count_exact_match(self, MockSolidLSP, MockLanguage):
        """
        CONTRACT TRACEABILITY:
        - Contract: SurgicalRestartContract.surgical_restart_lsp()
        - Enforces: POST-SR-03: len(new_lsp.workspace_roots) == len(old_workspace_roots)
        - Category: positive (deterministic exact value)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Crashed LSP with 2 workspace roots
        language = MockLanguage.PYTHON
        old_roots = [Path("/workspace1"), Path("/workspace2")]
        crashed_lsp = MagicMock()
        crashed_lsp.workspace_roots = old_roots

        self.mock_adapter_registry.get_pool_key.return_value = language
        self.pool._pool[language] = crashed_lsp
        self.pool._session_refs[language] = {"session-1"}

        # New LSP with workspace_roots list that add_workspace_root will populate
        new_lsp = MagicMock()
        new_lsp.workspace_roots = []

        # Mock add_workspace_root to actually append to workspace_roots
        def mock_add_root(lsp, root):
            lsp.workspace_roots.append(root)
        self.mock_adapter.add_workspace_root.side_effect = mock_add_root

        with patch.object(self.pool, "_create_lsp", return_value=new_lsp):
            # ACT: Call surgical_restart_lsp
            result = self.pool.surgical_restart_lsp(language)

            # ASSERT: POST-SR-03 - EXACT count match (== 2, not > 0)
            assert len(result.workspace_roots) == 2, (
                f"POST-SR-03 violation: Workspace root count mismatch\n"
                f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-03\n"
                f"EXPECTED: len(new_lsp.workspace_roots) == {len(old_roots)} (EXACT match)\n"
                f"ACTUAL: len(new_lsp.workspace_roots) == {len(result.workspace_roots)}\n"
                f"GUIDANCE: Method MUST restore ALL workspace roots from crashed LSP. "
                f"Snapshot old_lsp.workspace_roots BEFORE stopping LSP, then loop over snapshot "
                f"calling adapter.add_workspace_root(new_lsp, root) for EACH root."
            )

    @patch("serena.global_lsp_pool.Language", create=True)
    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_seq_sr_01_calls_add_workspace_root_for_each(self, MockSolidLSP, MockLanguage):
        """
        CONTRACT TRACEABILITY:
        - Contract: SurgicalRestartContract.surgical_restart_lsp()
        - Enforces: SEQ-SR-01: MUST call adapter.add_workspace_root(new_lsp, root) for EACH root
        - Category: integration wiring (Tier 1.5)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Crashed LSP with 3 workspace roots
        language = MockLanguage.PYTHON
        old_roots = [Path("/ws1"), Path("/ws2"), Path("/ws3")]
        crashed_lsp = MagicMock()
        crashed_lsp.workspace_roots = old_roots

        self.mock_adapter_registry.get_pool_key.return_value = language
        self.pool._pool[language] = crashed_lsp
        self.pool._session_refs[language] = {"session-1"}

        new_lsp = MagicMock()
        new_lsp.workspace_roots = []

        with patch.object(self.pool, "_create_lsp", return_value=new_lsp):
            # ACT: Call surgical_restart_lsp
            result = self.pool.surgical_restart_lsp(language)

            # ASSERT: SEQ-SR-01 - add_workspace_root called EXACTLY 3 times
            assert self.mock_adapter.add_workspace_root.call_count == 3, (
                f"SEQ-SR-01 violation: add_workspace_root not called correct number of times\n"
                f"Contract: SurgicalRestartContract.surgical_restart_lsp() SEQ-SR-01\n"
                f"EXPECTED: adapter.add_workspace_root() called 3 times (once per root)\n"
                f"ACTUAL: called {self.mock_adapter.add_workspace_root.call_count} times\n"
                f"GUIDANCE: Surgical restart MUST loop over ALL old workspace roots. "
                f"Snapshot old_lsp.workspace_roots before stopping, then for each root "
                f"in snapshot call adapter.add_workspace_root(new_lsp, root)."
            )

            # Verify all roots were passed
            actual_roots = [call.args[1] for call in self.mock_adapter.add_workspace_root.call_args_list]
            assert set(actual_roots) == set(old_roots), (
                f"SEQ-SR-01 violation: Not all roots were restored\n"
                f"Contract: SurgicalRestartContract.surgical_restart_lsp() SEQ-SR-01\n"
                f"EXPECTED roots: {set(old_roots)}\n"
                f"ACTUAL roots passed to add_workspace_root: {set(actual_roots)}\n"
                f"GUIDANCE: Ensure snapshot includes ALL workspace roots. "
                f"Use old_roots_snapshot = list(old_lsp.workspace_roots) BEFORE stopping."
            )

    @patch("serena.global_lsp_pool.Language", create=True)
    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_post_sr_04_session_references_unchanged(self, MockSolidLSP, MockLanguage):
        """
        CONTRACT TRACEABILITY:
        - Contract: SurgicalRestartContract.surgical_restart_lsp()
        - Enforces: POST-SR-04: Session references unchanged after restart
        - Category: positive (state preservation)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Crashed LSP with session references
        language = MockLanguage.PYTHON
        crashed_lsp = MagicMock()
        crashed_lsp.workspace_roots = [Path("/workspace")]

        # Initial session refs
        original_session_refs = {"session-1", "session-2", "session-3"}

        self.mock_adapter_registry.get_pool_key.return_value = language
        self.pool._pool[language] = crashed_lsp
        self.pool._session_refs[language] = original_session_refs.copy()

        new_lsp = MagicMock()
        new_lsp.workspace_roots = []

        with patch.object(self.pool, "_create_lsp", return_value=new_lsp):
            # ACT: Call surgical_restart_lsp
            result = self.pool.surgical_restart_lsp(language)

            # ASSERT: POST-SR-04 - session references UNCHANGED
            assert self.pool._session_refs[language] == original_session_refs, (
                f"POST-SR-04 violation: Session references were modified\n"
                f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-04\n"
                f"EXPECTED: session_refs unchanged ({original_session_refs})\n"
                f"ACTUAL: session_refs = {self.pool._session_refs[language]}\n"
                f"GUIDANCE: Surgical restart MUST preserve session references. Do NOT call "
                f"_session_refs[language].clear() or reassign _session_refs[language]. "
                f"Only replace the LSP instance in _pool[language], leave _session_refs alone."
            )

    @patch("serena.global_lsp_pool.Language", create=True)
    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_inv_sr_01_restart_affects_only_target_language(self, MockSolidLSP, MockLanguage):
        """
        CONTRACT TRACEABILITY:
        - Contract: SurgicalRestartContract.surgical_restart_lsp()
        - Enforces: INV-SR-01: Restart affects ONLY target language's LSP instance
        - Category: invariant (isolation)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Two languages in pool - PYTHON (to restart) and TYPESCRIPT (other)
        python_lang = MockLanguage.PYTHON
        typescript_lang = MockLanguage.TYPESCRIPT

        crashed_python_lsp = MagicMock()
        crashed_python_lsp.workspace_roots = [Path("/python_ws")]

        unaffected_ts_lsp = MagicMock()
        unaffected_ts_lsp.workspace_roots = [Path("/ts_ws")]

        # Setup adapter to return different pool keys for different languages
        def get_pool_key_side_effect(lang, root=None):
            return lang  # Multi-root: just the language
        self.mock_adapter_registry.get_pool_key.side_effect = get_pool_key_side_effect

        # Add both to pool (test-only hack)
        self.pool._pool[python_lang] = crashed_python_lsp
        self.pool._pool[typescript_lang] = unaffected_ts_lsp
        self.pool._session_refs[python_lang] = {"py-session"}
        self.pool._session_refs[typescript_lang] = {"ts-session"}

        new_python_lsp = MagicMock()
        new_python_lsp.workspace_roots = []

        with patch.object(self.pool, "_create_lsp", return_value=new_python_lsp):
            # ACT: Restart PYTHON
            result = self.pool.surgical_restart_lsp(python_lang)

            # ASSERT: INV-SR-01 - TypeScript LSP UNCHANGED
            assert self.pool._pool[typescript_lang] is unaffected_ts_lsp, (
                f"INV-SR-01 violation: Other language's LSP was modified\n"
                f"Contract: SurgicalRestartContract.surgical_restart_lsp() INV-SR-01\n"
                f"EXPECTED: TypeScript LSP unchanged (id={id(unaffected_ts_lsp)})\n"
                f"ACTUAL: TypeScript LSP = {self.pool._pool[typescript_lang]} (id={id(self.pool._pool[typescript_lang])})\n"
                f"GUIDANCE: Surgical restart MUST affect ONLY the target language. "
                f"Use pool_key = adapter.get_pool_key(language, None) to identify target entry. "
                f"Do NOT iterate over all pool entries or call stop_all()."
            )

    @patch("serena.global_lsp_pool.Language", create=True)
    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_post_sr_05_other_lsp_workspace_roots_unchanged(self, MockSolidLSP, MockLanguage):
        """
        CONTRACT TRACEABILITY:
        - Contract: SurgicalRestartContract.surgical_restart_lsp()
        - Enforces: POST-SR-05: Other LSPs' workspace_roots unchanged
        - Category: positive (isolation)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Two languages with different workspace roots
        python_lang = MockLanguage.PYTHON
        rust_lang = MockLanguage.RUST

        crashed_python_lsp = MagicMock()
        crashed_python_lsp.workspace_roots = [Path("/python_ws")]

        rust_lsp = MagicMock()
        original_rust_roots = [Path("/rust_ws1"), Path("/rust_ws2")]
        rust_lsp.workspace_roots = original_rust_roots.copy()

        def get_pool_key_side_effect(lang, root=None):
            return lang
        self.mock_adapter_registry.get_pool_key.side_effect = get_pool_key_side_effect

        self.pool._pool[python_lang] = crashed_python_lsp
        self.pool._pool[rust_lang] = rust_lsp
        self.pool._session_refs[python_lang] = {"py-session"}
        self.pool._session_refs[rust_lang] = {"rust-session"}

        new_python_lsp = MagicMock()
        new_python_lsp.workspace_roots = []

        with patch.object(self.pool, "_create_lsp", return_value=new_python_lsp):
            # ACT: Restart Python
            result = self.pool.surgical_restart_lsp(python_lang)

            # ASSERT: POST-SR-05 - Rust workspace_roots UNCHANGED
            assert rust_lsp.workspace_roots == original_rust_roots, (
                f"POST-SR-05 violation: Other LSP's workspace_roots were modified\n"
                f"Contract: SurgicalRestartContract.surgical_restart_lsp() POST-SR-05\n"
                f"EXPECTED: Rust LSP workspace_roots unchanged ({original_rust_roots})\n"
                f"ACTUAL: Rust LSP workspace_roots = {rust_lsp.workspace_roots}\n"
                f"GUIDANCE: Surgical restart MUST NOT modify other languages' workspace roots. "
                f"Ensure add_workspace_root is called ONLY on the NEW Python LSP, not on other LSPs. "
                f"Isolate target using pool_key lookup."
            )

    @patch("serena.global_lsp_pool.Language", create=True)
    def test_post_sr_gwr_01_returns_list_of_paths(self, MockLanguage):
        """
        CONTRACT TRACEABILITY:
        - Contract: SurgicalRestartContract.get_workspace_roots_for_language()
        - Enforces: POST-SR-GWR-01: Returns list of Path (possibly empty)
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: LSP with workspace roots in pool
        language = MockLanguage.PYTHON
        lsp = MagicMock()
        roots = [Path("/ws1"), Path("/ws2")]
        lsp.workspace_roots = roots

        self.mock_adapter_registry.get_pool_key.return_value = language
        self.pool._pool[language] = lsp

        # ACT: Call get_workspace_roots_for_language
        result = self.pool.get_workspace_roots_for_language(language)

        # ASSERT: POST-SR-GWR-01 - returns list of Path
        assert isinstance(result, list), (
            f"POST-SR-GWR-01 violation: Did not return list\n"
            f"Contract: SurgicalRestartContract.get_workspace_roots_for_language() POST-SR-GWR-01\n"
            f"EXPECTED: list[Path]\n"
            f"ACTUAL: {type(result).__name__}\n"
            f"GUIDANCE: Method MUST return a list, even if empty. "
            f"Look up LSP via pool_key = adapter.get_pool_key(language, None), then "
            f"return list(lsp.workspace_roots) if LSP exists, or [] if not."
        )

        assert all(isinstance(path, Path) for path in result), (
            f"POST-SR-GWR-01 violation: List contains non-Path elements\n"
            f"Contract: SurgicalRestartContract.get_workspace_roots_for_language() POST-SR-GWR-01\n"
            f"EXPECTED: All elements are Path instances\n"
            f"ACTUAL: {[type(p).__name__ for p in result]}\n"
            f"GUIDANCE: Ensure workspace_roots contains only Path objects."
        )

    @patch("serena.global_lsp_pool.Language", create=True)
    def test_post_sr_gwr_02_does_not_modify_state(self, MockLanguage):
        """
        CONTRACT TRACEABILITY:
        - Contract: SurgicalRestartContract.get_workspace_roots_for_language()
        - Enforces: POST-SR-GWR-02: Does NOT modify state
        - Category: invariant (read-only)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: LSP in pool with session refs
        language = MockLanguage.PYTHON
        lsp = MagicMock()
        roots = [Path("/ws1")]
        lsp.workspace_roots = roots

        self.mock_adapter_registry.get_pool_key.return_value = language
        self.pool._pool[language] = lsp
        self.pool._session_refs[language] = {"session-1"}

        # Take snapshot of state BEFORE call
        pool_snapshot = dict(self.pool._pool)
        session_refs_snapshot = {k: v.copy() for k, v in self.pool._session_refs.items()}

        # ACT: Call get_workspace_roots_for_language
        result = self.pool.get_workspace_roots_for_language(language)

        # ASSERT: POST-SR-GWR-02 - state unchanged
        assert self.pool._pool == pool_snapshot, (
            f"POST-SR-GWR-02 violation: Pool state was modified\n"
            f"Contract: SurgicalRestartContract.get_workspace_roots_for_language() POST-SR-GWR-02\n"
            f"EXPECTED: _pool unchanged\n"
            f"ACTUAL: _pool was modified\n"
            f"GUIDANCE: This is a read-only query method. Do NOT modify _pool, _session_refs, "
            f"or LSP instances. Simply return list(lsp.workspace_roots) if LSP exists."
        )

        assert self.pool._session_refs == session_refs_snapshot, (
            f"POST-SR-GWR-02 violation: Session refs were modified\n"
            f"Contract: SurgicalRestartContract.get_workspace_roots_for_language() POST-SR-GWR-02\n"
            f"EXPECTED: _session_refs unchanged\n"
            f"ACTUAL: _session_refs was modified\n"
            f"GUIDANCE: This method MUST NOT modify any pool state. Read-only access."
        )


class TestWorkspaceReadinessIntegration(unittest.TestCase):
    """
    Integration tests for probe_workspace_readiness() standalone function.

    Contract: WorkspaceReadinessContract
    File: contracts/lsp_lifecycle_authority_contract.py (lines 140-221)

    NOTE: probe_workspace_readiness is a module-level function, not a method.
    Tests will fail with ImportError until function exists in module.
    """

    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_post_wr_01_returns_true_on_valid_response(self, MockSolidLSP):
        """
        CONTRACT TRACEABILITY:
        - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
        - Enforces: POST-WR-01: Returns True when LSP returns valid non-empty response
        - Category: positive
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock LSP that returns valid symbols
        lsp = MagicMock()

        # Mock textDocument/documentSymbol to return non-empty response
        def mock_request(method, params):
            if method == "textDocument/documentSymbol":
                return [{"name": "MyClass", "kind": 5}]  # Non-empty
            return None
        lsp.request = Mock(side_effect=mock_request)

        root = Path("/workspace")
        timeout = 5.0

        # ACT: Call probe_workspace_readiness (will fail until implemented)
        from serena.global_lsp_pool import probe_workspace_readiness
        result = probe_workspace_readiness(lsp, root, timeout)

        # ASSERT: POST-WR-01 - returns True
        assert result is True, (
            f"POST-WR-01 violation: Did not return True on valid response\n"
            f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() POST-WR-01\n"
            f"EXPECTED: True (LSP returned non-empty symbols)\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: When LSP returns non-empty response to textDocument/documentSymbol, "
            f"readiness check MUST return True. Find probeable file in workspace (e.g., first .py file), "
            f"construct file URI, send documentSymbol request. If response is non-empty list, return True."
        )

    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_post_wr_02_returns_false_on_timeout(self, MockSolidLSP):
        """
        CONTRACT TRACEABILITY:
        - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
        - Enforces: POST-WR-02: Returns False when timeout elapsed
        - Category: negative (timeout boundary)
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock LSP that never returns valid response
        lsp = MagicMock()

        def mock_request(method, params):
            return []  # Always empty (not ready)
        lsp.request = Mock(side_effect=mock_request)

        root = Path("/workspace")
        timeout = 0.1  # Very short timeout

        # ACT: Call probe_workspace_readiness
        from serena.global_lsp_pool import probe_workspace_readiness
        result = probe_workspace_readiness(lsp, root, timeout)

        # ASSERT: POST-WR-02 - returns False
        assert result is False, (
            f"POST-WR-02 violation: Did not return False on timeout\n"
            f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() POST-WR-02\n"
            f"EXPECTED: False (timeout elapsed without valid response)\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: When timeout_seconds elapses without non-empty response, return False. "
            f"Track elapsed time with start_time = time.time(), loop with backoff "
            f"(e.g., sleep(0.1), sleep(0.2), ...) until time.time() - start_time > timeout_seconds."
        )

    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_errors_wr_01_returns_false_on_lsp_crash(self, MockSolidLSP):
        """
        CONTRACT TRACEABILITY:
        - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
        - Enforces: ERRORS-WR-01: Returns False (does not raise) if LSP crashes during probing
        - Category: error handling
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock LSP that crashes on request
        lsp = MagicMock()

        def mock_request_crash(method, params):
            raise RuntimeError("LSP crashed during probe")
        lsp.request = Mock(side_effect=mock_request_crash)

        root = Path("/workspace")
        timeout = 5.0

        # ACT: Call probe_workspace_readiness (should NOT raise)
        from serena.global_lsp_pool import probe_workspace_readiness
        result = probe_workspace_readiness(lsp, root, timeout)

        # ASSERT: ERRORS-WR-01 - returns False, does not raise
        assert result is False, (
            f"ERRORS-WR-01 violation: Did not return False on LSP crash\n"
            f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() ERRORS-WR-01\n"
            f"EXPECTED: False (graceful degradation, no exception propagated)\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Wrap lsp.request() in try/except. On exception (RuntimeError, TimeoutError, etc.), "
            f"log at WARN level with logger.warning(), then return False. Do NOT re-raise exception."
        )

    @patch("serena.global_lsp_pool.SolidLanguageServer", create=True)
    def test_inv_wr_02_readiness_probe_is_non_destructive(self, MockSolidLSP):
        """
        CONTRACT TRACEABILITY:
        - Contract: WorkspaceReadinessContract.probe_workspace_readiness()
        - Enforces: INV-WR-02: Readiness probe is non-destructive (read-only LSP request)
        - Category: invariant
        - Adversarial: Implementation-blind
        """
        # ARRANGE: Mock LSP with request spy
        lsp = MagicMock()

        request_calls = []
        def mock_request(method, params):
            request_calls.append((method, params))
            return [{"name": "Symbol"}]  # Non-empty
        lsp.request = Mock(side_effect=mock_request)

        root = Path("/workspace")
        timeout = 5.0

        # ACT: Call probe_workspace_readiness
        from serena.global_lsp_pool import probe_workspace_readiness
        probe_workspace_readiness(lsp, root, timeout)

        # ASSERT: INV-WR-02 - only read-only requests made
        assert len(request_calls) > 0, "Expected at least one LSP request"

        for method, params in request_calls:
            # Verify ONLY read-only methods used (no didChange, didOpen, etc.)
            assert method in ["textDocument/documentSymbol", "textDocument/definition", "textDocument/hover"], (
                f"INV-WR-02 violation: Non-read-only LSP method called\n"
                f"Contract: WorkspaceReadinessContract.probe_workspace_readiness() INV-WR-02\n"
                f"EXPECTED: Only read-only LSP methods (documentSymbol, definition, hover)\n"
                f"ACTUAL: Method '{method}' called\n"
                f"GUIDANCE: Readiness probe MUST be non-destructive. Use ONLY read-only LSP requests "
                f"like textDocument/documentSymbol. Do NOT use didChange, didOpen, workspace/executeCommand, "
                f"or any method that modifies LSP state."
            )


if __name__ == "__main__":
    unittest.main()
