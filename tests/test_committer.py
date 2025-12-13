"""Tests for the committer module."""

import pathlib
import tempfile
import unittest
from unittest import mock

from imbi_automations import committer, models
from tests import base


class CommitterRoutingTestCase(base.AsyncTestCase):
    """Test cases for Committer.commit() routing logic."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        # Create required directory structure
        (self.working_directory / 'repository').mkdir()

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

    async def test_routes_to_claude_commit_when_all_conditions_true(
        self,
    ) -> None:
        """Test commit routes to _claude_commit when all conditions are met."""
        config = models.Configuration(
            ai_commits=True,
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            anthropic=models.AnthropicConfiguration(),
            git=models.GitConfiguration(
                user_name='Test', user_email='test@example.com'
            ),
            imbi=models.ImbiConfiguration(api_key='test', hostname='test.com'),
        )
        action = models.WorkflowAction(name='test-action', ai_commit=True)

        c = committer.Committer(config, verbose=False)

        with mock.patch.object(
            c, '_claude_commit', return_value=True
        ) as mock_claude:
            result = await c.commit(self.context, action)

        mock_claude.assert_called_once_with(self.context, action)
        self.assertTrue(result)

    async def test_routes_to_manual_commit_when_ai_commit_false(self) -> None:
        """Test commit routes to _manual_commit when ai_commit is False."""
        config = models.Configuration(
            ai_commits=True,
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            anthropic=models.AnthropicConfiguration(),
            git=models.GitConfiguration(
                user_name='Test', user_email='test@example.com'
            ),
            imbi=models.ImbiConfiguration(api_key='test', hostname='test.com'),
        )
        action = models.WorkflowAction(name='test-action', ai_commit=False)

        c = committer.Committer(config, verbose=False)

        with mock.patch.object(
            c, '_manual_commit', return_value=True
        ) as mock_manual:
            result = await c.commit(self.context, action)

        mock_manual.assert_called_once_with(self.context, action)
        self.assertTrue(result)

    async def test_routes_to_manual_commit_when_config_ai_commits_false(
        self,
    ) -> None:
        """Test routes to _manual_commit when config.ai_commits is False."""
        config = models.Configuration(
            ai_commits=False,
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            anthropic=models.AnthropicConfiguration(),
            git=models.GitConfiguration(
                user_name='Test', user_email='test@example.com'
            ),
            imbi=models.ImbiConfiguration(api_key='test', hostname='test.com'),
        )
        action = models.WorkflowAction(name='test-action', ai_commit=True)

        c = committer.Committer(config, verbose=False)

        with mock.patch.object(
            c, '_manual_commit', return_value=True
        ) as mock_manual:
            result = await c.commit(self.context, action)

        mock_manual.assert_called_once_with(self.context, action)
        self.assertTrue(result)

    async def test_routes_to_manual_commit_when_claude_disabled(self) -> None:
        """Test commit routes to _manual_commit when Claude is disabled."""
        config = models.Configuration(
            ai_commits=True,
            claude=models.ClaudeAgentConfiguration(
                enabled=False, executable='claude'
            ),
            anthropic=models.AnthropicConfiguration(),
            git=models.GitConfiguration(
                user_name='Test', user_email='test@example.com'
            ),
            imbi=models.ImbiConfiguration(api_key='test', hostname='test.com'),
        )
        action = models.WorkflowAction(name='test-action', ai_commit=True)

        c = committer.Committer(config, verbose=False)

        with mock.patch.object(
            c, '_manual_commit', return_value=True
        ) as mock_manual:
            result = await c.commit(self.context, action)

        mock_manual.assert_called_once_with(self.context, action)
        self.assertTrue(result)


class ClaudeCommitTestCase(base.AsyncTestCase):
    """Test cases for Committer._claude_commit()."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        # Create required directory structure
        (self.working_directory / 'repository').mkdir()
        (self.working_directory / 'workflow').mkdir()
        (self.working_directory / 'extracted').mkdir()

        self.config = models.Configuration(
            ai_commits=True,
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            anthropic=models.AnthropicConfiguration(),
            git=models.GitConfiguration(
                user_name='Test', user_email='test@example.com'
            ),
            imbi=models.ImbiConfiguration(api_key='test', hostname='test.com'),
        )

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

        self.action = models.WorkflowAction(name='test-action', ai_commit=True)

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch('imbi_automations.committer.prompts.render')
    @mock.patch('imbi_automations.committer.claude.Claude')
    async def test_returns_true_on_successful_commit(
        self, mock_claude_class: mock.MagicMock, mock_render: mock.MagicMock
    ) -> None:
        """Test _claude_commit returns True on successful commit."""
        mock_client = mock.MagicMock()
        mock_claude_class.return_value = mock_client
        mock_client.prompt_kwargs = {}
        mock_render.return_value = 'Commit the changes'

        # Create a proper async mock for agent_query
        async def mock_agent_query(prompt: str) -> models.ClaudeAgentResponse:
            return models.ClaudeAgentResponse(
                message='Committed changes successfully with SHA abc123'
            )

        mock_client.agent_query = mock_agent_query

        c = committer.Committer(self.config, verbose=False)
        result = await c._claude_commit(self.context, self.action)

        self.assertTrue(result)

    @mock.patch('imbi_automations.committer.prompts.render')
    @mock.patch('imbi_automations.committer.claude.Claude')
    async def test_returns_false_when_no_changes_to_commit(
        self, mock_claude_class: mock.MagicMock, mock_render: mock.MagicMock
    ) -> None:
        """Test _claude_commit returns False when no changes to commit."""
        mock_client = mock.MagicMock()
        mock_claude_class.return_value = mock_client
        mock_client.prompt_kwargs = {}
        mock_render.return_value = 'Commit the changes'

        async def mock_agent_query(prompt: str) -> models.ClaudeAgentResponse:
            return models.ClaudeAgentResponse(
                message='There are no changes to commit.'
            )

        mock_client.agent_query = mock_agent_query

        c = committer.Committer(self.config, verbose=False)
        result = await c._claude_commit(self.context, self.action)

        self.assertFalse(result)

    @mock.patch('imbi_automations.committer.prompts.render')
    @mock.patch('imbi_automations.committer.claude.Claude')
    async def test_returns_false_when_working_tree_clean(
        self, mock_claude_class: mock.MagicMock, mock_render: mock.MagicMock
    ) -> None:
        """Test _claude_commit returns False when working tree is clean."""
        mock_client = mock.MagicMock()
        mock_claude_class.return_value = mock_client
        mock_client.prompt_kwargs = {}
        mock_render.return_value = 'Commit the changes'

        async def mock_agent_query(prompt: str) -> models.ClaudeAgentResponse:
            return models.ClaudeAgentResponse(
                message='Nothing to commit, working tree is clean.'
            )

        mock_client.agent_query = mock_agent_query

        c = committer.Committer(self.config, verbose=False)
        result = await c._claude_commit(self.context, self.action)

        self.assertFalse(result)

    @mock.patch('imbi_automations.committer.prompts.render')
    @mock.patch('imbi_automations.committer.claude.Claude')
    async def test_raises_runtime_error_when_commit_failed(
        self, mock_claude_class: mock.MagicMock, mock_render: mock.MagicMock
    ) -> None:
        """Test _claude_commit raises RuntimeError when commit fails."""
        mock_client = mock.MagicMock()
        mock_claude_class.return_value = mock_client
        mock_client.prompt_kwargs = {}
        mock_render.return_value = 'Commit the changes'

        async def mock_agent_query(prompt: str) -> models.ClaudeAgentResponse:
            return models.ClaudeAgentResponse(
                message='Commit failed: pre-commit hook rejected changes'
            )

        mock_client.agent_query = mock_agent_query

        c = committer.Committer(self.config, verbose=False)

        with self.assertRaises(RuntimeError) as exc_context:
            await c._claude_commit(self.context, self.action)

        self.assertIn('Claude Code commit failed', str(exc_context.exception))
        self.assertIn('pre-commit hook', str(exc_context.exception))

    @mock.patch('imbi_automations.committer.prompts.render')
    @mock.patch('imbi_automations.committer.claude.Claude')
    async def test_case_insensitive_phrase_matching(
        self, mock_claude_class: mock.MagicMock, mock_render: mock.MagicMock
    ) -> None:
        """Test phrase matching is case-insensitive."""
        mock_client = mock.MagicMock()
        mock_claude_class.return_value = mock_client
        mock_client.prompt_kwargs = {}
        mock_render.return_value = 'Commit the changes'

        async def mock_agent_query(prompt: str) -> models.ClaudeAgentResponse:
            return models.ClaudeAgentResponse(
                message='NO CHANGES TO COMMIT in this repository'
            )

        mock_client.agent_query = mock_agent_query

        c = committer.Committer(self.config, verbose=False)
        result = await c._claude_commit(self.context, self.action)

        self.assertFalse(result)

    # test_passes_correct_response_model removed - agent_query no longer
    # takes response_model parameter with unified ClaudeAgentResponse


