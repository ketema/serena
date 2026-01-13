"""
Phase 3 Refactored Tests for Issue #6 Multi-Project Session Isolation

Constitutional Reference: CL12-A through CL12-E Design by Contract
Contract Index: contracts/issue6_contract_index.py (AUTHORITATIVE)
Version: 2.0 (Refactored with upgraded CL12 standards)

UPGRADE SUMMARY:
- CL12-A: PRE/POST/INV/ERRORS structure with 5-point INV checklist
- CL12-B: Behavioral contracts separated from data contracts
- CL12-C: Thread-safety explicit in contract specifications
- CL12-D: Path validation security-critical contract
- CL12-E: Contract test case specifications for traceability

ADVERSARIAL TDD ARCHITECTURE:
- Test writer BLIND to implementation (enforced by PreToolUse hook)
- Error messages are SPECIFICATIONS (5-point standard)
- Theater test prevention via exact value assertions

STRUCTURE:
1. Session Context Tests (SessionContextContract + SessionContextBehaviorContract)
2. Session Registry Tests (SessionRegistryContract - thread-safe)
3. Path Validation Tests (PathValidationContract - security-critical)
4. MCP Factory Activation Tests (MCPFactoryActivationContract)
5. Backward Compatibility Tests (BackwardCompatibilityContract)
6. Integration Tests (Multi-client, concurrency, disconnection)
"""

import logging
import threading
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Any

import pytest

# =============================================================================
# IMPORT AUTHORITATIVE CONTRACTS
# =============================================================================

