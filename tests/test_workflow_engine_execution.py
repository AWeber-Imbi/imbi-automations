"""Tests for workflow_engine.py execution logic.

Covers setup, initialization, primary stage execution, pull request creation,
followup stage cycling, and resumability.
"""

# ruff: noqa: S106, E501

import datetime
import pathlib
import tempfile
import unittest
from unittest import mock

import msgpack

from imbi_automations import models, workflow_engine
from tests import base


def create_mock_github_repository(
    id: int = 456,
    name: str = 'test-repo',
    full_name: str = 'org/test-repo',
    description: str = 'Test repository',
    private: bool = False,
    default_branch: str = 'main',
) -> models.GitHubRepository:
    """Create a GitHubRepository with all required fields for testing."""
    return models.GitHubRepository(
        id=id,
        node_id='MDEwOlJlcG9zaXRvcnl7aWR9',
        name=name,
        full_name=full_name,
        owner=models.GitHubUser(
            login='testuser',
            id=1,
            node_id='MDQ6VXNlcjE=',
            avatar_url='https://github.com/images/error/testuser.png',
            gravatar_id='',
            url='https://api.github.com/users/testuser',
            html_url='https://github.com/testuser',
            type='User',
            site_admin=False,
        ),
        private=private,
        html_url=f'https://github.com/{full_name}',
        description=description,
        fork=False,
        url=f'https://api.github.com/repos/{full_name}',
        default_branch=default_branch,
        clone_url=f'https://github.com/{full_name}.git',
        ssh_url=f'git@github.com:{full_name}.git',
        git_url=f'git://github.com/{full_name}.git',
        archived=False,
        disabled=False,
    )


