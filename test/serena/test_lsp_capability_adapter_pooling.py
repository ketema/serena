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
    # NOTE: On macOS, /tmp resolves to /private/tmp via symlink, so check both
    cache_path = cache_arg.split("=", 1)[1]
    valid_prefixes = ("/tmp/serena_clangd_", "/private/tmp/serena_clangd_")
    assert any(cache_path.startswith(prefix) for prefix in valid_prefixes), (
        f"REQ-CLANGD-2 VIOLATED: Cache path format unexpected\n"
        f"WHAT FAILED: Cache path prefix check\n"
        f"WHY: Cache paths should be in /tmp with serena_clangd prefix\n"
        f"EXPECTED: Path starting with '/tmp/serena_clangd_' or '/private/tmp/serena_clangd_' (macOS)\n"
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


# Edge case: Valid session isolation verification
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
    r"""
    SEC-5 (REQ-SEC-SANITY): Path traversal attacks MUST be rejected at Layer 1.

    GIVEN: ClangdAdapter instance
    WHEN: get_launch_arguments called with malicious session_id containing path traversal
    THEN: MUST raise ValueError (Layer 1 validation rejects invalid characters)

    GUIDANCE (Behavioral):
    - REQ-SEC-SANITY mandates three-layer defense: VALIDATE → HASH → VERIFY
    - Layer 1 (VALIDATE): session_id MUST match ^[a-zA-Z0-9\-_]+$
    - Malicious session_ids with /, .., %, null bytes FAIL validation
    - Implementation MUST raise ValueError with "SEC-5 VIOLATION" message
    - CRITICAL SECURITY: Reject early is safer than sanitize late

    ATTACK VECTOR (Prevented):
    - Attacker controls session_id via MCP session header
    - Without validation: --cache-path=/tmp/serena_clangd_../../etc/passwd_hash
    - With REQ-SEC-SANITY: ValueError raised BEFORE path construction
    """
    import pytest

    adapter = ClangdAdapter()
    workspace = Path("/project-a")

    # Malicious session_ids attempting path traversal
    # REQ-SEC-SANITY Layer 1 MUST reject all of these
    malicious_session_ids = [
        ("../../etc/passwd", "path traversal with .."),
        ("../../../tmp/evil", "deep path traversal"),
        ("session/../../../root", "embedded traversal"),
        ("..%2F..%2Fetc%2Fpasswd", "URL encoded traversal"),
        ("session\x00/etc/passwd", "null byte injection"),
        ("/absolute/path/attack", "absolute path injection"),
        ("session/path", "forward slash in session_id"),
        ("session.with.dots", "dots that could be confused with .."),
    ]

    for malicious_id, attack_type in malicious_session_ids:
        # REQ-SEC-SANITY Layer 1: MUST raise ValueError for invalid characters
        with pytest.raises(ValueError) as exc_info:
            adapter.get_launch_arguments(workspace, malicious_id)

        # EXPECTED: ValueError with SEC-5 VIOLATION message
        error_msg = str(exc_info.value)
        assert "SEC-5 VIOLATION" in error_msg, (
            f"REQ-SEC-SANITY VIOLATED: Invalid session_id not rejected properly\n"
            f"WHAT FAILED: Layer 1 validation error message\n"
            f"WHY: Malicious session_id must be rejected with 'SEC-5 VIOLATION' message\n"
            f"EXPECTED: ValueError containing 'SEC-5 VIOLATION'\n"
            f"ACTUAL: ValueError with message: {error_msg}\n"
            f"ATTACK INPUT: session_id={malicious_id!r} ({attack_type})\n"
            f"GUIDANCE: Layer 1 MUST validate session_id against ^[a-zA-Z0-9\\\\-_]+$"
        )

        assert "invalid characters" in error_msg.lower(), (
            f"REQ-SEC-SANITY VIOLATED: Error message doesn't explain rejection reason\n"
            f"WHAT FAILED: Error message clarity\n"
            f"WHY: Error messages should explain what failed\n"
            f"EXPECTED: Message containing 'invalid characters'\n"
            f"ACTUAL: {error_msg}\n"
            f"ATTACK INPUT: session_id={malicious_id!r} ({attack_type})\n"
            f"GUIDANCE: Error message should state what validation failed"
        )


def test_clangd_session_id_unicode_normalization_attacks():
    r"""
    SEC-5 (REQ-SEC-UNICODE): Unicode normalization attacks MUST be prevented.

    GIVEN: ClangdAdapter instance
    WHEN: get_launch_arguments called with session_id containing unicode lookalikes
    THEN: MUST either reject (validation layer) or hash safely (no path interpretation)

    GUIDANCE (Behavioral):
    - U+2044 FRACTION SLASH (⁄) looks like / but is different codepoint
    - U+FF0F FULLWIDTH SOLIDUS (／) is visual equivalent of /
    - U+2215 DIVISION SLASH (∕) another slash lookalike
    - Implementation MUST use validation layer to reject these OR hash them safely
    - Path must NEVER interpret these as actual path separators

    ATTACK VECTOR (Prevented):
    - Attacker uses unicode lookalikes that normalize to ASCII / in some systems
    - Without defense: session_id="..⁄..⁄etc⁄passwd" might normalize to path traversal
    - With three-layer defense: validation rejects non-[a-zA-Z0-9\-_] characters
    """
    adapter = ClangdAdapter()
    workspace = Path("/project-a")

    # Unicode lookalike attack vectors
    unicode_attack_ids = [
        "session\u2044etc\u2044passwd",  # U+2044 FRACTION SLASH
        "session\uff0f..\uff0f..",  # U+FF0F FULLWIDTH SOLIDUS
        "session\u2215root",  # U+2215 DIVISION SLASH
        "..\u2044..\u2044tmp",  # Combined attack
        "session\u0000hidden",  # Null in unicode
        "session\u202e\u002f\u002fetc",  # RTL override + slashes
    ]

    for attack_id in unicode_attack_ids:
        # LAYER 1 VALIDATION: Should reject invalid characters
        # The validation regex ^[a-zA-Z0-9\\-_]+$ rejects unicode
        import pytest

        with pytest.raises(ValueError) as exc_info:
            adapter.get_launch_arguments(workspace, attack_id)

        # EXPECTED: ValueError with SEC-5 VIOLATION message
        assert "SEC-5 VIOLATION" in str(exc_info.value), (
            f"REQ-SEC-UNICODE VIOLATED: Unicode attack not rejected\n"
            f"WHAT FAILED: Validation layer didn't catch unicode lookalike\n"
            f"WHY: Unicode normalization can bypass naive path checks\n"
            f"EXPECTED: ValueError with 'SEC-5 VIOLATION' message\n"
            f"ACTUAL: No exception or wrong exception type\n"
            f"ATTACK INPUT: session_id={attack_id!r} (contains {[hex(ord(c)) for c in attack_id]})\n"
            f"GUIDANCE: Validation MUST reject non-ASCII or use strict allowlist"
        )
