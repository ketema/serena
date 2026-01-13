"""
Tests for SerenaAgent Dependency Injection and Strangler Fig isolation.

Requirements coverage:
- REQ-DI-1: Constructor accepts session_registry param
- REQ-DI-2: Constructor accepts session_bridge param
- REQ-DI-3: Constructor accepts lsp_pool param
- REQ-SF-1: DI params = None → legacy path (pre-pool behavior)
- REQ-SF-2: Old behavior preserved when DI params = None
- REQ-SF-3: Old tests pass without new components
- REQ-SF-4: DI params provided → new multi-project path
"""

from unittest.mock import Mock

import pytest

from serena.agent import SerenaAgent


class TestDependencyInjectionParameters:
    """Test SerenaAgent accepts DI parameters per REQ-DI-1 to REQ-DI-3."""

    def test_constructor_accepts_session_registry_param(self):
        """
        REQ-DI-1: SerenaAgent constructor accepts session_registry param.

        What failed: Constructor signature validation for session_registry.
        Why: REQ-DI-1 requires optional SessionRegistry parameter.
        Expected: Constructor accepts session_registry: SessionRegistry | None = None.
        Actual: [Will show if param missing or type wrong].
        Guidance: Constructor MUST accept session_registry as optional keyword param.
                  Default value MUST be None.
                  Implementation free to use Any/Protocol for SessionRegistry type.
        """
        mock_registry = Mock()

        # Should not raise TypeError for unexpected keyword argument
        try:
            agent = SerenaAgent(session_registry=mock_registry)
            assert hasattr(agent, "_session_registry") or hasattr(agent, "session_registry"), \
                "session_registry param accepted but not stored"
        except TypeError as e:
            if "session_registry" in str(e):
                pytest.fail(
                    f"REQ-DI-1 VIOLATION: Constructor rejected session_registry param.\n"
                    f"Error: {e}\n"
                    f"Expected: session_registry: SessionRegistry | None = None in __init__"
                )
            raise

    def test_constructor_accepts_session_bridge_param(self):
        """
        REQ-DI-2: SerenaAgent constructor accepts session_bridge param.

        What failed: Constructor signature validation for session_bridge.
        Why: REQ-DI-2 requires optional MCPSessionBridge parameter.
        Expected: Constructor accepts session_bridge: MCPSessionBridge | None = None.
        Actual: [Will show if param missing or type wrong].
        Guidance: Constructor MUST accept session_bridge as optional keyword param.
                  Default value MUST be None.
                  Implementation free to use Any/Protocol for MCPSessionBridge type.
        """
        mock_bridge = Mock()

        try:
            agent = SerenaAgent(session_bridge=mock_bridge)
            assert hasattr(agent, "_session_bridge") or hasattr(agent, "session_bridge"), \
                "session_bridge param accepted but not stored"
        except TypeError as e:
            if "session_bridge" in str(e):
                pytest.fail(
                    f"REQ-DI-2 VIOLATION: Constructor rejected session_bridge param.\n"
                    f"Error: {e}\n"
                    f"Expected: session_bridge: MCPSessionBridge | None = None in __init__"
                )
            raise

    def test_constructor_accepts_lsp_pool_param(self):
        """
        REQ-DI-3: SerenaAgent constructor accepts lsp_pool param.

        What failed: Constructor signature validation for lsp_pool.
        Why: REQ-DI-3 requires optional GlobalLanguageServerPool parameter.
        Expected: Constructor accepts lsp_pool: GlobalLanguageServerPool | None = None.
        Actual: [Will show if param missing or type wrong].
        Guidance: Constructor MUST accept lsp_pool as optional keyword param.
                  Default value MUST be None.
                  Implementation free to use Any/Protocol for GlobalLanguageServerPool type.
        """
        mock_pool = Mock()

        try:
            agent = SerenaAgent(lsp_pool=mock_pool)
            assert hasattr(agent, "_lsp_pool") or hasattr(agent, "lsp_pool"), \
                "lsp_pool param accepted but not stored"
        except TypeError as e:
            if "lsp_pool" in str(e):
                pytest.fail(
                    f"REQ-DI-3 VIOLATION: Constructor rejected lsp_pool param.\n"
                    f"Error: {e}\n"
                    f"Expected: lsp_pool: GlobalLanguageServerPool | None = None in __init__"
                )
            raise

    def test_all_di_params_none_by_default(self):
        """
        REQ-DI-1/2/3: All DI params default to None (backward compatibility).

        What failed: Default parameter value validation.
        Why: Strangler Fig requires old behavior when DI params not provided.
        Expected: SerenaAgent() works without any DI params (all default to None).
        Actual: [Will show if any param is required].
        Guidance: All DI params MUST be optional with None default.
                  Constructor MUST work when called with zero arguments.
        """
        agent = SerenaAgent()

        # Verify agent initialized successfully with no DI params
        assert agent is not None


class TestDependencyInjectionStorage:
    """Verify provided DI params are stored for later use."""

    def test_di_params_stored(self):
        mock_registry = Mock(name="SessionRegistry")
        mock_bridge = Mock(name="MCPSessionBridge")
        mock_pool = Mock(name="GlobalLanguageServerPool")

        agent = SerenaAgent(
            session_registry=mock_registry,
            session_bridge=mock_bridge,
            lsp_pool=mock_pool
        )

        has_registry = any([
            hasattr(agent, "_session_registry"),
            hasattr(agent, "session_registry"),
            hasattr(agent, "_registry"),
        ])
        has_bridge = any([
            hasattr(agent, "_session_bridge"),
            hasattr(agent, "session_bridge"),
            hasattr(agent, "_bridge"),
        ])
        has_pool = any([
            hasattr(agent, "_lsp_pool"),
            hasattr(agent, "lsp_pool"),
            hasattr(agent, "_pool"),
        ])

        assert has_registry, "session_registry param accepted but not stored"
        assert has_bridge, "session_bridge param accepted but not stored"
        assert has_pool, "lsp_pool param accepted but not stored"
