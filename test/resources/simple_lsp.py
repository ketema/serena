#!/usr/bin/env python3
"""
Minimal JSON-RPC Language Server Protocol (LSP) Echo Server.

Purpose: Deterministic test fixture for integration testing.
Avoids external dependencies (npm, cargo) for CI stability.

Contract:
    PRE: Receives valid JSON-RPC 2.0 messages on stdin
    POST: Responds with appropriate LSP responses on stdout
    INV: No side effects, no file system access

Supported Methods:
    - initialize: Returns basic server capabilities
    - shutdown: Acknowledges shutdown request
    - exit: Terminates the server
    - textDocument/definition: Returns echo response with file position
    - textDocument/hover: Returns echo response with hover content
"""

import json
import sys
from typing import Any


def read_message() -> dict[str, Any] | None:
    """
    Read a JSON-RPC message using LSP Content-Length protocol.

    PRE: stdin contains Content-Length header followed by JSON body
    POST: Returns parsed JSON dict or None on EOF
    INV: stdin position advanced past the message
    """
    # Read Content-Length header
    header = ""
    while True:
        line = sys.stdin.readline()
        if not line:
            return None  # EOF
        header += line
        if header.endswith("\r\n\r\n") or header.endswith("\n\n"):
            break

    # Extract content length
    content_length = 0
    for line in header.strip().split("\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":")[1].strip())
            break

    if content_length == 0:
        return None

    # Read JSON body
    body = sys.stdin.read(content_length)
    return json.loads(body)


def write_message(msg: dict[str, Any]) -> None:
    """
    Write a JSON-RPC message using LSP Content-Length protocol.

    PRE: msg is valid JSON-serializable dict
    POST: Message written to stdout with Content-Length header
    INV: stdout flushed after write
    """
    body = json.dumps(msg)
    header = f"Content-Length: {len(body)}\r\n\r\n"
    sys.stdout.write(header + body)
    sys.stdout.flush()


def create_response(request_id: int | str | None, result: Any) -> dict[str, Any]:
    """Create a JSON-RPC 2.0 response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result
    }


def create_error(request_id: int | str | None, code: int, message: str) -> dict[str, Any]:
    """Create a JSON-RPC 2.0 error response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message
        }
    }


def handle_initialize(request_id: int | str | None) -> dict[str, Any]:
    """Handle LSP initialize request."""
    return create_response(request_id, {
        "capabilities": {
            "textDocumentSync": 1,
            "definitionProvider": True,
            "hoverProvider": True,
        },
        "serverInfo": {
            "name": "simple-lsp-test-server",
            "version": "1.0.0"
        }
    })


def handle_shutdown(request_id: int | str | None) -> dict[str, Any]:
    """Handle LSP shutdown request."""
    return create_response(request_id, None)


def handle_definition(request_id: int | str | None, params: dict[str, Any]) -> dict[str, Any]:
    """
    Handle textDocument/definition request.

    Returns an echo response pointing to the same location.
    This allows verification that the request was received correctly.
    """
    uri = params.get("textDocument", {}).get("uri", "file:///unknown")
    position = params.get("position", {"line": 0, "character": 0})

    # Echo back a location at the same position
    return create_response(request_id, {
        "uri": uri,
        "range": {
            "start": position,
            "end": {"line": position["line"], "character": position["character"] + 1}
        }
    })


def handle_hover(request_id: int | str | None, params: dict[str, Any]) -> dict[str, Any]:
    """
    Handle textDocument/hover request.

    Returns echo response with file info for verification.
    """
    uri = params.get("textDocument", {}).get("uri", "file:///unknown")
    position = params.get("position", {"line": 0, "character": 0})

    return create_response(request_id, {
        "contents": {
            "kind": "plaintext",
            "value": f"Echo from simple_lsp: {uri} at {position['line']}:{position['character']}"
        }
    })


def main() -> None:
    """
    Main loop: read requests, dispatch to handlers, write responses.

    PRE: stdin/stdout are valid file handles
    POST: Server terminates on 'exit' notification or EOF
    INV: All requests receive responses (except notifications)
    """
    initialized = False
    shutdown_requested = False

    while True:
        msg = read_message()
        if msg is None:
            break  # EOF

        method = msg.get("method", "")
        request_id = msg.get("id")
        params = msg.get("params", {})

        # Handle exit notification
        if method == "exit":
            sys.exit(0 if shutdown_requested else 1)

        # Handle shutdown request
        if method == "shutdown":
            shutdown_requested = True
            write_message(handle_shutdown(request_id))
            continue

        # Handle initialize request
        if method == "initialize":
            initialized = True
            write_message(handle_initialize(request_id))
            continue

        # Handle initialized notification (no response needed)
        if method == "initialized":
            continue

        # Require initialization for other methods
        if not initialized and request_id is not None:
            write_message(create_error(request_id, -32002, "Server not initialized"))
            continue

        # Route to method handlers
        if method == "textDocument/definition":
            write_message(handle_definition(request_id, params))
        elif method == "textDocument/hover":
            write_message(handle_hover(request_id, params))
        elif request_id is not None:
            # Unknown method with id = error
            write_message(create_error(request_id, -32601, f"Method not found: {method}"))
        # Notifications (no id) for unknown methods are silently ignored


if __name__ == "__main__":
    main()
