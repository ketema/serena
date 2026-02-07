"""
The Serena Model Context Protocol (MCP) Server
"""

import sys
import threading
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, cast

import docstring_parser
from mcp.server.fastmcp import server
from mcp.server.fastmcp.server import FastMCP, Settings
from mcp.server.fastmcp.tools.base import Tool as MCPTool
from mcp.types import ToolAnnotations
from pydantic_settings import SettingsConfigDict
from sensai.util import logging

from serena.agent import (
    SerenaAgent,
    SerenaConfig,
)
from serena.config.context_mode import SerenaAgentContext, SerenaAgentMode
from serena.config.serena_config import LanguageBackend
from serena.constants import DEFAULT_CONTEXT, DEFAULT_MODES, SERENA_LOG_FORMAT
from serena.global_lsp_pool import GlobalLanguageServerPool
from serena.mcp_session_bridge import MCPSessionBridge
from serena.mcp_transport_context import get_transport_session_id
from serena.session_registry import SessionRegistry
from serena.tools import Tool
from serena.util.exception import show_fatal_exception_safe
from serena.util.logging import MemoryLogHandler

log = logging.getLogger(__name__)


def configure_logging(*args, **kwargs) -> None:  # type: ignore
    # We only do something here if logging has not yet been configured.
    # Normally, logging is configured in the MCP server startup script.
    if not logging.is_enabled():
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, format=SERENA_LOG_FORMAT)


# patch the logging configuration function in fastmcp, because it's hard-coded and broken
server.configure_logging = configure_logging  # type: ignore


@dataclass
class SerenaMCPRequestContext:
    agent: SerenaAgent


