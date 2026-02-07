"""
The Serena Model Context Protocol (MCP) Server
"""

import multiprocessing
import os
import platform
import sys
import uuid
import webbrowser
from collections.abc import Callable
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, TypeVar

from sensai.util import logging

from interprompt.jinja_template import JinjaTemplate
from serena import serena_version
from serena.analytics import RegisteredTokenCountEstimator, ToolUsageStats
from serena.config.context_mode import SerenaAgentContext, SerenaAgentMode
from serena.config.serena_config import LanguageBackend, SerenaConfig, ToolInclusionDefinition
from serena.dashboard import SerenaDashboardAPI
from serena.global_lsp_pool import GlobalLanguageServerPool
from serena.mcp_transport_context import get_transport_session_id
from serena.project import Project
from serena.prompt_factory import SerenaPromptFactory
from serena.session_context import get_current_session, set_current_session
from serena.session_registry import SessionContext, SessionRegistry
from serena.task_executor import TaskExecutor
from serena.tools import ActivateProjectTool, GetCurrentConfigTool, ReplaceContentTool, Tool, ToolMarker, ToolRegistry
from serena.util.gui import system_has_usable_display
from serena.util.inspection import iter_subclasses
from serena.util.logging import MemoryLogHandler
from solidlsp.ls_config import Language

# Import PoolIntegrityError for CL12 contract enforcement
try:
    from contracts.lsp_lifecycle_authority_contract import PoolIntegrityError
except ImportError:
    # Graceful degradation if contracts module unavailable
    class PoolIntegrityError(Exception):  # type: ignore
        """Pool replacement violates integrity invariants."""
        pass

if TYPE_CHECKING:
    from serena.gui_log_viewer import GuiLogViewer
    from serena.mcp_session_bridge import MCPSessionBridge

log = logging.getLogger(__name__)
TTool = TypeVar("TTool", bound="Tool")
T = TypeVar("T")
SUCCESS_RESULT = "OK"


class ProjectNotFoundError(Exception):
    pass


class AvailableTools:
    """
    Represents the set of available/exposed tools of a SerenaAgent.
    """

    def __init__(self, tools: list[Tool]):
        """
        :param tools: the list of available tools
        """
        self.tools = tools
        self.tool_names = [tool.get_name_from_cls() for tool in tools]
        self.tool_marker_names = set()
        for marker_class in iter_subclasses(ToolMarker):
            for tool in tools:
                if isinstance(tool, marker_class):
                    self.tool_marker_names.add(marker_class.__name__)

    def __len__(self) -> int:
        return len(self.tools)


class ToolSet:
    """
    Represents a set of tools by their names.
    """

    LEGACY_TOOL_NAME_MAPPING = {"replace_regex": ReplaceContentTool.get_name_from_cls()}
    """
    maps legacy tool names to their new names for backward compatibility
    """

    def __init__(self, tool_names: set[str]) -> None:
        self._tool_names = tool_names

    @classmethod
    def default(cls) -> "ToolSet":
        """
        :return: the default tool set, which contains all tools that are enabled by default
        """
        from serena.tools import ToolRegistry

        return cls(set(ToolRegistry().get_tool_names_default_enabled()))

    def apply(self, *tool_inclusion_definitions: "ToolInclusionDefinition") -> "ToolSet":
        """
        Applies one or more tool inclusion definitions to this tool set,
        resulting in a new tool set.

        :param tool_inclusion_definitions: the definitions to apply
        :return: a new tool set with the definitions applied
        """
        from serena.tools import ToolRegistry

        def get_updated_tool_name(tool_name: str) -> str:
            """Retrieves the updated tool name if the provided tool name is deprecated, logging a warning."""
            if tool_name in self.LEGACY_TOOL_NAME_MAPPING:
                new_tool_name = self.LEGACY_TOOL_NAME_MAPPING[tool_name]
                log.warning("Tool name '%s' is deprecated, please use '%s' instead", tool_name, new_tool_name)
                return new_tool_name
            return tool_name

        registry = ToolRegistry()
        tool_names = set(self._tool_names)
        for definition in tool_inclusion_definitions:
            if definition.is_fixed_tool_set():
                tool_names = set()
                for fixed_tool in definition.fixed_tools:
                    fixed_tool = get_updated_tool_name(fixed_tool)
                    if not registry.is_valid_tool_name(fixed_tool):
                        raise ValueError(f"Invalid tool name '{fixed_tool}' provided for fixed tool set")
                    tool_names.add(fixed_tool)
                log.info(f"{definition} defined a fixed tool set with {len(tool_names)} tools: {', '.join(tool_names)}")
            else:
                included_tools = []
                excluded_tools = []
                for included_tool in definition.included_optional_tools:
                    included_tool = get_updated_tool_name(included_tool)
                    if not registry.is_valid_tool_name(included_tool):
                        raise ValueError(f"Invalid tool name '{included_tool}' provided for inclusion")
                    if included_tool not in tool_names:
                        tool_names.add(included_tool)
                        included_tools.append(included_tool)
                for excluded_tool in definition.excluded_tools:
                    excluded_tool = get_updated_tool_name(excluded_tool)
                    if not registry.is_valid_tool_name(excluded_tool):
                        raise ValueError(f"Invalid tool name '{excluded_tool}' provided for exclusion")
                    if excluded_tool in tool_names:
                        tool_names.remove(excluded_tool)
                        excluded_tools.append(excluded_tool)
                if included_tools:
                    log.info(f"{definition} included {len(included_tools)} tools: {', '.join(included_tools)}")
                if excluded_tools:
                    log.info(f"{definition} excluded {len(excluded_tools)} tools: {', '.join(excluded_tools)}")
        return ToolSet(tool_names)

    def without_editing_tools(self) -> "ToolSet":
        """
        :return: a new tool set that excludes all tools that can edit
        """
        from serena.tools import ToolRegistry

        registry = ToolRegistry()
        tool_names = set(self._tool_names)
        for tool_name in self._tool_names:
            if registry.get_tool_class_by_name(tool_name).can_edit():
                tool_names.remove(tool_name)
        return ToolSet(tool_names)

    def get_tool_names(self) -> set[str]:
        """
        Returns the names of the tools that are currently included in the tool set.
        """
        return self._tool_names

    def includes_name(self, tool_name: str) -> bool:
        return tool_name in self._tool_names


