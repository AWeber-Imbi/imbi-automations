"""Claude Code integration for AI-powered code transformations.

Provides integration with Claude Code SDK for executing complex multi-file
analysis and transformations using Claude AI, supporting both agent-based
workflows and direct Anthropic API queries.
"""

import json
import logging
import pathlib
import typing
from email import utils as email_utils

import anthropic
import claude_agent_sdk
import pydantic
from anthropic import types as anthropic_types
from claude_agent_sdk import types

from imbi_automations import mixins, models, prompts, tracker, utils, version

LOGGER = logging.getLogger(__name__)
BASE_PATH = pathlib.Path(__file__).parent

COMMIT = 'commit'


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
        self.agents: dict[str, types.AgentDefinition] = {}
        self.configuration = config
        self.context = context
        self.logger: logging.Logger = LOGGER
        self.session_id: str | None = None
        commit_author = email_utils.parseaddr(self.configuration.commit_author)
        self.prompt_kwargs = {
            'commit_author': self.configuration.commit_author,
            'commit_author_name': commit_author[0],
            'commit_author_address': commit_author[1],
            'configuration': self.configuration,
            'workflow_name': context.workflow.configuration.name,
            'working_directory': self.context.working_directory,
        }
        self.tracker = tracker.Tracker.get_instance()
        self._set_workflow_logger(self.context.workflow)
        self._submitted_response: models.AgentRun | models.AgentPlan | None = (
            None
        )
        self.client = self._create_client()

    async def agent_query(self, prompt: str) -> models.AgentRun:
        self._submitted_response = None  # Reset for each query
        await self.client.connect()
        await self.client.query(prompt)
        response = await self._response()
        await self.client.disconnect()
        return response

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
        """Create the Claude SDK client, initializing the environment"""
        settings = self._initialize_working_directory()
        LOGGER.debug('Claude Code settings: %s', settings)

        agent_tools = claude_agent_sdk.create_sdk_mcp_server(
            'agent_tools',
            version,
            [
                self._submit_task_response,
                self._submit_validation_response,
                self._submit_plan,
            ],
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

        options = claude_agent_sdk.ClaudeAgentOptions(
            agents=self.agents,
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
                'Write',
                'WebFetch',
                'WebSearch',
                'SlashCommand',
                'mcp__agent_tools__submit_task_response',
                'mcp__agent_tools__submit_validation_response',
                'mcp__agent_tools__submit_plan',
            ],
            cwd=self.context.working_directory,
            mcp_servers={'agent_tools': agent_tools},
            model=self.configuration.claude_code.model,
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

        # Import AgentType from actions.claude to iterate agent types
        from imbi_automations.actions import claude as claude_actions

        for agent_type in claude_actions.AgentType:
            self.agents[agent_type.value] = self._parse_agent_file(
                agent_type.value
            )

        # Create custom settings.json - disable all global settings
        settings = claude_dir / 'settings.json'
        settings_config = {
            'hooks': {},
            'outputStyle': 'json',
            'settingSources': ['project', 'local'],
        }

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
                        '%s %s: %s',
                        self.context.imbi_project.slug,
                        message_type,
                        entry.text,
                    )
                else:
                    raise RuntimeError(f'Unknown message type: {type(entry)}')
        else:
            self.logger.debug(
                '%s %s: %s',
                self.context.imbi_project.slug,
                message_type,
                content,
            )

    def _parse_agent_file(self, name: str) -> types.AgentDefinition:
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
        agent_file = BASE_PATH / 'claude-code' / 'agents' / f'{name}.md.j2'
        content = agent_file.read_text(encoding='utf-8')

        # Split frontmatter and prompt content
        parts = content.split('---', 2)
        if len(parts) < 3:
            raise ValueError(f'Invalid agent file format for {name}')

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
            model=frontmatter.get('model', 'inherit'),
        )

    def _parse_message(
        self, message: claude_agent_sdk.Message
    ) -> models.AgentRun | None:
        """Parse the response from Claude Code."""
        if isinstance(message, claude_agent_sdk.AssistantMessage):
            self._log_message('Claude Assistant', message.content)
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
                return models.AgentRun(
                    result=models.AgentRunResult.failure,
                    message='Claude Error',
                    errors=[message.result],
                )
            # Don't pre-strip code fences - let extract_json handle it
            LOGGER.debug('Result (%s): %r', message.session_id, message.result)

            try:
                payload = utils.extract_json(message.result)
            except ValueError as err:
                self.logger.error(
                    '%s failed to parse JSON result: %s',
                    self.context.imbi_project.slug,
                    err,
                )
                return models.AgentRun(
                    result=models.AgentRunResult.failure,
                    errors=[f'Failed to parse JSON result: {err}'],
                    message='Agent Contract Failure',
                )
            return models.AgentRun.model_validate(payload)
        return None

    async def _response(self) -> models.AgentRun:
        async for message in self.client.receive_response():
            response = self._parse_message(message)
            if response and isinstance(response, models.AgentRun):
                return response

        # Check if agent submitted response via tool (preferred method)
        if self._submitted_response:
            return self._submitted_response

        return models.AgentRun(
            result=models.AgentRunResult.failure,
            message='Unspecified failure',
            errors=[],
        )

    @claude_agent_sdk.tool(
        name='submit_task_response',
        description='Submit task execution result (task agents only)',
        input_schema={
            'type': 'object',
            'properties': {
                'result': {
                    'type': 'string',
                    'enum': ['success', 'failure'],
                    'description': 'Task execution result',
                },
                'message': {
                    'type': 'string',
                    'description': 'Optional completion message',
                },
                'errors': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'List of errors (for failures)',
                },
            },
            'required': ['result'],
        },
    )
    def _submit_task_response(self, **kwargs: typing.Any) -> str:
        """Submit task agent response."""
        LOGGER.debug('submit_task_response tool invoked with: %r', kwargs)
        try:
            response = models.AgentRun.model_validate(kwargs)
            self._submitted_response = response
            return 'Task response submitted successfully'
        except pydantic.ValidationError as exc:
            error_msg = f'Invalid task response: {exc}'
            LOGGER.error(error_msg)
            return error_msg

    @claude_agent_sdk.tool(
        name='submit_validation_response',
        description='Submit validation result (validation agents only)',
        input_schema={
            'type': 'object',
            'properties': {
                'result': {
                    'type': 'string',
                    'enum': ['success', 'failure'],
                    'description': 'Validation result',
                },
                'message': {
                    'type': 'string',
                    'description': 'Optional validation message',
                },
                'errors': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'List of validation errors',
                },
            },
            'required': ['result'],
        },
    )
    def _submit_validation_response(self, **kwargs: typing.Any) -> str:
        """Submit validation agent response."""
        LOGGER.debug('submit_validation_response invoked: %r', kwargs)
        try:
            response = models.AgentRun.model_validate(kwargs)
            self._submitted_response = response
            return 'Validation response submitted successfully'
        except pydantic.ValidationError as exc:
            error_msg = f'Invalid validation response: {exc}'
            LOGGER.error(error_msg)
            return error_msg

    @claude_agent_sdk.tool(
        name='submit_plan',
        description='Submit planning result (planning agents only)',
        input_schema={
            'type': 'object',
            'properties': {
                'result': {
                    'type': 'string',
                    'enum': ['success', 'failure'],
                    'description': 'Planning result',
                },
                'plan': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'List of tasks (simple strings)',
                },
                'analysis': {
                    'type': 'string',
                    'description': 'Analysis and context',
                },
            },
            'required': ['result', 'plan', 'analysis'],
        },
    )
    def _submit_plan(self, **kwargs: typing.Any) -> str:
        """Submit planning agent response."""
        LOGGER.debug('submit_plan tool invoked with: %r', kwargs)
        try:
            response = models.AgentRun.model_validate(kwargs)
            self._submitted_response = response
            return 'Plan submitted successfully'
        except pydantic.ValidationError as exc:
            error_msg = f'Invalid plan format: {exc}'
            LOGGER.error(error_msg)
            return error_msg
