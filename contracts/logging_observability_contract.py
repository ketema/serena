"""
Logging Observability Contract — Production Logging for ketema Branch Additions

PURPOSE: Define mandatory logging for LSP lifecycle, session management, and security
         events to provide full chain observability.

AUTHORITY: This is the singular authority for logging requirements on ketema branch code.
           Existing logging in upstream Serena is NOT covered by this contract.

CONVENTION REFERENCES:
  - LOG-1: Session context prefix [Session: <short_id> | <project_name>] <message>
  - LOG-2: LSP lifecycle events at INFO with resource details
  - LOG-3: Path validation failures as security boundary violations
  - Format: f-string (user decision 2026-02-07)
  - Logger init: logging.getLogger(__name__)

APPROVED PLAN: AI Panel conversation f1619c40-e8e1-4b8b-8596-351c89941d69
"""

# =============================================================================
# TIER 1: Pool Operations (GlobalLanguageServerPool) — CRITICAL
# File: src/serena/global_lsp_pool.py
# Session context: AVAILABLE (session_id is method parameter)
# =============================================================================

LOG_POOL_01 = """
LOG-POOL-01: GlobalLanguageServerPool.acquire() — Successful Acquisition

POST: On every successful return, MUST emit one INFO log containing:
  - language name (e.g., "python")
  - workspace_root path
  - session_id
  - acquisition mode: "new" (new LSP created) or "shared" (existing LSP reused)

FORMAT: "[LSP-Pool] Acquired {language} LSP for {workspace_root} "
        "(Session: {session_id}, Mode: {new|shared})"

LEVEL: INFO
WHEN: After successful LSP return, before method exit
NOTE: Crash recovery path already has logger.warning(); this clause covers the happy path.
"""

LOG_POOL_02 = """
LOG-POOL-02: GlobalLanguageServerPool.release() — Session Reference Release

POST: On every release call where session_id was actually removed, MUST emit one INFO log:
  - language name
  - workspace_root path
  - session_id being released
  - ref_count AFTER removal

FORMAT: "[LSP-Pool] Released {language} LSP for {workspace_root} "
        "(Session: {session_id}, Remaining refs: {ref_count})"

LEVEL: INFO
WHEN: After session_id removal from reference set

POST-ZERO: When ref_count reaches 0, MUST emit additional INFO log:
FORMAT-ZERO: "[LSP-Pool] {language} LSP for {workspace_root} has zero references, "
             "starting idle timer"

LEVEL: INFO
WHEN: After ref_count == 0 cleanup (workspace folder removal, idle timer start)

POST-NOOP: When pool_key not found (idempotent no-op), MUST emit DEBUG log.
LEVEL: DEBUG
"""

LOG_POOL_03 = """
LOG-POOL-03: GlobalLanguageServerPool.surgical_restart_lsp() — Surgical Restart

POST-START: MUST emit INFO log at start of restart:
FORMAT: "[LSP-Pool] Surgical restart: stopping {language} LSP "
        "(workspace_roots: {count})"
LEVEL: INFO

POST-COMPLETE: MUST emit INFO log after successful restart:
FORMAT: "[LSP-Pool] Surgical restart complete: {language} LSP restarted, "
        "{count} workspace root(s) restored"
LEVEL: INFO

WHEN: Before returning new_lsp
NOTE: Session references are preserved (not modified), no logging needed for refs.
"""

LOG_POOL_04 = """
LOG-POOL-04: GlobalLanguageServerPool.stop_all() — Pool Shutdown

POST: MUST emit INFO log with count of LSPs being stopped:
FORMAT: "[LSP-Pool] Stopping all LSPs ({count} instances, save_cache={save_cache})"
LEVEL: INFO
WHEN: Before stopping loop begins
"""

LOG_POOL_05 = """
LOG-POOL-05: GlobalLanguageServerPool._on_idle_timeout() — Idle Reclamation

POST: When keys_to_reclaim is non-empty, MUST emit INFO log per reclamation:
FORMAT: "[LSP-Pool] Reclaiming idle {language} LSP for {workspace_root}"
LEVEL: INFO
WHEN: Before invoking reclaim_callback for each key

NOTE: Error path already has logger.exception(); this clause covers the success path.
"""


# =============================================================================
# TIER 2: Bridge Cleanup Chain (MCPSessionBridge) — CRITICAL
# File: src/serena/mcp_session_bridge.py
# Session context: AVAILABLE (mcp_session_id is method parameter)
# =============================================================================

LOG_BRIDGE_01 = """
LOG-BRIDGE-01: MCPSessionBridge.on_transport_session_closed() — Per-Language Release

POST: For EACH language in the cleanup loop, MUST emit INFO log:
FORMAT: "[Session: {short_id}] Releasing {language} LSP for {workspace_root}"
LEVEL: INFO
WHEN: Before each pool.release() call in the cleanup loop

NOTE: This makes the cleanup chain observable. Currently you see "MCP session closed: X"
      but nothing about what LSP resources were released.
"""

LOG_BRIDGE_02 = """
LOG-BRIDGE-02: MCPSessionBridge.on_transport_session_closed() — No Pool Available

POST: When self._lsp_pool is None, MUST emit DEBUG log:
FORMAT: "[Session: {short_id}] No LSP pool available, skipping LSP cleanup"
LEVEL: DEBUG
WHEN: When lsp_pool is None (STDIO mode or pool not wired)
"""


