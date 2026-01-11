"""
MCP Session Bridge - bridges MCP transport sessions to SessionRegistry.

Implements MCPSessionBridgeContract with:
- Lifecycle hooks: on_transport_session_created/closed
- Context propagation: ContextVar-based session tracking
- Anonymous sessions: On-demand creation with TTL tracking
- Thread pool safety: copy_context() propagation
- TTL reaper: Async cleanup of expired anonymous sessions

THREAD SAFETY:
- SessionRegistry: Thread-safe via internal locks
- ContextVar: Thread-safe per execution context
- _anonymous_sessions: Protected by _anonymous_lock (threading.Lock)
  Accessed from: async reaper (event loop) + sync tool dispatch (thread pool)
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from contextvars import ContextVar, Token, copy_context
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from contracts.mcp_session_bridge_contract import (
    ANONYMOUS_SESSION_PREFIX,
    ANONYMOUS_SESSION_TTL_SECONDS,
    REAPER_INTERVAL_SECONDS,
    MCPSessionBridgeContract,
)
from serena.session_registry import SessionRegistry

logger = logging.getLogger(__name__)

# ContextVar for thread-safe session ID storage
_current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)


class MCPSessionBridge(MCPSessionBridgeContract):
    """
    Bridges MCP transport sessions to SessionRegistry.

    THREAD SAFETY:
    - SessionRegistry: Thread-safe via internal locks
    - ContextVar: Thread-safe per execution context
    - _anonymous_sessions: Protected by _anonymous_lock (threading.Lock)
      Accessed from: async reaper (event loop) + sync tool dispatch (thread pool)
    """

    def __init__(self, session_registry: SessionRegistry) -> None:
        """Initialize bridge with session registry."""
        self._session_registry = session_registry
        # Track anonymous session creation times for TTL
        self._anonymous_sessions: dict[str, datetime] = {}
        # Lock for thread-safe access to _anonymous_sessions
        # Accessed from: async reaper (event loop) + sync tool dispatch (thread pool)
        self._anonymous_lock = threading.Lock()
        # Reaper task
        self._reaper_task: asyncio.Task | None = None
        # Clear any leftover ContextVar state from previous instances
        # Set to None without resetting - this is for test isolation
        _current_session_id.set(None)

    # =========================================================================
    # LIFECYCLE HOOKS
    # =========================================================================

    def on_transport_session_created(
        self,
        mcp_session_id: str,
        workspace_root: Path | None = None,
    ) -> None:
        """
        Register MCP transport session in SessionRegistry.

        PRE: mcp_session_id is non-empty string
        POST: Session registered and available via get_session()
        """
        if not mcp_session_id:
            raise ValueError("mcp_session_id must be non-empty")

        # Default workspace if none provided
        if workspace_root is None:
            workspace_root = Path.cwd()

        # Register session
        self._session_registry.bind_session(mcp_session_id, workspace_root)

        logger.info(f"MCP session created: {mcp_session_id} @ {workspace_root}")

    def on_transport_session_closed(
        self,
        mcp_session_id: str,
    ) -> None:
        """
        Remove MCP transport session from SessionRegistry.

        POST: Session removed (idempotent - silent no-op if already removed)
        """
        # Unbind session (idempotent)
        self._session_registry.unbind_session(mcp_session_id)

        # Remove from anonymous tracking if present (thread-safe)
        with self._anonymous_lock:
            if mcp_session_id in self._anonymous_sessions:
                del self._anonymous_sessions[mcp_session_id]

        logger.info(f"MCP session closed: {mcp_session_id}")

    # =========================================================================
    # CONTEXT PROPAGATION
    # =========================================================================

    def set_session_context(
        self,
        session_id: str,
    ) -> Token:
        """
        Set session context in ContextVar.

        PRE: session_id is non-empty string
        POST: ContextVar set to session_id, token returned for reset
        """
        if not session_id:
            raise ValueError("session_id must be non-empty")

        # Set ContextVar and return token for reset
        token = _current_session_id.set(session_id)
        return token

    def reset_session_context(
        self,
        token: Token,
    ) -> None:
        """
        Reset session context to previous value.

        PRE: token from previous set_session_context()
        POST: ContextVar restored
        """
        _current_session_id.reset(token)

    def get_current_session_id(self) -> str | None:
        """
        Get current session ID from ContextVar.

        POST: Returns session_id if set, None otherwise
        """
        return _current_session_id.get(None)

    # =========================================================================
    # ANONYMOUS SESSION MANAGEMENT
    # =========================================================================

    def get_or_create_anonymous_session(
        self,
        workspace_root: Path | None = None,
    ) -> str:
        """
        Create an anonymous session for backward compatibility.

        PRE: workspace_root should be provided for security isolation
             (None allowed for backward compatibility but logged as warning)
        POST: Returns valid session_id with TTL tracking
        """
        # Generate anonymous session ID
        session_id = f"{ANONYMOUS_SESSION_PREFIX}{uuid4()}"

        # Default workspace if none provided (backward compat, but warn)
        if workspace_root is None:
            workspace_root = Path.cwd()
            logger.warning(
                f"Anonymous session {session_id} created without explicit workspace_root. "
                "Using cwd() for backward compatibility. Consider providing explicit workspace."
            )

        # Register session
        self._session_registry.bind_session(session_id, workspace_root)

        # Track creation time for TTL (thread-safe)
        with self._anonymous_lock:
            self._anonymous_sessions[session_id] = datetime.now()

        logger.info(f"Anonymous session created: {session_id}")

        return session_id

    def is_anonymous_session(
        self,
        session_id: str,
    ) -> bool:
        """
        Check if session_id is anonymous.

        POST: Returns True if session_id starts with ANONYMOUS_SESSION_PREFIX
        """
        return session_id.startswith(ANONYMOUS_SESSION_PREFIX)

    # =========================================================================
    # THREAD POOL PROPAGATION
    # =========================================================================

    def run_with_session_context(
        self,
        session_id: str,
        func: Callable[[], Any],
    ) -> Any:
        """
        Run sync function with session context propagated to thread pool.

        PRE: session_id is valid session ID
        PRE: func is callable taking no arguments
        POST: func executed with session_id in ContextVar
        """
        # Copy current context
        ctx = copy_context()

        # Set session_id in copied context
        def wrapper() -> Any:
            token = self.set_session_context(session_id)
            try:
                return func()
            finally:
                self.reset_session_context(token)

        # Run func with context
        return ctx.run(wrapper)

    # =========================================================================
    # SESSION REAPER
    # =========================================================================

    def start_reaper(self) -> None:
        """
        Start background task to clean up expired anonymous sessions.

        POST: Reaper task running every REAPER_INTERVAL_SECONDS
        """
        if self._reaper_task is not None:
            logger.warning("Reaper already running, skipping start")
            return

        self._reaper_task = asyncio.create_task(self._reap_loop())
        logger.info("Anonymous session reaper started")

    def stop_reaper(self) -> None:
        """
        Stop the reaper task.

        POST: Background task cancelled
        """
        if self._reaper_task is None:
            logger.warning("Reaper not running, skipping stop")
            return

        self._reaper_task.cancel()
        logger.info("Anonymous session reaper stopped")

    async def _reap_loop(self) -> None:
        """Background loop for reaping expired anonymous sessions."""
        try:
            while True:
                await asyncio.sleep(REAPER_INTERVAL_SECONDS)
                await self._reap_expired_sessions()
        except asyncio.CancelledError:
            logger.info("Reaper loop cancelled")
            raise

    async def _reap_expired_sessions(self) -> None:
        """Check all anonymous sessions and remove expired ones."""
        now = datetime.now()
        ttl = timedelta(seconds=ANONYMOUS_SESSION_TTL_SECONDS)

        # Get expired sessions under lock (thread-safe read)
        with self._anonymous_lock:
            expired_sessions = [session_id for session_id, created_at in self._anonymous_sessions.items() if now - created_at > ttl]

        # Close sessions outside lock (on_transport_session_closed acquires lock)
        for session_id in expired_sessions:
            logger.info(f"Reaping expired anonymous session: {session_id}")
            self.on_transport_session_closed(session_id)
