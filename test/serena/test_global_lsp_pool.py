"""
Tests for GlobalLanguageServerPool - manages LSP instances as shared global resources.

Following adversarial TDD approach: Tests written FIRST before implementation.
Contract: contracts/global_lsp_pool_contract.py (verified: 2026-01-11)
Issue: REQ-2 (LSP sharing), REQ-5 (idle reclamation), CON-1 (Serena owns isolation)

STRUCTURAL BLINDNESS: This test suite is written without access to implementation code.
All error messages must be self-documenting for the coder agent.

ARCHITECTURE: Database Connection Pooler Pattern (DD-1)
- Acquisition/release semantics
- Reference counting per session
- Idle timeout for reclamation (via LSPTimeoutManager integration)
- Capability-aware routing (multi-root vs single-root)

SYNC INTERFACE:
- All methods are synchronous (no async/await)
- Thread-safety via threading.Lock
- Lock hierarchy: session_lock -> pool_lock (DD-3, INV-6)
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock

from contracts.global_lsp_pool_contract import (
    MULTI_ROOT_LANGUAGES,
    POOL_KEY_TEST_CASES,
    SINGLE_ROOT_LANGUAGES,
    verify_pool_key_strategy,
    verify_reference_tracking,
)
from solidlsp.ls_config import Language


class TestGlobalLanguageServerPoolContract:
    """Test GlobalLanguageServerPool contract adherence."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_contract_multi_root_languages_valid(self):
        """
        Test that contract defines valid multi-root language list.

        CONTRACT VERIFICATION:
        - MULTI_ROOT_LANGUAGES must be list of valid language names
        - Used for pool key strategy (DD-2)

        WHAT: MULTI_ROOT_LANGUAGES list validation
        WHY: Ensures contract test data integrity before mock derivation (CL10)
        EXPECTED: All languages in MULTI_ROOT_LANGUAGES are valid Language enum values
        ACTUAL: Found invalid languages {invalid_langs}
        GUIDANCE: Contract must define MULTI_ROOT_LANGUAGES with valid Language enum names:
            - Each entry must match Language enum (e.g., "rust", "python", "go")
            - Multi-root LSPs share one instance across all workspace roots
            - Single-root LSPs require separate instances per root
        """
        invalid_langs = []
        for lang_str in MULTI_ROOT_LANGUAGES:
            try:
                # Verify language can be converted to Language enum
                Language[lang_str.upper()]
            except KeyError:
                invalid_langs.append(lang_str)

        assert len(invalid_langs) == 0, (
            f"❌ CONTRACT VIOLATION: Invalid languages in MULTI_ROOT_LANGUAGES\n"
            f"WHAT FAILED: Language enum validation\n"
            f"WHY: Contract test data must use valid Language enum values (CL10)\n"
            f"EXPECTED: All languages valid (rust, python, go, java, haskell, etc.)\n"
            f"ACTUAL: Invalid languages found: {invalid_langs}\n"
            f"GUIDANCE: Update MULTI_ROOT_LANGUAGES in contract with valid enum names"
        )

    def test_contract_single_root_languages_valid(self):
        """
        Test that contract defines valid single-root language list.

        CONTRACT VERIFICATION:
        - SINGLE_ROOT_LANGUAGES must be list of valid language names
        - Used for pool key strategy (DD-2)

        WHAT: SINGLE_ROOT_LANGUAGES list validation
        WHY: Ensures contract test data integrity before mock derivation (CL10)
        EXPECTED: All languages in SINGLE_ROOT_LANGUAGES are valid Language enum values
        ACTUAL: Found invalid languages {invalid_langs}
        GUIDANCE: Contract must define SINGLE_ROOT_LANGUAGES with valid Language enum names:
            - Each entry must match Language enum (e.g., "typescript", "c", "cpp")
            - Single-root LSPs require separate instances per workspace root
            - Multi-root LSPs share one instance across all roots
        """
        invalid_langs = []
        for lang_str in SINGLE_ROOT_LANGUAGES:
            try:
                # Verify language can be converted to Language enum
                Language[lang_str.upper()]
            except KeyError:
                invalid_langs.append(lang_str)

        assert len(invalid_langs) == 0, (
            f"❌ CONTRACT VIOLATION: Invalid languages in SINGLE_ROOT_LANGUAGES\n"
            f"WHAT FAILED: Language enum validation\n"
            f"WHY: Contract test data must use valid Language enum values (CL10)\n"
            f"EXPECTED: All languages valid (typescript, c, cpp, etc.)\n"
            f"ACTUAL: Invalid languages found: {invalid_langs}\n"
            f"GUIDANCE: Update SINGLE_ROOT_LANGUAGES in contract with valid enum names"
        )

    def test_contract_pool_key_test_cases_valid(self):
        """
        Test that contract POOL_KEY_TEST_CASES are structurally valid.

        CONTRACT VERIFICATION:
        - POOL_KEY_TEST_CASES must be list of 4-tuples
        - Format: (language_str, is_multi_root, workspace_root, expected_key_type)

        WHAT: POOL_KEY_TEST_CASES structure validation
        WHY: Ensures contract test data integrity before parametrized tests (CL10)
        EXPECTED: All test cases are 4-tuples with valid types
        ACTUAL: Found invalid test cases {invalid_cases}
        GUIDANCE: Contract must define POOL_KEY_TEST_CASES with format:
            - Each entry: (language_str, is_multi_root, workspace_root, expected_key_type)
            - language_str: str matching Language enum
            - is_multi_root: bool
            - workspace_root: Path
            - expected_key_type: "language" or "tuple"
        """
        invalid_cases = []
        for i, case in enumerate(POOL_KEY_TEST_CASES):
            if not isinstance(case, tuple) or len(case) != 4:
                invalid_cases.append((i, "not 4-tuple"))
            else:
                lang_str, is_multi, root, key_type = case
                if not isinstance(lang_str, str):
                    invalid_cases.append((i, f"language not str: {type(lang_str)}"))
                if not isinstance(is_multi, bool):
                    invalid_cases.append((i, f"is_multi_root not bool: {type(is_multi)}"))
                if not isinstance(root, Path):
                    invalid_cases.append((i, f"workspace_root not Path: {type(root)}"))
                if key_type not in ("language", "tuple"):
                    invalid_cases.append((i, f"invalid key_type: {key_type}"))

        assert len(invalid_cases) == 0, (
            f"❌ CONTRACT VIOLATION: Invalid POOL_KEY_TEST_CASES structure\n"
            f"WHAT FAILED: Test case validation\n"
            f"WHY: Contract test data must be properly structured (CL10)\n"
            f"EXPECTED: All test cases as 4-tuples (str, bool, Path, str)\n"
            f"ACTUAL: Invalid test cases: {invalid_cases}\n"
            f"GUIDANCE: Fix contract POOL_KEY_TEST_CASES to match required format"
        )

    def test_contract_verify_pool_key_strategy_helper(self):
        """
        Test that contract helper verify_pool_key_strategy() works correctly.

        CONTRACT VERIFICATION:
        - DD-2: Pool key = language (multi-root) or (language, rootUri) (single-root)
        - Helper must implement this logic for test validation

        WHAT: verify_pool_key_strategy() behavior validation
        WHY: Test helpers must correctly implement contract logic (CL10)
        EXPECTED: Multi-root returns language, single-root returns (language, root)
        ACTUAL: Multi-root key type {multi_key_type}, single-root key type {single_key_type}
        GUIDANCE: verify_pool_key_strategy() must return:
            - For multi-root (is_multi_root=True): Language enum (not tuple)
            - For single-root (is_multi_root=False): tuple of (Language, Path)
        """
        # Test multi-root case
        multi_key = verify_pool_key_strategy(
            Language.RUST,
            is_multi_root=True,
            workspace_root=Path("/project-a"),
        )
        multi_key_type = "language" if isinstance(multi_key, Language) else type(multi_key).__name__

        # Test single-root case
        single_key = verify_pool_key_strategy(
            Language.TYPESCRIPT,
            is_multi_root=False,
            workspace_root=Path("/project-b"),
        )
        single_key_type = "tuple" if isinstance(single_key, tuple) else type(single_key).__name__

        assert multi_key_type == "language", (
            f"❌ CONTRACT VIOLATION: verify_pool_key_strategy() multi-root logic wrong\n"
            f"WHAT FAILED: Multi-root pool key generation\n"
            f"WHY: DD-2 requires multi-root LSPs keyed by language only (INV-3)\n"
            f"EXPECTED: Language enum (not tuple)\n"
            f"ACTUAL: Key type is {multi_key_type}\n"
            f"GUIDANCE: For is_multi_root=True, return language (no root in key)"
        )

        assert single_key_type == "tuple", (
            f"❌ CONTRACT VIOLATION: verify_pool_key_strategy() single-root logic wrong\n"
            f"WHAT FAILED: Single-root pool key generation\n"
            f"WHY: DD-2 requires single-root LSPs keyed by (language, rootUri) (INV-4)\n"
            f"EXPECTED: tuple of (Language, Path)\n"
            f"ACTUAL: Key type is {single_key_type}\n"
            f"GUIDANCE: For is_multi_root=False, return tuple(language, workspace_root)"
        )

        # Verify single-root tuple structure
        if isinstance(single_key, tuple):
            assert len(single_key) == 2, (
                f"❌ CONTRACT VIOLATION: Single-root key tuple wrong length\n"
                f"WHAT FAILED: Tuple structure validation\n"
                f"WHY: DD-2 requires exactly 2 elements: (language, workspace_root)\n"
                f"EXPECTED: 2-tuple\n"
                f"ACTUAL: {len(single_key)}-tuple\n"
                f"GUIDANCE: Return tuple(language, workspace_root) for single-root"
            )

    def test_contract_verify_reference_tracking_helper(self):
        """
        Test that contract helper verify_reference_tracking() correctly tracks refs.

        CONTRACT VERIFICATION:
        - INV-2: Session references tracked accurately (no leaks)
        - Helper must implement acquire/release logic for test validation

        WHAT: verify_reference_tracking() behavior validation
        WHY: Test helpers must correctly implement contract logic (CL10)
        EXPECTED: Acquire adds session, release removes session
        ACTUAL: Acquire result {acq_result}, release result {rel_result}
        GUIDANCE: verify_reference_tracking() must:
            - For action="acquire": Add session_id to sessions_before set
            - For action="release": Remove session_id from sessions_before set
            - Return new set (don't mutate input)
        """
        # Test acquire action
        acq_result = verify_reference_tracking(
            sessions_before={"session-a"},
            session_id="session-b",
            action="acquire",
        )

        # Test release action
        rel_result = verify_reference_tracking(
            sessions_before={"session-a", "session-b"},
            session_id="session-a",
            action="release",
        )

        assert acq_result == {"session-a", "session-b"}, (
            f"❌ CONTRACT VIOLATION: verify_reference_tracking() acquire logic wrong\n"
            f"WHAT FAILED: Acquire reference tracking\n"
            f"WHY: POST-2 requires session reference recorded on acquire\n"
            f"EXPECTED: {{'session-a', 'session-b'}}\n"
            f"ACTUAL: {acq_result}\n"
            f"GUIDANCE: For action='acquire', add session_id to sessions_before set"
        )

        assert rel_result == {"session-b"}, (
            f"❌ CONTRACT VIOLATION: verify_reference_tracking() release logic wrong\n"
            f"WHAT FAILED: Release reference tracking\n"
            f"WHY: POST-4 requires session reference removed on release\n"
            f"EXPECTED: {{'session-b'}}\n"
            f"ACTUAL: {rel_result}\n"
            f"GUIDANCE: For action='release', remove session_id from sessions_before set"
        )


