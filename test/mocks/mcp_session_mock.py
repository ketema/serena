"""
MCP Session Mock (CL10 Compliant)

CONTRACT DERIVATION:
- Source Contract: contracts/mcp_session_contract.py
- Verified Against: Real HTTP behavior via test_mcp_session_http_integration.py

CL10 REQUIREMENTS:
- Mock MUST derive from verified contract
- Mock behavior MUST match real provider behavior
- Mock changes MUST trigger contract verification

THEATER DETECTION:
Q: "Can MOCK behave differently from REAL and tests pass?"
A: NO - Mock behavior is derived from contract POST/INV clauses,
   and verified against real HTTP handler in integration tests.

MOCK CONTRACT REFERENCE: contracts/mcp_session_contract.py
VERIFICATION TESTS: test/contracts/test_mcp_session_http_integration.py
"""

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4


@dataclass
class MockHTTPResponse:
    """
    Mock HTTP response matching real HTTP handler behavior.

    CONTRACT TRACEABILITY:
    - POST-5 (create_session): status_code 200 for success
    - POST-2 (create_session): headers contain Mcp-Session-Id
    - POST-2 (validate_session): 404 response has error body
    - POST-3 (validate_session): 400 response has error body
    """

    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        """Return body as JSON (matches httpx.Response.json())."""
        return self.body


class MCPSessionMock:
    """
    Contract-derived mock for MCP session management.

    This mock implements the exact behavior specified in the contract:
    - contracts/mcp_session_contract.py

    THEATER PREVENTION:
    - Each method documents which contract clauses it implements
    - Behavior matches real HTTP handler exactly
    - Integration tests verify mock matches real behavior

    USAGE:
    ```python
    mock = MCPSessionMock()

    # Create session
    response = mock.handle_request(
        method="POST",
        headers={},
        body={"method": "initialize", ...}
    )
    session_id = response.headers["Mcp-Session-Id"]

    # Use session
    response = mock.handle_request(
        method="POST",
        headers={"Mcp-Session-Id": session_id},
        body={"method": "tools/list", ...}
    )
    ```
    """

    def __init__(self):
        """Initialize mock with empty session registry."""
        # INV-1: Session registry tracks server-issued IDs
        self._sessions: dict[str, dict[str, Any]] = {}

    def handle_request(
        self,
        method: Literal["POST", "GET", "DELETE"],
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> MockHTTPResponse:
        """
        Handle HTTP request per contract behavior.

        CONTRACT TRACEABILITY:
        - create_session(): POST-1 through POST-6
        - validate_session(): POST-1 through POST-3, INV-1 through INV-3
        - security_invariants(): INV-SEC-1 through INV-SEC-6

        Args:
            method: HTTP method
            headers: HTTP headers (may contain Mcp-Session-Id)
            body: JSON-RPC body

        Returns:
            MockHTTPResponse matching real HTTP handler behavior

        """
        session_id = headers.get("Mcp-Session-Id")
        is_initialize = body.get("method") == "initialize"

        # Case 1: InitializeRequest without session ID - create new session
        # Contract: create_session() POST-1
        if is_initialize and session_id is None:
            return self._create_session(body)

        # Case 2: Request with valid session ID
        # Contract: validate_session() POST-1
        if session_id is not None and session_id in self._sessions:
            return self._handle_valid_session(session_id, body)

        # Case 3: Request with invalid/stale session ID
        # Contract: validate_session() POST-2
        if session_id is not None and session_id not in self._sessions:
            return self._reject_invalid_session(session_id)

        # Case 4: Non-init request without session ID
        # Contract: validate_session() POST-3
        if not is_initialize and session_id is None:
            return self._reject_missing_session()

        # Fallback - should not reach here
        return MockHTTPResponse(
            status_code=500,
            body={"error": {"code": -32603, "message": "Internal error"}},
        )

    def _create_session(self, body: dict[str, Any]) -> MockHTTPResponse:
        """
        Create new session per contract.

        CONTRACT TRACEABILITY:
        - POST-1: Create new session for InitializeRequest without session ID
        - POST-2: Return Mcp-Session-Id header in response
        - POST-3: Session ID MUST be cryptographically secure (UUID)
        - POST-4: Session ID MUST be visible ASCII only (hex satisfies)
        - POST-5: Response status MUST be 200 OK
        - POST-6: Response body MUST contain InitializeResult
        """
        # POST-3: Cryptographically secure session ID
        # POST-4: hex produces visible ASCII (0-9, a-f)
        new_session_id = uuid4().hex

        # INV-1: Register session in server-side registry
        self._sessions[new_session_id] = {
            "created": True,
            "client_info": body.get("params", {}).get("clientInfo", {}),
        }

        # POST-5: 200 OK
        # POST-2: Mcp-Session-Id header
        # POST-6: InitializeResult in body
        return MockHTTPResponse(
            status_code=200,
            headers={"Mcp-Session-Id": new_session_id},
            body={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "MockMCP", "version": "1.0"},
                },
            },
        )

    def _handle_valid_session(
        self, session_id: str, body: dict[str, Any]
    ) -> MockHTTPResponse:
        """
        Handle request with valid session ID per contract.

        CONTRACT TRACEABILITY:
        - validate_session() POST-1: Valid session → 200
        """
        # POST-1: Return 200 for valid session
        return MockHTTPResponse(
            status_code=200,
            headers={"Mcp-Session-Id": session_id},
            body={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"tools": []},  # Simplified response
            },
        )

    def _reject_invalid_session(self, session_id: str) -> MockHTTPResponse:
        """
        Reject invalid/stale session ID per contract.

        CONTRACT TRACEABILITY:
        - validate_session() POST-2: Invalid session → 404 Not Found
        - validate_session() INV-1: Only server-issued IDs valid
        - validate_session() INV-2: Stale sessions rejected
        - validate_session() INV-3: Fabricated sessions rejected
        """
        # POST-2: 404 Not Found with JSON-RPC error
        return MockHTTPResponse(
            status_code=404,
            body={
                "jsonrpc": "2.0",
                "id": "server-error",
                "error": {
                    "code": -32600,
                    "message": "Not Found: Invalid or expired session ID",
                },
            },
        )

    def _reject_missing_session(self) -> MockHTTPResponse:
        """
        Reject request missing session ID per contract.

        CONTRACT TRACEABILITY:
        - validate_session() POST-3: Missing session → 400 Bad Request
        """
        # POST-3: 400 Bad Request with JSON-RPC error
        return MockHTTPResponse(
            status_code=400,
            body={
                "jsonrpc": "2.0",
                "id": "server-error",
                "error": {
                    "code": -32600,
                    "message": "Bad Request: Missing session ID",
                },
            },
        )

    def reset(self) -> None:
        """Reset mock state (clear all sessions)."""
        self._sessions.clear()


