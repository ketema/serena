"""
Tests for SerenaAgent Dependency Injection and Strangler Fig isolation.

Requirements coverage:
- REQ-DI-1: Constructor accepts session_registry param
- REQ-DI-2: Constructor accepts session_bridge param
- REQ-DI-3: Constructor accepts lsp_pool param
- REQ-SF-1: DI params = None → old path (LanguageServerManager)
- REQ-SF-2: Old behavior preserved when DI params = None
- REQ-SF-3: Old tests pass without new components
- REQ-SF-4: DI params provided → new multi-project path
"""

from unittest.mock import MagicMock, Mock, patch

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
            with patch("serena.agent.LanguageServerManager"):
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
            with patch("serena.agent.LanguageServerManager"):
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
            with patch("serena.agent.LanguageServerManager"):
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
        with patch("serena.agent.LanguageServerManager"):
            agent = SerenaAgent()

        # Verify agent initialized successfully with no DI params
        assert agent is not None


class TestStranglerFigOldPath:
    """Test old path used when DI params = None per REQ-SF-1/2."""

    @patch("serena.agent.LanguageServerManager")
    def test_none_di_params_use_old_path(self, mock_lsm_class):
        """
        REQ-SF-1: DI params = None → SerenaAgent uses old path (LanguageServerManager).

        What failed: Old path verification when DI params = None.
        Why: REQ-SF-1 requires LanguageServerManager used when no DI params provided.
        Expected: SerenaAgent with DI params = None creates LanguageServerManager instance.
        Actual: [Will show if LanguageServerManager not instantiated or DI services accessed].
        Guidance: When session_registry AND session_bridge AND lsp_pool are ALL None,
                  MUST use LanguageServerManager (old path).
                  MUST NOT access any DI params when they are None.
                  Implementation free to choose: if-check, factory pattern, strategy pattern.
        """
        mock_lsm_instance = MagicMock()
        mock_lsm_class.return_value = mock_lsm_instance

        _ = SerenaAgent(
            session_registry=None,
            session_bridge=None,
            lsp_pool=None
        )

        # Verify LanguageServerManager was created (old path)
        assert mock_lsm_class.called, \
            "REQ-SF-1 VIOLATION: LanguageServerManager not created when DI params = None"

    @patch("serena.agent.LanguageServerManager")
    def test_old_behavior_preserved_with_none_params(self, mock_lsm_class):
        """
        REQ-SF-2: Old behavior preserved when DI params = None.

        What failed: Backward compatibility validation.
        Why: REQ-SF-2 requires identical behavior to pre-DI implementation.
        Expected: SerenaAgent with DI params = None behaves identically to old version.
                  LanguageServerManager receives same initialization as before DI.
        Actual: [Will show if initialization differs from old behavior].
        Guidance: When DI params = None, initialization sequence MUST match pre-DI version.
                  Any new code paths MUST be skipped when DI params absent.
                  Old initialization logic MUST remain untouched.
        """
        mock_lsm_instance = MagicMock()
        mock_lsm_class.return_value = mock_lsm_instance

        _ = SerenaAgent()  # No DI params, just like old usage

        # Verify LanguageServerManager created with expected args
        # (implementation detail: verify it was called at all, exact args may vary)
        assert mock_lsm_class.called, \
            "REQ-SF-2 VIOLATION: Old path not taken when DI params omitted"


class TestStranglerFigNewPath:
    """Test new path used when DI params provided per REQ-SF-4."""

    @patch("serena.agent.LanguageServerManager")
    def test_partial_di_params_use_new_path(self, mock_lsm_class):
        """
        REQ-SF-4: Even partial DI params → new path (no LanguageServerManager).

        What failed: New path verification when only some DI params provided.
        Why: REQ-SF-4 requires new path when ANY DI param is not None.
        Expected: Providing only one DI param triggers new path (LanguageServerManager NOT created).
        Actual: [Will show if LanguageServerManager created with partial DI].
        Guidance: When ANY of session_registry/bridge/pool is not None,
                  MUST use new multi-project path.
                  MUST NOT create LanguageServerManager even with partial DI.
                  Implementation free to: handle None DI params gracefully, create missing services internally, etc.
        """
        mock_registry = Mock(name="SessionRegistry")

        # Only session_registry provided, others None
        _ = SerenaAgent(session_registry=mock_registry)

        # Verify LanguageServerManager was NOT created (new path even with partial DI)
        assert not mock_lsm_class.called, \
            "REQ-SF-4 VIOLATION: LanguageServerManager created when partial DI params provided (should use new path)"

    @patch("serena.agent.LanguageServerManager")
    def test_di_params_provided_use_new_path(self, mock_lsm_class):
        """
        REQ-SF-4: DI params provided → SerenaAgent uses new multi-project path.

        What failed: New path verification when DI params provided.
        Why: REQ-SF-4 requires new services used when DI params provided.
        Expected: When session_registry/bridge/pool provided, SerenaAgent uses them (new path).
                  LanguageServerManager MUST NOT be created when DI params provided.
        Actual: [Will show if LanguageServerManager created or DI params ignored].
        Guidance: When ANY of session_registry/bridge/pool is not None,
                  MUST use provided DI services (new multi-project path).
                  MUST NOT create LanguageServerManager when DI params provided.
                  MUST store DI params for later use.
                  Implementation free to choose: if-check, factory pattern, strategy pattern.
        """
        mock_registry = Mock(name="SessionRegistry")
        mock_bridge = Mock(name="MCPSessionBridge")
        mock_pool = Mock(name="GlobalLanguageServerPool")

        agent = SerenaAgent(
            session_registry=mock_registry,
            session_bridge=mock_bridge,
            lsp_pool=mock_pool
        )

        # Verify LanguageServerManager was NOT created (new path taken)
        assert not mock_lsm_class.called, \
            "REQ-SF-4 VIOLATION: LanguageServerManager created when DI params provided (should use new path)"

        # Verify DI params stored (implementation may use different attribute names)
        # Check common attribute naming patterns
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
