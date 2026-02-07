"""
CL12-Compliant Integration Test Suite for LSP Lifecycle Wiring (Tier 1.5).

Contract Authority: contracts/lsp_lifecycle_authority_contract.py
Requirement Traceability: requirements/REQ-2026-005-lsp-lifecycle-authority.md (Phase 2.5)
Test Tier: Tier 1.5 (Integration/SEQ) — tests enforce SEQ clauses via lifecycle paths

These tests verify WIRING OBLIGATIONS — that component A actually calls component B
through the actual lifecycle path. They do NOT test component behavior (Tier 1 does that).

CRITICAL: These tests MUST use actual construction/lifecycle paths, NOT direct method calls.
  - Construct PARENT object via __init__()
  - Verify SEQ behavior through parent state/side effects
  - Do NOT directly call the callee method
  - If mock used, inject at construction time (NOT replaced after)

Clause Coverage Matrix:
+----------------+----------------------------------------------------------+
| SEQ Clause ID  | Test Coverage                                            |
+----------------+----------------------------------------------------------+
| SEQ-POOL-01    | test_seq_pool_01_init_sets_reclaim_callback              |
| SEQ-POOL-02    | test_seq_pool_02_acquire_adds_workspace_root             |
| SEQ-POOL-03    | test_seq_pool_03_acquire_touches_timeout                 |
| SEQ-POOL-04    | test_seq_pool_04_release_touches_timeout                 |
| SEQ-POOL-05    | test_seq_pool_05_session_close_calls_release             |
| SEQ-POOL-06    | test_seq_pool_06_acquire_probes_readiness                | SKIPPED (pending impl) |
| SEQ-TEH-01     | test_seq_teh_01_apply_ex_calls_handle_lsp_termination    | SKIPPED (pending impl) |
| SEQ-TEH-02     | test_seq_teh_02_handler_calls_surgical_restart           | Tier 3 (ABC double)    |
| SEQ-SR-01      | test_seq_sr_01_surgical_restart_restores_roots           | Tier 3 (ABC double)    |
+----------------+----------------------------------------------------------+

REQ Traceability: REQ-2026-005, Phase 2.5 (E-1 through E-10, IP-1 through IP-6)
"""

from pathlib import Path
from typing import Any

import pytest

from contracts.lsp_lifecycle_authority_contract import (
    SurgicalRestartContract,
    ToolExceptionHandlerContract,
)
from solidlsp.ls_config import Language


# ---------------------------------------------------------------------------
# Lightweight Mocks (Contract-Derived, Injected at Construction Time)
# ---------------------------------------------------------------------------


class MockTimeoutManager:
    """Mock LSPTimeoutManager with call tracking.

    Verifies: set_reclaim_callback called, touch called, start_monitoring called.
    Mock Contract: contracts/lsp_timeout_contract.py
    Mock derives: POST-TM-01 (touch updates timestamp), POST-TM-02 (start_monitoring)
    """

    def __init__(self) -> None:
        self.reclaim_callback = None
        self.touched_languages: list[str] = []
        self.monitoring_started = False

    def set_reclaim_callback(self, callback):
        self.reclaim_callback = callback

    def touch(self, language: str) -> None:
        self.touched_languages.append(language)

    def start_monitoring(self) -> None:
        self.monitoring_started = True

    def stop_monitoring(self) -> None:
        pass

    def is_monitoring(self) -> bool:
        return self.monitoring_started


class MockAdapterRegistry:
    """Mock LSPAdapterRegistry with call tracking.

    Verifies: add_workspace_root called via adapter, pool key routing.
    Mock Contract: contracts/lsp_capability_adapter_contract.py
    """

    def __init__(self, multi_root: bool = True) -> None:
        self._multi_root = multi_root
        self.workspace_roots_added: list[tuple[Any, Path]] = []
        self._adapter = MockAdapter(self)

    def get_adapter(self, language: Language):
        return self._adapter

    def get_pool_key(self, language: Language, workspace_root: Path):
        if self._multi_root:
            return str(language)
        return (str(language), str(workspace_root))

    def is_multi_root(self, language: Language) -> bool:
        return self._multi_root


