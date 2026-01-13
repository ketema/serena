"""
Session Context Contract - Per-Session Isolation Context

Constitutional Reference: CL12 Design by Contract
Domain: Core session data structure and behavior
Version: 1.0

AUTHORITY: This contract is AUTHORITATIVE for SessionContext behavior.
All implementations MUST satisfy these specifications.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .issue6_constants import SESSION_DEFAULT_TTL_SECONDS

if TYPE_CHECKING:
    from solidlsp.ls_config import Language


class SessionState(Enum):
    """Session lifecycle states."""

    CREATED = "created"  # Session created, no project activated
    ACTIVE = "active"  # Session has active project
    IDLE = "idle"  # Session active but no recent activity
    EXPIRED = "expired"  # Session TTL exceeded, pending cleanup


@dataclass
class SessionContextContract:
    """
    Contract for per-session isolation context.

    Issue #6 specifies these fields:
    - session_id: Unique MCP session identifier
    - workspace_root: Project path (absolute)
    - modes: Active modes for this session
    - lsp_workspace_folders: LSP workspace registrations

    INVARIANTS:
    - INV-1: session_id is non-empty, immutable after creation
    - INV-2: workspace_root is always absolute Path when set, None before activation
    - INV-3: activation_time is set once during bind_session(), never modified
    - INV-4: lsp_workspace_folders tracks ONLY workspaces registered with LSP
    - INV-5: last_activity_time updated on every tool call, never backdated
           ALLOCATION: SessionContextBehaviorContract.touch() performs the update
           CALLER RESPONSIBILITY: Tool dispatch layer MUST call touch() on every tool invocation
           See: SessionContextBehaviorContract.touch() for update contract
    - INV-6: state transitions follow: CREATED -> ACTIVE -> IDLE -> EXPIRED (only forward)
    """

    # REQUIRED FIELDS
    session_id: str  # PRE: Non-empty, immutable. POST: Uniquely identifies session.
    workspace_root: Path | None  # PRE: None or absolute Path. POST: Project root.
    activation_source: Literal["explicit", "auto", "anonymous"]
    activation_time: datetime

    # OPTIONAL FIELDS
    active_modes: list[str] = field(default_factory=list)
    lsp_workspace_folders: set[Path] = field(default_factory=set)

    # LIFECYCLE TRACKING
    last_activity_time: datetime = field(default_factory=datetime.now)
    state: SessionState = SessionState.CREATED
    ttl_seconds: int = SESSION_DEFAULT_TTL_SECONDS

    def __post_init__(self) -> None:
        """
        Validate invariants on construction.

        PRE: Fields have been set by dataclass
        POST: Instance is valid or ValueError raised
        INV: No side effects beyond validation
        INV: No external state modified
        """
        if not self.session_id:
            raise ValueError("INV-1 violation: session_id must be non-empty")
        if self.workspace_root is not None and not self.workspace_root.is_absolute():
            raise ValueError("INV-2 violation: workspace_root must be absolute Path")


class SessionContextBehaviorContract(ABC):
    """
    Behavioral contract for SessionContext operations.

    This defines WHAT a SessionContext must DO, not just what fields it has.
    """

    @abstractmethod
    def touch(self) -> None:
        """
        Update last_activity_time to current time.

        SATISFIES: SessionContextContract.INV-5 (last_activity_time update)
        CALLER: Tool dispatch layer MUST call this on every tool invocation

        PRE: Session is in CREATED, ACTIVE, or IDLE state (not EXPIRED)

        POST: last_activity_time = datetime.now() (current time, never backdated)
        POST: If state was IDLE, state transitions to ACTIVE

        INV (5-Point Checklist):
        1. State Invariance: activation_time, session_id, workspace_root unchanged
        2. Side Effect Prohibition: No logging, no metrics, no I/O, no external state
        3. Ordering Constraints: Thread-safe (callers may invoke concurrently)
        4. Resource Invariants: No memory allocation, no handles opened/closed
        5. Exception Safety: Method never raises; state always consistent after call

        ERRORS: None (never raises - PRE violation on EXPIRED state is silent no-op)
        """
        ...

    @abstractmethod
    def is_expired(self) -> bool:
        """
        Check if session has exceeded TTL.

        PRE: none (pure query, always safe to call)

        POST: Returns True if (now - last_activity_time) > ttl_seconds
        POST: Returns False otherwise

        INV (5-Point Checklist):
        1. State Invariance: ALL fields unchanged (pure read-only query)
        2. Side Effect Prohibition: No logging, no metrics, no I/O, no external state
        3. Ordering Constraints: Thread-safe, may be called concurrently with touch()
        4. Resource Invariants: No memory allocation, no handles
        5. Exception Safety: Never raises; always returns bool

        ERRORS: None (pure query, never raises)
        """
        ...

    @abstractmethod
    def register_lsp_workspace(self, workspace: Path, language: "Language") -> None:
        """
        Record that this session has registered a workspace with an LSP.

        PRE: workspace is absolute Path
        PRE: language is valid Language enum

        POST: workspace added to lsp_workspace_folders
        POST: Used to track which workspaces need cleanup on session close

        INV (5-Point Checklist):
        1. State Invariance: session_id, workspace_root, activation_time unchanged
        2. Side Effect Prohibition: Does NOT call LSP (GlobalLanguageServerPool's job),
           no logging, no metrics, no I/O
        3. Ordering Constraints: Thread-safe, idempotent (adding same workspace twice is no-op)
        4. Resource Invariants: No external handles, no network connections
        5. Exception Safety: On ValueError, lsp_workspace_folders unchanged

        ERRORS:
        - ValueError: if workspace is not absolute Path
        - ValueError: if language is not valid Language enum
        """
        ...

    @abstractmethod
    def unregister_lsp_workspace(self, workspace: Path) -> None:
        """
        Record that this session has unregistered a workspace from LSPs.

        PRE: none (idempotent - workspace may or may not be registered)

        POST: workspace removed from lsp_workspace_folders if present
        POST: lsp_workspace_folders unchanged if workspace was not registered

        INV (5-Point Checklist):
        1. State Invariance: session_id, workspace_root, activation_time unchanged
        2. Side Effect Prohibition: Does NOT call LSP (GlobalLanguageServerPool's job),
           no logging, no metrics, no I/O
        3. Ordering Constraints: Thread-safe, idempotent (removing absent workspace is no-op)
        4. Resource Invariants: No external handles, no network connections
        5. Exception Safety: Never raises; always succeeds (idempotent)

        ERRORS: None (idempotent - removing non-existent workspace is silent no-op)
        """
        ...