# =============================================================================
# TIER 3: Exception Handling (SerenaAgent + Tool) — HIGH
# Files: src/serena/agent.py, src/serena/tools/tools_base.py
# Session context: NOT AVAILABLE (no session_id parameter in these methods)
# Logger variable: `log` (both files use `log = logging.getLogger(__name__)`)
# =============================================================================

LOG_EXC_01 = """
LOG-EXC-01: SerenaAgent.handle_lsp_termination() — Restart Initiated

POST: MUST emit INFO log at the start of the restart attempt:
FORMAT: "[LSP-Recovery] Surgical restart initiated for {language} LSP"
LEVEL: INFO
WHEN: Before calling surgical_restart_lsp()
"""

LOG_EXC_02 = """
LOG-EXC-02: SerenaAgent.handle_lsp_termination() — Probe Result

POST-READY: When probe_workspace_readiness returns True, MUST emit INFO log:
FORMAT: "[LSP-Recovery] {language} LSP ready after restart (workspace: {workspace_root})"
LEVEL: INFO

POST-TIMEOUT: When probe_workspace_readiness returns False, MUST emit WARNING log:
FORMAT: "[LSP-Recovery] {language} LSP not ready after {timeout}s (workspace: {workspace_root})"
LEVEL: WARNING
WHEN: After probe_workspace_readiness returns
"""

LOG_EXC_03 = """
LOG-EXC-03: SerenaAgent.handle_lsp_termination() — Retry Result

POST-SUCCESS: When retry_fn() succeeds, MUST emit INFO log:
FORMAT: "[LSP-Recovery] Retry succeeded for {language} LSP"
LEVEL: INFO

POST-TERMINATED: When retry_fn() raises termination again, MUST emit WARNING log:
FORMAT: "[LSP-Recovery] Retry failed for {language} LSP: second termination"
LEVEL: WARNING
WHEN: After retry_fn() completes or raises
"""

LOG_EXC_04 = """
LOG-EXC-04: SerenaAgent.handle_lsp_termination() — Restart Failure

POST: When LSPRestartError caught, MUST emit ERROR log:
FORMAT: "[LSP-Recovery] Restart failed for {language} LSP: {error}"
LEVEL: ERROR
WHEN: In the LSPRestartError except block

NOTE: The unexpected Exception path already has log.exception(); this clause
      covers the typed LSPRestartError path specifically.
"""

LOG_EXC_05 = """
LOG-EXC-05: Tool.apply_ex() — Recovery Outcome

POST: After handle_lsp_termination() returns, MUST emit INFO log showing outcome:
FORMAT (success): "[Tool] {tool_name}: LSP recovery succeeded"
FORMAT (error): "[Tool] {tool_name}: LSP recovery returned error"
LEVEL: INFO
WHEN: After result = self.agent.handle_lsp_termination(...) returns

NOTE: apply_ex() already logs "Language server terminated...Performing surgical restart".
      This clause adds the OUTCOME log that is currently missing.
      Determination: result starts with "Error:" → error outcome, else → success.
"""


# =============================================================================
# TIER 4: Session Registry — HIGH
# Files: src/serena/session_registry.py, src/serena/agent.py
# Session context: AVAILABLE (session_id is method parameter)
# Logger: session_registry.py needs `logger = logging.getLogger(__name__)` (NEW)
#         agent.py uses `log = logging.getLogger(__name__)` (existing)
# =============================================================================

LOG_REG_01 = """
LOG-REG-01: SessionRegistry.bind_session() — Session Bound

POST: MUST emit INFO log when session successfully bound:
FORMAT: "[Session: {short_id}] Bound to {workspace_root} (source: {source})"
LEVEL: INFO
WHEN: After session stored in _sessions dict, before return

NOTE: short_id = session_id[:8]. workspace_root may be None (HTTP mode),
      log "None" in that case.
"""

LOG_REG_02 = """
LOG-REG-02: SessionRegistry.unbind_session() — Session Unbound

POST: MUST emit INFO log when session removed:
FORMAT: "[Session: {short_id}] Unbound from {workspace_root}"
LEVEL: INFO
WHEN: After session removed from _sessions dict

POST-NOOP: When session_id not found, MUST emit DEBUG log:
FORMAT: "[Session: {short_id}] Unbind no-op: not in registry"
LEVEL: DEBUG
"""

LOG_REG_03 = """
LOG-REG-03: SessionRegistry.unbind_session() — Last Session for Workspace

POST: When last session for a workspace is removed (workspace_sessions becomes empty),
      MUST emit INFO log:
FORMAT: "[Session: {short_id}] Last session for {workspace_root}, workspace cleanup eligible"
LEVEL: INFO
WHEN: After workspace_sessions entry deleted (len == 0 check)
"""

LOG_REG_04 = """
LOG-REG-04: SerenaAgent.activate_session_project() — Project Activation

POST: MUST emit INFO log after successful project activation:
FORMAT: "[Session: {short_id}] Activated project at {workspace_root} (source: {source})"
LEVEL: INFO
WHEN: Before returning loaded Project

POST-REBIND: When re-binding from one workspace to another, MUST emit INFO log:
FORMAT: "[Session: {short_id}] Re-binding from {old_workspace} to {workspace_root}"
LEVEL: INFO
WHEN: Before unbind_session call during re-binding
"""

LOG_REG_05 = """
LOG-REG-05: SerenaAgent.deactivate_session() — Session Deactivation

POST: MUST emit INFO log showing deactivation with LSP cleanup summary:
FORMAT: "[Session: {short_id}] Deactivated (released {count} LSP reference(s))"
LEVEL: INFO
WHEN: After LSP references cleared, before unbind_session call

NOTE: count = number of languages in lsp_references that were released.
"""
