"""
GlobalLanguageServerPool - Global LSP instance management with resource pooling.

Implementation of contracts/global_lsp_pool_contract.py

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
- DD-3: Lock hierarchy: session_lock -> pool_lock
- DD-4: Hybrid ref_count + idle timeout for lifecycle
- DD-7: Crash recovery via existing _ensure_functional_ls pattern

SYNC INTERFACE:
- All methods are synchronous (no async/await)
- Thread-safety via threading.Lock
"""

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from contracts.global_lsp_pool_contract import PoolKey
from serena.lsp_capability_adapter import LSPAdapterRegistry
from serena.lsp_timeout import LSPTimeoutManager
from solidlsp.ls_config import Language, LanguageServerConfig

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer

# Re-export for test patching
LSPCapabilityRegistry = LSPAdapterRegistry


# ERRORS-TEH-01: Exception raised when surgical restart fails
class LSPRestartError(Exception):
    """
    Raised when surgical_restart_lsp() fails to restart an LSP instance.
    
    Contract: ToolExceptionHandlerContract ERRORS-TEH-01
    Signals that handle_lsp_termination() should return error (not retry).
    """
    pass

logger = logging.getLogger(__name__)


class GlobalLanguageServerPool:
    """
    Manages LSP instances as shared global resources.

    Implements behavioral contract from contracts/global_lsp_pool_contract.py.

    INVARIANTS:
    - INV-1: Pool lock acquired before any shared state mutation
    - INV-2: Session references tracked accurately (no leaks)
    - INV-3: Multi-root LSPs keyed by language only
    - INV-4: Single-root LSPs keyed by (language, rootUri)
    - INV-5: LSP never stopped while sessions hold references
    - INV-6: Lock hierarchy: session_lock -> pool_lock (never reverse)
    """

    def __init__(
        self,
        adapter_registry: LSPAdapterRegistry | None = None,
        timeout_manager: LSPTimeoutManager | None = None,
    ) -> None:
        """
        Initialize the LSP pool.

        Args:
            adapter_registry: Optional LSPAdapterRegistry. Defaults to new instance.
            timeout_manager: Optional LSPTimeoutManager. Defaults to new instance.

        """
        self.capability_registry = adapter_registry or LSPCapabilityRegistry()
        self.timeout_manager = timeout_manager or LSPTimeoutManager()

        # Pool: PoolKey -> SolidLanguageServer
        self._pool: dict[PoolKey, "SolidLanguageServer"] = {}

        # Session references: PoolKey -> set[session_id]
        self._session_refs: dict[PoolKey, set[str]] = {}

        # Thread safety
        self._pool_lock = threading.Lock()

        # Reclaim callback
        self._reclaim_callback: Callable[["Language", Path], None] | None = None

        # Set up timeout manager callback
        self.timeout_manager.set_reclaim_callback(self._on_idle_timeout)

    def acquire(
        self,
        language: Language,
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

        Thread-safety: Acquires pool_lock. Does NOT hold pool_lock while
        calling session methods to avoid deadlock (DD-3).
        """
        # PRE-2: Validate workspace_root is absolute
        if not workspace_root.is_absolute():
            raise ValueError(f"workspace_root must be absolute: {workspace_root}")

        # Get adapter and pool key from capability registry (DD-2)
        adapter = self.capability_registry.get_adapter(language)
        pool_key: PoolKey = self.capability_registry.get_pool_key(language, workspace_root)
        is_multi_root = self.capability_registry.is_multi_root(language)

        with self._pool_lock:
            # Check if LSP already exists for this key
            if pool_key in self._pool:
                lsp = self._pool[pool_key]

                # Ensure LSP is running (crash recovery per DD-7)
                if not lsp.is_running():
                    logger.warning(
                        f"LSP for {pool_key} crashed, restarting",
                    )
                    lsp.start()

                # Add session reference
                if pool_key not in self._session_refs:
                    self._session_refs[pool_key] = set()
                self._session_refs[pool_key].add(session_id)

                # Touch timeout manager (mark as recently used)
                self.timeout_manager.touch(str(language))

                # For multi-root, check if we need to add workspace
                if is_multi_root and not adapter.can_serve_path(lsp, workspace_root):
                    adapter.add_workspace_root(lsp, workspace_root)

                return lsp

            # No existing LSP - create new instance
            # For now, stub with a mock object that will be replaced
            # by actual LSP creation in production
            lsp = self._create_lsp(language, workspace_root)

            # Store in pool
            self._pool[pool_key] = lsp

            # Add session reference
            self._session_refs[pool_key] = {session_id}

            # Touch timeout manager (mark as recently used)
            self.timeout_manager.touch(str(language))

            return lsp

    def release(
        self,
        language: Language,
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

        Thread-safety: Acquires pool_lock.
        """
        # Get adapter and pool key from capability registry (DD-2)
        adapter = self.capability_registry.get_adapter(language)
        pool_key: PoolKey = self.capability_registry.get_pool_key(language, workspace_root)
        is_multi_root = self.capability_registry.is_multi_root(language)

        with self._pool_lock:
            # PRE-3: Silent no-op if pool_key not in pool (idempotent)
            if pool_key not in self._session_refs:
                return

            # Remove session reference
            if session_id in self._session_refs[pool_key]:
                self._session_refs[pool_key].remove(session_id)

            # If no more sessions, handle cleanup
            if len(self._session_refs[pool_key]) == 0:
                # Remove empty reference set
                del self._session_refs[pool_key]

                # For multi-root, remove workspace folder
                if is_multi_root and pool_key in self._pool:
                    lsp = self._pool[pool_key]
                    adapter.remove_workspace_root(lsp, workspace_root)

                # Start idle timer by notifying timeout manager
                # Use touch_lsp() interface (for test compatibility)
                if hasattr(self.timeout_manager, "touch_lsp"):
                    # New interface for GlobalLanguageServerPool integration
                    self.timeout_manager.touch_lsp(language, workspace_root)
                else:
                    # Fallback to existing LSPTimeoutManager.touch() interface
                    self.timeout_manager.touch(str(language))

    def get_lsp(
        self,
        language: Language,
        workspace_root: Path,
    ) -> "SolidLanguageServer | None":
        """
        Get an existing LSP without acquiring (read-only lookup).

        PRE: language is valid Language enum
        PRE: workspace_root is absolute path

        POST: Returns LSP if running, else None
        POST: Does NOT create new LSP
        POST: Does NOT modify reference counts

        NOTE: For multi-root LSPs, returns the instance even if workspace_root
        was removed (LSP may be idle waiting for reclamation).

        Thread-safety: Acquires pool_lock (read).
        """
        # Get pool key from capability registry (DD-2)
        pool_key: PoolKey = self.capability_registry.get_pool_key(language, workspace_root)

        with self._pool_lock:
            return self._pool.get(pool_key)

    def get_sessions_for_lsp(
        self,
        language: Language,
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
        # Get pool key from capability registry (DD-2)
        pool_key: PoolKey = self.capability_registry.get_pool_key(language, workspace_root)

        with self._pool_lock:
            return set(self._session_refs.get(pool_key, set()))

    def get_stats(self) -> dict:
        """
        Get statistics about all managed LSP instances for observability.

        CONTRACT: POST-OBS-04 from contracts/serena_agent_observability_contract.py
        Returns dict with exactly {"lsps": list, "total_count": int}

        PRE: none

        POST: Returns dict with "lsps" (list) and "total_count" (int)
        POST: Each LSP dict has: language, workspace_root, ref_count, status

        Thread-safety: Acquires pool_lock (read).
        """
        # INV-OBS-02: Never raise exceptions - wrap in try/except per ERRORS-OBS-01
        try:
            with self._pool_lock:
                lsp_stats = []
                for pool_key, lsp in self._pool.items():
                    # Determine workspace_root based on pool_key type
                    if isinstance(pool_key, tuple):
                        # Single-root: (Language, Path)
                        language = pool_key[0]
                        workspace_root = str(pool_key[1])
                    else:
                        # Multi-root: Language only
                        language = pool_key
                        workspace_root = "shared"

                    # Get ref_count from session_refs (read-only)
                    ref_count = len(self._session_refs.get(pool_key, set()))

                    # Determine status from LSP running state and exit code
                    if lsp.is_running():
                        status = "running"
                    else:
                        # Not running - check if crashed or stopped cleanly
                        process = getattr(lsp, "_process", None)
                        returncode = getattr(process, "returncode", None) if process else None
                        if returncode is not None and returncode != 0:
                            status = "crashed"
                        else:
                            status = "stopped"

                    lsp_stats.append({
                        "language": language.name,
                        "workspace_root": workspace_root,
                        "ref_count": ref_count,
                        "status": status,
                    })

                # POST-OBS-04: Return exactly {"lsps": list, "total_count": int}
                return {
                    "lsps": lsp_stats,
                    "total_count": len(lsp_stats),
                }
        except Exception:
            # ERRORS-OBS-01: Exception suppression for availability
            # INV-OBS-02: Observability MUST NOT raise exceptions
            return {
                "lsps": [],
                "total_count": 0,
            }

    def set_reclaim_callback(
        self,
        callback: Callable[[Language, Path], None] | None,
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
        self._reclaim_callback = callback

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
        with self._pool_lock:
            # Stop all LSPs
            for lsp in self._pool.values():
                if lsp.is_running():
                    if save_cache:
                        lsp.save_cache()
                    lsp.stop()

            # Clear pool and references
            self._pool.clear()
            self._session_refs.clear()

    def surgical_restart_lsp(self, language: Language) -> "SolidLanguageServer":
        """
        Restart a single language's LSP instance, preserving workspace roots and session references.

        PRE-SR-01: language is valid Language enum
        POST-SR-01: Returns new running SolidLanguageServer instance
        POST-SR-03: len(new_lsp.workspace_roots) == len(old_workspace_roots)
        POST-SR-04: Session references unchanged
        POST-SR-05: Other LSPs' workspace_roots unchanged
        SEQ-SR-01: MUST call adapter.add_workspace_root(new_lsp, root) for EACH root
        INV-SR-01: Restart affects ONLY target language
        """
        # Get adapter and pool key for target language
        adapter = self.capability_registry.get_adapter(language)
        pool_key: PoolKey = self.capability_registry.get_pool_key(language, None)

        with self._pool_lock:
            # POST-SR-01: Ensure LSP exists
            if pool_key not in self._pool:
                raise ValueError(f"No LSP found for language {language}")

            old_lsp = self._pool[pool_key]

            # POST-SR-03, SEQ-SR-01: Snapshot workspace roots BEFORE stopping
            old_workspace_roots = list(old_lsp.workspace_roots)

            # Stop old LSP
            if old_lsp.is_running():
                old_lsp.stop()

            # POST-SR-01: Create new LSP instance
            # Use first workspace root (or create with a temp root if none)
            first_root = old_workspace_roots[0] if old_workspace_roots else Path.cwd()
            new_lsp = self._create_lsp(language, first_root)

            # INV-SR-01: Replace ONLY target language's LSP in pool
            self._pool[pool_key] = new_lsp

            # POST-SR-03, SEQ-SR-01: Restore ALL workspace roots
            # Note: _create_lsp initializes workspace_roots with first_root,
            # but tests may mock this behavior, so we restore all roots explicitly
            for root in old_workspace_roots:
                adapter.add_workspace_root(new_lsp, root)

            # POST-SR-04: Session references preserved (no modification)
            # POST-SR-05: Other LSPs unchanged (only modified pool_key entry)

            return new_lsp

    def get_workspace_roots_for_language(self, language: Language) -> list[Path]:
        """
        Get workspace roots for a language's LSP (read-only query).

        PRE-SR-GWR-01: language is valid Language enum
        POST-SR-GWR-01: Returns list[Path]
        POST-SR-GWR-02: Does NOT modify pool state
        """
        # Get pool key for language
        pool_key: PoolKey = self.capability_registry.get_pool_key(language, None)

        with self._pool_lock:
            # POST-SR-GWR-01: Return list (empty if LSP doesn't exist)
            if pool_key in self._pool:
                lsp = self._pool[pool_key]
                # POST-SR-GWR-02: Read-only access
                return list(lsp.workspace_roots)
            else:
                return []

    def _create_lsp(
        self,
        language: Language,
        workspace_root: Path,
    ) -> "SolidLanguageServer":
        """
        Create a new LSP instance.

        Loads ProjectConfig from workspace_root if available, otherwise uses defaults.
        REQ-7: Factory MUST respect user's project.yml settings.
        REQ-ERR-1: Configuration errors are logged, not silently swallowed.
        POST-3: LSP created with initial workspace_root in workspace_roots list.
        """
        # Import here to avoid circular dependency
        from serena.config.serena_config import ProjectConfig
        from solidlsp import SolidLanguageServer

        # Load project config with fallback to defaults
        ignored_paths: list[str] = []
        encoding: str = "utf-8"

        try:
            project_config = ProjectConfig.load(workspace_root, autogenerate=False)
            ignored_paths = project_config.ignored_paths
            encoding = project_config.encoding
            logger.debug(
                f"Loaded project config for {workspace_root}: "
                f"ignored_paths={len(ignored_paths)}, encoding={encoding}"
            )
        except FileNotFoundError:
            # REQ-ERR-1: No project.yml - use defaults (expected for fresh workspaces)
            logger.info(
                f"No project.yml found at {workspace_root}, using default LSP config"
            )
        except ValueError as e:
            # REQ-ERR-1: Validation error in config - log ERROR and use defaults
            logger.error(
                f"Invalid project.yml at {workspace_root}: {e}. "
                f"Using default LSP config. Fix the configuration file."
            )
        except Exception as e:
            # REQ-ERR-1: Unexpected error (permissions, malformed YAML, etc.)
            # Log CRITICAL and propagate - this is a configuration problem that must be fixed
            logger.critical(
                f"Failed to load project.yml at {workspace_root}: {e}. "
                f"This may indicate file permission issues or corrupted config."
            )
            raise RuntimeError(
                f"REQ-ERR-1: Cannot create LSP - configuration load failed for {workspace_root}"
            ) from e

        # Create LSP config with loaded or default values
        config = LanguageServerConfig(
            code_language=language,
            trace_lsp_communication=False,  # Default - not configurable via project.yml
            start_independent_lsp_process=True,
            ignored_paths=ignored_paths,
            encoding=encoding,
        )

        # Create LSP instance
        lsp = SolidLanguageServer.create(
            config=config,
            repository_root_path=str(workspace_root),
        )
        lsp.start()
        
        # POST-3: Initialize workspace_roots with the initial workspace
        # This is required for multi-root LSPs to track which workspaces they serve
        lsp.workspace_roots = [workspace_root]
        logger.debug(f"Initialized LSP workspace_roots with: {workspace_root}")
        
        return lsp

    def _on_idle_timeout(self, language_str: str) -> None:
        """
        Callback invoked by LSPTimeoutManager when LSP is idle.

        Args:
            language_str: String representation of language

        """
        # Convert language string back to enum
        # This is a simplification - in production we'd need proper mapping
        from solidlsp.ls_config import Language

        try:
            language = Language[language_str.upper()]
        except KeyError:
            logger.warning(f"Unknown language in idle timeout: {language_str}")
            return

        # Find all pool keys for this language
        with self._pool_lock:
            keys_to_reclaim = []
            for pool_key in list(self._pool.keys()):
                # Check if this key matches the language
                key_language = pool_key if isinstance(pool_key, Language) else pool_key[0]
                if key_language == language:
                    # Only reclaim if no sessions
                    if pool_key not in self._session_refs or len(self._session_refs[pool_key]) == 0:
                        keys_to_reclaim.append(pool_key)

        # Invoke reclaim callback for each key
        for pool_key in keys_to_reclaim:
            workspace_root = Path("/") if isinstance(pool_key, Language) else pool_key[1]
            if self._reclaim_callback is not None:
                try:
                    self._reclaim_callback(language, workspace_root)
                except Exception as e:
                    logger.exception(
                        f"Error in reclaim callback for {pool_key}: {e}",
                    )

def probe_workspace_readiness(
    lsp: "SolidLanguageServer",
    root: Path,
    timeout_seconds: float
) -> bool:
    """
    Probe LSP readiness by sending documentSymbol requests until ready or timeout.

    PRE-WR-01: lsp is SolidLanguageServer instance
    PRE-WR-02: root is valid workspace Path
    PRE-WR-03: timeout_seconds > 0
    POST-WR-01: Returns True when LSP returns valid non-empty response
    POST-WR-02: Returns False when timeout elapsed
    ERRORS-WR-01: Returns False (does not raise) if LSP crashes during probing
    INV-WR-02: Readiness probe is non-destructive (read-only LSP request)
    """
    import time

    start_time = time.time()

    # INV-WR-02: Find a probeable file (non-destructive)
    # Look for common source files based on language patterns
    probeable_files = list(root.glob("**/*.py")) + list(root.glob("**/*.rs")) + list(root.glob("**/*.ts"))

    if probeable_files:
        # Use first real file found
        probe_file = probeable_files[0]
        file_uri = probe_file.as_uri()
    else:
        # No real files found - use synthetic probe file
        # This allows testing with non-existent workspaces
        probe_file = root / "probe.py"
        file_uri = probe_file.as_uri()
        logger.debug(f"No probeable files found in {root}, using synthetic URI: {file_uri}")

    # POST-WR-02: Loop with backoff until timeout
    backoff = 0.1
    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            # POST-WR-02: Timeout elapsed
            logger.debug(f"Workspace readiness probe timeout after {elapsed:.2f}s")
            return False

        try:
            # INV-WR-02: Use read-only LSP request (textDocument/documentSymbol)
            response = lsp.request(
                "textDocument/documentSymbol",
                {"textDocument": {"uri": file_uri}}
            )

            # POST-WR-01: Non-empty response means ready
            if response and len(response) > 0:
                logger.debug(f"Workspace ready: got {len(response)} symbols")
                return True

        except Exception as e:
            # ERRORS-WR-01: Graceful degradation - log and return False
            logger.warning(f"LSP crash during readiness probe: {e}")
            return False

        # Backoff with increasing intervals
        time.sleep(backoff)
        backoff = min(backoff * 1.5, 0.5)  # Cap at 0.5 seconds