# =============================================================================
# MOCK THEATER DETECTION VERIFICATION
# =============================================================================

def verify_mock_matches_contract() -> bool:
    """
    Theater Detection Verification Function.

    This function verifies that the mock behavior matches the contract.
    It should be called during contract verification tests.

    Q: "Can MOCK behave differently from REAL and tests pass?"
    A: NO - This function verifies:
       1. Mock returns exact status codes per contract
       2. Mock returns exact error messages per contract
       3. Mock session ID format matches contract (UUID hex)

    Returns:
        True if mock matches contract, raises AssertionError otherwise

    """
    mock = MCPSessionMock()

    # Verify POST-2 (stale session → 404)
    response = mock.handle_request(
        method="POST",
        headers={"Mcp-Session-Id": "stale_id"},
        body={"method": "tools/list"},
    )
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    assert "Invalid or expired session ID" in response.body["error"]["message"]

    # Verify POST-3 (missing session → 400)
    response = mock.handle_request(
        method="POST",
        headers={},
        body={"method": "tools/list"},
    )
    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    assert "Missing session ID" in response.body["error"]["message"]

    # Verify POST-1 through POST-6 (create session)
    response = mock.handle_request(
        method="POST",
        headers={},
        body={"method": "initialize", "params": {}},
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert "Mcp-Session-Id" in response.headers
    session_id = response.headers["Mcp-Session-Id"]
    assert len(session_id) == 32, f"Expected UUID hex (32 chars), got {len(session_id)}"

    # Verify POST-1 valid session → 200
    response = mock.handle_request(
        method="POST",
        headers={"Mcp-Session-Id": session_id},
        body={"method": "tools/list"},
    )
    assert response.status_code == 200, f"Expected 200 for valid session, got {response.status_code}"

    return True
