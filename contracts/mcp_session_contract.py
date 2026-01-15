"""
MCP Session Management Contract

Authority: MCP Specification 2025-03-26
Reference: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#session-management
Requirement: REQ-SESSION-001

This contract defines the behavioral requirements for MCP HTTP session management
in the Serena MCP server. All implementations MUST satisfy these PRE/POST/INV
conditions.
"""

from typing import Literal

# Session ID constraints per MCP spec
SESSION_ID_MIN_ENTROPY_BITS = 128  # UUID provides 122 bits, acceptable
SESSION_ID_ASCII_RANGE = (0x21, 0x7E)  # Visible ASCII only


class MCPSessionContract:
    """
    Contract for MCP HTTP session management.

    PRE/POST/INV conditions define behavioral requirements that MUST be
    satisfied by any implementation. Type hints define structure;
    this contract defines BEHAVIOR.
    """

    # =========================================================================
    # SESSION CREATION (POST InitializeRequest)
    # =========================================================================

    @staticmethod
    def create_session(request_has_session_id: bool, is_initialize_request: bool) -> dict | None:
        """
        Handle session creation for InitializeRequest.

        PRE-1: Request MUST be POST method
        PRE-2: Request MUST contain InitializeRequest JSON-RPC message
        PRE-3: Request MAY or MAY NOT have Mcp-Session-Id header

        POST-1: If is_initialize_request AND NOT request_has_session_id:
                Server MUST create new session
        POST-2: Server MUST return Mcp-Session-Id header in response
        POST-3: Session ID MUST be cryptographically secure (UUID, JWT, or crypto hash)
        POST-4: Session ID MUST contain only visible ASCII (0x21-0x7E)
        POST-5: Response status MUST be 200 OK
        POST-6: Response body MUST contain InitializeResult

        INV-1: Session ID is globally unique within server lifetime
        INV-2: Session ID cannot be predicted or brute-forced

        ERRORS:
        - If request_has_session_id AND session_id is stale: 404 Not Found
        """
        # Reference implementation for contract tests
        # Real implementation: streamable_http_manager.py:_handle_stateful_request
        from uuid import uuid4
        
        if is_initialize_request and not request_has_session_id:
            # POST-1: Create new session
            session_id = uuid4().hex  # POST-3: Cryptographically secure
            return {
                "status_code": 200,  # POST-5
                "headers": {"Mcp-Session-Id": session_id},  # POST-2, POST-4 (hex is visible ASCII)
                "body": {"result": "InitializeResult"},  # POST-6 (simplified)
            }
        elif request_has_session_id:
            # ERRORS: Stale session case - would return 404 in real impl
            return {"status_code": 404, "error": "stale_session"}
        return None

    # =========================================================================
    # SESSION VALIDATION (Subsequent Requests)
    # =========================================================================

    @staticmethod
    def validate_session(
        request_has_session_id: bool,
        session_id_valid: bool,
        is_initialize_request: bool,
    ) -> Literal[200, 400, 404]:
        """
        Validate session ID on non-initialization requests.

        PRE-1: Request is NOT an InitializeRequest (handled separately)
        PRE-2: Server requires session IDs (stateful mode)

        POST-1: If request_has_session_id AND session_id_valid:
                Return 200 (or 202 for notifications)
        POST-2: If request_has_session_id AND NOT session_id_valid:
                Return 404 Not Found
                Response body MUST contain JSON-RPC error:
                {"jsonrpc": "2.0", "id": "server-error", "error": {"code": -32600, "message": "Not Found: Invalid or expired session ID"}}
        POST-3: If NOT request_has_session_id:
                Return 400 Bad Request
                Response body MUST contain JSON-RPC error:
                {"jsonrpc": "2.0", "id": "server-error", "error": {"code": -32600, "message": "Bad Request: Missing session ID"}}

        INV-1: Valid session IDs are those issued by THIS server instance
        INV-2: Session IDs from previous server instances are INVALID (stale)
        INV-3: Client-fabricated session IDs are INVALID (spoofed)

        ERRORS:
        - 400 Bad Request: Missing session ID (non-init request)
        - 404 Not Found: Invalid or expired session ID
        """
        if not is_initialize_request:
            if not request_has_session_id:
                return 400  # POST-3
            if not session_id_valid:
                return 404  # POST-2
            return 200  # POST-1
        return 200  # Initialize requests handled separately

    # =========================================================================
    # STALE SESSION RECOVERY (Client Responsibility)
    # =========================================================================

    @staticmethod
    def client_stale_session_recovery() -> None:
        """
        Contract for client behavior on stale session.

        PRE-1: Client received 404 Not Found with Mcp-Session-Id in request

        POST-1: Client MUST send new POST InitializeRequest
        POST-2: InitializeRequest MUST NOT contain Mcp-Session-Id header
        POST-3: Client MUST store new session ID from response
        POST-4: Client MUST use new session ID for all subsequent requests

        INV-1: Client does NOT retry with stale session ID
        INV-2: Client does NOT fabricate new session ID

        NOTE: This contract documents CLIENT obligations per MCP spec.
              Server cannot enforce this but can verify compliance via behavior.
        """
        pass  # Client implementation responsibility

    # =========================================================================
    # SESSION TERMINATION
    # =========================================================================

    @staticmethod
    def terminate_session(session_id: str, termination_source: Literal["client", "server", "restart"]) -> int:
        """
        Handle session termination.

        PRE-1: session_id is currently valid
        PRE-2: termination_source is one of: "client" (DELETE), "server" (timeout/error), "restart"

        POST-1: Session ID is removed from active sessions
        POST-2: Subsequent requests with this session ID return 404
        POST-3: If client-initiated (DELETE): Return 200 OK or 405 Method Not Allowed
        POST-4: Session termination event MUST be logged

        INV-1: Terminated session IDs cannot be reused
        INV-2: Server restart terminates ALL sessions

        ERRORS:
        - 405 Method Not Allowed: If server doesn't support client termination
        """
        pass  # Implementation in streamable_http_manager.py

    # =========================================================================
    # SECURITY INVARIANTS
    # =========================================================================

    @staticmethod
    def security_invariants() -> None:
        """
        Security invariants that MUST hold at all times.

        INV-SEC-1: Session IDs MUST be cryptographically secure
                   (minimum 128 bits of entropy, UUID v4 acceptable)
        INV-SEC-2: Session IDs MUST NOT be predictable
        INV-SEC-3: Session IDs MUST NOT be derivable from other session IDs
        INV-SEC-4: Client CANNOT access another client's session (isolation)
        INV-SEC-5: Client CANNOT fabricate valid session ID (anti-spoofing)
        INV-SEC-6: Session state MUST NOT leak between sessions

        ENFORCEMENT:
        - INV-SEC-1 through INV-SEC-3: Enforced by uuid4().hex generation
        - INV-SEC-4 through INV-SEC-5: Enforced by session ID validation
        - INV-SEC-6: Enforced by session isolation in _server_instances dict
        """
        pass  # Enforced by implementation

    # =========================================================================
    # AUDIT REQUIREMENTS
    # =========================================================================

    @staticmethod
    def audit_requirements() -> None:
        """
        Audit logging requirements for session lifecycle.

        INV-AUDIT-1: Session creation MUST be logged with:
                     - New session ID
                     - Timestamp
                     - Client metadata (if available)

        INV-AUDIT-2: Session rejection MUST be logged with:
                     - Invalid session ID
                     - Rejection reason (stale, missing, spoofed)
                     - Response code (400, 404)
                     - Timestamp

        INV-AUDIT-3: Session termination MUST be logged with:
                     - Session ID
                     - Termination source (client, server, restart)
                     - Timestamp

        ENFORCEMENT: Via logger.info/warning calls with structured extra data
        """
        pass  # Enforced by logging in implementation


# Response code constants for test assertions
RESPONSE_CODES = {
    "session_created": 200,
    "request_accepted": 202,
    "missing_session_id": 400,
    "invalid_session_id": 404,
    "method_not_allowed": 405,
}

# Error messages per MCP spec
ERROR_MESSAGES = {
    400: "Bad Request: Missing session ID",
    404: "Not Found: Invalid or expired session ID",
}
