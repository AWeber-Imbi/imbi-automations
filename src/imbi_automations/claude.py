"""Claude Code integration for AI-powered code transformations.

Provides integration with Claude Code SDK for executing complex multi-file
analysis and transformations using Claude AI, supporting both agent-based
workflows and direct Anthropic API queries.
"""

import asyncio
import json
import logging
import os
import pathlib
import re
import typing

import anthropic
import claude_agent_sdk
import pydantic
from anthropic import types as anthropic_types
from claude_agent_sdk import types

from imbi_automations import mixins, models, prompts, tracker

LOGGER = logging.getLogger(__name__)
BASE_PATH = pathlib.Path(__file__).parent
COMMIT = 'commit'


def _expand_env_vars(value: str) -> str:
    """Expand $VAR and ${VAR} patterns in a string.

    Uses os.path.expandvars for standard shell-style expansion and validates
    that all referenced environment variables are set.

    Args:
        value: String potentially containing environment variable references

    Returns:
        String with all environment variables expanded

    Raises:
        ValueError: If any referenced environment variable is not set

    """
    expanded = os.path.expandvars(value)
    # Check for unexpanded variables (os.path.expandvars leaves them unchanged)
    remaining = re.findall(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?', expanded)
    for var in remaining:
        if var not in os.environ:
            raise ValueError(f'Environment variable {var} not set')
    return expanded


def _expand_mcp_config(config: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """Recursively expand environment variables in MCP server config.

    Handles strings, lists of strings, and dicts with string values.
    Non-string values are passed through unchanged.

    Args:
        config: MCP server configuration dict from model_dump()

    Returns:
        New dict with all string values expanded

    """
    result: dict[str, typing.Any] = {}
    for key, value in config.items():
        if isinstance(value, str):
            result[key] = _expand_env_vars(value)
        elif isinstance(value, list):
            result[key] = [
                _expand_env_vars(v) if isinstance(v, str) else v for v in value
            ]
        elif isinstance(value, dict):
            result[key] = {
                k: _expand_env_vars(v) if isinstance(v, str) else v
                for k, v in value.items()
            }
        else:
            result[key] = value
    return result


class Agents(typing.TypedDict):
    """TypedDict for agent configuration."""

    planning: types.AgentDefinition | None
    task: types.AgentDefinition | None
    validation: types.AgentDefinition | None


def _merge_plugin_configs(
    main_config: models.ClaudePluginConfig,
    workflow_config: models.ClaudePluginConfig,
) -> models.ClaudePluginConfig:
    """Merge workflow plugin config with main config.

    Workflow config values take precedence for enabled_plugins.
    Marketplaces are merged with workflow values taking precedence.
    Local plugins are concatenated.

    Args:
        main_config: Plugin config from main Configuration
        workflow_config: Plugin config from WorkflowConfiguration

    Returns:
        Merged ClaudePluginConfig

    """
    # Merge enabled_plugins (workflow overrides main)
    merged_enabled = {**main_config.enabled_plugins}
    merged_enabled.update(workflow_config.enabled_plugins)

    # Merge marketplaces (workflow overrides main for same key)
    merged_marketplaces = {**main_config.marketplaces}
    merged_marketplaces.update(workflow_config.marketplaces)

    # Concatenate local plugins (deduplicate by path)
    seen_paths: set[str] = set()
    merged_local: list[models.ClaudeLocalPlugin] = []
    for plugin in main_config.local_plugins + workflow_config.local_plugins:
        if plugin.path not in seen_paths:
            seen_paths.add(plugin.path)
            merged_local.append(plugin)

    return models.ClaudePluginConfig(
        enabled_plugins=merged_enabled,
        marketplaces=merged_marketplaces,
        local_plugins=merged_local,
    )


AgentResult = models.ClaudeAgentResponse


class Claude(mixins.WorkflowLoggerMixin):
    """Claude Code client for executing AI-powered code transformations."""

    def __init__(
        self,
        config: models.Configuration,
        context: models.WorkflowContext,
        verbose: bool = False,
    ) -> None:
        super().__init__(verbose)
        if config.anthropic.bedrock:
            self.anthropic = anthropic.AsyncAnthropicBedrock()
        else:
            if isinstance(config.anthropic.api_key, str):
                api_key = config.anthropic.api_key
            elif isinstance(config.anthropic.api_key, pydantic.SecretStr):
                api_key = config.anthropic.api_key.get_secret_value()
            else:
                api_key = None
            self.anthropic = anthropic.AsyncAnthropic(api_key=api_key)
        self.agents: Agents = Agents(planning=None, task=None, validation=None)
        self.configuration = config
        self.context = context
        self.logger: logging.Logger = LOGGER
        self.session_id: str | None = None
        self.prompt_kwargs = {
            'commit_author': (
                f'{config.git.user_name} <{config.git.user_email}>'
            ),
            'commit_author_name': config.git.user_name,
            'commit_author_address': config.git.user_email,
            'configuration': self.configuration,
            'workflow_name': context.workflow.configuration.name,
            'working_directory': self.context.working_directory,
        }
        self.tracker = tracker.Tracker.get_instance()
        self._set_workflow_logger(self.context.workflow)
        self._submitted_response: AgentResult | None = None
        self._merged_local_plugins: list[models.ClaudeLocalPlugin] = []
        self.client = self._create_client()

    def get_agent_prompt(self, agent_type: models.ClaudeAgentType) -> str:
        """Get the prompt content for a specific agent type.

        Args:
            agent_type: The type of agent (planning, task, validation)

        Returns:
            The agent's prompt content

        Raises:
            ValueError: If the agent type has no definition

        """
        agent_def = self.agents.get(agent_type.value)
        if agent_def is None:
            raise ValueError(f'No agent definition for {agent_type.value}')
        return agent_def.prompt

    async def agent_query(
        self, prompt: str, timeout: str = '1h'
    ) -> AgentResult | None:
        """Execute an agent query and return unified response via MCP tool.

        Args:
            prompt: The prompt to send to the agent
            timeout: Maximum execution time in Go duration format (e.g., "30m",
                "1h", "90s")

        Returns:
            ClaudeAgentResponse with fields populated by the agent

        Raises:
            RuntimeError: If agent didn't call submit_agent_response tool
            TimeoutError: If execution exceeds the specified timeout

        """
        # Parse timeout to seconds
        import pytimeparse2

        timeout_seconds = pytimeparse2.parse(timeout)
        if timeout_seconds is None:
            raise ValueError(f'Invalid timeout format: {timeout}')

        # Execute SDK interaction with timeout wrapper
        try:
            result = await asyncio.wait_for(
                self._execute_sdk_query(prompt), timeout=timeout_seconds
            )
            return result
        except TimeoutError:
            # Attempt graceful shutdown
            LOGGER.warning(
                'Claude Code execution timed out after %s (%ds), '
                'attempting graceful shutdown',
                timeout,
                timeout_seconds,
            )
            try:
                await asyncio.wait_for(self.client.disconnect(), timeout=5)
            except TimeoutError:
                LOGGER.warning(
                    'Claude SDK disconnect failed due to timeout '
                    '(process may need forceful termination)'
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    'Claude SDK disconnect failed: %s '
                    '(process may need forceful termination)',
                    exc,
                )

            raise TimeoutError(
                f'Claude Code execution timed out after {timeout} '
                f'({timeout_seconds}s)'
            ) from None

    async def _execute_sdk_query(self, prompt: str) -> AgentResult | None:
        """Execute SDK query and capture tool-based response.

        Args:
            prompt: The prompt to send to the agent

        Returns:
            ClaudeAgentResponse populated by the agent via MCP tool

        Raises:
            RuntimeError: If agent didn't call submit_agent_response tool

        """
        self._submitted_response: AgentResult | None = None

        await self.client.connect()
        await self.client.query(prompt)
        async for message in self.client.receive_response():
            self._parse_message(message)
        await self.client.disconnect()

        if self._submitted_response is None:
            raise RuntimeError(
                'No response received from Claude Code - agent must call '
                'submit_agent_response tool'
            )

        return self._submitted_response

    async def anthropic_query(
        self, prompt: str, model: str | None = None
    ) -> str:
        """Use the Anthropic API to run one-off tasks"""
        message = await self.anthropic.messages.create(
            model=model or self.configuration.anthropic.model,
            max_tokens=8192,
            messages=[
                anthropic_types.MessageParam(role='user', content=prompt)
            ],
        )
        if isinstance(message.content[0], anthropic_types.TextBlock):
            return message.content[0].text
        LOGGER.warning(
            'Expected TextBlock response, got: %s',
            message.content[0].__class__,
        )
        return ''

    def _create_client(self) -> claude_agent_sdk.ClaudeSDKClient:
        """Create the Claude SDK client, initializing the environment."""
        settings = self._initialize_working_directory()
        LOGGER.debug('Claude Code settings: %s', settings)

        # Create MCP tool for unified agent responses
        @claude_agent_sdk.tool(
            'submit_agent_response',
            'Submit the final agent response (required)',
            models.ClaudeAgentResponse.model_json_schema(),
        )
        async def submit_agent_response(
            args: dict[str, typing.Any],
        ) -> dict[str, typing.Any]:
            """Submit unified agent response via MCP tool."""
            LOGGER.debug('submit_agent_response tool invoked with: %r', args)
            try:
                self._submitted_response = (
                    models.ClaudeAgentResponse.model_validate(args)
                )
            except pydantic.ValidationError as err:
                return {
                    'content': [
                        {
                            'type': 'text',
                            'text': f'Error: invalid response - {err}',
                        }
                    ],
                    'is_error': True,
                }
            return {
                'content': [
                    {'type': 'text', 'text': 'Response submitted successfully'}
                ]
            }

        agent_tools = claude_agent_sdk.create_sdk_mcp_server(
            'agent_tools', '1.0.0', [submit_agent_response]
        )

        system_prompt = (BASE_PATH / 'claude-code' / 'CLAUDE.md').read_text()
        if self.context.workflow.configuration.prompt:
            system_prompt += '\n\n---\n\n'
            if isinstance(
                self.context.workflow.configuration.prompt, pydantic.AnyUrl
            ):
                system_prompt += prompts.render(
                    self.context,
                    self.context.workflow.configuration.prompt,
                    **self.prompt_kwargs,
                )
            else:
                raise RuntimeError

        # Build MCP servers dict with workflow-defined servers
        mcp_servers: dict[str, typing.Any] = {'agent_tools': agent_tools}
        for (
            name,
            config,
        ) in self.context.workflow.configuration.mcp_servers.items():
            mcp_servers[name] = _expand_mcp_config(config.model_dump())
            LOGGER.debug('Added workflow MCP server: %s', name)

        # Build local plugins list for SDK
        sdk_plugins: list[types.SdkPluginConfig] = [
            types.SdkPluginConfig(type='local', path=plugin.path)
            for plugin in self._merged_local_plugins
        ]

        options = claude_agent_sdk.ClaudeAgentOptions(
            agents=dict(self.agents),
            allowed_tools=[
                'Bash',
                'Bash(git:*)',
                'BashOutput',
                'Edit',
                'Glob',
                'Grep',
                'KillShell',
                'MultiEdit',
                'Read',
                'Task',
                'Write',
                'WebFetch',
                'WebSearch',
                'SlashCommand',
                'mcp__agent_tools__submit_agent_response',
            ],
            cwd=self.context.working_directory / 'repository',
            mcp_servers=mcp_servers,
            model=self.configuration.claude.model,
            plugins=sdk_plugins,
            settings=str(settings),
            setting_sources=['local'],
            system_prompt=types.SystemPromptPreset(
                type='preset', preset='claude_code', append=system_prompt
            ),
            permission_mode='bypassPermissions',
        )

        return claude_agent_sdk.ClaudeSDKClient(options)

    def _initialize_working_directory(self) -> pathlib.Path:
        """Setup dynamic agents and settings for claude-agents action.

        Returns:
            Path to generated settings.json file

        """
        claude_dir = self.context.working_directory / '.claude'
        commands_dir = claude_dir / 'commands'
        commands_dir.mkdir(parents=True, exist_ok=True)

        for file in (BASE_PATH / 'claude-code' / 'commands').rglob('*'):
            if file.suffix == '.j2':
                content = prompts.render(
                    self.context, file, **self.prompt_kwargs
                )
            else:
                content = file.read_text(encoding='utf-8')
            commands_dir.joinpath(file.name.rstrip('.j2')).write_text(
                content, encoding='utf-8'
            )

        output_styles_dir = claude_dir / 'output-style'
        output_styles_dir.mkdir(parents=True, exist_ok=True)

        for agent_type in models.ClaudeAgentType:
            self.agents[agent_type.value] = self._parse_agent_file(agent_type)

        # Create custom settings.json - disable all global settings
        settings = claude_dir / 'settings.json'
        settings_config: dict[str, typing.Any] = {
            'hooks': {},
            'outputStyle': 'json',
            'settingSources': ['project', 'local'],
            'permissions': {'deny': ['StructuredOutput']},
        }

        # Add merged plugin configuration
        merged_plugins = _merge_plugin_configs(
            self.configuration.claude.plugins,
            self.context.workflow.configuration.plugins,
        )

        # Add enabled plugins to settings
        if merged_plugins.enabled_plugins:
            settings_config['enabledPlugins'] = merged_plugins.enabled_plugins

        # Add extra marketplaces to settings
        if merged_plugins.marketplaces:
            extra_marketplaces: dict[str, typing.Any] = {}
            for name, marketplace in merged_plugins.marketplaces.items():
                source = marketplace.source
                source_config: dict[str, str] = {'source': source.source.value}
                if source.repo:
                    source_config['repo'] = source.repo
                if source.url:
                    source_config['url'] = source.url
                if source.path:
                    source_config['path'] = source.path
                extra_marketplaces[name] = {'source': source_config}
            settings_config['extraKnownMarketplaces'] = extra_marketplaces

        # Store merged local plugins for use in _create_client
        self._merged_local_plugins = merged_plugins.local_plugins

        # Add git configuration if signing is enabled
        if self.configuration.git.gpg_sign:
            git_config: dict[str, typing.Any] = {'commit': {'gpgsign': True}}

            # Add format specification (required for SSH signing)
            if self.configuration.git.gpg_format:
                git_config['gpg'] = {
                    'format': self.configuration.git.gpg_format
                }

            # Add signing key
            if self.configuration.git.signing_key:
                git_config['user'] = {
                    'signingkey': self.configuration.git.signing_key
                }

            # Add SSH program (for SSH signing with 1Password, etc.)
            if self.configuration.git.ssh_program:
                if 'gpg' not in git_config:
                    git_config['gpg'] = {}
                git_config['gpg']['ssh'] = {
                    'program': self.configuration.git.ssh_program
                }

            # Add GPG program (for traditional GPG signing)
            if self.configuration.git.gpg_program:
                if 'gpg' not in git_config:
                    git_config['gpg'] = {}
                git_config['gpg']['program'] = (
                    self.configuration.git.gpg_program
                )

            settings_config['git'] = git_config

        settings.write_text(
            json.dumps(settings_config, indent=2), encoding='utf-8'
        )

        with settings.open('r', encoding='utf-8') as f:
            LOGGER.debug('Claude Code settings: %s', f.read())

        return settings

    def _log_message(
        self,
        message_type: str,
        content: str
        | list[
            claude_agent_sdk.TextBlock
            | claude_agent_sdk.ContentBlock
            | claude_agent_sdk.ToolUseBlock
            | claude_agent_sdk.ToolResultBlock
        ],
    ) -> None:
        """Log the message from Claude Code passed in as a dataclass."""
        if isinstance(content, list):
            for entry in content:
                if isinstance(
                    entry,
                    claude_agent_sdk.ToolUseBlock
                    | claude_agent_sdk.ToolResultBlock,
                ):
                    continue
                elif isinstance(entry, claude_agent_sdk.TextBlock):
                    self.logger.debug(
                        '[%s] %s: %s',
                        self.context.imbi_project.slug,
                        message_type,
                        entry.text.rstrip(':'),
                    )
                elif isinstance(
                    entry,
                    claude_agent_sdk.ToolUseBlock
                    | claude_agent_sdk.ToolResultBlock,
                ):
                    self.logger.debug(
                        '[%s] %s: %r',
                        self.context.imbi_project.slug,
                        message_type,
                        entry,
                    )
                else:
                    raise RuntimeError(f'Unknown message type: {type(entry)}')
        else:
            self.logger.debug(
                '[%s] %s: %s',
                self.context.imbi_project.slug,
                message_type,
                content,
            )

    def _parse_agent_file(
        self, agent_type: models.ClaudeAgentType
    ) -> types.AgentDefinition:
        """Parse the agent file and return the agent.

        Expects format:
        ---
        name: agent_name
        description: Agent description
        tools: Tool1, Tool2, Tool3
        model: inherit
        ---
        Prompt content here...
        """
        agent_file = (
            BASE_PATH / 'claude-code' / 'agents' / f'{agent_type.value}.md.j2'
        )
        content = agent_file.read_text(encoding='utf-8')

        # Split frontmatter and prompt content
        parts = content.split('---', 2)
        if len(parts) < 3:
            raise ValueError(
                f'Invalid agent file format for {agent_type.value}'
            )

        # Parse frontmatter manually (simple YAML-like format)
        frontmatter = {}
        for line in parts[1].strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                frontmatter[key.strip()] = value.strip()

        # Extract prompt (everything after second ---)
        prompt = parts[2].strip()

        # Parse tools (comma-separated string to list)
        tools_str = frontmatter.get('tools', '')
        tools = [t.strip() for t in tools_str.split(',')] if tools_str else []

        return types.AgentDefinition(
            description=frontmatter.get('description', ''),
            prompt=prompts.render(
                self.context, template=prompt, **self.prompt_kwargs
            ),
            tools=tools,
            model=frontmatter.get('model', 'inherit'),  # type: ignore
        )

    def _parse_message(self, message: claude_agent_sdk.Message) -> None:
        """Parse the response from Claude Code."""
        if isinstance(message, claude_agent_sdk.AssistantMessage):
            self._log_message('Claude Assistant', message.content)
            # Check for tool use blocks
            for content in message.content:
                if isinstance(content, claude_agent_sdk.ToolUseBlock):
                    LOGGER.debug(
                        'Tool use detected: %s with input: %r',
                        content.name,
                        content.input,
                    )
        elif isinstance(message, claude_agent_sdk.SystemMessage):
            self.logger.debug(
                '%s Claude System: %s',
                self.context.imbi_project.slug,
                message.data,
            )
        elif isinstance(message, claude_agent_sdk.UserMessage):
            self._log_message('Claude User', message.content)
        elif isinstance(message, claude_agent_sdk.ResultMessage):
            if self.session_id != message.session_id:
                self.session_id = message.session_id
            self.tracker.add_claude_run(message)
            if message.is_error:
                LOGGER.error('Claude Error: %s', message.result)
            else:
                LOGGER.debug(
                    'Result (%s): %r', message.session_id, message.result
                )
