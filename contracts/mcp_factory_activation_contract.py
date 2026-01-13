"""
MCP Factory Activation Contract - SerenaMCPFactory Session Activation

Constitutional Reference: CL12 Design by Contract
Domain: MCP factory session-aware project activation
Version: 1.0

AUTHORITY: This contract is AUTHORITATIVE for MCP factory activation behavior.
"""

from abc import ABC, abstractmethod


class MCPFactoryActivationContract(ABC):
    """
    Contract for SerenaMCPFactory.activate_project_for_mcp_session().

    This contract specifies the precise behavior for session-aware project activation.

    REQUIREMENTS:
    - REQ-4b: mcp.py uses activate_session_project() for MCP clients

    INVARIANTS:
    - INV-1: Only one workspace bound per session at a time
    - INV-2: Binding to same workspace is idempotent (no-op)
    - INV-3: Binding to different workspace unbinds previous first
    - INV-4: agent and session_id must exist before activation
    - INV-5: Other sessions unaffected by this activation
    """

    @abstractmethod
    def activate_project_for_mcp_session(
        self,
        project_name: str,
    ) -> None:
        """
        Activate a project for the current MCP session.

        PRE: self.agent is not None
        PRE: self.agent._current_session_id is not None (session exists)
        PRE: project_name is a string that exists in serena_config.project_names
             OR project_name is a string path to existing directory

        POST: SessionRegistry.bind_session(session_id, workspace_root) called
        POST: SessionRegistry.get_session(session_id) returns SessionContext
        POST: SessionContext.workspace_root == project.project_root.resolve()

        DECLARED BEHAVIOR (Strict Constructionism):
        1. Get session_id from agent._current_session_id
        2. Get project from config via get_project(project_name)
        3. Resolve workspace_root = project.project_root
        4. Get registry (from agent or factory)
        5. Check existing binding:
           a. If bound to SAME workspace: NO-OP, return immediately
           b. If bound to DIFFERENT workspace: unbind_session(session_id) first
           c. If not bound: proceed to bind
        6. Call registry.bind_session(session_id, workspace_root, "explicit")

        INV: Only one workspace per session (INV-1) - enforced by steps 5a/5b
        INV: Idempotent for same workspace (INV-2) - enforced by step 5a
        INV: Unbind before rebind (INV-3) - enforced by step 5b
        INV: Agent and session exist (INV-4) - enforced by PRE
        INV: Other sessions unaffected (INV-5) - operates only on current session_id

        ERRORS:
        - ValueError: if agent is None
        - ValueError: if session_id is None
        - ProjectNotFoundError: if project_name not in config and not valid path
        """
        ...