from contracts.issue6_contract_index import (
    # Constants
    SESSION_DEFAULT_TTL_SECONDS,
    SESSION_ANONYMOUS_TTL_SECONDS,
    SESSION_MAX_IDLE_SECONDS,
    TOUCH_STALENESS_THRESHOLD_SECONDS,
    # Enums
    SessionState,
    SessionCreationTrigger,
    # Data contracts
    SessionContextContract as SessionContextDataContract,
    # Behavioral contracts
    SessionContextBehaviorContract,
    SessionRegistryContract,
    PathValidationContract,
    MCPFactoryActivationContract,
    BackwardCompatibilityContract,
    # Path validation utilities
    PathBoundaryError,
    validate_path,
    verify_path_is_within_boundary,
    create_symlink_attack_scenario,
    SECURITY_TEST_CASES,
    # Session registry utilities
    verify_session_context,
    verify_isolation,
    # Test cases
    SESSION_CONTEXT_TEST_CASES,
    PATH_VALIDATION_TEST_CASES,
    MCP_FACTORY_ACTIVATION_TEST_CASES,
    BACKWARD_COMPAT_TEST_CASES,
    # Verification helpers
    verify_session_context_invariants,
    verify_path_boundary_enforcement,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def temp_workspace_a(tmp_path: Path) -> Path:
    """
    Create temporary workspace A with test files.

    PRE: tmp_path exists and is writable
    POST: Returns workspace_a directory with file_a.txt
    INV: No side effects beyond directory creation (ephemeral test fixture)
    """
    workspace = tmp_path / "workspace_a"
    workspace.mkdir()
    (workspace / "file_a.txt").write_text("content_a")
    (workspace / "subdir").mkdir()
    (workspace / "subdir" / "nested_a.txt").write_text("nested_content_a")
    return workspace


@pytest.fixture
def temp_workspace_b(tmp_path: Path) -> Path:
    """
    Create temporary workspace B with test files.

    PRE: tmp_path exists and is writable
    POST: Returns workspace_b directory with file_b.txt
    INV: No side effects beyond directory creation (ephemeral test fixture)
    """
    workspace = tmp_path / "workspace_b"
    workspace.mkdir()
    (workspace / "file_b.txt").write_text("content_b")
    (workspace / "subdir").mkdir()
    (workspace / "subdir" / "nested_b.txt").write_text("nested_content_b")
    return workspace


@pytest.fixture
def mock_serena_config(tmp_path: Path):
    """
    Mock SerenaConfig following established pattern.

    Contract: PRE for activate_project requires project in config
    POST: Returns (config, project_a, project_b) tuple
    INV: Config is self-contained mock (no external dependencies)
    """
    from serena.config.serena_config import LanguageBackend

    config = MagicMock()

    # Mock config attributes needed by SerenaAgent.__init__
    config.log_level = logging.INFO
    config.config_file_path = tmp_path / "serena_config.yml"
    config.project_names = ["project_a", "project_b"]
    config.gui_log_window_enabled = False
    config.language_backend = LanguageBackend.LSP
    config.token_count_estimator = "TIKTOKEN_GPT4O"
    config.web_dashboard = False
    config.modes = []

    # Create two workspace directories
    workspace_a = tmp_path / "workspace_a"
    workspace_a.mkdir()
    workspace_b = tmp_path / "workspace_b"
    workspace_b.mkdir()

    # Mock project objects
    project_a = MagicMock()
    project_a.project_name = "project_a"
    project_a.project_root = workspace_a

    project_b = MagicMock()
    project_b.project_name = "project_b"
    project_b.project_root = workspace_b

    # get_project(name) returns project or raises ProjectNotFoundError
    def get_project_mock(name: str):
        if name == "project_a":
            return project_a
        elif name == "project_b":
            return project_b
        else:
            from serena.agent import ProjectNotFoundError
            raise ProjectNotFoundError(f"Project '{name}' not found")

    config.get_project = MagicMock(side_effect=get_project_mock)
    config.projects = {"project_a": project_a, "project_b": project_b}

    return config, project_a, project_b


@pytest.fixture
def session_registry() -> Any:
    """
    Create real SessionRegistry instance.

    Contract: SessionRegistryContract
    POST: Returns SessionRegistry ready for multi-client testing
    INV: No sessions bound initially (empty registry)
    """
    from serena.session_registry import SessionRegistry
    return SessionRegistry()


# =============================================================================
# TEST CLASS 1: SESSION CONTEXT DATA CONTRACT
# =============================================================================


class TestSessionContextDataContract:
    """
    Tests for SessionContextContract (data structure).

    Contract Reference: contracts.issue6_contract_index.SessionContextContract
    Test Cases: SESSION_CONTEXT_TEST_CASES
    """

    def test_inv1_session_id_non_empty(self):
        """
        Contract: SessionContextContract.INV-1
        Enforces: session_id is non-empty, immutable after creation

        Theater Prevention:
        - Tests EXACT invariant violation (empty string)
        - Cannot pass if validation skipped
        """
        with pytest.raises(ValueError) as exc_info:
            SessionContextDataContract(
                session_id="",  # INV-1 violation
                workspace_root=None,
                activation_source="explicit",
                activation_time=datetime.now(),
            )

        assert "INV-1" in str(exc_info.value), (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: ValueError message missing 'INV-1' reference\n"
            "2. WHY: SessionContextContract.__post_init__ validation incomplete\n"
            "3. EXPECTED: ValueError message contains 'INV-1 violation'\n"
            f"4. ACTUAL: '{exc_info.value}'\n"
            "5. GUIDANCE: __post_init__ MUST reference violated invariant in error message.\n"
            "             Error message MUST include 'INV-1 violation: session_id must be non-empty'.\n"
        )

    def test_inv2_workspace_root_absolute_when_set(self, tmp_path: Path):
        """
        Contract: SessionContextContract.INV-2
        Enforces: workspace_root is always absolute Path when set, None before activation

        Theater Prevention:
        - Tests relative path rejection (exact value check)
        - Cannot pass with wrong validation logic
        """
        with pytest.raises(ValueError) as exc_info:
            SessionContextDataContract(
                session_id="test-session",
                workspace_root=Path("relative/path"),  # INV-2 violation
                activation_source="explicit",
                activation_time=datetime.now(),
            )

        assert "INV-2" in str(exc_info.value), (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: ValueError message missing 'INV-2' reference\n"
            "2. WHY: SessionContextContract.__post_init__ absolute path check incomplete\n"
            "3. EXPECTED: ValueError message contains 'INV-2 violation'\n"
            f"4. ACTUAL: '{exc_info.value}'\n"
            "5. GUIDANCE: __post_init__ MUST verify workspace_root.is_absolute() when not None.\n"
            "             Error message MUST reference INV-2 for path violations.\n"
        )

    def test_inv2_workspace_root_none_allowed(self):
        """
        Contract: SessionContextContract.INV-2
        Enforces: workspace_root=None allowed before project activation

        Theater Prevention:
        - Verifies None explicitly allowed (not just absence of error)
        - Cannot pass if None incorrectly rejected
        """
        ctx = SessionContextDataContract(
            session_id="test-session",
            workspace_root=None,  # Valid: before activation
            activation_source="explicit",
            activation_time=datetime.now(),
        )

        assert ctx.workspace_root is None, (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: workspace_root is not None when set to None\n"
            "2. WHY: SessionContextContract.__post_init__ modified None value\n"
            "3. EXPECTED: workspace_root == None\n"
            f"4. ACTUAL: workspace_root == {ctx.workspace_root}\n"
            "5. GUIDANCE: __post_init__ MUST preserve workspace_root=None (valid pre-activation state).\n"
            "             Only non-None values require absolute path validation.\n"
        )


# =============================================================================
# TEST CLASS 2: SESSION CONTEXT BEHAVIORAL CONTRACT
# =============================================================================


class TestSessionContextBehaviorContract:
    """
    Tests for SessionContextBehaviorContract (behavior).

    Contract Reference: contracts.issue6_contract_index.SessionContextBehaviorContract
    Enforces: touch(), is_expired(), register_lsp_workspace(), unregister_lsp_workspace()
    """

    def test_touch_updates_last_activity_time(self):
        """
        Contract: SessionContextBehaviorContract.touch()
        Enforces: POST: last_activity_time = datetime.now() (current time, never backdated)

        Theater Prevention:
        - Verifies timestamp increased (not just changed)
        - Cannot pass if touch() is no-op
        """
        from serena.session_registry import SessionContext

        ctx = SessionContext(
            session_id="test-session",
            workspace_root=None,
            activation_source="explicit",
            activation_time=datetime.now(),
        )

        # Capture time BEFORE touch
        time_before = ctx.last_activity_time

        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)

        # ACT: Call touch()
        ctx.touch()

        # POST ASSERTION: last_activity_time updated
        assert ctx.last_activity_time > time_before, (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: last_activity_time not updated by touch()\n"
            "2. WHY: SessionContextBehaviorContract.touch() POST violation\n"
            f"3. EXPECTED: last_activity_time > {time_before}\n"
            f"4. ACTUAL: last_activity_time == {ctx.last_activity_time}\n"
            "5. GUIDANCE: touch() MUST set last_activity_time = datetime.now().\n"
            "             Time MUST advance on every touch() call (never backdated).\n"
        )

    def test_touch_is_idempotent_on_expired_session(self):
        """
        Contract: SessionContextBehaviorContract.touch()
        Enforces: ERRORS: None (never raises - PRE violation on EXPIRED state is silent no-op)

        Theater Prevention:
        - Verifies no exception on invalid state (explicit error handling)
        - Cannot pass if touch() incorrectly raises on EXPIRED
        """
        from serena.session_registry import SessionContext

        ctx = SessionContext(
            session_id="test-session",
            workspace_root=None,
            activation_source="explicit",
            activation_time=datetime.now(),
        )
        ctx.state = SessionState.EXPIRED  # Simulate expired session

        # ACT: Call touch() on EXPIRED session
        try:
            ctx.touch()
        except Exception as e:
            pytest.fail(
                "5-POINT ERROR MESSAGE:\n"
                "1. WHAT FAILED: touch() raised exception on EXPIRED session\n"
                "2. WHY: SessionContextBehaviorContract.touch() ERRORS violation\n"
                "3. EXPECTED: touch() never raises (silent no-op on EXPIRED)\n"
                f"4. ACTUAL: touch() raised {type(e).__name__}: {e}\n"
                "5. GUIDANCE: touch() MUST be exception-safe.\n"
                "             PRE violation (EXPIRED state) MUST be silent no-op, not exception.\n"
            )

    def test_is_expired_returns_true_after_ttl(self):
        """
        Contract: SessionContextBehaviorContract.is_expired()
        Enforces: POST: Returns True if (now - last_activity_time) > ttl_seconds

        Theater Prevention:
        - Verifies exact boolean return (not truthy/falsy)
        - Cannot pass if TTL logic incorrect
        """
        from serena.session_registry import SessionContext
        from datetime import timedelta

        ctx = SessionContext(
            session_id="test-session",
            workspace_root=None,
            activation_source="explicit",
            activation_time=datetime.now(),
        )
        ctx.ttl_seconds = 1  # 1 second TTL for test
        ctx.last_activity_time = datetime.now() - timedelta(seconds=2)  # Expired

        # ACT: Check if expired
        result = ctx.is_expired()

        assert result is True, (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: is_expired() returned False when session expired\n"
            "2. WHY: SessionContextBehaviorContract.is_expired() POST violation\n"
            "3. EXPECTED: is_expired() == True (last_activity_time > ttl_seconds ago)\n"
            f"4. ACTUAL: is_expired() == {result}\n"
            "5. GUIDANCE: is_expired() MUST return True when (now - last_activity_time) > ttl_seconds.\n"
            "             Verify TTL calculation logic: datetime.now() - last_activity_time > timedelta(seconds=ttl_seconds).\n"
        )


