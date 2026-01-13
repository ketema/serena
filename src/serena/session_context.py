"""
Session context propagation via ContextVar.

Contract alignment: contracts/serena_agent_stateless_contract.py
"""

from contextvars import ContextVar
from typing import Optional

from serena.session_registry import SessionContext

_current_session: ContextVar[Optional[SessionContext]] = ContextVar("_current_session", default=None)


def get_current_session() -> Optional[SessionContext]:
    """
    Get current session from ContextVar.

    PRE: None (always callable)
    POST: Returns SessionContext if set in current async context
    POST: Returns None if no session bound in current context
    ERRORS: None
    """
    return _current_session.get()


def set_current_session(session: Optional[SessionContext]) -> None:
    """
    Set current session in ContextVar.

    PRE: session is SessionContext or None
    POST: get_current_session() returns session in current async context
    POST: Other async contexts unchanged (ContextVar isolation)
    ERRORS: None
    """
    _current_session.set(session)
