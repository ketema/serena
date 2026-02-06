"""
Tests for LSPCapabilityAdapter - Polymorphic LSP capability handling.

Tests derive from contract: contracts/lsp_capability_adapter_contract.py

Contract Requirements Tested:
- REQ-4: Different LSPs have different capabilities - handle polymorphically
- CON-2: Single-root LSP limitation (tsserver, clangd)
- DD-2: Pool key strategy varies by adapter (multi-root vs single-root)
- DD-6: Capability detection sequence (probe before workspace registration)

SYNC INTERFACE: All methods are synchronous (no async/await)
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Contract imports - tests verify implementation matches contract
from contracts.lsp_capability_adapter_contract import (
    CAN_SERVE_PATH_TEST_CASES,
    MULTI_ROOT_SUPPORT_TEST_CASES,
    MultiRootSupport,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_language_server():
    """
    Mock SolidLanguageServer for testing adapter methods.

    Contract: contracts/lsp_capability_adapter_contract.py
    - PRE-1: ls is running SolidLanguageServer instance
    - PRE-2: ls has workspace roots tracked
    - ls.server.notify.did_change_workspace_folders: LSP notification method

    Mock Derivation: This mock is derived from SolidLanguageServer structure
    where ls.server is SolidLanguageServerHandler and ls.server.notify is
    LspNotification (see src/solidlsp/ls_handler.py:144).
    """
    ls = MagicMock()
    ls.is_running.return_value = True
    ls.workspace_roots = []
    ls.root_uri = None
    # Mock the LSP notification path: ls.server.notify.did_change_workspace_folders
    # This is the actual method called by add_workspace_root/remove_workspace_root
    ls.server = MagicMock()
    ls.server.notify = MagicMock()
    ls.server.notify.did_change_workspace_folders = MagicMock()
    return ls


@pytest.fixture
def rust_adapter():
    """Rust-analyzer adapter (multi-root support: FULL)."""
    from serena.lsp_capability_adapter import RustAnalyzerAdapter

    return RustAnalyzerAdapter()


@pytest.fixture
def pylsp_adapter():
    """Pylsp adapter (multi-root support: FULL)."""
    from serena.lsp_capability_adapter import PylspAdapter

    return PylspAdapter()


@pytest.fixture
def tsserver_adapter():
    """Tsserver adapter (multi-root support: NONE)."""
    from serena.lsp_capability_adapter import TsServerAdapter

    return TsServerAdapter()


@pytest.fixture
def clangd_adapter():
    """Clangd adapter (multi-root support: NONE)."""
    from serena.lsp_capability_adapter import ClangdAdapter

    return ClangdAdapter()


@pytest.fixture
def adapter_registry():
    """LSP adapter registry."""
    from serena.lsp_capability_adapter import LSPAdapterRegistry

    return LSPAdapterRegistry()


# =============================================================================
# TEST: MultiRootSupport Levels
# =============================================================================


class TestMultiRootSupportLevels:
    """
    Tests that adapters report correct multi-root support levels.

    Contract Reference: LSPCapabilityAdapterContract.multi_root_support
    - FULL: Can reliably add/remove workspace folders dynamically
    - PARTIAL: Can add folders but with caveats (e.g., state bleed)
    - NONE: Single-root only, requires separate instance per project
    """

    def test_rust_analyzer_reports_full_multi_root_support(self, rust_adapter):
        """
        WHY: rust-analyzer supports workspace/didChangeWorkspaceFolders reliably.
        EXPECTED: multi_root_support == MultiRootSupport.FULL

        Error Message Format (5-point):
        1. What failed: multi_root_support property
        2. Why: rust-analyzer must support full multi-root per contract
        3. Expected: MultiRootSupport.FULL ("full")
        4. Actual: {actual_value}
        5. Guidance: Adapter must return FULL for rust-analyzer capability
        """
        actual = rust_adapter.multi_root_support

        assert actual == MultiRootSupport.FULL, (
            f"FAILED: rust_adapter.multi_root_support\n"
            f"WHY: rust-analyzer must support full multi-root per contract\n"
            f"EXPECTED: '{MultiRootSupport.FULL}'\n"
            f"ACTUAL: '{actual}'\n"
            f"GUIDANCE: RustAnalyzerAdapter.multi_root_support must return 'full'"
        )

    def test_pylsp_reports_full_multi_root_support(self, pylsp_adapter):
        """
        WHY: pylsp/pyright supports workspace/didChangeWorkspaceFolders.
        EXPECTED: multi_root_support == MultiRootSupport.FULL
        """
        actual = pylsp_adapter.multi_root_support

        assert actual == MultiRootSupport.FULL, (
            f"FAILED: pylsp_adapter.multi_root_support\n"
            f"WHY: pylsp must support full multi-root per contract\n"
            f"EXPECTED: '{MultiRootSupport.FULL}'\n"
            f"ACTUAL: '{actual}'\n"
            f"GUIDANCE: PylspAdapter.multi_root_support must return 'full'"
        )

    def test_tsserver_reports_none_multi_root_support(self, tsserver_adapter):
        """
        WHY: tsserver does NOT support dynamic workspace folder changes.
        EXPECTED: multi_root_support == MultiRootSupport.NONE
        """
        actual = tsserver_adapter.multi_root_support

        assert actual == MultiRootSupport.NONE, (
            f"FAILED: tsserver_adapter.multi_root_support\n"
            f"WHY: tsserver is single-root only per contract (CON-2)\n"
            f"EXPECTED: '{MultiRootSupport.NONE}'\n"
            f"ACTUAL: '{actual}'\n"
            f"GUIDANCE: TsServerAdapter.multi_root_support must return 'none'"
        )

    def test_clangd_reports_none_multi_root_support(self, clangd_adapter):
        """
        WHY: clangd uses compilation database per project, single-root only.
        EXPECTED: multi_root_support == MultiRootSupport.NONE
        """
        actual = clangd_adapter.multi_root_support

        assert actual == MultiRootSupport.NONE, (
            f"FAILED: clangd_adapter.multi_root_support\n"
            f"WHY: clangd is single-root only per contract (CON-2)\n"
            f"EXPECTED: '{MultiRootSupport.NONE}'\n"
            f"ACTUAL: '{actual}'\n"
            f"GUIDANCE: ClangdAdapter.multi_root_support must return 'none'"
        )

    @pytest.mark.parametrize(
        "adapter_type,expected_support", MULTI_ROOT_SUPPORT_TEST_CASES
    )
    def test_contract_multi_root_support_cases(
        self, adapter_registry, adapter_type, expected_support
    ):
        """
        WHY: Verify all contract-defined multi-root support cases.
        Contract Reference: MULTI_ROOT_SUPPORT_TEST_CASES
        """
        from solidlsp.ls_config import Language

        # Map adapter type to language
        # Note: Language enum uses CPP for C/C++ (clangd serves both via CPP enum)
        adapter_type_to_language = {
            "rust-analyzer": Language.RUST,
            "pylsp": Language.PYTHON,
            "gopls": Language.GO,
            "tsserver": Language.TYPESCRIPT,
            "clangd": Language.CPP,
        }

        language = adapter_type_to_language.get(adapter_type)
        if language is None:
            pytest.skip(f"Unknown adapter type: {adapter_type}")

        adapter = adapter_registry.get_adapter(language)
        actual = adapter.multi_root_support

        assert actual == expected_support, (
            f"FAILED: {adapter_type} multi_root_support\n"
            f"WHY: Contract defines expected support level\n"
            f"EXPECTED: '{expected_support}'\n"
            f"ACTUAL: '{actual}'\n"
            f"GUIDANCE: Adapter must return contract-defined support level"
        )


# =============================================================================
# TEST: can_serve_path Behavior
# =============================================================================


class TestCanServePath:
    """
    Tests for can_serve_path method.

    Contract Reference: LSPCapabilityAdapterContract.can_serve_path
    PRE: ls is running SolidLanguageServer instance
    PRE: path is absolute path to file or directory
    POST: Returns True if LSP can provide symbols/diagnostics for path
    POST: Returns False if LSP cannot serve this path
    """

    def test_multi_root_can_serve_path_under_workspace(
        self, rust_adapter, mock_language_server
    ):
        """
        WHY: Multi-root LSP should serve paths under registered workspace folders.
        EXPECTED: can_serve_path returns True for path under workspace root.
        """
        mock_language_server.workspace_roots = [Path("/project-a")]
        path = Path("/project-a/src/main.rs")

        result = rust_adapter.can_serve_path(mock_language_server, path)

        assert result is True, (
            f"FAILED: can_serve_path for path under workspace\n"
            f"WHY: Multi-root LSP must serve paths under workspace folders\n"
            f"EXPECTED: True\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Check if path.relative_to(workspace_root) succeeds"
        )

    def test_multi_root_cannot_serve_path_outside_workspace(
        self, rust_adapter, mock_language_server
    ):
        """
        WHY: Multi-root LSP should NOT serve paths outside workspace folders.
        EXPECTED: can_serve_path returns False for path outside workspace.
        """
        mock_language_server.workspace_roots = [Path("/project-a")]
        path = Path("/project-b/src/main.rs")

        result = rust_adapter.can_serve_path(mock_language_server, path)

        assert result is False, (
            f"FAILED: can_serve_path for path outside workspace\n"
            f"WHY: Must reject paths not under any workspace folder\n"
            f"EXPECTED: False\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Path must be under at least one workspace root"
        )

    def test_multi_root_can_serve_path_under_second_workspace(
        self, rust_adapter, mock_language_server
    ):
        """
        WHY: Multi-root LSP with multiple workspace folders.
        EXPECTED: can_serve_path returns True for path under second workspace.
        """
        mock_language_server.workspace_roots = [
            Path("/project-a"),
            Path("/project-b"),
        ]
        path = Path("/project-b/src/lib.rs")

        result = rust_adapter.can_serve_path(mock_language_server, path)

        assert result is True, (
            f"FAILED: can_serve_path for path under second workspace\n"
            f"WHY: Must check ALL workspace folders, not just first\n"
            f"EXPECTED: True\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Iterate through all workspace_roots"
        )

    def test_single_root_can_serve_path_under_root_uri(
        self, tsserver_adapter, mock_language_server
    ):
        """
        WHY: Single-root LSP should serve paths under its root URI.
        EXPECTED: can_serve_path returns True for path under root_uri.
        """
        mock_language_server.root_uri = Path("/project-a")
        path = Path("/project-a/src/index.ts")

        result = tsserver_adapter.can_serve_path(mock_language_server, path)

        assert result is True, (
            f"FAILED: can_serve_path for single-root LSP\n"
            f"WHY: Single-root LSP must serve paths under root_uri\n"
            f"EXPECTED: True\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Check path.relative_to(root_uri)"
        )

    def test_single_root_cannot_serve_path_outside_root_uri(
        self, tsserver_adapter, mock_language_server
    ):
        """
        WHY: Single-root LSP should NOT serve paths outside its root URI.
        EXPECTED: can_serve_path returns False for path outside root_uri.
        """
        mock_language_server.root_uri = Path("/project-a")
        path = Path("/project-b/src/index.ts")

        result = tsserver_adapter.can_serve_path(mock_language_server, path)

        assert result is False, (
            f"FAILED: can_serve_path for path outside root_uri\n"
            f"WHY: Single-root LSP cannot serve outside its root\n"
            f"EXPECTED: False\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Single-root LSP scoped to root_uri only"
        )

    @pytest.mark.parametrize(
        "workspace_roots,query_path,expected_result", CAN_SERVE_PATH_TEST_CASES
    )
    def test_contract_can_serve_path_cases(
        self,
        rust_adapter,
        mock_language_server,
        workspace_roots,
        query_path,
        expected_result,
    ):
        """
        WHY: Verify all contract-defined can_serve_path cases.
        Contract Reference: CAN_SERVE_PATH_TEST_CASES
        """
        mock_language_server.workspace_roots = workspace_roots

        result = rust_adapter.can_serve_path(mock_language_server, query_path)

        assert result == expected_result, (
            f"FAILED: Contract can_serve_path test case\n"
            f"WHY: Contract defines expected behavior\n"
            f"EXPECTED: {expected_result}\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Implementation must match contract test case"
        )


# =============================================================================
# TEST: add_workspace_root Behavior
# =============================================================================


class TestAddWorkspaceRoot:
    """
    Tests for add_workspace_root method.

    Contract Reference: LSPCapabilityAdapterContract.add_workspace_root
    PRE: ls is running SolidLanguageServer instance
    PRE: root is absolute path to project root
    PRE: multi_root_support != NONE
    POST: If successful, returns True
    POST: If failed (or not supported), returns False
    POST: On success, LSP now serves paths under root
    """

    def test_multi_root_add_workspace_root_succeeds(
        self, rust_adapter, mock_language_server
    ):
        """
        Enforces: POST-3 (On success, LSP now serves paths under root)

        WHY: Multi-root LSP should successfully add workspace roots.
        EXPECTED: add_workspace_root returns True AND sends LSP notification.
        """
        mock_language_server.workspace_roots = []
        root = Path("/project-a")

        result = rust_adapter.add_workspace_root(mock_language_server, root)

        # POST-3 assertion: Returns True on success
        assert result is True, (
            f"POST-3 violation: add_workspace_root did not return True\n"
            f"WHY: Multi-root adapter must support adding workspace roots\n"
            f"EXPECTED: True\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Return True after sending notification"
        )

        # POST-3 assertion: LSP notification was sent
        mock_language_server.server.notify.did_change_workspace_folders.assert_called_once()
        call_args = mock_language_server.server.notify.did_change_workspace_folders.call_args[0][0]
        assert len(call_args["event"]["added"]) == 1, (
            f"POST-3 violation: workspace/didChangeWorkspaceFolders not sent correctly\n"
            f"WHY: LSP must be notified of new workspace folder\n"
            f"EXPECTED: event.added contains 1 WorkspaceFolder\n"
            f"ACTUAL: event.added contains {len(call_args['event']['added'])} items\n"
            f"GUIDANCE: Send notification with added=[WorkspaceFolder(uri, name)]"
        )
        assert call_args["event"]["added"][0]["uri"] == root.as_uri(), (
            f"POST-3 violation: Wrong URI in notification\n"
            f"WHY: Notification must contain the correct root URI\n"
            f"EXPECTED: {root.as_uri()}\n"
            f"ACTUAL: {call_args['event']['added'][0]['uri']}\n"
            f"GUIDANCE: Use root.as_uri() to convert Path to URI"
        )

        # POST-3 assertion: Root added to tracking
        assert root in mock_language_server.workspace_roots, (
            f"POST-3 violation: Root not added to workspace_roots tracking\n"
            f"WHY: LSP instance must track which roots it serves\n"
            f"EXPECTED: {root} in workspace_roots\n"
            f"ACTUAL: workspace_roots = {mock_language_server.workspace_roots}\n"
            f"GUIDANCE: Append root to ls.workspace_roots after notification"
        )

    def test_single_root_add_workspace_root_fails(
        self, tsserver_adapter, mock_language_server
    ):
        """
        WHY: Single-root LSP cannot add workspace roots dynamically.
        EXPECTED: add_workspace_root returns False for single-root adapter.
        """
        root = Path("/project-a")

        result = tsserver_adapter.add_workspace_root(mock_language_server, root)

        assert result is False, (
            f"FAILED: add_workspace_root for single-root LSP\n"
            f"WHY: Single-root adapter cannot add workspace roots (CON-2)\n"
            f"EXPECTED: False\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Return False immediately for single-root LSP"
        )

    def test_clangd_add_workspace_root_fails(
        self, clangd_adapter, mock_language_server
    ):
        """
        WHY: clangd is single-root, cannot add workspace roots.
        EXPECTED: add_workspace_root returns False.
        """
        root = Path("/project-a")

        result = clangd_adapter.add_workspace_root(mock_language_server, root)

        assert result is False, (
            f"FAILED: add_workspace_root for clangd\n"
            f"WHY: clangd is single-root only (compilation database per project)\n"
            f"EXPECTED: False\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Return False for all single-root adapters"
        )


# =============================================================================
# TEST: remove_workspace_root Behavior
# =============================================================================


class TestRemoveWorkspaceRoot:
    """
    Tests for remove_workspace_root method.

    Contract Reference: LSPCapabilityAdapterContract.remove_workspace_root
    PRE: ls is running SolidLanguageServer instance
    PRE: root is absolute path previously added
    POST: If successful, returns True
    POST: If failed (or not supported), returns False
    POST: On success, LSP no longer serves paths under root
    """

    def test_multi_root_remove_workspace_root_succeeds(
        self, rust_adapter, mock_language_server
    ):
        """
        Enforces: POST-3 (On success, LSP no longer serves paths under root)

        WHY: Multi-root LSP should successfully remove workspace roots.
        EXPECTED: remove_workspace_root returns True AND sends LSP notification.
        """
        root = Path("/project-a")
        mock_language_server.workspace_roots = [root]

        result = rust_adapter.remove_workspace_root(mock_language_server, root)

        # POST-3 assertion: Returns True on success
        assert result is True, (
            f"POST-3 violation: remove_workspace_root did not return True\n"
            f"WHY: Multi-root adapter must support removing workspace roots\n"
            f"EXPECTED: True\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Return True after sending notification"
        )

        # POST-3 assertion: LSP notification was sent
        mock_language_server.server.notify.did_change_workspace_folders.assert_called_once()
        call_args = mock_language_server.server.notify.did_change_workspace_folders.call_args[0][0]
        assert len(call_args["event"]["removed"]) == 1, (
            f"POST-3 violation: workspace/didChangeWorkspaceFolders not sent correctly\n"
            f"WHY: LSP must be notified of removed workspace folder\n"
            f"EXPECTED: event.removed contains 1 WorkspaceFolder\n"
            f"ACTUAL: event.removed contains {len(call_args['event']['removed'])} items\n"
            f"GUIDANCE: Send notification with removed=[WorkspaceFolder(uri, name)]"
        )
        assert call_args["event"]["removed"][0]["uri"] == root.as_uri(), (
            f"POST-3 violation: Wrong URI in notification\n"
            f"WHY: Notification must contain the correct root URI\n"
            f"EXPECTED: {root.as_uri()}\n"
            f"ACTUAL: {call_args['event']['removed'][0]['uri']}\n"
            f"GUIDANCE: Use root.as_uri() to convert Path to URI"
        )

        # POST-3 assertion: Root removed from tracking
        assert root not in mock_language_server.workspace_roots, (
            f"POST-3 violation: Root not removed from workspace_roots tracking\n"
            f"WHY: LSP instance must update its tracking after removal\n"
            f"EXPECTED: {root} not in workspace_roots\n"
            f"ACTUAL: workspace_roots = {mock_language_server.workspace_roots}\n"
            f"GUIDANCE: Remove root from ls.workspace_roots after notification"
        )

    def test_single_root_remove_workspace_root_fails(
        self, tsserver_adapter, mock_language_server
    ):
        """
        WHY: Single-root LSP cannot remove workspace roots (must terminate).
        EXPECTED: remove_workspace_root returns False for single-root adapter.
        """
        root = Path("/project-a")

        result = tsserver_adapter.remove_workspace_root(mock_language_server, root)

        assert result is False, (
            f"FAILED: remove_workspace_root for single-root LSP\n"
            f"WHY: Single-root adapter cannot remove roots, must terminate instance\n"
            f"EXPECTED: False\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Return False, caller must terminate instance instead"
        )


# =============================================================================
# TEST: get_workspace_roots Behavior
# =============================================================================


class TestGetWorkspaceRoots:
    """
    Tests for get_workspace_roots method.

    Contract Reference: LSPCapabilityAdapterContract.get_workspace_roots
    PRE: ls is running SolidLanguageServer instance
    POST: Returns list of absolute Paths (possibly empty)
    POST: For single-root LSPs, returns list with one element
    """

    def test_multi_root_returns_all_workspace_roots(
        self, rust_adapter, mock_language_server
    ):
        """
        WHY: get_workspace_roots should return all registered roots.
        EXPECTED: Returns list matching workspace_roots attribute.
        """
        expected_roots = [Path("/project-a"), Path("/project-b")]
        mock_language_server.workspace_roots = expected_roots

        result = rust_adapter.get_workspace_roots(mock_language_server)

        assert result == expected_roots, (
            f"FAILED: get_workspace_roots for multi-root LSP\n"
            f"WHY: Must return all registered workspace folders\n"
            f"EXPECTED: {expected_roots}\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Return ls.workspace_roots"
        )

    def test_single_root_returns_root_uri_as_list(
        self, tsserver_adapter, mock_language_server
    ):
        """
        WHY: Single-root LSP should return root_uri as single-element list.
        EXPECTED: Returns [root_uri].
        """
        mock_language_server.root_uri = Path("/project-a")

        result = tsserver_adapter.get_workspace_roots(mock_language_server)

        assert result == [Path("/project-a")], (
            f"FAILED: get_workspace_roots for single-root LSP\n"
            f"WHY: Single-root must return root_uri as single-element list\n"
            f"EXPECTED: [Path('/project-a')]\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Return [ls.root_uri] for single-root adapters"
        )

    def test_empty_workspace_roots(self, rust_adapter, mock_language_server):
        """
        WHY: get_workspace_roots should return empty list when no roots.
        EXPECTED: Returns empty list.
        """
        mock_language_server.workspace_roots = []

        result = rust_adapter.get_workspace_roots(mock_language_server)

        assert result == [], (
            f"FAILED: get_workspace_roots with no roots\n"
            f"WHY: Should return empty list when no workspace folders registered\n"
            f"EXPECTED: []\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: Return empty list, not None"
        )


# =============================================================================
# TEST: detect_capabilities Behavior (DD-6)
# =============================================================================


class TestDetectCapabilities:
    """
    Tests for detect_capabilities method.

    Contract Reference: LSPCapabilityAdapterContract.detect_capabilities
    DD-6: Capability detection sequence - probe before workspace registration

    PRE: ls is running and initialized
    PRE: initialize response received
    POST: Returns dict with capability information
    POST: Keys include: "workspace.workspaceFolders", etc.
    """

    def test_detect_capabilities_returns_dict(self, rust_adapter, mock_language_server):
        """
        WHY: detect_capabilities must return capability dict.
        EXPECTED: Returns dict with workspace.workspaceFolders key.
        """
        # Mock LSP capabilities (from initialize response)
        mock_language_server.server_capabilities = {
            "workspace": {"workspaceFolders": {"supported": True}}
        }

        result = rust_adapter.detect_capabilities(mock_language_server)

        assert isinstance(result, dict), (
            f"FAILED: detect_capabilities return type\n"
            f"WHY: Must return capability dict per DD-6\n"
            f"EXPECTED: dict\n"
            f"ACTUAL: {type(result)}\n"
            f"GUIDANCE: Parse ServerCapabilities and return structured dict"
        )

    def test_detect_capabilities_includes_workspace_folders_key(
        self, rust_adapter, mock_language_server
    ):
        """
        WHY: Capability dict must include workspace.workspaceFolders info.
        EXPECTED: Dict has 'workspace.workspaceFolders' key.
        """
        mock_language_server.server_capabilities = {
            "workspace": {"workspaceFolders": {"supported": True}}
        }

        result = rust_adapter.detect_capabilities(mock_language_server)

        assert "workspace.workspaceFolders" in result, (
            f"FAILED: detect_capabilities missing key\n"
            f"WHY: Must include workspace.workspaceFolders capability per contract\n"
            f"EXPECTED: 'workspace.workspaceFolders' in result\n"
            f"ACTUAL: {list(result.keys())}\n"
            f"GUIDANCE: Parse workspace.workspaceFolders from ServerCapabilities"
        )

    def test_detect_capabilities_single_root_reports_no_workspace_folders(
        self, tsserver_adapter, mock_language_server
    ):
        """
        WHY: Single-root LSP should report no workspace folder support.
        EXPECTED: workspace.workspaceFolders is False or not supported.
        """
        mock_language_server.server_capabilities = {}  # tsserver has no workspace folders

        result = tsserver_adapter.detect_capabilities(mock_language_server)

        workspace_folders = result.get("workspace.workspaceFolders", False)
        assert workspace_folders is False or workspace_folders == {"supported": False}, (
            f"FAILED: detect_capabilities for single-root\n"
            f"WHY: Single-root LSP must not claim workspace folder support\n"
            f"EXPECTED: False or {{'supported': False}}\n"
            f"ACTUAL: {workspace_folders}\n"
            f"GUIDANCE: Return False for workspace.workspaceFolders"
        )


# =============================================================================
# TEST: Adapter Registry
# =============================================================================


class TestAdapterRegistry:
    """
    Tests for LSPAdapterRegistry.

    Contract Reference: LSPAdapterRegistryContract
    - get_adapter(language) returns adapter for language
    - register_adapter(language, adapter) registers adapter
    - Default adapter assumes single-root (conservative)
    """

    def test_get_adapter_returns_rust_adapter_for_rust(self, adapter_registry):
        """
        WHY: Registry must return correct adapter for Rust.
        EXPECTED: get_adapter(RUST) returns RustAnalyzerAdapter.
        """
        from serena.lsp_capability_adapter import RustAnalyzerAdapter
        from solidlsp.ls_config import Language

        adapter = adapter_registry.get_adapter(Language.RUST)

        assert isinstance(adapter, RustAnalyzerAdapter), (
            f"FAILED: get_adapter for RUST\n"
            f"WHY: Must return RustAnalyzerAdapter for Rust language\n"
            f"EXPECTED: RustAnalyzerAdapter instance\n"
            f"ACTUAL: {type(adapter)}\n"
            f"GUIDANCE: Register RustAnalyzerAdapter for Language.RUST"
        )

    def test_get_adapter_returns_tsserver_adapter_for_typescript(self, adapter_registry):
        """
        WHY: Registry must return correct adapter for TypeScript.
        EXPECTED: get_adapter(TYPESCRIPT) returns TsServerAdapter.
        """
        from serena.lsp_capability_adapter import TsServerAdapter
        from solidlsp.ls_config import Language

        adapter = adapter_registry.get_adapter(Language.TYPESCRIPT)

        assert isinstance(adapter, TsServerAdapter), (
            f"FAILED: get_adapter for TYPESCRIPT\n"
            f"WHY: Must return TsServerAdapter for TypeScript language\n"
            f"EXPECTED: TsServerAdapter instance\n"
            f"ACTUAL: {type(adapter)}\n"
            f"GUIDANCE: Register TsServerAdapter for Language.TYPESCRIPT"
        )

    def test_get_adapter_returns_default_for_unknown_language(self, adapter_registry):
        """
        WHY: Unknown language should get conservative default adapter.
        EXPECTED: Default adapter with multi_root_support == NONE.
        """
        from solidlsp.ls_config import Language

        # Use a language that might not have a specific adapter
        adapter = adapter_registry.get_adapter(Language.PERL)

        # Default should be conservative (single-root)
        assert adapter.multi_root_support == MultiRootSupport.NONE, (
            f"FAILED: Default adapter multi_root_support\n"
            f"WHY: Default adapter must be conservative (single-root)\n"
            f"EXPECTED: '{MultiRootSupport.NONE}'\n"
            f"ACTUAL: '{adapter.multi_root_support}'\n"
            f"GUIDANCE: DefaultAdapter.multi_root_support must return 'none'"
        )

    def test_register_adapter_overwrites_existing(self, adapter_registry):
        """
        WHY: register_adapter should overwrite existing adapter.
        EXPECTED: New adapter replaces old adapter for same language.
        """
        from serena.lsp_capability_adapter import LSPCapabilityAdapterContract
        from solidlsp.ls_config import Language

        class CustomAdapter(LSPCapabilityAdapterContract):
            @property
            def language(self):
                return Language.RUST

            @property
            def multi_root_support(self):
                return MultiRootSupport.PARTIAL

            def can_serve_path(self, ls, path):
                return True

            def add_workspace_root(self, ls, root):
                return True

            def remove_workspace_root(self, ls, root):
                return True

            def get_workspace_roots(self, ls):
                return []

            def detect_capabilities(self, ls):
                return {}

            def get_pooling_policy(self):
                from serena.lsp_capability_adapter import PoolingPolicy

                return PoolingPolicy.ISOLATED_PROCESS

            def get_launch_arguments(self, workspace_root, session_id):
                return []

        custom_adapter = CustomAdapter()
        adapter_registry.register_adapter(Language.RUST, custom_adapter)

        retrieved = adapter_registry.get_adapter(Language.RUST)

        assert retrieved is custom_adapter, (
            f"FAILED: register_adapter overwrite\n"
            f"WHY: register_adapter must overwrite existing adapter\n"
            f"EXPECTED: custom_adapter instance\n"
            f"ACTUAL: {retrieved}\n"
            f"GUIDANCE: Store adapter in dict, overwrite if key exists"
        )


# =============================================================================
# TEST: Language Property
# =============================================================================


class TestLanguageProperty:
    """
    Tests that adapters report correct language.

    Contract Reference: LSPCapabilityAdapterContract.language
    """

    def test_rust_adapter_language(self, rust_adapter):
        """
        WHY: Adapter must report its language.
        EXPECTED: language == Language.RUST
        """
        from solidlsp.ls_config import Language

        assert rust_adapter.language == Language.RUST, (
            f"FAILED: rust_adapter.language\n"
            f"WHY: Adapter must report correct language\n"
            f"EXPECTED: Language.RUST\n"
            f"ACTUAL: {rust_adapter.language}\n"
            f"GUIDANCE: Return Language.RUST from language property"
        )

    def test_tsserver_adapter_language(self, tsserver_adapter):
        """
        WHY: Adapter must report its language.
        EXPECTED: language == Language.TYPESCRIPT
        """
        from solidlsp.ls_config import Language

        assert tsserver_adapter.language == Language.TYPESCRIPT, (
            f"FAILED: tsserver_adapter.language\n"
            f"WHY: Adapter must report correct language\n"
            f"EXPECTED: Language.TYPESCRIPT\n"
            f"ACTUAL: {tsserver_adapter.language}\n"
            f"GUIDANCE: Return Language.TYPESCRIPT from language property"
        )


# =============================================================================
# TEST: Invariant - Adapter is Stateless (INV-1, INV-2)
# =============================================================================


class TestAdapterStatelessInvariant:
    """
    Tests that adapters maintain statelessness.

    Contract Invariants:
    - INV-1: Adapter is stateless (all state in LSP instance)
    - INV-2: Methods never modify adapter internal state
    """

    def test_adapter_has_no_mutable_instance_state(self, rust_adapter):
        """
        WHY: Adapter must be stateless per INV-1.
        EXPECTED: No mutable instance attributes.
        """
        # Get instance attributes (excluding methods and class attributes)
        instance_attrs = {
            k: v
            for k, v in vars(rust_adapter).items()
            if not k.startswith("_") and not callable(v)
        }

        assert len(instance_attrs) == 0, (
            f"FAILED: Adapter statelessness INV-1\n"
            f"WHY: Adapter must be stateless, all state in LSP instance\n"
            f"EXPECTED: No mutable instance attributes\n"
            f"ACTUAL: {instance_attrs}\n"
            f"GUIDANCE: Remove instance attributes, store state in ls object"
        )

    def test_multiple_calls_do_not_change_adapter_state(
        self, rust_adapter, mock_language_server
    ):
        """
        WHY: Methods must not modify adapter state per INV-2.
        EXPECTED: Adapter state unchanged after method calls.
        """
        mock_language_server.workspace_roots = [Path("/project-a")]
        mock_language_server.server_capabilities = {"workspace": {}}

        # Capture initial state
        initial_state = dict(vars(rust_adapter))

        # Call various methods
        rust_adapter.can_serve_path(mock_language_server, Path("/project-a/src/main.rs"))
        rust_adapter.get_workspace_roots(mock_language_server)
        rust_adapter.detect_capabilities(mock_language_server)

        # Verify state unchanged
        final_state = dict(vars(rust_adapter))

        assert initial_state == final_state, (
            f"FAILED: Adapter state modified INV-2\n"
            f"WHY: Methods must not modify adapter internal state\n"
            f"EXPECTED: {initial_state}\n"
            f"ACTUAL: {final_state}\n"
            f"GUIDANCE: Store all state in ls object, not adapter"
        )