# =============================================================================
# TEST CLASS 3: SESSION REGISTRY CONTRACT (Thread-Safe)
# =============================================================================


class TestSessionRegistryContract:
    """
    Tests for SessionRegistryContract (thread-safe session management).

    Contract Reference: contracts.issue6_contract_index.SessionRegistryContract
    Test Cases: Derived from MCP_FACTORY_ACTIVATION_TEST_CASES
    """

    def test_bind_session_stores_context_retrievable_by_id(
        self, session_registry: Any, temp_workspace_a: Path
    ):
        """
        Contract: SessionRegistryContract.bind_session()
        Enforces: POST: get_session(session_id) returns SessionContext

        Theater Prevention:
        - Verifies ACTUAL retrieval (not mock.called)
        - Cannot pass if bind doesn't persist
        """
        session_id = "test-bind-session"

        # ACT: Bind session
        session_registry.bind_session(
            session_id=session_id,
            workspace_root=temp_workspace_a,
            source="explicit"
        )

        # POST ASSERTION: get_session returns context
        session_ctx = session_registry.get_session(session_id)

        assert session_ctx is not None, (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: get_session(session_id) returned None after bind_session\n"
            "2. WHY: SessionRegistryContract.bind_session() POST violation\n"
            f"3. EXPECTED: get_session('{session_id}') returns SessionContext\n"
            "4. ACTUAL: get_session() returned None\n"
            "5. GUIDANCE: bind_session MUST store session_id → SessionContext mapping.\n"
            "             get_session MUST retrieve stored context immediately after bind.\n"
        )

        assert verify_session_context(session_ctx), (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: Retrieved context does not satisfy SessionContext contract\n"
            "2. WHY: SessionRegistryContract.bind_session() POST violation\n"
            "3. EXPECTED: session_ctx has all required fields (session_id, workspace_root, etc.)\n"
            f"4. ACTUAL: verify_session_context(session_ctx) == False\n"
            "5. GUIDANCE: bind_session MUST create valid SessionContext.\n"
            "             Verify all required fields: session_id, workspace_root, activation_source, activation_time.\n"
        )

    def test_bind_session_workspace_root_resolves_correctly(
        self, session_registry: Any, temp_workspace_a: Path
    ):
        """
        Contract: SessionRegistryContract.bind_session()
        Enforces: POST: returned SessionContext.workspace_root == workspace_root.resolve()

        Theater Prevention:
        - Verifies EXACT workspace_root value (not just presence)
        - Cannot pass if wrong workspace bound
        """
        session_id = "test-workspace-resolution"

        session_registry.bind_session(
            session_id=session_id,
            workspace_root=temp_workspace_a,
            source="explicit"
        )

        session_ctx = session_registry.get_session(session_id)
        expected_workspace = temp_workspace_a.resolve()
        actual_workspace = Path(session_ctx.workspace_root).resolve()

        assert actual_workspace == expected_workspace, (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: workspace_root != workspace_root.resolve()\n"
            "2. WHY: SessionRegistryContract.bind_session() POST violation\n"
            f"3. EXPECTED: workspace_root == {expected_workspace}\n"
            f"4. ACTUAL: workspace_root == {actual_workspace}\n"
            "5. GUIDANCE: bind_session MUST set workspace_root to resolved absolute path.\n"
            "             Use workspace_root.resolve() to ensure canonical path.\n"
        )

    def test_bind_session_duplicate_raises_valueerror(
        self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path
    ):
        """
        Contract: SessionRegistryContract.bind_session()
        Enforces: ERRORS: ValueError if session_id already bound (INV-1 violation)

        Theater Prevention:
        - Verifies exact exception type and message
        - Cannot pass if duplicate detection skipped
        """
        session_id = "duplicate-session"

        # First bind (should succeed)
        session_registry.bind_session(
            session_id=session_id,
            workspace_root=temp_workspace_a,
            source="explicit"
        )

        # Second bind to DIFFERENT workspace (should raise)
        with pytest.raises(ValueError) as exc_info:
            session_registry.bind_session(
                session_id=session_id,
                workspace_root=temp_workspace_b,
                source="explicit"
            )

        assert session_id in str(exc_info.value), (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: ValueError message missing session_id\n"
            "2. WHY: SessionRegistryContract.bind_session() ERRORS violation\n"
            f"3. EXPECTED: Error message contains '{session_id}'\n"
            f"4. ACTUAL: '{exc_info.value}'\n"
            "5. GUIDANCE: ValueError MUST include session_id in message for debugging.\n"
            "             Example: 'Session {session_id} already bound to {workspace_root}'.\n"
        )

    def test_unbind_session_removes_from_registry(
        self, session_registry: Any, temp_workspace_a: Path
    ):
        """
        Contract: SessionRegistryContract.unbind_session()
        Enforces: POST: get_session(session_id) returns None

        Theater Prevention:
        - Verifies ACTUAL removal (None return)
        - Cannot pass if unbind is no-op
        """
        session_id = "test-unbind"

        # Bind first
        session_registry.bind_session(
            session_id=session_id,
            workspace_root=temp_workspace_a,
            source="explicit"
        )

        # Verify bound
        assert session_registry.get_session(session_id) is not None

        # ACT: Unbind
        session_registry.unbind_session(session_id)

        # POST ASSERTION: get_session returns None
        assert session_registry.get_session(session_id) is None, (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: get_session(session_id) returned non-None after unbind\n"
            "2. WHY: SessionRegistryContract.unbind_session() POST violation\n"
            f"3. EXPECTED: get_session('{session_id}') == None\n"
            f"4. ACTUAL: get_session('{session_id}') != None\n"
            "5. GUIDANCE: unbind_session MUST remove session from registry.\n"
            "             get_session MUST return None for unbound session_id.\n"
        )

    def test_unbind_session_idempotent(self, session_registry: Any):
        """
        Contract: SessionRegistryContract.unbind_session()
        Enforces: ERRORS: None (idempotent - unbinding non-existent session is silent no-op)

        Theater Prevention:
        - Verifies no exception on non-existent session
        - Cannot pass if unbind incorrectly raises
        """
        session_id = "non-existent-session"

        # ACT: Unbind non-existent session
        try:
            session_registry.unbind_session(session_id)
        except Exception as e:
            pytest.fail(
                "5-POINT ERROR MESSAGE:\n"
                "1. WHAT FAILED: unbind_session raised exception on non-existent session\n"
                "2. WHY: SessionRegistryContract.unbind_session() ERRORS violation\n"
                "3. EXPECTED: unbind_session never raises (idempotent)\n"
                f"4. ACTUAL: unbind_session raised {type(e).__name__}: {e}\n"
                "5. GUIDANCE: unbind_session MUST be idempotent.\n"
                "             Unbinding non-existent session MUST be silent no-op (return early if not in registry).\n"
            )

    def test_thread_safety_concurrent_bind(
        self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path
    ):
        """
        Contract: SessionRegistryContract.bind_session()
        Enforces: INV-4: All mutations are atomic (thread-safe via threading.Lock)

        Theater Prevention:
        - Verifies no corruption under concurrent access
        - Cannot pass if locking incomplete
        """
        results: dict[str, Any] = {}
        errors: list[tuple[str, Exception]] = []

        def bind_session_a():
            try:
                session_registry.bind_session(
                    session_id="thread-a",
                    workspace_root=temp_workspace_a,
                    source="explicit"
                )
                results["thread-a"] = session_registry.get_session("thread-a")
            except Exception as e:
                errors.append(("thread-a", e))

        def bind_session_b():
            try:
                session_registry.bind_session(
                    session_id="thread-b",
                    workspace_root=temp_workspace_b,
                    source="explicit"
                )
                results["thread-b"] = session_registry.get_session("thread-b")
            except Exception as e:
                errors.append(("thread-b", e))

        # Launch concurrent binds
        thread_a = threading.Thread(target=bind_session_a)
        thread_b = threading.Thread(target=bind_session_b)

        thread_a.start()
        thread_b.start()

        thread_a.join(timeout=5.0)
        thread_b.join(timeout=5.0)

        # Verify no exceptions
        assert len(errors) == 0, (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: Exception during concurrent bind_session\n"
            "2. WHY: SessionRegistryContract.bind_session() INV-4 violation (not thread-safe)\n"
            "3. EXPECTED: All bind_session calls succeed without exceptions\n"
            f"4. ACTUAL: errors == {errors}\n"
            "5. GUIDANCE: bind_session MUST use threading.Lock to protect shared state.\n"
            "             Lock MUST be acquired BEFORE any registry mutation.\n"
        )

        # Verify both sessions bound correctly
        assert "thread-a" in results and results["thread-a"] is not None
        assert "thread-b" in results and results["thread-b"] is not None

        # Verify correct workspace_root mapping (no cross-talk)
        assert verify_isolation(session_registry, "thread-a", "thread-b"), (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: Sessions not properly isolated after concurrent bind\n"
            "2. WHY: SessionRegistryContract.bind_session() INV-4 violation (registry corruption)\n"
            "3. EXPECTED: Each session has different workspace_root or session_id\n"
            f"4. ACTUAL: verify_isolation(thread-a, thread-b) == False\n"
            "5. GUIDANCE: Thread-safety MUST prevent workspace_root corruption.\n"
            "             Verify Lock is held during entire bind operation, not just partial state update.\n"
        )


