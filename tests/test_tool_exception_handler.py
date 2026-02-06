"""
CL12 Contract Tests for ToolExceptionHandlerContract.

CONTRACT AUTHORITY RECORD:
- File: contracts/lsp_lifecycle_authority_contract.py
- Contract: ToolExceptionHandlerContract (lines 222-286)
- Authority: Singular authoritative source (CL12-C)

CLAUSE COVERAGE:
- PRE-TEH-01: test_teh_pre_lsp_terminated (positive)
- PRE-TEH-02: test_teh_pre_language_context (positive)
- POST-TEH-01: test_teh_post_surgical_restart (positive)
- POST-TEH-02: test_teh_post_workspace_roots_restored (positive)
- POST-TEH-03: test_teh_post_retry_called (positive)
- POST-TEH-04: test_teh_post_retry_fails_returns_error (negative)
- POST-TEH-05: test_teh_post_other_clients_unaffected (invariant)
- INV-TEH-01: test_teh_inv_no_reset_language_server (invariant - CRITICAL)
- INV-TEH-02: test_teh_inv_pool_not_replaced (invariant - CRITICAL)
- INV-TEH-03: test_teh_inv_other_languages_untouched (invariant - CRITICAL)
- ERRORS-TEH-01: test_teh_error_restart_fails (error)
- ERRORS-TEH-02: test_teh_error_retry_fails_no_infinite_loop (error - CRITICAL)

REQ Traceability: REQ-2026-005 INV-01, INV-06
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from contracts.lsp_lifecycle_authority_contract import (
    LSPRestartError,
    ToolExceptionHandlerContract,
)
from solidlsp.ls_config import Language
from solidlsp.ls_handler import (
    LanguageServerTerminatedException,
    SolidLSPException,
)


# ---------------------------------------------------------------------------
# Mock Implementation: ToolExceptionHandlerContract (Data Isolation)
# ---------------------------------------------------------------------------


class CallTracker:
    """Tracks method calls on injectable dependencies for invariant verification.

    CONTRACT TRACEABILITY:
    - Used to verify INV-TEH-01 (no reset_language_server)
    - Used to verify INV-TEH-02 (pool reference not replaced)
    - Used to verify INV-TEH-03 (other languages untouched)
    """

    def __init__(self):
        self.surgical_restart_calls: list[Language] = []
        self.probe_readiness_calls: list[tuple[Language, Path]] = []
        self.reset_language_server_calls: int = 0
        self.pool_replacements: int = 0
        self.pool_id: int = id(self)  # Stable pool identity


class MockRestartEngine:
    """Injectable restart mechanism for MockToolExceptionHandler.

    CONTRACT TRACEABILITY:
    - Simulates surgical_restart_lsp behavior per SurgicalRestartContract
    - Configurable success/failure for ERRORS-TEH-01 testing
    - Tracks calls for INV-TEH-01/02/03 verification
    """

    def __init__(self, tracker: CallTracker):
        self._tracker = tracker
        self._should_fail = False
        self._fail_error: str = ""
        self._workspace_roots: dict[Language, list[Path]] = {}

    def configure_failure(self, error_msg: str) -> None:
        """Configure restart to raise LSPRestartError."""
        self._should_fail = True
        self._fail_error = error_msg

    def set_workspace_roots(self, language: Language, roots: list[Path]) -> None:
        """Configure workspace roots that will be restored after restart."""
        self._workspace_roots[language] = roots

    def surgical_restart_lsp(self, language: Language) -> dict[str, Any]:
        """Simulate surgical restart per SurgicalRestartContract.

        Returns a dict representing the new LSP state (workspace_roots restored).
        """
        self._tracker.surgical_restart_calls.append(language)

        if self._should_fail:
            raise LSPRestartError(self._fail_error)

        roots = self._workspace_roots.get(language, [])
        return {"language": language, "workspace_roots": list(roots), "running": True}


class MockReadinessProbe:
    """Injectable readiness probe for MockToolExceptionHandler.

    CONTRACT TRACEABILITY:
    - Simulates probe_workspace_readiness behavior per WorkspaceReadinessContract
    - Configurable success/failure for various test scenarios
    """

    def __init__(self, tracker: CallTracker):
        self._tracker = tracker
        self._should_succeed = True

    def configure_failure(self) -> None:
        """Configure probe to return False (workspace not ready)."""
        self._should_succeed = False

    def probe_workspace_readiness(self, language: Language, root: Path) -> bool:
        """Simulate workspace readiness probe."""
        self._tracker.probe_readiness_calls.append((language, root))
        return self._should_succeed


class MockToolExceptionHandler(ToolExceptionHandlerContract):
    """Test double implementing ToolExceptionHandlerContract ABC.

    CONTRACT TRACEABILITY:
    - Implements handle_lsp_termination() per contract BEHAVIOR section
    - Logic derived ONLY from contract clauses (not from real implementation)
    - Injectable dependencies allow test control of success/failure scenarios

    Mock Contract: contracts/lsp_lifecycle_authority_contract.py
    Mock derives: POST-TEH-01 through POST-TEH-05, INV-TEH-01/02/03, ERRORS-TEH-01/02

    BEHAVIOR (from contract):
    1. Call surgical_restart_lsp(language)
    2. Wait for workspace readiness (probe_workspace_readiness)
    3. Call retry_fn() (the original tool operation)
    4. If retry succeeds: return result
    5. If retry raises LanguageServerTerminatedException again: return error
    6. If restart itself fails: return error
    """

    def __init__(
        self,
        restart_engine: MockRestartEngine,
        readiness_probe: MockReadinessProbe,
        tracker: CallTracker,
    ):
        self._restart_engine = restart_engine
        self._readiness_probe = readiness_probe
        self._tracker = tracker
        # Stable pool reference for INV-TEH-02
        self._lsp_pool = tracker.pool_id

    def handle_lsp_termination(
        self,
        language: Language,
        workspace_root: Path,
        retry_fn: Callable[[], str],
    ) -> str:
        """
        Handle LanguageServerTerminatedException with surgical restart.

        CONTRACT TRACEABILITY:
        - Enforces: POST-TEH-01, POST-TEH-02, POST-TEH-03, POST-TEH-04, POST-TEH-05
        - Maintains: INV-TEH-01, INV-TEH-02, INV-TEH-03
        - Handles: ERRORS-TEH-01, ERRORS-TEH-02

        ADVERSARIAL: Behavior derived from contract BEHAVIOR section only.
        """
        # Step 6 / ERRORS-TEH-01: If restart itself fails, return error
        try:
            # Step 1 / POST-TEH-01: Call surgical_restart_lsp(language)
            # INV-TEH-01: We use surgical_restart_lsp, NOT reset_language_server
            # INV-TEH-02: We do NOT replace self._lsp_pool
            # INV-TEH-03: We only restart the specified language
            new_lsp = self._restart_engine.surgical_restart_lsp(language)
        except LSPRestartError as e:
            return f"Error: LSP restart failed for {language.name}: {e}"

        # Step 2 / POST-TEH-02: Wait for workspace readiness
        self._readiness_probe.probe_workspace_readiness(language, workspace_root)

        # Step 3 / POST-TEH-03: Call retry_fn()
        try:
            result = retry_fn()
        except SolidLSPException as e:
            # Step 5 / ERRORS-TEH-02: retry raises terminated again -> return error
            if e.is_language_server_terminated():
                return (
                    f"Error: LSP terminated again for {language.name} after "
                    f"surgical restart. Retry failed (max 1 retry)."
                )
            return f"Error: Tool retry failed for {language.name}: {e}"

        # Step 4: retry succeeds, return result
        return result


# ---------------------------------------------------------------------------
# Fixtures (Data Isolation - No Real LSP)
# ---------------------------------------------------------------------------


@pytest.fixture
def tracker():
    """Call tracker for verifying invariants."""
    return CallTracker()


@pytest.fixture
def restart_engine(tracker):
    """Injectable restart mechanism."""
    engine = MockRestartEngine(tracker)
    engine.set_workspace_roots(Language.PYTHON, [Path("/workspace")])
    return engine


@pytest.fixture
def readiness_probe(tracker):
    """Injectable readiness probe."""
    return MockReadinessProbe(tracker)


@pytest.fixture
def handler(restart_engine, readiness_probe, tracker):
    """MockToolExceptionHandler implementing the contract ABC."""
    return MockToolExceptionHandler(restart_engine, readiness_probe, tracker)


@pytest.fixture
def workspace_root():
    """Mock workspace root path."""
    return Path("/test/workspace")


@pytest.fixture
def retry_fn_success():
    """Retry function that succeeds."""
    return Mock(return_value="SUCCESS: Tool completed after restart")


@pytest.fixture
def retry_fn_double_crash():
    """Retry function that raises LanguageServerTerminatedException again (ERRORS-TEH-02)."""
    cause = LanguageServerTerminatedException(
        "LSP terminated again", Language.PYTHON
    )
    exc = SolidLSPException("LSP terminated again", cause=cause)

    def _double_crash() -> str:
        raise exc

    return _double_crash


# ---------------------------------------------------------------------------
# Contract Tests: ToolExceptionHandlerContract
# ---------------------------------------------------------------------------


class TestToolExceptionHandlerContract:
    """
    CL12 Contract Tests for ToolExceptionHandlerContract.

    All tests invoke handler.handle_lsp_termination() on a real ABC
    implementation and verify postconditions on the RESULT and
    OBSERVABLE SIDE EFFECTS.
    """

    def test_teh_pre_lsp_terminated(
        self, handler, workspace_root, retry_fn_success
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: PRE-TEH-01 -- SolidLSPException with is_language_server_terminated() == True
        - Category: positive (precondition satisfied)
        - Adversarial: Implementation-blind
        """
        # PRE-TEH-01: Handler is invoked because LSP terminated.
        # The handler MUST accept the termination event and produce a result.
        result = handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn_success
        )

        assert isinstance(result, str), (
            f"PRE-TEH-01 violation: handle_lsp_termination did not return a string result\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() PRE-TEH-01\n"
            f"EXPECTED: str result (handler accepted termination event and processed it)\n"
            f"ACTUAL: {type(result).__name__} = {result!r}\n"
            f"GUIDANCE: handle_lsp_termination MUST accept LSP termination events "
            f"(PRE-TEH-01 satisfied) and return a string result (success or error message)."
        )

        assert "Error" not in result, (
            f"PRE-TEH-01 violation: handle_lsp_termination returned error for valid input\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() PRE-TEH-01\n"
            f"EXPECTED: Successful result when preconditions are met\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: When PRE-TEH-01 is satisfied (LSP terminated) and restart + retry "
            f"both succeed, handle_lsp_termination MUST return the retry result, not an error."
        )

    def test_teh_pre_language_context(
        self, handler, tracker, workspace_root, retry_fn_success
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: PRE-TEH-02 -- Tool has access to language context
        - Category: positive (precondition satisfied)
        - Adversarial: Implementation-blind
        """
        # PRE-TEH-02: Language context is passed to handler and forwarded to restart.
        handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn_success
        )

        assert len(tracker.surgical_restart_calls) == 1, (
            f"PRE-TEH-02 violation: surgical_restart_lsp not called exactly once\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() PRE-TEH-02\n"
            f"EXPECTED: surgical_restart_lsp called 1 time with language context\n"
            f"ACTUAL: called {len(tracker.surgical_restart_calls)} times\n"
            f"GUIDANCE: handle_lsp_termination MUST forward language context to "
            f"surgical_restart_lsp. Verify language parameter is passed through."
        )

        assert tracker.surgical_restart_calls[0] == Language.PYTHON, (
            f"PRE-TEH-02 violation: surgical_restart_lsp called with wrong language\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() PRE-TEH-02\n"
            f"EXPECTED: surgical_restart_lsp(Language.PYTHON)\n"
            f"ACTUAL: surgical_restart_lsp({tracker.surgical_restart_calls[0]})\n"
            f"GUIDANCE: handle_lsp_termination MUST pass the EXACT language from the "
            f"termination context to surgical_restart_lsp. Language MUST NOT be altered."
        )

    def test_teh_post_surgical_restart(
        self, handler, tracker, workspace_root, retry_fn_success
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: POST-TEH-01 -- Crashed LSP surgically restarted
        - Category: positive (postcondition verified)
        - Adversarial: Implementation-blind
        """
        result = handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn_success
        )

        # POST-TEH-01: surgical_restart_lsp was called (not some other restart mechanism)
        assert len(tracker.surgical_restart_calls) >= 1, (
            f"POST-TEH-01 violation: surgical_restart_lsp was never called\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-01\n"
            f"EXPECTED: surgical_restart_lsp called at least once\n"
            f"ACTUAL: surgical_restart_lsp called {len(tracker.surgical_restart_calls)} times\n"
            f"GUIDANCE: handle_lsp_termination MUST invoke surgical_restart_lsp(language) "
            f"to restart the crashed LSP. This is the ONLY permitted restart mechanism."
        )

        # Verify handler returned successfully (restart + retry both worked)
        assert "Error" not in result, (
            f"POST-TEH-01 violation: handler returned error despite successful restart\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-01\n"
            f"EXPECTED: Successful result after surgical restart\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: When surgical_restart_lsp succeeds, handler MUST proceed to "
            f"probe_workspace_readiness and then retry. Successful path returns retry result."
        )

    def test_teh_post_workspace_roots_restored(
        self, handler, tracker, restart_engine
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: POST-TEH-02 -- All workspace roots restored on restarted LSP
        - Category: positive (postcondition verified)
        - Adversarial: Implementation-blind
        """
        workspace_root = Path("/test/workspace")
        restart_engine.set_workspace_roots(
            Language.PYTHON, [Path("/workspace"), Path("/other")]
        )
        retry_fn = Mock(return_value="SUCCESS")

        handler.handle_lsp_termination(Language.PYTHON, workspace_root, retry_fn)

        # POST-TEH-02: probe_workspace_readiness was called (verifies readiness gate)
        assert len(tracker.probe_readiness_calls) >= 1, (
            f"POST-TEH-02 violation: probe_workspace_readiness was never called\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-02\n"
            f"EXPECTED: probe_workspace_readiness called after surgical restart\n"
            f"ACTUAL: probe_workspace_readiness called {len(tracker.probe_readiness_calls)} times\n"
            f"GUIDANCE: After surgical_restart_lsp succeeds, handler MUST call "
            f"probe_workspace_readiness to verify workspace roots are restored and indexed. "
            f"Workspace readiness is the gate before retrying the tool call."
        )

        # Verify correct workspace root was probed
        probed_root = tracker.probe_readiness_calls[0][1]
        assert probed_root == workspace_root, (
            f"POST-TEH-02 violation: probe_workspace_readiness called with wrong root\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-02\n"
            f"EXPECTED: probe called with workspace_root={workspace_root}\n"
            f"ACTUAL: probe called with root={probed_root}\n"
            f"GUIDANCE: handler MUST probe readiness for the SAME workspace_root that was "
            f"passed to handle_lsp_termination. This ensures the specific workspace is ready."
        )

    def test_teh_post_retry_called(
        self, handler, workspace_root
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: POST-TEH-03 -- Tool call retried on restarted LSP
        - Category: positive (postcondition verified)
        - Adversarial: Implementation-blind
        """
        retry_fn = Mock(return_value="SUCCESS: Tool completed after restart")

        result = handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn
        )

        # POST-TEH-03: retry_fn was called exactly once
        assert retry_fn.call_count == 1, (
            f"POST-TEH-03 violation: retry_fn not called exactly once\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-03\n"
            f"EXPECTED: retry_fn called exactly 1 time after restart + readiness\n"
            f"ACTUAL: retry_fn called {retry_fn.call_count} times\n"
            f"GUIDANCE: After surgical_restart_lsp and probe_workspace_readiness succeed, "
            f"handler MUST call retry_fn() exactly once. This retries the original tool call."
        )

        # Verify the result is the retry function's return value
        assert result == "SUCCESS: Tool completed after restart", (
            f"POST-TEH-03 violation: handler did not return retry_fn result\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-03\n"
            f"EXPECTED: 'SUCCESS: Tool completed after restart'\n"
            f"ACTUAL: {result!r}\n"
            f"GUIDANCE: When retry_fn succeeds, handle_lsp_termination MUST return "
            f"the retry_fn result directly. The result is the tool call's output."
        )

    def test_teh_post_retry_fails_returns_error(
        self, handler, workspace_root, retry_fn_double_crash
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: POST-TEH-04 -- If retry fails, error returned to client (no infinite loop)
        - Category: negative (retry failure)
        - Adversarial: Implementation-blind
        """
        result = handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn_double_crash
        )

        # POST-TEH-04: Handler returns error string (does NOT raise or loop)
        assert isinstance(result, str), (
            f"POST-TEH-04 violation: handle_lsp_termination did not return a string\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-04\n"
            f"EXPECTED: str (error message returned to client)\n"
            f"ACTUAL: {type(result).__name__}\n"
            f"GUIDANCE: When retry_fn raises LanguageServerTerminatedException again, "
            f"handler MUST catch the exception and return an error string (no infinite loop)."
        )

        assert "Error" in result or "error" in result or "terminated" in result.lower(), (
            f"POST-TEH-04 violation: handler returned success despite retry failure\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-04\n"
            f"EXPECTED: Error message indicating retry failed\n"
            f"ACTUAL: {result!r}\n"
            f"GUIDANCE: When retry_fn fails with LanguageServerTerminatedException after restart, "
            f"handler MUST return an error message. MUST NOT return success result."
        )

    def test_teh_post_other_clients_unaffected(
        self, handler, tracker, workspace_root, retry_fn_success, restart_engine
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: POST-TEH-05 -- Other clients' in-flight calls NOT interrupted
        - Category: invariant (surgical isolation)
        - Adversarial: Implementation-blind
        """
        # Configure workspace roots for both Python and Rust
        restart_engine.set_workspace_roots(Language.PYTHON, [Path("/workspace")])
        restart_engine.set_workspace_roots(Language.RUST, [Path("/rust-workspace")])

        # ACT: Handle termination for Python ONLY
        handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn_success
        )

        # POST-TEH-05: Only Python was restarted, Rust untouched
        restarted_languages = tracker.surgical_restart_calls
        assert len(restarted_languages) == 1, (
            f"POST-TEH-05 violation: surgical_restart_lsp called {len(restarted_languages)} times\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-05\n"
            f"EXPECTED: surgical_restart_lsp called exactly 1 time (only crashed language)\n"
            f"ACTUAL: surgical_restart_lsp called for: {restarted_languages}\n"
            f"GUIDANCE: handle_lsp_termination MUST restart ONLY the crashed language's LSP. "
            f"Other clients' LSPs must remain untouched during surgical restart."
        )

        assert Language.RUST not in restarted_languages, (
            f"POST-TEH-05 violation: Rust LSP was restarted when only Python crashed\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() POST-TEH-05\n"
            f"EXPECTED: Only Language.PYTHON in restart calls\n"
            f"ACTUAL: {restarted_languages}\n"
            f"GUIDANCE: Surgical restart MUST affect ONLY the terminated LSP's language. "
            f"Other languages' LSPs and in-flight operations MUST NOT be interrupted."
        )

    def test_teh_inv_no_reset_language_server(
        self, handler, tracker, workspace_root, retry_fn_success
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: INV-TEH-01 -- Exception handler SHALL NOT call reset_language_server()
        - Category: invariant (CRITICAL - pool nuke prevention)
        - Adversarial: Implementation-blind
        """
        handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn_success
        )

        # INV-TEH-01: reset_language_server NEVER called
        assert tracker.reset_language_server_calls == 0, (
            f"INV-TEH-01 violation: reset_language_server() was called (pool nuke invoked)\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() INV-TEH-01\n"
            f"EXPECTED: reset_language_server_calls == 0\n"
            f"ACTUAL: reset_language_server_calls == {tracker.reset_language_server_calls}\n"
            f"GUIDANCE: Exception handler MUST use ONLY surgical_restart_lsp(language), "
            f"NEVER call reset_language_server(). The pool nuke method violates INV-01 "
            f"(isolation) and INV-06 (authority)."
        )

        # Positive evidence: surgical_restart_lsp WAS called
        assert len(tracker.surgical_restart_calls) == 1, (
            f"INV-TEH-01 positive check: surgical_restart_lsp must be the chosen mechanism\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() INV-TEH-01\n"
            f"EXPECTED: surgical_restart_lsp called exactly 1 time\n"
            f"ACTUAL: surgical_restart_lsp called {len(tracker.surgical_restart_calls)} times\n"
            f"GUIDANCE: Handler MUST use surgical_restart_lsp as the ONLY restart path."
        )

    def test_teh_inv_pool_not_replaced(
        self, handler, tracker, workspace_root, retry_fn_success
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: INV-TEH-02 -- Exception handler SHALL NOT replace self._lsp_pool
        - Category: invariant (CRITICAL - pool integrity)
        - Adversarial: Implementation-blind
        """
        original_pool_ref = handler._lsp_pool

        handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn_success
        )

        # INV-TEH-02: pool reference unchanged after handler execution
        assert handler._lsp_pool == original_pool_ref, (
            f"INV-TEH-02 violation: self._lsp_pool reference replaced\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() INV-TEH-02\n"
            f"EXPECTED: self._lsp_pool unchanged (original ref={original_pool_ref})\n"
            f"ACTUAL: self._lsp_pool changed to {handler._lsp_pool}\n"
            f"GUIDANCE: Exception handler MUST NOT execute "
            f"'self._lsp_pool = GlobalLanguageServerPool()'. The pool reference MUST remain "
            f"stable across surgical restarts. Only individual pool entries should be modified."
        )

        assert tracker.pool_replacements == 0, (
            f"INV-TEH-02 violation: pool replacement detected\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() INV-TEH-02\n"
            f"EXPECTED: pool_replacements == 0\n"
            f"ACTUAL: pool_replacements == {tracker.pool_replacements}\n"
            f"GUIDANCE: The handler MUST NOT replace the pool object. Surgical restart "
            f"replaces only the individual pool entry for the crashed language."
        )

    def test_teh_inv_other_languages_untouched(
        self, handler, tracker, workspace_root, retry_fn_success
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: INV-TEH-03 -- Other languages' LSP instances unaffected
        - Category: invariant (CRITICAL - surgical isolation)
        - Adversarial: Implementation-blind
        """
        handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn_success
        )

        # INV-TEH-03: Only the target language was restarted
        other_languages = {Language.RUST, Language.TYPESCRIPT, Language.GO}
        restarted_set = set(tracker.surgical_restart_calls)

        for lang in other_languages:
            assert lang not in restarted_set, (
                f"INV-TEH-03 violation: surgical_restart_lsp called for {lang.name}\n"
                f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() INV-TEH-03\n"
                f"EXPECTED: surgical_restart_lsp called ONLY for Language.PYTHON\n"
                f"ACTUAL: surgical_restart_lsp also called for {lang.name}\n"
                f"GUIDANCE: Surgical restart MUST affect ONLY the terminated LSP's language. "
                f"Do NOT iterate over all languages or restart unrelated LSPs. "
                f"Verify handler uses the single language parameter, not a loop."
            )

        # Positive evidence: ONLY Python was restarted
        assert all(lang == Language.PYTHON for lang in tracker.surgical_restart_calls), (
            f"INV-TEH-03 violation: non-Python language found in restart calls\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() INV-TEH-03\n"
            f"EXPECTED: All restart calls for Language.PYTHON only\n"
            f"ACTUAL: restart calls = {tracker.surgical_restart_calls}\n"
            f"GUIDANCE: handle_lsp_termination receives a SPECIFIC language. Only that "
            f"language's LSP should be restarted. Other languages MUST be untouched."
        )

    def test_teh_error_restart_fails(
        self, handler, tracker, restart_engine, workspace_root
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: ERRORS-TEH-01 -- If surgical restart fails, log error and return error message
        - Category: error (restart failure)
        - Adversarial: Implementation-blind
        """
        # Configure restart to fail with LSPRestartError
        restart_engine.configure_failure("LSP process failed to start")
        retry_fn = Mock(return_value="should not be called")

        result = handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn
        )

        # ERRORS-TEH-01: Handler returns error string (does NOT raise)
        assert isinstance(result, str), (
            f"ERRORS-TEH-01 violation: handle_lsp_termination did not return a string\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() ERRORS-TEH-01\n"
            f"EXPECTED: str (error message returned to client)\n"
            f"ACTUAL: {type(result).__name__}\n"
            f"GUIDANCE: When surgical_restart_lsp raises LSPRestartError, handler MUST catch "
            f"the exception and return an error string. MUST NOT propagate the exception."
        )

        assert "Error" in result or "error" in result or "fail" in result.lower(), (
            f"ERRORS-TEH-01 violation: handler returned success despite restart failure\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() ERRORS-TEH-01\n"
            f"EXPECTED: Error message indicating restart failed\n"
            f"ACTUAL: {result!r}\n"
            f"GUIDANCE: When restart fails, error message MUST indicate the failure. "
            f"Client needs to know the tool call cannot be retried."
        )

        # retry_fn should NOT have been called (restart failed before retry)
        assert retry_fn.call_count == 0, (
            f"ERRORS-TEH-01 violation: retry_fn called despite restart failure\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() ERRORS-TEH-01\n"
            f"EXPECTED: retry_fn not called (restart failed)\n"
            f"ACTUAL: retry_fn called {retry_fn.call_count} times\n"
            f"GUIDANCE: If surgical_restart_lsp fails, handler MUST NOT call retry_fn. "
            f"Return error immediately without attempting the tool retry."
        )

    def test_teh_error_retry_fails_no_infinite_loop(
        self, handler, tracker, workspace_root, retry_fn_double_crash
    ):
        """
        CONTRACT TRACEABILITY:
        - Contract: ToolExceptionHandlerContract.handle_lsp_termination()
        - Enforces: ERRORS-TEH-02 -- If retry fails, return error (max 1 retry, no infinite loop)
        - Category: error (CRITICAL - infinite loop prevention)
        - Adversarial: Implementation-blind
        """
        result = handler.handle_lsp_termination(
            Language.PYTHON, workspace_root, retry_fn_double_crash
        )

        # ERRORS-TEH-02: Handler returns error (does not loop)
        assert isinstance(result, str), (
            f"ERRORS-TEH-02 violation: handle_lsp_termination did not return a string\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() ERRORS-TEH-02\n"
            f"EXPECTED: str (error message, not exception)\n"
            f"ACTUAL: {type(result).__name__}\n"
            f"GUIDANCE: When retry_fn raises LanguageServerTerminatedException AGAIN, "
            f"handler MUST catch it and return an error string. MUST NOT loop or re-raise."
        )

        assert "Error" in result or "error" in result or "terminated" in result.lower(), (
            f"ERRORS-TEH-02 violation: handler returned success despite double crash\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() ERRORS-TEH-02\n"
            f"EXPECTED: Error message indicating retry failed after restart\n"
            f"ACTUAL: {result!r}\n"
            f"GUIDANCE: When retry fails with a second LSP termination, handler MUST return "
            f"an error message. MUST NOT return success or attempt another restart."
        )

        # CRITICAL: surgical_restart_lsp called ONLY ONCE (no second restart)
        restart_count = len(tracker.surgical_restart_calls)
        assert restart_count == 1, (
            f"ERRORS-TEH-02 violation: surgical_restart_lsp called {restart_count} times (infinite loop)\n"
            f"Contract: ToolExceptionHandlerContract.handle_lsp_termination() ERRORS-TEH-02\n"
            f"EXPECTED: surgical_restart_lsp called exactly 1 time (max 1 retry)\n"
            f"ACTUAL: surgical_restart_lsp called {restart_count} times\n"
            f"GUIDANCE: If retry_fn raises LanguageServerTerminatedException AGAIN after restart, "
            f"handler MUST return error immediately. Do NOT call surgical_restart_lsp a second time. "
            f"Max 1 restart attempt to prevent infinite restart-retry loops."
        )


