"""Jira ticket creation action using an agentic Claude session.

Invokes Claude Agent SDK with a configurable task prompt and an in-process
MCP tool that posts to the Jira Cloud REST API. Claude authors the ticket
summary and description; project_key, issue_type, labels, and components
come from the action config and cannot be overridden by the agent.
"""

import logging
import typing

import claude_agent_sdk
import httpx

from imbi_automations import claude, clients, mixins, models, prompts

LOGGER = logging.getLogger(__name__)

_TOOL_SCHEMA: dict[str, typing.Any] = {
    'type': 'object',
    'properties': {
        'summary': {
            'type': 'string',
            'description': 'Concise issue title (plain text, no markdown).',
        },
        'description': {
            'type': 'string',
            'description': (
                'Issue body as plain text or markdown. Use blank lines to '
                'separate paragraphs. The client wraps this into ADF.'
            ),
        },
    },
    'required': ['summary', 'description'],
}


class JiraActions(mixins.WorkflowLoggerMixin):
    """Executes Jira actions (currently: create_ticket)."""

    def __init__(
        self,
        configuration: models.Configuration,
        context: models.WorkflowContext,
        verbose: bool,
    ) -> None:
        super().__init__(verbose)
        self._set_workflow_logger(context.workflow)
        self.logger = LOGGER
        self.configuration = configuration
        self.context = context
        self._created_issue: models.JiraIssueCreated | None = None
        self._last_tool_error: str | None = None

    async def execute(self, action: models.WorkflowJiraAction) -> None:
        """Execute a Jira action.

        Raises:
            RuntimeError: If command is not supported or the agent fails to
                create a ticket within max_cycles.
            ValueError: If jira configuration is missing.

        """
        match action.command:
            case models.WorkflowJiraActionCommand.create_ticket:
                await self._create_ticket(action)
            case _:
                raise RuntimeError(f'Unsupported command: {action.command}')

    async def _create_ticket(self, action: models.WorkflowJiraAction) -> None:
        if self.configuration.jira is None:
            raise ValueError(
                'jira configuration is required for jira actions. Set '
                'ATLASSIAN_DOMAIN, ATLASSIAN_EMAIL, ATLASSIAN_API_KEY or '
                'provide a [jira] section in config.toml.'
            )

        jira_client = clients.Jira(self.configuration.jira)
        try:
            await self._run_create_ticket(action, jira_client)
        finally:
            await jira_client.http_client.aclose()

    async def _run_create_ticket(
        self, action: models.WorkflowJiraAction, jira_client: clients.Jira
    ) -> None:
        project_key = self._render(action.project_key)
        issue_type = self._render(action.issue_type)
        priority = self._render(action.priority)
        labels = [self._render(label) for label in action.labels]
        components = [self._render(c) for c in action.components]

        base_prompt = prompts.render(
            self.context,
            action.prompt,
            project_key=project_key,
            issue_type=issue_type,
            labels=labels,
            components=components,
            priority=priority,
        )

        handler = self._build_create_handler(
            action,
            jira_client,
            project_key=project_key,
            issue_type=issue_type,
            labels=labels,
            components=components,
            priority=priority,
        )
        create_tool = claude_agent_sdk.tool(
            'create_jira_issue',
            (
                'Create a Jira ticket. The project, issue type, labels, and '
                'components are fixed by the workflow — only supply summary '
                'and description.'
            ),
            _TOOL_SCHEMA,
        )(handler)
        jira_mcp = claude_agent_sdk.create_sdk_mcp_server(
            'jira_tools', '1.0.0', [create_tool]
        )

        claude_client = claude.Claude(
            self.configuration, self.context, self.verbose
        )
        allowed_tools = ['Read', 'Skill', 'mcp__jira_tools__create_jira_issue']
        timeout = action.timeout or '5m'

        for cycle in range(1, action.max_cycles + 1):
            self.logger.debug(
                '%s [%s/%s] %s jira create_ticket cycle %d/%d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                cycle,
                action.max_cycles,
            )
            self._created_issue = None
            prior_error = self._last_tool_error
            self._last_tool_error = None

            prompt = base_prompt
            if cycle > 1 and prior_error:
                prompt = (
                    f'{base_prompt}\n\n---\n\n'
                    'The previous attempt failed with this error from Jira:\n'
                    f'```\n{prior_error}\n```\n\n'
                    'Adjust the summary and/or description and call '
                    '`create_jira_issue` again.'
                )

            try:
                await claude_client.custom_tool_session(
                    prompt,
                    mcp_server_name='jira_tools',
                    mcp_server=jira_mcp,
                    allowed_tools=allowed_tools,
                    timeout=timeout,
                )
            except TimeoutError as exc:
                raise RuntimeError(
                    f'Jira action {action.name} timed out after {timeout} '
                    f'in cycle {cycle}/{action.max_cycles}'
                ) from exc

            if self._created_issue is not None:
                break

            self.logger.warning(
                '%s [%s/%s] %s no ticket created in cycle %d/%d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                cycle,
                action.max_cycles,
            )

        if self._created_issue is None:
            raise RuntimeError(
                f'Jira action {action.name} did not create a ticket after '
                f'{action.max_cycles} cycles'
            )

        issue = self._created_issue
        self.logger.info(
            '%s [%s/%s] %s created Jira ticket %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            issue.key,
        )

        if action.variable_name:
            self.context.variables[action.variable_name] = {
                'id': issue.id,
                'key': issue.key,
                'url': str(issue.self_url),
                'browse_url': jira_client.browse_url(issue.key),
            }

    def _render(self, value: str | None) -> str | None:
        """Render a workflow-configured string as a Jinja2 template.

        Returns the input unchanged when it is None or does not contain any
        Jinja2 delimiters, so unused/empty fields are pass-through.
        """
        if value is None or ('{{' not in value and '{%' not in value):
            return value
        return prompts.render_template_string(
            value,
            workflow=self.context.workflow,
            github_repository=self.context.github_repository,
            imbi_project=self.context.imbi_project,
            working_directory=self.context.working_directory,
            starting_commit=self.context.starting_commit,
            variables=self.context.variables,
        )

    def _build_create_handler(
        self,
        action: models.WorkflowJiraAction,
        jira_client: clients.Jira,
        *,
        project_key: str,
        issue_type: str,
        labels: list[str],
        components: list[str],
        priority: str | None,
    ) -> typing.Callable[..., typing.Awaitable[dict[str, typing.Any]]]:
        """Return the raw tool-handler coroutine bound to the action config.

        Returned separately from the `@claude_agent_sdk.tool` decoration so
        tests can invoke the handler directly without going through the SDK
        tool wrapper.
        """

        async def create_jira_issue(
            args: dict[str, typing.Any],
        ) -> dict[str, typing.Any]:
            summary = args.get('summary')
            description = args.get('description')
            if not summary or not description:
                return {
                    'content': [
                        {
                            'type': 'text',
                            'text': (
                                'Both summary and description are required.'
                            ),
                        }
                    ],
                    'is_error': True,
                }

            try:
                issue = await jira_client.create_issue(
                    project_key=project_key,
                    summary=summary,
                    issue_type=issue_type,
                    description=description,
                    labels=list(labels) or None,
                    components=list(components) or None,
                    priority=priority,
                )
            except httpx.HTTPStatusError as err:
                err_text = (
                    f'Jira returned HTTP {err.response.status_code}: '
                    f'{err.response.text}'
                )
                self._last_tool_error = err_text
                return {
                    'content': [{'type': 'text', 'text': err_text}],
                    'is_error': True,
                }
            except httpx.HTTPError as err:
                err_text = f'Jira request failed: {err}'
                self._last_tool_error = err_text
                return {
                    'content': [{'type': 'text', 'text': err_text}],
                    'is_error': True,
                }

            self._created_issue = issue
            return {
                'content': [
                    {
                        'type': 'text',
                        'text': (
                            f'Created Jira issue {issue.key} (id={issue.id}).'
                        ),
                    }
                ]
            }

        return create_jira_issue
