"""
Backward Compatibility Contract - Legacy Single-Project Mode

Constitutional Reference: CL12 Design by Contract
Domain: CLI and legacy API compatibility
Version: 1.0

AUTHORITY: This contract is AUTHORITATIVE for backward compatibility behavior.
"""

from abc import ABC, abstractmethod
from typing import Literal


class BackwardCompatibilityContract(ABC):
    """
    Contract for backward compatibility with single-project mode.

    Issue #6 Requirement: "Single-project mode should still work"

    This contract ensures:
    1. CLI invocations work without session isolation
    2. Legacy activate_project() API preserved
    3. Existing single-session flows unaffected
    4. Error messages consistent

    INVARIANTS:
    - INV-1: CLI mode (no MCP transport) uses legacy _active_project
    - INV-2: Single-project workflows do NOT require SessionRegistry
    - INV-3: Legacy activate_project() signature unchanged
    - INV-4: Error messages for invalid project names unchanged
    """

    @abstractmethod
    def activate_project_legacy(
        self,
        project_name: str,
    ) -> None:
        """
        Legacy project activation (no session context).

        PRE: project_name exists in config

        POST: _active_project set to project
        POST: SessionRegistry NOT modified
        POST: LSP started via legacy LanguageServerManager path

        INV: Does NOT create session (INV-1, INV-2)
        INV: Does NOT call bind_session()
        INV: Other sessions (if any) unaffected
        INV: No ContextVar modification

        ERRORS: ProjectNotFoundError if project_name not in config
        """
        ...

    @abstractmethod
    def activate_project_with_session(
        self,
        project_name: str,
    ) -> None:
        """
        Session-aware project activation (MCP context exists).

        PRE: project_name exists in config
        PRE: Session context exists (from MCP transport)

        POST: Session bound to project workspace via SessionRegistry
        POST: Legacy _active_project NOT set (stateless agent)

        INV: _active_project unchanged
        INV: Other sessions unaffected
        INV: Only current session modified
        INV: Thread-safe (registry handles locking)

        ERRORS: ProjectNotFoundError if project_name not in config
        """
        ...

    @abstractmethod
    def detect_execution_context(self) -> Literal["mcp", "cli", "unknown"]:
        """
        Detect whether running in MCP or CLI context.

        PRE: none

        POST: Returns "mcp" if session context exists
        POST: Returns "cli" if no session context
        POST: Returns "unknown" if cannot determine

        INV: Does not modify state (read-only detection)
        INV: Thread-safe
        INV: No side effects

        ERRORS: None (returns "unknown" on error)
        """
        ...