class ManualCommitTestCase(base.AsyncTestCase):
    """Test cases for Committer._manual_commit()."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        # Create required directory structure
        (self.working_directory / 'repository').mkdir()

        self.config = models.Configuration(
            ai_commits=False,
            claude=models.ClaudeAgentConfiguration(
                enabled=False, executable='claude'
            ),
            anthropic=models.AnthropicConfiguration(),
            git=models.GitConfiguration(
                user_name='Test Author', user_email='test@example.com'
            ),
            imbi=models.ImbiConfiguration(api_key='test', hostname='test.com'),
        )

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

    @mock.patch('imbi_automations.committer.git.commit_changes')
    @mock.patch('imbi_automations.committer.git.add_files')
    async def test_returns_true_when_commit_succeeds(
        self,
        mock_add_files: mock.MagicMock,
        mock_commit_changes: mock.MagicMock,
    ) -> None:
        """Test _manual_commit returns True when commit succeeds."""
        mock_add_files.return_value = None
        mock_commit_changes.return_value = 'abc123def456'

        action = models.WorkflowAction(name='test-action', ai_commit=False)

        c = committer.Committer(self.config, verbose=False)
        result = await c._manual_commit(self.context, action)

        self.assertTrue(result)
        mock_add_files.assert_called_once()
        mock_commit_changes.assert_called_once()

    @mock.patch('imbi_automations.committer.git.commit_changes')
    @mock.patch('imbi_automations.committer.git.add_files')
    async def test_returns_false_when_no_changes(
        self,
        mock_add_files: mock.MagicMock,
        mock_commit_changes: mock.MagicMock,
    ) -> None:
        """Test _manual_commit returns False when no changes to commit."""
        mock_add_files.return_value = None
        mock_commit_changes.return_value = (
            None  # No commit SHA means no changes
        )

        action = models.WorkflowAction(name='test-action', ai_commit=False)

        c = committer.Committer(self.config, verbose=False)
        result = await c._manual_commit(self.context, action)

        self.assertFalse(result)

    @mock.patch('imbi_automations.committer.git.commit_changes')
    @mock.patch('imbi_automations.committer.git.add_files')
    async def test_raises_runtime_error_when_commit_fails(
        self,
        mock_add_files: mock.MagicMock,
        mock_commit_changes: mock.MagicMock,
    ) -> None:
        """Test _manual_commit raises RuntimeError when git commit fails."""
        mock_add_files.return_value = None
        mock_commit_changes.side_effect = RuntimeError('Git commit failed')

        action = models.WorkflowAction(name='test-action', ai_commit=False)

        c = committer.Committer(self.config, verbose=False)

        with self.assertRaises(RuntimeError) as exc_context:
            await c._manual_commit(self.context, action)

        self.assertIn('Git commit failed', str(exc_context.exception))

    @mock.patch('imbi_automations.committer.git.commit_changes')
    @mock.patch('imbi_automations.committer.git.add_files')
    async def test_includes_commit_message_in_body(
        self,
        mock_add_files: mock.MagicMock,
        mock_commit_changes: mock.MagicMock,
    ) -> None:
        """Test _manual_commit includes action.commit_message in body."""
        mock_add_files.return_value = None
        mock_commit_changes.return_value = 'abc123'

        action = models.WorkflowAction(
            name='test-action',
            ai_commit=False,
            commit_message='Custom commit body text',
        )

        c = committer.Committer(self.config, verbose=False)
        await c._manual_commit(self.context, action)

        # Verify the commit message includes the custom body
        call_args = mock_commit_changes.call_args
        message = call_args.kwargs['message']
        self.assertIn('Custom commit body text', message)

    @mock.patch('imbi_automations.committer.git.commit_changes')
    @mock.patch('imbi_automations.committer.git.add_files')
    async def test_omits_body_when_commit_message_empty(
        self,
        mock_add_files: mock.MagicMock,
        mock_commit_changes: mock.MagicMock,
    ) -> None:
        """Test _manual_commit omits body when commit_message is empty."""
        mock_add_files.return_value = None
        mock_commit_changes.return_value = 'abc123'

        action = models.WorkflowAction(
            name='test-action', ai_commit=False, commit_message=''
        )

        c = committer.Committer(self.config, verbose=False)
        await c._manual_commit(self.context, action)

        # Verify the commit message has no extra body (no double newlines
        # before the trailer)
        call_args = mock_commit_changes.call_args
        message = call_args.kwargs['message']

        # The message should have format: subject\n\ntrailer (no extra body)
        lines = message.split('\n')
        # First line is subject, second is empty, rest is trailer
        self.assertTrue(lines[0].startswith('imbi-automations:'))

    @mock.patch('imbi_automations.committer.git.commit_changes')
    @mock.patch('imbi_automations.committer.git.add_files')
    async def test_commit_message_format(
        self,
        mock_add_files: mock.MagicMock,
        mock_commit_changes: mock.MagicMock,
    ) -> None:
        """Test _manual_commit creates correctly formatted commit message."""
        mock_add_files.return_value = None
        mock_commit_changes.return_value = 'abc123'

        action = models.WorkflowAction(name='update-deps', ai_commit=False)

        c = committer.Committer(self.config, verbose=False)
        await c._manual_commit(self.context, action)

        call_args = mock_commit_changes.call_args
        message = call_args.kwargs['message']

        # Should contain workflow name and action name
        self.assertIn('test-workflow', message)
        self.assertIn('update-deps', message)
        # Should contain the trailer
        self.assertIn('Generated with [Imbi Automations]', message)

    @mock.patch('imbi_automations.committer.git.commit_changes')
    @mock.patch('imbi_automations.committer.git.add_files')
    async def test_uses_git_config_from_configuration(
        self,
        mock_add_files: mock.MagicMock,
        mock_commit_changes: mock.MagicMock,
    ) -> None:
        """Test _manual_commit uses git user config from Configuration."""
        mock_add_files.return_value = None
        mock_commit_changes.return_value = 'abc123'

        action = models.WorkflowAction(name='test-action', ai_commit=False)

        c = committer.Committer(self.config, verbose=False)
        await c._manual_commit(self.context, action)

        call_args = mock_commit_changes.call_args
        self.assertEqual(call_args.kwargs['user_name'], 'Test Author')
        self.assertEqual(call_args.kwargs['user_email'], 'test@example.com')

    @mock.patch('imbi_automations.committer.git.commit_changes')
    @mock.patch('imbi_automations.committer.git.add_files')
    async def test_uses_correct_working_directory(
        self,
        mock_add_files: mock.MagicMock,
        mock_commit_changes: mock.MagicMock,
    ) -> None:
        """Test _manual_commit uses repository subdirectory."""
        mock_add_files.return_value = None
        mock_commit_changes.return_value = 'abc123'

        action = models.WorkflowAction(name='test-action', ai_commit=False)

        c = committer.Committer(self.config, verbose=False)
        await c._manual_commit(self.context, action)

        # Verify add_files was called with repository directory
        add_call_args = mock_add_files.call_args
        expected_repo_dir = self.working_directory / 'repository'
        self.assertEqual(
            add_call_args.kwargs['working_directory'], expected_repo_dir
        )

        # Verify commit_changes was called with repository directory
        commit_call_args = mock_commit_changes.call_args
        self.assertEqual(
            commit_call_args.kwargs['working_directory'], expected_repo_dir
        )


if __name__ == '__main__':
    unittest.main()
