"""
MCP Transport Context - Session ID Propagation from HTTP Layer to Tool Dispatch.

Constitutional Reference: CL12 Design by Contract
Domain: MCP transport session ID propagation
Version: 1.0

PURPOSE:
This module provides a ContextVar to propagate the MCP session ID from the
HTTP transport layer down to tool execution. This bridges the gap between:
1. HTTP layer: knows mcp_session_id from headers
2. Tool layer: needs to restore Serena session context

USAGE:
- HTTP layer (streamable_http_manager.py): Sets _mcp_transport_session_id
- Tool layer (mcp.py): Reads _mcp_transport_session_id to restore session context

This module is intentionally minimal with no imports from other Serena modules
to avoid circular dependencies. The MCPSessionBridge is responsible for
translating between transport session ID and Serena session context.
"""

from contextvars import ContextVar, Token
from typing import Optional

# ContextVar storing the MCP transport session ID
# Set at HTTP request entry, read at tool dispatch
_mcp_transport_session_id: ContextVar[Optional[str]] = ContextVar(
    "mcp_transport_session_id", default=None
)


def get_transport_session_id() -> Optional[str]:
    """
    Get the current MCP transport session ID.

    PRE: Called within async context of MCP request handling

    POST: Returns session ID if set by HTTP layer, None otherwise
    POST: None indicates stateless mode or STDIO transport

    INV: Never raises, always returns str or None
    """
    return _mcp_transport_session_id.get(None)


def set_transport_session_id(session_id: Optional[str]) -> Token[Optional[str]]:
    """
    Set the MCP transport session ID for the current async context.

    PRE: session_id is non-empty string or None

    POST: ContextVar set to session_id
    POST: Returns token for reset

    INV: Token MUST be used for reset to prevent context leaks
    """
    return _mcp_transport_session_id.set(session_id)


def reset_transport_session_id(token: Token[Optional[str]]) -> None:
    """
    Reset the MCP transport session ID using the provided token.

    PRE: token from previous set_transport_session_id()

    POST: ContextVar restored to previous value

    INV: Safe to call in finally block
    """
    _mcp_transport_session_id.reset(token)