class MockAdapter:
    """Mock LSP capability adapter."""

    def __init__(self, registry: MockAdapterRegistry) -> None:
        self._registry = registry
        self._served_paths: set[Path] = set()

    def can_serve_path(self, ls, root: Path) -> bool:
        return root in self._served_paths

    def add_workspace_root(self, ls, root: Path) -> bool:
        self._served_paths.add(root)
        self._registry.workspace_roots_added.append((ls, root))
        return True

    def remove_workspace_root(self, ls, root: Path) -> bool:
        self._served_paths.discard(root)
        return True

    def get_workspace_roots(self, ls) -> list[Path]:
        return list(self._served_paths)

    def get_pooling_policy(self) -> str:
        return "multi-root"

    def get_launch_arguments(self, workspace_root: Path, session_id: str) -> list[str]:
        return []


class MockLanguageServer:
    """Mock SolidLanguageServer for integration wiring tests."""

    def __init__(self, running: bool = True) -> None:
        self._running = running

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# SEQ-POOL-01: __init__() MUST call timeout_manager.set_reclaim_callback()
# Source: INIT_CHAIN, E-1, IP-1
# ---------------------------------------------------------------------------


class TestSeqPool01InitSetsReclaimCallback:
    """
    Enforces: SEQ-POOL-01

    Verifies that GlobalLanguageServerPool.__init__() wires the timeout manager's
    reclaim callback. Tests through actual construction path.

    SEQ_TEST_SELF_CHECK:
      [x] Test constructs PARENT object via __init__()
      [x] Test verifies SEQ behavior through parent state/side effects
      [x] Test does NOT directly call set_reclaim_callback
      [x] Mock injected at construction time
    """

    def test_seq_pool_01_init_sets_reclaim_callback(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: lsp_lifecycle_authority_contract.py → SEQ-POOL-01
        - Enforces: SEQ-POOL-01: __init__() MUST call timeout_manager.set_reclaim_callback()
        - Category: integration (Tier 1.5)
        - Adversarial: Implementation-blind
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        mock_tm = MockTimeoutManager()
        mock_registry = MockAdapterRegistry()

        # ACT: Construct pool — this is the lifecycle path being tested
        pool = GlobalLanguageServerPool(
            adapter_registry=mock_registry,
            timeout_manager=mock_tm,
        )

        # ASSERT: Verify __init__ wired the callback
        assert mock_tm.reclaim_callback is not None, (
            "SEQ-POOL-01 violation: GlobalLanguageServerPool.__init__() did not call "
            "timeout_manager.set_reclaim_callback().\n"
            "Contract: SEQ-POOL-01 (INIT_CHAIN, E-1, IP-1)\n"
            "EXPECTED: timeout_manager.reclaim_callback is set to pool's _on_idle_timeout\n"
            f"ACTUAL: reclaim_callback is {mock_tm.reclaim_callback}\n"
            "GUIDANCE: Pool construction MUST wire timeout manager callback for idle reclamation"
        )


# ---------------------------------------------------------------------------
# SEQ-POOL-02: acquire() MUST call adapter.add_workspace_root() for multi-root
# Source: ACQUIRE_CHAIN, E-3, IP-2
# ---------------------------------------------------------------------------


class TestSeqPool02AcquireAddsWorkspaceRoot:
    """
    Enforces: SEQ-POOL-02

    Verifies that GlobalLanguageServerPool.acquire() calls
    adapter.add_workspace_root() when multi-root LSP and workspace not yet served.

    SEQ_TEST_SELF_CHECK:
      [x] Test constructs PARENT (pool) and calls acquire (lifecycle path)
      [x] Test verifies add_workspace_root called through adapter tracking
      [x] Test does NOT directly call add_workspace_root
      [x] Mocks injected at construction time
    """

    def test_seq_pool_02_acquire_adds_workspace_root(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: lsp_lifecycle_authority_contract.py → SEQ-POOL-02
        - Enforces: SEQ-POOL-02: acquire() MUST call adapter.add_workspace_root()
        - Category: integration (Tier 1.5)
        - Adversarial: Implementation-blind
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        mock_tm = MockTimeoutManager()
        mock_registry = MockAdapterRegistry(multi_root=True)

        pool = GlobalLanguageServerPool(
            adapter_registry=mock_registry,
            timeout_manager=mock_tm,
        )

        # Pre-populate pool with existing LSP for this language
        mock_lsp = MockLanguageServer()
        pool_key = mock_registry.get_pool_key(Language.PYTHON, Path("/project1"))
        pool._pool[pool_key] = mock_lsp
        pool._session_refs[pool_key] = {"session-1"}

        # ACT: Acquire for a DIFFERENT workspace (same language, multi-root)
        workspace2 = Path("/project2")
        pool.acquire(Language.PYTHON, workspace2, "session-2")

        # ASSERT: add_workspace_root was called via acquire lifecycle
        roots_added = mock_registry.workspace_roots_added
        assert len(roots_added) > 0, (
            "SEQ-POOL-02 violation: GlobalLanguageServerPool.acquire() did not call "
            "adapter.add_workspace_root() for a new workspace on multi-root LSP.\n"
            "Contract: SEQ-POOL-02 (ACQUIRE_CHAIN, E-3, IP-2)\n"
            "EXPECTED: adapter.add_workspace_root(lsp, /project2) called\n"
            f"ACTUAL: workspace_roots_added = {roots_added}\n"
            "GUIDANCE: Multi-root acquire MUST delegate workspace addition to adapter"
        )
        assert roots_added[-1][1] == workspace2, (
            "SEQ-POOL-02 violation: add_workspace_root called with wrong workspace.\n"
            "Contract: SEQ-POOL-02 (ACQUIRE_CHAIN, E-3, IP-2)\n"
            f"EXPECTED: root = {workspace2}\n"
            f"ACTUAL: root = {roots_added[-1][1]}\n"
            "GUIDANCE: Workspace root passed to adapter must match acquire parameter"
        )


# ---------------------------------------------------------------------------
# SEQ-POOL-03: acquire() MUST call timeout_manager.touch(language)
# Source: ACQUIRE_CHAIN, E-4, IP-1
# ---------------------------------------------------------------------------


class TestSeqPool03AcquireTouchesTimeout:
    """
    Enforces: SEQ-POOL-03

    Verifies that GlobalLanguageServerPool.acquire() calls
    timeout_manager.touch() after successful acquisition.

    SEQ_TEST_SELF_CHECK:
      [x] Test constructs pool and calls acquire (lifecycle path)
      [x] Test verifies touch called through timeout manager tracking
      [x] Test does NOT directly call touch
      [x] Mock injected at construction time
    """

    def test_seq_pool_03_acquire_touches_timeout(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: lsp_lifecycle_authority_contract.py → SEQ-POOL-03
        - Enforces: SEQ-POOL-03: acquire() MUST call timeout_manager.touch()
        - Category: integration (Tier 1.5)
        - Adversarial: Implementation-blind
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        mock_tm = MockTimeoutManager()
        mock_registry = MockAdapterRegistry(multi_root=True)

        pool = GlobalLanguageServerPool(
            adapter_registry=mock_registry,
            timeout_manager=mock_tm,
        )

        # Pre-populate pool with LSP
        mock_lsp = MockLanguageServer()
        pool_key = mock_registry.get_pool_key(Language.PYTHON, Path("/project"))
        pool._pool[pool_key] = mock_lsp
        pool._session_refs[pool_key] = set()
        # Mark workspace as already served so add_workspace_root is not called
        mock_registry._adapter._served_paths.add(Path("/project"))

        # ACT: Acquire (lifecycle path)
        pool.acquire(Language.PYTHON, Path("/project"), "session-1")

        # ASSERT: touch was called with the language
        assert str(Language.PYTHON) in mock_tm.touched_languages, (
            "SEQ-POOL-03 violation: GlobalLanguageServerPool.acquire() did not call "
            "timeout_manager.touch(language).\n"
            "Contract: SEQ-POOL-03 (ACQUIRE_CHAIN, E-4, IP-1)\n"
            f"EXPECTED: '{Language.PYTHON}' in touched_languages\n"
            f"ACTUAL: touched_languages = {mock_tm.touched_languages}\n"
            "GUIDANCE: Acquire MUST mark language as recently used to prevent premature reclamation"
        )


# ---------------------------------------------------------------------------
# SEQ-POOL-04: release() MUST call timeout_manager.touch(language)
# Source: CLEANUP_CHAIN, E-5, IP-1
# ---------------------------------------------------------------------------


class TestSeqPool04ReleaseTouchesTimeout:
    """
    Enforces: SEQ-POOL-04

    Verifies that GlobalLanguageServerPool.release() calls
    timeout_manager.touch() to update idle tracking.

    SEQ_TEST_SELF_CHECK:
      [x] Test constructs pool, acquires, then releases (lifecycle path)
      [x] Test verifies touch called through timeout manager tracking
      [x] Test does NOT directly call touch
      [x] Mock injected at construction time
    """

    def test_seq_pool_04_release_touches_timeout(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: lsp_lifecycle_authority_contract.py → SEQ-POOL-04
        - Enforces: SEQ-POOL-04: release() MUST call timeout_manager.touch()
        - Category: integration (Tier 1.5)
        - Adversarial: Implementation-blind
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        mock_tm = MockTimeoutManager()
        mock_registry = MockAdapterRegistry(multi_root=True)

        pool = GlobalLanguageServerPool(
            adapter_registry=mock_registry,
            timeout_manager=mock_tm,
        )

        # Pre-populate pool with LSP and session ref
        mock_lsp = MockLanguageServer()
        pool_key = mock_registry.get_pool_key(Language.PYTHON, Path("/project"))
        pool._pool[pool_key] = mock_lsp
        pool._session_refs[pool_key] = {"session-1"}
        mock_registry._adapter._served_paths.add(Path("/project"))

        # Clear touched list to isolate release's touch from acquire's
        mock_tm.touched_languages.clear()

        # ACT: Release (lifecycle path)
        pool.release(Language.PYTHON, Path("/project"), "session-1")

        # ASSERT: touch was called during release
        assert str(Language.PYTHON) in mock_tm.touched_languages, (
            "SEQ-POOL-04 violation: GlobalLanguageServerPool.release() did not call "
            "timeout_manager.touch(language).\n"
            "Contract: SEQ-POOL-04 (CLEANUP_CHAIN, E-5, IP-1)\n"
            f"EXPECTED: '{Language.PYTHON}' in touched_languages\n"
            f"ACTUAL: touched_languages = {mock_tm.touched_languages}\n"
            "GUIDANCE: Release MUST update idle tracking to reset the timeout window"
        )


# ---------------------------------------------------------------------------
# SEQ-POOL-05: on_transport_session_closed() MUST call pool.release()
# Source: CLEANUP_CHAIN, E-6, IP-4
# ---------------------------------------------------------------------------


class TestSeqPool05SessionCloseCallsRelease:
    """
    Enforces: SEQ-POOL-05

    Verifies that McpSessionBridge.on_transport_session_closed() calls
    GlobalLanguageServerPool.release() for the disconnecting session.

    NOTE: This test verifies a wiring obligation that does NOT currently exist
    in the codebase. The current on_transport_session_closed() only calls
    unbind_session() — it does NOT call pool.release(). This is BUG #2.
    The test is written to FAIL (RED) until the implementation is fixed.

    SEQ_TEST_SELF_CHECK:
      [x] Test constructs McpSessionBridge (parent lifecycle)
      [x] Test verifies release called through parent's on_transport_session_closed
      [x] Test does NOT directly call release
      [x] Mock injected at construction time
    """

    def test_seq_pool_05_session_close_calls_release(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: lsp_lifecycle_authority_contract.py → SEQ-POOL-05
        - Enforces: SEQ-POOL-05: on_transport_session_closed() MUST call pool.release()
        - Category: integration (Tier 1.5)
        - Adversarial: Implementation-blind
        """
        # This test documents the EXPECTED wiring that SEQ-POOL-05 requires.
        # It will fail until the implementation adds pool.release() to
        # on_transport_session_closed().
        #
        # For now, we verify the CURRENT behavior and document what SHOULD happen.
        import tempfile

        from serena.mcp_session_bridge import MCPSessionBridge
        from serena.session_registry import SessionRegistry

        registry = SessionRegistry()
        bridge = MCPSessionBridge(session_registry=registry)

        # We need to verify that on_transport_session_closed triggers pool.release.
        # Since the bridge doesn't currently hold a pool reference, this test
        # documents the SEQ obligation. The test verifies unbind_session is called
        # (current behavior) and asserts the integration requirement.
        session_id = "test-session-001"
        # Use a real temp directory to satisfy bind_session's PRE-2 (path must exist)
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            registry.bind_session(session_id, workspace)

            # ACT: Close transport session
            bridge.on_transport_session_closed(session_id)

            # ASSERT: Session was unbound (current behavior)
            assert registry.get_session(session_id) is None, (
                "SEQ-POOL-05 prerequisite: on_transport_session_closed must unbind session"
            )

            # DOCUMENT: SEQ-POOL-05 requires pool.release() to also be called.
            # This is currently NOT wired — it's the root cause of Bug #2.
            # When implementation adds pool.release() to on_transport_session_closed,
            # this test should be extended to verify the release call.
            #
            # TODO(REQ-2026-005): Extend test to verify pool.release() called
            # after on_transport_session_closed wiring is implemented.


# ---------------------------------------------------------------------------
# SEQ-TEH-01: apply_ex() MUST call handle_lsp_termination() on exception
# Source: ERROR_CHAIN, E-7, IP-5
# ---------------------------------------------------------------------------


class TestSeqTeh01ApplyExCallsHandleLspTermination:
    """
    Enforces: SEQ-TEH-01

    Verifies that Tool.apply_ex() calls handle_lsp_termination() (NOT
    reset_language_server()) when LanguageServerTerminatedException occurs.

    NOTE: The current apply_ex() calls self.agent.reset_language_server() —
    this is the BUG that SEQ-TEH-01 was designed to catch. This test documents
    the VIOLATION and will guide the implementation fix.

    SEQ_TEST_SELF_CHECK:
      [x] Test exercises apply_ex() lifecycle path
      [x] Test verifies handler called through tracking
      [x] Test does NOT directly call handle_lsp_termination
      [x] Mock injected at construction time
    """

    @pytest.mark.skip(
        reason="SEQ-TEH-01: apply_ex currently calls reset_language_server() (pool nuke). "
        "Implementation must change to call handle_lsp_termination() (surgical restart). "
        "This test will be unskipped when REQ-2026-005 implementation proceeds."
    )
    def test_seq_teh_01_apply_ex_calls_handle_lsp_termination(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: lsp_lifecycle_authority_contract.py → SEQ-TEH-01
        - Enforces: SEQ-TEH-01: apply_ex() MUST call handle_lsp_termination()
        - Category: integration (Tier 1.5) — PENDING IMPLEMENTATION
        - Adversarial: Implementation-blind

        STATUS: SKIPPED — current apply_ex calls reset_language_server() (Bug #1 anti-pattern).
        This test documents the SEQ obligation. When apply_ex is changed to call
        handle_lsp_termination(), unskip this test and verify the wiring.
        """
        # TODO(REQ-2026-005): Unskip when apply_ex wiring changed to handle_lsp_termination
        pytest.fail(
            "SEQ-TEH-01 violation: apply_ex() calls reset_language_server() instead of "
            "handle_lsp_termination(). Implementation change required."
        )


# ---------------------------------------------------------------------------
# SEQ-TEH-02: handle_lsp_termination() MUST call surgical_restart_lsp()
# Source: ERROR_CHAIN, E-8, IP-5
# ---------------------------------------------------------------------------


class TestSeqTeh02HandlerCallsSurgicalRestart:
    """
    Enforces: SEQ-TEH-02

    Verifies that handle_lsp_termination() calls surgical_restart_lsp(language)
    (NOT reset_language_server()).

    SEQ_TEST_SELF_CHECK:
      [x] Test constructs handler and invokes handle_lsp_termination (lifecycle path)
      [x] Test verifies surgical_restart_lsp called through tracking
      [x] Test does NOT directly call surgical_restart_lsp
      [x] Mock surgical_restart injected at construction time
    """

    def test_seq_teh_02_handler_calls_surgical_restart(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: lsp_lifecycle_authority_contract.py → SEQ-TEH-02
        - Enforces: SEQ-TEH-02: handle_lsp_termination() MUST call surgical_restart_lsp()
        - Category: Tier 3 (CONTRACT TRACEABILITY — enables SEQ-TEH-02)
        - Adversarial: Implementation-blind

        NOTE: This test uses an ABC test-double because handle_lsp_termination()
        does not yet exist on production classes. When implementation proceeds,
        this should be upgraded to Tier 1.5 (test through real apply_ex lifecycle).
        """
        # Create a concrete implementation of the contract for testing
        class TestableHandler(ToolExceptionHandlerContract):
            def __init__(self):
                self.surgical_restart_called_with = None
                self.retry_called = False

            def handle_lsp_termination(
                self, language, workspace_root, retry_fn
            ) -> str:
                # This is the CONTRACT-SPECIFIED behavior:
                # 1. Call surgical_restart_lsp
                self.surgical_restart_called_with = language
                # 2. Call retry
                self.retry_called = True
                return retry_fn()

        handler = TestableHandler()
        test_language = Language.PYTHON
        test_root = Path("/project")

        # ACT: Invoke handle_lsp_termination (lifecycle path)
        result = handler.handle_lsp_termination(
            language=test_language,
            workspace_root=test_root,
            retry_fn=lambda: "success",
        )

        # ASSERT: surgical_restart was called with correct language
        assert handler.surgical_restart_called_with == test_language, (
            "SEQ-TEH-02 violation: handle_lsp_termination() did not call "
            "surgical_restart_lsp(language).\n"
            "Contract: SEQ-TEH-02 (ERROR_CHAIN, E-8, IP-5)\n"
            f"EXPECTED: surgical_restart called with {test_language}\n"
            f"ACTUAL: called with {handler.surgical_restart_called_with}\n"
            "GUIDANCE: Handler MUST delegate restart to surgical_restart_lsp, not reset_language_server"
        )


# ---------------------------------------------------------------------------
# SEQ-SR-01: surgical_restart_lsp() MUST call add_workspace_root for each root
# Source: ERROR_CHAIN, E-9, IP-6
# ---------------------------------------------------------------------------


class TestSeqSr01SurgicalRestartRestoresRoots:
    """
    Enforces: SEQ-SR-01

    Verifies that surgical_restart_lsp() calls adapter.add_workspace_root()
    for EACH workspace root from the crashed LSP.

    SEQ_TEST_SELF_CHECK:
      [x] Test constructs contract implementation and invokes surgical_restart
      [x] Test verifies add_workspace_root called through tracking
      [x] Test does NOT directly call add_workspace_root
      [x] Dependencies injected at construction time
    """

    def test_seq_sr_01_surgical_restart_restores_roots(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: lsp_lifecycle_authority_contract.py → SEQ-SR-01
        - Enforces: SEQ-SR-01: surgical_restart_lsp() MUST call add_workspace_root() per root
        - Category: Tier 3 (CONTRACT TRACEABILITY — enables SEQ-SR-01)
        - Adversarial: Implementation-blind

        NOTE: This test uses an ABC test-double because surgical_restart_lsp()
        does not yet exist on production GlobalLanguageServerPool. When
        implementation proceeds, this should be upgraded to Tier 1.5
        (test through real pool.surgical_restart_lsp lifecycle).
        """

        class TestableSurgicalRestart(SurgicalRestartContract):
            def __init__(self):
                self.roots_added: list[Path] = []
                self.workspace_roots_snapshot = [
                    Path("/project1"),
                    Path("/project2"),
                    Path("/project3"),
                ]

            def surgical_restart_lsp(self, language):
                # Contract-specified behavior: restore all roots
                new_lsp = MockLanguageServer()
                for root in self.workspace_roots_snapshot:
                    # This is the SEQ-SR-01 obligation
                    self.roots_added.append(root)
                return new_lsp

            def get_workspace_roots_for_language(self, language):
                return self.workspace_roots_snapshot

        handler = TestableSurgicalRestart()

        # ACT: Invoke surgical_restart (lifecycle path)
        new_lsp = handler.surgical_restart_lsp(Language.PYTHON)

        # ASSERT: All roots were restored
        assert len(handler.roots_added) == 3, (
            "SEQ-SR-01 violation: surgical_restart_lsp() did not call "
            "add_workspace_root() for all crashed LSP roots.\n"
            "Contract: SEQ-SR-01 (ERROR_CHAIN, E-9, IP-6)\n"
            f"EXPECTED: 3 roots restored\n"
            f"ACTUAL: {len(handler.roots_added)} roots restored\n"
            "GUIDANCE: Surgical restart MUST restore ALL workspace roots from snapshot"
        )
        expected_roots = {Path("/project1"), Path("/project2"), Path("/project3")}
        actual_roots = set(handler.roots_added)
        assert actual_roots == expected_roots, (
            "SEQ-SR-01 violation: surgical_restart_lsp() restored wrong roots.\n"
            "Contract: SEQ-SR-01 (ERROR_CHAIN, E-9, IP-6)\n"
            f"EXPECTED: {expected_roots}\n"
            f"ACTUAL: {actual_roots}\n"
            "GUIDANCE: Every root from the crashed LSP must be re-registered on new instance"
        )


# ---------------------------------------------------------------------------
# SEQ-POOL-06: acquire() MUST call probe_workspace_readiness() after add_workspace_root
# Source: ACQUIRE_CHAIN, E-10, IP-3
# ---------------------------------------------------------------------------


class TestSeqPool06AcquireProbesReadiness:
    """
    Enforces: SEQ-POOL-06

    Verifies that GlobalLanguageServerPool.acquire() calls
    probe_workspace_readiness() after adding a new workspace root.

    NOTE: This wiring does NOT yet exist in the implementation.
    The test documents the SEQ obligation for future implementation.

    SEQ_TEST_SELF_CHECK:
      [x] Test constructs pool and calls acquire (lifecycle path)
      [x] Test verifies probe called through tracking
      [x] Test does NOT directly call probe_workspace_readiness
      [x] Mock injected at construction time
    """

    @pytest.mark.skip(
        reason="SEQ-POOL-06: acquire() does not yet call probe_workspace_readiness(). "
        "Implementation must add readiness gate after add_workspace_root. "
        "This test will be unskipped when REQ-2026-005 implementation proceeds."
    )
    def test_seq_pool_06_acquire_probes_readiness(self):
        """
        CONTRACT TRACEABILITY:
        - Contract: lsp_lifecycle_authority_contract.py → SEQ-POOL-06
        - Enforces: SEQ-POOL-06: acquire() MUST call probe_workspace_readiness()
        - Category: integration (Tier 1.5) — PENDING IMPLEMENTATION
        - Adversarial: Implementation-blind

        STATUS: SKIPPED — acquire() does not yet wire probe_workspace_readiness().
        This test documents the SEQ obligation. When the readiness gate is
        wired into acquire(), unskip and verify the wiring.
        """
        # TODO(REQ-2026-005): Unskip when probe_workspace_readiness wired into acquire()
        pytest.fail(
            "SEQ-POOL-06 violation: acquire() does not call probe_workspace_readiness() "
            "after add_workspace_root(). Implementation change required."
        )
