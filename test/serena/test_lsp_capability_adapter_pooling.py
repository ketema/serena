"""
Test adapter-specific launch arguments for LSP capability pooling.
"""

from pathlib import Path

from serena.lsp_capability_adapter import (
    ClangdAdapter,
    DefaultAdapter,
    TsServerAdapter,
)
from solidlsp.ls_config import Language


# REQ-CLANGD-1, REQ-CLANGD-2, REQ-CLANGD-3: Clangd cache isolation
def test_clangd_cache_path_isolation():
    """
    Clangd cache path MUST contain session_id for isolation.

    GIVEN: ClangdAdapter instance
    WHEN: get_launch_arguments called with workspace_root and session_id
    THEN: Return list containing --cache-path argument with session_id embedded

    GUIDANCE (Behavioral):
    - Cache path MUST contain session_id substring for session isolation
    - Cache path MUST differ between different workspace_roots
    - Implementation free to choose: tempdir, hash, or path combination
    - MUST produce deterministic path for same inputs (no random UUIDs)
    """
    adapter = ClangdAdapter()
    workspace = Path("/project-a")
    session_id = "session-123"

    args = adapter.get_launch_arguments(workspace, session_id)

    # EXPECTED: List containing --cache-path argument
    assert isinstance(args, list), (
        f"REQ-CLANGD-1 VIOLATED: get_launch_arguments must return list\n"
        f"WHAT FAILED: Type check\n"
        f"WHY: Clangd requires cache-path argument for session isolation\n"
        f"EXPECTED: list (e.g., ['--cache-path=/tmp/clangd-session-123-hash'])\n"
        f"ACTUAL: {type(args).__name__}\n"
        f"GUIDANCE: Return list of string arguments for Clangd LSP launch"
    )

    # Find --cache-path argument
    cache_arg = None
    for arg in args:
        if arg.startswith("--cache-path="):
            cache_arg = arg
            break

    assert cache_arg is not None, (
        f"REQ-CLANGD-1 VIOLATED: Missing --cache-path argument\n"
        f"WHAT FAILED: Cache path argument presence\n"
        f"WHY: Clangd requires cache path for session isolation\n"
        f"EXPECTED: List containing string starting with '--cache-path='\n"
        f"ACTUAL: {args}\n"
        f"GUIDANCE: Include '--cache-path=<path>' where path contains session_id"
    )

    # EXPECTED: Cache path contains session_id
    assert session_id in cache_arg, (
        f"REQ-CLANGD-2 VIOLATED: Cache path missing session_id\n"
        f"WHAT FAILED: Session isolation requirement\n"
        f"WHY: Different sessions MUST use different cache directories\n"
        f"EXPECTED: Cache path containing 'session-123'\n"
        f"ACTUAL: {cache_arg}\n"
        f"GUIDANCE: Cache path MUST embed session_id substring for isolation"
    )


def test_clangd_workspace_uniqueness():
    """
    Clangd cache path MUST differ for different workspace_roots.

    GIVEN: ClangdAdapter with same session_id
    WHEN: get_launch_arguments called with different workspace_roots
    THEN: Cache paths MUST be different (workspace isolation)

    GUIDANCE (Behavioral):
    - Different workspace_roots → different cache paths
    - MUST use workspace_root in path generation (hash, basename, or full path)
    - Prevents cache contamination between projects
    """
    adapter = ClangdAdapter()
    session_id = "session-456"

    args_a = adapter.get_launch_arguments(Path("/project-a"), session_id)
    args_b = adapter.get_launch_arguments(Path("/project-b"), session_id)

    # Extract cache paths
    cache_path_a = None
    cache_path_b = None

    for arg in args_a:
        if arg.startswith("--cache-path="):
            cache_path_a = arg
            break

    for arg in args_b:
        if arg.startswith("--cache-path="):
            cache_path_b = arg
            break

    assert cache_path_a is not None and cache_path_b is not None, (
        f"REQ-CLANGD-1 VIOLATED: Missing cache path in one or both results\n"
        f"WHAT FAILED: Cache path argument presence\n"
        f"WHY: Clangd requires cache path for workspace isolation\n"
        f"EXPECTED: Both results contain '--cache-path=...' argument\n"
        f"ACTUAL: args_a={args_a}, args_b={args_b}\n"
        f"GUIDANCE: Return '--cache-path=<path>' for all workspace_roots"
    )

    # EXPECTED: Different cache paths for different workspaces
    assert cache_path_a != cache_path_b, (
        f"REQ-CLANGD-3 VIOLATED: Workspace isolation failure\n"
        f"WHAT FAILED: Cache path uniqueness\n"
        f"WHY: Different projects MUST use different cache directories\n"
        f"EXPECTED: Different cache paths for /project-a vs /project-b\n"
        f"ACTUAL: Both use {cache_path_a}\n"
        f"GUIDANCE: Cache path MUST incorporate workspace_root (hash, basename, or full path)"
    )


