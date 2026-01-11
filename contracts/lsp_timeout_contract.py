"""
Contract: LSPTimeoutManager

Defines the behavioral contract for LSP idle timeout management.
Integrates with existing LSPManager for resource reclamation.
Mocks for tests MUST derive from this contract (CL10).

Component: LSPTimeoutManager
Purpose: Manage per-language idle timeouts for LSP reclamation

SYNC INTERFACE (v2):
- All methods are synchronous (no async/await)
- Background monitoring via daemon threading.Thread (not asyncio.Task)
- Thread-safety via threading.Lock for shared state
- Compatible with sync LanguageServerManager integration points
"""

from datetime import datetime, timedelta
from typing import Any, Callable


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_TIMEOUTS_SECONDS: dict[str, int] = {
    # Heavy LSPs - reclaim faster (high memory footprint)
    "rust": 1800,      # 30 min - rust-analyzer: 500MB-1.5GB
    "java": 1800,      # 30 min - jdtls: 400MB-1GB
    "csharp": 1800,    # 30 min - omnisharp: 300-800MB

    # Medium LSPs - balanced
    "typescript": 3600,  # 1 hr - tsserver: 150-400MB
    "go": 3600,          # 1 hr - gopls: 100-300MB
    "haskell": 3600,     # 1 hr - hls: 200-500MB
    "vue": 3600,         # 1 hr - volar: 100-200MB

    # Light LSPs - keep longer (low memory, fast startup)
    "python": 3600,    # 1 hr - pylsp: 50-150MB (reduced from 2hr per AI Panel)
    "ruby": 3600,      # 1 hr - solargraph: 50-100MB (reduced from 2hr per AI Panel)
    "php": 3600,       # 1 hr - intelephense: 50-150MB

    # Default for unlisted languages
    "default": 3600,   # 1 hr
}


# =============================================================================
# BEHAVIORAL CONTRACTS
# =============================================================================

class LSPTimeoutManagerContract:
    """
    Behavioral contract for LSP timeout management (SYNC v2).

    INVARIANTS:
    - INV-1: All timeout values are positive integers (seconds)
    - INV-2: last_used timestamps are always <= current time
    - INV-3: Monitoring runs in daemon thread without blocking main thread
    - INV-4: All shared state mutations protected by threading.Lock

    PRECONDITIONS:
    - PRE-1 (touch): language is a valid string identifier
    - PRE-2 (get_timeout): language is a valid string identifier
    - PRE-3 (start_monitoring): not already monitoring

    POSTCONDITIONS:
    - POST-1 (touch): last_used[language] updated to current time
    - POST-2 (get_timeout): returns configured timeout or default
    - POST-3 (start_monitoring): daemon thread created and running
    - POST-4 (reclaim): LSP for language is shutdown if idle > timeout
    """

    def touch(self, language: str) -> None:
        """
        Mark a language as recently used.

        PRE: language is non-empty string
        POST: last_used[language] == current_time (within 1 second tolerance)
        """
        ...

    def get_timeout(self, language: str) -> int:
        """
        Get configured timeout for language in seconds.

        PRE: language is non-empty string
        POST: returns int > 0
        POST: if language in config, returns config[language]
        POST: if language not in config, returns config["default"]
        """
        ...

    def start_monitoring(self) -> None:
        """
        Start background monitoring daemon thread (SYNC).

        PRE: not already monitoring (idempotent - safe to call multiple times)
        POST: daemon thread is running
        POST: check_interval is reasonable (60 seconds recommended)

        Thread-safety: Creates daemon thread that runs until stop_monitoring called.
        """
        ...

    def stop_monitoring(self) -> None:
        """
        Stop background monitoring daemon thread (SYNC).

        PRE: none (safe to call even if not monitoring)
        POST: monitoring thread is stopped (via _running flag)

        Thread-safety: Sets _running = False, thread exits on next iteration.
        """
        ...

    def check_and_reclaim(self) -> list[str]:
        """
        Check all languages and reclaim idle LSPs (SYNC).

        PRE: none
        POST: returns list of reclaimed language names
        POST: for each reclaimed language: (now - last_used[lang]) > timeout[lang]

        Thread-safety: Acquires lock when reading/modifying last_used state.
        """
        ...

    def set_reclaim_callback(self, callback: "Callable[[str], None] | None") -> None:
        """
        Set the callback to invoke when an LSP should be reclaimed (SYNC).

        PRE: callback is None or callable taking language string
        POST: callback will be called for each language that exceeds timeout

        NOTE: Callback is SYNC (Callable[[str], None]), not async.
        The callback runs in the monitoring thread context.
        """
        ...


# =============================================================================
# TEST VERIFICATION HELPERS
# =============================================================================

def verify_timeout_defaults() -> bool:
    """Verify default timeout configuration is valid."""
    for lang, timeout in DEFAULT_TIMEOUTS_SECONDS.items():
        if not isinstance(timeout, int) or timeout <= 0:
            return False
    if "default" not in DEFAULT_TIMEOUTS_SECONDS:
        return False
    return True


def verify_idle_detection(
    last_used: datetime,
    timeout_seconds: int,
    current_time: datetime | None = None
) -> bool:
    """Verify if an LSP should be considered idle."""
    now = current_time or datetime.now()
    idle_duration = (now - last_used).total_seconds()
    return idle_duration > timeout_seconds


def create_expired_scenario(timeout_seconds: int) -> datetime:
    """Create a last_used timestamp that is expired."""
    return datetime.now() - timedelta(seconds=timeout_seconds + 60)


def create_active_scenario() -> datetime:
    """Create a last_used timestamp that is still active."""
    return datetime.now() - timedelta(seconds=10)


# =============================================================================
# CONTRACT TEST ASSERTIONS
# =============================================================================

TIMEOUT_TEST_CASES = [
    # (language, expected_timeout, description)
    ("rust", 1800, "Heavy LSP with 30min timeout"),
    ("python", 3600, "Light LSP with 1hr timeout"),
    ("unknown_language", 3600, "Unknown language uses default"),
]

RECLAIM_TEST_CASES = [
    # (idle_seconds, timeout_seconds, should_reclaim, description)
    (100, 3600, False, "Recently used - not reclaimed"),
    (3700, 3600, True, "Idle past timeout - reclaimed"),
    (1800, 1800, False, "Exactly at timeout - not reclaimed (boundary)"),
    (1801, 1800, True, "Just past timeout - reclaimed"),
]