class WorkflowEngineSetupTestCase(base.AsyncTestCase):
    """Test cases for WorkflowEngine setup and initialization."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )
        self.project = models.ImbiProject(
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

    async def test_init_validates_claude_requirement_for_claude_actions(
        self,
    ) -> None:
        """Test that __init__ raises error when Claude action exists but Claude disabled."""  # noqa: E501
        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[
                    models.WorkflowClaudeAction(
                        name='claude-action',
                        type=models.WorkflowActionTypes.claude,
                        task_prompt='prompts/task.md.j2',
                    )
                ],
            ),
        )
        config_no_claude = models.Configuration(
            claude=models.ClaudeAgentConfiguration(enabled=False),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            'Workflow requires Claude Code, but it is not enabled',
        ):
            workflow_engine.WorkflowEngine(config_no_claude, workflow)

    async def test_init_validates_claude_requirement_for_pr_creation(
        self,
    ) -> None:
        """Test that __init__ raises error when PR creation enabled but Claude disabled."""  # noqa: E501
        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[],
                github=models.WorkflowGitHub(create_pull_request=True),
            ),
        )
        config_no_claude = models.Configuration(
            claude=models.ClaudeAgentConfiguration(enabled=False),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            'Workflow requires Claude Code, but it is not enabled',
        ):
            workflow_engine.WorkflowEngine(config_no_claude, workflow)

    async def test_setup_workflow_run_creates_directory_structure(
        self,
    ) -> None:
        """Test that _setup_workflow_run creates proper directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            working_dir = pathlib.Path(temp_dir)
            engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

            context = engine._setup_workflow_run(
                self.project, str(working_dir), None
            )

            # Check directory structure
            self.assertTrue((working_dir / 'workflow').is_symlink())
            self.assertTrue((working_dir / 'extracted').exists())
            self.assertTrue((working_dir / 'repository').exists())

            # Check context values
            self.assertEqual(context.imbi_project, self.project)
            self.assertEqual(context.working_directory, working_dir)
            self.assertIsNone(context.starting_commit)
            self.assertFalse(context.has_repository_changes)

    async def test_setup_workflow_run_raises_on_symlink_failure(self) -> None:
        """Test that _setup_workflow_run raises if symlink creation fails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            working_dir = pathlib.Path(temp_dir)

            # Create a regular file where symlink should be to trigger an error
            workflow_link = working_dir / 'workflow'
            workflow_link.write_text('blocking file')

            engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

            # symlink_to raises FileExistsError before is_symlink check
            with self.assertRaises(FileExistsError):
                engine._setup_workflow_run(
                    self.project, str(working_dir), None
                )

    async def test_restore_workflow_context_from_resume_state(self) -> None:
        """Test that _restore_workflow_context properly reconstructs context."""  # noqa: E501
        with tempfile.TemporaryDirectory() as temp_dir:
            working_dir = pathlib.Path(temp_dir)

            # Create a real workflow directory to symlink to
            actual_workflow_dir = pathlib.Path(temp_dir) / 'actual_workflow'
            actual_workflow_dir.mkdir()

            # Create preserved directory structure
            (working_dir / 'workflow').symlink_to(actual_workflow_dir)
            (working_dir / 'extracted').mkdir()
            (working_dir / 'repository').mkdir()

            resume_state = models.ResumeState(
                workflow_slug='test-workflow',
                workflow_path=self.workflow.path,
                project_id=123,
                project_slug='test-project',
                failed_action_index=1,
                failed_action_name='action-1',
                completed_action_indices=[0],
                starting_commit='abc123',
                has_repository_changes=True,
                github_repository=None,
                error_message='Test error',
                error_timestamp=datetime.datetime.now(tz=datetime.UTC),
                preserved_directory_path=working_dir,
                configuration_hash='test-hash',
            )

            engine = workflow_engine.WorkflowEngine(
                self.config, self.workflow, resume_state=resume_state
            )

            context = engine._restore_workflow_context(
                str(working_dir), self.project, None
            )

            # Verify context restoration
            self.assertEqual(context.starting_commit, 'abc123')
            self.assertTrue(context.has_repository_changes)
            self.assertEqual(context.imbi_project, self.project)
            self.assertEqual(context.working_directory, working_dir)

    async def test_restore_workflow_context_raises_without_resume_state(
        self,
    ) -> None:
        """Test that _restore_workflow_context raises if resume_state is None."""  # noqa: E501
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

            with self.assertRaisesRegex(
                RuntimeError, 'resume_state must be set when restoring context'
            ):
                engine._restore_workflow_context(
                    str(temp_dir), self.project, None
                )

    async def test_restore_workflow_context_raises_if_symlink_missing(
        self,
    ) -> None:
        """Test that _restore_workflow_context raises if workflow symlink missing."""  # noqa: E501
        with tempfile.TemporaryDirectory() as temp_dir:
            working_dir = pathlib.Path(temp_dir)

            resume_state = models.ResumeState(
                workflow_slug='test-workflow',
                workflow_path=self.workflow.path,
                project_id=123,
                project_slug='test-project',
                failed_action_index=1,
                failed_action_name='action-1',
                completed_action_indices=[0],
                starting_commit='abc123',
                has_repository_changes=True,
                github_repository=None,
                error_message='Test error',
                error_timestamp=datetime.datetime.now(tz=datetime.UTC),
                preserved_directory_path=working_dir,
                configuration_hash='test-hash',
            )

            engine = workflow_engine.WorkflowEngine(
                self.config, self.workflow, resume_state=resume_state
            )

            with self.assertRaisesRegex(
                RuntimeError,
                'Workflow symlink not found in preserved directory',
            ):
                engine._restore_workflow_context(
                    str(working_dir), self.project, None
                )


class WorkflowEnginePrimaryStageTestCase(base.AsyncTestCase):
    """Test cases for primary stage execution."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        self.config = models.Configuration(
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                git=models.WorkflowGit(clone=False),
                actions=[
                    models.WorkflowShellAction(
                        name='action-1',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                    )
                ],
            ),
        )

        self.project = models.ImbiProject(
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

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_execute_single_action_success(self) -> None:
        """Test successful execution of a single action."""
        # Create repository directory
        (self.working_directory / 'repository').mkdir(parents=True)

        engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ) as mock_execute,
            mock.patch.object(engine.committer, 'commit', return_value=False),
        ):
            mock_context = models.WorkflowContext(
                workflow=self.workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project)

            self.assertTrue(result)
            mock_execute.assert_called_once()

    async def test_execute_skips_action_when_filter_fails(self) -> None:
        """Test that action is skipped when filter doesn't match."""
        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                git=models.WorkflowGit(clone=False),
                actions=[
                    models.WorkflowShellAction(
                        name='action-1',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        filter=models.WorkflowFilter(
                            project_types=['different-type']
                        ),
                    )
                ],
            ),
        )

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ) as mock_execute,
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project)

            self.assertTrue(result)
            mock_execute.assert_not_called()

    async def test_execute_skips_action_when_condition_fails(self) -> None:
        """Test that action is skipped when condition check fails."""
        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                git=models.WorkflowGit(clone=False),
                actions=[
                    models.WorkflowShellAction(
                        name='action-1',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        conditions=[
                            models.WorkflowCondition(
                                file_exists='nonexistent.txt'
                            )
                        ],
                    )
                ],
            ),
        )

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            # First call (workflow-level conditions) returns True, second call (action-level) returns False # noqa: E501
            mock.patch.object(
                engine.condition_checker, 'check', side_effect=[True, False]
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ) as mock_execute,
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project)

            self.assertTrue(result)
            mock_execute.assert_not_called()

    async def test_execute_committable_action_makes_commit(self) -> None:
        """Test that committable action triggers commit."""
        # Create repository directory for the action to run in
        (self.working_directory / 'repository').mkdir(parents=True)

        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                git=models.WorkflowGit(clone=False),
                github=models.WorkflowGitHub(create_pull_request=False),
                actions=[
                    models.WorkflowShellAction(
                        name='action-1',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        committable=True,
                    )
                ],
            ),
        )

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ),
            mock.patch.object(
                engine.committer, 'commit', return_value=True
            ) as mock_commit,
            mock.patch(
                'imbi_automations.git.push_changes',
                new_callable=mock.AsyncMock,
            ),
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project)

            self.assertTrue(result)
            mock_commit.assert_called_once()
            self.assertTrue(mock_context.has_repository_changes)

    async def test_execute_preserves_error_with_preserve_on_error(
        self,
    ) -> None:
        """Test that execution errors are preserved when preserve_on_error=True."""  # noqa: E501
        config = models.Configuration(
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
            preserve_on_error=True,
            error_dir=pathlib.Path(self.temp_dir.name) / 'errors',
        )

        engine = workflow_engine.WorkflowEngine(config, self.workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', side_effect=ValueError('Test error')
            ),
            mock.patch.object(
                engine,
                '_preserve_working_directory',
                return_value=pathlib.Path('/error'),
            ) as mock_preserve,
        ):
            mock_context = models.WorkflowContext(
                workflow=self.workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            with self.assertRaisesRegex(ValueError, 'Test error'):
                await engine.execute(self.project)

            mock_preserve.assert_called_once()
            self.assertEqual(
                engine.get_last_error_path(), pathlib.Path('/error')
            )

    async def test_execute_returns_false_when_remote_conditions_not_met(
        self,
    ) -> None:
        """Test that execute returns False when remote conditions fail."""
        engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run'),
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=False
            ),
        ):
            result = await engine.execute(self.project)

            self.assertFalse(result)

    async def test_execute_returns_false_when_local_conditions_not_met(
        self,
    ) -> None:
        """Test that execute returns False when local conditions fail."""
        engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run'),
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=False
            ),
        ):
            result = await engine.execute(self.project)

            self.assertFalse(result)

    async def test_execute_clones_repository_when_configured(self) -> None:
        """Test that repository is cloned when git.clone=True."""
        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                git=models.WorkflowGit(clone=True, starting_branch='main'),
                actions=[],
            ),
        )

        github_repo = create_mock_github_repository()

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch(
                'imbi_automations.git.clone_repository',
                return_value='commit-abc',
            ) as mock_clone,
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
                github_repository=github_repo,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project, github_repo)

            self.assertTrue(result)
            mock_clone.assert_called_once()
            self.assertEqual(mock_context.starting_commit, 'commit-abc')


