"""LSP idle timeout management with automatic resource reclamation."""

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from contracts.lsp_timeout_contract import DEFAULT_TIMEOUTS_SECONDS

logger = logging.getLogger(__name__)


class LSPTimeoutManager:
    """
    Manages per-language idle timeouts for LSP resource reclamation.

    Implements behavioral contract from contracts/lsp_timeout_contract.py.
    Tracks last-used timestamps and triggers reclamation for idle LSPs.
    """

    def __init__(
        self,
        timeout_config: dict[str, int] | None = None,
        check_interval: int = 60,
    ) -> None:
        """
        Initialize timeout manager.

        Args:
            timeout_config: Optional custom timeout config. Defaults to DEFAULT_TIMEOUTS_SECONDS.
            check_interval: Seconds between idle checks (default: 60).

        """
        # Use contract defaults if no custom config provided (avoid default arg binding)
        if timeout_config is not None:
            self._timeout_config = timeout_config
        else:
            self._timeout_config = DEFAULT_TIMEOUTS_SECONDS

        self._check_interval = check_interval
        self._last_used: dict[str, datetime] = {}
        self._monitoring_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._reclaim_callback: Callable[[str], None] | None = None

    def get_timeout(self, language: str) -> int:
        """
        Get configured timeout for language in seconds.

        Returns configured value or default if language not in config.
        """
        # Try language-specific timeout, then 'default' from config, then contract default
        if language in self._timeout_config:
            return self._timeout_config[language]
        if "default" in self._timeout_config:
            return self._timeout_config["default"]
        return DEFAULT_TIMEOUTS_SECONDS["default"]

    def touch(self, language: str) -> None:
        """
        Mark a language as recently used.

        Updates last_used[language] to current time.
        """
        self._last_used[language] = datetime.now()

    def get_last_used(self, language: str) -> datetime | None:
        """
        Get last used timestamp for language.

        Returns None if language has never been touched.
        """
        return self._last_used.get(language)

    def start_monitoring(self) -> None:
        """
        Start background monitoring thread.

        Creates daemon thread that periodically checks for idle LSPs.
        Idempotent - safe to call multiple times.
        """
        if self._monitoring_thread is not None and self._monitoring_thread.is_alive():
            return  # Already monitoring

        self._stop_event.clear()
        self._monitoring_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitoring_thread.start()

    def stop_monitoring(self) -> None:
        """
        Stop background monitoring thread.

        Signals stop event and waits for thread to finish.
        Safe to call even if not monitoring.
        """
        if self._monitoring_thread is not None and self._monitoring_thread.is_alive():
            self._stop_event.set()
            self._monitoring_thread.join(timeout=5.0)

    def is_monitoring(self) -> bool:
        """
        Check if monitoring thread is running.

        Returns True if background thread is active.
        """
        return self._monitoring_thread is not None and self._monitoring_thread.is_alive()

    def check_and_reclaim(self) -> list[str]:
        """
        Check all languages and reclaim idle LSPs.

        Returns list of reclaimed language names.
        For each reclaimed language: (now - last_used[lang]) > timeout[lang]
        """
        reclaimed: list[str] = []
        now = datetime.now()

        for language, last_used in self._last_used.items():
            idle_time = (now - last_used).total_seconds()
            timeout = self.get_timeout(language)

            if idle_time > timeout:
                reclaimed.append(language)
                if self._reclaim_callback is not None:
                    self._reclaim_callback(language)

        return reclaimed

    def set_reclaim_callback(self, callback: Callable[[str], None]) -> None:
        """
        Set callback for when an LSP needs to be reclaimed.

        Callback is called with language name when idle timeout exceeded.
        """
        self._reclaim_callback = callback

    def _monitor_loop(self) -> None:
        """Background thread that periodically checks for idle LSPs."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._check_interval)
            if self._stop_event.is_set():
                break
            try:
                self.check_and_reclaim()
            except Exception as e:
                # Log error but continue monitoring - don't crash the background thread
                logger.exception(
                    "Error in LSPTimeoutManager monitor loop: %s",
                    e,
                )
