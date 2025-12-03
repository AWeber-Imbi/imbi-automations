"""Tests for GitHub actions."""

import pathlib
import tempfile
from unittest import mock

import httpx

from imbi_automations import errors, models
from imbi_automations.actions import github
from tests import base


class GitHubActionsTestCase(base.AsyncTestCase):
    """Test cases for GitHubActions class."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        # Create mock workflow
        self.workflow = models.Workflow(
            path=pathlib.Path('/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

        # Create mock GitHub repository
        self.github_repository = mock.Mock(spec=models.GitHubRepository)
        self.github_repository.id = 12345
        self.github_repository.name = 'test-repo'
        self.github_repository.full_name = 'test-org/test-repo'
        self.github_repository.default_branch = 'main'

        # Create mock Imbi project
        self.imbi_project = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=[
                models.ImbiEnvironment(
                    name='Development', slug='development', icon_class='fa-dev'
                ),
                models.ImbiEnvironment(
                    name='Staging', slug='staging', icon_class='fa-stage'
                ),
                models.ImbiEnvironment(
                    name='Production', slug='production', icon_class='fa-prod'
                ),
            ],
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
        )

        # Create context with GitHub repository
        self.context = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=self.imbi_project,
            github_repository=self.github_repository,
            working_directory=self.working_directory,
        )

        # Create configuration
        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-key'  # noqa: S106
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        # Create GitHubActions instance
        self.github_actions = github.GitHubActions(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_sync_environments_success_create_and_delete(self) -> None:
        """Test successful environment sync with creates and deletes."""
        action = models.WorkflowGitHubAction(
            name='sync-envs',
            type='github',
            command=models.WorkflowGitHubCommand.sync_environments,
        )

        # Mock GitHub client
        mock_github_client = mock.AsyncMock()

        # Mock get_repository_environments - return GitHub with extra env
        mock_github_client.get_repository_environments.return_value = [
            models.GitHubEnvironment(
                id=1, name='development', created_at='2024-01-01T00:00:00Z'
            ),
            models.GitHubEnvironment(
                id=2, name='production', created_at='2024-01-01T00:00:00Z'
            ),
            models.GitHubEnvironment(
                id=3, name='old-env', created_at='2024-01-01T00:00:00Z'
            ),
        ]

        # Mock create and delete to succeed
        mock_github_client.create_environment.return_value = (
            models.GitHubEnvironment(
                id=4, name='staging', created_at='2024-01-01T00:00:00Z'
            )
        )
        mock_github_client.delete_environment.return_value = True

        # Patch GitHub client constructor
        with mock.patch(
            'imbi_automations.actions.github.clients.GitHub',
            return_value=mock_github_client,
        ):
            await self.github_actions.execute(action)

        # Verify calls
        mock_github_client.get_repository_environments.assert_called_once_with(
            'test-org', 'test-repo'
        )
        mock_github_client.create_environment.assert_called_once_with(
            'test-org', 'test-repo', 'staging'
        )
        mock_github_client.delete_environment.assert_called_once_with(
            'test-org', 'test-repo', 'old-env'
        )

    async def test_sync_environments_no_environments_in_imbi(self) -> None:
        """Test sync with None environments deletes all GitHub envs."""
        # Create context with no environments (None)
        imbi_project_no_envs = models.ImbiProject(
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
        )

        context_no_envs = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=imbi_project_no_envs,
            github_repository=self.github_repository,
            working_directory=self.working_directory,
        )

        github_actions_no_envs = github.GitHubActions(
            self.configuration, context_no_envs, verbose=True
        )

        action = models.WorkflowGitHubAction(
            name='sync-envs',
            type='github',
            command=models.WorkflowGitHubCommand.sync_environments,
        )

        # Mock GitHub client with existing environments
        mock_github_client = mock.AsyncMock()
        mock_github_client.get_repository_environments.return_value = [
            models.GitHubEnvironment(
                id=1, name='old-env', created_at='2024-01-01T00:00:00Z'
            )
        ]

        with mock.patch(
            'imbi_automations.actions.github.clients.GitHub',
            return_value=mock_github_client,
        ):
            await github_actions_no_envs.execute(action)

        # Should fetch environments and delete the existing one
        mock_github_client.get_repository_environments.assert_called_once()
        mock_github_client.delete_environment.assert_called_once_with(
            'test-org', 'test-repo', 'old-env'
        )
        mock_github_client.create_environment.assert_not_called()

    async def test_sync_environments_no_github_repository(self) -> None:
        """Test sync raises error when no GitHub repository in context."""
        # Create context without GitHub repository
        context_no_github = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=self.imbi_project,
            github_repository=None,
            working_directory=self.working_directory,
        )

        github_actions_no_repo = github.GitHubActions(
            self.configuration, context_no_github, verbose=True
        )

        action = models.WorkflowGitHubAction(
            name='sync-envs',
            type='github',
            command=models.WorkflowGitHubCommand.sync_environments,
        )

        with self.assertRaises(ValueError) as ctx:
            await github_actions_no_repo.execute(action)

        self.assertIn('No GitHub repository', str(ctx.exception))

    async def test_sync_environments_repository_not_found(self) -> None:
        """Test sync handles repository not found error."""
        action = models.WorkflowGitHubAction(
            name='sync-envs',
            type='github',
            command=models.WorkflowGitHubCommand.sync_environments,
        )

        # Mock GitHub client to raise not found error
        mock_github_client = mock.AsyncMock()
        mock_github_client.get_repository_environments.side_effect = (
            errors.GitHubNotFoundError('Repository not found')
        )

        with (
            mock.patch(
                'imbi_automations.actions.github.clients.GitHub',
                return_value=mock_github_client,
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            await self.github_actions.execute(action)

        self.assertIn('Environment sync failed', str(ctx.exception))
        self.assertIn(
            'Repository test-org/test-repo not found', str(ctx.exception)
        )

    async def test_sync_environments_http_error(self) -> None:
        """Test sync handles generic HTTP errors."""
        action = models.WorkflowGitHubAction(
            name='sync-envs',
            type='github',
            command=models.WorkflowGitHubCommand.sync_environments,
        )

        # Mock GitHub client to raise HTTP error
        mock_github_client = mock.AsyncMock()
        mock_github_client.get_repository_environments.side_effect = (
            httpx.HTTPStatusError(
                'Server error',
                request=mock.Mock(),
                response=mock.Mock(status_code=500),
            )
        )

        with (
            mock.patch(
                'imbi_automations.actions.github.clients.GitHub',
                return_value=mock_github_client,
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            await self.github_actions.execute(action)

        self.assertIn('Environment sync failed', str(ctx.exception))

    async def test_sync_environments_exact_match(self) -> None:
        """Test sync with exact slug matches (no creates/deletes)."""
        action = models.WorkflowGitHubAction(
            name='sync-envs',
            type='github',
            command=models.WorkflowGitHubCommand.sync_environments,
        )

        # Mock GitHub client with exact slug matches
        mock_github_client = mock.AsyncMock()
        mock_github_client.get_repository_environments.return_value = [
            models.GitHubEnvironment(
                id=1, name='development', created_at='2024-01-01T00:00:00Z'
            ),
            models.GitHubEnvironment(
                id=2, name='staging', created_at='2024-01-01T00:00:00Z'
            ),
            models.GitHubEnvironment(
                id=3, name='production', created_at='2024-01-01T00:00:00Z'
            ),
        ]

        with mock.patch(
            'imbi_automations.actions.github.clients.GitHub',
            return_value=mock_github_client,
        ):
            await self.github_actions.execute(action)

        # Should not create or delete (all match exactly)
        mock_github_client.create_environment.assert_not_called()
        mock_github_client.delete_environment.assert_not_called()

    async def test_sync_environments_partial_failure(self) -> None:
        """Test sync handles partial failures during create/delete."""
        action = models.WorkflowGitHubAction(
            name='sync-envs',
            type='github',
            command=models.WorkflowGitHubCommand.sync_environments,
        )

        # Mock GitHub client
        mock_github_client = mock.AsyncMock()
        mock_github_client.get_repository_environments.return_value = [
            models.GitHubEnvironment(
                id=1, name='old-env', created_at='2024-01-01T00:00:00Z'
            )
        ]

        # Mock delete to fail
        mock_github_client.delete_environment.side_effect = httpx.HTTPError(
            'Delete failed'
        )

        # Mock create to succeed
        mock_github_client.create_environment.return_value = (
            models.GitHubEnvironment(
                id=2, name='development', created_at='2024-01-01T00:00:00Z'
            )
        )

        with (
            mock.patch(
                'imbi_automations.actions.github.clients.GitHub',
                return_value=mock_github_client,
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            await self.github_actions.execute(action)

        self.assertIn('Environment sync failed', str(ctx.exception))

    async def test_sync_environments_empty_imbi_list(self) -> None:
        """Test sync with empty environments list deletes all GitHub envs."""
        # Create project with empty list (not None)
        imbi_project_empty = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=[],
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
        )

        context_empty = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=imbi_project_empty,
            github_repository=self.github_repository,
            working_directory=self.working_directory,
        )

        github_actions_empty = github.GitHubActions(
            self.configuration, context_empty, verbose=True
        )

        action = models.WorkflowGitHubAction(
            name='sync-envs',
            type='github',
            command=models.WorkflowGitHubCommand.sync_environments,
        )

        # Mock GitHub client with existing environments
        mock_github_client = mock.AsyncMock()
        mock_github_client.get_repository_environments.return_value = [
            models.GitHubEnvironment(
                id=1, name='old-env-1', created_at='2024-01-01T00:00:00Z'
            ),
            models.GitHubEnvironment(
                id=2, name='old-env-2', created_at='2024-01-01T00:00:00Z'
            ),
        ]

        with mock.patch(
            'imbi_automations.actions.github.clients.GitHub',
            return_value=mock_github_client,
        ):
            await github_actions_empty.execute(action)

        # Should fetch environments and delete all existing ones
        mock_github_client.get_repository_environments.assert_called_once()
        self.assertEqual(mock_github_client.delete_environment.call_count, 2)
        mock_github_client.create_environment.assert_not_called()

    async def test_execute_unsupported_command(self) -> None:
        """Test execute raises error for unsupported command."""
        # Create action with invalid command (using mock)
        action = mock.Mock(spec=models.WorkflowGitHubAction)
        action.command = 'invalid_command'
        action.name = 'test-action'

        with self.assertRaises(RuntimeError) as ctx:
            await self.github_actions.execute(action)

        self.assertIn('Unsupported command', str(ctx.exception))

    async def test_sync_environments_sorted_order(self) -> None:
        """Test environments are sorted alphabetically in logs."""
        # Create project with unsorted environments
        imbi_project_unsorted = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=[
                models.ImbiEnvironment(
                    name='Staging', slug='staging', icon_class='fa-stage'
                ),
                models.ImbiEnvironment(
                    name='Production', slug='production', icon_class='fa-prod'
                ),
                models.ImbiEnvironment(
                    name='Development', slug='development', icon_class='fa-dev'
                ),
            ],
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
        )

        context_unsorted = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=imbi_project_unsorted,
            github_repository=self.github_repository,
            working_directory=self.working_directory,
        )

        github_actions_unsorted = github.GitHubActions(
            self.configuration, context_unsorted, verbose=True
        )

        action = models.WorkflowGitHubAction(
            name='sync-envs',
            type='github',
            command=models.WorkflowGitHubCommand.sync_environments,
        )

        # Mock GitHub client
        mock_github_client = mock.AsyncMock()
        mock_github_client.get_repository_environments.return_value = []

        with mock.patch(
            'imbi_automations.actions.github.clients.GitHub',
            return_value=mock_github_client,
        ):
            await github_actions_unsorted.execute(action)

        # Verify the environments were sorted when passed to sync function
        # The call should have ['development', 'production', 'staging']
        # Check that create was called with sorted environments
        # (In this case, they should all be created since GitHub has none)
        self.assertEqual(mock_github_client.create_environment.call_count, 3)

        # Verify order by checking call arguments
        calls = mock_github_client.create_environment.call_args_list
        env_names = [
            call.args[2] if call.args else call.kwargs['env_name']
            for call in calls
        ]
        self.assertEqual(env_names, ['development', 'production', 'staging'])
