"""
Contract: SolidLanguageServer Path Resolution

Constitutional Reference: CL12 Design by Contract
Domain: LSP path resolution for multi-project workspace isolation
Version: 1.0
Requirement: REQ-2026-003

AUTHORITY: This contract is AUTHORITATIVE for SolidLanguageServer path resolution.
No other contract may define path resolution behavior for SolidLanguageServer methods.

ROOT CAUSE (bug this contract prevents):
    SolidLanguageServer.repository_root_path is set at LSP creation time.
    For shared multi-root LSPs (pool key = Language only per INV-3 of
    global_lsp_pool_contract.py), ALL sessions resolve paths against the
    FIRST session's workspace root. This silently produces wrong paths for
    every subsequent session with a different workspace.

SOLUTION:
    Every public method that resolves paths takes a mandatory workspace_root: str
    parameter. Four centralized helper methods handle resolution, URI construction,
    cache keying, and validation.

DESIGN DECISIONS:
    DD-1: workspace_root is MANDATORY (not Optional) — eliminates silent fallback
          trap where callers forget parameter and get broken behavior that tests
          don't catch in single-project mode.
          Decided By: User (verbatim: "If the mandatory approach would produce
          reliable consistent correct behavior I think that is the right solution")
    DD-2: repository_root_path retained for cache dirs, LSP process init, and
          subclass _start_server methods. NOT used for path resolution.
    DD-3: Absolute relative_path rejected by _resolve_path (ValueError) — prevents
          bypass of workspace_root parameter.
    DD-4: Cache keys include workspace_root for cross-workspace isolation.
    DD-5: 35+ LSP subclass files require ZERO changes — they implement
          _start_server, not path-resolving methods.

CROSS-REFERENCES:
    - contracts/global_lsp_pool_contract.py (INV-3: multi-root keyed by language)
    - contracts/lsp_workspace_multiplexing_contract.py (INV-1: shared instances)
    - contracts/lsp_capability_adapter_contract.py (add_workspace_root, can_serve_path)
    - requirements/REQ-2026-003-solidlsp-path-resolution.md

REQUIREMENTS SATISFIED:
    - REQ-2: LSP instances shared where possible and correct
    - CON-1: Serena owns isolation (LSPs don't know sessions)
    - CON-3: Memory constraints (resource conservation via shared LSPs)
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


# =============================================================================
# INVARIANTS (apply to ALL methods in this contract)
# =============================================================================
#
# INV-01: Path resolution MUST use workspace_root parameter,
#         NEVER self.repository_root_path.
#
# INV-02: workspace_root parameter MUST be mandatory (not Optional)
#         on ALL public methods that resolve paths.
#
# INV-03: _resolve_path MUST raise ValueError if relative_path is absolute.
#
# INV-04: Cache keys MUST include workspace_root to prevent
#         cross-workspace pollution.
#
# INV-05: Subclass files (_start_server implementations) require ZERO changes.
#
# INV-06: Multi-root LSPs remain shared (one instance per language,
#         per global_lsp_pool_contract.py INV-3).
#
# INV-07: repository_root_path is retained ONLY for:
#         (a) cache directory paths on disk,
#         (b) LSP process initialization (create/start),
#         (c) subclass _start_server methods.
#         It is NEVER used for runtime path resolution of tool requests.


class SolidLSPPathResolutionContract(ABC):
    """
    Behavioral contract for SolidLanguageServer path resolution.

    All path-resolving public methods MUST accept a mandatory workspace_root: str
    parameter and use it (via helper methods) instead of self.repository_root_path.

    INVARIANTS:
    - INV-01: Path resolution uses workspace_root, never repository_root_path
    - INV-02: workspace_root is mandatory on all path-resolving methods
    - INV-03: _resolve_path rejects absolute relative_path
    - INV-04: Cache keys include workspace_root
    - INV-05: Zero subclass changes
    - INV-06: Multi-root LSPs stay shared
    - INV-07: repository_root_path scoped to cache/init/subclass only
    """

    # =========================================================================
    # HELPER METHODS (centralized path resolution)
    # =========================================================================

    @abstractmethod
    def _effective_root(self, workspace_root: str) -> Path:
        """
        Validate workspace_root and return as Path.

        PRE-1: workspace_root is non-empty string
        PRE-2: workspace_root is an absolute path

        POST-1: Returns Path(workspace_root)
        POST-2: Returned Path is absolute

        ERRORS-1: Raises ValueError if workspace_root is empty
        ERRORS-2: Raises ValueError if workspace_root is not absolute

        INV-02: workspace_root is mandatory (str, not Optional)
        """
        ...

    @abstractmethod
    def _resolve_path(self, workspace_root: str, relative_path: str) -> Path:
        """
        Resolve relative_path against workspace_root.

        Central path resolution method. ALL public methods that construct
        absolute paths from relative paths MUST delegate to this method.

        PRE-3: workspace_root is non-empty, absolute path
        PRE-4: relative_path is a relative path (not absolute)

        POST-3: Returns (Path(workspace_root) / relative_path).resolve()
        POST-4: Returned path starts with workspace_root (no path traversal escape)

        ERRORS-3: Raises ValueError if relative_path is absolute
                  (INV-03: prevents bypass of workspace_root)
        ERRORS-4: Raises ValueError if workspace_root is empty or not absolute

        INV-01: Uses workspace_root, never self.repository_root_path
        """
        ...

    @abstractmethod
    def _resolve_uri(self, workspace_root: str, relative_path: str) -> str:
        """
        Build file:// URI from workspace_root and relative_path.

        PRE-5: workspace_root is non-empty, absolute path
        PRE-6: relative_path is a relative path (not absolute)

        POST-5: Returns string starting with "file://"
        POST-6: URI path component equals _resolve_path(workspace_root, relative_path)

        ERRORS-5: Propagates ValueError from _resolve_path if relative_path is absolute
        ERRORS-6: Propagates ValueError from _effective_root if workspace_root invalid

        INV-01: Uses workspace_root, never self.repository_root_path
        """
        ...

    @abstractmethod
    def _make_cache_key(self, workspace_root: str, *args: Any) -> str:
        """
        Build cache key that includes workspace_root for isolation.

        PRE-7: workspace_root is non-empty string

        POST-7: Returned key contains workspace_root as component
        POST-8: Two calls with different workspace_root and same args
                produce DIFFERENT cache keys
        POST-9: Two calls with same workspace_root and same args
                produce IDENTICAL cache keys

        INV-04: Cache keys include workspace_root
        """
        ...

    # =========================================================================
    # PATH-RESOLVING PUBLIC METHODS
    # =========================================================================
    #
    # Each method below has workspace_root: str as MANDATORY parameter.
    # Only path-resolution-specific PRE/POST/ERRORS are listed.
    # General method behavior (LSP protocol, return types) is preserved.
    #
    # Common contract clauses applied to ALL methods below:
    #
    #   COMMON-PRE-1: workspace_root is non-empty, absolute path string
    #                 (type: str, not Optional[str], not None)
    #
    #   COMMON-POST-1: All absolute paths constructed by the method are
    #                  derived from workspace_root (via _resolve_path or
    #                  _resolve_uri), NEVER from self.repository_root_path.
    #                  TESTABLE: Given workspace_root="/a" and relative="f.py",
    #                  resolved path MUST start with "/a/", not with
    #                  self.repository_root_path.
    #
    #   COMMON-POST-2: All relative paths returned in Location objects are
    #                  computed relative to workspace_root, not
    #                  repository_root_path.
    #                  TESTABLE: For an LSP created with repository_root_path="/x"
    #                  and called with workspace_root="/y", returned relativePath
    #                  is relative to "/y".
    #
    #   COMMON-INV-1: self.repository_root_path is NOT read, accessed, or used
    #                 for any path resolution within the method body.
    #                 Only workspace_root parameter is used.
    #
    #   COMMON-ERRORS-1: ValueError if workspace_root is empty or not absolute
    #
    # THEATER PREVENTION NOTE:
    #   Tests MUST NOT just check "workspace_root parameter exists in signature".
    #   Tests MUST verify the RESOLVED PATH contains workspace_root prefix and
    #   does NOT contain repository_root_path when the two differ.
    #   The canonical test pattern:
    #     lsp = create_lsp(repository_root_path="/old/root")
    #     result = lsp.method(relative_path="file.py", workspace_root="/new/root")
    #     assert "/new/root" in str(resolved_path)
    #     assert "/old/root" not in str(resolved_path)
    #
    # =========================================================================

    @abstractmethod
    def open_file(self, relative_file_path: str, workspace_root: str) -> Any:
        """
        Open a file in the Language Server.

        PRE: COMMON-PRE-1
        PRE-OF-1: relative_file_path is relative (not absolute)

        POST-OF-1: File opened at _resolve_path(workspace_root, relative_file_path)
        POST-OF-2: URI constructed via _resolve_uri(workspace_root, relative_file_path)
        POST-OF-3: File buffer stored with URI derived from workspace_root

        ERRORS-OF-1: FileNotFoundError if resolved path does not exist
        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def is_ignored_path(
        self,
        relative_path: str,
        workspace_root: str,
        ignore_unsupported_files: bool = True,
    ) -> bool:
        """
        Determine if a path should be ignored.

        PRE: COMMON-PRE-1
        PRE-IP-1: relative_path is relative (not absolute)

        POST-IP-1: Path checked at _resolve_path(workspace_root, relative_path)
        POST-IP-2: Ignore patterns applied relative to workspace_root

        ERRORS-IP-1: FileNotFoundError if resolved path does not exist
        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def insert_text_at_position(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        text_to_be_inserted: str,
        workspace_root: str,
    ) -> Any:
        """
        Insert text at position in file.

        PRE: COMMON-PRE-1

        POST-IT-1: File resolved via _resolve_path(workspace_root, relative_file_path)
        POST-IT-2: URI constructed via _resolve_uri(workspace_root, relative_file_path)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def delete_text_between_positions(
        self,
        relative_file_path: str,
        start_line: int,
        start_column: int,
        end_line: int,
        end_column: int,
        workspace_root: str,
    ) -> Any:
        """
        Delete text between two positions in file.

        PRE: COMMON-PRE-1

        POST-DT-1: File resolved via _resolve_path(workspace_root, relative_file_path)
        POST-DT-2: URI constructed via _resolve_uri(workspace_root, relative_file_path)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_definition(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        workspace_root: str,
    ) -> list:
        """
        Request symbol definition locations.

        PRE: COMMON-PRE-1

        POST-RD-1: URI in request constructed via _resolve_uri(workspace_root, ...)
        POST-RD-2: Returned Location.relativePath computed relative to workspace_root
                   (not repository_root_path)
        POST-RD-3: Returned Location.absolutePath starts with workspace_root

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_references(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        workspace_root: str,
    ) -> list:
        """
        Request symbol reference locations.

        PRE: COMMON-PRE-1

        POST-RR-1: References filtered by is_relative_to(workspace_root)
                   (not repository_root_path)
        POST-RR-2: Returned Location.relativePath computed relative to workspace_root
        POST-RR-3: Ignored paths checked via is_ignored_path(..., workspace_root)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_referencing_symbols(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        workspace_root: str,
        include_imports: bool = True,
        include_self: bool = False,
        include_body: bool = False,
        include_file_symbols: bool = False,
    ) -> list:
        """
        Find symbols that reference the symbol at given location.

        PRE: COMMON-PRE-1

        POST-RS-1: Internal calls to open_file, request_references,
                   request_document_symbols, request_containing_symbol
                   all pass workspace_root through
        POST-RS-2: File symbol fallback constructs URI/path via workspace_root
        POST-RS-3: retrieve_full_file_content called with workspace_root

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_document_symbols(
        self,
        relative_file_path: str,
        workspace_root: str,
        file_buffer: Any = None,
    ) -> Any:
        """
        Retrieve symbols in a document.

        PRE: COMMON-PRE-1

        POST-DS-1: absolutePath in returned symbols = _resolve_path(workspace_root, ...)
        POST-DS-2: URI in Location = _resolve_uri(workspace_root, ...)
        POST-DS-3: Cache key includes workspace_root (INV-04)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_full_symbol_tree(
        self,
        within_relative_path: str,
        workspace_root: str,
    ) -> list:
        """
        Request full symbol tree for file or directory.

        PRE: COMMON-PRE-1

        POST-ST-1: Path resolved via _resolve_path(workspace_root, within_relative_path)
        POST-ST-2: All child symbols have absolutePath derived from workspace_root

        ERRORS: COMMON-ERRORS-1
        ERRORS-ST-1: FileNotFoundError if resolved path does not exist
        """
        ...

    @abstractmethod
    def request_overview(
        self,
        within_relative_path: str,
        workspace_root: str,
    ) -> dict:
        """
        Overview of all symbols in file or directory.

        PRE: COMMON-PRE-1

        POST-OV-1: Existence check at _resolve_path(workspace_root, within_relative_path)
        POST-OV-2: Delegates to request_document_overview or request_dir_overview
                   with workspace_root passed through

        ERRORS: COMMON-ERRORS-1
        ERRORS-OV-1: FileNotFoundError if resolved path does not exist
        """
        ...

    @abstractmethod
    def request_dir_overview(
        self,
        relative_dir_path: str,
        workspace_root: str,
    ) -> dict:
        """
        Overview of symbols in a directory.

        PRE: COMMON-PRE-1

        POST-DO-1: Child symbol relativePath computed relative to workspace_root
        POST-DO-2: Delegates to request_full_symbol_tree with workspace_root

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_document_overview(
        self,
        relative_file_path: str,
        workspace_root: str,
    ) -> list:
        """
        Overview of symbols in a single document (top-level only).

        PRE: COMMON-PRE-1

        POST-DMO-1: Delegates to request_document_symbols with workspace_root

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_hover(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        workspace_root: str,
    ) -> Any:
        """
        Request hover information for symbol.

        PRE: COMMON-PRE-1

        POST-HV-1: URI in request constructed via _resolve_uri(workspace_root, ...)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_completions(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        workspace_root: str,
    ) -> list:
        """
        Request code completions at position.

        PRE: COMMON-PRE-1

        POST-CP-1: URI in request constructed via _resolve_uri(workspace_root, ...)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_text_document_diagnostics(
        self,
        relative_file_path: str,
        workspace_root: str,
    ) -> list:
        """
        Request diagnostics for a document.

        PRE: COMMON-PRE-1

        POST-DG-1: URI in request constructed via _resolve_uri(workspace_root, ...)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_rename_symbol_edit(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        new_name: str,
        workspace_root: str,
    ) -> Any:
        """
        Retrieve workspace edit for renaming a symbol.

        PRE: COMMON-PRE-1

        POST-RN-1: URI in RenameParams constructed via
                   _resolve_uri(workspace_root, relative_file_path)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def apply_text_edits_to_file(
        self,
        relative_file_path: str,
        edits: list,
        workspace_root: str,
    ) -> None:
        """
        Apply text edits to a file.

        PRE: COMMON-PRE-1

        POST-AE-1: File resolved via _resolve_path(workspace_root, relative_file_path)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def retrieve_full_file_content(
        self,
        relative_file_path: str,
        workspace_root: str,
    ) -> str:
        """
        Retrieve full content of a file.

        PRE: COMMON-PRE-1

        POST-FC-1: File read from _resolve_path(workspace_root, relative_file_path)

        ERRORS: COMMON-ERRORS-1
        ERRORS-FC-1: FileNotFoundError if resolved path does not exist
        """
        ...

    @abstractmethod
    def retrieve_content_around_line(
        self,
        relative_file_path: str,
        line: int,
        context_lines: int,
        workspace_root: str,
    ) -> str:
        """
        Retrieve content around a specific line.

        PRE: COMMON-PRE-1

        POST-CL-1: File read from _resolve_path(workspace_root, relative_file_path)

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def retrieve_symbol_body(
        self,
        symbol: Any,
        workspace_root: str,
        file_lines: list | None = None,
    ) -> str:
        """
        Retrieve the body/source code of a symbol.

        PRE: COMMON-PRE-1

        POST-SB-1: If file read needed, resolved via workspace_root

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_containing_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        workspace_root: str,
        include_body: bool = False,
    ) -> Any:
        """
        Find the symbol containing the given position.

        PRE: COMMON-PRE-1

        POST-CS-1: Delegates to request_document_symbols with workspace_root

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_defining_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        workspace_root: str,
    ) -> Any:
        """
        Find the defining symbol at the given position.

        PRE: COMMON-PRE-1

        POST-DF-1: Delegates to request_definition with workspace_root
        POST-DF-2: Delegates to request_document_symbols with workspace_root

        ERRORS: COMMON-ERRORS-1
        """
        ...

    @abstractmethod
    def request_workspace_symbol(
        self,
        query: str,
        workspace_root: str,
    ) -> list:
        """
        Search for symbols matching query across workspace.

        PRE: COMMON-PRE-1

        POST-WS-1: Returned symbols have relativePath computed
                   relative to workspace_root

        ERRORS: COMMON-ERRORS-1
        """
        ...


# =============================================================================
# CALLER CONTRACT: LanguageServerSymbolRetriever
# =============================================================================
#
# symbol.py is the PRIMARY caller of SolidLanguageServer methods.
# This contract defines WHAT symbol.py must do when calling LSP methods.
#
# This is a targeted addition — not a full symbol.py contract. Full
# symbol.py contract should be written during /constitutional-refactor.
#

class SymbolRetrieverCallerContract(ABC):
    """
    Caller contract for LanguageServerSymbolRetriever.

    Defines the obligation of symbol.py when calling SolidLanguageServer
    path-resolving methods.

    INVARIANT:
    - CALLER-INV-1: Every call to a path-resolving SolidLanguageServer
      method MUST pass the current session's workspace_root (from
      get_active_project_or_raise().project_root), NEVER the LSP's
      repository_root_path.
    """

    @abstractmethod
    def get_workspace_root(self) -> str:
        """
        Get the current session's workspace root for passing to LSP methods.

        PRE-CW-1: Active session exists (get_current_session() is not None)
        PRE-CW-2: Active project exists (project_root is not None)

        POST-CW-1: Returns absolute path string of current session's workspace
        POST-CW-2: Returned value equals get_active_project_or_raise().project_root

        ERRORS-CW-1: ProjectNotFoundError if no active session/project

        INV: CALLER-INV-1: returned value is session's workspace, not LSP's root
        """
        ...


# =============================================================================
# CALLER CONTRACT: LanguageServerCodeEditor
# =============================================================================

class CodeEditorCallerContract(ABC):
    """
    Caller contract for LanguageServerCodeEditor.

    Same obligation as SymbolRetrieverCallerContract — pass session's
    workspace_root to all LSP method calls.

    INVARIANT:
    - CALLER-INV-1: Same as SymbolRetrieverCallerContract
    """

    @abstractmethod
    def get_workspace_root(self) -> str:
        """
        Same contract as SymbolRetrieverCallerContract.get_workspace_root.

        PRE: PRE-CW-1, PRE-CW-2
        POST: POST-CW-1, POST-CW-2
        ERRORS: ERRORS-CW-1
        INV: CALLER-INV-1
        """
        ...
