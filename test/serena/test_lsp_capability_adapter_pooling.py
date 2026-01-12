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
    Clangd cache path MUST enable session isolation.

    GIVEN: ClangdAdapter instance
    WHEN: get_launch_arguments called with workspace_root and session_id
    THEN: Return list containing --cache-path argument that varies by session

    GUIDANCE (Behavioral):
    - Cache path MUST vary by session_id (different sessions → different paths)
    - Cache path MUST vary by workspace_root (different workspaces → different paths)
    - session_id may be hashed for path safety (SEC-5 path traversal prevention)
    - MUST produce deterministic path for same inputs (no random UUIDs)

    SECURITY NOTE (SEC-5):
    - session_id is hashed before use in path to prevent path traversal attacks
    - An attacker cannot use session_id="../../etc/passwd" to escape cache directory
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
        f"EXPECTED: list (e.g., ['--cache-path=/tmp/clangd-<hash>-<hash>'])\n"
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
        f"GUIDANCE: Include '--cache-path=<path>' with session-unique component"
    )

    # EXPECTED: Cache path starts with expected prefix and has deterministic format
    cache_path = cache_arg.split("=", 1)[1]
    assert cache_path.startswith("/tmp/serena_clangd_"), (
        f"REQ-CLANGD-2 VIOLATED: Cache path format unexpected\n"
        f"WHAT FAILED: Cache path prefix check\n"
        f"WHY: Cache paths should be in /tmp with serena_clangd prefix\n"
        f"EXPECTED: Path starting with '/tmp/serena_clangd_'\n"
        f"ACTUAL: {cache_path}\n"
        f"GUIDANCE: Cache path format: /tmp/serena_clangd_<session_hash>_<workspace_hash>"
    )

    # EXPECTED: Deterministic - same inputs produce same output
    args2 = adapter.get_launch_arguments(workspace, session_id)
    assert args == args2, (
        f"REQ-CLANGD-3 VIOLATED: Non-deterministic cache path\n"
        f"WHAT FAILED: Determinism requirement\n"
        f"WHY: Same inputs MUST produce same cache path for reproducibility\n"
        f"EXPECTED: {args}\n"
        f"ACTUAL: {args2}\n"
        f"GUIDANCE: Cache path computation MUST be deterministic (no random UUIDs)"
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



def test_clangd_session_id_path_traversal_prevention():
    """
    SEC-5: Session ID MUST be sanitized to prevent path traversal attacks.

    GIVEN: ClangdAdapter instance
    WHEN: get_launch_arguments called with malicious session_id containing path traversal
    THEN: Cache path MUST remain within /tmp (no escape via ../)

    GUIDANCE (Behavioral):
    - Malicious session_id="../../etc/passwd" MUST NOT escape /tmp
    - All session_ids produce paths within /tmp/serena_clangd_*
    - Implementation free to: sanitize, hash, validate, or reject
    - CRITICAL SECURITY: Path injection is a CONSTITUTIONAL VIOLATION

    ATTACK VECTOR (Prevented):
    - Attacker controls session_id via MCP session header
    - Without sanitization: --cache-path=/tmp/serena_clangd_../../etc/passwd_hash
    - This could allow reading/writing files outside cache directory
    """
    adapter = ClangdAdapter()
    workspace = Path("/project-a")

    # Malicious session_ids attempting path traversal
    malicious_session_ids = [
        "../../etc/passwd",
        "../../../tmp/evil",
        "session/../../../root",
        "..%2F..%2Fetc%2Fpasswd",  # URL encoded
        "session\x00/etc/passwd",  # Null byte injection
        "/absolute/path/attack",
    ]

    for malicious_id in malicious_session_ids:
        args = adapter.get_launch_arguments(workspace, malicious_id)

        # Find --cache-path argument
        cache_arg = None
        for arg in args:
            if arg.startswith("--cache-path="):
                cache_arg = arg
                break

        assert cache_arg is not None, f"Missing cache-path for session_id={malicious_id!r}"
        cache_path = cache_arg.split("=", 1)[1]

        # CRITICAL: Path must remain in /tmp/serena_clangd_* (no escape)
        assert cache_path.startswith("/tmp/serena_clangd_"), (
            f"SEC-5 VIOLATED: Path traversal attack succeeded\n"
            f"WHAT FAILED: Path sanitization for malicious session_id\n"
            f"WHY: Malicious session_id MUST NOT escape cache directory\n"
            f"EXPECTED: Path starting with '/tmp/serena_clangd_'\n"
            f"ACTUAL: {cache_path}\n"
            f"ATTACK INPUT: session_id={malicious_id!r}\n"
            f"GUIDANCE: session_id MUST be hashed or sanitized before path construction"
        )

        # CRITICAL: No path traversal sequences in final path
        assert ".." not in cache_path, (
            f"SEC-5 VIOLATED: Path contains traversal sequence\n"
            f"WHAT FAILED: Path traversal prevention\n"
            f"WHY: '..' in path allows escaping cache directory\n"
            f"EXPECTED: Path without '..' sequences\n"
            f"ACTUAL: {cache_path}\n"
            f"ATTACK INPUT: session_id={malicious_id!r}\n"
            f"GUIDANCE: Hash session_id to eliminate special characters"
        )

        # CRITICAL: No null bytes (can truncate path)
        assert "\x00" not in cache_path, (
            f"SEC-5 VIOLATED: Path contains null byte\n"
            f"WHAT FAILED: Null byte injection prevention\n"
            f"WHY: Null bytes can truncate paths in C-based systems\n"
            f"EXPECTED: Path without null bytes\n"
            f"ACTUAL: Path contains \\x00\n"
            f"ATTACK INPUT: session_id={malicious_id!r}\n"
            f"GUIDANCE: Hash session_id to eliminate null bytes"
        )
