"""
StreamableHTTP Session Manager for MCP servers.

SERENA PATCH: This file is a patched version of mcp.server.streamable_http_manager
from the mcp-python-sdk package. It includes modifications to handle invalid/expired
session IDs gracefully by creating new sessions instead of returning 400 errors.

Original package: mcp==1.25.0
Patch applied: 2025-10-08
Patch reason: Augment MCP client caches session IDs across server restarts
"""

from __future__ import annotations

import contextlib
import logging
import warnings
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import anyio
from anyio.abc import TaskStatus
from mcp.server.lowlevel.server import Server as MCPServer
from mcp.server.streamable_http import MCP_SESSION_ID_HEADER, EventStore, StreamableHTTPServerTransport
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.types import Receive, Scope, Send

# SERENA PATCH: Import session context for HTTP mode session propagation
from serena.mcp_transport_context import reset_transport_session_id, set_transport_session_id

# SERENA PATCH: Version compatibility check
EXPECTED_MCP_VERSION = "1.25.0"
try:
    import mcp

    if hasattr(mcp, "__version__") and mcp.__version__ != EXPECTED_MCP_VERSION:
        warnings.warn(
            f"Patched streamable_http_manager expects mcp=={EXPECTED_MCP_VERSION}, "
            f"found mcp=={mcp.__version__}. Patch may not work correctly.",
            RuntimeWarning,
            stacklevel=2,
        )
except ImportError:
    pass

logger = logging.getLogger(__name__)


