"""Tests for the Jira action module."""

import pathlib
import tempfile
from unittest import mock

import httpx
import pydantic

from imbi_automations import models
from imbi_automations.actions import jira as jira_actions
from tests import base


class JiraActionsTestCase(base.AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        (self.working_directory / 'workflow').mkdir()
        (self.working_directory / 'workflow' / 'prompts').mkdir()
        self.prompt_path = (
            self.working_directory / 'workflow' / 'prompts' / 'file.md.j2'
        )
        self.prompt_path.write_text(
            'Create a ticket for {{ imbi_project.name }} in {{ project_key }}.'
        )

        self.workflow = models.Workflow(
            path=pathlib.Path('/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

        self.context = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=models.ImbiProject(
                id=123,
                dependencies=None,
                description='Test project',
                environments=None,
                facts={},
                identifiers={},
                links=None,
                name='Test Project',
                namespace='ns',
                namespace_slug='ns',
                project_score=None,
                project_type='API',
                project_type_slug='api',
                slug='test-project',
                urls=None,
                imbi_url='https://imbi.example.com/projects/123',
            ),
            working_directory=self.working_directory,
        )

        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-key'  # noqa: S106
            ),
            jira=models.JiraConfiguration(
                domain='example.atlassian.net',
                email='tester@example.com',
                api_key='abc',  # noqa: S106
            ),
        )

        self.executor = jira_actions.JiraActions(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    def _make_action(self, **overrides: object) -> models.WorkflowJiraAction:
        kwargs = {
            'name': 'file-ticket',
            'type': 'jira',
            'command': 'create_ticket',
            'project_key': 'SEC',
            'issue_type': 'Task',
            'labels': ['automated'],
            'components': ['AppSec'],
            'prompt': 'workflow:///prompts/file.md.j2',
            'max_cycles': 3,
            'timeout': '5m',
        }
        kwargs.update(overrides)
        return models.WorkflowJiraAction(**kwargs)

    def _issue(self, key: str = 'SEC-1') -> models.JiraIssueCreated:
        return models.JiraIssueCreated.model_validate(
            {
                'id': '10001',
                'key': key,
                'self': (
                    'https://example.atlassian.net/rest/api/3/issue/10001'
                ),
            }
        )

    async def _simulate_tool_call(
        self,
        executor: jira_actions.JiraActions,
        action: models.WorkflowJiraAction,
        issue: models.JiraIssueCreated | None,
        error_text: str | None = None,
    ) -> None:
        """Simulate what the Claude session would do: set closure state."""
        executor._created_issue = issue
        executor._last_tool_error = error_text

    async def test_create_ticket_success_stores_variable(self) -> None:
        action = self._make_action(variable_name='ticket')
        issue = self._issue('SEC-42')

        async def fake_session(prompt: str, **kwargs: object) -> None:
            self.assertIn('Create a ticket for Test Project in SEC.', prompt)
            self.assertIn('Skill', kwargs['allowed_tools'])
            self.assertIn(
                'mcp__jira_tools__create_jira_issue', kwargs['allowed_tools']
            )
            await self._simulate_tool_call(self.executor, action, issue)

        with mock.patch(
            'imbi_automations.claude.Claude.custom_tool_session',
            side_effect=fake_session,
        ):
            await self.executor.execute(action)

        stored = self.context.variables['ticket']
        self.assertEqual(stored['key'], 'SEC-42')
        self.assertEqual(stored['id'], '10001')
        self.assertEqual(
            stored['browse_url'], 'https://example.atlassian.net/browse/SEC-42'
        )

    async def test_create_ticket_no_variable_still_succeeds(self) -> None:
        action = self._make_action()
        issue = self._issue()

        async def fake_session(prompt: str, **kwargs: object) -> None:
            await self._simulate_tool_call(self.executor, action, issue)

        with mock.patch(
            'imbi_automations.claude.Claude.custom_tool_session',
            side_effect=fake_session,
        ):
            await self.executor.execute(action)

        self.assertEqual(self.context.variables, {})

    async def test_create_ticket_retries_on_tool_error(self) -> None:
        action = self._make_action(max_cycles=3)
        call_count = {'n': 0}
        issue = self._issue('SEC-9')

        async def fake_session(prompt: str, **kwargs: object) -> None:
            call_count['n'] += 1
            if call_count['n'] == 1:
                await self._simulate_tool_call(
                    self.executor,
                    action,
                    issue=None,
                    error_text='HTTP 400: summary too long',
                )
            elif call_count['n'] == 2:
                # Second cycle should receive the retry prompt with the error.
                self.assertIn('summary too long', prompt)
                await self._simulate_tool_call(self.executor, action, issue)
            else:
                self.fail('Should not need a third cycle')

        with mock.patch(
            'imbi_automations.claude.Claude.custom_tool_session',
            side_effect=fake_session,
        ):
            await self.executor.execute(action)

        self.assertEqual(call_count['n'], 2)

    async def test_create_ticket_fails_when_no_issue_after_max_cycles(
        self,
    ) -> None:
        action = self._make_action(max_cycles=2)

        async def fake_session(prompt: str, **kwargs: object) -> None:
            await self._simulate_tool_call(
                self.executor, action, issue=None, error_text='failed'
            )

        with mock.patch(
            'imbi_automations.claude.Claude.custom_tool_session',
            side_effect=fake_session,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await self.executor.execute(action)
            self.assertIn('after 2 cycles', str(ctx.exception))

    async def test_create_ticket_timeout_raises_runtime_error(self) -> None:
        action = self._make_action()

        async def fake_session(prompt: str, **kwargs: object) -> None:
            raise TimeoutError('timed out')

        with mock.patch(
            'imbi_automations.claude.Claude.custom_tool_session',
            side_effect=fake_session,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await self.executor.execute(action)
            self.assertIn('timed out', str(ctx.exception))

    async def test_missing_jira_config_raises(self) -> None:
        self.configuration.jira = None
        action = self._make_action()
        with self.assertRaises(ValueError) as ctx:
            await self.executor.execute(action)
        self.assertIn('jira configuration is required', str(ctx.exception))

    async def test_tool_closure_builds_and_calls_client(self) -> None:
        """Exercise the MCP tool closure directly to verify it wires to the
        Jira client with action config (project_key/issue_type/labels/
        components/priority)."""
        action = self._make_action(
            labels=['a', 'b'], components=['c'], priority='High'
        )
        mock_client = mock.AsyncMock()
        mock_client.create_issue.return_value = self._issue('SEC-7')
        tool = self.executor._build_create_handler(
            action,
            mock_client,
            project_key='SEC',
            issue_type='Task',
            labels=['a', 'b'],
            components=['c'],
            priority='High',
        )

        result = await tool({'summary': 'Hello', 'description': 'World'})

        self.assertNotIn('is_error', result)
        mock_client.create_issue.assert_awaited_once_with(
            project_key='SEC',
            summary='Hello',
            issue_type='Task',
            description='World',
            labels=['a', 'b'],
            components=['c'],
            priority='High',
        )
        self.assertEqual(self.executor._created_issue.key, 'SEC-7')

    async def test_tool_closure_captures_http_error(self) -> None:
        action = self._make_action()
        mock_client = mock.AsyncMock()
        request = httpx.Request('POST', 'https://x/rest/api/3/issue')
        response = httpx.Response(400, request=request, text='bad')
        mock_client.create_issue.side_effect = httpx.HTTPStatusError(
            'bad', request=request, response=response
        )
        tool = self.executor._build_create_handler(
            action,
            mock_client,
            project_key='SEC',
            issue_type='Task',
            labels=['automated'],
            components=['AppSec'],
            priority=None,
        )

        result = await tool({'summary': 's', 'description': 'd'})

        self.assertTrue(result.get('is_error'))
        self.assertIn('HTTP 400', result['content'][0]['text'])
        self.assertIn('HTTP 400', self.executor._last_tool_error)
        self.assertIsNone(self.executor._created_issue)

    async def test_tool_closure_rejects_missing_fields(self) -> None:
        action = self._make_action()
        mock_client = mock.AsyncMock()
        tool = self.executor._build_create_handler(
            action,
            mock_client,
            project_key='SEC',
            issue_type='Task',
            labels=['automated'],
            components=['AppSec'],
            priority=None,
        )

        result = await tool({'summary': 'only summary'})
        self.assertTrue(result.get('is_error'))
        mock_client.create_issue.assert_not_called()

    async def test_missing_required_fields_fails_validation(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            models.WorkflowJiraAction(
                name='missing',
                type='jira',
                command='create_ticket',
                # Missing project_key and prompt
            )

    async def test_create_ticket_renders_templated_project_key(self) -> None:
        """project_key and labels support Jinja2 templates (e.g. for mapping
        imbi_project.namespace_slug to a Jira project key)."""
        action = self._make_action(
            project_key=(
                "{{ {'ns':'MAPPED','other':'OTHER'}"
                '[imbi_project.namespace_slug] }}'
            ),
            labels=['automated', '{{ imbi_project.slug }}'],
        )
        captured: dict[str, object] = {}
        real_build = self.executor._build_create_handler

        def capture_build(*args: object, **kwargs: object) -> object:
            captured.update(kwargs)
            return real_build(*args, **kwargs)

        async def fake_session(prompt: str, **_kwargs: object) -> None:
            self.assertIn('MAPPED', prompt)
            await self._simulate_tool_call(
                self.executor, action, self._issue('MAPPED-1')
            )

        with (
            mock.patch.object(
                self.executor,
                '_build_create_handler',
                side_effect=capture_build,
            ),
            mock.patch(
                'imbi_automations.claude.Claude.custom_tool_session',
                side_effect=fake_session,
            ),
        ):
            await self.executor.execute(action)

        self.assertEqual(captured.get('project_key'), 'MAPPED')
        self.assertEqual(captured.get('labels'), ['automated', 'test-project'])
        self.assertEqual(captured.get('issue_type'), 'Task')
        self.assertEqual(captured.get('components'), ['AppSec'])
        self.assertIsNone(captured.get('priority'))

    async def test_unsupported_command_raises(self) -> None:
        action = self._make_action()
        action.command = 'not_real'  # type: ignore[assignment]
        with self.assertRaises(RuntimeError):
            await self.executor.execute(action)
