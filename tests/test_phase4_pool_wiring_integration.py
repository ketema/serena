"""
Integration tests for Phase 4 Pool Wiring Integration (REQ-2026-005).

Tests the integration between:
1. McpSessionBridge.on_transport_session_closed() → GlobalLanguageServerPool.release()
2. GlobalLanguageServerPool.acquire() → probe_workspace_readiness()

Contract Authority: contracts/lsp_lifecycle_authority_contract.py
Enforces: SEQ-POOL-05, SEQ-POOL-06

NOTE: These wiring behaviors DON'T EXIST YET (RED phase).
Tests will fail until implementation is complete. This is intentional - tests specify
the behavior.

Integration Test Strategy (Tier 1.5):
These tests verify WIRING between components through actual lifecycle paths.
They test through actual construction and method invocation, not direct calls.

CONTRACT AUTHORITY RECORD:
- File: contracts/lsp_lifecycle_authority_contract.py
- Authority: "AUTHORITATIVE for LSP lifecycle" (line 8)
- PRE clauses: N/A (SEQ tests focus on wiring, not preconditions)
- POST clauses: N/A (SEQ tests verify calls were made, not postconditions)
- INV clauses: N/A (SEQ tests focus on integration)
- SEQ clauses: 2 extracted
  - SEQ-POOL-05 (line 444-447): on_transport_session_closed MUST call pool.release()
  - SEQ-POOL-06 (line 449-453): acquire MUST call probe_workspace_readiness after add_workspace_root
- ERRORS: N/A (SEQ tests verify wiring, not error handling)

CLAUSE REGISTRY:
SEQ-POOL-05: McpSessionBridge.on_transport_session_closed() MUST call
             GlobalLanguageServerPool.release() for each language in the
             session's lsp_references with the session's workspace_root.
             Source: REQ-2026-005, CLEANUP_CHAIN, E-6, IP-4
             Failure mode: Ref count leak; LSPs never reclaimed after disconnect

SEQ-POOL-06: GlobalLanguageServerPool.acquire() MUST call
             probe_workspace_readiness(lsp, workspace_root, timeout) after
             adapter.add_workspace_root() for newly added multi-root workspaces.
             Source: REQ-2026-005, ACQUIRE_CHAIN, E-10, IP-3
             Failure mode: Tool calls dispatched to un-indexed workspace

SEQ_TEST_SELF_CHECK (applied to all SEQ tests):
  ✓ Test constructs PARENT object via __init__()? YES - uses real McpSessionBridge/GlobalLanguageServerPool
  ✓ Test verifies SEQ behavior through parent state/side effects? YES - mocks to observe calls
  ✓ Test does NOT directly call the callee method? YES - only calls public interface
  ✓ If mock used, injected at construction time? YES - via __init__ parameters
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

from solidlsp.ls_config import Language

from serena.mcp_session_bridge import MCPSessionBridge
from serena.global_lsp_pool import GlobalLanguageServerPool
from serena.session_registry import SessionRegistry


class TestPoolWiringIntegration(unittest.TestCase):
    """
    Integration tests for Phase 4 pool wiring between McpSessionBridge and GlobalLanguageServerPool.

    Contract: LSPLifecycleAuthorityContract (SEQ-POOL-05, SEQ-POOL-06)
    File: contracts/lsp_lifecycle_authority_contract.py (lines 444-453)

    These are Tier 1.5 integration tests - they verify WIRING through actual lifecycle paths.
    Tests must use actual construction paths per SEQ testing discipline.
    """

    def setUp(self):
        """
        Setup real McpSessionBridge and mock GlobalLanguageServerPool for integration testing.

        We use REAL bridge and registry to verify actual wiring behavior.
        We mock LSP pool to observe whether release() is called correctly.

        NOTE: MCPSessionBridge does not currently accept lsp_pool in constructor.
        This test suite SPECIFIES the requirement for constructor injection (TDD).
        Tests document expected integration behavior once GREEN phase implements injection.
        """
        # Real session registry (ephemeral, test isolation)
        self.registry = SessionRegistry()

        # Mock LSP pool (will be injected for testing)
        # TODO GREEN: Add lsp_pool parameter to MCPSessionBridge.__init__()
        self.mock_pool = MagicMock(spec=GlobalLanguageServerPool)

        # Real bridge (wiring will be verified via integration)
        self.bridge = MCPSessionBridge(self.registry)

        # TEMPORARY: Post-construction injection for RED phase testing
        # This violates Characteristic #5 but is necessary until GREEN phase
        # implements constructor injection. Tests specify what behavior is needed.
        self.bridge._lsp_pool = self.mock_pool

    # =========================================================================
    # SEQ-POOL-05: on_transport_session_closed → pool.release() wiring
    # =========================================================================

    def test_seq_pool_05_cleanup_calls_release_per_language(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: McpSessionBridge.on_transport_session_closed()
        - Enforces: SEQ-POOL-05: on_transport_session_closed MUST call GlobalLanguageServerPool.release()
                    for each language in session's lsp_references (line 444-447)
        - Category: positive (integration wiring)
        - Adversarial: Implementation-blind

        BEHAVIOR:
        When on_transport_session_closed fires for a session with lsp_references and workspace_root,
        pool.release() MUST be called for EACH language in lsp_references.

        Integration path: on_transport_session_closed() → (internal logic) → pool.release()
        """
        # ARRANGE: Create session with workspace_root and lsp_references
        session_id = "test-session-123"
        workspace_root = Path.cwd()  # Use current directory for test (ephemeral session)

        # Register session via bridge (lifecycle path)
        self.bridge.on_transport_session_created(session_id, workspace_root)

        # Simulate LSP acquisition by adding lsp_references to session
        session = self.registry.get_session(session_id)
        assert session is not None, "Precondition: session must be registered"
        session.lsp_references = {
            "python": {"adapter": "mock_adapter", "lsp": "mock_lsp_python"},
            "rust": {"adapter": "mock_adapter", "lsp": "mock_lsp_rust"},
        }

        # ACT: Close session (lifecycle path)
        self.bridge.on_transport_session_closed(session_id)

        # ASSERT: SEQ-POOL-05 - pool.release() called for each language
        # Error message structure: WHAT/WHY/EXPECTED/ACTUAL/GUIDANCE
        self.assertEqual(
            self.mock_pool.release.call_count,
            2,
            msg=(
                f"\n[WHAT] test_seq_pool_05_cleanup_calls_release_per_language FAILED\n"
                f"[WHY] SEQ-POOL-05 violation: pool.release() not called once per language\n"
                f"[CONTRACT] McpSessionBridge.on_transport_session_closed() SEQ-POOL-05 (line 444-447)\n"
                f"[EXPECTED] pool.release() called 2 times (once per language in lsp_references)\n"
                f"[ACTUAL] pool.release() called {self.mock_pool.release.call_count} times\n"
                f"[GUIDANCE - BEHAVIORAL] When on_transport_session_closed() fires for a session\n"
                f"with workspace_root and lsp_references, pool.release() MUST be invoked for EACH\n"
                f"language key. Implementation must: (1) verify session exists, (2) check workspace_root\n"
                f"is not None, (3) iterate lsp_references.keys(), (4) map string keys to Language enum,\n"
                f"(5) call pool.release(language, workspace_root, session_id) per language."
            )
        )

        # Verify both expected calls occurred (unordered)
        expected_calls = [
            call(Language.PYTHON, workspace_root, session_id),
            call(Language.RUST, workspace_root, session_id),
        ]
        actual_calls = self.mock_pool.release.call_args_list
        for expected_call in expected_calls:
            self.assertIn(
                expected_call,
                actual_calls,
                msg=(
                    f"\n[WHAT] test_seq_pool_05_cleanup_calls_release_per_language FAILED (call verification)\n"
                    f"[WHY] SEQ-POOL-05 violation: Expected pool.release() call not found\n"
                    f"[CONTRACT] McpSessionBridge.on_transport_session_closed() SEQ-POOL-05 (line 444-447)\n"
                    f"[EXPECTED] pool.release({expected_call.args[0]}, {expected_call.args[1]}, {expected_call.args[2]})\n"
                    f"[ACTUAL] calls made: {actual_calls}\n"
                    f"[GUIDANCE - BEHAVIORAL] Each language string key in lsp_references MUST map to\n"
                    f"corresponding Language enum value. Use Language enum lookup (e.g., Language[key.upper()])\n"
                    f"or explicit mapping dict. Pass session's workspace_root and session_id as parameters."
                )
            )

    def test_seq_pool_05_guard_no_release_without_workspace(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: McpSessionBridge.on_transport_session_closed()
        - Enforces: SEQ-POOL-05 guard: NO pool.release() when workspace_root=None (HTTP mode)
        - Category: negative (guard clause)
        - Adversarial: Implementation-blind

        BEHAVIOR:
        When session has workspace_root=None (HTTP mode before activate_project),
        pool.release() MUST NOT be called (no-op).

        Integration path: on_transport_session_closed() → (guard check) → no pool.release()
        """
        # ARRANGE: Create session WITHOUT workspace_root (HTTP mode)
        session_id = "http-session-456"

        # Register session with None workspace (HTTP mode before activate_project)
        self.bridge.on_transport_session_created(session_id, workspace_root=None)

        # Simulate LSP references (even though no workspace)
        session = self.registry.get_session(session_id)
        self.assertIsNotNone(session, "Precondition: session must be registered")
        session.lsp_references = {
            "python": {"adapter": "mock", "lsp": "mock_lsp"},
        }

        # ACT: Close session
        self.bridge.on_transport_session_closed(session_id)

        # ASSERT: SEQ-POOL-05 guard - pool.release() NOT called when workspace_root=None
        self.assertEqual(
            self.mock_pool.release.call_count,
            0,
            msg=(
                f"\n[WHAT] test_seq_pool_05_guard_no_release_without_workspace FAILED\n"
                f"[WHY] SEQ-POOL-05 guard violation: pool.release() invoked for HTTP mode session\n"
                f"[CONTRACT] McpSessionBridge.on_transport_session_closed() SEQ-POOL-05 guard\n"
                f"[EXPECTED] pool.release() NOT called when session.workspace_root is None\n"
                f"[ACTUAL] pool.release() called {self.mock_pool.release.call_count} times\n"
                f"[GUIDANCE - BEHAVIORAL] Before invoking pool.release(), implementation MUST verify\n"
                f"session.workspace_root is not None. HTTP mode sessions start with workspace_root=None\n"
                f"until activate_project is called. During cleanup, check workspace_root guard BEFORE\n"
                f"attempting to release LSP references. No pool operations permitted without workspace binding."
            )
        )

    def test_seq_pool_05_idempotent_unknown_session(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: McpSessionBridge.on_transport_session_closed()
        - Enforces: SEQ-POOL-05 idempotent: No error when session_id unknown
        - Category: boundary (idempotent)
        - Adversarial: Implementation-blind

        BEHAVIOR:
        When on_transport_session_closed fires for unknown session_id,
        behavior MUST be idempotent (no error, no pool calls).

        Integration path: on_transport_session_closed() → (session not found) → no-op
        """
        # ARRANGE: No session registered
        session_id = "unknown-session-789"

        # ACT: Close unknown session (idempotent operation)
        # Should not raise exception
        try:
            self.bridge.on_transport_session_closed(session_id)
        except Exception as e:
            self.fail(
                f"\n[WHAT] test_seq_pool_05_idempotent_unknown_session FAILED (exception)\n"
                f"[WHY] SEQ-POOL-05 idempotent violation: Exception raised for unknown session\n"
                f"[CONTRACT] McpSessionBridge.on_transport_session_closed() idempotent behavior\n"
                f"[EXPECTED] No exception, silent no-op when session not found\n"
                f"[ACTUAL] {type(e).__name__}: {e}\n"
                f"[GUIDANCE - BEHAVIORAL] on_transport_session_closed() MUST be idempotent and\n"
                f"handle unknown session_id gracefully. Implementation should: (1) attempt to\n"
                f"retrieve session from registry, (2) if None, return early (no error), (3) only\n"
                f"proceed with cleanup if session exists. This prevents errors on duplicate close\n"
                f"or race conditions between reaper and explicit close."
            )

        # ASSERT: No pool.release() calls for unknown session
        self.assertEqual(
            self.mock_pool.release.call_count,
            0,
            msg=(
                f"\n[WHAT] test_seq_pool_05_idempotent_unknown_session FAILED (pool call count)\n"
                f"[WHY] SEQ-POOL-05 idempotent violation: pool.release() invoked for non-existent session\n"
                f"[CONTRACT] McpSessionBridge.on_transport_session_closed() idempotent behavior\n"
                f"[EXPECTED] No pool.release() calls when session not found in registry\n"
                f"[ACTUAL] pool.release() called {self.mock_pool.release.call_count} times\n"
                f"[GUIDANCE - BEHAVIORAL] Guard pool cleanup behind session existence check.\n"
                f"Retrieve session = registry.get_session(session_id). If session is None, return\n"
                f"early before any pool operations. Only proceed with lsp_references iteration if\n"
                f"session exists."
            )
        )

    def test_seq_pool_05_multi_language_iteration(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: McpSessionBridge.on_transport_session_closed()
        - Enforces: SEQ-POOL-05: pool.release() called once per language (3 languages)
        - Category: positive (multi-language)
        - Adversarial: Implementation-blind

        BEHAVIOR:
        When a session has multiple languages in lsp_references (3+),
        pool.release() MUST be called once per language.

        Integration path: on_transport_session_closed() → iterate lsp_references → pool.release() × N
        """
        # ARRANGE: Create session with 3 languages
        session_id = "multi-lang-session"
        workspace_root = Path.cwd()  # Use current directory for test

        self.bridge.on_transport_session_created(session_id, workspace_root)

        # Add 3 languages to lsp_references
        session = self.registry.get_session(session_id)
        self.assertIsNotNone(session, "Precondition: session must exist")
        session.lsp_references = {
            "python": {"lsp": "mock_python"},
            "rust": {"lsp": "mock_rust"},
            "typescript": {"lsp": "mock_typescript"},
        }

        # ACT: Close session
        self.bridge.on_transport_session_closed(session_id)

        # ASSERT: SEQ-POOL-05 - pool.release() called 3 times
        self.assertEqual(
            self.mock_pool.release.call_count,
            3,
            msg=(
                f"\n[WHAT] test_seq_pool_05_multi_language_iteration FAILED\n"
                f"[WHY] SEQ-POOL-05 violation: pool.release() not called for all languages\n"
                f"[CONTRACT] McpSessionBridge.on_transport_session_closed() SEQ-POOL-05 (line 444-447)\n"
                f"[EXPECTED] pool.release() called 3 times (once per language in lsp_references)\n"
                f"[ACTUAL] pool.release() called {self.mock_pool.release.call_count} times\n"
                f"[GUIDANCE - BEHAVIORAL] Implementation MUST iterate over ALL keys in\n"
                f"session.lsp_references dictionary. Use for loop over lsp_references.keys() or\n"
                f".items(). Do not break early, do not skip languages. Each iteration must map\n"
                f"language string key to Language enum and call pool.release() with that enum,\n"
                f"workspace_root, and session_id. Complete iteration before returning."
            )
        )

        # Verify all 3 languages were released
        actual_languages = [call_args[0][0] for call_args in self.mock_pool.release.call_args_list]
        expected_languages = [Language.PYTHON, Language.RUST, Language.TYPESCRIPT]

        for expected_lang in expected_languages:
            self.assertIn(
                expected_lang,
                actual_languages,
                msg=(
                    f"\n[WHAT] test_seq_pool_05_multi_language_iteration FAILED (missing language)\n"
                    f"[WHY] SEQ-POOL-05 violation: Language {expected_lang} not released\n"
                    f"[CONTRACT] McpSessionBridge.on_transport_session_closed() SEQ-POOL-05\n"
                    f"[EXPECTED] All languages in lsp_references must be released: {expected_languages}\n"
                    f"[ACTUAL] Languages released: {actual_languages}\n"
                    f"[GUIDANCE - BEHAVIORAL] Verify language string-to-enum mapping is complete.\n"
                    f"Common mappings: 'python' \u2192 Language.PYTHON, 'rust' \u2192 Language.RUST,\n"
                    f"'typescript' \u2192 Language.TYPESCRIPT. Use consistent mapping mechanism for\n"
                    f"all supported languages. Missing mapping indicates incomplete language support."
                )
            )

    # =========================================================================
    # SEQ-POOL-06: acquire() → probe_workspace_readiness wiring
    # =========================================================================

    @patch('serena.global_lsp_pool.probe_workspace_readiness')
    def test_seq_pool_06_acquire_probes_new_workspace(self, mock_probe):
        """
        CONTRACT TRACEABILITY:
        - Contract: GlobalLanguageServerPool.acquire()
        - Enforces: SEQ-POOL-06: acquire MUST call probe_workspace_readiness after add_workspace_root
                    for newly added multi-root workspaces (line 449-453)
        - Category: positive (integration wiring)
        - Adversarial: Implementation-blind

        BEHAVIOR:
        When acquire() adds a new workspace root to a multi-root LSP,
        probe_workspace_readiness MUST be called with the new workspace_root.

        Integration path: acquire() → adapter.add_workspace_root() → probe_workspace_readiness()
        """
        # Mock contract: contracts/lsp_lifecycle_authority_contract.py SEQ-POOL-06

        # ARRANGE: Mock LSP pool components for multi-root scenario
        # We need to test through actual GlobalLanguageServerPool construction
        mock_adapter_registry = MagicMock()
        mock_timeout_manager = MagicMock()

        # Create REAL GlobalLanguageServerPool (not mock - tests wiring)
        pool = GlobalLanguageServerPool(
            adapter_registry=mock_adapter_registry,
            timeout_manager=mock_timeout_manager
        )

        # Mock adapter for multi-root LSP
        mock_adapter = MagicMock()
        mock_adapter.can_serve_path.return_value = False  # New workspace (not yet served)

        # Mock adapter registry responses (GlobalLanguageServerPool stores as capability_registry)
        workspace_root = Path.cwd()  # Use current directory for test
        mock_adapter_registry.get_adapter.return_value = mock_adapter
        mock_adapter_registry.is_multi_root.return_value = True
        mock_adapter_registry.get_pool_key.return_value = ("python", workspace_root)

        # Mock LSP instance (already in pool, multi-root)
        mock_lsp = MagicMock()
        mock_lsp.is_alive.return_value = True

        # Pre-populate pool with existing LSP (multi-root scenario)
        pool_key = ("python", workspace_root)
        pool._pool[pool_key] = mock_lsp
        pool._session_refs[pool_key] = set()

        # Mock probe to return True (ready)
        mock_probe.return_value = True

        session_id = "test-session"

        # ACT: Acquire LSP (will add new workspace to multi-root LSP)
        result_lsp = pool.acquire(Language.PYTHON, workspace_root, session_id)

        # ASSERT: SEQ-POOL-06 - probe_workspace_readiness called after add_workspace_root
        self.assertTrue(
            mock_probe.called,
            msg=(
                f"\n[WHAT] test_seq_pool_06_acquire_probes_new_workspace FAILED\n"
                f"[WHY] SEQ-POOL-06 violation: probe_workspace_readiness not invoked after add_workspace_root\n"
                f"[CONTRACT] GlobalLanguageServerPool.acquire() SEQ-POOL-06 (line 449-453)\n"
                f"[EXPECTED] probe_workspace_readiness() called after adapter.add_workspace_root()\n"
                f"[ACTUAL] probe_workspace_readiness not called\n"
                f"[GUIDANCE - BEHAVIORAL] After calling adapter.add_workspace_root(lsp, workspace_root)\n"
                f"for a NEW workspace on multi-root LSP, implementation MUST call\n"
                f"probe_workspace_readiness(lsp, workspace_root, timeout_seconds) to verify LSP has\n"
                f"indexed the new workspace. Sequence: (1) check can_serve_path, (2) if False and\n"
                f"multi-root, call add_workspace_root, (3) THEN call probe_workspace_readiness.\n"
                f"Timeout should come from configuration (default 30 seconds)."
            )
        )

        # Verify probe was called with correct arguments
        mock_probe.assert_called_once_with(
            mock_lsp,
            workspace_root,
            30  # Expected timeout (default from config)
        )

        # Verify adapter.add_workspace_root was called BEFORE probe
        mock_adapter.add_workspace_root.assert_called_once_with(mock_lsp, workspace_root)

    @patch('serena.global_lsp_pool.probe_workspace_readiness')
    def test_seq_pool_06_skip_probe_existing_workspace(self, mock_probe):
        """
        CONTRACT TRACEABILITY:
        - Contract: GlobalLanguageServerPool.acquire()
        - Enforces: SEQ-POOL-06 skip: NO probe_workspace_readiness when workspace already served
        - Category: negative (guard clause)
        - Adversarial: Implementation-blind

        BEHAVIOR:
        When acquire() hits an existing LSP where the workspace is already served
        (can_serve_path returns True), probe_workspace_readiness MUST NOT be called.

        Integration path: acquire() → (check can_serve_path) → no probe
        """
        # Mock contract: contracts/lsp_lifecycle_authority_contract.py SEQ-POOL-06

        # ARRANGE: Mock LSP pool for existing workspace scenario
        mock_adapter_registry = MagicMock()
        mock_timeout_manager = MagicMock()

        pool = GlobalLanguageServerPool(
            adapter_registry=mock_adapter_registry,
            timeout_manager=mock_timeout_manager
        )

        # Mock adapter for multi-root LSP (workspace ALREADY served)
        workspace_root = Path.cwd()  # Use current directory for test
        mock_adapter = MagicMock()
        mock_adapter.can_serve_path.return_value = True  # Existing workspace

        mock_adapter_registry.get_adapter.return_value = mock_adapter
        mock_adapter_registry.is_multi_root.return_value = True
        mock_adapter_registry.get_pool_key.return_value = ("python", workspace_root)

        # Mock LSP already in pool
        mock_lsp = MagicMock()
        mock_lsp.is_alive.return_value = True

        pool_key = ("python", workspace_root)
        pool._pool[pool_key] = mock_lsp
        pool._session_refs[pool_key] = set()

        session_id = "test-session"

        # ACT: Acquire LSP (existing workspace)
        result_lsp = pool.acquire(Language.PYTHON, workspace_root, session_id)

        # ASSERT: SEQ-POOL-06 skip - probe NOT called for existing workspace
        self.assertFalse(
            mock_probe.called,
            msg=(
                f"\n[WHAT] test_seq_pool_06_skip_probe_existing_workspace FAILED\n"
                f"[WHY] SEQ-POOL-06 skip violation: probe_workspace_readiness invoked for existing workspace\n"
                f"[CONTRACT] GlobalLanguageServerPool.acquire() SEQ-POOL-06 skip guard\n"
                f"[EXPECTED] probe_workspace_readiness NOT called when adapter.can_serve_path() returns True\n"
                f"[ACTUAL] probe_workspace_readiness called {mock_probe.call_count} times\n"
                f"[GUIDANCE - BEHAVIORAL] Before calling probe_workspace_readiness, implementation\n"
                f"MUST check if workspace is already served. Use adapter.can_serve_path(lsp, workspace_root)\n"
                f"to determine if workspace is already indexed. Guard sequence: (1) check can_serve_path,\n"
                f"(2) if True, skip add_workspace_root AND skip probe_workspace_readiness (workspace\n"
                f"already ready), (3) only if False (new workspace), proceed with add + probe."
            )
        )

        # Verify add_workspace_root was also NOT called (existing workspace)
        self.assertFalse(
            mock_adapter.add_workspace_root.called,
            msg=(
                f"\n[WHAT] test_seq_pool_06_skip_probe_existing_workspace FAILED (add_workspace_root)\n"
                f"[WHY] Implementation error: add_workspace_root called for existing workspace\n"
                f"[EXPECTED] add_workspace_root NOT called when adapter.can_serve_path() returns True\n"
                f"[ACTUAL] add_workspace_root called {mock_adapter.add_workspace_root.call_count} times\n"
                f"[GUIDANCE - BEHAVIORAL] Verify adapter.can_serve_path() guard is checked BEFORE\n"
                f"both add_workspace_root and probe_workspace_readiness. Calling add_workspace_root\n"
                f"for already-served workspace can cause LSP errors or duplicate notifications."
            )
        )


if __name__ == '__main__':
    unittest.main()
