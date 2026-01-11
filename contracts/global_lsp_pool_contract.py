"""
Contract: GlobalLanguageServerPool

Defines the behavioral contract for global LSP instance management.
Follows database connection pooler pattern for resource sharing.
Mocks for tests MUST derive from this contract (CL10).

Component: GlobalLanguageServerPool
Purpose: Manage LSP instances as shared global resources across sessions

DESIGN PATTERN: Database Connection Pooler
- Acquisition/release semantics
- Reference counting per session
- Idle timeout for reclamation
- Capability-aware routing

REQUIREMENTS SATISFIED:
- REQ-2: LSP instances shared where possible and correct
- REQ-5: LSPs reclaimed after idle timeout
- CON-1: Serena owns isolation (LSPs don't know sessions)
- CON-2: Single-root LSP limitation (per-root instances)
- CON-3: Memory constraints (resource conservation)

DESIGN DECISIONS:
- DD-1: Connection pooler pattern
- DD-2: Pool key = language (multi-root) or (language, rootUri) (single-root)
- DD-4: Hybrid ref_count + idle timeout for lifecycle
- DD-5: Workspace folder cleanup on disconnect
- DD-7: Crash recovery via existing _ensure_functional_ls pattern

SYNC INTERFACE:
- All methods are synchronous (no async/await)
- Thread-safety via threading.Lock
- Lock hierarchy: session_lock -> pool_lock (DD-3)

INTEGRATION POINTS:
- LSPTimeoutManager: Pool delegates idle detection to existing LSPTimeoutManager.
  When ref_count reaches 0, pool notifies timeout manager to start idle timer.
  Timeout values defined in lsp_timeout_contract.py (e.g., rust=1800s, python=3600s).
- Crash Recovery (DD-7): Pool uses existing _ensure_functional_ls pattern from
  LanguageServerManager. Before returning LSP from acquire(), check is_running()
  and auto-restart if crashed. This pattern already exists in ls_manager.py.

LOCK HIERARCHY ENFORCEMENT (DD-3):
When acquiring multiple locks, ALWAYS acquire in this order:
  1. session_lock (if needed)
  2. pool_lock (if needed)

NEVER acquire session_lock while holding pool_lock. If you need both:
  - Release pool_lock first
  - Acquire session_lock
  - Re-acquire pool_lock
  - Re-validate state (may have changed)

Example (CORRECT):
  with session_lock:
      session = get_session(session_id)
  with pool_lock:
      lsp = acquire_from_pool(language, root)

Example (INCORRECT - DEADLOCK RISK):
  with pool_lock:
      with session_lock:  # NEVER DO THIS
          ...
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer
    from solidlsp.ls_config import Language


# =============================================================================
# TYPE DEFINITIONS
# =============================================================================

from typing import Union

# Pool key types
# For multi-root LSPs: just the language (e.g., Language.RUST)
# For single-root LSPs: tuple of (language, root) (e.g., (Language.TYPESCRIPT, Path("/project")))
PoolKey = Union["Language", tuple["Language", Path]]


# =============================================================================
# BEHAVIORAL CONTRACTS
# =============================================================================

class GlobalLanguageServerPoolContract(ABC):
    """
    Behavioral contract for global LSP pool management (SYNC).

    INVARIANTS:
    - INV-1: Pool lock acquired before any shared state mutation
    - INV-2: Session references tracked accurately (no leaks)
    - INV-3: Multi-root LSPs keyed by language only
    - INV-4: Single-root LSPs keyed by (language, rootUri)
    - INV-5: LSP never stopped while sessions hold references
    - INV-6: Lock hierarchy: session_lock -> pool_lock (never reverse)

    PRECONDITIONS:
    - PRE-1 (acquire): language is valid Language enum
    - PRE-2 (acquire): workspace_root is absolute Path
    - PRE-3 (release): session_id was previously used to acquire

    POSTCONDITIONS:
    - POST-1 (acquire): Returns functional LSP instance
    - POST-2 (acquire): Session reference recorded
    - POST-3 (acquire): For multi-root, workspace added if new
    - POST-4 (release): Session reference removed
    - POST-5 (release): If ref_count == 0, idle timer started
    """

    @abstractmethod
    def acquire(
        self,
        language: "Language",
        workspace_root: Path,
        session_id: str,
    ) -> "SolidLanguageServer":
        """
        Acquire an LSP for the given language and workspace.

        PRE: language is valid Language enum
        PRE: workspace_root is absolute path to project root
        PRE: session_id is non-empty string

        POST: Returns SolidLanguageServer instance (possibly shared)
        POST: session_id recorded as reference holder
        POST: If LSP supports multi-root and root not yet added:
              workspace/didChangeWorkspaceFolders sent
        POST: If LSP is single-root and different root:
              new instance created with key (language, workspace_root)

        BEHAVIOR:
        1. Check if LSP already running for this language/root
        2. Get capability adapter for language
        3. If multi-root and can serve path: reuse, add workspace if needed
        4. If single-root or cannot serve: create new instance
        5. Record session reference
        6. Touch timeout manager
        7. Return LSP (ensured functional via _ensure_functional_ls)

        Thread-safety: Acquires pool_lock. Does NOT hold pool_lock while
        calling session methods to avoid deadlock (DD-3).
        """
        ...

    @abstractmethod
    def release(
        self,
        language: "Language",
        workspace_root: Path,
        session_id: str,
    ) -> None:
        """
        Release a session's reference to an LSP.

        PRE: session_id previously acquired this language/root
        PRE: language is valid Language enum
        PRE: workspace_root matches what was acquired

        POST: session_id removed from reference set
        POST: If ref_count == 0:
              - For multi-root: remove workspace folder via didChangeWorkspaceFolders
              - Start idle timer (LSPTimeoutManager)
        POST: LSP NOT stopped immediately (idle timeout handles reclamation)

        BEHAVIOR:
        1. Look up LSP by appropriate key
        2. Remove session from reference set
        3. If no sessions remain:
           a. For multi-root: send workspace/didChangeWorkspaceFolders(removed=[])
           b. Delegate to LSPTimeoutManager for idle-based reclamation
        4. Do NOT stop LSP here (violates DD-4)

        Thread-safety: Acquires pool_lock.
        """
        ...

    @abstractmethod
    def get_lsp(
        self,
        language: "Language",
        workspace_root: Path,
    ) -> "SolidLanguageServer | None":
        """
        Get an existing LSP without acquiring (read-only lookup).

        PRE: language is valid Language enum
        PRE: workspace_root is absolute path

        POST: Returns LSP if running and can serve path, else None
        POST: Does NOT create new LSP
        POST: Does NOT modify reference counts

        Thread-safety: Acquires pool_lock (read).
        """
        ...

    @abstractmethod
    def get_sessions_for_lsp(
        self,
        language: "Language",
        workspace_root: Path,
    ) -> set[str]:
        """
        Get session IDs currently referencing an LSP.

        PRE: language is valid Language enum
        PRE: workspace_root is absolute path

        POST: Returns set of session_ids (possibly empty)
        POST: Does NOT modify state

        Thread-safety: Acquires pool_lock (read).
        """
        ...

    @abstractmethod
    def set_reclaim_callback(
        self,
        callback: Callable[["Language", Path], None] | None,
    ) -> None:
        """
        Set callback invoked when LSP should be reclaimed.

        PRE: callback is None or callable taking (language, workspace_root)

        POST: Callback stored for invocation on reclaim events
        POST: Callback will be called by LSPTimeoutManager when idle > timeout

        CALLBACK CONTRACT:
        - Callback is SYNC
        - Callback should stop LSP and remove from pool
        - Callback exceptions logged but don't terminate monitoring
        """
        ...

    @abstractmethod
    def stop_all(self, save_cache: bool = False) -> None:
        """
        Stop all managed LSPs (shutdown).

        PRE: none

        POST: All LSPs stopped
        POST: All caches saved if save_cache=True
        POST: Pool empty
        POST: All session references cleared

        Thread-safety: Acquires pool_lock.
        """
        ...


# =============================================================================
# CAPABILITY DETECTION CONTRACT
# =============================================================================

class LSPCapabilityRegistryContract(ABC):
    """
    Registry for LSP capability information.

    Purpose: Determine pool key strategy per language.
    """

    @abstractmethod
    def is_multi_root(self, language: "Language") -> bool:
        """
        Check if language's LSP supports multi-root workspaces.

        PRE: language is valid Language enum
        POST: Returns True if LSP supports workspace/didChangeWorkspaceFolders
        POST: Returns False if LSP is single-root only
        """
        ...

    @abstractmethod
    def get_pool_key(
        self,
        language: "Language",
        workspace_root: Path,
    ) -> PoolKey:
        """
        Get the appropriate pool key for this language/root.

        PRE: language is valid Language enum
        PRE: workspace_root is absolute path

        POST: For multi-root LSPs: returns language
        POST: For single-root LSPs: returns (language, workspace_root)
        """
        ...


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================

def verify_pool_key_strategy(
    language: "Language",
    is_multi_root: bool,
    workspace_root: Path,
) -> PoolKey:
    """Verify correct pool key generation per DD-2."""
    if is_multi_root:
        return language
    else:
        return (language, workspace_root)


def verify_reference_tracking(
    sessions_before: set[str],
    session_id: str,
    action: str,  # "acquire" or "release"
) -> set[str]:
    """Verify reference tracking behavior."""
    if action == "acquire":
        return sessions_before | {session_id}
    elif action == "release":
        return sessions_before - {session_id}
    else:
        raise ValueError(f"Unknown action: {action}")


# =============================================================================
# CONTRACT TEST ASSERTIONS
# =============================================================================

POOL_KEY_TEST_CASES = [
    # (language, is_multi_root, workspace_root, expected_key_type)
    ("rust", True, Path("/project-a"), "language"),
    ("python", True, Path("/project-a"), "language"),
    ("typescript", False, Path("/project-a"), "tuple"),
    ("typescript", False, Path("/project-b"), "tuple"),
]

ACQUIRE_RELEASE_TEST_CASES = [
    # (initial_sessions, action, session_id, expected_sessions)
    (set(), "acquire", "session-a", {"session-a"}),
    ({"session-a"}, "acquire", "session-b", {"session-a", "session-b"}),
    ({"session-a", "session-b"}, "release", "session-a", {"session-b"}),
    ({"session-a"}, "release", "session-a", set()),
]

MULTI_ROOT_LANGUAGES = ["rust", "python", "go", "java", "haskell"]
SINGLE_ROOT_LANGUAGES = ["typescript", "cpp"]  # cpp covers C/C++ via clangd