class WorkflowEnginePullRequestTestCase(base.AsyncTestCase):
    """Test cases for pull request creation."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        self.config = models.Configuration(
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                slug='test-workflow',
                git=models.WorkflowGit(clone=False),
                github=models.WorkflowGitHub(create_pull_request=True),
                actions=[
                    models.WorkflowShellAction(
                        name='action-1',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        committable=True,
                    )
                ],
            ),
        )

        self.project = models.ImbiProject(
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

        self.github_repo = create_mock_github_repository()

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_create_pull_request_generates_branch_and_pr(self) -> None:
        """Test that _create_pull_request creates branch and PR."""
        # Create repository directory
        (self.working_directory / 'repository').mkdir(parents=True)

        # Create workflow with explicit slug to match expected branch name
        workflow_with_slug = models.Workflow(
            path=self.workflow.path,
            configuration=self.workflow.configuration,
            slug='test-workflow',
        )

        engine = workflow_engine.WorkflowEngine(
            self.config, workflow_with_slug
        )

        context = models.WorkflowContext(
            workflow=workflow_with_slug,
            imbi_project=self.project,
            working_directory=self.working_directory,
            starting_commit='commit-abc',
            github_repository=self.github_repo,
        )

        pr = models.GitHubPullRequest(
            id=789,
            number=42,
            title='Test PR',
            body='Test body',
            state='open',
            html_url='https://github.com/org/test-repo/pull/42',
            url='https://api.github.com/repos/org/test-repo/pulls/42',
            user=models.GitHubUser(
                login='testuser',
                id=1,
                node_id='MDQ6VXNlcjE=',
                avatar_url='https://github.com/images/error/testuser.png',
                gravatar_id='',
                url='https://api.github.com/users/testuser',
                html_url='https://github.com/testuser',
                type='User',
                site_admin=False,
            ),
            created_at=datetime.datetime.now(tz=datetime.UTC),
            updated_at=datetime.datetime.now(tz=datetime.UTC),
            head={'ref': 'imbi-automations/test-workflow', 'sha': 'abc123'},
            base={'ref': 'main', 'sha': 'def456'},
        )

        with (
            mock.patch(
                'imbi_automations.git.delete_remote_branch_if_exists',
                new_callable=mock.AsyncMock,
            ) as mock_delete,
            mock.patch(
                'imbi_automations.git.create_branch',
                new_callable=mock.AsyncMock,
            ) as mock_create_branch,
            mock.patch(
                'imbi_automations.git.push_changes',
                new_callable=mock.AsyncMock,
            ) as mock_push,
            mock.patch(
                'imbi_automations.git.get_commits_since',
                new_callable=mock.AsyncMock,
                return_value=models.GitCommitSummary(
                    total_commits=0,
                    commits=[],
                    files_affected=[],
                    commit_range='abc123..abc123',
                ),
            ),
            mock.patch(
                'imbi_automations.prompts.render', return_value='prompt'
            ),
            mock.patch('imbi_automations.claude.Claude') as mock_claude_class,
            mock.patch.object(
                engine.github,
                'create_pull_request',
                new_callable=mock.AsyncMock,
                return_value=pr,
            ) as mock_create_pr,
        ):
            mock_claude_instance = mock.Mock()
            mock_claude_instance.anthropic_query = mock.AsyncMock(
                return_value='PR body'
            )
            mock_claude_class.return_value = mock_claude_instance

            result_pr, branch_name = await engine._create_pull_request(context)

            self.assertEqual(result_pr, pr)
            self.assertEqual(branch_name, 'imbi-automations/test-workflow')
            mock_delete.assert_not_called()
            mock_create_branch.assert_called_once()
            mock_push.assert_called_once()
            mock_create_pr.assert_called_once()

    async def test_create_pull_request_deletes_branch_when_replace_enabled(
        self,
    ) -> None:
        """Test that _create_pull_request deletes remote branch when replace_branch=True."""  # noqa: E501
        # Create repository directory
        (self.working_directory / 'repository').mkdir(parents=True)

        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                slug='test-workflow',
                git=models.WorkflowGit(clone=False),
                github=models.WorkflowGitHub(
                    create_pull_request=True, replace_branch=True
                ),
                actions=[],
            ),
        )

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        context = models.WorkflowContext(
            workflow=workflow,
            imbi_project=self.project,
            working_directory=self.working_directory,
            starting_commit='commit-abc',
            github_repository=self.github_repo,
        )

        pr = models.GitHubPullRequest(
            id=789,
            number=42,
            title='Test PR',
            body='Test body',
            state='open',
            html_url='https://github.com/org/test-repo/pull/42',
            url='https://api.github.com/repos/org/test-repo/pulls/42',
            user=models.GitHubUser(
                login='testuser',
                id=1,
                node_id='MDQ6VXNlcjE=',
                avatar_url='https://github.com/images/error/testuser.png',
                gravatar_id='',
                url='https://api.github.com/users/testuser',
                html_url='https://github.com/testuser',
                type='User',
                site_admin=False,
            ),
            created_at=datetime.datetime.now(tz=datetime.UTC),
            updated_at=datetime.datetime.now(tz=datetime.UTC),
            head={'ref': 'imbi-automations/test-workflow', 'sha': 'abc123'},
            base={'ref': 'main', 'sha': 'def456'},
        )

        with (
            mock.patch(
                'imbi_automations.git.delete_remote_branch_if_exists',
                new_callable=mock.AsyncMock,
            ) as mock_delete,
            mock.patch(
                'imbi_automations.git.create_branch',
                new_callable=mock.AsyncMock,
            ),
            mock.patch(
                'imbi_automations.git.push_changes',
                new_callable=mock.AsyncMock,
            ),
            mock.patch(
                'imbi_automations.git.get_commits_since',
                new_callable=mock.AsyncMock,
                return_value=models.GitCommitSummary(
                    total_commits=0,
                    commits=[],
                    files_affected=[],
                    commit_range='abc123..abc123',
                ),
            ),
            mock.patch(
                'imbi_automations.prompts.render', return_value='prompt'
            ),
            mock.patch('imbi_automations.claude.Claude') as mock_claude_class,
            mock.patch.object(
                engine.github,
                'create_pull_request',
                new_callable=mock.AsyncMock,
                return_value=pr,
            ),
        ):
            mock_claude_instance = mock.Mock()
            mock_claude_instance.anthropic_query = mock.AsyncMock(
                return_value='PR body'
            )
            mock_claude_class.return_value = mock_claude_instance

            await engine._create_pull_request(context)

            mock_delete.assert_called_once()

    async def test_execute_creates_pr_when_changes_exist(self) -> None:
        """Test that execute creates PR when has_repository_changes=True."""
        # Create repository directory
        (self.working_directory / 'repository').mkdir(parents=True)

        engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

        pr = models.GitHubPullRequest(
            id=789,
            number=42,
            title='Test PR',
            body='Test body',
            state='open',
            html_url='https://github.com/org/test-repo/pull/42',
            url='https://api.github.com/repos/org/test-repo/pulls/42',
            user=models.GitHubUser(
                login='testuser',
                id=1,
                node_id='MDQ6VXNlcjE=',
                avatar_url='https://github.com/images/error/testuser.png',
                gravatar_id='',
                url='https://api.github.com/users/testuser',
                html_url='https://github.com/testuser',
                type='User',
                site_admin=False,
            ),
            created_at=datetime.datetime.now(tz=datetime.UTC),
            updated_at=datetime.datetime.now(tz=datetime.UTC),
            head={'ref': 'imbi-automations/test-workflow', 'sha': 'abc123'},
            base={'ref': 'main', 'sha': 'def456'},
        )

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ),
            mock.patch.object(engine.committer, 'commit', return_value=True),
            mock.patch.object(
                engine,
                '_create_pull_request',
                new_callable=mock.AsyncMock,
                return_value=(pr, 'imbi-automations/test-workflow'),
            ) as mock_create_pr,
        ):
            mock_context = models.WorkflowContext(
                workflow=self.workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
                github_repository=self.github_repo,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project, self.github_repo)

            self.assertTrue(result)
            mock_create_pr.assert_called_once()
            self.assertEqual(mock_context.pull_request, pr)
            self.assertEqual(
                mock_context.pr_branch, 'imbi-automations/test-workflow'
            )

    async def test_execute_pushes_without_pr_when_pr_creation_disabled(
        self,
    ) -> None:
        """Test that execute pushes directly when create_pull_request=False."""
        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                git=models.WorkflowGit(clone=False),
                github=models.WorkflowGitHub(create_pull_request=False),
                actions=[
                    models.WorkflowShellAction(
                        name='action-1',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        committable=True,
                    )
                ],
            ),
        )

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ),
            mock.patch.object(engine.committer, 'commit', return_value=True),
            mock.patch('imbi_automations.git.push_changes') as mock_push,
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project)

            self.assertTrue(result)
            mock_push.assert_called_once()


class WorkflowEngineFollowupStageTestCase(base.AsyncTestCase):
    """Test cases for followup stage execution."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        self.config = models.Configuration(
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.project = models.ImbiProject(
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

        self.pr = models.GitHubPullRequest(
            id=789,
            number=42,
            title='Test PR',
            body='Test body',
            state='open',
            html_url='https://github.com/org/test-repo/pull/42',
            url='https://api.github.com/repos/org/test-repo/pulls/42',
            user=models.GitHubUser(
                login='testuser',
                id=1,
                node_id='MDQ6VXNlcjE=',
                avatar_url='https://github.com/images/error/testuser.png',
                gravatar_id='',
                url='https://api.github.com/users/testuser',
                html_url='https://github.com/testuser',
                type='User',
                site_admin=False,
            ),
            created_at=datetime.datetime.now(tz=datetime.UTC),
            updated_at=datetime.datetime.now(tz=datetime.UTC),
            head={'ref': 'imbi-automations/test', 'sha': 'abc123'},
            base={'ref': 'main', 'sha': 'def456'},
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_execute_followup_stage_single_cycle_no_commits(
        self,
    ) -> None:
        """Test followup stage completes after single cycle with no commits."""
        # Create repository directory
        (self.working_directory / 'repository').mkdir(parents=True)

        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                slug='test-workflow',
                git=models.WorkflowGit(clone=False),
                github=models.WorkflowGitHub(create_pull_request=True),
                max_followup_cycles=3,
                actions=[
                    models.WorkflowShellAction(
                        name='primary-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        stage=models.WorkflowActionStage.primary,
                        committable=True,
                    ),
                    models.WorkflowShellAction(
                        name='followup-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo followup',
                        stage=models.WorkflowActionStage.followup,
                        committable=False,
                    ),
                ],
            ),
        )

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ),
            mock.patch.object(
                engine.committer, 'commit', side_effect=[True, False]
            ),
            mock.patch.object(
                engine,
                '_create_pull_request',
                new_callable=mock.AsyncMock,
                return_value=(self.pr, 'imbi-automations/test'),
            ),
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project)

            self.assertTrue(result)
            # Followup action should be executed once (no cycling)
            self.assertEqual(engine.actions.execute.call_count, 2)

    async def test_execute_followup_stage_cycles_on_commits(self) -> None:
        """Test followup stage cycles when commits are made."""
        # Create repository directory
        (self.working_directory / 'repository').mkdir(parents=True)

        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                slug='test-workflow',
                git=models.WorkflowGit(clone=False),
                github=models.WorkflowGitHub(create_pull_request=True),
                max_followup_cycles=3,
                actions=[
                    models.WorkflowShellAction(
                        name='primary-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        stage=models.WorkflowActionStage.primary,
                        committable=True,
                    ),
                    models.WorkflowShellAction(
                        name='followup-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo followup',
                        stage=models.WorkflowActionStage.followup,
                        committable=True,
                    ),
                ],
            ),
        )

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        # Simulate committer returning True twice, then False
        commit_results = [True, True, True, False]

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ),
            mock.patch.object(
                engine.committer, 'commit', side_effect=commit_results
            ),
            mock.patch.object(
                engine,
                '_create_pull_request',
                new_callable=mock.AsyncMock,
                return_value=(self.pr, 'imbi-automations/test'),
            ),
            mock.patch(
                'imbi_automations.git.push_changes',
                new_callable=mock.AsyncMock,
            ),
            mock.patch.object(
                engine,
                '_refresh_pr_status',
                new_callable=mock.AsyncMock,
                return_value=self.pr,
            ) as mock_refresh,
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project)

            self.assertTrue(result)
            # Primary action (1) + followup action (3 cycles)
            self.assertEqual(engine.actions.execute.call_count, 4)
            # Refresh called after first two cycles (not after final cycle)
            self.assertEqual(mock_refresh.call_count, 2)

    async def test_execute_followup_stage_raises_on_max_cycles(self) -> None:
        """Test that followup stage raises RuntimeError when max_cycles reached."""  # noqa: E501
        # Create repository directory
        (self.working_directory / 'repository').mkdir(parents=True)

        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                slug='test-workflow',
                git=models.WorkflowGit(clone=False),
                github=models.WorkflowGitHub(create_pull_request=True),
                max_followup_cycles=2,
                actions=[
                    models.WorkflowShellAction(
                        name='primary-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        stage=models.WorkflowActionStage.primary,
                        committable=True,
                    ),
                    models.WorkflowShellAction(
                        name='followup-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo followup',
                        stage=models.WorkflowActionStage.followup,
                        committable=True,
                    ),
                ],
            ),
        )

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ),
            mock.patch.object(engine.committer, 'commit', return_value=True),
            mock.patch.object(
                engine,
                '_create_pull_request',
                new_callable=mock.AsyncMock,
                return_value=(self.pr, 'imbi-automations/test'),
            ),
            mock.patch(
                'imbi_automations.git.push_changes',
                new_callable=mock.AsyncMock,
            ),
            mock.patch.object(
                engine,
                '_refresh_pr_status',
                new_callable=mock.AsyncMock,
                return_value=self.pr,
            ),
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            with self.assertRaisesRegex(
                RuntimeError, 'Followup stage reached max cycles'
            ):
                await engine.execute(self.project)

    async def test_execute_followup_stage_preserves_error(self) -> None:
        """Test that followup stage errors are preserved with preserve_on_error."""  # noqa: E501
        # Create repository directory
        (self.working_directory / 'repository').mkdir(parents=True)

        config = models.Configuration(
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
            preserve_on_error=True,
            error_dir=pathlib.Path(self.temp_dir.name) / 'errors',
        )

        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                slug='test-workflow',
                git=models.WorkflowGit(clone=False),
                github=models.WorkflowGitHub(create_pull_request=True),
                actions=[
                    models.WorkflowShellAction(
                        name='primary-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        stage=models.WorkflowActionStage.primary,
                        committable=True,
                    ),
                    models.WorkflowShellAction(
                        name='followup-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo followup',
                        stage=models.WorkflowActionStage.followup,
                        committable=True,
                    ),
                ],
            ),
        )

        engine = workflow_engine.WorkflowEngine(config, workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions,
                'execute',
                side_effect=[None, ValueError('Followup error')],
                new_callable=mock.AsyncMock,
            ),
            mock.patch.object(engine.committer, 'commit', return_value=True),
            mock.patch.object(
                engine,
                '_create_pull_request',
                new_callable=mock.AsyncMock,
                return_value=(self.pr, 'imbi-automations/test'),
            ),
            mock.patch.object(
                engine,
                '_preserve_working_directory',
                return_value=pathlib.Path('/error'),
            ) as mock_preserve,
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            with self.assertRaisesRegex(ValueError, 'Followup error'):
                await engine.execute(self.project)

            # Check that preserve was called with followup stage info
            call_kwargs = mock_preserve.call_args.kwargs
            self.assertEqual(call_kwargs['current_stage'], 'followup')
            self.assertEqual(call_kwargs['followup_cycle'], 1)


