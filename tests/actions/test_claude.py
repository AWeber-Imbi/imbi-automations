"""Comprehensive tests for the ClaudeAction class."""

import pathlib
import tempfile
import unittest
from unittest import mock

from imbi_automations import models
from imbi_automations.actions import claude
from tests import base


class ClaudeActionTestCase(base.AsyncTestCase):
    """Test cases for the ClaudeAction class."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        self.config = models.Configuration(
            claude_code=models.ClaudeCodeConfiguration(executable='claude'),
            anthropic=models.AnthropicConfiguration(),
            imbi=models.ImbiConfiguration(api_key='test', hostname='test.com'),
            github=models.GitHubConfiguration(api_key='test'),
            commit_author='Test Author <test@example.com>',
        )

        # Create required directory structure
        (self.working_directory / 'workflow').mkdir()
        (self.working_directory / 'extracted').mkdir()
        (self.working_directory / 'repository').mkdir()

        # Create mock workflow and context
        self.workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
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
                facts=None,
                identifiers=None,
                links=None,
                name='test-project',
                namespace='test-namespace',
                namespace_slug='test-namespace',
                project_score=None,
                project_type='API',
                project_type_slug='api',
                slug='test-project',
                urls=None,
                imbi_url='https://imbi.example.com/projects/123',
            ),
            working_directory=self.working_directory,
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    def test_get_prompt_task_with_jinja2(self) -> None:
        """Test _get_prompt method for task agent with Jinja2 template."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_action = claude.ClaudeAction(
                self.config, self.context, verbose=True
            )

        action = models.WorkflowClaudeAction(
            name='test-action', type='claude', task_prompt='test-prompt.j2'
        )

        # Create Jinja2 template file
        template_content = 'Hello {{ imbi_project.name }}!'
        (self.working_directory / 'workflow' / 'test-prompt.j2').write_text(
            template_content
        )

        with mock.patch(
            'imbi_automations.prompts.render',
            return_value='Hello test-project!',
        ) as mock_render:
            prompt = claude_action._get_prompt(action, claude.AgentType.task)

        self.assertIn('"task"', prompt)
        self.assertIn('Hello test-project!', prompt)
        mock_render.assert_called_once()

    def test_get_prompt_validator_with_plain_text(self) -> None:
        """Test _get_prompt method for validator agent with plain text."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_action = claude.ClaudeAction(
                self.config, self.context, verbose=True
            )

        action = models.WorkflowClaudeAction(
            name='test-action',
            type='claude',
            task_prompt='test-prompt.md',
            validation_prompt='test-validation.md',
        )

        # Create plain text prompt file
        validation_content = 'Validate the generated code'
        (
            self.working_directory / 'workflow' / 'test-validation.md'
        ).write_text(validation_content)

        prompt = claude_action._get_prompt(action, claude.AgentType.validation)

        self.assertIn('"validation"', prompt)
        self.assertIn('Validate the generated code', prompt)

    @mock.patch('imbi_automations.claude.Claude.agent_query')
    async def test_execute_cycle_success(
        self, mock_agent_query: mock.AsyncMock
    ) -> None:
        """Test successful execution cycle."""
        # Mock successful agent responses
        mock_agent_query.return_value = models.AgentRun(
            result=models.AgentRunResult.success, message='Success', errors=[]
        )

        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_action = claude.ClaudeAction(
                self.config, self.context, verbose=True
            )

        action = models.WorkflowClaudeAction(
            name='test-action',
            type='claude',
            task_prompt='test-prompt.md',
            validation_prompt='test-validation.md',
        )

        # Create prompt files
        (self.working_directory / 'workflow' / 'test-prompt.md').write_text(
            'Task prompt'
        )
        (
            self.working_directory / 'workflow' / 'test-validation.md'
        ).write_text('Validation prompt')

        result = await claude_action._execute_cycle(action, cycle=1)

        self.assertTrue(result)
        self.assertEqual(mock_agent_query.call_count, 2)  # task + validator

    @mock.patch('imbi_automations.claude.Claude.agent_query')
    async def test_execute_cycle_task_failure(
        self, mock_agent_query: mock.AsyncMock
    ) -> None:
        """Test execution cycle with task agent failure."""
        # Mock task agent failure
        mock_agent_query.return_value = models.AgentRun(
            result=models.AgentRunResult.failure,
            message='Task failed',
            errors=['Error 1'],
        )

        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_action = claude.ClaudeAction(
                self.config, self.context, verbose=True
            )

        action = models.WorkflowClaudeAction(
            name='test-action', type='claude', task_prompt='test-prompt.md'
        )

        (self.working_directory / 'workflow' / 'test-prompt.md').write_text(
            'Task prompt'
        )

        result = await claude_action._execute_cycle(action, cycle=1)

        self.assertFalse(result)
        mock_agent_query.assert_called_once()

    @mock.patch('imbi_automations.claude.Claude.agent_query')
    async def test_execute_all_cycles_success(
        self, mock_agent_query: mock.AsyncMock
    ) -> None:
        """Test execute with successful first cycle."""
        mock_agent_query.return_value = models.AgentRun(
            result=models.AgentRunResult.success, message='Success', errors=[]
        )

        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_action = claude.ClaudeAction(
                self.config, self.context, verbose=True
            )

        action = models.WorkflowClaudeAction(
            name='test-action',
            type='claude',
            task_prompt='test-prompt.md',
            max_cycles=3,
        )

        (self.working_directory / 'workflow' / 'test-prompt.md').write_text(
            'Task prompt'
        )

        await claude_action.execute(action)

        # Should only call once since first cycle succeeds
        mock_agent_query.assert_called_once()

    @mock.patch('imbi_automations.claude.Claude.agent_query')
    async def test_execute_all_cycles_fail(
        self, mock_agent_query: mock.AsyncMock
    ) -> None:
        """Test execute with all cycles failing."""
        mock_agent_query.return_value = models.AgentRun(
            result=models.AgentRunResult.failure,
            message='Failed',
            errors=['Error'],
        )

        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_action = claude.ClaudeAction(
                self.config, self.context, verbose=True
            )

        action = models.WorkflowClaudeAction(
            name='test-action',
            type='claude',
            task_prompt='test-prompt.md',
            max_cycles=2,
        )

        (self.working_directory / 'workflow' / 'test-prompt.md').write_text(
            'Task prompt'
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await claude_action.execute(action)

        self.assertIn('failed after 2 cycles', str(exc_context.exception))
        self.assertEqual(mock_agent_query.call_count, 2)  # Both cycles tried

    @mock.patch('imbi_automations.claude.Claude.agent_query')
    async def test_execute_multiple_cycles_eventual_success(
        self, mock_agent_query: mock.AsyncMock
    ) -> None:
        """Test execute with success on second cycle."""
        # First cycle fails, second succeeds
        mock_agent_query.side_effect = [
            models.AgentRun(
                result=models.AgentRunResult.failure,
                message='Failed',
                errors=[],
            ),
            models.AgentRun(
                result=models.AgentRunResult.success,
                message='Success',
                errors=[],
            ),
        ]

        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_action = claude.ClaudeAction(
                self.config, self.context, verbose=True
            )

        action = models.WorkflowClaudeAction(
            name='test-action',
            type='claude',
            task_prompt='test-prompt.md',
            max_cycles=3,
        )

        (self.working_directory / 'workflow' / 'test-prompt.md').write_text(
            'Task prompt'
        )

        await claude_action.execute(action)

        self.assertEqual(mock_agent_query.call_count, 2)


if __name__ == '__main__':
    unittest.main()