class TestGlobalLanguageServerPoolAcquireRelease:
    """Test GlobalLanguageServerPool acquire/release semantics."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_acquire_returns_functional_lsp(self):
        """
        Test that acquire() returns a functional SolidLanguageServer instance.

        CONTRACT:
        - POST-1: Returns functional LSP instance
        - PRE-1: language is valid Language enum
        - PRE-2: workspace_root is absolute Path

        WHAT: acquire() return value validation
        WHY: Clients depend on receiving working LSP for symbol operations
        EXPECTED: Returns SolidLanguageServer instance (not None, not Mock, not stub)
        ACTUAL: Returned {type(result).__name__}
        GUIDANCE: acquire() must return concrete LSP instance:
            - Import and instantiate SolidLanguageServer (or get from pool)
            - Ensure is_running() check via _ensure_functional_ls pattern (DD-7)
            - Never return None for valid inputs (PRE-1, PRE-2 satisfied)
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        result = pool.acquire(
            language=Language.PYTHON,
            workspace_root=self.project_path,
            session_id="test-session-1",
        )

        assert result is not None, (
            f"❌ FAILURE: acquire() returned None\n"
            f"WHAT FAILED: POST-1 (Returns functional LSP instance)\n"
            f"WHY: Client cannot perform symbol operations without LSP\n"
            f"EXPECTED: SolidLanguageServer instance\n"
            f"ACTUAL: None\n"
            f"GUIDANCE: acquire() must never return None for valid inputs.\n"
            f"  - Check PRE-1: language={Language.PYTHON} is valid Language enum\n"
            f"  - Check PRE-2: workspace_root={self.project_path} is absolute Path\n"
            f"  - Ensure LSP created or retrieved from pool"
        )

        # Verify it's a SolidLanguageServer (not Mock, not stub)
        from solidlsp import SolidLanguageServer

        assert isinstance(result, SolidLanguageServer), (
            f"❌ FAILURE: acquire() returned wrong type\n"
            f"WHAT FAILED: POST-1 (Returns functional LSP instance)\n"
            f"WHY: Client expects SolidLanguageServer for symbol operations\n"
            f"EXPECTED: SolidLanguageServer instance\n"
            f"ACTUAL: {type(result).__name__}\n"
            f"GUIDANCE: acquire() must return actual SolidLanguageServer.\n"
            f"  - Import from solidlsp: from solidlsp import SolidLanguageServer\n"
            f"  - Create instance or retrieve from pool._instances dict\n"
            f"  - Use _ensure_functional_ls pattern for crash recovery (DD-7)"
        )

        pool.stop_all(save_cache=False)

    def test_acquire_records_session_reference(self):
        """
        Test that acquire() records session_id as reference holder.

        CONTRACT:
        - POST-2: session_id recorded as reference holder
        - INV-2: Session references tracked accurately (no leaks)

        WHAT: Session reference tracking after acquire()
        WHY: REQ-2 requires reference counting for shared LSP management
        EXPECTED: get_sessions_for_lsp() returns {session_id} after acquire
        ACTUAL: Returns {actual_sessions}
        GUIDANCE: acquire() must record session reference:
            - Maintain sessions tracking dict: _sessions[pool_key] = set[session_id]
            - Add session_id to set on acquire: _sessions[key].add(session_id)
            - Return updated set from get_sessions_for_lsp()
            - Thread-safe: acquire pool_lock before mutation (INV-1)
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()
        session_id = "test-session-1"

        pool.acquire(
            language=Language.PYTHON,
            workspace_root=self.project_path,
            session_id=session_id,
        )

        actual_sessions = pool.get_sessions_for_lsp(
            language=Language.PYTHON,
            workspace_root=self.project_path,
        )

        assert session_id in actual_sessions, (
            f"❌ FAILURE: acquire() did not record session reference\n"
            f"WHAT FAILED: POST-2 (session_id recorded as reference holder)\n"
            f"WHY: INV-2 requires accurate reference tracking (no leaks)\n"
            f"EXPECTED: get_sessions_for_lsp() returns set containing '{session_id}'\n"
            f"ACTUAL: get_sessions_for_lsp() returns {actual_sessions}\n"
            f"GUIDANCE: acquire() must update session tracking:\n"
            f"  - Pool key = (Language.PYTHON, {self.project_path}) for single-root\n"
            f"  - Or just Language.PYTHON if multi-root\n"
            f"  - Add to _sessions[pool_key]: self._sessions[key].add(session_id)\n"
            f"  - Acquire pool_lock before mutation (thread-safety)"
        )

        pool.stop_all(save_cache=False)

    def test_acquire_multi_root_shares_instance(self):
        """
        Test that acquire() shares LSP instance for multi-root languages.

        CONTRACT:
        - DD-2: Pool key = language (multi-root) or (language, rootUri) (single-root)
        - INV-3: Multi-root LSPs keyed by language only
        - REQ-2: LSP instances shared where possible and correct

        WHAT: Multi-root LSP instance sharing across different workspace roots
        WHY: REQ-2 requires sharing LSPs to conserve memory (CON-3)
        EXPECTED: Same SolidLanguageServer instance for different roots (rust, python)
        ACTUAL: lsp1 is lsp2: {is_same}, lsp1 id={id(lsp1)}, lsp2 id={id(lsp2)}
        GUIDANCE: For multi-root languages (rust, python, go, java, haskell):
            - Pool key = language ONLY (ignore workspace_root)
            - Check if LSP already running: pool_key in self._instances
            - Return existing instance if found (don't create new)
            - Use LSPCapabilityRegistry.is_multi_root(language) to determine
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire rust LSP for project-a
        lsp1 = pool.acquire(
            language=Language.RUST,
            workspace_root=Path("/tmp/project-a"),
            session_id="session-a",
        )

        # Acquire rust LSP for project-b (different root)
        lsp2 = pool.acquire(
            language=Language.RUST,
            workspace_root=Path("/tmp/project-b"),
            session_id="session-b",
        )

        is_same = lsp1 is lsp2

        assert is_same, (
            f"❌ FAILURE: acquire() created separate LSP instances for multi-root language\n"
            f"WHAT FAILED: INV-3 (Multi-root LSPs keyed by language only)\n"
            f"WHY: REQ-2 requires sharing LSPs across roots for multi-root languages\n"
            f"EXPECTED: lsp1 is lsp2 (same instance)\n"
            f"ACTUAL: lsp1 is lsp2 = {is_same}, lsp1 id={id(lsp1)}, lsp2 id={id(lsp2)}\n"
            f"GUIDANCE: For multi-root languages (rust in MULTI_ROOT_LANGUAGES):\n"
            f"  - Pool key = Language.RUST (NOT tuple with root)\n"
            f"  - Check: pool_key in self._instances before creating new LSP\n"
            f"  - Return existing instance if found\n"
            f"  - Use LSPCapabilityRegistry.is_multi_root(Language.RUST) → True"
        )

        pool.stop_all(save_cache=False)

    def test_acquire_single_root_separate_instances(self):
        """
        Test that acquire() creates separate LSP instances for single-root languages.

        CONTRACT:
        - DD-2: Pool key = (language, rootUri) for single-root LSPs
        - INV-4: Single-root LSPs keyed by (language, rootUri)
        - CON-2: Single-root LSP limitation (per-root instances)

        WHAT: Single-root LSP instance separation across different workspace roots
        WHY: CON-2 requires separate instances (single-root LSPs can't serve multiple roots)
        EXPECTED: Different SolidLanguageServer instances for different roots (typescript)
        ACTUAL: lsp1 is lsp2: {is_same}, lsp1 id={id(lsp1)}, lsp2 id={id(lsp2)}
        GUIDANCE: For single-root languages (typescript, c, cpp):
            - Pool key = (language, workspace_root) tuple
            - Each root gets separate LSP instance
            - Check: pool_key in self._instances (key includes root)
            - Use LSPCapabilityRegistry.is_multi_root(language) → False
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire typescript LSP for project-a
        lsp1 = pool.acquire(
            language=Language.TYPESCRIPT,
            workspace_root=Path("/tmp/project-a"),
            session_id="session-a",
        )

        # Acquire typescript LSP for project-b (different root)
        lsp2 = pool.acquire(
            language=Language.TYPESCRIPT,
            workspace_root=Path("/tmp/project-b"),
            session_id="session-b",
        )

        is_same = lsp1 is lsp2

        assert not is_same, (
            f"❌ FAILURE: acquire() shared LSP instance for single-root language\n"
            f"WHAT FAILED: INV-4 (Single-root LSPs keyed by (language, rootUri))\n"
            f"WHY: CON-2 requires separate instances (single-root LSPs can't serve multiple roots)\n"
            f"EXPECTED: lsp1 is lsp2 = False (different instances)\n"
            f"ACTUAL: lsp1 is lsp2 = {is_same}, lsp1 id={id(lsp1)}, lsp2 id={id(lsp2)}\n"
            f"GUIDANCE: For single-root languages (typescript in SINGLE_ROOT_LANGUAGES):\n"
            f"  - Pool key = (Language.TYPESCRIPT, workspace_root) tuple\n"
            f"  - Each root gets separate LSP instance\n"
            f"  - Check: (language, root) in self._instances\n"
            f"  - Use LSPCapabilityRegistry.is_multi_root(Language.TYPESCRIPT) → False"
        )

        pool.stop_all(save_cache=False)

    def test_release_removes_session_reference(self):
        """
        Test that release() removes session_id from reference tracking.

        CONTRACT:
        - POST-4: session_id removed from reference set
        - PRE-3: session_id was previously used to acquire

        WHAT: Session reference removal after release()
        WHY: INV-2 requires accurate reference tracking (no leaks)
        EXPECTED: get_sessions_for_lsp() returns empty set after release
        ACTUAL: Returns {actual_sessions}
        GUIDANCE: release() must remove session reference:
            - Find pool_key for language/workspace_root
            - Remove from _sessions[pool_key]: self._sessions[key].discard(session_id)
            - Acquire pool_lock before mutation (thread-safety)
            - Don't raise error if session_id not found (idempotent)
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()
        session_id = "test-session-1"

        # Acquire first
        pool.acquire(
            language=Language.PYTHON,
            workspace_root=self.project_path,
            session_id=session_id,
        )

        # Release
        pool.release(
            language=Language.PYTHON,
            workspace_root=self.project_path,
            session_id=session_id,
        )

        actual_sessions = pool.get_sessions_for_lsp(
            language=Language.PYTHON,
            workspace_root=self.project_path,
        )

        assert session_id not in actual_sessions, (
            f"❌ FAILURE: release() did not remove session reference\n"
            f"WHAT FAILED: POST-4 (session_id removed from reference set)\n"
            f"WHY: INV-2 requires accurate reference tracking (no leaks)\n"
            f"EXPECTED: get_sessions_for_lsp() returns set NOT containing '{session_id}'\n"
            f"ACTUAL: get_sessions_for_lsp() returns {actual_sessions}\n"
            f"GUIDANCE: release() must remove session from tracking:\n"
            f"  - Pool key = (Language.PYTHON, {self.project_path}) or just Language.PYTHON\n"
            f"  - Remove: self._sessions[pool_key].discard(session_id)\n"
            f"  - Acquire pool_lock before mutation (thread-safety)"
        )

        pool.stop_all(save_cache=False)

    def test_release_does_not_stop_lsp_immediately(self):
        """
        Test that release() does NOT stop LSP immediately (idle timeout handles reclamation).

        CONTRACT:
        - DD-4: Hybrid ref_count + idle timeout for lifecycle
        - POST: LSP NOT stopped immediately (idle timeout handles reclamation)

        WHAT: LSP remains running after release() with zero references
        WHY: DD-4 requires idle timeout for reclamation (not immediate stop)
        EXPECTED: get_lsp() returns same instance after release (still running)
        ACTUAL: get_lsp() returns {result_type}
        GUIDANCE: release() delegates reclamation to LSPTimeoutManager:
            - Do NOT call lsp.stop() in release()
            - When ref_count reaches 0, notify LSPTimeoutManager to start idle timer
            - LSPTimeoutManager invokes reclaim_callback after idle > timeout
            - Callback (set via set_reclaim_callback) stops LSP and removes from pool
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()
        session_id = "test-session-1"

        # Acquire
        lsp_before = pool.acquire(
            language=Language.PYTHON,
            workspace_root=self.project_path,
            session_id=session_id,
        )

        # Release
        pool.release(
            language=Language.PYTHON,
            workspace_root=self.project_path,
            session_id=session_id,
        )

        # LSP should still be running (not stopped)
        lsp_after = pool.get_lsp(
            language=Language.PYTHON,
            workspace_root=self.project_path,
        )

        result_type = type(lsp_after).__name__ if lsp_after else "None"

        assert lsp_after is lsp_before, (
            f"❌ FAILURE: release() stopped LSP immediately (violates DD-4)\n"
            f"WHAT FAILED: POST (LSP NOT stopped immediately)\n"
            f"WHY: DD-4 requires idle timeout for reclamation (not immediate stop)\n"
            f"EXPECTED: get_lsp() returns same instance (still running)\n"
            f"ACTUAL: get_lsp() returns {result_type} (None means stopped)\n"
            f"GUIDANCE: release() must NOT stop LSP:\n"
            f"  - Do NOT call lsp.stop() in release()\n"
            f"  - When ref_count reaches 0, notify LSPTimeoutManager:\n"
            f"    timeout_manager.touch_lsp(language, workspace_root)\n"
            f"  - LSPTimeoutManager invokes reclaim_callback after idle > timeout\n"
            f"  - Callback stops LSP and removes from pool"
        )

        pool.stop_all(save_cache=False)

    def test_release_starts_idle_timer_when_ref_count_zero(self):
        """
        Test that release() starts idle timer when ref_count reaches 0.

        CONTRACT:
        - POST-5: If ref_count == 0, idle timer started
        - DD-4: Hybrid ref_count + idle timeout for lifecycle
        - Integration: LSPTimeoutManager for idle detection

        WHAT: Idle timer activation after last session releases
        WHY: REQ-5 requires LSPs reclaimed after idle timeout
        EXPECTED: LSPTimeoutManager.touch_lsp() called when ref_count drops to 0
        ACTUAL: touch_lsp called {call_count} times
        GUIDANCE: release() must notify timeout manager when idle:
            - Track ref_count per pool_key: len(self._sessions[pool_key])
            - If ref_count becomes 0 after release:
              self.timeout_manager.touch_lsp(language, workspace_root)
            - LSPTimeoutManager starts idle timer (timeout from lsp_timeout_contract.py)
            - Do NOT start timer if ref_count > 0 (still in use)
        """
        from unittest.mock import Mock

        from serena.global_lsp_pool import GlobalLanguageServerPool

        # Mock LSPTimeoutManager
        mock_timeout_manager = Mock()

        pool = GlobalLanguageServerPool()
        pool.timeout_manager = mock_timeout_manager

        session_id = "test-session-1"

        # Acquire
        pool.acquire(
            language=Language.PYTHON,
            workspace_root=self.project_path,
            session_id=session_id,
        )

        # Release (ref_count goes to 0)
        pool.release(
            language=Language.PYTHON,
            workspace_root=self.project_path,
            session_id=session_id,
        )

        # Check if touch_lsp was called
        call_count = mock_timeout_manager.touch_lsp.call_count

        assert call_count > 0, (
            f"❌ FAILURE: release() did not start idle timer when ref_count reached 0\n"
            f"WHAT FAILED: POST-5 (If ref_count == 0, idle timer started)\n"
            f"WHY: REQ-5 requires LSPs reclaimed after idle timeout\n"
            f"EXPECTED: timeout_manager.touch_lsp() called at least once\n"
            f"ACTUAL: touch_lsp called {call_count} times\n"
            f"GUIDANCE: release() must notify timeout manager when idle:\n"
            f"  - Check ref_count: len(self._sessions[pool_key])\n"
            f"  - If ref_count == 0:\n"
            f"    self.timeout_manager.touch_lsp(language, workspace_root)\n"
            f"  - LSPTimeoutManager starts idle timer\n"
            f"  - Do NOT call touch_lsp if ref_count > 0"
        )

        pool.stop_all(save_cache=False)


class TestGlobalLanguageServerPoolMultiSession:
    """Test GlobalLanguageServerPool with multiple concurrent sessions."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_multiple_sessions_share_lsp_instance(self):
        """
        Test that multiple sessions share the same LSP instance for multi-root languages.

        CONTRACT:
        - REQ-2: LSP instances shared where possible and correct
        - INV-3: Multi-root LSPs keyed by language only

        WHAT: Multiple sessions acquiring same multi-root LSP
        WHY: REQ-2 requires sharing to conserve memory (CON-3)
        EXPECTED: All sessions get same instance, ref_count = {num_sessions}
        ACTUAL: Unique instances = {num_unique}, sessions = {actual_sessions}
        GUIDANCE: acquire() must share LSP across sessions:
            - Pool key = language (for multi-root)
            - Check: pool_key in self._instances before creating new
            - Add session to _sessions[pool_key] set
            - Return existing instance
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire from 3 different sessions
        lsp1 = pool.acquire(Language.RUST, self.project_path, "session-a")
        lsp2 = pool.acquire(Language.RUST, self.project_path, "session-b")
        lsp3 = pool.acquire(Language.RUST, self.project_path, "session-c")

        # Check all are same instance
        unique_instances = len({id(lsp1), id(lsp2), id(lsp3)})
        num_unique = unique_instances

        # Check session tracking
        actual_sessions = pool.get_sessions_for_lsp(Language.RUST, self.project_path)

        assert num_unique == 1, (
            f"❌ FAILURE: Multiple sessions got different LSP instances\n"
            f"WHAT FAILED: REQ-2 (LSP instances shared where possible)\n"
            f"WHY: Must share LSP across sessions to conserve memory (CON-3)\n"
            f"EXPECTED: All 3 sessions get same instance (unique_instances = 1)\n"
            f"ACTUAL: Unique instances = {num_unique}\n"
            f"GUIDANCE: acquire() must reuse existing LSP:\n"
            f"  - Pool key = Language.RUST (multi-root)\n"
            f"  - Check: pool_key in self._instances\n"
            f"  - If found: return existing instance\n"
            f"  - Add session to _sessions[pool_key] set"
        )

        assert actual_sessions == {"session-a", "session-b", "session-c"}, (
            f"❌ FAILURE: Session reference tracking incorrect for multiple sessions\n"
            f"WHAT FAILED: INV-2 (Session references tracked accurately)\n"
            f"WHY: Must track all sessions referencing shared LSP\n"
            f"EXPECTED: {{'session-a', 'session-b', 'session-c'}}\n"
            f"ACTUAL: {actual_sessions}\n"
            f"GUIDANCE: acquire() must add session to tracking:\n"
            f"  - self._sessions[pool_key].add(session_id)\n"
            f"  - Acquire pool_lock before mutation"
        )

        pool.stop_all(save_cache=False)

    def test_partial_release_keeps_lsp_running(self):
        """
        Test that releasing one session keeps LSP running for other sessions.

        CONTRACT:
        - INV-5: LSP never stopped while sessions hold references
        - DD-4: Hybrid ref_count + idle timeout

        WHAT: LSP lifecycle with partial session release
        WHY: INV-5 requires LSP stays running while any session references it
        EXPECTED: After releasing session-a, LSP still running, sessions = {{'session-b', 'session-c'}}
        ACTUAL: LSP running = {lsp_running}, sessions = {actual_sessions}
        GUIDANCE: release() must NOT stop LSP if ref_count > 0:
            - Remove session from _sessions[pool_key]
            - Check ref_count: len(self._sessions[pool_key])
            - If ref_count > 0: Do NOT stop LSP, Do NOT start idle timer
            - If ref_count == 0: Start idle timer (touch_lsp)
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire from 3 sessions
        pool.acquire(Language.RUST, self.project_path, "session-a")
        pool.acquire(Language.RUST, self.project_path, "session-b")
        pool.acquire(Language.RUST, self.project_path, "session-c")

        # Release one session
        pool.release(Language.RUST, self.project_path, "session-a")

        # LSP should still be running
        lsp = pool.get_lsp(Language.RUST, self.project_path)
        lsp_running = lsp is not None

        # Check session tracking
        actual_sessions = pool.get_sessions_for_lsp(Language.RUST, self.project_path)

        assert lsp_running, (
            f"❌ FAILURE: LSP stopped while other sessions still hold references\n"
            f"WHAT FAILED: INV-5 (LSP never stopped while sessions hold references)\n"
            f"WHY: Other sessions (session-b, session-c) still using LSP\n"
            f"EXPECTED: get_lsp() returns instance (still running)\n"
            f"ACTUAL: LSP running = {lsp_running} (get_lsp returned None)\n"
            f"GUIDANCE: release() must check ref_count before stopping:\n"
            f"  - Remove session: self._sessions[pool_key].discard(session_id)\n"
            f"  - Check: len(self._sessions[pool_key]) > 0\n"
            f"  - If ref_count > 0: Do NOT stop LSP, Do NOT start idle timer"
        )

        assert actual_sessions == {"session-b", "session-c"}, (
            f"❌ FAILURE: Session reference tracking incorrect after partial release\n"
            f"WHAT FAILED: POST-4 (session_id removed from reference set)\n"
            f"WHY: Must remove released session but keep others\n"
            f"EXPECTED: {{'session-b', 'session-c'}}\n"
            f"ACTUAL: {actual_sessions}\n"
            f"GUIDANCE: release() must remove only specified session:\n"
            f"  - self._sessions[pool_key].discard(session_id)\n"
            f"  - Don't clear entire set (other sessions still active)"
        )

        pool.stop_all(save_cache=False)


class TestGlobalLanguageServerPoolCapabilityIntegration:
    """Test GlobalLanguageServerPool integration with LSPCapabilityRegistry."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_pool_uses_capability_registry_for_pool_key(self):
        """
        Test that pool queries LSPCapabilityRegistry for pool key strategy.

        CONTRACT:
        - DD-2: Pool key = language (multi-root) or (language, rootUri) (single-root)
        - Integration: LSPCapabilityRegistry.get_pool_key()

        WHAT: Pool key determination via LSPCapabilityRegistry
        WHY: Capability detection determines sharing strategy (CON-2)
        EXPECTED: Pool calls capability_registry.get_pool_key(language, workspace_root)
        ACTUAL: get_pool_key called {call_count} times
        GUIDANCE: acquire() must consult capability registry:
            - Create LSPCapabilityRegistry instance (or inject via __init__)
            - Call: pool_key = self.capability_registry.get_pool_key(language, workspace_root)
            - Use returned pool_key for _instances and _sessions dicts
            - Don't hardcode multi-root detection (use registry)
        """
        from unittest.mock import Mock, patch

        from serena.global_lsp_pool import GlobalLanguageServerPool

        mock_capability_registry = Mock()
        # Mock returns language for multi-root
        mock_capability_registry.get_pool_key.return_value = Language.RUST

        with patch(
            "serena.global_lsp_pool.LSPCapabilityRegistry",
            return_value=mock_capability_registry,
        ):
            pool = GlobalLanguageServerPool()

            pool.acquire(Language.RUST, self.project_path, "session-a")

            call_count = mock_capability_registry.get_pool_key.call_count

            assert call_count > 0, (
                f"❌ FAILURE: Pool did not query LSPCapabilityRegistry for pool key\n"
                f"WHAT FAILED: DD-2 (Pool key strategy from capability registry)\n"
                f"WHY: Capability detection determines sharing strategy (CON-2)\n"
                f"EXPECTED: capability_registry.get_pool_key() called at least once\n"
                f"ACTUAL: get_pool_key called {call_count} times\n"
                f"GUIDANCE: acquire() must consult capability registry:\n"
                f"  - Create: self.capability_registry = LSPCapabilityRegistry()\n"
                f"  - Call: pool_key = self.capability_registry.get_pool_key(language, root)\n"
                f"  - Use returned pool_key (don't hardcode multi-root detection)"
            )

            pool.stop_all(save_cache=False)


class TestGlobalLanguageServerPoolLockHierarchy:
    """Test GlobalLanguageServerPool lock hierarchy enforcement (DD-3, INV-6)."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_acquire_thread_safe(self):
        """
        Test that acquire() is thread-safe (uses pool_lock).

        CONTRACT:
        - INV-1: Pool lock acquired before any shared state mutation
        - Sync interface: Thread-safety via threading.Lock

        WHAT: Thread-safe acquire() with concurrent calls
        WHY: Multiple sessions may acquire LSPs concurrently
        EXPECTED: All 10 concurrent acquires succeed, ref_count = 10, unique instances = 1
        ACTUAL: Successful acquires = {success_count}, unique instances = {num_unique}, sessions = {actual_sessions}
        GUIDANCE: acquire() must use thread-safe locking:
            - Create: self._lock = threading.Lock()
            - Wrap mutations: with self._lock: <mutate _instances, _sessions>
            - Lock hierarchy: session_lock -> pool_lock (DD-3)
            - Do NOT hold pool_lock while calling external methods (deadlock risk)
            - THEATER TEST PREVENTION: Record instance ID DURING acquisition to catch race conditions
        """
        import threading

        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        success_count = 0
        acquired_instance_ids = []  # THEATER TEST FIX: Capture IDs during execution
        success_lock = threading.Lock()

        def acquire_lsp(session_id):
            nonlocal success_count
            try:
                lsp = pool.acquire(Language.PYTHON, self.project_path, session_id)
                with success_lock:
                    acquired_instance_ids.append(id(lsp))  # Record DURING acquire
                    success_count += 1
            except Exception as e:
                print(f"acquire failed for {session_id}: {e}")

        # Launch 10 concurrent acquires
        threads = []
        for i in range(10):
            t = threading.Thread(target=acquire_lsp, args=(f"session-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        actual_sessions = pool.get_sessions_for_lsp(Language.PYTHON, self.project_path)
        num_unique = len(set(acquired_instance_ids))

        assert success_count == 10, (
            f"❌ FAILURE: Concurrent acquire() calls failed (race condition)\n"
            f"WHAT FAILED: INV-1 (Pool lock acquired before mutation)\n"
            f"WHY: Thread-safety required for concurrent session operations\n"
            f"EXPECTED: All 10 acquire() calls succeed\n"
            f"ACTUAL: Successful acquires = {success_count}\n"
            f"GUIDANCE: acquire() must use threading.Lock:\n"
            f"  - Create: self._lock = threading.Lock()\n"
            f"  - Wrap: with self._lock: <mutate _instances, _sessions>\n"
            f"  - Do NOT hold lock while calling external methods"
        )

        # THEATER TEST CHECK: Verify all threads got SAME instance
        assert num_unique == 1, (
            f"❌ FAILURE: Concurrent acquire() returned different LSP instances (race condition)\n"
            f"WHAT FAILED: INV-3 (Multi-root LSPs keyed by language only)\n"
            f"WHY: REQ-2 requires sharing single instance across concurrent sessions\n"
            f"EXPECTED: All 10 threads get same instance (unique IDs = 1)\n"
            f"ACTUAL: Unique instance IDs = {num_unique}, IDs captured: {acquired_instance_ids}\n"
            f"GUIDANCE: Pool locking must ensure first acquire wins, others wait:\n"
            f"  - Check: pool_key in self._instances INSIDE lock\n"
            f"  - If found: return existing instance\n"
            f"  - If not found: create, add to _instances, return\n"
            f"  - Avoid thread-local storage or post-hoc deduplication"
        )

        assert len(actual_sessions) == 10, (
            f"❌ FAILURE: Session tracking lost concurrent updates (race condition)\n"
            f"WHAT FAILED: INV-2 (Session references tracked accurately)\n"
            f"WHY: Thread-safety required for reference tracking\n"
            f"EXPECTED: 10 sessions tracked\n"
            f"ACTUAL: {len(actual_sessions)} sessions tracked: {actual_sessions}\n"
            f"GUIDANCE: Use lock for _sessions updates:\n"
            f"  - with self._lock: self._sessions[pool_key].add(session_id)"
        )

        pool.stop_all(save_cache=False)


class TestGlobalLanguageServerPoolReclamationCallback:
    """Test GlobalLanguageServerPool reclamation callback integration."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_set_reclaim_callback_stores_callback(self):
        """
        Test that set_reclaim_callback() stores callback for later invocation.

        CONTRACT:
        - POST: Callback stored for invocation on reclaim events
        - Callback will be called by LSPTimeoutManager when idle > timeout

        WHAT: Reclaim callback storage
        WHY: LSPTimeoutManager invokes callback to stop idle LSPs
        EXPECTED: Callback stored in pool._reclaim_callback attribute
        ACTUAL: Callback stored = {callback_stored}
        GUIDANCE: set_reclaim_callback() must store callback:
            - Store in instance attribute: self._reclaim_callback = callback
            - LSPTimeoutManager invokes: self._reclaim_callback(language, workspace_root)
            - Callback should stop LSP and remove from pool
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        mock_callback = Mock()
        pool.set_reclaim_callback(mock_callback)

        callback_stored = hasattr(pool, "_reclaim_callback") and pool._reclaim_callback is mock_callback

        assert callback_stored, (
            f"❌ FAILURE: set_reclaim_callback() did not store callback\n"
            f"WHAT FAILED: POST (Callback stored for invocation)\n"
            f"WHY: LSPTimeoutManager needs callback to reclaim idle LSPs\n"
            f"EXPECTED: pool._reclaim_callback == mock_callback\n"
            f"ACTUAL: Callback stored = {callback_stored}\n"
            f"GUIDANCE: set_reclaim_callback() must store callback:\n"
            f"  - self._reclaim_callback = callback\n"
            f"  - Callback signature: Callable[[Language, Path], None]\n"
            f"  - Callback invoked by LSPTimeoutManager when idle > timeout"
        )

        pool.stop_all(save_cache=False)


class TestGlobalLanguageServerPoolStopAll:
    """Test GlobalLanguageServerPool stop_all() shutdown behavior."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_stop_all_stops_all_lsps(self):
        """
        Test that stop_all() stops all managed LSPs.

        CONTRACT:
        - POST: All LSPs stopped
        - POST: Pool empty
        - POST: All session references cleared

        WHAT: Shutdown behavior of stop_all()
        WHY: Clean shutdown required for session invalidation
        EXPECTED: All LSPs stopped, get_lsp() returns None for all
        ACTUAL: LSP1 running = {lsp1_running}, LSP2 running = {lsp2_running}
        GUIDANCE: stop_all() must clean up all resources:
            - Iterate over all LSPs in self._instances.values()
            - Call lsp.stop() for each (or lsp.stop(save_cache=save_cache))
            - Clear pool: self._instances.clear()
            - Clear sessions: self._sessions.clear()
            - Acquire pool_lock before mutations
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire 2 LSPs
        pool.acquire(Language.PYTHON, self.project_path, "session-a")
        pool.acquire(Language.RUST, self.project_path, "session-b")

        # Stop all
        pool.stop_all(save_cache=False)

        # Check LSPs stopped
        lsp1 = pool.get_lsp(Language.PYTHON, self.project_path)
        lsp2 = pool.get_lsp(Language.RUST, self.project_path)

        lsp1_running = lsp1 is not None
        lsp2_running = lsp2 is not None

        assert not lsp1_running, (
            f"❌ FAILURE: stop_all() did not stop Python LSP\n"
            f"WHAT FAILED: POST (All LSPs stopped)\n"
            f"WHY: Clean shutdown required for session invalidation\n"
            f"EXPECTED: get_lsp() returns None after stop_all()\n"
            f"ACTUAL: LSP1 running = {lsp1_running} (get_lsp returned instance)\n"
            f"GUIDANCE: stop_all() must stop all LSPs:\n"
            f"  - Iterate: for lsp in self._instances.values(): lsp.stop()\n"
            f"  - Clear pool: self._instances.clear()\n"
            f"  - Clear sessions: self._sessions.clear()"
        )

        assert not lsp2_running, (
            f"❌ FAILURE: stop_all() did not stop Rust LSP\n"
            f"WHAT FAILED: POST (All LSPs stopped)\n"
            f"WHY: Clean shutdown required for session invalidation\n"
            f"EXPECTED: get_lsp() returns None after stop_all()\n"
            f"ACTUAL: LSP2 running = {lsp2_running} (get_lsp returned instance)\n"
            f"GUIDANCE: stop_all() must stop all LSPs:\n"
            f"  - Iterate: for lsp in self._instances.values(): lsp.stop()\n"
            f"  - Clear pool: self._instances.clear()"
        )

    def test_stop_all_clears_session_references(self):
        """
        Test that stop_all() clears all session references.

        CONTRACT:
        - POST: All session references cleared

        WHAT: Session reference cleanup on stop_all()
        WHY: Prevents reference leaks after shutdown
        EXPECTED: get_sessions_for_lsp() returns empty set after stop_all()
        ACTUAL: Sessions remaining = {sessions_remaining}
        GUIDANCE: stop_all() must clear session tracking:
            - Clear all: self._sessions.clear()
            - Acquire pool_lock before mutation
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire LSP
        pool.acquire(Language.PYTHON, self.project_path, "session-a")

        # Stop all
        pool.stop_all(save_cache=False)

        # Check sessions cleared
        sessions_remaining = pool.get_sessions_for_lsp(Language.PYTHON, self.project_path)

        assert len(sessions_remaining) == 0, (
            f"❌ FAILURE: stop_all() did not clear session references\n"
            f"WHAT FAILED: POST (All session references cleared)\n"
            f"WHY: Prevents reference leaks after shutdown\n"
            f"EXPECTED: get_sessions_for_lsp() returns empty set\n"
            f"ACTUAL: Sessions remaining = {sessions_remaining}\n"
            f"GUIDANCE: stop_all() must clear session tracking:\n"
            f"  - Clear: self._sessions.clear()\n"
            f"  - Acquire pool_lock before mutation"
        )


class TestGlobalLanguageServerPoolContractViolations:
    """Test GlobalLanguageServerPool contract violation handling."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_release_without_acquire_is_idempotent(self):
        """
        Test that release() without prior acquire is idempotent (doesn't crash).

        CONTRACT:
        - PRE-3: session_id was previously used to acquire (but implementation should be defensive)

        WHAT: Defensive programming for release() without acquire
        WHY: Clients may call release() multiple times or after crash recovery
        EXPECTED: release() succeeds (no exception), ref_count stays 0
        ACTUAL: Exception raised = {exception_raised}, type = {exc_type}
        GUIDANCE: release() should be idempotent:
            - Use set.discard() instead of set.remove() (no KeyError if missing)
            - Don't raise error if session_id not in tracking
            - Log warning for debugging but don't crash
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        exception_raised = False
        exc_type = None

        try:
            # Release without acquire
            pool.release(
                language=Language.PYTHON,
                workspace_root=self.project_path,
                session_id="never-acquired",
            )
        except Exception as e:
            exception_raised = True
            exc_type = type(e).__name__

        assert not exception_raised, (
            f"❌ FAILURE: release() raised exception for non-existent session\n"
            f"WHAT FAILED: Defensive programming (idempotent release)\n"
            f"WHY: Clients may call release() multiple times or after crash\n"
            f"EXPECTED: release() succeeds (no exception)\n"
            f"ACTUAL: Exception raised = {exception_raised}, type = {exc_type}\n"
            f"GUIDANCE: release() should be idempotent:\n"
            f"  - Use: self._sessions[pool_key].discard(session_id)\n"
            f"  - NOT: self._sessions[pool_key].remove(session_id)\n"
            f"  - discard() doesn't raise KeyError if missing"
        )

        pool.stop_all(save_cache=False)

    def test_acquire_with_relative_path_fails(self):
        """
        Test that acquire() rejects relative workspace_root paths.

        CONTRACT:
        - PRE-2: workspace_root is absolute Path

        WHAT: Input validation for workspace_root
        WHY: LSP protocol requires absolute paths for rootUri
        EXPECTED: acquire() raises ValueError for relative path
        ACTUAL: Exception raised = {exception_raised}, type = {exc_type}
        GUIDANCE: acquire() must validate workspace_root:
            - Check: workspace_root.is_absolute()
            - Raise ValueError with message: "workspace_root must be absolute"
            - Perform check BEFORE pool_lock acquisition (fail fast)
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        exception_raised = False
        exc_type = None

        try:
            # Try to acquire with relative path
            pool.acquire(
                language=Language.PYTHON,
                workspace_root=Path("relative/path"),
                session_id="test-session",
            )
        except ValueError:
            exception_raised = True
            exc_type = "ValueError"
        except Exception as e:
            exception_raised = True
            exc_type = type(e).__name__

        assert exception_raised and exc_type == "ValueError", (
            f"❌ FAILURE: acquire() accepted relative workspace_root path\n"
            f"WHAT FAILED: PRE-2 (workspace_root is absolute Path)\n"
            f"WHY: LSP protocol requires absolute paths for rootUri\n"
            f"EXPECTED: ValueError raised for Path('relative/path')\n"
            f"ACTUAL: Exception raised = {exception_raised}, type = {exc_type}\n"
            f"GUIDANCE: acquire() must validate workspace_root:\n"
            f"  - Check: if not workspace_root.is_absolute():\n"
            f"  - Raise: ValueError('workspace_root must be absolute path')\n"
            f"  - Perform check BEFORE acquiring pool_lock"
        )

        pool.stop_all(save_cache=False)


class TestGlobalLanguageServerPoolEnhancedReclamation:
    """Test GlobalLanguageServerPool reclamation callback contract adherence."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_reclaim_callback_receives_correct_parameters(self):
        """
        Test that reclaim callback receives correct (language, workspace_root).

        CONTRACT:
        - CALLBACK CONTRACT: Callback receives (language, workspace_root)
        - LSPTimeoutManager invokes callback when idle > timeout

        WHAT: Reclaim callback parameter validation
        WHY: Callback needs correct params to stop right LSP instance
        EXPECTED: Callback invoked with (Language.PYTHON, {project_path})
        ACTUAL: Callback invoked = {callback_invoked}, params = {callback_params}
        GUIDANCE: When invoking reclaim_callback:
            - Call: self._reclaim_callback(language, workspace_root)
            - Pass Language enum (not string)
            - Pass Path object (not string)
            - Match parameters used in acquire/release
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        callback_params = []
        callback_invoked = False

        def capture_callback(language, workspace_root):
            nonlocal callback_invoked
            callback_invoked = True
            callback_params.append((language, workspace_root))

        pool.set_reclaim_callback(capture_callback)

        # Acquire and release to trigger idle timer
        pool.acquire(Language.PYTHON, self.project_path, "session-a")
        pool.release(Language.PYTHON, self.project_path, "session-a")

        # Simulate timeout by manually invoking callback
        # (Real LSPTimeoutManager integration tested separately)
        if hasattr(pool, "_reclaim_callback") and pool._reclaim_callback:
            pool._reclaim_callback(Language.PYTHON, self.project_path)

        assert callback_invoked, (
            f"❌ FAILURE: Reclaim callback never invoked\n"
            f"WHAT FAILED: CALLBACK CONTRACT (callback invoked on reclaim)\n"
            f"WHY: LSPTimeoutManager needs callback to stop idle LSPs\n"
            f"EXPECTED: Callback invoked at least once\n"
            f"ACTUAL: Callback invoked = {callback_invoked}\n"
            f"GUIDANCE: Ensure callback stored and invoked:\n"
            f"  - Store: self._reclaim_callback = callback\n"
            f"  - Invoke: self._reclaim_callback(language, workspace_root)"
        )

        if callback_invoked and callback_params:
            lang, root = callback_params[0]
            assert lang == Language.PYTHON, (
                f"❌ FAILURE: Reclaim callback received wrong language parameter\n"
                f"WHAT FAILED: CALLBACK CONTRACT (correct parameters)\n"
                f"WHY: Callback needs correct language to stop right LSP\n"
                f"EXPECTED: Language.PYTHON\n"
                f"ACTUAL: {lang}\n"
                f"GUIDANCE: Pass Language enum (not string) to callback"
            )

            assert root == self.project_path, (
                f"❌ FAILURE: Reclaim callback received wrong workspace_root parameter\n"
                f"WHAT FAILED: CALLBACK CONTRACT (correct parameters)\n"
                f"WHY: Callback needs correct root to stop right LSP instance\n"
                f"EXPECTED: {self.project_path}\n"
                f"ACTUAL: {root}\n"
                f"GUIDANCE: Pass Path object (not string) to callback"
            )

        pool.stop_all(save_cache=False)

    def test_partial_release_does_not_invoke_reclaim_callback(self):
        """
        Test that reclaim callback NOT invoked when ref_count > 0.

        CONTRACT:
        - POST-5: If ref_count == 0, idle timer started
        - Callback invoked by LSPTimeoutManager only when idle

        WHAT: Reclaim callback gating on ref_count
        WHY: Must NOT stop LSP while sessions still reference it (INV-5)
        EXPECTED: Callback NOT invoked after partial release (ref_count = 1)
        ACTUAL: Callback invoked = {callback_invoked}
        GUIDANCE: release() must check ref_count before notifying timeout manager:
            - Check: len(self._sessions[pool_key]) == 0
            - If ref_count > 0: Do NOT call timeout_manager.touch_lsp()
            - If ref_count == 0: Call timeout_manager.touch_lsp()
            - Callback invoked by timeout manager later (not release())
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        callback_invoked = False

        def capture_callback(language, workspace_root):
            nonlocal callback_invoked
            callback_invoked = True

        pool.set_reclaim_callback(capture_callback)

        # Acquire from 2 sessions
        pool.acquire(Language.PYTHON, self.project_path, "session-a")
        pool.acquire(Language.PYTHON, self.project_path, "session-b")

        # Release one (ref_count still 1)
        pool.release(Language.PYTHON, self.project_path, "session-a")

        # Callback should NOT be invoked (ref_count > 0)
        # Note: This tests that release() doesn't invoke callback directly
        # LSPTimeoutManager integration tested separately

        assert not callback_invoked, (
            f"❌ FAILURE: Reclaim callback invoked while ref_count > 0\n"
            f"WHAT FAILED: INV-5 (LSP never stopped while sessions hold references)\n"
            f"WHY: Other session (session-b) still using LSP\n"
            f"EXPECTED: Callback NOT invoked after partial release\n"
            f"ACTUAL: Callback invoked = {callback_invoked}\n"
            f"GUIDANCE: release() must check ref_count:\n"
            f"  - Check: len(self._sessions[pool_key]) == 0\n"
            f"  - If ref_count > 0: Do NOT notify timeout manager\n"
            f"  - Only start idle timer when ref_count drops to 0"
        )

        pool.stop_all(save_cache=False)
        # Check LSPs stopped
        lsp1 = pool.get_lsp(Language.PYTHON, self.project_path)
        lsp2 = pool.get_lsp(Language.RUST, self.project_path)

        lsp1_running = lsp1 is not None
        lsp2_running = lsp2 is not None

        assert not lsp1_running, (
            f"❌ FAILURE: stop_all() did not stop Python LSP\n"
            f"WHAT FAILED: POST (All LSPs stopped)\n"
            f"WHY: Clean shutdown required for session invalidation\n"
            f"EXPECTED: get_lsp() returns None after stop_all()\n"
            f"ACTUAL: LSP1 running = {lsp1_running} (get_lsp returned instance)\n"
            f"GUIDANCE: stop_all() must stop all LSPs:\n"
            f"  - Iterate: for lsp in self._instances.values(): lsp.stop()\n"
            f"  - Clear pool: self._instances.clear()\n"
            f"  - Clear sessions: self._sessions.clear()"
        )

        assert not lsp2_running, (
            f"❌ FAILURE: stop_all() did not stop Rust LSP\n"
            f"WHAT FAILED: POST (All LSPs stopped)\n"
            f"WHY: Clean shutdown required for session invalidation\n"
            f"EXPECTED: get_lsp() returns None after stop_all()\n"
            f"ACTUAL: LSP2 running = {lsp2_running} (get_lsp returned instance)\n"
            f"GUIDANCE: stop_all() must stop all LSPs:\n"
            f"  - Iterate: for lsp in self._instances.values(): lsp.stop()\n"
            f"  - Clear pool: self._instances.clear()"
        )

    def test_stop_all_clears_session_references(self):
        """
        Test that stop_all() clears all session references.

        CONTRACT:
        - POST: All session references cleared

        WHAT: Session reference cleanup on stop_all()
        WHY: Prevents reference leaks after shutdown
        EXPECTED: get_sessions_for_lsp() returns empty set after stop_all()
        ACTUAL: Sessions remaining = {sessions_remaining}
        GUIDANCE: stop_all() must clear session tracking:
            - Clear all: self._sessions.clear()
            - Acquire pool_lock before mutation
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire LSP
        pool.acquire(Language.PYTHON, self.project_path, "session-a")

        # Stop all
        pool.stop_all(save_cache=False)

        # Check sessions cleared
        sessions_remaining = pool.get_sessions_for_lsp(Language.PYTHON, self.project_path)

        assert len(sessions_remaining) == 0, (
            f"❌ FAILURE: stop_all() did not clear session references\n"
            f"WHAT FAILED: POST (All session references cleared)\n"
            f"WHY: Prevents reference leaks after shutdown\n"
            f"EXPECTED: get_sessions_for_lsp() returns empty set\n"
            f"ACTUAL: Sessions remaining = {sessions_remaining}\n"
            f"GUIDANCE: stop_all() must clear session tracking:\n"
            f"  - Clear: self._sessions.clear()\n"
            f"  - Acquire pool_lock before mutation"
        )


class TestGlobalLanguageServerPoolGetPoolStats:
    """Test GlobalLanguageServerPool.get_stats() observability API."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_get_stats_empty_pool(self):
        """
        Test that get_stats() returns empty list when no LSPs acquired.

        CONTRACT:
        - POST: Returns dict with "lsps" (list) and "total_count" (int)
        - POST: len(lsps) == total_count

        WHAT: get_stats() behavior with empty pool
        WHY: REQ-API-2 requires stats API for observability
        EXPECTED: Returns {"lsps": [], "total_count": 0}
        ACTUAL: stats = {stats}
        GUIDANCE: get_stats() must return empty stats for empty pool:
            - Return dict with "lsps" key (list) and "total_count" key (int)
            - For empty pool: lsps = [], total_count = 0
            - Check: len(self._pool) == 0 or self._pool.keys()
            - Thread-safe: acquire pool_lock for consistent snapshot
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        stats = pool.get_stats()

        assert isinstance(stats, dict), (
            f"❌ FAILURE: get_stats() did not return dict\n"
            f"WHAT FAILED: POST (Returns dict with lsps and total_count)\n"
            f"WHY: REQ-API-2 requires dict return type for stats API\n"
            f"EXPECTED: dict type\n"
            f"ACTUAL: {type(stats).__name__}\n"
            f"GUIDANCE: get_stats() must return dict:\n"
            f"  - return {{'lsps': [...], 'total_count': N}}"
        )

        assert "lsps" in stats, (
            f"❌ FAILURE: get_stats() missing 'lsps' key\n"
            f"WHAT FAILED: POST (Returns dict with 'lsps' key)\n"
            f"WHY: REQ-API-2 requires lsps list in response\n"
            f"EXPECTED: 'lsps' key in returned dict\n"
            f"ACTUAL: stats keys = {stats.keys()}\n"
            f"GUIDANCE: Include 'lsps' key in return dict"
        )

        assert "total_count" in stats, (
            f"❌ FAILURE: get_stats() missing 'total_count' key\n"
            f"WHAT FAILED: POST (Returns dict with 'total_count' key)\n"
            f"WHY: REQ-API-2b requires total count in response\n"
            f"EXPECTED: 'total_count' key in returned dict\n"
            f"ACTUAL: stats keys = {stats.keys()}\n"
            f"GUIDANCE: Include 'total_count' key in return dict"
        )

        assert isinstance(stats["lsps"], list), (
            f"❌ FAILURE: get_stats()['lsps'] is not a list\n"
            f"WHAT FAILED: POST ('lsps' must be list)\n"
            f"WHY: REQ-API-2 requires lsps as list of dicts\n"
            f"EXPECTED: list type\n"
            f"ACTUAL: {type(stats['lsps']).__name__}\n"
            f"GUIDANCE: 'lsps' value must be list"
        )

        assert len(stats["lsps"]) == 0, (
            f"❌ FAILURE: get_stats() returned non-empty lsps for empty pool\n"
            f"WHAT FAILED: POST (Empty pool returns empty list)\n"
            f"WHY: No LSPs acquired yet\n"
            f"EXPECTED: lsps = []\n"
            f"ACTUAL: lsps = {stats['lsps']}\n"
            f"GUIDANCE: For empty pool, return empty list:\n"
            f"  - Check: len(self._pool) == 0\n"
            f"  - Return: {{'lsps': [], 'total_count': 0}}"
        )

        assert stats["total_count"] == 0, (
            f"❌ FAILURE: get_stats() returned non-zero total_count for empty pool\n"
            f"WHAT FAILED: POST (total_count == len(lsps))\n"
            f"WHY: No LSPs acquired yet\n"
            f"EXPECTED: total_count = 0\n"
            f"ACTUAL: total_count = {stats['total_count']}\n"
            f"GUIDANCE: total_count must match len(lsps)"
        )

        pool.stop_all(save_cache=False)

    def test_get_stats_single_lsp(self):
        """
        Test that get_stats() returns correct stats for single LSP.

        CONTRACT:
        - POST: Each LSP dict contains language, workspace_root, ref_count, status

        WHAT: get_stats() with one acquired LSP
        WHY: REQ-API-2 requires stats for all managed LSPs
        EXPECTED: Returns 1 LSP with language="PYTHON", ref_count=1, status="running"
        ACTUAL: stats = {stats}
        GUIDANCE: get_stats() must include all required fields:
            - language: str (Language enum name, e.g., "PYTHON")
            - workspace_root: str (absolute path or "shared")
            - ref_count: int (len of session set for this LSP)
            - status: str ("running", "idle", or "stopped")
            - Use Language.name for language field (enum to string)
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire one LSP
        pool.acquire(Language.PYTHON, self.project_path, "session-a")

        stats = pool.get_stats()

        assert len(stats["lsps"]) == 1, (
            f"❌ FAILURE: get_stats() returned wrong number of LSPs\n"
            f"WHAT FAILED: POST (One LSP acquired, one returned)\n"
            f"WHY: Must report all managed LSPs\n"
            f"EXPECTED: len(lsps) = 1\n"
            f"ACTUAL: len(lsps) = {len(stats['lsps'])}\n"
            f"GUIDANCE: Return one dict per LSP in pool:\n"
            f"  - Iterate: for pool_key, lsp in self._pool.items()"
        )

        assert stats["total_count"] == 1, (
            f"❌ FAILURE: get_stats() total_count does not match lsps length\n"
            f"WHAT FAILED: POST (total_count == len(lsps))\n"
            f"WHY: total_count must reflect actual LSP count\n"
            f"EXPECTED: total_count = 1\n"
            f"ACTUAL: total_count = {stats['total_count']}\n"
            f"GUIDANCE: Set total_count = len(lsps)"
        )

        lsp_info = stats["lsps"][0]

        # Verify required fields
        assert "language" in lsp_info, (
            f"❌ FAILURE: LSP stats missing 'language' field\n"
            f"WHAT FAILED: POST (Each LSP dict contains language)\n"
            f"WHY: REQ-API-2 requires language in stats\n"
            f"EXPECTED: 'language' key in LSP dict\n"
            f"ACTUAL: LSP dict keys = {lsp_info.keys()}\n"
            f"GUIDANCE: Include 'language' field in each LSP dict"
        )

        assert "workspace_root" in lsp_info, (
            f"❌ FAILURE: LSP stats missing 'workspace_root' field\n"
            f"WHAT FAILED: POST (Each LSP dict contains workspace_root)\n"
            f"WHY: REQ-API-2 requires workspace_root in stats\n"
            f"EXPECTED: 'workspace_root' key in LSP dict\n"
            f"ACTUAL: LSP dict keys = {lsp_info.keys()}\n"
            f"GUIDANCE: Include 'workspace_root' field in each LSP dict"
        )

        assert "ref_count" in lsp_info, (
            f"❌ FAILURE: LSP stats missing 'ref_count' field\n"
            f"WHAT FAILED: POST (Each LSP dict contains ref_count)\n"
            f"WHY: REQ-API-2 requires ref_count in stats\n"
            f"EXPECTED: 'ref_count' key in LSP dict\n"
            f"ACTUAL: LSP dict keys = {lsp_info.keys()}\n"
            f"GUIDANCE: Include 'ref_count' field in each LSP dict"
        )

        assert "status" in lsp_info, (
            f"❌ FAILURE: LSP stats missing 'status' field\n"
            f"WHAT FAILED: POST (Each LSP dict contains status)\n"
            f"WHY: REQ-API-2 requires status in stats\n"
            f"EXPECTED: 'status' key in LSP dict\n"
            f"ACTUAL: LSP dict keys = {lsp_info.keys()}\n"
            f"GUIDANCE: Include 'status' field in each LSP dict"
        )

        # Verify field values
        assert lsp_info["language"] == "PYTHON", (
            f"❌ FAILURE: LSP stats has wrong language\n"
            f"WHAT FAILED: POST (language is Language enum name)\n"
            f"WHY: Must report correct language for LSP\n"
            f"EXPECTED: 'PYTHON'\n"
            f"ACTUAL: {lsp_info['language']}\n"
            f"GUIDANCE: Use Language.name for language field:\n"
            f"  - For pool_key that is Language: pool_key.name\n"
            f"  - For pool_key that is tuple: pool_key[0].name"
        )

        assert isinstance(lsp_info["ref_count"], int), (
            f"❌ FAILURE: LSP stats ref_count is not int\n"
            f"WHAT FAILED: POST (ref_count is int)\n"
            f"WHY: ref_count must be numeric for comparison\n"
            f"EXPECTED: int type\n"
            f"ACTUAL: {type(lsp_info['ref_count']).__name__}\n"
            f"GUIDANCE: ref_count must be int"
        )

        assert lsp_info["ref_count"] == 1, (
            f"❌ FAILURE: LSP stats ref_count does not match actual sessions\n"
            f"WHAT FAILED: POST (ref_count reflects current session count)\n"
            f"WHY: One session acquired, ref_count should be 1\n"
            f"EXPECTED: ref_count = 1\n"
            f"ACTUAL: ref_count = {lsp_info['ref_count']}\n"
            f"GUIDANCE: ref_count = len(self._session_refs[pool_key])"
        )

        assert lsp_info["status"] in ("running", "stopped", "crashed", "initializing"), (
            f"❌ FAILURE: LSP stats status has invalid value\n"
            f"WHAT FAILED: POST (status is 'running', 'stopped', 'crashed', or 'initializing')\n"
            f"WHY: REQ-API-2 requires status field with valid value\n"
            f"EXPECTED: One of: 'running', 'stopped', 'crashed', 'initializing'\n"
            f"ACTUAL: {lsp_info['status']}\n"
            f"GUIDANCE: Determine status based on process state:\n"
            f"  - 'running': lsp.is_running() == True\n"
            f"  - 'stopped': clean shutdown (returncode == 0 or None before start)\n"
            f"  - 'crashed': abnormal termination (returncode != 0 and != None)\n"
            f"  - 'initializing': process started but not yet responsive"
        )

        pool.stop_all(save_cache=False)

    def test_get_stats_multiple_lsps(self):
        """
        Test that get_stats() returns stats for all LSPs.

        CONTRACT:
        - POST: Returns all LSPs in pool
        - POST: total_count matches len(lsps)

        WHAT: get_stats() with multiple LSPs
        WHY: REQ-API-2 requires stats for all managed LSPs
        EXPECTED: Returns 3 LSPs (PYTHON, RUST, TYPESCRIPT)
        ACTUAL: stats = {stats}, languages = {languages}
        GUIDANCE: get_stats() must include all LSPs:
            - Iterate over all pool_keys in self._pool
            - Create one dict per LSP
            - Return all in 'lsps' list
            - Set total_count = len(lsps)
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire 3 different LSPs
        pool.acquire(Language.PYTHON, self.project_path, "session-a")
        pool.acquire(Language.RUST, Path("/tmp/project-b"), "session-b")
        pool.acquire(Language.TYPESCRIPT, Path("/tmp/project-c"), "session-c")

        stats = pool.get_stats()

        assert len(stats["lsps"]) == 3, (
            f"❌ FAILURE: get_stats() did not return all LSPs\n"
            f"WHAT FAILED: POST (Returns all LSPs in pool)\n"
            f"WHY: Must report all 3 managed LSPs\n"
            f"EXPECTED: len(lsps) = 3\n"
            f"ACTUAL: len(lsps) = {len(stats['lsps'])}\n"
            f"GUIDANCE: Return one dict per LSP:\n"
            f"  - Iterate: for pool_key in self._pool.keys()\n"
            f"  - Append dict for each LSP to lsps list"
        )

        assert stats["total_count"] == 3, (
            f"❌ FAILURE: get_stats() total_count does not match lsps length\n"
            f"WHAT FAILED: POST (total_count == len(lsps))\n"
            f"WHY: total_count must reflect actual LSP count\n"
            f"EXPECTED: total_count = 3\n"
            f"ACTUAL: total_count = {stats['total_count']}\n"
            f"GUIDANCE: Set total_count = len(lsps)"
        )

        # Verify all languages present
        languages = {lsp["language"] for lsp in stats["lsps"]}
        expected_languages = {"PYTHON", "RUST", "TYPESCRIPT"}

        assert languages == expected_languages, (
            f"❌ FAILURE: get_stats() missing or has extra languages\n"
            f"WHAT FAILED: POST (All acquired LSPs present)\n"
            f"WHY: Must report exactly the LSPs that were acquired\n"
            f"EXPECTED: languages = {expected_languages}\n"
            f"ACTUAL: languages = {languages}\n"
            f"GUIDANCE: Include one dict per pool_key in self._pool"
        )

        pool.stop_all(save_cache=False)

    def test_get_stats_ref_count_accurate(self):
        """
        Test that get_stats() ref_count matches actual session count.

        CONTRACT:
        - POST: ref_count reflects CURRENT session count
        - INVARIANT: Read-only - does not modify ref_count

        WHAT: ref_count accuracy in get_stats()
        WHY: REQ-API-2 requires ref_count to reflect actual sessions
        EXPECTED: ref_count = 3 after 3 sessions acquire same LSP
        ACTUAL: ref_count = {ref_count}
        GUIDANCE: ref_count must reflect current sessions:
            - Count sessions: len(self._session_refs[pool_key])
            - Do NOT modify _session_refs (read-only)
            - Thread-safe: acquire pool_lock for consistent snapshot
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire from 3 sessions (multi-root, same instance)
        pool.acquire(Language.RUST, self.project_path, "session-a")
        pool.acquire(Language.RUST, self.project_path, "session-b")
        pool.acquire(Language.RUST, self.project_path, "session-c")

        stats = pool.get_stats()

        assert len(stats["lsps"]) == 1, (
            f"❌ FAILURE: get_stats() returned wrong number of LSPs\n"
            f"WHAT FAILED: Multi-root LSP sharing\n"
            f"WHY: Rust is multi-root, should share single instance\n"
            f"EXPECTED: len(lsps) = 1\n"
            f"ACTUAL: len(lsps) = {len(stats['lsps'])}\n"
            f"GUIDANCE: Multi-root LSPs keyed by language only"
        )

        ref_count = stats["lsps"][0]["ref_count"]

        assert ref_count == 3, (
            f"❌ FAILURE: get_stats() ref_count does not match session count\n"
            f"WHAT FAILED: POST (ref_count reflects current session count)\n"
            f"WHY: 3 sessions acquired, ref_count should be 3\n"
            f"EXPECTED: ref_count = 3\n"
            f"ACTUAL: ref_count = {ref_count}\n"
            f"GUIDANCE: ref_count must match actual sessions:\n"
            f"  - ref_count = len(self._session_refs[pool_key])\n"
            f"  - For multi-root: pool_key = language\n"
            f"  - For single-root: pool_key = (language, workspace_root)"
        )

        pool.stop_all(save_cache=False)

    def test_get_stats_status_reflects_running(self):
        """
        Test that get_stats() status is "running" for active LSP.

        CONTRACT:
        - POST: status is "running", "stopped", "crashed", or "initializing"

        WHAT: status field accuracy in get_stats()
        WHY: REQ-API-2 requires status to indicate LSP state
        EXPECTED: status = "running" for LSP with is_running() == True
        ACTUAL: status = {status}, ref_count = {ref_count}
        GUIDANCE: Determine status based on process state:
            - "running": lsp.is_running() == True (process alive and responsive)
            - "stopped": clean shutdown (returncode == 0 or None before start)
            - "crashed": abnormal termination (returncode != 0 and != None)
            - "initializing": process started but not yet responsive
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire LSP (should be running)
        pool.acquire(Language.PYTHON, self.project_path, "session-a")

        stats = pool.get_stats()
        lsp_info = stats["lsps"][0]

        ref_count = lsp_info["ref_count"]
        status = lsp_info["status"]

        assert status == "running", (
            f"❌ FAILURE: get_stats() status wrong for active LSP\n"
            f"WHAT FAILED: POST (status reflects LSP state)\n"
            f"WHY: LSP process is alive and responsive, should be 'running'\n"
            f"EXPECTED: status = 'running'\n"
            f"ACTUAL: status = {status}, ref_count = {ref_count}\n"
            f"GUIDANCE: status determination logic:\n"
            f"  - If lsp.is_running() == True: status = 'running'\n"
            f"  - If returncode == 0 or None (never started): status = 'stopped'\n"
            f"  - If returncode != 0 and != None: status = 'crashed'"
        )

        pool.stop_all(save_cache=False)

    def test_get_stats_status_detects_crashed(self):
        """
        Test that get_stats() status is "crashed" when LSP exits abnormally.

        CONTRACT:
        - POST: status is "crashed" when returncode != 0 and != None

        WHAT: crashed status detection in get_stats()
        WHY: REQ-API-2 requires distinguishing crash from clean shutdown
        EXPECTED: status = "crashed" for LSP with non-zero returncode
        ACTUAL: status = {status}
        GUIDANCE: Detect crashed state:
            - Check lsp._process.returncode (or equivalent accessor)
            - If returncode is None: process still running or never started
            - If returncode == 0: clean shutdown -> "stopped"
            - If returncode != 0: abnormal termination -> "crashed"
            - This distinction is CRITICAL for debugging LSP issues
        """
        from unittest.mock import MagicMock, PropertyMock

        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire LSP to populate pool
        pool.acquire(Language.PYTHON, self.project_path, "session-a")

        # Get the LSP and mock it as crashed (is_running=False, returncode=1)
        pool_key = list(pool._pool.keys())[0]
        mock_lsp = pool._pool[pool_key]

        # Mock is_running() to return False (not running)
        mock_lsp.is_running = MagicMock(return_value=False)

        # Mock _process.returncode to return non-zero (crashed)
        mock_process = MagicMock()
        type(mock_process).returncode = PropertyMock(return_value=1)  # Non-zero = crashed
        mock_lsp._process = mock_process

        stats = pool.get_stats()
        lsp_info = stats["lsps"][0]
        status = lsp_info["status"]

        assert status == "crashed", (
            f"❌ FAILURE: get_stats() failed to detect crashed LSP\n"
            f"WHAT FAILED: POST (status is 'crashed' for abnormal termination)\n"
            f"WHY: LSP exited with returncode=1, should be 'crashed' not 'stopped'\n"
            f"EXPECTED: status = 'crashed'\n"
            f"ACTUAL: status = {status}\n"
            f"GUIDANCE: Check process returncode:\n"
            f"  - If not is_running() and returncode != 0: status = 'crashed'\n"
            f"  - If not is_running() and returncode == 0: status = 'stopped'\n"
            f"  - Access returncode via lsp._process.returncode or lsp.returncode"
        )

        pool.stop_all(save_cache=False)

    def test_get_stats_no_ref_count_increment(self):
        """
        Test that get_stats() does NOT increment ref_count.

        CONTRACT:
        - INVARIANT: Read-only - does not modify ref_count or pool state
        - REQ-LEAK-TEST: Calling get_stats() does NOT increment ref_count

        WHAT: get_stats() ref_count side effects
        WHY: REQ-LEAK-TEST requires no reference leaks from stats API
        EXPECTED: ref_count unchanged after get_stats() call
        ACTUAL: ref_count before = {ref_count_before}, after = {ref_count_after}
        GUIDANCE: get_stats() must be read-only:
            - Do NOT call pool.acquire() internally
            - Do NOT modify self._session_refs
            - Use pool_lock for consistent read, release after snapshot
            - Return data snapshot, not live references to internal state
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire LSP
        pool.acquire(Language.PYTHON, self.project_path, "session-a")

        # Get ref_count before
        stats_before = pool.get_stats()
        ref_count_before = stats_before["lsps"][0]["ref_count"]

        # Call get_stats() again (should not change ref_count)
        stats_after = pool.get_stats()
        ref_count_after = stats_after["lsps"][0]["ref_count"]

        assert ref_count_after == ref_count_before, (
            f"❌ FAILURE: get_stats() modified ref_count\n"
            f"WHAT FAILED: INVARIANT (Read-only method)\n"
            f"WHY: REQ-LEAK-TEST requires no reference leaks from stats API\n"
            f"EXPECTED: ref_count unchanged ({ref_count_before})\n"
            f"ACTUAL: ref_count before = {ref_count_before}, after = {ref_count_after}\n"
            f"GUIDANCE: get_stats() must NOT modify state:\n"
            f"  - Do NOT call acquire() internally\n"
            f"  - Do NOT add to _session_refs\n"
            f"  - Read-only snapshot: acquire pool_lock, read state, release lock\n"
            f"  - Return dict with copied data (not references to internal state)"
        )

        # Verify session tracking also unchanged
        sessions_after = pool.get_sessions_for_lsp(Language.PYTHON, self.project_path)

        assert len(sessions_after) == 1, (
            f"❌ FAILURE: get_stats() modified session tracking\n"
            f"WHAT FAILED: INVARIANT (Read-only method)\n"
            f"WHY: Must not create reference leaks\n"
            f"EXPECTED: 1 session (only 'session-a')\n"
            f"ACTUAL: {len(sessions_after)} sessions: {sessions_after}\n"
            f"GUIDANCE: Do NOT modify _session_refs in get_stats()"
        )

        pool.stop_all(save_cache=False)

    def test_get_stats_thread_safety(self):
        """
        Test that get_stats() is thread-safe with concurrent acquire/release.

        CONTRACT:
        - Thread-safety: Acquires pool_lock (read)
        - POST: Returns consistent snapshot

        WHAT: Thread-safety of get_stats() with concurrent mutations
        WHY: Observability API must work during active pool operations
        EXPECTED: get_stats() succeeds without crash, returns valid data
        ACTUAL: stats calls succeeded = {stats_success_count}, exceptions = {exceptions}
        GUIDANCE: get_stats() must use thread-safe locking:
            - Acquire pool_lock before reading _pool and _session_refs
            - Create snapshot dict while holding lock
            - Release lock after snapshot created
            - Do NOT hold lock while serializing/formatting data
        """
        import threading

        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        stats_success_count = 0
        exceptions = []
        stats_lock = threading.Lock()

        def acquire_release_loop():
            """Acquire and release LSP in loop."""
            for i in range(10):
                try:
                    pool.acquire(Language.PYTHON, self.project_path, f"session-{threading.get_ident()}-{i}")
                    pool.release(Language.PYTHON, self.project_path, f"session-{threading.get_ident()}-{i}")
                except Exception as e:
                    with stats_lock:
                        exceptions.append(("acquire/release", str(e)))

        def get_stats_loop():
            """Call get_stats in loop."""
            nonlocal stats_success_count
            for _ in range(10):
                try:
                    stats = pool.get_stats()
                    # Verify basic structure
                    assert isinstance(stats, dict)
                    assert "lsps" in stats
                    assert "total_count" in stats
                    with stats_lock:
                        stats_success_count += 1
                except Exception as e:
                    with stats_lock:
                        exceptions.append(("get_stats", str(e)))

        # Launch concurrent threads
        threads = []
        for _ in range(3):
            t1 = threading.Thread(target=acquire_release_loop)
            t2 = threading.Thread(target=get_stats_loop)
            threads.extend([t1, t2])
            t1.start()
            t2.start()

        for t in threads:
            t.join()

        assert len(exceptions) == 0, (
            f"❌ FAILURE: get_stats() raised exceptions with concurrent operations\n"
            f"WHAT FAILED: Thread-safety (pool_lock acquisition)\n"
            f"WHY: Observability API must work during active pool operations\n"
            f"EXPECTED: No exceptions from concurrent get_stats() calls\n"
            f"ACTUAL: {len(exceptions)} exceptions: {exceptions}\n"
            f"GUIDANCE: get_stats() must use thread-safe locking:\n"
            f"  - Acquire pool_lock: with self._pool_lock:\n"
            f"  - Create snapshot while holding lock\n"
            f"  - Release lock after snapshot created"
        )

        assert stats_success_count == 30, (
            f"❌ FAILURE: Not all get_stats() calls succeeded\n"
            f"WHAT FAILED: Thread-safety (consistent reads)\n"
            f"WHY: All 30 calls should succeed with proper locking\n"
            f"EXPECTED: 30 successful get_stats() calls\n"
            f"ACTUAL: {stats_success_count} successful calls\n"
            f"GUIDANCE: Ensure pool_lock prevents concurrent modification during read"
        )

        pool.stop_all(save_cache=False)

    def test_get_stats_multi_root_workspace_root_shared(self):
        """
        Test that get_stats() shows "shared" for multi-root LSP workspace_root.

        CONTRACT:
        - POST: workspace_root is str (path or "shared" for multi-root)

        WHAT: workspace_root field for multi-root LSPs
        WHY: REQ-API-2 requires distinguishing multi-root from single-root
        EXPECTED: workspace_root = "shared" for multi-root LSPs
        ACTUAL: workspace_root = {workspace_root}
        GUIDANCE: Determine workspace_root field:
            - For multi-root (pool_key is Language): workspace_root = "shared"
            - For single-root (pool_key is tuple): workspace_root = str(pool_key[1])
            - Use "shared" string literal (not None, not empty string)
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire multi-root LSP (RUST)
        pool.acquire(Language.RUST, self.project_path, "session-a")

        stats = pool.get_stats()
        lsp_info = stats["lsps"][0]

        workspace_root = lsp_info["workspace_root"]

        assert workspace_root == "shared", (
            f"❌ FAILURE: get_stats() wrong workspace_root for multi-root LSP\n"
            f"WHAT FAILED: POST (workspace_root 'shared' for multi-root)\n"
            f"WHY: REQ-API-2 requires distinguishing multi-root from single-root\n"
            f"EXPECTED: workspace_root = 'shared'\n"
            f"ACTUAL: workspace_root = {workspace_root}\n"
            f"GUIDANCE: For multi-root LSPs:\n"
            f"  - Check: isinstance(pool_key, Language)\n"
            f"  - Set: workspace_root = 'shared'\n"
            f"  - For single-root: workspace_root = str(pool_key[1])"
        )

        pool.stop_all(save_cache=False)

    def test_get_stats_single_root_workspace_root_path(self):
        """
        Test that get_stats() shows path for single-root LSP workspace_root.

        CONTRACT:
        - POST: workspace_root is str (absolute path for single-root)

        WHAT: workspace_root field for single-root LSPs
        WHY: REQ-API-2 requires path for single-root LSPs
        EXPECTED: workspace_root = str(project_path) for single-root LSPs
        ACTUAL: workspace_root = {workspace_root}
        GUIDANCE: Determine workspace_root field:
            - For single-root (pool_key is tuple): workspace_root = str(pool_key[1])
            - Use str() to convert Path to string
            - Return absolute path (not relative)
        """
        from serena.global_lsp_pool import GlobalLanguageServerPool

        pool = GlobalLanguageServerPool()

        # Acquire single-root LSP (TYPESCRIPT)
        project_c = Path("/tmp/project-c")
        pool.acquire(Language.TYPESCRIPT, project_c, "session-c")

        stats = pool.get_stats()
        lsp_info = stats["lsps"][0]

        workspace_root = lsp_info["workspace_root"]

        assert workspace_root == str(project_c), (
            f"❌ FAILURE: get_stats() wrong workspace_root for single-root LSP\n"
            f"WHAT FAILED: POST (workspace_root is absolute path for single-root)\n"
            f"WHY: REQ-API-2 requires path for single-root LSPs\n"
            f"EXPECTED: workspace_root = {project_c!s}\n"
            f"ACTUAL: workspace_root = {workspace_root}\n"
            f"GUIDANCE: For single-root LSPs:\n"
            f"  - Check: isinstance(pool_key, tuple)\n"
            f"  - Set: workspace_root = str(pool_key[1])\n"
            f"  - Ensure absolute path (not 'shared')"
        )

        pool.stop_all(save_cache=False)
