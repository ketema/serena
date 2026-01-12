"""
Contract: LSPCapabilityAdapter

Defines the behavioral contract for polymorphic LSP capability handling.
Each LSP type (rust-analyzer, tsserver, etc.) has different capabilities
for multi-root workspace support. Adapters handle these differences.

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

CAPABILITY DETECTION SEQUENCE (DD-6) - MANDATORY:
Before registering ANY workspace with an LSP, the following sequence MUST occur:
  1. Start LSP process
  2. Send LSP initialize request
  3. Receive initialize response with ServerCapabilities
  4. Call adapter.detect_capabilities(ls) to parse and cache capabilities
  5. ONLY THEN may workspace roots be registered via add_workspace_root()

This sequence ensures:
- Correct multi_root_support determination before pooling decisions
- workspace.workspaceFolders capability is verified before sending notifications
- Graceful fallback for LSPs that don't support expected capabilities

Violation of this sequence may result in:
- Incorrect LSP sharing (treating single-root as multi-root)
- LSP errors from unsupported workspace/didChangeWorkspaceFolders
- Silent failures or undefined behavior
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer
    from solidlsp.ls_config import Language


# =============================================================================
# LSP CAPABILITY LEVELS
# =============================================================================

class MultiRootSupport:
    """Enum-like class for multi-root support levels."""

    FULL = "full"  # Supports workspace/didChangeWorkspaceFolders reliably
    PARTIAL = "partial"  # Supports it but with caveats
    NONE = "none"  # Single-root only


# =============================================================================
# BEHAVIORAL CONTRACTS
# =============================================================================

class LSPCapabilityAdapterContract(ABC):
    """
    Abstract adapter for LSP-specific capability handling.

    INVARIANTS:
    - INV-1: Adapter is stateless (all state in LSP instance)
    - INV-2: Methods never modify adapter internal state
    - INV-3: All LSP communication is synchronous

    Each concrete adapter handles a specific LSP type's capabilities:
    - rust-analyzer: Full multi-root support
    - pylsp/pyright: Full multi-root support
    - gopls: Full multi-root support
    - tsserver: Single-root only
    - clangd: Single-root only (compilation database per project)
    """

    @property
    @abstractmethod
    def language(self) -> "Language":
        """The language this adapter handles."""
        ...

    @property
    @abstractmethod
    def multi_root_support(self) -> str:
        """
        Multi-root support level for this LSP.

        Returns one of: MultiRootSupport.FULL, PARTIAL, NONE

        FULL: Can reliably add/remove workspace folders dynamically
        PARTIAL: Can add folders but with caveats (e.g., state bleed)
        NONE: Single-root only, requires separate instance per project
        """
        ...

    @abstractmethod
    def can_serve_path(
        self,
        ls: "SolidLanguageServer",
        path: Path,
    ) -> bool:
        """
        Check if this LSP instance can serve the given path.

        PRE: ls is running SolidLanguageServer instance
        PRE: path is absolute path to file or directory

        POST: Returns True if LSP can provide symbols/diagnostics for path
        POST: Returns False if LSP cannot serve this path

        BEHAVIOR (varies by adapter):
        - Multi-root: Check if path is under any registered workspace folder
        - Single-root: Check if path is under the LSP's root URI
        """
        ...

    @abstractmethod
    def add_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        """
        Add a workspace root to an existing LSP.

        PRE: ls is running SolidLanguageServer instance
        PRE: root is absolute path to project root
        PRE: multi_root_support != NONE

        POST: If successful, returns True
        POST: If failed (or not supported), returns False
        POST: On success, LSP now serves paths under root

        BEHAVIOR (varies by adapter):
        - Multi-root: Send workspace/didChangeWorkspaceFolders notification
        - Single-root: Return False (not supported)

        NOTE: This method is synchronous but LSP may process asynchronously.
        Caller should handle potential delay before LSP fully indexes new root.
        """
        ...

    @abstractmethod
    def remove_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        """
        Remove a workspace root from an existing LSP.

        PRE: ls is running SolidLanguageServer instance
        PRE: root is absolute path previously added

        POST: If successful, returns True
        POST: If failed (or not supported), returns False
        POST: On success, LSP no longer serves paths under root

        BEHAVIOR (varies by adapter):
        - Multi-root: Send workspace/didChangeWorkspaceFolders notification
        - Single-root: Return False (not supported, must terminate instance)
        """
        ...

    @abstractmethod
    def get_workspace_roots(
        self,
        ls: "SolidLanguageServer",
    ) -> list[Path]:
        """
        Get all workspace roots currently registered with LSP.

        PRE: ls is running SolidLanguageServer instance

        POST: Returns list of absolute Paths (possibly empty)
        POST: For single-root LSPs, returns list with one element

        NOTE: This queries Serena's tracking, not LSP directly.
        """
        ...

    @abstractmethod
    def detect_capabilities(
        self,
        ls: "SolidLanguageServer",
    ) -> dict:
        """
        Detect and return LSP capabilities after initialization.

        PRE: ls is running and initialized
        PRE: initialize response received

        POST: Returns dict with capability information
        POST: Keys include: "workspace.workspaceFolders", etc.

        This implements DD-6 (capability detection sequence):
        Called after LSP initialize, before workspace registration.

        BEHAVIOR:
        1. Parse ServerCapabilities from initialize response
        2. Check for workspace.workspaceFolders support
        3. Return structured capability dict
        """
        ...


# =============================================================================
# CONCRETE ADAPTER STUBS (Contracts only - implementation separate)
# =============================================================================

class RustAnalyzerAdapterContract(LSPCapabilityAdapterContract):
    """
    Adapter contract for rust-analyzer.

    CAPABILITIES:
    - multi_root_support: FULL
    - Supports workspace/didChangeWorkspaceFolders
    - Each workspace folder treated as potential Cargo workspace

    CAVEATS (UC-1 - User Responsibility):
    - Conflicting Cargo.toml can cause diagnostics bleed
    - User should organize projects correctly
    """

    @property
    def multi_root_support(self) -> str:
        return MultiRootSupport.FULL


class PylspAdapterContract(LSPCapabilityAdapterContract):
    """
    Adapter contract for pylsp/pyright.

    CAPABILITIES:
    - multi_root_support: FULL
    - Supports workspace/didChangeWorkspaceFolders
    """

    @property
    def multi_root_support(self) -> str:
        return MultiRootSupport.FULL


class GoplsAdapterContract(LSPCapabilityAdapterContract):
    """
    Adapter contract for gopls.

    CAPABILITIES:
    - multi_root_support: FULL
    - Supports workspace/didChangeWorkspaceFolders
    """

    @property
    def multi_root_support(self) -> str:
        return MultiRootSupport.FULL


class TsServerAdapterContract(LSPCapabilityAdapterContract):
    """
    Adapter contract for tsserver.

    CAPABILITIES:
    - multi_root_support: NONE
    - Does NOT support dynamic workspace folder changes
    - Requires separate instance per project root

    POOL KEY: (Language.TYPESCRIPT, workspace_root)
    """

    @property
    def multi_root_support(self) -> str:
        return MultiRootSupport.NONE

    def add_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        # tsserver does not support adding workspace folders
        return False

    def remove_workspace_root(
        self,
        ls: "SolidLanguageServer",
        root: Path,
    ) -> bool:
        # tsserver does not support removing workspace folders
        # Must terminate instance instead
        return False


class ClangdAdapterContract(LSPCapabilityAdapterContract):
    """
    Adapter contract for clangd.

    CAPABILITIES:
    - multi_root_support: NONE
    - Uses compilation database per project
    - Requires separate instance per project root

    POOL KEY: (Language.C, workspace_root) or (Language.CPP, workspace_root)
    """

    @property
    def multi_root_support(self) -> str:
        return MultiRootSupport.NONE


# =============================================================================
# ADAPTER REGISTRY CONTRACT
# =============================================================================

class LSPAdapterRegistryContract(ABC):
    """
    Registry for LSP capability adapters.

    Provides adapter lookup by language.
    """

    @abstractmethod
    def get_adapter(self, language: "Language") -> LSPCapabilityAdapterContract:
        """
        Get the capability adapter for a language.

        PRE: language is valid Language enum

        POST: Returns adapter for language
        POST: If no specific adapter, returns default adapter

        NOTE: Default adapter assumes single-root (conservative).
        """
        ...

    @abstractmethod
    def register_adapter(
        self,
        language: "Language",
        adapter: LSPCapabilityAdapterContract,
    ) -> None:
        """
        Register an adapter for a language.

        PRE: language is valid Language enum
        PRE: adapter implements LSPCapabilityAdapterContract

        POST: Adapter registered for language
        POST: Overwrites any existing adapter for language
        """
        ...


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================

def verify_multi_root_support(
    adapter: LSPCapabilityAdapterContract,
    expected: str,
) -> bool:
    """Verify adapter reports correct multi-root support level."""
    return adapter.multi_root_support == expected


def verify_can_serve_path(
    workspace_roots: list[Path],
    query_path: Path,
    is_multi_root: bool,
) -> bool:
    """Verify can_serve_path logic."""
    for root in workspace_roots:
        try:
            query_path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


# =============================================================================
# CONTRACT TEST ASSERTIONS
# =============================================================================

MULTI_ROOT_SUPPORT_TEST_CASES = [
    # (adapter_type, expected_support)
    ("rust-analyzer", MultiRootSupport.FULL),
    ("pylsp", MultiRootSupport.FULL),
    ("gopls", MultiRootSupport.FULL),
    ("tsserver", MultiRootSupport.NONE),
    ("clangd", MultiRootSupport.NONE),
]

CAN_SERVE_PATH_TEST_CASES = [
    # (workspace_roots, query_path, expected_result)
    ([Path("/project-a")], Path("/project-a/src/main.rs"), True),
    ([Path("/project-a")], Path("/project-b/src/main.rs"), False),
    ([Path("/project-a"), Path("/project-b")], Path("/project-b/src/lib.rs"), True),
]

ADD_WORKSPACE_ROOT_TEST_CASES = [
    # (adapter_type, expected_success)
    ("rust-analyzer", True),
    ("pylsp", True),
    ("tsserver", False),
    ("clangd", False),
]
