"""
LSP Workspace Multiplexing Contract - Shared LSP Management

Constitutional Reference: CL12 Design by Contract
Domain: LSP workspace folder management across sessions
Version: 1.0

AUTHORITY: This contract is AUTHORITATIVE for LSP workspace multiplexing.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from .issue6_constants import LSP_MAX_WORKSPACES_PER_INSTANCE

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer
    from solidlsp.ls_config import Language


class LSPWorkspaceMultiplexingContract(ABC):
    """
    Contract for LSP workspace folder management.

    Issue #6 Phase 3 requires:
    - "Shared LSP processes per language"
    - "Dynamic workspace/didChangeWorkspaceFolders calls"
    - "Track workspace registrations per language"

    This contract defines the BEHAVIORAL requirements for workspace multiplexing.

    INVARIANTS:
    - INV-1: Multi-root LSPs share instance across sessions with different workspaces
    - INV-2: Single-root LSPs get one instance per workspace
    - INV-3: Workspace folder count never exceeds LSP_MAX_WORKSPACES_PER_INSTANCE
    - INV-4: Workspace registration/deregistration uses didChangeWorkspaceFolders
    - INV-5: Session reference tracking accurate (no orphaned workspaces)
    """

    @abstractmethod
    def register_workspace(
        self,
        language: "Language",
        workspace_root: Path,
        session_id: str,
    ) -> "SolidLanguageServer":
        """
        Register a workspace with appropriate LSP instance.

        PRE: language is valid Language enum
        PRE: workspace_root is absolute Path
        PRE: session_id is valid session in registry

        POST: Returns LSP instance that can serve workspace_root
        POST: For multi-root LSP: workspace added via didChangeWorkspaceFolders if new
        POST: For single-root LSP: new instance created if needed
        POST: session_id recorded as reference holder
        POST: SessionContext.lsp_workspace_folders updated

        INV: Never exceeds LSP_MAX_WORKSPACES_PER_INSTANCE (INV-3)
        INV: Session reference count accurate (INV-5)
        INV: Other sessions unaffected
        INV: Thread-safe (holds pool lock)

        ERRORS:
        - ValueError: if language not supported
        - RuntimeError: if max workspaces exceeded
        """
        ...

    @abstractmethod
    def unregister_workspace(
        self,
        language: "Language",
        workspace_root: Path,
        session_id: str,
    ) -> None:
        """
        Unregister a workspace for a session.

        PRE: session_id previously registered this language/workspace
        PRE: language is valid Language enum
        PRE: workspace_root was previously registered

        POST: session_id removed from reference set
        POST: If last session for this workspace on multi-root LSP:
              - workspace/didChangeWorkspaceFolders(removed=[workspace_root]) sent
        POST: SessionContext.lsp_workspace_folders updated

        INV: Other workspaces on same LSP unaffected
        INV: Other sessions unaffected
        INV: Idempotent (unregistering non-registered is no-op)
        INV: Thread-safe (holds pool lock)

        ERRORS: None (silently ignores non-registered workspace)
        """
        ...

    @abstractmethod
    def get_registered_workspaces(
        self,
        language: "Language",
    ) -> dict[Path, set[str]]:
        """
        Get all registered workspaces and their session references.

        PRE: language is valid Language enum

        POST: Returns dict mapping workspace_root -> set of session_ids
        POST: Empty dict if no workspaces registered

        INV: Read-only, does not modify state
        INV: Thread-safe (read lock)
        INV: Returns copy, not internal data structure

        ERRORS: None (returns empty dict for invalid language)
        """
        ...
