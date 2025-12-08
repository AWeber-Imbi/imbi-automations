"""Tests for the git action module."""

import pathlib
import tempfile
import unittest
from unittest import mock

from imbi_automations import models
from imbi_automations.actions import git as git_actions
from tests import base


class GitActionsTestCase(base.AsyncTestCase):
    """Test cases for GitActions functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        # Create workflow and repository directories
        (self.working_directory / 'workflow').mkdir()
        (self.working_directory / 'repository').mkdir()
        (self.working_directory / 'extracted').mkdir()

        # Create workflow context
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
                facts=None,
                identifiers={'github': 'test-org/test-project'},
                links=None,
                name='Test Project',
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

        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-key'  # noqa: S106
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.git_executor = git_actions.GitActions(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch('imbi_automations.git.extract_file_from_commit')
    async def test_execute_extract_success(
        self, mock_extract: mock.AsyncMock
    ) -> None:
        """Test successful file extraction from git history."""
        mock_extract.return_value = True

        action = models.WorkflowGitAction(
            name='extract-config',
            type='git',
            command='extract',
            source='src/config.py',
            destination='extracted:///old-config.py',
            commit_keyword='BREAKING CHANGE',
            search_strategy='before_last_match',
        )

        await self.git_executor.execute(action)

        mock_extract.assert_called_once_with(
            working_directory=self.working_directory / 'repository',
            source_file=pathlib.Path('src/config.py'),
            destination_file=(
                self.working_directory / 'extracted' / 'old-config.py'
            ),
            commit_keyword='BREAKING CHANGE',
            search_strategy=(
                models.WorkflowGitActionCommitMatchStrategy.before_last_match
            ),
        )

    @mock.patch('imbi_automations.git.extract_file_from_commit')
    async def test_execute_extract_default_strategy(
        self, mock_extract: mock.AsyncMock
    ) -> None:
        """Test extract uses default search strategy when not specified."""
        mock_extract.return_value = True

        action = models.WorkflowGitAction(
            name='extract-file',
            type='git',
            command='extract',
            source='README.md',
            destination='extracted:///old-readme.md',
            commit_keyword='v1.0',
        )

        await self.git_executor.execute(action)

        mock_extract.assert_called_once()
        call_kwargs = mock_extract.call_args.kwargs
        self.assertEqual(call_kwargs['search_strategy'], 'before_last_match')

    @mock.patch('imbi_automations.git.extract_file_from_commit')
    async def test_execute_extract_failure_raises(
        self, mock_extract: mock.AsyncMock
    ) -> None:
        """Test extract raises error on failure when ignore_errors is False."""
        mock_extract.return_value = False

        action = models.WorkflowGitAction(
            name='extract-missing',
            type='git',
            command='extract',
            source='nonexistent.py',
            destination='extracted:///file.py',
            commit_keyword='some-keyword',
            ignore_errors=False,
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.git_executor.execute(action)

        self.assertIn('Git extraction failed', str(exc_context.exception))
        self.assertIn('nonexistent.py', str(exc_context.exception))

    @mock.patch('imbi_automations.git.extract_file_from_commit')
    async def test_execute_extract_failure_ignored(
        self, mock_extract: mock.AsyncMock
    ) -> None:
        """Test extract does not raise when ignore_errors is True."""
        mock_extract.return_value = False

        action = models.WorkflowGitAction(
            name='extract-optional',
            type='git',
            command='extract',
            source='optional-file.py',
            destination='extracted:///file.py',
            commit_keyword='some-keyword',
            ignore_errors=True,
        )

        # Should not raise
        await self.git_executor.execute(action)

        mock_extract.assert_called_once()

    @mock.patch('imbi_automations.git.extract_file_from_commit')
    async def test_execute_extract_before_first_match(
        self, mock_extract: mock.AsyncMock
    ) -> None:
        """Test extract with before_first_match strategy."""
        mock_extract.return_value = True

        action = models.WorkflowGitAction(
            name='extract-first',
            type='git',
            command='extract',
            source='src/main.py',
            destination='extracted:///main.py',
            commit_keyword='initial commit',
            search_strategy='before_first_match',
        )

        await self.git_executor.execute(action)

        call_kwargs = mock_extract.call_args.kwargs
        self.assertEqual(call_kwargs['search_strategy'], 'before_first_match')

    @mock.patch('imbi_automations.git.clone_to_directory')
    async def test_execute_clone_success(
        self, mock_clone: mock.AsyncMock
    ) -> None:
        """Test successful repository clone."""
        mock_clone.return_value = None

        action = models.WorkflowGitAction(
            name='clone-repo',
            type='git',
            command='clone',
            url='https://github.com/example/repo.git',
            destination='extracted:///external-repo',
            branch='main',
            depth=1,
        )

        await self.git_executor.execute(action)

        mock_clone.assert_called_once_with(
            working_directory=self.working_directory,
            clone_url='https://github.com/example/repo.git',
            destination=self.working_directory / 'extracted' / 'external-repo',
            branch='main',
            depth=1,
        )

    @mock.patch('imbi_automations.git.clone_to_directory')
    async def test_execute_clone_no_branch(
        self, mock_clone: mock.AsyncMock
    ) -> None:
        """Test clone without specifying branch."""
        mock_clone.return_value = None

        action = models.WorkflowGitAction(
            name='clone-default-branch',
            type='git',
            command='clone',
            url='git@github.com:example/repo.git',
            destination='extracted:///repo',
        )

        await self.git_executor.execute(action)

        call_kwargs = mock_clone.call_args.kwargs
        self.assertIsNone(call_kwargs['branch'])

    @mock.patch('imbi_automations.git.clone_to_directory')
    async def test_execute_clone_full_depth(
        self, mock_clone: mock.AsyncMock
    ) -> None:
        """Test clone with full history (no depth limit)."""
        mock_clone.return_value = None

        action = models.WorkflowGitAction(
            name='clone-full',
            type='git',
            command='clone',
            url='https://github.com/example/repo.git',
            destination='extracted:///full-repo',
            depth=None,
        )

        await self.git_executor.execute(action)

        call_kwargs = mock_clone.call_args.kwargs
        self.assertIsNone(call_kwargs['depth'])

    @mock.patch('imbi_automations.git.clone_to_directory')
    async def test_execute_clone_failure(
        self, mock_clone: mock.AsyncMock
    ) -> None:
        """Test clone raises error on failure."""
        mock_clone.side_effect = RuntimeError('Clone failed: access denied')

        action = models.WorkflowGitAction(
            name='clone-private',
            type='git',
            command='clone',
            url='git@github.com:private/repo.git',
            destination='extracted:///private-repo',
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.git_executor.execute(action)

        self.assertIn('Clone failed', str(exc_context.exception))


if __name__ == '__main__':
    unittest.main()