class SerenaAgent:
    def __init__(
        self,
        project: str | None = None,
        project_activation_callback: Callable[[], None] | None = None,
        serena_config: SerenaConfig | None = None,
        context: SerenaAgentContext | None = None,
        modes: list[SerenaAgentMode] | None = None,
        memory_log_handler: MemoryLogHandler | None = None,
        session_registry: "SessionRegistry | None" = None,
        session_bridge: "MCPSessionBridge | None" = None,
        lsp_pool: "GlobalLanguageServerPool | None" = None,
    ):
        """
        :param project: the project to load immediately or None to not load any project; may be a path to the project or a name of
            an already registered project;
        :param project_activation_callback: a callback function to be called when a project is activated.
        :param serena_config: the Serena configuration or None to read the configuration from the default location.
        :param context: the context in which the agent is operating, None for default context.
            The context may adjust prompts, tool availability, and tool descriptions.
        :param modes: list of modes in which the agent is operating (they will be combined), None for default modes.
            The modes may adjust prompts, tool availability, and tool descriptions.
        :param memory_log_handler: a MemoryLogHandler instance from which to read log messages; if None, a new one will be created
            if necessary.
        :param session_registry: Optional SessionRegistry for multi-project session management. If None, a new one is created.
        :param session_bridge: Optional MCPSessionBridge for MCP protocol session bridging.
        :param lsp_pool: Optional GlobalLanguageServerPool for shared language server management.
        """
        # obtain serena configuration using the decoupled factory function
        self.serena_config = serena_config or SerenaConfig.from_config_file()

        # Session management for multi-project isolation
        self._session_registry = session_registry if session_registry is not None else SessionRegistry()
        self._session_bridge = session_bridge
        self._lsp_pool = lsp_pool

        # adjust log level
        serena_log_level = self.serena_config.log_level
        if Logger.root.level != serena_log_level:
            log.info(f"Changing the root logger level to {serena_log_level}")
            Logger.root.setLevel(serena_log_level)

        def get_memory_log_handler() -> MemoryLogHandler:
            nonlocal memory_log_handler
            if memory_log_handler is None:
                memory_log_handler = MemoryLogHandler(level=serena_log_level)
                Logger.root.addHandler(memory_log_handler)
            return memory_log_handler

        # open GUI log window if enabled
        self._gui_log_viewer: Optional["GuiLogViewer"] = None
        if self.serena_config.gui_log_window_enabled:
            log.info("Opening GUI window")
            if platform.system() == "Darwin":
                log.warning("GUI log window is not supported on macOS")
            else:
                # even importing on macOS may fail if tkinter dependencies are unavailable (depends on Python interpreter installation
                # which uv used as a base, unfortunately)
                from serena.gui_log_viewer import GuiLogViewer

                self._gui_log_viewer = GuiLogViewer("dashboard", title="Serena Logs", memory_log_handler=get_memory_log_handler())
                self._gui_log_viewer.start()
        else:
            log.debug("GUI window is disabled")

        # set the agent context
        if context is None:
            context = SerenaAgentContext.load_default()
        self._context = context

        # instantiate all tool classes
        self._all_tools: dict[type[Tool], Tool] = {tool_class: tool_class(self) for tool_class in ToolRegistry().get_all_tool_classes()}
        tool_names = [tool.get_name_from_cls() for tool in self._all_tools.values()]

        # If GUI log window is enabled, set the tool names for highlighting
        if self._gui_log_viewer is not None:
            self._gui_log_viewer.set_tool_names(tool_names)

        token_count_estimator = RegisteredTokenCountEstimator[self.serena_config.token_count_estimator]
        log.info(f"Will record tool usage statistics with token count estimator: {token_count_estimator.name}.")
        self._tool_usage_stats = ToolUsageStats(token_count_estimator)

        # log fundamental information
        log.info(
            f"Starting Serena server (version={serena_version()}, process id={os.getpid()}, parent process id={os.getppid()}; "
            f"language backend={self.serena_config.language_backend.name})"
        )
        log.info("Configuration file: %s", self.serena_config.config_file_path)
        log.info("Available projects: {}".format(", ".join(self.serena_config.project_names)))
        log.info(f"Loaded tools ({len(self._all_tools)}): {', '.join([tool.get_name_from_cls() for tool in self._all_tools.values()])}")

        self._check_shell_settings()

        # determine the base toolset defining the set of exposed tools (which e.g. the MCP shall see),
        # limited by the Serena config, the context (which is fixed for the session) and JetBrains mode
        tool_inclusion_definitions: list[ToolInclusionDefinition] = [self.serena_config, self._context]
        if self._context.single_project:
            tool_inclusion_definitions.extend(self._single_project_context_tool_inclusion_definitions(project))
        if self.serena_config.language_backend == LanguageBackend.JETBRAINS:
            tool_inclusion_definitions.append(SerenaAgentMode.from_name_internal("jetbrains"))

        self._base_tool_set = ToolSet.default().apply(*tool_inclusion_definitions)
        self._exposed_tools = AvailableTools([t for t in self._all_tools.values() if self._base_tool_set.includes_name(t.get_name())])
        log.info(f"Number of exposed tools: {len(self._exposed_tools)}")

        # create executor for starting the language server and running tools in another thread
        # This executor is used to achieve linear task execution
        self._task_executor = TaskExecutor("SerenaAgentTaskExecutor")

        # Initialize the prompt factory
        self.prompt_factory = SerenaPromptFactory()
        self._project_activation_callback = project_activation_callback

        # set the active modes
        if modes is None:
            modes = SerenaAgentMode.load_default_modes()
        self._modes = modes

        self._active_tools: dict[type[Tool], Tool] = {}
        self._update_active_tools()

        # activate a project configuration (if provided or if there is only a single project available)
        if project is not None:
            try:
                self.activate_project_from_path_or_name(project)
            except Exception as e:
                log.error(f"Error activating project '{project}' at startup: {e}", exc_info=e)

        # start the dashboard (web frontend), registering its log handler
        # should be the last thing to happen in the initialization since the dashboard
        # may access various parts of the agent
        if self.serena_config.web_dashboard:
            self._dashboard_thread, port = SerenaDashboardAPI(
                get_memory_log_handler(), tool_names, agent=self, tool_usage_stats=self._tool_usage_stats
            ).run_in_thread(host=self.serena_config.web_dashboard_listen_address)
            dashboard_host = self.serena_config.web_dashboard_listen_address
            if dashboard_host == "0.0.0.0":
                dashboard_host = "localhost"
            dashboard_url = f"http://{dashboard_host}:{port}/dashboard/index.html"
            log.info("Serena web dashboard started at %s", dashboard_url)
            if self.serena_config.web_dashboard_open_on_launch:
                if not system_has_usable_display():
                    log.warning("Not opening the Serena web dashboard automatically because no usable display was detected.")
                else:
                    # open the dashboard URL in the default web browser (using a separate process to control
                    # output redirection)
                    process = multiprocessing.Process(target=self._open_dashboard, args=(dashboard_url,))
                    process.start()
                    process.join(timeout=1)
            # inform the GUI window (if any)
            if self._gui_log_viewer is not None:
                self._gui_log_viewer.set_dashboard_url(dashboard_url)

    def get_current_tasks(self) -> list[TaskExecutor.TaskInfo]:
        """
        Gets the list of tasks currently running or queued for execution.
        The function returns a list of thread-safe TaskInfo objects (specifically created for the caller).

        :return: the list of tasks in the execution order (running task first)
        """
        return self._task_executor.get_current_tasks()

    def get_last_executed_task(self) -> TaskExecutor.TaskInfo | None:
        """
        Gets the last executed task.

        :return: the last executed task info or None if no task has been executed yet
        """
        return self._task_executor.get_last_executed_task()

    def get_lsp_pool(self) -> GlobalLanguageServerPool:
        if self._lsp_pool is None:
            self._lsp_pool = GlobalLanguageServerPool()
        return self._lsp_pool

    def get_context(self) -> SerenaAgentContext:
        return self._context

    def get_tool_description_override(self, tool_name: str) -> str | None:
        return self._context.tool_description_overrides.get(tool_name, None)

    def _check_shell_settings(self) -> None:
        # On Windows, Claude Code sets COMSPEC to Git-Bash (often even with a path containing spaces),
        # which causes all sorts of trouble, preventing language servers from being launched correctly.
        # So we make sure that COMSPEC is unset if it has been set to bash specifically.
        if platform.system() == "Windows":
            comspec = os.environ.get("COMSPEC", "")
            if "bash" in comspec:
                os.environ["COMSPEC"] = ""  # force use of default shell
                log.info("Adjusting COMSPEC environment variable to use the default shell instead of '%s'", comspec)

    def _single_project_context_tool_inclusion_definitions(self, project_root_or_name: str | None) -> list[ToolInclusionDefinition]:
        """
        In the IDE assistant context, the agent is assumed to work on a single project, and we thus
        want to apply that project's tool exclusions/inclusions from the get-go, limiting the set
        of tools that will be exposed to the client.
        Furthermore, we disable tools that are only relevant for project activation.
        So if the project exists, we apply all the aforementioned exclusions.

        :param project_root_or_name: the project root path or project name
        :return:
        """
        tool_inclusion_definitions = []
        if project_root_or_name is not None:
            # Note: Auto-generation is disabled, because the result must be returned instantaneously
            #   (project generation could take too much time), so as not to delay MCP server startup
            #   and provide responses to the client immediately.
            project = self.load_project_from_path_or_name(project_root_or_name, autogenerate=False)
            if project is not None:
                log.info(
                    "Applying tool inclusion/exclusion definitions for single-project context based on project '%s'", project.project_name
                )
                tool_inclusion_definitions.append(
                    ToolInclusionDefinition(
                        excluded_tools=[ActivateProjectTool.get_name_from_cls(), GetCurrentConfigTool.get_name_from_cls()]
                    )
                )
                tool_inclusion_definitions.append(project.project_config)
        return tool_inclusion_definitions

    def record_tool_usage(self, input_kwargs: dict, tool_result: str | dict, tool: Tool) -> None:
        """
        Record the usage of a tool with the given input and output strings if tool usage statistics recording is enabled.
        """
        tool_name = tool.get_name()
        input_str = str(input_kwargs)
        output_str = str(tool_result)
        log.debug(f"Recording tool usage for tool '{tool_name}'")
        self._tool_usage_stats.record_tool_usage(tool_name, input_str, output_str)

    @staticmethod
    def _open_dashboard(url: str) -> None:
        # Redirect stdout and stderr file descriptors to /dev/null,
        # making sure that nothing can be written to stdout/stderr, even by subprocesses
        null_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null_fd, sys.stdout.fileno())
        os.dup2(null_fd, sys.stderr.fileno())
        os.close(null_fd)

        # open the dashboard URL in the default web browser
        webbrowser.open(url)

    def get_project_root(self) -> str:
        """
        :return: the root directory of the active project (if any); raises a ValueError if there is no active project
        """
        project = self.get_active_project()
        if project is None:
            raise ValueError("Cannot get project root if no project is active.")
        return project.project_root

    def get_exposed_tool_instances(self) -> list["Tool"]:
        """
        :return: the tool instances which are exposed (e.g. to the MCP client).
            Note that the set of exposed tools is fixed for the session, as
            clients don't react to changes in the set of tools, so this is the superset
            of tools that can be offered during the session.
            If a client should attempt to use a tool that is dynamically disabled
            (e.g. because a project is activated that disables it), it will receive an error.
        """
        return list(self._exposed_tools.tools)

    def get_active_project(self) -> Project | None:
        """
        :return: the active project or None if no project is active
        """
        session = get_current_session()
        if session is None or session.workspace_root is None:
            return None
        try:
            return Project.load(session.workspace_root)
        except Exception:
            return None

    def get_active_project_or_raise(self) -> Project:
        """
        :return: the active project or raises an exception if no project is active
        """
        session = get_current_session()
        if session is None:
            raise ProjectNotFoundError("No active session. Please activate a project first.")
        if session.workspace_root is None:
            raise ProjectNotFoundError(
                f"Session {session.session_id} has no workspace bound. "
                "Please call activate_project first."
            )
        try:
            return Project.load(session.workspace_root)
        except Exception as exc:
            raise ProjectNotFoundError("No active project for current session.") from exc

    def get_current_session_context(self) -> "SessionContext | None":
        """
        :return: the current session context or None if no session is active
        """
        return get_current_session()

    def set_modes(self, modes: list[SerenaAgentMode]) -> None:
        """
        Set the current mode configurations.

        :param modes: List of mode names or paths to use
        """
        self._modes = modes
        self._update_active_tools()

        log.info(f"Set modes to {[mode.name for mode in modes]}")

    def get_active_modes(self) -> list[SerenaAgentMode]:
        """
        :return: the list of active modes
        """
        return list(self._modes)

    def _format_prompt(self, prompt_template: str) -> str:
        template = JinjaTemplate(prompt_template)
        return template.render(available_tools=self._exposed_tools.tool_names, available_markers=self._exposed_tools.tool_marker_names)

    def create_system_prompt(self) -> str:
        available_markers = self._exposed_tools.tool_marker_names
        log.info("Generating system prompt with available_tools=(see exposed tools), available_markers=%s", available_markers)
        system_prompt = self.prompt_factory.create_system_prompt(
            context_system_prompt=self._format_prompt(self._context.prompt),
            mode_system_prompts=[self._format_prompt(mode.prompt) for mode in self._modes],
            available_tools=self._exposed_tools.tool_names,
            available_markers=available_markers,
        )

        # If a project is active at startup, append its activation message
        active_project = self.get_active_project()
        if active_project is not None:
            system_prompt += "\n\n" + active_project.get_activation_message()

        log.info("System prompt:\n%s", system_prompt)
        return system_prompt

    def _update_active_tools(self) -> None:
        """
        Update the active tools based on enabled modes and the active project.
        The base tool set already takes the Serena configuration and the context into account
        (as well as any internal modes that are not handled dynamically, such as JetBrains mode).
        """
        tool_set = self._base_tool_set.apply(*self._modes)
        active_project = self.get_active_project()
        if active_project is not None:
            tool_set = tool_set.apply(active_project.project_config)
            if active_project.project_config.read_only:
                tool_set = tool_set.without_editing_tools()

        self._active_tools = {
            tool_class: tool_instance
            for tool_class, tool_instance in self._all_tools.items()
            if tool_set.includes_name(tool_instance.get_name())
        }

        log.info(f"Active tools ({len(self._active_tools)}): {', '.join(self.get_active_tool_names())}")

    def issue_task(
        self, task: Callable[[], T], name: str | None = None, logged: bool = True, timeout: float | None = None
    ) -> TaskExecutor.Task[T]:
        """
        Issue a task to the executor for asynchronous execution.
        It is ensured that tasks are executed in the order they are issued, one after another.

        :param task: the task to execute
        :param name: the name of the task for logging purposes; if None, use the task function's name
        :param logged: whether to log management of the task; if False, only errors will be logged
        :param timeout: the maximum time to wait for task completion in seconds, or None to wait indefinitely
        :return: the task object, through which the task's future result can be accessed
        """
        return self._task_executor.issue_task(task, name=name, logged=logged, timeout=timeout)

    def execute_task(self, task: Callable[[], T], name: str | None = None, logged: bool = True, timeout: float | None = None) -> T:
        """
        Executes the given task synchronously via the agent's task executor.
        This is useful for tasks that need to be executed immediately and whose results are needed right away.

        :param task: the task to execute
        :param name: the name of the task for logging purposes; if None, use the task function's name
        :param logged: whether to log management of the task; if False, only errors will be logged
        :param timeout: the maximum time to wait for task completion in seconds, or None to wait indefinitely
        :return: the result of the task execution
        """
        return self._task_executor.execute_task(task, name=name, logged=logged, timeout=timeout)

    def is_using_language_server(self) -> bool:
        """
        :return: whether this agent uses language server-based code analysis
        """
        return self.serena_config.language_backend == LanguageBackend.LSP

    def _get_language_for_file(self, project: Project, file_path: str) -> Language | None:
        return project.get_language_for_file(file_path)

    def get_language_server_for_file(self, file_path: str) -> "SolidLanguageServer | None":
        """
        Get language server for file via GlobalLanguageServerPool.
        """
        project = self.get_active_project()
        session = get_current_session()
        if project is None or session is None:
            return None
        language = self._get_language_for_file(project, file_path)
        if language is None:
            return None
        workspace_root = Path(project.project_root)
        lsp = self.get_lsp_pool().acquire(language, workspace_root, session.session_id)
        session.lsp_references[language.value] = lsp
        return lsp

    @property
    def language_server(self) -> "SolidLanguageServer | None":
        project = self.get_active_project()
        session = get_current_session()
        if project is None or session is None:
            return None
        language = project.project_config.language
        workspace_root = Path(project.project_root)
        lsp = self.get_lsp_pool().acquire(language, workspace_root, session.session_id)
        session.lsp_references[language.value] = lsp
        return lsp

    # =========================================================================
    # BRIDGE PROPERTIES (Phase 2 - Remove in Phase 4 demolition)
    # Contract: contracts/serena_agent_observability_contract.py
    # =========================================================================

    @property
    def session_registry(self) -> "SessionRegistry":
        """
        BRIDGE: Expose session registry for dashboard observability.
        
        PRE: None (always callable)
        POST: Returns SessionRegistry instance (never None)
        INV: Does not mutate state
        INV: Thread-safe (SessionRegistry uses internal locking)
        
        Contract Authority: contracts/serena_agent_observability_contract.py
        Remove after: Phase 4 demolition when contract tests exist
        """
        return self._session_registry

    def get_session_overview(self) -> dict[str, Any]:
        """
        Get overview of all bound sessions (delegation to SessionRegistry).

        CONTRACT: POST-OBS-03, INV-OBS-02, ERRORS-OBS-01
        from contracts/serena_agent_observability_contract.py

        PRE: None
        POST: Returns {"sessions": list, "total_count": int}
        INV-OBS-02: Never raises exceptions (availability guarantee)
        ERRORS-OBS-01: Exception suppression, return empty structure

        This method exists per DISCONNECT MATRIX B3: delegation to registry.
        Dashboard and direct callers use this instead of accessing registry directly.
        """
        # ERRORS-OBS-01: Catch all exceptions, return empty structure
        try:
            return self._session_registry.get_session_overview()
        except Exception:
            # INV-OBS-02: Observability MUST NOT raise exceptions
            # Return empty valid structure on any error
            return {
                "sessions": [],
                "total_count": 0,
            }

    @property
    def lsp_pool(self) -> "GlobalLanguageServerPool | None":
        """
        BRIDGE: Expose LSP pool for dashboard observability.
        
        PRE: None (always callable)
        POST: Returns GlobalLanguageServerPool or None if not initialized
        INV: Does not mutate state
        INV: Thread-safe (pool uses internal locking)
        
        Contract Authority: contracts/serena_agent_observability_contract.py
        Remove after: Phase 4 demolition when contract tests exist
        """
        return self._lsp_pool

    def _activate_project(self, project: Project) -> None:
        log.info(f"Activating {project.project_name} at {project.project_root}")

        # POST-1: Get session_id from MCP session bridge or create anonymous
        # Contract: PRE-2 requires session_id is not None
        session_id = self._session_bridge.get_current_session_id() if self._session_bridge else None
        if session_id is None:
            # Fallback to anonymous session when no MCP session
            session_id = str(uuid.uuid4())

        # POST-1, POST-2, POST-3: Bind session to workspace
        # INV-2: Idempotent - bind_session internally handles same workspace case
        self.activate_session_project(
            session_id=session_id,
            workspace_root=Path(project.project_root),
            source="explicit",
        )

    def load_project_from_path_or_name(self, project_root_or_name: str, autogenerate: bool) -> Project | None:
        """
        Get a project instance from a path or a name.

        :param project_root_or_name: the path to the project root or the name of the project
        :param autogenerate: whether to autogenerate the project for the case where first argument is a directory
            which does not yet contain a Serena project configuration file
        :return: the project instance if it was found/could be created, None otherwise
        """
        project_instance: Project | None = self.serena_config.get_project(project_root_or_name)
        if project_instance is not None:
            log.info(f"Found registered project '{project_instance.project_name}' at path {project_instance.project_root}")
        elif autogenerate and os.path.isdir(project_root_or_name):
            project_instance = self.serena_config.add_project_from_path(project_root_or_name)
            log.info(f"Added new project {project_instance.project_name} for path {project_instance.project_root}")
        return project_instance

    def activate_project_from_path_or_name(self, project_root_or_name: str) -> Project:
        """
        Activate a project from a path or a name.
        If the project was already registered, it will just be activated.
        If the argument is a path at which no Serena project previously existed, the project will be created beforehand.
        Raises ProjectNotFoundError if the project could neither be found nor created.

        :return: a tuple of the project instance and a Boolean indicating whether the project was newly
            created
        """
        project_instance: Project | None = self.load_project_from_path_or_name(project_root_or_name, autogenerate=True)
        if project_instance is None:
            raise ProjectNotFoundError(
                f"Project '{project_root_or_name}' not found: Not a valid project name or directory. "
                f"Existing project names: {self.serena_config.project_names}"
            )
        self._activate_project(project_instance)
        return Project.load(Path(project_instance.project_root))

    def get_active_tool_classes(self) -> list[type["Tool"]]:
        """
        :return: the list of active tool classes for the current project
        """
        return list(self._active_tools.keys())

    def get_active_tool_names(self) -> list[str]:
        """
        :return: the list of names of the active tools for the current project
        """
        return sorted([tool.get_name_from_cls() for tool in self.get_active_tool_classes()])

    def tool_is_active(self, tool_class: type["Tool"] | str) -> bool:
        """
        :param tool_class: the class or name of the tool to check
        :return: True if the tool is active, False otherwise
        """
        if isinstance(tool_class, str):
            return tool_class in self.get_active_tool_names()
        else:
            return tool_class in self.get_active_tool_classes()

    def get_current_config_overview(self) -> str:
        """
        :return: a string overview of the current configuration, including the active and available configuration options
        """
        result_str = "Current configuration:\n"
        result_str += f"Serena version: {serena_version()}\n"
        result_str += f"Loglevel: {self.serena_config.log_level}, trace_lsp_communication={self.serena_config.trace_lsp_communication}\n"
        active_project = self.get_active_project()
        if active_project is not None:
            result_str += f"Active project: {active_project.project_name}\n"
        else:
            result_str += "No active project\n"
        result_str += "Available projects:\n" + "\n".join(list(self.serena_config.project_names)) + "\n"
        result_str += f"Active context: {self._context.name}\n"

        # Active modes
        active_mode_names = [mode.name for mode in self.get_active_modes()]
        result_str += "Active modes: {}\n".format(", ".join(active_mode_names)) + "\n"

        # Available but not active modes
        all_available_modes = SerenaAgentMode.list_registered_mode_names()
        inactive_modes = [mode for mode in all_available_modes if mode not in active_mode_names]
        if inactive_modes:
            result_str += "Available but not active modes: {}\n".format(", ".join(inactive_modes)) + "\n"

        # Active tools
        result_str += "Active tools (after all exclusions from the project, context, and modes):\n"
        active_tool_names = self.get_active_tool_names()
        # print the tool names in chunks
        chunk_size = 4
        for i in range(0, len(active_tool_names), chunk_size):
            chunk = active_tool_names[i : i + chunk_size]
            result_str += "  " + ", ".join(chunk) + "\n"

        # Available but not active tools
        all_tool_names = sorted([tool.get_name_from_cls() for tool in self._all_tools.values()])
        inactive_tool_names = [tool for tool in all_tool_names if tool not in active_tool_names]
        if inactive_tool_names:
            result_str += "Available but not active tools:\n"
            for i in range(0, len(inactive_tool_names), chunk_size):
                chunk = inactive_tool_names[i : i + chunk_size]
                result_str += "  " + ", ".join(chunk) + "\n"

        return result_str

    def reset_language_server(self) -> None:
        """
        Reset language server resources by reinitializing the global pool.

        GUARDS (CL12 PoolIntegrityContract):
        - INV-PI-01: Pool NEVER replaced while sessions active
        - POST-PI-01: HTTP mode + active sessions → PoolIntegrityError
        - ERRORS-PI-02: STDIO mode proceeds with deprecation warning
        """
        # Detect HTTP mode
        session_id = get_transport_session_id()
        is_http_mode = session_id is not None

        # Get active session count
        # INV-PI-01: Check SessionRegistry.get_session_overview()['total_count']
        session_overview = self._session_registry.get_session_overview()
        active_session_count = session_overview["total_count"]

        # POST-PI-01, ERRORS-PI-01: HTTP mode + active sessions → raise PoolIntegrityError
        if is_http_mode and active_session_count > 0:
            raise PoolIntegrityError(
                f"Cannot replace LSP pool: {active_session_count} active sessions in HTTP mode. "
                "Pool replacement would destroy active client sessions."
            )

        # ERRORS-PI-02: STDIO mode proceeds with deprecation warning
        if not is_http_mode:
            log.warning(
                "reset_language_server() called in STDIO mode. "
                "This is deprecated. Pool replacement in STDIO mode may break active sessions. "
                "Migrate to HTTP mode with server-managed LSP lifecycle."
            )

        # POST-PI-02: No active sessions → replacement proceeds
        self._lsp_pool = GlobalLanguageServerPool()

    def handle_lsp_termination(
        self,
        language: "Language",
        workspace_root: Path,
        retry_fn: Callable[[], str],
    ) -> str:
        """
        Handle LanguageServerTerminatedException with surgical restart.

        Contract: ToolExceptionHandlerContract (lsp_lifecycle_authority_contract.py lines 230-304)
        
        PRE-TEH-01: LSP for language has terminated
        PRE-TEH-02: language and workspace_root identify the affected LSP
        
        POST-TEH-01: LSP surgically restarted (via surgical_restart_lsp)
        POST-TEH-02: Workspace roots restored on restarted LSP
        POST-TEH-03: retry_fn called on restarted LSP, result returned
        POST-TEH-04: If retry fails, returns error string (no infinite retry)
        POST-TEH-05: Other clients unaffected
        
        INV-TEH-01: Does NOT call reset_language_server() (pool-wide nuke)
        INV-TEH-02: Does NOT replace self._lsp_pool
        INV-TEH-03: Other languages' LSP instances unaffected
        
        ERRORS-TEH-01: Returns error string if restart fails
        ERRORS-TEH-02: Returns error string if retry fails (max 1 retry)
        
        SEQ-TEH-02: Calls surgical_restart_lsp(language)
        
        :param language: Language of the terminated LSP
        :param workspace_root: Workspace root for readiness probing
        :param retry_fn: Callable that retries the original tool operation
        :return: Result from retry_fn on success, or error string on failure
        """
        from serena.global_lsp_pool import LSPRestartError, probe_workspace_readiness
        from solidlsp.ls_exceptions import SolidLSPException
        
        try:
            # POST-TEH-01, SEQ-TEH-02: Surgical restart of terminated LSP
            new_lsp = self._lsp_pool.surgical_restart_lsp(language)
            
            # POST-TEH-02: Wait for workspace readiness (workspace roots restored by surgical_restart_lsp)
            timeout_seconds = 5.0
            is_ready = probe_workspace_readiness(new_lsp, workspace_root, timeout_seconds)
            
            if not is_ready:
                # ERRORS-TEH-01: Restart succeeded but LSP not ready
                return f"Error: LSP restart succeeded but workspace not ready after {timeout_seconds}s"
            
            # POST-TEH-03: Retry the original tool operation on restarted LSP
            try:
                result = retry_fn()
                return result
            except SolidLSPException as e:
                if e.is_language_server_terminated():
                    # ERRORS-TEH-02: Retry also raised termination → return error (max 1 retry)
                    return "Error: Retry after restart also failed with LSP termination"
                else:
                    # Non-termination LSP exception → re-raise for outer handler
                    raise
                    
        except LSPRestartError as e:
            # ERRORS-TEH-01: Restart itself failed
            return f"Error: LSP restart failed (LSPRestartError) - {e}"
        except Exception as e:
            # ERRORS-TEH-01: Unexpected failure during restart
            log.exception("Unexpected error during LSP restart")
            return f"Error: Unexpected failure during LSP restart - {type(e).__name__}: {e}"

    def reset_language_server_manager(self) -> None:
        """
        Backward compatibility alias for reset_language_server().
        """
        self.reset_language_server()

    def add_language(self, language: Language) -> None:
        """
        Adds a new language to the active project, spawning the respective language server and updating the project configuration.
        The addition is scheduled via the agent's task executor and executed synchronously, i.e. the method returns
        when the addition is complete.

        :param language: the language to add
        """
        self.execute_task(lambda: self.get_active_project_or_raise().add_language(language), name=f"AddLanguage:{language.value}")

    def remove_language(self, language: Language) -> None:
        """
        Removes a language from the active project, shutting down the respective language server and updating the project configuration.
        The removal is scheduled via the agent's task executor and executed asynchronously.

        :param language: the language to remove
        """
        self.issue_task(lambda: self.get_active_project_or_raise().remove_language(language), name=f"RemoveLanguage:{language.value}")

    def get_tool(self, tool_class: type[TTool]) -> TTool:
        return self._all_tools[tool_class]  # type: ignore

    def print_tool_overview(self) -> None:
        ToolRegistry().print_tool_overview(self._active_tools.values())

    def __del__(self) -> None:
        self.shutdown()

    def shutdown(self, timeout: float = 2.0) -> None:
        """
        Shuts down the agent, freeing resources and stopping background tasks.
        """
        if not hasattr(self, "_is_initialized"):
            return
        log.info("SerenaAgent is shutting down ...")
        current = get_current_session()
        if current is not None:
            log.info(f"Unbinding session {current.session_id}")
            self.deactivate_session(current.session_id)
        if self._gui_log_viewer:
            log.info("Stopping the GUI log window ...")
            self._gui_log_viewer.stop()
            self._gui_log_viewer = None

    def get_tool_by_name(self, tool_name: str) -> Tool:
        tool_class = ToolRegistry().get_tool_class_by_name(tool_name)
        return self.get_tool(tool_class)

    def activate_session_project(self, session_id: str, workspace_root: Path, source: str = "explicit") -> Project:
        """
        Bind session to workspace and set as current.

        PRE: session_id is non-empty string
        PRE: workspace_root exists and is absolute path
        PRE: source in ("explicit", "auto", "anonymous")

        POST-1: SessionRegistry.bind_session() called
        POST-2: set_current_session() called with new SessionContext
        POST-3: Project loaded and initialized for workspace
        POST-4: Returns loaded Project
        """
        if not session_id:
            raise ValueError("session_id must be non-empty")
        if not workspace_root.is_absolute():
            raise ValueError(f"workspace_root must be absolute: {workspace_root}")
        if not workspace_root.exists():
            raise FileNotFoundError(f"workspace_root does not exist: {workspace_root}")
        if source not in ("explicit", "auto", "anonymous"):
            raise ValueError(f"Invalid source: {source}")

        existing_session = self._session_registry.get_session(session_id)
        if existing_session is not None:
            # INV-B1-03: activate_project is the ONLY mechanism to bind workspace
            # Handle transitions: None→Path (initial binding) or Path→Path (re-binding)
            if existing_session.workspace_root is None:
                # HTTP mode: Session created without workspace, now binding via activate_project
                self._session_registry.unbind_session(session_id)
            elif Path(existing_session.workspace_root).resolve() != workspace_root.resolve():
                # Re-binding to different workspace
                self._session_registry.unbind_session(session_id)
            else:
                # Already bound to same workspace, no-op
                set_current_session(existing_session)
                return Project.load(workspace_root)

        session = self._session_registry.bind_session(session_id, workspace_root, source)
        set_current_session(session)

        try:
            project = Project.load(workspace_root)
        except Exception as exc:
            self._session_registry.unbind_session(session_id)
            set_current_session(None)
            raise ProjectNotFoundError("Failed to load project for session.") from exc

        # INV-B3-01: MUST NOT call _update_active_tools() on shared Agent
        # INV-B2-01: _active_tools dict MUST NOT be mutated by activate_project
        # POST-B3-05: _project_activation_callback NOT called (affects all sessions)
        # POST-B2-02: Shared Agent state unchanged after call
        #
        # Tool availability is now computed dynamically per-session via get_active_tools_for_session()
        # No shared state mutation required.

        return project

    def deactivate_session(self, session_id: str) -> None:
        """
        Unbind session and clear from current context if active.
        """
        current = get_current_session()
        if current is not None and current.session_id == session_id:
            set_current_session(None)

        if current is not None:
            for lang_name in list(current.lsp_references.keys()):
                try:
                    language = Language[lang_name.upper()]
                except KeyError:
                    continue
                if current.workspace_root is not None:
                    self.get_lsp_pool().release(language, current.workspace_root, session_id)
            current.lsp_references.clear()

        self._session_registry.unbind_session(session_id)

    def activate_project(self, project_name: str) -> None:
        """
        Legacy API: Activate project by name or path.
        """
        self.activate_project_from_path_or_name(project_name)