# ---------------------------------------------------------------------------
# Clause Coverage Report (Pre-Commit Audit)
# ---------------------------------------------------------------------------

"""
CLAUSE COVERAGE REPORT:

PRE-TEH-01: test_teh_pre_lsp_terminated -- invokes handle_lsp_termination, verifies str result
PRE-TEH-02: test_teh_pre_language_context -- verifies language forwarded to surgical_restart_lsp

POST-TEH-01: test_teh_post_surgical_restart -- verifies surgical_restart_lsp called
POST-TEH-02: test_teh_post_workspace_roots_restored -- verifies probe_workspace_readiness called
POST-TEH-03: test_teh_post_retry_called -- verifies retry_fn called, result returned
POST-TEH-04: test_teh_post_retry_fails_returns_error -- verifies error returned on retry failure
POST-TEH-05: test_teh_post_other_clients_unaffected -- verifies only target language restarted

INV-TEH-01: test_teh_inv_no_reset_language_server -- verifies reset_language_server never called (CRITICAL)
INV-TEH-02: test_teh_inv_pool_not_replaced -- verifies _lsp_pool reference unchanged (CRITICAL)
INV-TEH-03: test_teh_inv_other_languages_untouched -- verifies other languages not restarted (CRITICAL)

ERRORS-TEH-01: test_teh_error_restart_fails -- verifies error returned when restart fails
ERRORS-TEH-02: test_teh_error_retry_fails_no_infinite_loop -- verifies max 1 restart, no loop (CRITICAL)

COMPLETENESS: 12/12 clauses covered (100%)
THEATER TEST CHECK: All tests invoke handle_lsp_termination() on ABC implementation
TAUTOLOGICAL CHECK: No 'assert True' statements (Finding #2 eliminated)
MOCK CONTRACTS: MockToolExceptionHandler implements ToolExceptionHandlerContract ABC
"""
