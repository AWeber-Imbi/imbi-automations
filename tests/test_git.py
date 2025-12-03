"""Comprehensive tests for the git module."""

import datetime
import pathlib
import tempfile
import unittest
from unittest import mock

from imbi_automations import git, models, workflow_engine
from tests import base


class GitModuleTestCase(base.AsyncTestCase):
    """Test cases for git module functions."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_clone_repository_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test successful repository cloning."""
        # First call: git clone, Second call: git rev-parse HEAD
        mock_run_git.side_effect = [
            (0, 'Cloning into repository...', ''),
            (0, 'abc1234567890abcdef\n', ''),
        ]

        result = await git.clone_repository(
            working_directory=self.working_directory,
            clone_url='https://github.com/test/repo.git',
            branch='main',
            depth=1,
        )

        # Should return the HEAD commit hash
        self.assertEqual(result, 'abc1234567890abcdef')

        # Verify both git commands were called
        self.assertEqual(mock_run_git.call_count, 2)

        # Verify git clone command was called correctly
        clone_call = mock_run_git.call_args_list[0]
        command = clone_call[0][0]

        self.assertEqual(command[0], 'git')
        self.assertEqual(command[1], 'clone')
        self.assertIn('--depth', command)
        self.assertIn('1', command)
        self.assertIn('--branch', command)
        self.assertIn('main', command)
        self.assertIn('https://github.com/test/repo.git', command)

        # Verify git rev-parse HEAD command was called
        rev_parse_call = mock_run_git.call_args_list[1]
        rev_parse_command = rev_parse_call[0][0]
        self.assertEqual(rev_parse_command, ['git', 'rev-parse', 'HEAD'])

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_clone_repository_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test repository cloning failure."""
        mock_run_git.return_value = (128, '', 'fatal: repository not found')

        with self.assertRaises(RuntimeError) as exc_context:
            await git.clone_repository(
                working_directory=self.working_directory,
                clone_url='https://github.com/test/nonexistent.git',
            )

        self.assertIn('Git clone failed', str(exc_context.exception))
        self.assertIn(
            'fatal: repository not found', str(exc_context.exception)
        )

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_clone_repository_no_branch_no_depth(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test repository cloning with no branch or depth specified."""
        # First call: git clone, Second call: git rev-parse HEAD
        mock_run_git.side_effect = [
            (0, 'Cloning into repository...', ''),
            (0, 'def5678901234567890\n', ''),
        ]

        result = await git.clone_repository(
            working_directory=self.working_directory,
            clone_url='https://github.com/test/repo.git',
        )

        # Should return the HEAD commit hash
        self.assertEqual(result, 'def5678901234567890')

        # Verify git clone command was called with default depth
        clone_call = mock_run_git.call_args_list[0]
        command = clone_call[0][0]

        # Default depth is 1, so should include --depth option
        self.assertIn('git', command)
        self.assertIn('clone', command)
        self.assertIn('--depth', command)
        self.assertIn('https://github.com/test/repo.git', command)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_clone_repository_rev_parse_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test repository cloning with rev-parse HEAD failure."""
        # First call: git clone succeeds, Second call: git rev-parse fails
        mock_run_git.side_effect = [
            (0, 'Cloning into repository...', ''),
            (128, '', 'fatal: not a git repository'),
        ]

        with self.assertRaises(RuntimeError) as exc_context:
            await git.clone_repository(
                working_directory=self.working_directory,
                clone_url='https://github.com/test/repo.git',
            )

        self.assertIn('Git rev-parse HEAD failed', str(exc_context.exception))

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_add_files_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test successful file addition to git."""
        mock_run_git.return_value = (0, '', '')

        await git.add_files(self.working_directory)

        mock_run_git.assert_called_once_with(
            ['git', 'add', '--all'],
            cwd=self.working_directory,
            timeout_seconds=60,
        )

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_add_files_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test file addition failure."""
        mock_run_git.return_value = (
            1,
            '',
            'fatal: pathspec did not match any files',
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await git.add_files(self.working_directory)

        self.assertIn('Git add failed', str(exc_context.exception))

    # Note: commit_changes has been moved to Claude-powered commits
    # These tests are removed as the function signature has changed

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_push_changes_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test successful git push."""
        mock_run_git.return_value = (0, 'Everything up-to-date', '')

        await git.push_changes(
            working_directory=self.working_directory,
            remote='origin',
            branch='main',
            force=True,
            set_upstream=True,
        )

        mock_run_git.assert_called_once()
        call_args = mock_run_git.call_args
        command = call_args[0][0]

        self.assertEqual(command[0], 'git')
        self.assertEqual(command[1], 'push')
        self.assertIn('--force', command)
        self.assertIn('--set-upstream', command)
        self.assertIn('origin', command)
        self.assertIn('main', command)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_push_changes_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test git push failure."""
        mock_run_git.return_value = (
            1,
            '',
            'fatal: unable to access repository',
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await git.push_changes(self.working_directory, 'origin')

        self.assertIn('Git push failed', str(exc_context.exception))

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_push_changes_imbi_automations_branch_force(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test that imbi-automations branches automatically use force push."""
        mock_run_git.return_value = (0, 'Everything up-to-date', '')

        await git.push_changes(
            working_directory=self.working_directory,
            remote='origin',
            branch='imbi-automations/test-workflow',
            set_upstream=True,
        )

        mock_run_git.assert_called_once()
        call_args = mock_run_git.call_args
        command = call_args[0][0]

        # Should automatically include --force for imbi-automations branches
        self.assertEqual(command[0], 'git')
        self.assertEqual(command[1], 'push')
        self.assertIn('--force', command)
        self.assertIn('--set-upstream', command)
        self.assertIn('origin', command)
        self.assertIn('imbi-automations/test-workflow', command)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_push_changes_regular_branch_no_force(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test that regular branches don't automatically use force push."""
        mock_run_git.return_value = (0, 'Everything up-to-date', '')

        await git.push_changes(
            working_directory=self.working_directory,
            remote='origin',
            branch='feature/regular-branch',
        )

        mock_run_git.assert_called_once()
        call_args = mock_run_git.call_args
        command = call_args[0][0]

        # Should NOT include --force for regular branches
        self.assertEqual(command[0], 'git')
        self.assertEqual(command[1], 'push')
        self.assertNotIn('--force', command)
        self.assertIn('origin', command)
        self.assertIn('feature/regular-branch', command)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_create_branch_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test successful branch creation."""
        mock_run_git.return_value = (0, 'Switched to a new branch', '')

        await git.create_branch(
            working_directory=self.working_directory,
            branch_name='feature/test',
            checkout=True,
        )

        mock_run_git.assert_called_once_with(
            ['git', 'checkout', '-b', 'feature/test'],
            cwd=self.working_directory,
            timeout_seconds=30,
        )

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_create_branch_no_checkout(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test branch creation without checkout."""
        mock_run_git.return_value = (0, '', '')

        await git.create_branch(
            working_directory=self.working_directory,
            branch_name='feature/test',
            checkout=False,
        )

        mock_run_git.assert_called_once_with(
            ['git', 'branch', 'feature/test'],
            cwd=self.working_directory,
            timeout_seconds=30,
        )

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_create_branch_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test branch creation failure."""
        mock_run_git.return_value = (128, '', 'fatal: branch already exists')

        with self.assertRaises(RuntimeError) as exc_context:
            await git.create_branch(self.working_directory, 'existing-branch')

        self.assertIn('Git branch creation failed', str(exc_context.exception))

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_current_branch_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test getting current branch name."""
        mock_run_git.return_value = (0, 'main\n', '')

        result = await git.get_current_branch(self.working_directory)

        self.assertEqual(result, 'main')
        mock_run_git.assert_called_once_with(
            ['git', 'branch', '--show-current'],
            cwd=self.working_directory,
            timeout_seconds=30,
        )

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_current_branch_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test get current branch failure."""
        mock_run_git.return_value = (128, '', 'fatal: not a git repository')

        with self.assertRaises(RuntimeError) as exc_context:
            await git.get_current_branch(self.working_directory)

        self.assertIn('Git branch query failed', str(exc_context.exception))

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commits_with_keyword_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _get_commits_with_keyword with successful results."""
        mock_stdout = (
            'abc1234 Fix: resolve issue with authentication\n'
            'def5678 feat: add new authentication feature\n'
        )
        mock_run_git.return_value = (0, mock_stdout, '')

        result = await git._get_commits_with_keyword(
            self.working_directory, 'auth'
        )

        expected = [
            ('abc1234', 'Fix: resolve issue with authentication'),
            ('def5678', 'feat: add new authentication feature'),
        ]
        self.assertEqual(result, expected)

        mock_run_git.assert_called_once_with(
            ['git', 'log', '--grep', 'auth', '--format=%H %s', '--all'],
            cwd=self.working_directory,
            timeout_seconds=30,
        )

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commits_with_keyword_no_matches(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _get_commits_with_keyword with no matches."""
        mock_run_git.return_value = (0, '', '')

        result = await git._get_commits_with_keyword(
            self.working_directory, 'nonexistent'
        )

        self.assertEqual(result, [])

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commits_with_keyword_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _get_commits_with_keyword with git command failure."""
        mock_run_git.return_value = (128, '', 'fatal: not a git repository')

        with self.assertRaises(RuntimeError) as exc_context:
            await git._get_commits_with_keyword(self.working_directory, 'test')

        self.assertIn('Git log failed', str(exc_context.exception))

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commits_with_keyword_malformed_output(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _get_commits_with_keyword with malformed git output."""
        # Test with lines that don't have proper format
        mock_stdout = 'abc1234\n\ndef5678 proper commit message\n  \n'
        mock_run_git.return_value = (0, mock_stdout, '')

        result = await git._get_commits_with_keyword(
            self.working_directory, 'test'
        )

        # Should only include properly formatted commits
        expected = [('def5678', 'proper commit message')]
        self.assertEqual(result, expected)

    def test_select_target_commit_before_last_match(self) -> None:
        """Test _select_target_commit with before_last_match strategy."""
        matching_commits = [
            ('newest123', 'Latest commit with keyword'),
            ('middle456', 'Middle commit with keyword'),
            ('oldest789', 'Oldest commit with keyword'),
        ]

        result = git._select_target_commit(
            matching_commits, 'before_last_match'
        )

        # Should return first in list (newest chronologically)
        self.assertEqual(result, 'newest123')

    def test_select_target_commit_before_first_match(self) -> None:
        """Test _select_target_commit with before_first_match strategy."""
        matching_commits = [
            ('newest123', 'Latest commit with keyword'),
            ('middle456', 'Middle commit with keyword'),
            ('oldest789', 'Oldest commit with keyword'),
        ]

        result = git._select_target_commit(
            matching_commits, 'before_first_match'
        )

        # Should return last in list (oldest chronologically)
        self.assertEqual(result, 'oldest789')

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_parent_commit_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _get_parent_commit with successful result."""
        mock_run_git.return_value = (0, 'parent123\n', '')

        result = await git._get_parent_commit(
            self.working_directory, 'child456'
        )

        self.assertEqual(result, 'parent123')
        mock_run_git.assert_called_once_with(
            ['git', 'rev-parse', 'child456^'],
            cwd=self.working_directory,
            timeout_seconds=30,
        )

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_parent_commit_no_parent(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _get_parent_commit with no parent (first commit)."""
        mock_run_git.return_value = (128, '', 'fatal: unknown revision')

        result = await git._get_parent_commit(
            self.working_directory, 'first123'
        )

        self.assertIsNone(result)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_parent_commit_other_error(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _get_parent_commit with other git error."""
        mock_run_git.return_value = (128, '', 'fatal: not a git repository')

        result = await git._get_parent_commit(
            self.working_directory, 'commit123'
        )

        self.assertIsNone(result)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_parent_commit_empty_output(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _get_parent_commit with empty output."""
        mock_run_git.return_value = (0, '  \n  ', '')

        result = await git._get_parent_commit(
            self.working_directory, 'commit123'
        )

        self.assertIsNone(result)

    @mock.patch('imbi_automations.git._get_commits_with_keyword')
    @mock.patch('imbi_automations.git._get_parent_commit')
    async def test_find_commit_before_keyword_success_last_match(
        self, mock_get_parent: mock.AsyncMock, mock_get_commits: mock.AsyncMock
    ) -> None:
        """Test find_commit_before_keyword with successful last match."""
        mock_get_commits.return_value = [
            ('newest123', 'Latest commit with BREAKING'),
            ('older456', 'Older commit with BREAKING'),
        ]
        mock_get_parent.return_value = 'parent789'

        result = await git.find_commit_before_keyword(
            self.working_directory, 'BREAKING', 'before_last_match'
        )

        self.assertEqual(result, 'parent789')
        mock_get_commits.assert_called_once_with(
            self.working_directory, 'BREAKING'
        )
        mock_get_parent.assert_called_once_with(
            self.working_directory, 'newest123'
        )

    @mock.patch('imbi_automations.git._get_commits_with_keyword')
    @mock.patch('imbi_automations.git._get_parent_commit')
    async def test_find_commit_before_keyword_success_first_match(
        self, mock_get_parent: mock.AsyncMock, mock_get_commits: mock.AsyncMock
    ) -> None:
        """Test find_commit_before_keyword with successful first match."""
        mock_get_commits.return_value = [
            ('newest123', 'Latest commit with BREAKING'),
            ('older456', 'Older commit with BREAKING'),
        ]
        mock_get_parent.return_value = 'parent789'

        result = await git.find_commit_before_keyword(
            self.working_directory, 'BREAKING', 'before_first_match'
        )

        self.assertEqual(result, 'parent789')
        mock_get_commits.assert_called_once_with(
            self.working_directory, 'BREAKING'
        )
        mock_get_parent.assert_called_once_with(
            self.working_directory, 'older456'
        )

    @mock.patch('imbi_automations.git._get_commits_with_keyword')
    async def test_find_commit_before_keyword_no_matches(
        self, mock_get_commits: mock.AsyncMock
    ) -> None:
        """Test find_commit_before_keyword with no keyword matches."""
        mock_get_commits.return_value = []

        result = await git.find_commit_before_keyword(
            self.working_directory, 'NONEXISTENT'
        )

        self.assertIsNone(result)
        mock_get_commits.assert_called_once_with(
            self.working_directory, 'NONEXISTENT'
        )

    @mock.patch('imbi_automations.git._get_commits_with_keyword')
    @mock.patch('imbi_automations.git._get_parent_commit')
    async def test_find_commit_before_keyword_no_parent(
        self, mock_get_parent: mock.AsyncMock, mock_get_commits: mock.AsyncMock
    ) -> None:
        """Test find_commit_before_keyword when target commit has no parent."""
        mock_get_commits.return_value = [
            ('first123', 'First commit with keyword')
        ]
        mock_get_parent.return_value = None

        result = await git.find_commit_before_keyword(
            self.working_directory, 'BREAKING'
        )

        self.assertIsNone(result)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_file_at_commit_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test successful file retrieval at commit."""
        mock_run_git.return_value = (0, 'file content\nat commit\n', '')

        result = await git.get_file_at_commit(
            self.working_directory, 'src/file.py', 'commit123'
        )

        self.assertEqual(result, 'file content\nat commit\n')
        mock_run_git.assert_called_once_with(
            ['git', 'show', 'commit123:src/file.py'],
            cwd=self.working_directory,
            timeout_seconds=30,
        )

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_file_at_commit_file_not_exists(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test file retrieval when file doesn't exist at commit."""
        mock_run_git.return_value = (128, '', 'fatal: path does not exist')

        result = await git.get_file_at_commit(
            self.working_directory, 'nonexistent.py', 'commit123'
        )

        self.assertIsNone(result)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_file_at_commit_git_error(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test file retrieval with git command error."""
        mock_run_git.return_value = (128, '', 'fatal: invalid commit hash')

        with self.assertRaises(RuntimeError) as exc_context:
            await git.get_file_at_commit(
                self.working_directory, 'file.py', 'invalid_hash'
            )

        self.assertIn('Git show failed', str(exc_context.exception))

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_delete_remote_branch_if_exists_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test successful remote branch deletion."""
        # First call: check if branch exists (returns non-empty)
        # Second call: delete branch
        mock_run_git.side_effect = [
            (0, 'refs/heads/feature-branch\n', ''),  # ls-remote
            (
                0,
                'To origin\n - [deleted]         feature-branch',
                '',
            ),  # push --delete
        ]

        result = await git.delete_remote_branch_if_exists(
            self.working_directory, 'feature-branch'
        )

        self.assertTrue(result)
        self.assertEqual(mock_run_git.call_count, 2)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_delete_remote_branch_if_exists_not_exists(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test remote branch deletion when branch doesn't exist."""
        mock_run_git.return_value = (0, '', '')  # ls-remote returns empty

        result = await git.delete_remote_branch_if_exists(
            self.working_directory, 'nonexistent-branch'
        )

        self.assertTrue(result)
        # Should only call ls-remote, not push --delete
        self.assertEqual(mock_run_git.call_count, 1)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_delete_remote_branch_if_exists_deletion_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test remote branch deletion failure."""
        mock_run_git.side_effect = [
            (0, 'refs/heads/feature-branch\n', ''),  # ls-remote success
            (1, '', 'error: unable to delete'),  # push --delete failure
        ]

        result = await git.delete_remote_branch_if_exists(
            self.working_directory, 'feature-branch'
        )

        self.assertFalse(result)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commit_messages_since_branch_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test successful commit message retrieval since branch."""
        mock_stdout = (
            'Add new feature\n'
            'Fix bug in authentication\n'
            'Update documentation\n'
        )
        mock_run_git.return_value = (0, mock_stdout, '')

        result = await git.get_commit_messages_since_branch(
            self.working_directory, 'main'
        )

        expected = [
            'Add new feature',
            'Fix bug in authentication',
            'Update documentation',
        ]
        self.assertEqual(result, expected)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commit_messages_since_branch_unknown_revision(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test commit message retrieval with unknown revision fallback."""
        # First call fails with unknown revision, second call succeeds
        mock_run_git.side_effect = [
            (128, '', 'fatal: bad revision unknown revision'),
            (0, 'Fallback commit message\n', ''),
        ]

        result = await git.get_commit_messages_since_branch(
            self.working_directory, 'nonexistent-branch'
        )

        expected = ['Fallback commit message']
        self.assertEqual(result, expected)
        self.assertEqual(mock_run_git.call_count, 2)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commit_messages_since_branch_no_commits(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test commit message retrieval with no commits."""
        mock_run_git.return_value = (0, '', '')

        result = await git.get_commit_messages_since_branch(
            self.working_directory, 'main'
        )

        self.assertEqual(result, [])

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commit_messages_since_branch_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test commit message retrieval with persistent failure."""
        mock_run_git.return_value = (128, '', 'fatal: not a git repository')

        with self.assertRaises(RuntimeError) as exc_context:
            await git.get_commit_messages_since_branch(
                self.working_directory, 'main'
            )

        self.assertIn('Git log failed', str(exc_context.exception))

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_run_git_command_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _run_git_command with successful execution."""
        # This tests the actual _run_git_command function directly
        mock_run_git.return_value = (0, 'success output', '')

        returncode, stdout, stderr = await git._run_git_command(
            ['git', 'status'], cwd=self.working_directory
        )

        self.assertEqual(returncode, 0)
        self.assertEqual(stdout, 'success output')
        self.assertEqual(stderr, '')

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_run_git_command_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test _run_git_command with command failure."""
        mock_run_git.return_value = (1, '', 'error output')

        returncode, stdout, stderr = await git._run_git_command(
            ['git', 'invalid-command'], cwd=self.working_directory
        )

        self.assertEqual(returncode, 1)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, 'error output')


class GitCommitHistoryTestCase(base.AsyncTestCase):
    """Test cases for git commit history functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        self.repository_dir = self.working_directory / 'repository'
        self.repository_dir.mkdir()

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch('imbi_automations.git._get_current_head_commit')
    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commits_since_with_new_commits(
        self, mock_run_git: mock.AsyncMock, mock_get_head: mock.AsyncMock
    ) -> None:
        """Test get_commits_since with new commits."""
        mock_get_head.return_value = 'newcommit123'

        # Mock git log output with commits and file changes
        commit1_line = (
            'abc123|John Doe|john@example.com|John Doe|john@example.com|'
            '1640995200|1640995200|Add new feature|Initial implementation'
        )
        commit2_line = (
            'def456|Jane Smith|jane@example.com|Jane Smith|jane@example.com|'
            '1640995260|1640995260|Fix bug in authentication|Bug fix'
        )
        mock_stdout = (
            f'{commit1_line}\n'
            'M\tsrc/feature.py\n'
            'A\ttests/test_feature.py\n'
            '\n'
            f'{commit2_line}\n'
            'Fixes: #123\n'
            'Co-authored-by: Bob <bob@example.com>\n'
            'M\tsrc/auth.py\n'
            'D\told_auth.py\n'
        )
        # Setup mock responses: git log, then git show for each commit
        mock_run_git.side_effect = [
            (0, mock_stdout, ''),  # git log
            (0, 'diff content for abc123', ''),  # git show abc123
            (0, 'diff content for def456', ''),  # git show def456
        ]

        result = await git.get_commits_since(
            self.repository_dir, 'startcommit789'
        )

        # Verify git commands were called correctly
        self.assertEqual(mock_run_git.call_count, 3)

        # First call should be git log
        log_call = mock_run_git.call_args_list[0]
        self.assertEqual(
            log_call[0][0],
            [
                'git',
                'log',
                'startcommit789..HEAD',
                '--pretty=format:%H|%an|%ae|%cn|%ce|%at|%ct|%s|%b',
                '--name-status',
            ],
        )

        # Verify summary data
        self.assertEqual(result.total_commits, 2)
        self.assertEqual(result.commit_range, 'startcommit789..newcommit123')
        self.assertEqual(
            result.files_affected,
            [
                'src/feature.py',
                'tests/test_feature.py',
                'src/auth.py',
                'old_auth.py',
            ],
        )

        # Verify first commit
        commit1 = result.commits[0]
        self.assertEqual(commit1.hash, 'abc123')
        self.assertEqual(commit1.author_name, 'John Doe')
        self.assertEqual(commit1.author_email, 'john@example.com')
        self.assertEqual(commit1.subject, 'Add new feature')
        self.assertEqual(commit1.body, 'Initial implementation')
        self.assertEqual(len(commit1.files_changed), 2)

        # Check file changes for first commit
        self.assertEqual(commit1.files_changed[0].status, 'M')
        self.assertEqual(commit1.files_changed[0].file_path, 'src/feature.py')
        self.assertEqual(commit1.files_changed[1].status, 'A')
        self.assertEqual(
            commit1.files_changed[1].file_path, 'tests/test_feature.py'
        )

        # Verify second commit
        commit2 = result.commits[1]
        self.assertEqual(commit2.hash, 'def456')
        self.assertEqual(commit2.subject, 'Fix bug in authentication')
        self.assertEqual(commit2.trailers['Fixes'], '#123')
        self.assertEqual(
            commit2.trailers['Co-authored-by'], 'Bob <bob@example.com>'
        )

    @mock.patch('imbi_automations.git._get_current_head_commit')
    async def test_get_commits_since_no_new_commits(
        self, mock_get_head: mock.AsyncMock
    ) -> None:
        """Test get_commits_since when no new commits exist."""
        # HEAD is same as starting commit
        mock_get_head.return_value = 'samecommit123'

        result = await git.get_commits_since(
            self.repository_dir, 'samecommit123'
        )

        self.assertEqual(result.total_commits, 0)
        self.assertEqual(result.commits, [])
        self.assertEqual(result.files_affected, [])
        self.assertEqual(result.commit_range, 'samecommit123..samecommit123')

    @mock.patch('imbi_automations.git._get_current_head_commit')
    @mock.patch('imbi_automations.git._run_git_command')
    async def test_get_commits_since_git_log_failure(
        self, mock_run_git: mock.AsyncMock, mock_get_head: mock.AsyncMock
    ) -> None:
        """Test get_commits_since with git log failure."""
        mock_get_head.return_value = 'newcommit123'
        mock_run_git.return_value = (128, '', 'fatal: bad revision')

        with self.assertRaises(RuntimeError) as exc_context:
            await git.get_commits_since(self.repository_dir, 'badcommit')

        self.assertIn('Git log failed', str(exc_context.exception))

    def test_parse_commit_body_and_trailers_with_trailers(self) -> None:
        """Test parsing commit body with trailers."""
        body = (
            'This is the commit body\n'
            'with multiple lines\n'
            '\n'
            'Fixes: #123\n'
            'Co-authored-by: Bob <bob@example.com>\n'
            'Signed-off-by: Alice <alice@example.com>'
        )

        commit_body, trailers = git._parse_commit_body_and_trailers(body)

        expected_body = 'This is the commit body\nwith multiple lines'
        expected_trailers = {
            'Fixes': '#123',
            'Co-authored-by': 'Bob <bob@example.com>',
            'Signed-off-by': 'Alice <alice@example.com>',
        }

        self.assertEqual(commit_body, expected_body)
        self.assertEqual(trailers, expected_trailers)

    def test_parse_commit_body_and_trailers_no_trailers(self) -> None:
        """Test parsing commit body without trailers."""
        body = 'Simple commit message\nwith no trailers'

        commit_body, trailers = git._parse_commit_body_and_trailers(body)

        self.assertEqual(
            commit_body, 'Simple commit message\nwith no trailers'
        )
        self.assertEqual(trailers, {})

    def test_parse_commit_body_and_trailers_empty(self) -> None:
        """Test parsing empty commit body."""
        commit_body, trailers = git._parse_commit_body_and_trailers('')

        self.assertEqual(commit_body, '')
        self.assertEqual(trailers, {})

    def test_parse_file_change_line_modified(self) -> None:
        """Test parsing modified file change line."""
        result = git._parse_file_change_line('M\tsrc/config.py')

        self.assertEqual(result.status, 'M')
        self.assertEqual(result.file_path, 'src/config.py')
        self.assertIsNone(result.old_path)

    def test_parse_file_change_line_added(self) -> None:
        """Test parsing added file change line."""
        result = git._parse_file_change_line('A\tnew_file.txt')

        self.assertEqual(result.status, 'A')
        self.assertEqual(result.file_path, 'new_file.txt')
        self.assertIsNone(result.old_path)

    def test_parse_file_change_line_renamed(self) -> None:
        """Test parsing renamed file change line."""
        result = git._parse_file_change_line('R100\told_name.py\tnew_name.py')

        self.assertEqual(result.status, 'R100')
        self.assertEqual(result.file_path, 'new_name.py')
        self.assertEqual(result.old_path, 'old_name.py')

    def test_parse_file_change_line_invalid(self) -> None:
        """Test parsing invalid file change line."""
        result = git._parse_file_change_line('invalid_line')

        self.assertIsNone(result)

    def test_parse_file_change_line_empty(self) -> None:
        """Test parsing empty file change line."""
        result = git._parse_file_change_line('')

        self.assertIsNone(result)

    def test_parse_diff_output_single_file(self) -> None:
        """Test parsing diff output for a single file."""
        diff_output = (
            'diff --git a/src/config.py b/src/config.py\n'
            'index abc123..def456 100644\n'
            '--- a/src/config.py\n'
            '+++ b/src/config.py\n'
            '@@ -1,3 +1,4 @@\n'
            ' import os\n'
            ' \n'
            '+NEW_SETTING = True\n'
            ' def get_config():\n'
        )

        result = git._parse_diff_output(diff_output)

        self.assertIn('src/config.py', result)
        self.assertIn(
            'diff --git a/src/config.py b/src/config.py',
            result['src/config.py'],
        )
        self.assertIn('+NEW_SETTING = True', result['src/config.py'])

    def test_parse_diff_output_multiple_files(self) -> None:
        """Test parsing diff output for multiple files."""
        diff_output = (
            'diff --git a/file1.py b/file1.py\n'
            'index abc123..def456 100644\n'
            '--- a/file1.py\n'
            '+++ b/file1.py\n'
            '@@ -1,1 +1,2 @@\n'
            ' print("hello")\n'
            '+print("world")\n'
            'diff --git a/file2.py b/file2.py\n'
            'index ghi789..jkl012 100644\n'
            '--- a/file2.py\n'
            '+++ b/file2.py\n'
            '@@ -1,1 +1,1 @@\n'
            '-old_code()\n'
            '+new_code()\n'
        )

        result = git._parse_diff_output(diff_output)

        self.assertEqual(len(result), 2)
        self.assertIn('file1.py', result)
        self.assertIn('file2.py', result)
        self.assertIn('+print("world")', result['file1.py'])
        self.assertIn('+new_code()', result['file2.py'])
        self.assertIn('-old_code()', result['file2.py'])

    def test_parse_diff_output_empty(self) -> None:
        """Test parsing empty diff output."""
        result = git._parse_diff_output('')
        self.assertEqual(result, {})

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_add_diffs_to_commit_success(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test adding diffs to commit file changes."""
        # Mock diff output
        diff_output = (
            'diff --git a/src/config.py b/src/config.py\n'
            'index abc123..def456 100644\n'
            '--- a/src/config.py\n'
            '+++ b/src/config.py\n'
            '@@ -1,3 +1,4 @@\n'
            ' import os\n'
            '+NEW_SETTING = True\n'
        )
        mock_run_git.return_value = (0, diff_output, '')

        # Create a commit with file changes
        commit = models.GitCommit(
            hash='abc123',
            author_name='Test',
            author_email='test@example.com',
            committer_name='Test',
            committer_email='test@example.com',
            author_date=datetime.datetime.now(datetime.UTC),
            commit_date=datetime.datetime.now(datetime.UTC),
            subject='Test commit',
            body='',
            trailers={},
            files_changed=[
                models.GitFileChange(status='M', file_path='src/config.py')
            ],
        )

        await git._add_diffs_to_commit(self.repository_dir, commit)

        # Verify git show command was called
        mock_run_git.assert_called_once_with(
            ['git', 'show', '--format=', 'abc123'],
            cwd=self.repository_dir,
            timeout_seconds=60,
        )

        # Verify diff was added to file change
        self.assertIsNotNone(commit.files_changed[0].diff)
        self.assertIn(
            'diff --git a/src/config.py b/src/config.py',
            commit.files_changed[0].diff,
        )
        self.assertIn('+NEW_SETTING = True', commit.files_changed[0].diff)

    @mock.patch('imbi_automations.git._run_git_command')
    async def test_add_diffs_to_commit_failure(
        self, mock_run_git: mock.AsyncMock
    ) -> None:
        """Test adding diffs to commit when git show fails."""
        mock_run_git.return_value = (128, '', 'fatal: bad object')

        commit = models.GitCommit(
            hash='badcommit',
            author_name='Test',
            author_email='test@example.com',
            committer_name='Test',
            committer_email='test@example.com',
            author_date=datetime.datetime.now(datetime.UTC),
            commit_date=datetime.datetime.now(datetime.UTC),
            subject='Test commit',
            body='',
            trailers={},
            files_changed=[
                models.GitFileChange(status='M', file_path='src/config.py')
            ],
        )

        # Should not raise, but should log warning
        await git._add_diffs_to_commit(self.repository_dir, commit)

        # Diff should remain None
        self.assertIsNone(commit.files_changed[0].diff)

    async def test_add_diffs_to_commit_no_files(self) -> None:
        """Test adding diffs to commit with no file changes."""
        commit = models.GitCommit(
            hash='abc123',
            author_name='Test',
            author_email='test@example.com',
            committer_name='Test',
            committer_email='test@example.com',
            author_date=datetime.datetime.now(datetime.UTC),
            commit_date=datetime.datetime.now(datetime.UTC),
            subject='Test commit',
            body='',
            trailers={},
            files_changed=[],  # No files changed
        )

        # Should return early without making git calls
        await git._add_diffs_to_commit(self.repository_dir, commit)
        # No assertions needed, just verify it doesn't crash


class GitExtractTestCase(base.AsyncTestCase):
    """Test cases for git.extract_file_from_commit functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        self.repository_dir = self.working_directory / 'repository'
        self.repository_dir.mkdir()

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch('imbi_automations.git.find_commit_before_keyword')
    @mock.patch('imbi_automations.git.get_file_at_commit')
    async def test_extract_file_from_commit_with_keyword_success(
        self, mock_get_file: mock.AsyncMock, mock_find_commit: mock.AsyncMock
    ) -> None:
        """Test successful file extraction with commit keyword."""
        mock_find_commit.return_value = 'abc1234567890'
        mock_get_file.return_value = 'extracted file content\nline 2\n'

        source_file = pathlib.Path('src/config.py')
        destination_file = self.working_directory / 'extracted/old-config.py'

        await git.extract_file_from_commit(
            working_directory=self.repository_dir,
            source_file=source_file,
            destination_file=destination_file,
            commit_keyword='BREAKING CHANGE',
            search_strategy='before_last_match',
        )

        # Verify git operations were called correctly
        mock_find_commit.assert_called_once_with(
            self.repository_dir, 'BREAKING CHANGE', 'before_last_match'
        )

        mock_get_file.assert_called_once_with(
            self.repository_dir, 'src/config.py', 'abc1234567890'
        )

        # Verify file was written to destination
        self.assertTrue(destination_file.exists())
        content = destination_file.read_text()
        self.assertEqual(content, 'extracted file content\nline 2\n')

    @mock.patch('imbi_automations.git.find_commit_before_keyword')
    async def test_extract_file_from_commit_no_commit_found(
        self, mock_find_commit: mock.AsyncMock
    ) -> None:
        """Test file extraction when no commit found for keyword."""
        mock_find_commit.return_value = None

        source_file = pathlib.Path('src/config.py')
        destination_file = self.working_directory / 'extracted/old-config.py'

        with self.assertRaises(RuntimeError) as exc_context:
            await git.extract_file_from_commit(
                working_directory=self.repository_dir,
                source_file=source_file,
                destination_file=destination_file,
                commit_keyword='NONEXISTENT',
                search_strategy='before_first_match',
            )

        self.assertIn(
            'No commit found before keyword "NONEXISTENT"',
            str(exc_context.exception),
        )
        self.assertIn(
            'using strategy "before_first_match"', str(exc_context.exception)
        )

    @mock.patch('imbi_automations.git.get_file_at_commit')
    async def test_extract_file_from_commit_no_keyword_uses_head(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test file extraction without keyword uses HEAD commit."""
        mock_get_file.return_value = 'current file content\n'

        source_file = pathlib.Path('README.md')
        destination_file = (
            self.working_directory / 'extracted/current-readme.md'
        )

        await git.extract_file_from_commit(
            working_directory=self.repository_dir,
            source_file=source_file,
            destination_file=destination_file,
            # No commit_keyword specified
        )

        # Should use HEAD commit
        mock_get_file.assert_called_once_with(
            self.repository_dir, 'README.md', 'HEAD'
        )

        # Verify file was written
        self.assertTrue(destination_file.exists())
        self.assertEqual(
            destination_file.read_text(), 'current file content\n'
        )

    @mock.patch('imbi_automations.git.find_commit_before_keyword')
    @mock.patch('imbi_automations.git.get_file_at_commit')
    async def test_extract_file_from_commit_file_not_found(
        self, mock_get_file: mock.AsyncMock, mock_find_commit: mock.AsyncMock
    ) -> None:
        """Test file extraction when file doesn't exist at target commit."""
        mock_find_commit.return_value = 'abc1234567890'
        mock_get_file.return_value = None  # File doesn't exist

        source_file = pathlib.Path('nonexistent.txt')
        destination_file = self.working_directory / 'extracted/file.txt'

        result = await git.extract_file_from_commit(
            working_directory=self.repository_dir,
            source_file=source_file,
            destination_file=destination_file,
            commit_keyword='BREAKING CHANGE',
        )

        self.assertFalse(result)

    @mock.patch('imbi_automations.git.get_file_at_commit')
    async def test_extract_file_from_commit_file_not_found_at_head(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test file extraction when file doesn't exist at HEAD commit."""
        mock_get_file.return_value = None  # File doesn't exist

        source_file = pathlib.Path('missing.txt')
        destination_file = self.working_directory / 'extracted/file.txt'

        result = await git.extract_file_from_commit(
            working_directory=self.repository_dir,
            source_file=source_file,
            destination_file=destination_file,
            # No commit_keyword, so uses HEAD
        )

        self.assertFalse(result)

    @mock.patch('imbi_automations.git.find_commit_before_keyword')
    @mock.patch('imbi_automations.git.get_file_at_commit')
    async def test_extract_file_from_commit_creates_destination_directory(
        self, mock_get_file: mock.AsyncMock, mock_find_commit: mock.AsyncMock
    ) -> None:
        """Test file extraction creates destination directory."""
        mock_find_commit.return_value = 'abc1234567890'
        mock_get_file.return_value = 'file content\n'

        source_file = pathlib.Path('src/deep/file.py')
        destination_file = (
            self.working_directory / 'extracted/nested/deep/file.py'
        )

        # Ensure nested directory doesn't exist initially
        nested_dir = self.working_directory / 'extracted/nested/deep'
        self.assertFalse(nested_dir.exists())

        await git.extract_file_from_commit(
            working_directory=self.repository_dir,
            source_file=source_file,
            destination_file=destination_file,
            commit_keyword='BREAKING CHANGE',
        )

        # Verify nested directory was created
        self.assertTrue(nested_dir.exists())

        # Verify file was written to nested location
        self.assertTrue(destination_file.exists())
        self.assertEqual(destination_file.read_text(), 'file content\n')

    @mock.patch('imbi_automations.git.find_commit_before_keyword')
    @mock.patch('imbi_automations.git.get_file_at_commit')
    async def test_extract_file_from_commit_uses_default_strategy(
        self, mock_get_file: mock.AsyncMock, mock_find_commit: mock.AsyncMock
    ) -> None:
        """Test file extraction uses default strategy when not specified."""
        mock_find_commit.return_value = 'abc1234567890'
        mock_get_file.return_value = 'file content\n'

        source_file = pathlib.Path('config.json')
        destination_file = self.working_directory / 'extracted/config.json'

        await git.extract_file_from_commit(
            working_directory=self.repository_dir,
            source_file=source_file,
            destination_file=destination_file,
            commit_keyword='BREAKING CHANGE',
            # No search_strategy specified - should use default
        )

        # Should use default strategy 'before_last_match'
        mock_find_commit.assert_called_once_with(
            self.repository_dir, 'BREAKING CHANGE', 'before_last_match'
        )


class WorkflowEngineGitTestCase(base.AsyncTestCase):
    """Test cases for WorkflowEngine git action integration."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        # Create required directory structure
        (self.working_directory / 'repository').mkdir()
        (self.working_directory / 'extracted').mkdir()

        # Create mock configuration
        self.config = models.Configuration(
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.test.com'
            ),
            github=models.GitHubConfiguration(
                token='test-github-key',  # noqa: S106
                host='github.com',
            ),
            claude=models.ClaudeAgentConfiguration(enabled=False),
        )

        # Create mock workflow
        self.workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[],
                github=models.WorkflowGitHub(create_pull_request=False),
            ),
        )

        # Create mock context
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

        # Create engine instance
        self.engine = workflow_engine.WorkflowEngine(
            config=self.config, workflow=self.workflow
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch('imbi_automations.git.extract_file_from_commit')
    async def test_execute_action_git_extract_integration(
        self, mock_extract: mock.AsyncMock
    ) -> None:
        """Test integration of git action with extract command."""
        action = models.WorkflowGitAction(
            name='extract-integration',
            type='git',
            command='extract',
            source=pathlib.Path('test.txt'),
            destination=pathlib.Path('extracted/test.txt'),
            commit_keyword='TEST',
            search_strategy='before_first_match',
        )

        await self.engine.actions.execute(self.context, action)

        # Verify git.extract_file_from_commit was called correctly
        mock_extract.assert_called_once_with(
            working_directory=self.working_directory / 'repository',
            source_file=pathlib.Path('test.txt'),
            destination_file=self.working_directory / 'extracted/test.txt',
            commit_keyword='TEST',
            search_strategy=models.WorkflowGitActionCommitMatchStrategy.before_first_match,
        )

    @mock.patch('imbi_automations.git.extract_file_from_commit')
    async def test_execute_action_git_extract_no_strategy(
        self, mock_extract: mock.AsyncMock
    ) -> None:
        """Test git extract action with default strategy."""
        action = models.WorkflowGitAction(
            name='extract-default',
            type='git',
            command='extract',
            source=pathlib.Path('config.py'),
            destination=pathlib.Path('extracted/config.py'),
            commit_keyword='BREAKING',
            # No search_strategy specified
        )

        await self.engine.actions.execute(self.context, action)

        # Should use default strategy
        mock_extract.assert_called_once_with(
            working_directory=self.working_directory / 'repository',
            source_file=pathlib.Path('config.py'),
            destination_file=self.working_directory / 'extracted/config.py',
            commit_keyword='BREAKING',
            search_strategy='before_last_match',
        )


if __name__ == '__main__':
    unittest.main()