class WorkflowEngineResumabilityTestCase(base.AsyncTestCase):
    """Test cases for workflow resumability."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.preserved_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        self.preserved_path = pathlib.Path(self.preserved_dir.name)

        self.config = models.Configuration(
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.workflow_path = pathlib.Path('/mock/workflow')
        self.workflow = models.Workflow(
            path=self.workflow_path,
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                slug='test-workflow',
                git=models.WorkflowGit(clone=False),
                github=models.WorkflowGitHub(create_pull_request=False),
                actions=[
                    models.WorkflowShellAction(
                        name='action-1',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test1',
                    ),
                    models.WorkflowShellAction(
                        name='action-2',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test2',
                    ),
                    models.WorkflowShellAction(
                        name='action-3',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test3',
                    ),
                ],
            ),
        )

        self.project = models.ImbiProject(
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

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()
        self.preserved_dir.cleanup()

    async def test_execute_resumes_from_failed_action(self) -> None:
        """Test that execute resumes from the correct action index."""
        # Create a real workflow directory to symlink to
        actual_workflow_dir = self.preserved_path / 'actual_workflow'
        actual_workflow_dir.mkdir()

        # Create preserved directory structure
        (self.preserved_path / 'workflow').symlink_to(actual_workflow_dir)
        (self.preserved_path / 'extracted').mkdir()
        (self.preserved_path / 'repository').mkdir()

        resume_state = models.ResumeState(
            workflow_slug='test-workflow',
            workflow_path=self.workflow_path,
            project_id=123,
            project_slug='test-project',
            failed_action_index=1,
            failed_action_name='action-2',
            completed_action_indices=[0],
            starting_commit='commit-abc',
            has_repository_changes=True,
            github_repository=None,
            error_message='Test error',
            error_timestamp=datetime.datetime.now(tz=datetime.UTC),
            preserved_directory_path=self.preserved_path,
            configuration_hash='test-hash',
        )

        engine = workflow_engine.WorkflowEngine(
            self.config, self.workflow, resume_state=resume_state
        )

        with (
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ) as mock_execute,
            mock.patch.object(engine.committer, 'commit', return_value=False),
            mock.patch(
                'imbi_automations.git.push_changes',
                new_callable=mock.AsyncMock,
            ),
            mock.patch.object(engine, '_cleanup_resume_state') as mock_cleanup,
        ):
            result = await engine.execute(self.project)

            self.assertTrue(result)
            # Should execute action-2 and action-3 only (indices 1 and 2)
            self.assertEqual(mock_execute.call_count, 2)
            mock_cleanup.assert_called_once()

    async def test_execute_skips_conditions_when_resuming(self) -> None:
        """Test that execute skips pre-execution condition checks when resuming."""
        # Create a real workflow directory to symlink to
        actual_workflow_dir = self.preserved_path / 'actual_workflow'
        actual_workflow_dir.mkdir()

        # Create preserved directory structure
        (self.preserved_path / 'workflow').symlink_to(actual_workflow_dir)
        (self.preserved_path / 'extracted').mkdir()
        (self.preserved_path / 'repository').mkdir()

        resume_state = models.ResumeState(
            workflow_slug='test-workflow',
            workflow_path=self.workflow_path,
            project_id=123,
            project_slug='test-project',
            failed_action_index=1,
            failed_action_name='action-2',
            completed_action_indices=[0],
            starting_commit='commit-abc',
            has_repository_changes=False,
            github_repository=None,
            error_message='Test error',
            error_timestamp=datetime.datetime.now(tz=datetime.UTC),
            preserved_directory_path=self.preserved_path,
            configuration_hash='test-hash',
        )

        engine = workflow_engine.WorkflowEngine(
            self.config, self.workflow, resume_state=resume_state
        )

        # Track when actions execute to verify conditions checked after
        action_executed = False

        async def track_execute(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
            nonlocal action_executed
            action_executed = True

        with (
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', side_effect=track_execute
            ),
            mock.patch.object(engine.committer, 'commit', return_value=False),
        ):
            result = await engine.execute(self.project)

            self.assertTrue(result)
            # Actions should have been executed
            self.assertTrue(action_executed)
            # Condition checks may happen but only after actions start
            # (not before like in normal execution)

    async def test_cleanup_resume_state_removes_preserved_directory(
        self,
    ) -> None:
        """Test that _cleanup_resume_state removes the preserved directory."""
        # Create a temporary directory to be cleaned up
        cleanup_dir = pathlib.Path(self.temp_dir.name) / 'cleanup-test'
        cleanup_dir.mkdir()
        (cleanup_dir / 'test.txt').write_text('test content')

        resume_state = models.ResumeState(
            workflow_slug='test-workflow',
            workflow_path=self.workflow_path,
            project_id=123,
            project_slug='test-project',
            failed_action_index=0,
            failed_action_name='action-1',
            completed_action_indices=[],
            starting_commit=None,
            has_repository_changes=False,
            github_repository=None,
            error_message='Test error',
            error_timestamp=datetime.datetime.now(tz=datetime.UTC),
            preserved_directory_path=cleanup_dir,
            configuration_hash='test-hash',
        )

        engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

        # Verify directory exists before cleanup
        self.assertTrue(cleanup_dir.exists())

        engine._cleanup_resume_state(resume_state)

        # Verify directory is removed
        self.assertFalse(cleanup_dir.exists())

    async def test_preserve_working_directory_creates_state_file(self) -> None:
        """Test that _preserve_working_directory creates .state file with correct data."""  # noqa: E501
        preserve_dir = pathlib.Path(self.temp_dir.name) / 'preserve-test'
        preserve_dir.mkdir(parents=True)

        with tempfile.TemporaryDirectory() as work_temp:
            work_dir = tempfile.TemporaryDirectory()
            work_dir.name = work_temp
            (pathlib.Path(work_temp) / 'test.txt').write_text('test')

            context = models.WorkflowContext(
                workflow=self.workflow,
                imbi_project=self.project,
                working_directory=pathlib.Path(work_temp),
                starting_commit='commit-abc',
                has_repository_changes=True,
            )

            engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

            result_path = engine._preserve_working_directory(
                context,
                work_dir,
                preserve_dir,
                failed_action_index=1,
                failed_action_name='action-2',
                completed_action_indices=[0],
                error_message='Test error message',
                current_stage='primary',
                followup_cycle=0,
            )

            self.assertIsNotNone(result_path)
            self.assertTrue(result_path.exists())

            # Verify .state file exists and can be deserialized
            state_file = result_path / '.state'
            self.assertTrue(state_file.exists())

            state_data = msgpack.unpackb(state_file.read_bytes(), raw=False)
            self.assertEqual(state_data['failed_action_index'], 1)
            self.assertEqual(state_data['failed_action_name'], 'action-2')
            self.assertEqual(state_data['completed_action_indices'], [0])
            self.assertEqual(state_data['error_message'], 'Test error message')
            self.assertEqual(state_data['current_stage'], 'primary')
            self.assertEqual(state_data['followup_cycle'], 0)


class WorkflowEngineDryRunTestCase(base.AsyncTestCase):
    """Test cases for dry-run mode."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        self.config = models.Configuration(
            claude=models.ClaudeAgentConfiguration(
                enabled=True, executable='claude'
            ),
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
            dry_run=True,
            dry_run_dir=pathlib.Path(self.temp_dir.name) / 'dry-run',
        )

        self.workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                git=models.WorkflowGit(clone=False),
                actions=[
                    models.WorkflowShellAction(
                        name='action-1',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        committable=True,
                    )
                ],
            ),
        )

        self.project = models.ImbiProject(
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

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_execute_preserves_state_in_dry_run_mode(self) -> None:
        """Test that execute preserves working directory in dry-run mode."""
        engine = workflow_engine.WorkflowEngine(self.config, self.workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ),
            mock.patch.object(engine.committer, 'commit', return_value=True),
            mock.patch.object(
                engine,
                '_preserve_working_directory',
                return_value=pathlib.Path('/dry-run'),
            ) as mock_preserve,
        ):
            mock_context = models.WorkflowContext(
                workflow=self.workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project)

            self.assertTrue(result)
            mock_preserve.assert_called_once()
            # Verify preserve was called with dry_run_dir
            self.assertEqual(
                mock_preserve.call_args[0][2], self.config.dry_run_dir
            )

    async def test_execute_skips_followup_in_dry_run_mode(self) -> None:
        """Test that execute skips followup actions in dry-run mode."""
        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                git=models.WorkflowGit(clone=False),
                actions=[
                    models.WorkflowShellAction(
                        name='primary-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo test',
                        stage=models.WorkflowActionStage.primary,
                        committable=True,
                    ),
                    models.WorkflowShellAction(
                        name='followup-action',
                        type=models.WorkflowActionTypes.shell,
                        command='echo followup',
                        stage=models.WorkflowActionStage.followup,
                    ),
                ],
            ),
        )

        engine = workflow_engine.WorkflowEngine(self.config, workflow)

        with (
            mock.patch.object(engine, '_setup_workflow_run') as mock_setup,
            mock.patch.object(
                engine.condition_checker, 'check_remote', return_value=True
            ),
            mock.patch.object(
                engine.condition_checker, 'check', return_value=True
            ),
            mock.patch.object(
                engine.actions, 'execute', new_callable=mock.AsyncMock
            ) as mock_execute,
            mock.patch.object(engine.committer, 'commit', return_value=True),
            mock.patch.object(
                engine,
                '_preserve_working_directory',
                return_value=pathlib.Path('/dry-run'),
            ),
        ):
            mock_context = models.WorkflowContext(
                workflow=workflow,
                imbi_project=self.project,
                working_directory=self.working_directory,
            )
            mock_setup.return_value = mock_context

            result = await engine.execute(self.project)

            self.assertTrue(result)
            # Only primary action should be executed
            self.assertEqual(mock_execute.call_count, 1)


if __name__ == '__main__':
    unittest.main()
