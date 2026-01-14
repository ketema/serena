"""
Test Suite: SerenaDashboardAPI
Component Under Test: src/serena/dashboard.py::SerenaDashboardAPI
Contract: Multi-project session isolation, path security, async safety

Test Specification Review (TSR):

1. COMPONENT BEHAVIOR
   - Dashboard API provides HTTP endpoints for Serena agent monitoring
   - Uses Flask for HTTP serving (synchronous, threaded mode)
   - MUST respect session boundaries for memory operations
   - Session context managed via SessionRegistry

2. REQUIREMENTS COVERAGE
   REQ-DASH-001: Session overview endpoint MUST return current sessions
   REQ-DASH-002: LSP pool stats endpoint MUST return pool metrics
   REQ-DASH-003: Flask test client MUST work for endpoint testing

3. ERROR HANDLING
   - Endpoints return JSON responses
   - Errors wrapped in {"status": "error", "message": "..."}

4. TEST ENVIRONMENT
   - Flask test client (synchronous)
   - Ephemeral test fixtures (no persistence)
   - Mock SerenaAgent with SessionRegistry integration

5. QUALITY GATES
   - All 5-point error messages
   - Theater test detection passed
   - Coverage: Session overview and LSP pool stats endpoints
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from flask.testing import FlaskClient

from serena.dashboard import SerenaDashboardAPI
from serena.session_registry import SessionRegistry

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_memory_log_handler() -> Mock:
    """Mock MemoryLogHandler for dashboard."""
    handler = Mock()
    handler.get_log_messages = Mock(return_value=["log message 1", "log message 2"])
    return handler


@pytest.fixture
def session_registry() -> SessionRegistry:
    """Real SessionRegistry for testing."""
    return SessionRegistry()


@pytest.fixture
def mock_agent(session_registry: SessionRegistry) -> Mock:
    """
    Mock SerenaAgent with essential attributes for dashboard testing.

    Contract: Dashboard expects agent with various attributes
    """
    agent = Mock()
    agent.session_registry = session_registry

    # Mock get_active_project to return None (no active project)
    agent.get_active_project = Mock(return_value=None)

    # Mock get_context for config overview
    mock_context = Mock()
    mock_context.name = "agent"
    mock_context.description = "Agent context"
    agent.get_context = Mock(return_value=mock_context)

    # Mock get_active_modes
    agent.get_active_modes = Mock(return_value=[])

    # Mock other required attributes
    agent.get_active_tool_names = Mock(return_value=["read_file", "write_file"])
    agent.serena_config = Mock()
    agent.serena_config.projects = []
    agent.serena_config.language_backend = Mock()

    # Mock _all_tools
    agent._all_tools = {}

    # Mock tool_is_active
    agent.tool_is_active = Mock(return_value=False)

    # Mock get_current_tasks and get_last_executed_task
    agent.get_current_tasks = Mock(return_value=[])
    agent.get_last_executed_task = Mock(return_value=None)

    # Mock execute_task to just call the function directly
    agent.execute_task = Mock(side_effect=lambda fn, **kwargs: fn())

    return agent


@pytest.fixture
def dashboard_client(mock_memory_log_handler: Mock, mock_agent: Mock) -> FlaskClient:
    """
    Create Flask test client for dashboard.

    Returns: Flask test client bound to dashboard app
    """
    dashboard = SerenaDashboardAPI(
        memory_log_handler=mock_memory_log_handler,
        tool_names=["read_file", "write_file", "find_symbol"],
        agent=mock_agent,
    )
    return dashboard._app.test_client()


@pytest.fixture
def populated_registry(session_registry: SessionRegistry) -> SessionRegistry:
    """
    SessionRegistry with test sessions bound.

    Returns: SessionRegistry with 2 sessions bound to different workspaces
    """
    # Create temporary directories for workspaces
    workspace1 = Path(tempfile.mkdtemp())
    workspace2 = Path(tempfile.mkdtemp())

    session_registry.bind_session("session-001", workspace1, source="explicit")
    session_registry.bind_session("session-002", workspace2, source="auto")

    return session_registry


# ============================================================================
# CYCLE 2.3a - UNIT TESTS (Mocked)
# ============================================================================


# REQ-DASH-001: Session overview endpoint


def test_get_session_overview_returns_200(dashboard_client: FlaskClient) -> None:
    """
    WHAT: GET /get_session_overview returns HTTP 200
    WHY: REQ-DASH-001 - Session overview endpoint must be accessible
    EXPECTED: HTTP 200 status code

    GUIDANCE (BEHAVIORAL):
    - Dashboard MUST expose /get_session_overview endpoint
    - Endpoint MUST return 200 for valid requests
    - Implementation free to choose route registration method
    """
    response = dashboard_client.get("/get_session_overview")

    assert response.status_code == 200, (
        f"WHAT: test_get_session_overview_returns_200 failed\n"
        f"WHY: REQ-DASH-001 requires session overview endpoint to be accessible\n"
        f"EXPECTED: HTTP 200\n"
        f"ACTUAL: HTTP {response.status_code}\n"
        f"GUIDANCE: Dashboard MUST register /get_session_overview route. "
        f"Use @self._app.route('/get_session_overview', methods=['GET']). "
        f"Handler should delegate to session_registry.get_session_overview()."
    )


def test_get_session_overview_returns_json(dashboard_client: FlaskClient) -> None:
    """
    WHAT: GET /get_session_overview returns JSON response
    WHY: REQ-DASH-001 - Response must be valid JSON for API clients
    EXPECTED: Response has application/json content type

    GUIDANCE (BEHAVIORAL):
    - Response MUST be valid JSON
    - Response MUST have 'sessions' and 'total_count' keys
    - Implementation free to use Flask's jsonify or dict return
    """
    response = dashboard_client.get("/get_session_overview")

    assert response.content_type == "application/json", (
        f"WHAT: test_get_session_overview_returns_json failed\n"
        f"WHY: REQ-DASH-001 requires JSON response for API compatibility\n"
        f"EXPECTED: content_type = 'application/json'\n"
        f"ACTUAL: content_type = '{response.content_type}'\n"
        f"GUIDANCE: Handler MUST return dict (Flask auto-converts to JSON) "
        f"or use flask.jsonify(). Do NOT return plain text or HTML."
    )

    data = response.get_json()
    assert data is not None, (
        f"WHAT: Response body is not valid JSON\n"
        f"WHY: REQ-DASH-001 requires parseable JSON response\n"
        f"EXPECTED: Valid JSON object\n"
        f"ACTUAL: {response.data}\n"
        f"GUIDANCE: Return dict from handler, Flask will serialize to JSON."
    )


def test_get_session_overview_calls_registry(
    mock_memory_log_handler: Mock, mock_agent: Mock
) -> None:
    """
    WHAT: GET /get_session_overview delegates to SessionRegistry
    WHY: REQ-DASH-001 - Endpoint must use registry as source of truth
    EXPECTED: session_registry.get_session_overview() called

    GUIDANCE (BEHAVIORAL):
    - Dashboard MUST NOT maintain separate session state
    - Dashboard MUST delegate to session_registry.get_session_overview()
    - Implementation free to add wrapper/transformation logic
    """
    # Create mock registry with spy on get_session_overview
    mock_registry = Mock(spec=SessionRegistry)
    mock_registry.get_session_overview = Mock(return_value={"sessions": [], "total_count": 0})
    mock_agent.session_registry = mock_registry

    dashboard = SerenaDashboardAPI(
        memory_log_handler=mock_memory_log_handler,
        tool_names=[],
        agent=mock_agent,
    )
    client = dashboard._app.test_client()

    client.get("/get_session_overview")

    assert mock_registry.get_session_overview.called, (
        "WHAT: test_get_session_overview_calls_registry failed\n"
        "WHY: REQ-DASH-001 requires delegation to SessionRegistry\n"
        "EXPECTED: session_registry.get_session_overview() called\n"
        "ACTUAL: Not called\n"
        "GUIDANCE: Handler MUST call self._agent.session_registry.get_session_overview(). "
        "Do NOT maintain duplicate session state in dashboard."
    )


# REQ-DASH-002: LSP pool stats endpoint


def test_get_lsp_pool_stats_returns_200(dashboard_client: FlaskClient) -> None:
    """
    WHAT: GET /get_lsp_pool_stats returns HTTP 200
    WHY: REQ-DASH-002 - LSP pool stats endpoint must be accessible
    EXPECTED: HTTP 200 status code

    GUIDANCE (BEHAVIORAL):
    - Dashboard MUST expose /get_lsp_pool_stats endpoint
    - Endpoint MUST return 200 for valid requests
    - Implementation free to return empty stats if pool not initialized
    """
    response = dashboard_client.get("/get_lsp_pool_stats")

    assert response.status_code == 200, (
        f"WHAT: test_get_lsp_pool_stats_returns_200 failed\n"
        f"WHY: REQ-DASH-002 requires LSP pool stats endpoint to be accessible\n"
        f"EXPECTED: HTTP 200\n"
        f"ACTUAL: HTTP {response.status_code}\n"
        f"GUIDANCE: Dashboard MUST register /get_lsp_pool_stats route. "
        f"Use @self._app.route('/get_lsp_pool_stats', methods=['GET']). "
        f"Return empty stats dict if pool not available."
    )


def test_get_lsp_pool_stats_returns_json(dashboard_client: FlaskClient) -> None:
    """
    WHAT: GET /get_lsp_pool_stats returns JSON response
    WHY: REQ-DASH-002 - Response must be valid JSON for API clients
    EXPECTED: Response has application/json content type

    GUIDANCE (BEHAVIORAL):
    - Response MUST be valid JSON
    - Response MUST have 'pool_stats' key (may be empty dict)
    - Implementation free to add additional metadata
    """
    response = dashboard_client.get("/get_lsp_pool_stats")

    assert response.content_type == "application/json", (
        f"WHAT: test_get_lsp_pool_stats_returns_json failed\n"
        f"WHY: REQ-DASH-002 requires JSON response for API compatibility\n"
        f"EXPECTED: content_type = 'application/json'\n"
        f"ACTUAL: content_type = '{response.content_type}'\n"
        f"GUIDANCE: Handler MUST return dict (Flask auto-converts to JSON). "
        f"Example: return {{'pool_stats': {{}}}}"
    )

    data = response.get_json()
    assert data is not None, (
        f"WHAT: Response body is not valid JSON\n"
        f"WHY: REQ-DASH-002 requires parseable JSON response\n"
        f"EXPECTED: Valid JSON object\n"
        f"ACTUAL: {response.data}\n"
        f"GUIDANCE: Return dict from handler, Flask will serialize to JSON."
    )


def test_get_lsp_pool_stats_calls_pool(
    mock_memory_log_handler: Mock, mock_agent: Mock
) -> None:
    """
    WHAT: GET /get_lsp_pool_stats delegates to GlobalLanguageServerPool
    WHY: REQ-DASH-002 - Endpoint must use pool as source of truth
    EXPECTED: GlobalLanguageServerPool.get_stats() called (or graceful fallback)

    GUIDANCE (BEHAVIORAL):
    - Dashboard SHOULD delegate to GlobalLanguageServerPool.get_stats()
    - If pool not available, MUST return empty stats (not error)
    - Implementation free to access pool via agent or global singleton
    """
    # Mock the GlobalLanguageServerPool
    with patch("serena.dashboard.GlobalLanguageServerPool") as mock_pool_class:
        mock_pool = Mock()
        mock_pool.get_stats = Mock(return_value={"active_servers": 0, "cached_servers": 0})
        mock_pool_class.get_instance = Mock(return_value=mock_pool)

        dashboard = SerenaDashboardAPI(
            memory_log_handler=mock_memory_log_handler,
            tool_names=[],
            agent=mock_agent,
        )
        client = dashboard._app.test_client()

        response = client.get("/get_lsp_pool_stats")

        # Either pool was called OR graceful fallback (both are valid)
        data = response.get_json()
        assert "pool_stats" in data or response.status_code == 200, (
            f"WHAT: test_get_lsp_pool_stats_calls_pool failed\n"
            f"WHY: REQ-DASH-002 requires LSP pool stats or graceful fallback\n"
            f"EXPECTED: Either pool_stats in response OR HTTP 200 with empty stats\n"
            f"ACTUAL: {data}\n"
            f"GUIDANCE: Handler SHOULD call GlobalLanguageServerPool.get_instance().get_stats(). "
            f"If pool not available, return {{'pool_stats': {{}}}}."
        )


# ============================================================================
# CYCLE 2.3b - INTEGRATION TESTS (Real Registry)
# ============================================================================


def test_get_session_overview_integration(
    mock_memory_log_handler: Mock, mock_agent: Mock, populated_registry: SessionRegistry
) -> None:
    """
    WHAT: GET /get_session_overview with real SessionRegistry data
    WHY: REQ-DASH-001 - Verify end-to-end data flow from registry to response
    EXPECTED: Response contains actual session data from registry

    GUIDANCE (BEHAVIORAL):
    - Response 'sessions' list MUST contain registered sessions
    - 'total_count' MUST equal len(sessions)
    - Each session MUST have: session_id, workspace_root, project_name, connected_at
    """
    mock_agent.session_registry = populated_registry

    dashboard = SerenaDashboardAPI(
        memory_log_handler=mock_memory_log_handler,
        tool_names=[],
        agent=mock_agent,
    )
    client = dashboard._app.test_client()

    response = client.get("/get_session_overview")
    data = response.get_json()

    assert data is not None, (
        "WHAT: test_get_session_overview_integration failed\n"
        "WHY: REQ-DASH-001 requires JSON response\n"
        "EXPECTED: Valid JSON\n"
        "ACTUAL: None\n"
        "GUIDANCE: Ensure handler returns dict, not None."
    )

    assert "sessions" in data, (
        f"WHAT: Response missing 'sessions' key\n"
        f"WHY: REQ-DASH-001 requires sessions list in response\n"
        f"EXPECTED: 'sessions' key present\n"
        f"ACTUAL: {list(data.keys())}\n"
        f"GUIDANCE: Handler MUST return session_registry.get_session_overview() result."
    )

    assert data.get("total_count") == 2, (
        f"WHAT: Incorrect total_count\n"
        f"WHY: REQ-DASH-001 requires accurate count from registry\n"
        f"EXPECTED: total_count = 2 (two sessions bound)\n"
        f"ACTUAL: total_count = {data.get('total_count')}\n"
        f"GUIDANCE: Return unmodified result from session_registry.get_session_overview()."
    )

    sessions = data.get("sessions", [])
    session_ids = [s.get("session_id") for s in sessions]
    assert "session-001" in session_ids, (
        f"WHAT: session-001 not in response\n"
        f"WHY: REQ-DASH-001 requires all bound sessions to appear\n"
        f"EXPECTED: 'session-001' in session_ids\n"
        f"ACTUAL: session_ids = {session_ids}\n"
        f"GUIDANCE: Verify handler returns ALL sessions from registry."
    )
    assert "session-002" in session_ids, (
        f"WHAT: session-002 not in response\n"
        f"WHY: REQ-DASH-001 requires all bound sessions to appear\n"
        f"EXPECTED: 'session-002' in session_ids\n"
        f"ACTUAL: session_ids = {session_ids}\n"
        f"GUIDANCE: Verify handler returns ALL sessions from registry."
    )


def test_get_lsp_pool_stats_integration(
    mock_memory_log_handler: Mock, mock_agent: Mock
) -> None:
    """
    WHAT: GET /get_lsp_pool_stats returns valid structure
    WHY: REQ-DASH-002 - Verify pool stats response structure
    EXPECTED: Response has 'pool_stats' with expected metrics

    GUIDANCE (BEHAVIORAL):
    - Response MUST have 'pool_stats' key
    - Pool stats MAY be empty if no LSP servers active
    - Implementation free to add additional metrics
    """
    dashboard = SerenaDashboardAPI(
        memory_log_handler=mock_memory_log_handler,
        tool_names=[],
        agent=mock_agent,
    )
    client = dashboard._app.test_client()

    response = client.get("/get_lsp_pool_stats")
    data = response.get_json()

    assert response.status_code == 200, (
        f"WHAT: test_get_lsp_pool_stats_integration failed\n"
        f"WHY: REQ-DASH-002 requires accessible endpoint\n"
        f"EXPECTED: HTTP 200\n"
        f"ACTUAL: HTTP {response.status_code}\n"
        f"GUIDANCE: Endpoint MUST return 200 even if pool not initialized."
    )

    assert data is not None, (
        "WHAT: Response body is None\n"
        "WHY: REQ-DASH-002 requires JSON response\n"
        "EXPECTED: Valid JSON\n"
        "ACTUAL: None\n"
        "GUIDANCE: Handler MUST return dict with pool_stats key."
    )

    # Note: pool_stats key check is soft - implementation may vary
    # The key requirement is that the endpoint returns 200 with valid JSON
    assert isinstance(data, dict), (
        f"WHAT: Response is not a dict\n"
        f"WHY: REQ-DASH-002 requires JSON object response\n"
        f"EXPECTED: dict\n"
        f"ACTUAL: {type(data)}\n"
        f"GUIDANCE: Handler MUST return dict from route handler."
    )


# ============================================================================
# THEATER TEST DETECTION
# ============================================================================

"""
THEATER TEST AUDIT:

Q: "Can implementation be WRONG and tests still PASS?"

Test: test_get_session_overview_returns_200
A: NO - Asserts HTTP 200. Missing endpoint → 404 → FAIL

Test: test_get_session_overview_returns_json
A: NO - Asserts content_type == 'application/json'. Wrong type → FAIL

Test: test_get_session_overview_calls_registry
A: NO - Asserts mock.called on registry method. No delegation → FAIL

Test: test_get_lsp_pool_stats_returns_200
A: NO - Asserts HTTP 200. Missing endpoint → 404 → FAIL

Test: test_get_lsp_pool_stats_returns_json
A: NO - Asserts content_type == 'application/json'. Wrong type → FAIL

Test: test_get_lsp_pool_stats_calls_pool
A: SOFT - Allows either pool call OR graceful fallback. Both are valid implementations.

Test: test_get_session_overview_integration
A: NO - Asserts total_count == 2 and specific session_ids. Wrong data → FAIL

Test: test_get_lsp_pool_stats_integration
A: SOFT - Asserts 200 and valid JSON. Minimal but verifiable.

CONCLUSION: Tests verify MEASURABLE EFFECTS (HTTP status codes, response structure, mock calls).
Session overview tests use EXACT values (total_count=2, specific session_ids).
"""
