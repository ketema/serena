"""
CL12 Behavioral Contracts for REQ-2026-005: Server-Centric LSP Lifecycle Authority.

Authoritative source for LSP lifecycle management contracts.
Requirements traceability: requirements/REQ-2026-005-lsp-lifecycle-authority.md

Contract Authority:
    This file is the SINGULAR authoritative source (CL12-C) for LSP lifecycle
    authority contracts. Tests MUST cite clause IDs from this file (CL12-E).
    Deprecated contracts: None (new domain).

Revision History:
    2026-02-06: Initial contracts from /design-by-contract (Phases 0-6 complete)
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from solidlsp.solid_language_server import SolidLanguageServer

    from solidlsp.ls_config import Language


# ---------------------------------------------------------------------------
# Contract 1: Surgical LSP Restart
# REQ: INV-01 (Isolation), INV-03 (Surgical Recovery), INV-04 (Workspace Accounting)
# ---------------------------------------------------------------------------


class SurgicalRestartContract(ABC):
    """
    Behavioral contract for surgical per-language LSP restart.

    The server exclusively owns LSP lifecycle. When an LSP crashes, the server
    restarts ONLY that language's LSP instance and restores ALL workspace roots
    that were registered before the crash.

    INVARIANTS:
    - INV-SR-01: Restart affects ONLY the target language's LSP instance
    - INV-SR-02: Other languages' LSP instances remain running and unaffected
    - INV-SR-03: Session references for the target language are preserved (not cleared)
    - INV-SR-04: Pool lock is held during restart to prevent concurrent access

    PRECONDITIONS:
    - PRE-SR-01: language is valid Language enum with a crashed/terminated LSP
    - PRE-SR-02: Pool contains at least one LSP entry for the given language

    POSTCONDITIONS:
    - POST-SR-01: New LSP instance running for the target language
    - POST-SR-02: ALL workspace roots from the crashed LSP re-registered on new instance
    - POST-SR-03: Workspace root count on new instance == count on crashed instance
    - POST-SR-04: Session references unchanged (same sessions mapped to new LSP)
    - POST-SR-05: Other LSP instances' workspace_roots unchanged

    ERRORS:
    - ERRORS-SR-01: Raises LSPRestartError if new LSP fails to start
    - ERRORS-SR-02: Raises LSPRestartError if workspace root restoration fails
                    (partial restoration is logged; all roots attempted)
    """

    @abstractmethod
    def surgical_restart_lsp(
        self,
        language: "Language",
    ) -> "SolidLanguageServer":
        """
        Restart a single language's LSP and restore its workspace roots.

        PRE-SR-01: language has a crashed/terminated LSP in the pool
        PRE-SR-02: Pool contains entry for language

        POST-SR-01: Returns new running SolidLanguageServer instance
        POST-SR-02: All workspace roots from crashed LSP re-registered
        POST-SR-03: len(new_lsp.workspace_roots) == len(old_workspace_roots)
        POST-SR-04: Session references unchanged
        POST-SR-05: Other LSPs untouched

        ERRORS-SR-01: LSPRestartError if new LSP cannot start
        ERRORS-SR-02: LSPRestartError if root restoration fails

        BEHAVIOR:
        1. Acquire pool_lock
        2. Snapshot workspace_roots and session_refs for crashed LSP
        3. Mark pool entry as "restarting" (prevents concurrent acquire)
        4. Release pool_lock (minimize contention — AI Panel REC-02)
        5. Stop the crashed LSP (if not already dead)
        6. Create new LSP instance for language (via _create_lsp or equivalent)
        7. For each workspace_root in snapshot:
           a. Call add_workspace_root(new_lsp, root)
           b. Log success/failure per root
        8. Re-acquire pool_lock
        9. Replace pool entry: _pool[key] = new_lsp
        10. Clear "restarting" marker
        11. Preserve session references (do NOT clear _session_refs[key])
        12. Release pool_lock
        13. Return new LSP

        Thread-safety: Pool lock held only during snapshot (steps 1-4)
        and swap (steps 8-12). LSP creation and root restoration (steps 5-7)
        run WITHOUT pool lock to avoid blocking other languages' operations.
        "Restarting" marker prevents concurrent acquire for same language.
        """
        ...

    @abstractmethod
    def get_workspace_roots_for_language(
        self,
        language: "Language",
    ) -> list[Path]:
        """
        Get all workspace roots currently registered for a language's LSP.

        PRE-SR-GWR-01: language is valid Language enum

        POST-SR-GWR-01: Returns list of Path (possibly empty if no LSP running)
        POST-SR-GWR-02: Does NOT modify state

        Thread-safety: Acquires pool_lock (read).
        """
        ...


# ---------------------------------------------------------------------------
# Contract 2: Workspace Readiness Gate
# REQ: INV-05 (Readiness)
# ---------------------------------------------------------------------------


class WorkspaceReadinessContract(ABC):
    """
    Behavioral contract for probe-based workspace readiness detection.

    After add_workspace_root sends didChangeWorkspaceFolders notification,
    the LSP needs time to index the new workspace. This contract defines
    the blocking readiness gate that prevents tool calls against un-indexed
    workspaces.

    INVARIANTS:
    - INV-WR-01: No tool call dispatched for a workspace that has not passed readiness
    - INV-WR-02: Readiness probe is non-destructive (read-only LSP request)
    - INV-WR-03: Timeout is bounded — probe loop terminates in finite time

    PRECONDITIONS:
    - PRE-WR-01: ls is a running SolidLanguageServer instance
    - PRE-WR-02: root has been added via add_workspace_root (notification sent)
    - PRE-WR-03: timeout_seconds > 0

    POSTCONDITIONS:
    - POST-WR-01: On success (True): LSP returns valid, non-empty response for
                  a file in the target workspace
    - POST-WR-02: On timeout (False): timeout_seconds elapsed without valid response
    - POST-WR-03: No side effects on LSP state (read-only probes)

    ERRORS:
    - ERRORS-WR-01: Returns False (does not raise) if LSP crashes during probing
    - ERRORS-WR-02: Returns False (does not raise) if no probeable file found in root
    """

    @abstractmethod
    def probe_workspace_readiness(
        self,
        ls: "SolidLanguageServer",
        root: Path,
        timeout_seconds: float,
    ) -> bool:
        """
        Block until LSP has indexed the workspace, or timeout.

        PRE-WR-01: ls is running
        PRE-WR-02: root was added via add_workspace_root
        PRE-WR-03: timeout_seconds > 0

        POST-WR-01: True means LSP returned valid response for workspace file
        POST-WR-02: False means timeout or probe failure
        POST-WR-03: No side effects on LSP state

        ERRORS-WR-01: Returns False on LSP crash (no exception propagated)
        ERRORS-WR-02: Returns False if no probeable file exists

        BEHAVIOR:
        1. Find a probeable file in root (e.g., first .py file for Python)
        2. Loop with backoff until timeout_seconds:
           a. Send textDocument/documentSymbol request for probeable file
           b. If response is non-empty list: return True (indexed)
           c. If response is empty or error: sleep(backoff), retry
        3. If timeout reached: return False

        Thread-safety: Does NOT hold pool_lock. LSP requests are thread-safe.
        """
        ...

    @abstractmethod
    def find_probeable_file(
        self,
        root: Path,
        language: "Language",
    ) -> Path | None:
        """
        Find a suitable file for readiness probing.

        PRE-WR-FPF-01: root is absolute path to existing directory
        PRE-WR-FPF-02: language determines file extensions to search

        POST-WR-FPF-01: Returns Path to a file suitable for LSP probing, or None
        POST-WR-FPF-02: File exists on disk and matches language extension
        POST-WR-FPF-03: Prefers small files (faster parsing)

        ERRORS: Does not raise. Returns None if no suitable file found.
        """
        ...


# ---------------------------------------------------------------------------
# Contract 3: Tool Exception Handler (apply_ex)
# REQ: INV-01 (Isolation), INV-06 (Authority)
# ---------------------------------------------------------------------------


class ToolExceptionHandlerContract(ABC):
    """
    Behavioral contract for LSP exception handling in tool dispatch.

    When a tool call encounters LanguageServerTerminatedException, the handler
    MUST perform surgical restart of ONLY the affected LSP, not pool-wide nuke.

    INVARIANTS:
    - INV-TEH-01: Exception handler SHALL NOT call reset_language_server()
                  (pool-wide replacement forbidden)
    - INV-TEH-02: Exception handler SHALL NOT replace self._lsp_pool
    - INV-TEH-03: Other languages' LSP instances unaffected by handler execution

    PRECONDITIONS:
    - PRE-TEH-01: A SolidLSPException with is_language_server_terminated() == True
                  was raised during tool execution
    - PRE-TEH-02: The tool has access to language context (which LSP was in use)

    POSTCONDITIONS:
    - POST-TEH-01: Crashed LSP surgically restarted (via surgical_restart_lsp)
    - POST-TEH-02: All workspace roots restored on restarted LSP
    - POST-TEH-03: Tool call retried on restarted LSP
    - POST-TEH-04: If retry also fails, error returned to client (no infinite loop)
    - POST-TEH-05: Other clients' in-flight calls NOT interrupted

    ERRORS:
    - ERRORS-TEH-01: If surgical restart fails (LSPRestartError), log error and
                     return error message to client (do NOT retry)
    - ERRORS-TEH-02: If retry after restart also raises LanguageServerTerminatedException,
                     return error (do NOT restart again — prevent infinite loop)
    """

    @abstractmethod
    def handle_lsp_termination(
        self,
        language: "Language",
        workspace_root: Path,
        retry_fn: Callable[[], str],
    ) -> str:
        """
        Handle LanguageServerTerminatedException with surgical restart.

        PRE-TEH-01: LSP for language has terminated
        PRE-TEH-02: language and workspace_root identify the affected LSP

        POST-TEH-01: LSP surgically restarted
        POST-TEH-02: Workspace roots restored
        POST-TEH-03: retry_fn called on restarted LSP
        POST-TEH-04: If retry fails, returns error string (no infinite retry)
        POST-TEH-05: Other clients unaffected

        ERRORS-TEH-01: Returns error string if restart fails
        ERRORS-TEH-02: Returns error string if retry fails (max 1 retry)

        BEHAVIOR:
        1. Call surgical_restart_lsp(language)
        2. Wait for workspace readiness (probe_workspace_readiness)
        3. Call retry_fn() (the original tool operation)
        4. If retry succeeds: return result
        5. If retry raises LanguageServerTerminatedException again: return error
        6. If restart itself fails: return error

        Thread-safety: surgical_restart_lsp handles locking internally.
        """
        ...


# ---------------------------------------------------------------------------
# Contract 4: Restart Tool Guard (HTTP mode)
# REQ: INV-06 (Authority)
# ---------------------------------------------------------------------------


class RestartToolGuardContract(ABC):
    """
    Behavioral contract for RestartLanguageServerTool in HTTP mode.

    In multi-client HTTP mode, clients SHALL NOT have any mechanism to trigger
    pool-wide or LSP-wide restart. The RestartLanguageServerTool MUST return
    an error when called in HTTP mode.

    INVARIANTS:
    - INV-RTG-01: In HTTP mode, RestartLanguageServerTool NEVER calls
                  reset_language_server() or surgical_restart_lsp()
    - INV-RTG-02: In STDIO mode, behavior unchanged (backward compatible)

    PRECONDITIONS:
    - PRE-RTG-01: Tool invoked by MCP client

    POSTCONDITIONS:
    - POST-RTG-01: In HTTP mode, returns error message explaining tool is disabled
    - POST-RTG-02: In HTTP mode, pool state completely unchanged
    - POST-RTG-03: In STDIO mode, existing restart behavior preserved

    ERRORS:
    - ERRORS-RTG-01: Returns error string (does not raise) in HTTP mode
    """

    @abstractmethod
    def apply_restart_tool(
        self,
        is_http_mode: bool,
    ) -> str:
        """
        Execute restart tool with mode-aware guard.

        PRE-RTG-01: Tool invoked by client

        POST-RTG-01: HTTP mode → error message returned, no restart
        POST-RTG-02: HTTP mode → pool state unchanged
        POST-RTG-03: STDIO mode → existing restart behavior

        ERRORS-RTG-01: HTTP mode returns error string
        """
        ...


# ---------------------------------------------------------------------------
# Contract 5: Pool Integrity
# REQ: INV-02 (Pool Integrity)
# ---------------------------------------------------------------------------


class PoolIntegrityContract(ABC):
    """
    Behavioral contract for pool wholesale replacement prevention.

    The pool SHALL NOT be replaced wholesale (self._lsp_pool = GlobalLanguageServerPool())
    while any session is active. The reset_language_server() method must be
    guarded or replaced.

    INVARIANTS:
    - INV-PI-01: self._lsp_pool reference NEVER replaced while
                 SessionRegistry.get_session_overview() returns non-empty
    - INV-PI-02: Pool replacement ONLY allowed during clean shutdown
                 (stop_all with no active sessions)

    PRECONDITIONS:
    - PRE-PI-01: Caller requests pool replacement (reset_language_server)

    POSTCONDITIONS:
    - POST-PI-01: If active sessions exist → pool NOT replaced, error returned
    - POST-PI-02: If no active sessions → pool replacement proceeds (clean shutdown)
    - POST-PI-03: If active sessions and HTTP mode → pool NOT replaced, log warning

    ERRORS:
    - ERRORS-PI-01: Raises PoolIntegrityError if replacement attempted with
                    active sessions in HTTP mode
    - ERRORS-PI-02: In STDIO mode, replacement proceeds (backward compat) but
                    logs deprecation warning
    """

    @abstractmethod
    def guarded_reset_language_server(
        self,
        is_http_mode: bool,
        active_session_count: int,
    ) -> None:
        """
        Pool replacement with integrity guard.

        PRE-PI-01: Caller requests pool replacement

        POST-PI-01: HTTP mode + active sessions → PoolIntegrityError raised
        POST-PI-02: No active sessions → pool replaced
        POST-PI-03: STDIO mode → pool replaced (backward compat) with deprecation warning

        ERRORS-PI-01: PoolIntegrityError in HTTP mode with active sessions
        ERRORS-PI-02: STDIO mode proceeds with warning
        """
        ...


# ---------------------------------------------------------------------------
# Custom Exception Types (ERRORS clause implementations)
# ---------------------------------------------------------------------------


class LSPRestartError(Exception):
    """Raised when surgical LSP restart fails.

    Used by: ERRORS-SR-01, ERRORS-SR-02, ERRORS-TEH-01
    """

    pass


class PoolIntegrityError(Exception):
    """Raised when pool replacement violates integrity invariants.

    Used by: ERRORS-PI-01
    """

    pass


class WorkspaceNotReadyError(Exception):
    """Raised when workspace readiness probe times out.

    Used by: INV-WR-01 enforcement — tool dispatch must check readiness.
    Not directly raised by probe_workspace_readiness (which returns bool),
    but by the readiness enforcement layer that wraps tool dispatch.
    """

    pass
