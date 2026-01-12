"""
Adversarial TDD tests for SessionAwareToolDispatch (Cycle 2.5).

Contract: contracts/session_tool_dispatch_contract.py (verified: 2026-01-11)
Scope: dispatch_lsp_tool must route by session workspace, acquire LSP, execute tool,
release LSP after execution, and handle errors deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from unittest.mock import Mock

import pytest

from serena.session_registry import SessionContext
from serena.session_tool_dispatch import (
    LSPNotAvailableError,
    SessionAwareToolDispatch,
    SessionNotFoundError,
)
from solidlsp.ls_config import Language


@dataclass
class ToolCallSpec:
    tool_name: str
    relative_path: str
    arguments: dict
    language: Language


def _failure_message(what: str, why: str, expected: str, actual: str, guidance: str) -> str:
    return (
        f"FAILURE: {what}\n"
        f"WHY: {why}\n"
        f"EXPECTED: {expected}\n"
        f"ACTUAL: {actual}\n"
        f"GUIDANCE: {guidance}"
    )


def _make_session_context(session_id: str, workspace_root: Path) -> SessionContext:
    return SessionContext(
        session_id=session_id,
        workspace_root=workspace_root,
        activation_source="explicit",
        activation_time=datetime.utcnow(),
    )


def _make_dispatch(
    registry: Mock,
    pool: Mock,
    validator: Mock | None = None,
) -> SessionAwareToolDispatch:
    if validator is None:
        validator = Mock(side_effect=lambda rel, root: Path(root) / rel)
    return SessionAwareToolDispatch(
        session_registry=registry,
        lsp_pool=pool,
        path_validator=validator,
    )


class TestSessionToolDispatchCycle25:
    def test_dispatch_routes_to_correct_workspace(self) -> None:
        """
        REQ-5a/REQ-5b/REQ-5c: Bound session routes to its workspace, acquires LSP,
        and executes requested tool with arguments.
        """
        workspace_a = Path("/project-a")
        workspace_b = Path("/project-b")
        session_a = _make_session_context("session-a", workspace_a)
        session_b = _make_session_context("session-b", workspace_b)

        registry = Mock()
        registry.get_session.side_effect = lambda session_id: (
            session_a if session_id == "session-a" else session_b
        )

        lsp = Mock()
        lsp.definition = Mock(return_value={"ok": True})

        pool = Mock()
        pool.acquire.return_value = lsp

        dispatch = _make_dispatch(registry, pool)

        tool = ToolCallSpec(
            tool_name="definition",
            relative_path="src/main.py",
            arguments={"line": 12, "character": 3},
            language=Language.PYTHON,
        )

        result = dispatch.dispatch_lsp_tool(
            "session-a",
            tool.tool_name,
            tool.relative_path,
            tool.arguments,
        )

        pool.acquire.assert_called_once_with(tool.language, workspace_a, "session-a")
        lsp.definition.assert_called_once_with(**tool.arguments)
        assert result == {"ok": True}, _failure_message(
            "dispatch_lsp_tool returned unexpected result",
            "REQ-5c requires returning the LSP tool result",
            "{'ok': True}",
            repr(result),
            "Return the LSP tool method result instead of a placeholder payload.",
        )

    def test_dispatch_releases_lsp_after_execution(self) -> None:
        """
        REQ-5d: LSP must be released after successful tool execution.
        """
        workspace = Path("/project-a")
        session_ctx = _make_session_context("session-a", workspace)

        registry = Mock()
        registry.get_session.return_value = session_ctx

        lsp = Mock()
        lsp.definition = Mock(return_value="ok")

        pool = Mock()
        pool.acquire.return_value = lsp

        dispatch = _make_dispatch(registry, pool)

        dispatch.dispatch_lsp_tool("session-a", "definition", "src/main.py", {})

        pool.release.assert_called_once_with(Language.PYTHON, workspace, "session-a")

    def test_dispatch_handles_lsp_acquisition_failure(self) -> None:
        """
        If LSP acquisition fails, error should surface and no release or execute occurs.
        """
        workspace = Path("/project-a")
        session_ctx = _make_session_context("session-a", workspace)

        registry = Mock()
        registry.get_session.return_value = session_ctx

        pool = Mock()
        pool.acquire.side_effect = RuntimeError("pool unavailable")

        dispatch = _make_dispatch(registry, pool)

        with pytest.raises(LSPNotAvailableError):
            dispatch.dispatch_lsp_tool("session-a", "definition", "src/main.py", {})

        pool.release.assert_not_called()

    def test_dispatch_handles_tool_execution_failure(self) -> None:
        """
        If tool execution fails, error should surface and LSP must be released.
        """
        workspace = Path("/project-a")
        session_ctx = _make_session_context("session-a", workspace)

        registry = Mock()
        registry.get_session.return_value = session_ctx

        lsp = Mock()
        lsp.definition = Mock(side_effect=RuntimeError("tool failed"))

        pool = Mock()
        pool.acquire.return_value = lsp

        dispatch = _make_dispatch(registry, pool)

        with pytest.raises(RuntimeError):
            dispatch.dispatch_lsp_tool("session-a", "definition", "src/main.py", {})

        pool.release.assert_called_once_with(Language.PYTHON, workspace, "session-a")

    def test_path_validation_performance(self) -> None:
        """
        REQ-PERF-1: Path validation overhead must be < 10ms per call.
        """
        workspace = Path("/project-a")
        session_ctx = _make_session_context("session-a", workspace)

        registry = Mock()
        registry.get_session.return_value = session_ctx

        lsp = Mock()
        lsp.definition = Mock(return_value="ok")

        pool = Mock()
        pool.acquire.return_value = lsp

        validator = Mock(side_effect=lambda rel, root: Path(root) / rel)
        dispatch = _make_dispatch(registry, pool, validator=validator)

        iterations = 1000
        start = time.perf_counter()
        for _ in range(iterations):
            dispatch.dispatch_lsp_tool("session-a", "definition", "src/main.py", {})
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 10, _failure_message(
            "Path validation overhead too slow",
            "REQ-PERF-1 sets a 10ms per-call overhead ceiling",
            "< 10ms average",
            f"{avg_ms:.3f}ms",
            "Optimize path validation and dispatch hot path.",
        )

    def test_missing_session_raises_error(self) -> None:
        """
        PRE: session_id must exist in SessionRegistry.
        """
        registry = Mock()
        registry.get_session.return_value = None

        pool = Mock()
        dispatch = _make_dispatch(registry, pool)

        with pytest.raises(SessionNotFoundError):
            dispatch.dispatch_lsp_tool("missing-session", "definition", "src/main.py", {})