class StreamableHTTPSessionManager:
    """
    Manages StreamableHTTP sessions with optional resumability via event store.

    This class abstracts away the complexity of session management, event storage,
    and request handling for StreamableHTTP transports. It handles:

    1. Session tracking for clients
    2. Resumability via an optional event store
    3. Connection management and lifecycle
    4. Request handling and transport setup

    Important: Only one StreamableHTTPSessionManager instance should be created
    per application. The instance cannot be reused after its run() context has
    completed. If you need to restart the manager, create a new instance.

    Args:
        app: The MCP server instance
        event_store: Optional event store for resumability support.
                     If provided, enables resumable connections where clients
                     can reconnect and receive missed events.
                     If None, sessions are still tracked but not resumable.
        json_response: Whether to use JSON responses instead of SSE streams
        stateless: If True, creates a completely fresh transport for each request
                   with no session tracking or state persistence between requests.

    """

    def __init__(
        self,
        app: MCPServer[Any, Any],
        event_store: EventStore | None = None,
        json_response: bool = False,
        stateless: bool = False,
        security_settings: TransportSecuritySettings | None = None,
        retry_interval: int | None = None,
        on_session_created: Any | None = None,  # PRE-1: Optional[Callable[[str], None]]
        on_session_closed: Any | None = None,   # PRE-1: Optional[Callable[[str], None]]
    ):
        self.app = app
        self.event_store = event_store
        self.json_response = json_response
        self.stateless = stateless
        self.security_settings = security_settings
        self.retry_interval = retry_interval

        # PRE-1: Store lifecycle callbacks (contract: TransportSessionCallbackContract)
        # PRE-1: Callbacks are callable or None
        self._on_session_created = on_session_created
        self._on_session_closed = on_session_closed

        # Session tracking (only used if not stateless)
        self._session_creation_lock = anyio.Lock()
        self._server_instances: dict[str, StreamableHTTPServerTransport] = {}

        # The task group will be set during lifespan
        self._task_group = None
        # Thread-safe tracking of run() calls
        self._run_lock = anyio.Lock()
        self._has_started = False

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        """
        Run the session manager with proper lifecycle management.

        This creates and manages the task group for all session operations.

        Important: This method can only be called once per instance. The same
        StreamableHTTPSessionManager instance cannot be reused after this
        context manager exits. Create a new instance if you need to restart.

        Use this in the lifespan context manager of your Starlette app:

        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncIterator[None]:
            async with session_manager.run():
                yield
        """
        # Thread-safe check to ensure run() is only called once
        async with self._run_lock:
            if self._has_started:
                raise RuntimeError(
                    "StreamableHTTPSessionManager .run() can only be called "
                    "once per instance. Create a new instance if you need to run again."
                )
            self._has_started = True

        async with anyio.create_task_group() as tg:
            # Store the task group for later use
            self._task_group = tg
            logger.info("StreamableHTTP session manager started")
            try:
                yield  # Let the application run
            finally:
                logger.info("StreamableHTTP session manager shutting down")
                # Cancel task group to stop all spawned tasks
                tg.cancel_scope.cancel()
                self._task_group = None
                # Clear any remaining server instances
                self._server_instances.clear()

    async def handle_request(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """
        Process ASGI request with proper session handling and transport setup.

        Dispatches to the appropriate handler based on stateless mode.

        Args:
            scope: ASGI scope
            receive: ASGI receive function
            send: ASGI send function

        """
        if self._task_group is None:
            raise RuntimeError("Task group is not initialized. Make sure to use run().")

        # Dispatch to the appropriate handler
        if self.stateless:
            await self._handle_stateless_request(scope, receive, send)
        else:
            await self._handle_stateful_request(scope, receive, send)

    async def _handle_stateless_request(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """
        Process request in stateless mode - creating a new transport for each request.

        Args:
            scope: ASGI scope
            receive: ASGI receive function
            send: ASGI send function

        """
        logger.debug("Stateless mode: Creating new transport for this request")
        # No session ID needed in stateless mode
        http_transport = StreamableHTTPServerTransport(
            mcp_session_id=None,  # No session tracking in stateless mode
            is_json_response_enabled=self.json_response,
            event_store=None,  # No event store in stateless mode
            security_settings=self.security_settings,
        )

        # Start server in a new task
        async def run_stateless_server(*, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED):
            async with http_transport.connect() as streams:
                read_stream, write_stream = streams
                task_status.started()
                try:
                    await self.app.run(
                        read_stream,
                        write_stream,
                        self.app.create_initialization_options(),
                        stateless=True,
                    )
                except Exception:
                    logger.exception("Stateless session crashed")

        # Assert task group is not None for type checking
        assert self._task_group is not None
        # Start the server task
        await self._task_group.start(run_stateless_server)

        # Handle the HTTP request and return the response
        await http_transport.handle_request(scope, receive, send)

        # Terminate the transport after the request is handled
        await http_transport.terminate()

    async def _handle_stateful_request(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """
        Process request in stateful mode - maintaining session state between requests.

        Args:
            scope: ASGI scope
            receive: ASGI receive function
            send: ASGI send function

        """
        request = Request(scope, receive)
        request_mcp_session_id = request.headers.get(MCP_SESSION_ID_HEADER)

        # Existing session case
        if request_mcp_session_id is not None and request_mcp_session_id in self._server_instances:
            transport = self._server_instances[request_mcp_session_id]
            logger.debug("Session already exists, handling request directly")
            # SERENA PATCH: Set session context for existing session
            token = set_transport_session_id(request_mcp_session_id)
            try:
                await transport.handle_request(scope, receive, send)
            finally:
                reset_transport_session_id(token)
            return

        if request_mcp_session_id is None:
            # New session case
            logger.debug("Creating new transport")
            async with self._session_creation_lock:
                new_session_id = uuid4().hex
                http_transport = StreamableHTTPServerTransport(
                    mcp_session_id=new_session_id,
                    is_json_response_enabled=self.json_response,
                    event_store=self.event_store,  # May be None (no resumability)
                    security_settings=self.security_settings,
                )

                assert http_transport.mcp_session_id is not None
                self._server_instances[http_transport.mcp_session_id] = http_transport
                logger.info(f"Created new transport with session ID: {new_session_id}")

                # POST-1: Invoke on_session_created callback (INV-01: before first tool executes)
                # Contract: TransportSessionCallbackContract
                self._invoke_session_created(new_session_id)

                # SERENA PATCH: Set session context BEFORE starting task
                # Child task will inherit a copy of this context via anyio's copy_context()
                token = set_transport_session_id(new_session_id)
                try:
                    # Define the server runner
                    async def run_server(*, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
                        async with http_transport.connect() as streams:
                            read_stream, write_stream = streams
                            task_status.started()
                            try:
                                await self.app.run(
                                    read_stream,
                                    write_stream,
                                    self.app.create_initialization_options(),
                                    stateless=False,  # Stateful mode
                                )
                            except Exception as e:
                                logger.exception(f"Session {http_transport.mcp_session_id} crashed: {e}")
                            finally:
                                # Only remove from instances if not terminated
                                if (
                                    http_transport.mcp_session_id
                                    and http_transport.mcp_session_id in self._server_instances
                                    and not http_transport.is_terminated
                                ):
                                    logger.info(f"Cleaning up crashed session {http_transport.mcp_session_id} from active instances.")
                                    # POST-2: Invoke on_session_closed callback (INV-02: on termination)
                                    # Contract: TransportSessionCallbackContract
                                    self._invoke_session_closed(http_transport.mcp_session_id)
                                    del self._server_instances[http_transport.mcp_session_id]

                    # Assert task group is not None for type checking
                    assert self._task_group is not None
                    # Start the server task (inherits copied context with session_id)
                    await self._task_group.start(run_server)

                    # Handle the HTTP request and return the response
                    await http_transport.handle_request(scope, receive, send)
                finally:
                    # Reset after request handling (doesn't affect already-copied child context)
                    reset_transport_session_id(token)
        else:
            # MCP SPEC COMPLIANCE: Invalid/expired session ID - return 404 Not Found
            # Per MCP Specification 2025-03-26, Section "Session Management":
            # "The server MAY terminate the session at any time, after which it MUST
            #  respond to requests containing that session ID with HTTP 404 Not Found."
            # "When a client receives HTTP 404 in response to a request containing an
            #  Mcp-Session-Id, it MUST start a new session by sending a new
            #  InitializeRequest without a session ID attached."
            #
            # Reference: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#session-management
            # Requirement: REQ-SESSION-001, INV-06
            logger.warning(
                "Invalid or expired session ID received: %s. Returning 404 per MCP spec.",
                request_mcp_session_id,
                extra={
                    "invalid_session_id": request_mcp_session_id,
                    "action": "reject_stale_session",
                    "response_code": 404,
                },
            )

            # Return 404 Not Found per MCP spec - client MUST reinitialize
            from starlette.responses import JSONResponse
            response = JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": "server-error",
                    "error": {
                        "code": -32600,
                        "message": "Not Found: Invalid or expired session ID",
                    },
                },
                status_code=404,
            )
            await response(scope, receive, send)

    def set_session_callbacks(
        self,
        on_session_created: Any | None = None,
        on_session_closed: Any | None = None,
    ) -> None:
        """
        Set callbacks for session lifecycle events.

        Contract: TransportSessionCallbackContract.set_session_callbacks

        PRE-1: on_session_created is callable or None
        PRE-2: on_session_closed is callable or None

        POST-1: Subsequent session creations invoke on_session_created
        POST-2: Subsequent session closures invoke on_session_closed
        POST-3: Replaces any previously set callbacks
        POST-4: If sessions already exist when on_session_created is set,
                on_session_created is invoked IMMEDIATELY for each existing session
                (retroactive registration to handle race condition where session
                is created before callbacks are wired)
        """
        # DEBUG: Log when callbacks are being wired
        logger.info(
            "Setting session callbacks: on_created=%s, on_closed=%s, active_sessions=%d",
            on_session_created is not None,
            on_session_closed is not None,
            len(self._server_instances),
        )
        self._on_session_created = on_session_created
        self._on_session_closed = on_session_closed

        # POST-4: Retroactive registration for sessions created before callbacks were wired
        # This handles the race condition where HTTP transport creates session before
        # MCPServer lifespan wires callbacks
        if on_session_created is not None and self._server_instances:
            for session_id in list(self._server_instances.keys()):
                logger.info(
                    "POST-4: Retroactive callback invocation for pre-existing session: %s",
                    session_id,
                )
                on_session_created(session_id)

    def _invoke_session_created(self, session_id: str) -> None:
        """
        Invoke the on_session_created callback.

        Contract: TransportSessionCallbackContract._invoke_session_created

        PRE-1: session_id is non-empty string
        PRE-2: Called after session_id is generated but before first tool executes

        POST-1: If callback is set → callback(session_id) invoked
        POST-2: If callback is None → silent no-op
        POST-3: INV-01 satisfied (called before first tool)

        ERRORS-1: Callback exceptions propagate
        """
        # DEBUG: Log callback state at invocation time
        logger.debug(
            "Session callback invocation: session_id=%s, callback_set=%s",
            session_id,
            self._on_session_created is not None,
        )
        if self._on_session_created is not None:
            # POST-1: Invoke callback with session_id
            # ERRORS-1: Let exceptions propagate (not swallowed)
            logger.info("Invoking on_session_created callback for session %s", session_id)
            self._on_session_created(session_id)
        else:
            # DEBUG: Log when callback is None (indicates race condition)
            logger.warning(
                "on_session_created callback is None for session %s - callbacks not yet wired",
                session_id,
            )

    def _invoke_session_closed(self, session_id: str) -> None:
        """
        Invoke the on_session_closed callback.

        Contract: TransportSessionCallbackContract._invoke_session_closed

        PRE-1: session_id is non-empty string
        PRE-2: session_id was previously created via this transport

        POST-1: If callback is set → callback(session_id) invoked
        POST-2: If callback is None → silent no-op
        POST-3: INV-02 satisfied (called on termination)

        ERRORS-1: Callback exceptions propagate (but should be logged, not crash server)
        """
        if self._on_session_closed is not None:
            try:
                # POST-1: Invoke callback with session_id
                self._on_session_closed(session_id)
            except Exception:
                # ERRORS-1: Log exception but don't let it crash server
                logger.exception(f"Error in on_session_closed callback for session {session_id}")