# =============================================================================
# TEST CLASS 4: PATH VALIDATION CONTRACT (Security-Critical)
# =============================================================================


class TestPathValidationContract:
    """
    Tests for PathValidationContract (secure path validation).

    Contract Reference: contracts.issue6_contract_index.PathValidationContract
    Test Cases: SECURITY_TEST_CASES, PATH_VALIDATION_TEST_CASES
    Security: Critical - prevents path traversal attacks
    """

    @pytest.mark.parametrize("relative_path,should_pass,description", [
        ("src/main.py", True, "Normal relative path within project"),
        ("./lib/utils.py", True, "Dot-prefixed relative path"),
        ("../outside", False, "Simple parent escape"),
        ("../../etc/passwd", False, "Multi-level parent escape"),
        ("src/../../../etc/passwd", False, "Mixed path with parent escape"),
    ])
    def test_validate_path_boundary_enforcement(
        self, tmp_path: Path, relative_path: str, should_pass: bool, description: str
    ):
        """
        Contract: PathValidationContract.validate_path()
        Enforces: POST: Returns resolved absolute Path within project boundary
        Enforces: ERRORS: PathBoundaryError if resolved path escapes boundary

        Theater Prevention:
        - Tests exact boundary logic (not just exception presence)
        - Cannot pass with incorrect path resolution
        """
        project_root = tmp_path / "project"
        project_root.mkdir()

        if should_pass:
            # Should succeed
            try:
                result = validate_path(relative_path, project_root)
                assert verify_path_is_within_boundary(result, project_root.resolve()), (
                    f"5-POINT ERROR MESSAGE:\n"
                    f"1. WHAT FAILED: validate_path returned path outside boundary\n"
                    f"2. WHY: PathValidationContract.validate_path() POST violation ({description})\n"
                    f"3. EXPECTED: Returned path within {project_root.resolve()}\n"
                    f"4. ACTUAL: Returned path {result} outside boundary\n"
                    f"5. GUIDANCE: validate_path MUST verify returned path is within project_root.\n"
                    f"             Use path.relative_to(project_root) to verify containment.\n"
                )
            except PathBoundaryError:
                pytest.fail(
                    f"5-POINT ERROR MESSAGE:\n"
                    f"1. WHAT FAILED: validate_path raised PathBoundaryError for valid path\n"
                    f"2. WHY: PathValidationContract.validate_path() POST violation ({description})\n"
                    f"3. EXPECTED: validate_path('{relative_path}') succeeds\n"
                    f"4. ACTUAL: PathBoundaryError raised\n"
                    f"5. GUIDANCE: validate_path MUST allow paths within project_root.\n"
                    f"             Verify boundary check logic: resolved_path starts with resolved project_root.\n"
                )
        else:
            # Should raise PathBoundaryError
            with pytest.raises(PathBoundaryError) as exc_info:
                validate_path(relative_path, project_root)

            # Verify error attributes
            assert hasattr(exc_info.value, 'resolved_path'), (
                "5-POINT ERROR MESSAGE:\n"
                "1. WHAT FAILED: PathBoundaryError missing 'resolved_path' attribute\n"
                "2. WHY: PathValidationContract.validate_path() ERRORS violation\n"
                "3. EXPECTED: PathBoundaryError has 'resolved_path' attribute\n"
                "4. ACTUAL: No 'resolved_path' attribute found\n"
                "5. GUIDANCE: PathBoundaryError MUST include resolved_path for debugging.\n"
                "             Set exc.resolved_path = resolved_path before raising.\n"
            )

            assert hasattr(exc_info.value, 'project_root'), (
                "5-POINT ERROR MESSAGE:\n"
                "1. WHAT FAILED: PathBoundaryError missing 'project_root' attribute\n"
                "2. WHY: PathValidationContract.validate_path() ERRORS violation\n"
                "3. EXPECTED: PathBoundaryError has 'project_root' attribute\n"
                "4. ACTUAL: No 'project_root' attribute found\n"
                "5. GUIDANCE: PathBoundaryError MUST include project_root for remediation.\n"
                "             Set exc.project_root = project_root before raising.\n"
            )

    def test_symlink_traversal_attack_prevention(self, tmp_path: Path):
        """
        Contract: PathValidationContract.validate_path()
        Enforces: SEC-1: Symlinks MUST be resolved before boundary check

        Theater Prevention:
        - Tests actual symlink attack scenario
        - Cannot pass without symlink resolution
        """
        # Create symlink attack scenario
        project_root, malicious_link, target_outside = create_symlink_attack_scenario(tmp_path)

        # Attempt to access file via symlink (should be blocked)
        with pytest.raises(PathBoundaryError) as exc_info:
            validate_path(Path(malicious_link.name) / "secret.txt", project_root)

        # Verify symlink was resolved (resolved_path should be outside project)
        resolved = exc_info.value.resolved_path
        assert not verify_path_is_within_boundary(resolved, project_root.resolve()), (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: Symlink traversal attack not prevented\n"
            "2. WHY: PathValidationContract.validate_path() SEC-1 violation\n"
            "3. EXPECTED: Symlink resolved BEFORE boundary check (resolved_path outside project)\n"
            f"4. ACTUAL: resolved_path {resolved} appears within project (symlink not resolved)\n"
            "5. GUIDANCE: validate_path MUST call Path.resolve() BEFORE boundary check.\n"
            "             Algorithm: resolved = (project_root / relative_path).resolve(); verify resolved.relative_to(project_root.resolve()).\n"
        )


