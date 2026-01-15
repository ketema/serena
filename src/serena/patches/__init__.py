"""
Serena patches for external dependencies.

This module contains minimal patches to external packages that need modifications
for Serena's specific requirements. Patches are applied via import hooks to ensure
they survive cache invalidation and environment rebuilds.

Current patches:
- mcp.server.streamable_http_manager: Graceful session handling for invalid/expired session IDs
- mcp.server.streamable_http: Parse comma-separated protocol version headers
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import logging
import re
import sys
from collections.abc import Sequence
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.types import Send

logger = logging.getLogger(__name__)

# Protocol version format: YYYY-MM-DD
_VERSION_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def negotiate_best_version(
    client_versions: list[str], supported_versions: list[str]
) -> str | None:
    """
    Negotiate the best mutually-supported protocol version.

    Takes client's preferred versions and server's supported versions,
    returns the newest version supported by both parties.

    Algorithm:
    1. Filter valid versions (non-empty, YYYY-MM-DD format)
    2. Sort by date descending (lexicographic works for YYYY-MM-DD)
    3. Return first version that exists in supported list

    Args:
        client_versions: List of version strings from client header
        supported_versions: List of server-supported versions

    Returns:
        Newest mutually-supported version, or None if no match

    """
    # Filter and validate versions
    valid_versions = [
        v for v in client_versions
        if v and _VERSION_PATTERN.match(v)
    ]

    # Sort descending (newest first) - lexicographic works for YYYY-MM-DD
    valid_versions.sort(reverse=True)

    # Find first mutually supported version
    for version in valid_versions:
        if version in supported_versions:
            return version

    return None


# Security limits for protocol version header parsing
MAX_PROTOCOL_VERSION_HEADER_LEN = 1024  # Max header length (DOS protection)
MAX_PROTOCOL_VERSION_TOKENS = 10  # Max number of versions to parse


def _apply_protocol_version_patch() -> None:
    """
    Monkey-patch StreamableHTTPServerTransport._validate_protocol_version.

    This patch adds comma-separated protocol version parsing per RFC 7230.
    Multiple major clients (Claude, Codex, Gemini) send comma-separated versions
    but upstream SDK treats the header as a literal string.

    Upstream issue: https://github.com/modelcontextprotocol/python-sdk/issues/1861
    """
    try:
        from mcp.server.streamable_http import (
            MCP_PROTOCOL_VERSION_HEADER,
            StreamableHTTPServerTransport,
        )
        from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS

        async def _patched_validate_protocol_version(
            self: StreamableHTTPServerTransport, request: Request, send: Send
        ) -> bool:
            """
            Validate protocol version header with comma-separated parsing.

            Parses all versions from comma-separated header, sorts by date
            descending, and returns True if any version is supported.
            """
            raw_version = request.headers.get(MCP_PROTOCOL_VERSION_HEADER)

            # If no protocol version provided, assume default
            if raw_version is None:
                return True

            # Security: Limit header length
            if len(raw_version) > MAX_PROTOCOL_VERSION_HEADER_LEN:
                logger.warning(
                    "Protocol version header too long (%d chars), truncating",
                    len(raw_version),
                )
                raw_version = raw_version[:MAX_PROTOCOL_VERSION_HEADER_LEN]

            # Parse comma-separated versions
            client_versions = [
                v.strip()
                for v in raw_version.split(",")[:MAX_PROTOCOL_VERSION_TOKENS]
                if v.strip()
            ]

            # Log if comma-separated (unusual but valid per RFC 7230)
            if len(client_versions) > 1:
                logger.debug(
                    "Client sent %d protocol versions: %s",
                    len(client_versions),
                    client_versions[:3],  # Don't log all for security
                )

            # Negotiate best version
            negotiated = negotiate_best_version(
                client_versions, list(SUPPORTED_PROTOCOL_VERSIONS)
            )

            if negotiated is not None:
                logger.debug("Negotiated protocol version: %s", negotiated)
                return True

            # No mutual version found - return detailed error
            client_list = ", ".join(client_versions[:5])  # Truncate for security
            server_list = ", ".join(SUPPORTED_PROTOCOL_VERSIONS)
            response = self._create_error_response(
                f"Bad Request: No mutually supported protocol version. "
                f"Client offered: [{client_list}]. Server supports: [{server_list}]",
                HTTPStatus.BAD_REQUEST,
            )
            await response(request.scope, request.receive, send)
            return False

        # Apply the monkey patch
        StreamableHTTPServerTransport._validate_protocol_version = _patched_validate_protocol_version
        logger.info("Applied protocol version comma-parsing patch to StreamableHTTPServerTransport")

    except ImportError as e:
        logger.warning("Could not apply protocol version patch: %s", e)
    except Exception as e:
        logger.exception("Failed to apply protocol version patch: %s", e)


class _PatchLoader(importlib.abc.Loader):
    """
    Loader for patched modules.

    Implements PEP 451 loader protocol to load patched versions of modules.
    """

    def exec_module(self, module: Any) -> None:
        """
        Execute the patched module in the given namespace.

        Args:
            module: The module object to populate

        """
        try:
            # Load our patched version
            patched_module = importlib.import_module("serena.patches.mcp.server.streamable_http_manager")

            # Copy all attributes from patched module to the target module
            module.__dict__.update(patched_module.__dict__)

            logger.debug("Successfully loaded patched mcp.server.streamable_http_manager")
        except Exception as e:
            logger.exception(f"Failed to load patched module: {e}")
            raise


class _PatchImportHook(importlib.abc.MetaPathFinder):
    """
    Import hook to redirect specific mcp modules to patched versions.

    This hook intercepts imports of mcp.server.streamable_http_manager and redirects
    them to our patched version in serena.patches.mcp.server.streamable_http_manager.

    All other mcp imports use the external mcp package normally.

    Implements PEP 451 import hook protocol (find_spec) instead of deprecated
    find_module/load_module for better compatibility with modern Python.
    """

    def find_spec(
        self, fullname: str, path: Optional[Sequence[str]], target: Optional[Any] = None
    ) -> Optional[importlib.machinery.ModuleSpec]:
        """
        Find module spec if it's one we patch.

        Args:
            fullname: Fully qualified module name
            path: Package path (for submodules)
            target: Target module (for reloading)

        Returns:
            ModuleSpec for patched module, or None if not patched

        """
        if fullname == "mcp.server.streamable_http_manager":
            logger.debug(f"Intercepting import of {fullname}, redirecting to patched version")
            return importlib.util.spec_from_loader(fullname, _PatchLoader(), origin="serena.patches.mcp.server.streamable_http_manager")
        return None


# Install the import hook if not already installed
if not any(isinstance(h, _PatchImportHook) for h in sys.meta_path):
    sys.meta_path.insert(0, _PatchImportHook())
    logger.debug("Installed Serena patch import hook")

# Apply protocol version comma-parsing patch
_apply_protocol_version_patch()