class SerenaMCPFactory:
    """
    Factory for the creation of the Serena MCP server with an associated SerenaAgent.
    """

    def __init__(self, context: str = DEFAULT_CONTEXT, project: str | None = None, memory_log_handler: MemoryLogHandler | None = None):
        """
        :param context: The context name or path to context file
        :param project: Either an absolute path to the project directory or a name of an already registered project.
            If the project passed here hasn't been registered yet, it will be registered automatically and can be activated by its name
            afterward.
        :param memory_log_handler: the in-memory log handler to use for the agent's logging
        """
        self.context = SerenaAgentContext.load(context)
        self.project = project
        self.agent: SerenaAgent | None = None
        self.memory_log_handler = memory_log_handler

        # Singleton instances for global services
        self._session_registry: SessionRegistry | None = None
        self._session_bridge: MCPSessionBridge | None = None
        self._lsp_pool: GlobalLanguageServerPool | None = None
        self._lock = threading.RLock()

    @staticmethod
    def _sanitize_for_openai_tools(schema: dict) -> dict:
        """
        This method was written by GPT-5, I have not reviewed it in detail.
        Only called when `openai_tool_compatible` is True.

        Make a Pydantic/JSON Schema object compatible with OpenAI tool schema.
        - 'integer' -> 'number' (+ multipleOf: 1)
        - remove 'null' from union type arrays
        - coerce integer-only enums to number
        - best-effort simplify oneOf/anyOf when they only differ by integer/number
        """
        s = deepcopy(schema)

        def walk(node):  # type: ignore
            if not isinstance(node, dict):
                # lists get handled by parent calls
                return node

            # ---- handle type ----
            t = node.get("type")
            if isinstance(t, str):
                if t == "integer":
                    node["type"] = "number"
                    # preserve existing multipleOf but ensure it's integer-like
                    if "multipleOf" not in node:
                        node["multipleOf"] = 1
            elif isinstance(t, list):
                # remove 'null' (OpenAI tools don't support nullables)
                t2 = [x if x != "integer" else "number" for x in t if x != "null"]
                if not t2:
                    # fall back to object if it somehow becomes empty
                    t2 = ["object"]
                node["type"] = t2[0] if len(t2) == 1 else t2
                if "integer" in t or "number" in t2:
                    # if integers were present, keep integer-like restriction
                    node.setdefault("multipleOf", 1)

            # ---- enums of integers -> number ----
            if "enum" in node and isinstance(node["enum"], list):
                vals = node["enum"]
                if vals and all(isinstance(v, int) for v in vals):
                    node.setdefault("type", "number")
                    # keep them as ints; JSON 'number' covers ints
                    node.setdefault("multipleOf", 1)

            # ---- simplify anyOf/oneOf if they only differ by integer/number ----
            for key in ("oneOf", "anyOf"):
                if key in node and isinstance(node[key], list):
                    # Special case: anyOf or oneOf with "type X" and "null"
                    if len(node[key]) == 2:
                        types = [sub.get("type") for sub in node[key]]
                        if "null" in types:
                            non_null_type = next(t for t in types if t != "null")
                            if isinstance(non_null_type, str):
                                node["type"] = non_null_type
                                node.pop(key, None)
                                continue
                    simplified = []
                    changed = False
                    for sub in node[key]:
                        sub = walk(sub)  # recurse
                        simplified.append(sub)
                    # If all subs are the same after integer→number, collapse
                    try:
                        import json

                        canon = [json.dumps(x, sort_keys=True) for x in simplified]
                        if len(set(canon)) == 1:
                            # copy the single schema up
                            only = simplified[0]
                            node.pop(key, None)
                            for k, v in only.items():
                                if k not in node:
                                    node[k] = v
                            changed = True
                    except Exception:
                        pass
                    if not changed:
                        node[key] = simplified

            # ---- recurse into known schema containers ----
            for child_key in ("properties", "patternProperties", "definitions", "$defs"):
                if child_key in node and isinstance(node[child_key], dict):
                    for k, v in list(node[child_key].items()):
                        node[child_key][k] = walk(v)

            # arrays/items
            if "items" in node:
                node["items"] = walk(node["items"])

            # allOf/if/then/else - pass through with integer→number conversions applied inside
            for key in ("allOf",):
                if key in node and isinstance(node[key], list):
                    node[key] = [walk(x) for x in node[key]]

            if "if" in node:
                node["if"] = walk(node["if"])
            if "then" in node:
                node["then"] = walk(node["then"])
            if "else" in node:
                node["else"] = walk(node["else"])

            return node

        return walk(s)

    @staticmethod
    def make_mcp_tool(tool: Tool, openai_tool_compatible: bool = True) -> MCPTool:
        """
        Create an MCP tool from a Serena Tool instance.

        :param tool: The Serena Tool instance to convert.
        :param openai_tool_compatible: whether to process the tool schema to be compatible with OpenAI tools
            (doesn't accept integer, needs number instead, etc.). This allows using Serena MCP within codex.
        """
        func_name = tool.get_name()
        func_doc = tool.get_apply_docstring() or ""
        func_arg_metadata = tool.get_apply_fn_metadata()
        is_async = False
        parameters = func_arg_metadata.arg_model.model_json_schema()
        if openai_tool_compatible:
            parameters = SerenaMCPFactory._sanitize_for_openai_tools(parameters)

        docstring = docstring_parser.parse(func_doc)

        # Mount the tool description as a combination of the docstring description and
        # the return value description, if it exists.
        overridden_description = tool.agent.get_context().tool_description_overrides.get(func_name, None)

        if overridden_description is not None:
            func_doc = overridden_description
        elif docstring.description:
            func_doc = docstring.description
        else:
            func_doc = ""
        func_doc = func_doc.strip().strip(".")
        if func_doc:
            func_doc += "."
        if docstring.returns and (docstring_returns_descr := docstring.returns.description):
            # Only add a space before "Returns" if func_doc is not empty
            prefix = " " if func_doc else ""
            func_doc = f"{func_doc}{prefix}Returns {docstring_returns_descr.strip().strip('.')}."

        # Parse the parameter descriptions from the docstring and add pass its description
        # to the parameter schema.
        docstring_params = {param.arg_name: param for param in docstring.params}
        parameters_properties: dict[str, dict[str, Any]] = parameters["properties"]
        for parameter, properties in parameters_properties.items():
            if (param_doc := docstring_params.get(parameter)) and param_doc.description:
                param_desc = f"{param_doc.description.strip().strip('.') + '.'}"
                properties["description"] = param_desc[0].upper() + param_desc[1:]

        def execute_fn(**kwargs) -> str:  # type: ignore
            # PRE-3: Read transport session ID (set by HTTP layer)
            session_id = get_transport_session_id()
            
            # POST-1/POST-2: Restore session context if session ID present
            if session_id and tool.agent._session_bridge:
                # HTTP mode: wrap with session context restoration
                return tool.agent._session_bridge.run_with_session_context(
                    session_id,
                    lambda: tool.apply_ex(log_call=True, catch_exceptions=True, **kwargs)
                )
            else:
                # STDIO mode or no session: direct call
                return tool.apply_ex(log_call=True, catch_exceptions=True, **kwargs)

        annotations = ToolAnnotations(readOnlyHint=not tool.can_edit())

        return MCPTool(
            fn=execute_fn,
            name=func_name,
            description=func_doc,
            parameters=parameters,
            fn_metadata=func_arg_metadata,
            is_async=is_async,
            context_kwarg=None,
            annotations=annotations,
            title=None,
        )

    def _iter_tools(self) -> Iterator[Tool]:
        assert self.agent is not None
        yield from self.agent.get_exposed_tool_instances()

    # noinspection PyProtectedMember
    def _set_mcp_tools(self, mcp: FastMCP, openai_tool_compatible: bool = False) -> None:
        """Update the tools in the MCP server"""
        if mcp is not None:
            mcp._tool_manager._tools = {}
            for tool in self._iter_tools():
                mcp_tool = self.make_mcp_tool(tool, openai_tool_compatible=openai_tool_compatible)
                mcp._tool_manager._tools[tool.get_name()] = mcp_tool
            log.info(f"Starting MCP server with {len(mcp._tool_manager._tools)} tools: {list(mcp._tool_manager._tools.keys())}")

    def _create_serena_agent(self, serena_config: SerenaConfig, modes: list[SerenaAgentMode]) -> SerenaAgent:
        agent = SerenaAgent(
            project=self.project, serena_config=serena_config, context=self.context, modes=modes, memory_log_handler=self.memory_log_handler
        )
        
        # Store agent reference and config for later use
        self.agent = agent
        self._serena_config = serena_config
        
        # REQ-4b: Session activation handled during request lifecycle
        
        return agent

    def _create_default_serena_config(self) -> SerenaConfig:
        return SerenaConfig.from_config_file()

    def create_mcp_server(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        modes: Sequence[str] = DEFAULT_MODES,
        language_backend: LanguageBackend | None = None,
        enable_web_dashboard: bool | None = None,
        enable_gui_log_window: bool | None = None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
        trace_lsp_communication: bool | None = None,
        tool_timeout: float | None = None,
    ) -> FastMCP:
        """
        Create an MCP server with process-isolated SerenaAgent to prevent asyncio contamination.

        :param host: The host to bind to
        :param port: The port to bind to
        :param modes: List of mode names or paths to mode files
        :param language_backend: the language backend to use, overriding the configuration setting.
        :param enable_web_dashboard: Whether to enable the web dashboard. If not specified, will take the value from the serena configuration.
        :param enable_gui_log_window: Whether to enable the GUI log window. It currently does not work on macOS, and setting this to True will be ignored then.
            If not specified, will take the value from the serena configuration.
        :param log_level: Log level. If not specified, will take the value from the serena configuration.
        :param trace_lsp_communication: Whether to trace the communication between Serena and the language servers.
            This is useful for debugging language server issues.
        :param tool_timeout: Timeout in seconds for tool execution. If not specified, will take the value from the serena configuration.
        """
        try:
            config = self._create_default_serena_config()

            # update configuration with the provided parameters
            if enable_web_dashboard is not None:
                config.web_dashboard = enable_web_dashboard
            if enable_gui_log_window is not None:
                config.gui_log_window_enabled = enable_gui_log_window
            if log_level is not None:
                log_level = cast(Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], log_level.upper())
                config.log_level = logging.getLevelNamesMapping()[log_level]
            if trace_lsp_communication is not None:
                config.trace_lsp_communication = trace_lsp_communication
            if tool_timeout is not None:
                config.tool_timeout = tool_timeout
            if language_backend is not None:
                config.language_backend = language_backend

            modes_instances = [SerenaAgentMode.load(mode) for mode in modes]
            self.agent = self._create_serena_agent(config, modes_instances)

        except Exception as e:
            show_fatal_exception_safe(e)
            raise

        # Override model_config to disable the use of `.env` files for reading settings, because user projects are likely to contain
        # `.env` files (e.g. containing LOG_LEVEL) that are not supposed to override the MCP settings;
        # retain only FASTMCP_ prefix for already set environment variables.
        Settings.model_config = SettingsConfigDict(env_prefix="FASTMCP_")
        instructions = self._get_initial_instructions()
        mcp = FastMCP(lifespan=self.server_lifespan, host=host, port=port, instructions=instructions)
        return mcp

    @asynccontextmanager
    async def server_lifespan(self, mcp_server: FastMCP) -> AsyncIterator[None]:
        """Manage server startup and shutdown lifecycle.
        
        REQ-3: Initialize global services at startup to avoid first-request latency.
        Services are initialized eagerly before yielding to ensure:
        - No cold-start penalty on first tool call
        - Thread-safe initialization completes before concurrent requests
        - Predictable startup behavior for deployment health checks
        """
        # REQ-3: Initialize global services BEFORE yielding (eager initialization)
        # This ensures no first-request latency penalty
        log.info("Initializing global services...")
        self.get_session_registry()
        self.get_session_bridge()
        self.get_lsp_pool()
        log.info("Global services initialized")

        # REQ-SESSION-002: Wire session bridge to agent for tool dispatch context restoration
        # Root cause fix: Agent created before session_bridge exists, so _session_bridge was None
        # This ensures execute_fn can restore session context per-request
        if self.agent is not None:
            self.agent._session_bridge = self.get_session_bridge()
            self.agent._session_registry = self.get_session_registry()
            self.agent._lsp_pool = self.get_lsp_pool()
            log.info("Session bridge wired to agent")

        # REQ-2026-002: Wire transport session callbacks to session bridge
        # Contract: SessionCallbackWiringContract.wire_session_callbacks
        # PRE-W1: session_bridge initialized (satisfied above)
        # PRE-W2: transport_manager accessible (via mcp_server._session_manager)
        # POST-W1: on_session_created → bridge.on_transport_session_created(session_id, workspace_root=None)
        # POST-W2: on_session_closed → bridge.on_transport_session_closed(session_id)
        # INV-W1: Wiring MUST occur before first HTTP request (satisfied: before yield)
        if hasattr(mcp_server, '_session_manager'):
            bridge = self.get_session_bridge()
            transport_manager = mcp_server._session_manager
            transport_manager.set_session_callbacks(
                on_session_created=lambda sid: bridge.on_transport_session_created(sid, workspace_root=None),
                on_session_closed=lambda sid: bridge.on_transport_session_closed(sid),
            )
            log.info("Transport session callbacks wired to session bridge")
        else:
            log.warning("FastMCP does not expose _session_manager; transport-session bridge not wired")

        openai_tool_compatible = self.context.name in ["chatgpt", "codex", "oaicompat-agent"]
        self._set_mcp_tools(mcp_server, openai_tool_compatible=openai_tool_compatible)
        
        # REQ-4b: Activate session project after agent creation
        if self.project is not None and self.agent is not None:
            self.activate_project_for_mcp_session(self.project)
        
        log.info("MCP server lifetime setup complete")
        yield

    def activate_project_for_mcp_session(self, project_name: str) -> None:
        """
        Activate a project for the current MCP session.

        REQ-4b: Use activate_session_project() instead of activate_project() for MCP clients.
        This method binds the session to the project workspace without triggering legacy activation.

        Contract Reference: contracts/issue6_multi_project_contract.py::MCPFactoryActivationContract

        PRE: self.agent is not None
        PRE: current session context exists via MCPSessionBridge
        PRE: project_name is a string that exists in serena_config.project_names
             OR project_name is a string path to existing directory

        POST: SessionRegistry.bind_session(session_id, workspace_root) called
        POST: SessionRegistry.get_session(session_id) returns SessionContext
        POST: SessionContext.workspace_root == project.project_root.resolve()

        INV: Only one workspace bound per session at a time
        INV: Binding to same workspace is idempotent (no-op, returns immediately)
        INV: Binding to different workspace unbinds previous workspace first
        INV: Other sessions unaffected by this activation

        ERRORS:
        - ValueError: if agent is None ("Cannot activate session project: agent not initialized")
        - ValueError: if session_id is None ("Cannot activate session project: no session ID on agent")
        - ProjectNotFoundError: if project_name not in config and not valid path

        :param project_name: The name or path of the project to activate for this session
        """
        # PRE: Validate agent exists
        if self.agent is None:
            raise ValueError("Cannot activate session project: agent not initialized")

        # PRE: Validate session_id exists
        session_id = self.get_session_bridge().get_current_session_id()
        if session_id is None:
            raise ValueError("Cannot activate session project: no session ID on agent")

        # PRE: Validate project exists in config
        config = self._serena_config if hasattr(self, '_serena_config') else self.agent.serena_config
        from serena.agent import ProjectNotFoundError
        project = config.get_project(project_name)
        if project is None:
            raise ProjectNotFoundError(
                f"Project '{project_name}' not found: Not a valid project name."
            )

        # Get workspace root
        from pathlib import Path
        workspace_root = Path(project.project_root)

        # Get registry
        self.agent.activate_session_project(session_id, workspace_root, source="explicit")

    def _get_initial_instructions(self) -> str:
        assert self.agent is not None
        return self.agent.create_system_prompt()

    def get_session_registry(self) -> SessionRegistry:
        """
        Get or create the SessionRegistry singleton.
        Thread-safe lazy initialization ensures only one instance is created.

        REQ-DCL-FIX: Uses simple lock without DCL pattern.
        DCL is rejected as non-portable in Python (no volatile, memory visibility issues).

        :return: The SessionRegistry singleton instance
        """
        # REQ-DCL-FIX: Simple lock - no outer if check (DCL unsafe in Python)
        with self._lock:
            if self._session_registry is None:
                self._session_registry = SessionRegistry()
            return self._session_registry

    def get_session_bridge(self) -> MCPSessionBridge:
        """
        Get or create the MCPSessionBridge singleton.
        Thread-safe lazy initialization ensures only one instance is created.
        Depends on SessionRegistry being initialized first.

        REQ-DCL-FIX: Uses simple lock without DCL pattern.
        SEQ-POOL-05-FACTORY: Passes lsp_pool reference to bridge constructor
                             to enable SEQ-POOL-05 cleanup chain.

        :return: The MCPSessionBridge singleton instance
        """
        # REQ-DCL-FIX: Simple lock - no outer if check (DCL unsafe in Python)
        with self._lock:
            if self._session_bridge is None:
                session_registry = self.get_session_registry()
                # SEQ-POOL-05-FACTORY: Wire lsp_pool into bridge for cleanup chain
                # Factory uses RLock (reentrant), so nested get_lsp_pool() call is safe
                lsp_pool = self.get_lsp_pool()
                assert lsp_pool is not None, "Factory.get_lsp_pool() returned None"
                self._session_bridge = MCPSessionBridge(session_registry, lsp_pool=lsp_pool)
            return self._session_bridge

    def get_lsp_pool(self) -> GlobalLanguageServerPool:
        """
        Get or create the GlobalLanguageServerPool singleton.
        Thread-safe lazy initialization ensures only one instance is created.

        REQ-DCL-FIX: Uses simple lock without DCL pattern.

        :return: The GlobalLanguageServerPool singleton instance
        """
        # REQ-DCL-FIX: Simple lock - no outer if check (DCL unsafe in Python)
        with self._lock:
            if self._lsp_pool is None:
                self._lsp_pool = GlobalLanguageServerPool()
            return self._lsp_pool

    def shutdown(self) -> None:
        """
        Clear all singleton instances to allow clean shutdown.
        This is useful for testing or when recreating the factory.
        """
        with self._lock:
            self._session_registry = None
            self._session_bridge = None
            self._lsp_pool = None