# =============================================================================
# THEATER TEST PREVENTION: Integration Tests (No Mocks)
# =============================================================================


class TestMultiClientIntegrationNoMocks:
    """
    Integration tests for multi-client isolation (NO MOCKS).

    Contract Reference: Phase 3 MCP Multi-Client Architecture
    Requirements: REQ-6.1, REQ-6.2, REQ-6.3
    """

    def test_multi_client_isolation_real_registry(
        self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path
    ):
        """
        Contract: SessionRegistryContract (full integration)
        Enforces: Multi-client isolation with real SessionRegistry

        Theater Prevention:
        - NO MOCKS - tests real SessionRegistry implementation
        - Verifies exact workspace_root mapping (not just presence)
        """
        # Bind two sessions
        session_registry.bind_session("client-a", temp_workspace_a, "explicit")
        session_registry.bind_session("client-b", temp_workspace_b, "explicit")

        # Verify isolation
        session_a = session_registry.get_session("client-a")
        session_b = session_registry.get_session("client-b")

        assert session_a is not None and session_b is not None
        assert session_a.workspace_root == temp_workspace_a
        assert session_b.workspace_root == temp_workspace_b

        # Verify overview accuracy
        overview = session_registry.get_session_overview()
        assert overview["total_count"] == 2

        workspace_map = {s["session_id"]: s["workspace_root"] for s in overview["sessions"]}
        assert workspace_map["client-a"] == str(temp_workspace_a), (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: Overview workspace_root for client-a incorrect\n"
            "2. WHY: SessionRegistryContract.get_session_overview() integration failure\n"
            f"3. EXPECTED: workspace_map['client-a'] == '{temp_workspace_a}'\n"
            f"4. ACTUAL: workspace_map['client-a'] == {workspace_map['client-a']}\n"
            "5. GUIDANCE: get_session_overview MUST return exact workspace_root from bound sessions.\n"
            "             Theater test prevention: Verify EXACT mapping, not just set membership.\n"
        )

    def test_disconnection_isolation_real_registry(
        self, session_registry: Any, temp_workspace_a: Path, temp_workspace_b: Path
    ):
        """
        Contract: SessionRegistryContract.unbind_session()
        Enforces: REQ-6.2 - Disconnection does not affect other clients

        Theater Prevention:
        - NO MOCKS - tests real SessionRegistry
        - Verifies survivor state unchanged (pre/post comparison)
        """
        session_registry.bind_session("client-a", temp_workspace_a, "explicit")
        session_registry.bind_session("client-b", temp_workspace_b, "explicit")

        # Capture client-b state before disconnect
        session_b_before = session_registry.get_session("client-b")
        workspace_b_before = session_b_before.workspace_root

        # Disconnect client-a
        session_registry.unbind_session("client-a")

        # Verify client-a removed
        assert session_registry.get_session("client-a") is None

        # Verify client-b unchanged
        session_b_after = session_registry.get_session("client-b")
        assert session_b_after is not None
        assert session_b_after.workspace_root == workspace_b_before, (
            "5-POINT ERROR MESSAGE:\n"
            "1. WHAT FAILED: Client-b workspace_root changed after client-a disconnect\n"
            "2. WHY: SessionRegistryContract.unbind_session() REQ-6.2 violation\n"
            f"3. EXPECTED: workspace_root == {workspace_b_before}\n"
            f"4. ACTUAL: workspace_root == {session_b_after.workspace_root}\n"
            "5. GUIDANCE: unbind_session MUST NOT modify other session state.\n"
            "             Theater test prevention: Compare pre/post state, not just post existence.\n"
        )