def test_clangd_deterministic_cache_path():
    """
    Clangd cache path MUST be deterministic for same inputs.

    GIVEN: ClangdAdapter with same workspace_root and session_id
    WHEN: get_launch_arguments called multiple times
    THEN: Cache paths MUST be identical (no random components)

    GUIDANCE (Behavioral):
    - Same workspace_root + session_id → same cache path
    - MUST NOT use random UUIDs or timestamps
    - Deterministic path allows caching and reproducibility
    """
    adapter = ClangdAdapter()
    workspace = Path("/project-a")
    session_id = "session-789"

    args_1 = adapter.get_launch_arguments(workspace, session_id)
    args_2 = adapter.get_launch_arguments(workspace, session_id)

    # Extract cache paths
    cache_path_1 = None
    cache_path_2 = None

    for arg in args_1:
        if arg.startswith("--cache-path="):
            cache_path_1 = arg
            break

    for arg in args_2:
        if arg.startswith("--cache-path="):
            cache_path_2 = arg
            break

    # EXPECTED: Identical cache paths for same inputs
    assert cache_path_1 == cache_path_2, (
        f"REQ-CLANGD-3 VIOLATED: Non-deterministic cache path\n"
        f"WHAT FAILED: Determinism requirement\n"
        f"WHY: Same inputs MUST produce same cache path for reproducibility\n"
        f"EXPECTED: Identical cache paths for same workspace_root + session_id\n"
        f"ACTUAL: First call={cache_path_1}, Second call={cache_path_2}\n"
        f"GUIDANCE: Use deterministic hash/path (no random UUIDs or timestamps)"
    )


# REQ-TS-1, REQ-TS-2: TypeScript base behavior (optional resource management)
def test_tsserver_base_implementation():
    """
    TsServerAdapter MAY return memory limit arguments (optional).

    GIVEN: TsServerAdapter instance
    WHEN: get_launch_arguments called
    THEN: Returns list (may be empty per base implementation)

    GUIDANCE (Behavioral):
    - Current base implementation returns empty list (no resource management yet)
    - Future enhancement: may return memory limit arguments
    - This test ensures method exists and returns list type
    """
    adapter = TsServerAdapter()
    workspace = Path("/project")
    session_id = "session-ts-1"

    args = adapter.get_launch_arguments(workspace, session_id)

    # EXPECTED: Returns list (may be empty)
    assert isinstance(args, list), (
        f"REQ-TS-1 VIOLATED: get_launch_arguments must return list\n"
        f"WHAT FAILED: Type check\n"
        f"WHY: Base adapter interface requires list return type\n"
        f"EXPECTED: list (empty or with memory limit arguments)\n"
        f"ACTUAL: {type(args).__name__}\n"
        f"GUIDANCE: Return list of string arguments (empty list if no special args)"
    )

    # NOTE: Empty list is valid per REQ-TS-2 (base implementation)
    # No assertion on content - optional memory management


# REQ-DEFAULT-1: DefaultAdapter returns empty list (conservative)
def test_default_adapter_empty_list():
    """
    DefaultAdapter returns empty list (no special args for unknown LSPs).

    GIVEN: DefaultAdapter instance
    WHEN: get_launch_arguments called
    THEN: Returns empty list (conservative - no assumptions about unknown LSP)

    GUIDANCE (Behavioral):
    - Unknown LSPs get no special arguments (conservative)
    - Prevents breaking LSPs with unsupported flags
    - Implementation MUST return empty list (not None, not error)
    """
    adapter = DefaultAdapter(Language.BASH)  # Unknown language
    workspace = Path("/project")
    session_id = "session-default-1"

    args = adapter.get_launch_arguments(workspace, session_id)

    # EXPECTED: Empty list for unknown LSP
    assert args == [], (
        f"REQ-DEFAULT-1 VIOLATED: DefaultAdapter must return empty list\n"
        f"WHAT FAILED: Conservative behavior requirement\n"
        f"WHY: Unknown LSPs should get no special arguments to avoid breakage\n"
        f"EXPECTED: [] (empty list)\n"
        f"ACTUAL: {args}\n"
        f"GUIDANCE: Return empty list for DefaultAdapter (no assumptions about unknown LSP)"
    )


# Edge case: Session isolation verification
def test_clangd_different_sessions_different_cache():
    """
    Different session_ids MUST produce different cache paths.

    GIVEN: ClangdAdapter with same workspace_root
    WHEN: get_launch_arguments called with different session_ids
    THEN: Cache paths MUST be different (session isolation)

    GUIDANCE (Behavioral):
    - session_id differentiation is primary isolation mechanism
    - Prevents session A from reading session B's cache
    - Critical for multi-session support
    """
    adapter = ClangdAdapter()
    workspace = Path("/project-shared")

    args_session_a = adapter.get_launch_arguments(workspace, "session-a")
    args_session_b = adapter.get_launch_arguments(workspace, "session-b")

    # Extract cache paths
    cache_path_a = None
    cache_path_b = None

    for arg in args_session_a:
        if arg.startswith("--cache-path="):
            cache_path_a = arg
            break

    for arg in args_session_b:
        if arg.startswith("--cache-path="):
            cache_path_b = arg
            break

    # EXPECTED: Different cache paths for different sessions
    assert cache_path_a != cache_path_b, (
        f"REQ-CLANGD-2 VIOLATED: Session isolation failure\n"
        f"WHAT FAILED: Session-specific cache paths\n"
        f"WHY: Different sessions MUST use different cache directories\n"
        f"EXPECTED: Different cache paths for 'session-a' vs 'session-b'\n"
        f"ACTUAL: Both use {cache_path_a}\n"
        f"GUIDANCE: Cache path MUST embed session_id for isolation (critical for multi-session)"
    )
