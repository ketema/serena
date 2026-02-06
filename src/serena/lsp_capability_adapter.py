"""
LSPCapabilityAdapter - Polymorphic LSP capability handling.

Implementation of contracts/lsp_capability_adapter_contract.py

Component: LSPCapabilityAdapter
Purpose: Polymorphic interface for handling LSP-specific capabilities

DESIGN PATTERN: Adapter/Strategy Pattern
- Abstract adapter interface
- Concrete adapter per LSP type
- Runtime capability detection

REQUIREMENTS SATISFIED:
- REQ-4: Different LSPs have different capabilities - handle polymorphically
- CON-2: Single-root LSP limitation (tsserver, clangd)

DESIGN DECISIONS:
- DD-2: Pool key strategy varies by adapter (multi-root vs single-root)
- DD-6: Capability detection sequence (probe before workspace registration)

SYNC INTERFACE:
- All methods are synchronous (no async/await)
- LSP communication uses existing SolidLanguageServer sync interface

INVARIANTS:
- INV-1: Adapter is stateless (all state in LSP instance)
- INV-2: Methods never modify adapter internal state
- INV-3: All LSP communication is synchronous
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from solidlsp.ls_config import Language

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer


# =============================================================================
# MULTI-ROOT SUPPORT LEVELS (from contract)
# =============================================================================


class MultiRootSupport:
    """Enum-like class for multi-root support levels."""

    FULL = "full"  # Supports workspace/didChangeWorkspaceFolders reliably
    PARTIAL = "partial"  # Supports it but with caveats
    NONE = "none"  # Single-root only


# =============================================================================
# POOLING POLICY LEVELS
# =============================================================================


class PoolingPolicy:
    """
    Enum-like class for LSP process pooling strategies.

    Determines how LSP processes are allocated and shared across workspace roots.
    """

    SHARED_INSTANCE = "shared_instance"  # Single process for all roots (multi-root LSPs)
    ISOLATED_PROCESS = "isolated_process"  # Separate process per root (single-root LSPs)
    ISOLATED_WITH_RESOURCE_MANAGEMENT = "isolated_with_resource_management"  # Isolated + monitoring
    FORCED_ISOLATION = "forced_isolation"  # Never pool, even if multi-root capable


# =============================================================================
# ABSTRACT BASE ADAPTER
# =============================================================================


class LSPCapabilityAdapterContract(ABC):
    """
    Abstract adapter for LSP-specific capability handling.

    Re-exported from contract for implementation inheritance.
    """

    @property
    @abstractmethod
    def language(self) -> Language:
        """The language this adapter handles."""
        ...

    @property
    @abstractmethod
    def multi_root_support(self) -> str:
        """Multi-root support level for this LSP."""
        ...

    @abstractmethod
    def can_serve_path(
        self,
        ls: "SolidLanguageServer",
        path: Path,
    ) -> bool:
        """Check if this LSP instance can serve the given path."""
        ...

    @abstractmethod
    def add_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        """Add a workspace root to an existing LSP."""
        ...

    @abstractmethod
    def remove_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        """Remove a workspace root from an existing LSP."""
        ...

    @abstractmethod
    def get_workspace_roots(
        self,
        ls: "SolidLanguageServer",
    ) -> list[Path]:
        """Get all workspace roots currently registered with LSP."""
        ...

    @abstractmethod
    def get_pooling_policy(self) -> str:
        """Return the pooling policy for this LSP."""
        ...

    @abstractmethod
    def get_launch_arguments(
        self,
        workspace_root: Path,
        session_id: str,
    ) -> list[str]:
        """
        Return LSP-specific launch arguments.

        PRE: workspace_root is absolute path to project root
        PRE: session_id is unique identifier for this session
        POST: Returns list of command-line arguments
        """
        ...

    @abstractmethod
    def detect_capabilities(
        self,
        ls: "SolidLanguageServer",
    ) -> dict:
        """Detect and return LSP capabilities after initialization."""
        ...


# =============================================================================
# BASE MULTI-ROOT ADAPTER
# =============================================================================


class BaseMultiRootAdapter(LSPCapabilityAdapterContract):
    """
    Base implementation for multi-root capable LSPs.

    Provides common implementation for:
    - rust-analyzer
    - pylsp/pyright
    - gopls
    """

    @property
    def multi_root_support(self) -> str:
        return MultiRootSupport.FULL

    def get_pooling_policy(self) -> str:
        """Multi-root LSPs use SHARED_INSTANCE pooling."""
        return PoolingPolicy.SHARED_INSTANCE

    def get_launch_arguments(
        self,
        workspace_root: Path,
        session_id: str,
    ) -> list[str]:
        """
        Return default launch arguments for multi-root LSPs.

        Base implementation returns empty list - subclasses override if needed.
        """
        return []

    def can_serve_path(
        self,
        ls: "SolidLanguageServer",
        path: Path,
    ) -> bool:
        """
        Check if path is under any registered workspace folder.

        PRE: ls is running SolidLanguageServer instance
        PRE: path is absolute path to file or directory
        POST: Returns True if path is under any workspace root
        """
        workspace_roots = getattr(ls, "workspace_roots", [])
        for root in workspace_roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def add_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        """
        Add workspace root via workspace/didChangeWorkspaceFolders.

        PRE: ls is running SolidLanguageServer instance
        PRE: root is absolute path to project root
        POST-3: Returns True on success
        POST-3: On success, LSP now serves paths under root
        BEHAVIOR: Send workspace/didChangeWorkspaceFolders notification
        """
        from solidlsp.lsp_protocol_handler import lsp_types
        
        # Check if already registered
        workspace_roots: list[Path] = getattr(ls, "workspace_roots", [])
        if root in workspace_roots:
            log.debug(f"Root {root} already registered in workspace_roots")
            return True
        
        # Create WorkspaceFolder for the new root
        root_uri = root.as_uri()
        workspace_folder: lsp_types.WorkspaceFolder = {
            "uri": root_uri,
            "name": root.name,
        }
        
        # Create notification params
        params: lsp_types.DidChangeWorkspaceFoldersParams = {
            "event": {
                "added": [workspace_folder],
                "removed": [],
            }
        }
        
        # Send notification to LSP
        try:
            ls.server.notify.did_change_workspace_folders(params)
            log.info(f"Sent workspace/didChangeWorkspaceFolders notification: added {root}")
            
            # Update local tracking
            if not hasattr(ls, "workspace_roots"):
                ls.workspace_roots = []
            ls.workspace_roots.append(root)
            
            return True
        except Exception as e:
            log.error(f"Failed to add workspace root {root}: {e}")
            return False

    def remove_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        """
        Remove workspace root via workspace/didChangeWorkspaceFolders.

        PRE: ls is running SolidLanguageServer instance
        PRE: root is absolute path previously added
        POST-3: Returns True on success
        POST-3: On success, LSP no longer serves paths under root
        BEHAVIOR: Send workspace/didChangeWorkspaceFolders notification
        """
        from solidlsp.lsp_protocol_handler import lsp_types
        
        # Check if registered
        workspace_roots: list[Path] = getattr(ls, "workspace_roots", [])
        if root not in workspace_roots:
            log.debug(f"Root {root} not in workspace_roots, nothing to remove")
            return True  # Idempotent - already removed
        
        # Create WorkspaceFolder for the root to remove
        root_uri = root.as_uri()
        workspace_folder: lsp_types.WorkspaceFolder = {
            "uri": root_uri,
            "name": root.name,
        }
        
        # Create notification params
        params: lsp_types.DidChangeWorkspaceFoldersParams = {
            "event": {
                "added": [],
                "removed": [workspace_folder],
            }
        }
        
        # Send notification to LSP
        try:
            ls.server.notify.did_change_workspace_folders(params)
            log.info(f"Sent workspace/didChangeWorkspaceFolders notification: removed {root}")
            
            # Update local tracking
            ls.workspace_roots.remove(root)
            
            return True
        except Exception as e:
            log.error(f"Failed to remove workspace root {root}: {e}")
            return False

    def get_workspace_roots(
        self,
        ls: "SolidLanguageServer",
    ) -> list[Path]:
        """
        Get all workspace roots from LSP instance.

        PRE: ls is running SolidLanguageServer instance
        POST: Returns list of absolute Paths
        """
        return getattr(ls, "workspace_roots", [])

    def detect_capabilities(
        self,
        ls: "SolidLanguageServer",
    ) -> dict:
        """
        Detect capabilities from LSP ServerCapabilities.

        PRE: ls is running and initialized
        POST: Returns dict with capability information
        """
        capabilities = getattr(ls, "server_capabilities", {})
        workspace = capabilities.get("workspace", {})
        workspace_folders = workspace.get("workspaceFolders", {})

        return {
            "workspace.workspaceFolders": (
                workspace_folders.get("supported", False) if isinstance(workspace_folders, dict) else bool(workspace_folders)
            ),
        }


# =============================================================================
# BASE SINGLE-ROOT ADAPTER
# =============================================================================


class BaseSingleRootAdapter(LSPCapabilityAdapterContract):
    """
    Base implementation for single-root LSPs.

    Provides common implementation for:
    - tsserver
    - clangd
    """

    @property
    def multi_root_support(self) -> str:
        return MultiRootSupport.NONE

    def get_pooling_policy(self) -> str:
        """Single-root LSPs use ISOLATED_PROCESS pooling."""
        return PoolingPolicy.ISOLATED_PROCESS

    def get_launch_arguments(
        self,
        workspace_root: Path,
        session_id: str,
    ) -> list[str]:
        """
        Return default launch arguments for single-root LSPs.

        Base implementation returns empty list - subclasses override if needed.
        """
        return []

    def can_serve_path(
        self,
        ls: "SolidLanguageServer",
        path: Path,
    ) -> bool:
        """
        Check if path is under the LSP's root URI.

        PRE: ls is running SolidLanguageServer instance
        PRE: path is absolute path to file or directory
        POST: Returns True if path is under root_uri
        """
        root_uri = getattr(ls, "root_uri", None)
        if root_uri is None:
            return False
        try:
            path.relative_to(root_uri)
            return True
        except ValueError:
            return False

    def add_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        """
        Single-root LSP cannot add workspace roots.

        PRE: Any
        POST: Always returns False
        """
        return False

    def remove_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        """
        Single-root LSP cannot remove workspace roots.

        PRE: Any
        POST: Always returns False
        """
        return False

    def get_workspace_roots(
        self,
        ls: "SolidLanguageServer",
    ) -> list[Path]:
        """
        Get single workspace root from root_uri.

        PRE: ls is running SolidLanguageServer instance
        POST: Returns [root_uri] if set, else []
        """
        root_uri = getattr(ls, "root_uri", None)
        if root_uri is None:
            return []
        return [root_uri]

    def detect_capabilities(
        self,
        ls: "SolidLanguageServer",
    ) -> dict:
        """
        Single-root LSP reports no workspace folder support.

        PRE: ls is running and initialized
        POST: Returns dict with workspace.workspaceFolders = False
        """
        return {
            "workspace.workspaceFolders": False,
        }


# =============================================================================
# CONCRETE ADAPTERS
# =============================================================================


class RustAnalyzerAdapter(BaseMultiRootAdapter):
    """
    Adapter for rust-analyzer.

    CAPABILITIES:
    - multi_root_support: FULL
    - Supports workspace/didChangeWorkspaceFolders
    - Each workspace folder treated as potential Cargo workspace
    """

    @property
    def language(self) -> Language:
        return Language.RUST


class PylspAdapter(BaseMultiRootAdapter):
    """
    Adapter for pylsp/pyright.

    CAPABILITIES:
    - multi_root_support: FULL
    - Supports workspace/didChangeWorkspaceFolders
    """

    @property
    def language(self) -> Language:
        return Language.PYTHON


class GoplsAdapter(BaseMultiRootAdapter):
    """
    Adapter for gopls.

    CAPABILITIES:
    - multi_root_support: FULL
    - Supports workspace/didChangeWorkspaceFolders
    """

    @property
    def language(self) -> Language:
        return Language.GO


class TsServerAdapter(BaseSingleRootAdapter):
    """
    Adapter for tsserver.

    CAPABILITIES:
    - multi_root_support: NONE
    - Does NOT support dynamic workspace folder changes
    - Requires separate instance per project root

    POOL KEY: (Language.TYPESCRIPT, workspace_root)
    """

    @property
    def language(self) -> Language:
        return Language.TYPESCRIPT


class ClangdAdapter(BaseSingleRootAdapter):
    """
    Adapter for clangd.

    CAPABILITIES:
    - multi_root_support: NONE
    - Uses compilation database per project
    - Requires separate instance per project root

    POOL KEY: (Language.CPP, workspace_root)
    Note: Language enum uses CPP for C/C++ (clangd serves both via CPP enum)
    """

    @property
    def language(self) -> Language:
        return Language.CPP

    def get_launch_arguments(
        self,
        workspace_root: Path,
        session_id: str,
    ) -> list[str]:
        r"""
        Return clangd-specific launch arguments with session-isolated cache path.

        REQ-SEC-SANITY: Three-layer defense against path traversal:
        1. VALIDATE: session_id must match ^[a-zA-Z0-9\-_]+$
        2. HASH: SHA256 hash eliminates path interpretation
        3. VERIFY: Final path must resolve to child of /tmp

        Cache path format: /tmp/serena_clangd_{session_hash}_{workspace_hash}

        Raises:
            ValueError: If session_id fails validation (contains invalid characters)

        """
        import hashlib
        import re

        # LAYER 1: VALIDATE - Reject invalid session_ids before processing
        # REQ-SEC-SANITY: session_id must match ^[a-zA-Z0-9\-_]+$
        if not re.match(r"^[a-zA-Z0-9\-_]+$", session_id):
            raise ValueError(
                f"SEC-5 VIOLATION: session_id contains invalid characters. "
                f"Expected: ^[a-zA-Z0-9\\-_]+$, Got: {session_id!r}"
            )

        # LAYER 2: HASH - Eliminate path interpretation risk
        session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:8]
        workspace_hash = hashlib.sha256(str(workspace_root).encode()).hexdigest()[:8]

        # Construct cache path
        cache_dir = Path("/tmp")
        cache_path = cache_dir / f"serena_clangd_{session_hash}_{workspace_hash}"

        # LAYER 3: VERIFY - Ensure resolved path is child of cache directory
        # REQ-SEC-SANITY: Defense in depth - verify path containment
        resolved_path = cache_path.resolve()
        resolved_cache_dir = cache_dir.resolve()

        if not str(resolved_path).startswith(str(resolved_cache_dir) + "/"):
            raise ValueError(
                f"SEC-5 VIOLATION: Cache path escapes base directory. "
                f"Base: {resolved_cache_dir}, Path: {resolved_path}"
            )

        return [f"--cache-path={resolved_path}"]


class DefaultAdapter(BaseSingleRootAdapter):
    """
    Default adapter for unknown languages.

    Uses conservative single-root behavior per contract:
    "If no specific adapter, returns default adapter"
    "Default adapter assumes single-root (conservative)."
    """

    def __init__(self, language: Language):
        self._language = language

    @property
    def language(self) -> Language:
        return self._language


# =============================================================================
# ADAPTER REGISTRY
# =============================================================================


class LSPAdapterRegistry:
    """
    Registry for LSP capability adapters.

    Provides adapter lookup by language.

    Contract Reference: LSPAdapterRegistryContract
    - get_adapter(language) returns adapter for language
    - register_adapter(language, adapter) registers adapter
    - Default adapter assumes single-root (conservative)
    """

    def __init__(self) -> None:
        """Initialize registry with default adapters."""
        self._adapters: dict[Language, LSPCapabilityAdapterContract] = {
            Language.RUST: RustAnalyzerAdapter(),
            Language.PYTHON: PylspAdapter(),
            Language.GO: GoplsAdapter(),
            Language.TYPESCRIPT: TsServerAdapter(),
            Language.CPP: ClangdAdapter(),  # CPP enum covers C/C++ via clangd
        }

    def get_adapter(self, language: Language) -> LSPCapabilityAdapterContract:
        """
        Get the capability adapter for a language.

        PRE: language is valid Language enum
        POST: Returns adapter for language
        POST: If no specific adapter, returns default adapter (single-root)
        """
        if language in self._adapters:
            return self._adapters[language]
        # Return conservative default for unknown languages
        return DefaultAdapter(language)

    def register_adapter(
        self,
        language: Language,
        adapter: LSPCapabilityAdapterContract,
    ) -> None:
        """
        Register an adapter for a language.

        PRE: language is valid Language enum
        PRE: adapter implements LSPCapabilityAdapterContract
        POST: Adapter registered for language
        POST: Overwrites any existing adapter for language
        """
        self._adapters[language] = adapter

    def is_multi_root(self, language: Language) -> bool:
        """
        Check if language's LSP supports multi-root workspaces.

        PRE: language is valid Language enum
        POST: Returns True if LSP supports workspace/didChangeWorkspaceFolders
        POST: Returns False if LSP is single-root only
        """
        adapter = self.get_adapter(language)
        return adapter.multi_root_support == MultiRootSupport.FULL

    def get_pool_key(
        self,
        language: Language,
        workspace_root: Path,
    ) -> "Language | tuple[Language, Path]":
        """
        Get the appropriate pool key for this language/root.

        PRE: language is valid Language enum
        PRE: workspace_root is absolute path

        POST: For multi-root LSPs: returns language
        POST: For single-root LSPs: returns (language, workspace_root)
        """
        if self.is_multi_root(language):
            return language
        else:
            return (language, workspace_root)