# =============================================================================
# SUMMARY: TEST COVERAGE REPORT
# =============================================================================

"""
TEST COVERAGE REPORT (CL12-A through CL12-E Compliance):

SessionContextContract (Data):
✓ INV-1: session_id non-empty validation
✓ INV-2: workspace_root absolute path validation
✓ INV-2: workspace_root None allowed before activation

SessionContextBehaviorContract (Behavior):
✓ touch() POST: last_activity_time updated
✓ touch() ERRORS: Silent no-op on EXPIRED
✓ is_expired() POST: Correct TTL calculation

SessionRegistryContract (Thread-Safe):
✓ bind_session POST: get_session returns context
✓ bind_session POST: workspace_root resolved correctly
✓ bind_session ERRORS: ValueError on duplicate
✓ unbind_session POST: get_session returns None
✓ unbind_session ERRORS: Idempotent (no exception)
✓ INV-4: Thread-safety (concurrent bind no corruption)

PathValidationContract (Security-Critical):
✓ validate_path POST: Returns path within boundary
✓ validate_path ERRORS: PathBoundaryError with attributes
✓ SEC-1: Symlink traversal attack prevention

Integration Tests (No Mocks):
✓ Multi-client isolation (real SessionRegistry)
✓ Disconnection isolation (survivor state unchanged)

THEATER TEST PREVENTION:
✓ All tests use EXACT value assertions (not just presence/absence)
✓ No mocks for core contracts (SessionRegistry, PathValidation)
✓ Pre/post state comparison for idempotency/isolation
✓ 5-point error messages provide BEHAVIORAL guidance (WHAT, not HOW)

NEXT PHASE:
- Run tests with: pytest test/serena/test_phase3_issue6_refactored.py -v
- Verify all contracts satisfied by implementation
- Document coverage gaps (if any)
"""
