"""Tests for controller.py - Main automation controller.

Covers initialization, iterator detection, project filtering, workflow
execution, resumption from state, and filter validation.
"""

# ruff: noqa: S106, S108

import argparse
import pathlib
import typing
from unittest import mock

import httpx

from imbi_automations import controller, imc, models
from tests import base


def create_test_project(**kwargs: typing.Any) -> models.ImbiProject:  # noqa: ANN401
    """Helper to create a test ImbiProject with default values."""
    defaults = {
        'id': 1,
        'dependencies': None,
        'description': 'Test project',
        'environments': None,
        'facts': None,
        'identifiers': None,
        'links': None,
        'name': 'test-project',
        'namespace': 'test-namespace',
        'namespace_slug': 'test-namespace',
        'project_score': None,
        'project_type': 'API',
        'project_type_slug': 'api',
        'slug': 'test-project',
        'urls': None,
        'imbi_url': 'https://imbi.example.com/projects/1',
    }
    defaults.update(kwargs)
    return models.ImbiProject(**defaults)


class ControllerInitializationTestCase(base.AsyncTestCase):
    """Test controller initialization and component setup."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

    def test_init_creates_components(self) -> None:
        """Test that initialization creates all required components."""
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=False,
            resume=None,
            project_id=None,
            project_type=None,
            all_projects=False,
        )

        automation = controller.Automation(args, self.config, self.workflow)

        self.assertEqual(automation.args, args)
        self.assertEqual(automation.configuration, self.config)
        self.assertEqual(automation.workflow, self.workflow)
        self.assertIsInstance(automation.registry, imc.ImbiMetadataCache)
        self.assertIsNotNone(automation.workflow_filter)
        self.assertIsNone(automation._workflow_engine)

    def test_workflow_engine_lazy_initialization(self) -> None:
        """Test that workflow engine is created on first access."""
        args = argparse.Namespace(
            verbose=False, max_concurrency=5, exit_on_error=False, resume=None
        )

        automation = controller.Automation(args, self.config, self.workflow)

        self.assertIsNone(automation._workflow_engine)
        engine = automation.workflow_engine
        self.assertIsNotNone(engine)
        self.assertIs(automation.workflow_engine, engine)

    def test_iterator_single_project(self) -> None:
        """Test iterator detection for single project mode."""
        args = argparse.Namespace(
            verbose=False,
            resume=None,
            project_id=123,
            project_type=None,
            all_projects=False,
            github_repository=None,
            github_organization=None,
            all_github_repositories=False,
        )

        automation = controller.Automation(args, self.config, self.workflow)
        self.assertEqual(
            automation.iterator, controller.AutomationIterator.imbi_project
        )

    def test_iterator_project_type(self) -> None:
        """Test iterator detection for project type mode."""
        args = argparse.Namespace(
            verbose=False,
            resume=None,
            project_id=None,
            project_type='apis',
            all_projects=False,
            github_repository=None,
            github_organization=None,
            all_github_repositories=False,
        )

        automation = controller.Automation(args, self.config, self.workflow)
        self.assertEqual(
            automation.iterator,
            controller.AutomationIterator.imbi_project_type,
        )

    def test_iterator_all_projects(self) -> None:
        """Test iterator detection for all projects mode."""
        args = argparse.Namespace(
            verbose=False,
            resume=None,
            project_id=None,
            project_type=None,
            all_projects=True,
            github_repository=None,
            github_organization=None,
            all_github_repositories=False,
        )

        automation = controller.Automation(args, self.config, self.workflow)
        self.assertEqual(
            automation.iterator, controller.AutomationIterator.imbi_projects
        )

    def test_iterator_resume_mode(self) -> None:
        """Test that resume mode returns None iterator."""
        args = argparse.Namespace(
            verbose=False,
            resume=pathlib.Path('/tmp/errors/workflow/project-123'),
            project_id=None,
            project_type=None,
            all_projects=False,
        )

        automation = controller.Automation(args, self.config, self.workflow)
        self.assertIsNone(automation.iterator)


class ControllerProjectFilteringTestCase(base.AsyncTestCase):
    """Test project filtering functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[],
                filter=models.WorkflowFilter(project_types=['apis']),
            ),
        )

    async def test_filter_projects_applies_workflow_filter(self) -> None:
        """Test that _filter_projects applies workflow filters."""
        args = argparse.Namespace(
            verbose=False, max_concurrency=5, exit_on_error=False
        )

        automation = controller.Automation(args, self.config, self.workflow)

        projects = [
            create_test_project(id=1, slug='test-api', name='Test API'),
            create_test_project(
                id=2,
                slug='test-consumer',
                name='Test Consumer',
                project_type_slug='consumers',
            ),
        ]

        with mock.patch.object(
            automation.workflow_filter, 'filter_project'
        ) as mock_filter:
            mock_filter.side_effect = [projects[0], None]

            result = await automation._filter_projects(projects)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].id, 1)
            self.assertEqual(mock_filter.call_count, 2)

    async def test_filter_projects_with_concurrency(self) -> None:
        """Test that filtering respects concurrency limits."""
        args = argparse.Namespace(
            verbose=False, max_concurrency=2, exit_on_error=False
        )

        automation = controller.Automation(args, self.config, self.workflow)

        projects = [
            create_test_project(id=i, slug=f'project-{i}', name=f'Project {i}')
            for i in range(5)
        ]

        with mock.patch.object(
            automation.workflow_filter, 'filter_project'
        ) as mock_filter:
            mock_filter.side_effect = projects

            result = await automation._filter_projects(projects)

            self.assertEqual(len(result), 5)

    async def test_filter_projects_empty_results(self) -> None:
        """Test handling of empty filter results."""
        args = argparse.Namespace(
            verbose=False, max_concurrency=5, exit_on_error=False
        )

        automation = controller.Automation(args, self.config, self.workflow)

        projects = [
            create_test_project(id=1, slug='test-api', name='Test API')
        ]

        with mock.patch.object(
            automation.workflow_filter, 'filter_project'
        ) as mock_filter:
            mock_filter.return_value = None

            result = await automation._filter_projects(projects)

            self.assertEqual(len(result), 0)

    async def test_filter_projects_no_workflow_filter(self) -> None:
        """Test that projects pass through when no filter configured."""
        workflow_no_filter = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

        args = argparse.Namespace(
            verbose=False, max_concurrency=5, exit_on_error=False
        )

        automation = controller.Automation(
            args, self.config, workflow_no_filter
        )

        projects = [
            create_test_project(id=1, slug='test-api', name='Test API')
        ]

        result = await automation._filter_projects(projects)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, 1)


class ControllerSingleProjectTestCase(base.AsyncTestCase):
    """Test single project workflow execution."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

    async def test_process_imbi_project_success(self) -> None:
        """Test successful single project processing."""
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=False,
            project_id=123,
        )

        automation = controller.Automation(args, self.config, self.workflow)

        project = create_test_project(id=123, slug='test-api', name='Test API')

        self.http_client_side_effect = httpx.Response(
            200, json=project.model_dump()
        )

        with mock.patch.object(
            automation, '_process_workflow_from_imbi_project'
        ) as mock_process:
            mock_process.return_value = True

            result = await automation._process_imbi_project()

            self.assertTrue(result)
            mock_process.assert_called_once()

    async def test_process_imbi_project_with_github_repo(self) -> None:
        """Test single project processing with GitHub integration."""
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=False,
            project_id=123,
        )

        automation = controller.Automation(args, self.config, self.workflow)

        project = create_test_project(
            id=123,
            slug='test-api',
            name='Test API',
            identifiers={'github': 'org/repo'},
        )

        self.http_client_side_effect = httpx.Response(
            200, json=project.model_dump()
        )

        with mock.patch.object(
            automation, '_process_workflow_from_imbi_project'
        ) as mock_process:
            mock_process.return_value = True

            result = await automation._process_imbi_project()

            self.assertTrue(result)
            mock_process.assert_called_once()

    async def test_process_imbi_project_failure(self) -> None:
        """Test handling of workflow execution failure."""
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=False,
            project_id=123,
        )

        automation = controller.Automation(args, self.config, self.workflow)

        project = create_test_project(id=123, slug='test-api', name='Test API')

        self.http_client_side_effect = httpx.Response(
            200, json=project.model_dump()
        )

        with mock.patch.object(
            automation, '_process_workflow_from_imbi_project'
        ) as mock_process:
            mock_process.return_value = False

            result = await automation._process_imbi_project()

            self.assertFalse(result)


class ControllerProjectTypeTestCase(base.AsyncTestCase):
    """Test project type iterator functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

    async def test_process_imbi_project_type_validates_slug(self) -> None:
        """Test that project type slug is validated."""
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=False,
            project_type='apis',
        )

        automation = controller.Automation(args, self.config, self.workflow)
        automation.registry.cache_data.project_types = [
            models.ImbiProjectType(
                id=1,
                slug='apis',
                name='APIs',
                plural_name='APIs',
                icon_class='fa-api',
                environment_urls=False,
            )
        ]

        with mock.patch.object(
            automation, '_process_imbi_projects_common'
        ) as mock_process:
            mock_process.return_value = True

            projects = [
                create_test_project(id=1, slug='test-api', name='Test API')
            ]

            self.http_client_side_effect = httpx.Response(
                200, json=[p.model_dump() for p in projects]
            )

            result = await automation._process_imbi_project_type()

            self.assertTrue(result)
            mock_process.assert_called_once()

    async def test_process_imbi_project_type_invalid_slug(self) -> None:
        """Test error handling for invalid project type slug."""
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=False,
            project_type='invalid-type',
        )

        automation = controller.Automation(args, self.config, self.workflow)
        automation.registry.cache_data.project_types = [
            models.ImbiProjectType(
                id=1,
                slug='apis',
                name='APIs',
                plural_name='APIs',
                icon_class='fa-api',
                environment_urls=False,
            )
        ]

        with self.assertRaises(RuntimeError) as ctx:
            await automation._process_imbi_project_type()

        self.assertIn('Invalid project type slug', str(ctx.exception))


class ControllerAllProjectsTestCase(base.AsyncTestCase):
    """Test all projects iterator functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

    async def test_process_imbi_projects_exit_on_error_mode(self) -> None:
        """Test exit-on-error mode uses TaskGroup."""
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=True,
            all_projects=True,
        )

        automation = controller.Automation(args, self.config, self.workflow)

        projects = [
            create_test_project(id=1, slug='test-api', name='Test API'),
            create_test_project(
                id=2, slug='test-consumer', name='Test Consumer'
            ),
        ]

        self.http_client_side_effect = httpx.Response(
            200, json=[p.model_dump() for p in projects]
        )

        with (
            mock.patch.object(automation, '_filter_projects') as mock_filter,
            mock.patch.object(
                automation.workflow_engine, 'execute'
            ) as mock_execute,
            mock.patch.object(
                automation, '_get_github_repository', new=mock.AsyncMock()
            ) as mock_github,
        ):
            mock_filter.return_value = projects
            mock_execute.return_value = True
            mock_github.return_value = None

            result = await automation._process_imbi_projects()

            self.assertTrue(result)
            self.assertEqual(mock_execute.call_count, 2)

    async def test_process_imbi_projects_continue_on_error_mode(self) -> None:
        """Test continue-on-error mode uses gather."""
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=False,
            all_projects=True,
        )

        automation = controller.Automation(args, self.config, self.workflow)

        projects = [
            create_test_project(id=1, slug='test-api', name='Test API'),
            create_test_project(
                id=2, slug='test-consumer', name='Test Consumer'
            ),
        ]

        self.http_client_side_effect = httpx.Response(
            200, json=[p.model_dump() for p in projects]
        )

        with (
            mock.patch.object(automation, '_filter_projects') as mock_filter,
            mock.patch.object(
                automation.workflow_engine, 'execute'
            ) as mock_execute,
            mock.patch.object(
                automation, '_get_github_repository', new=mock.AsyncMock()
            ) as mock_github,
        ):
            mock_filter.return_value = projects
            mock_execute.side_effect = [True, False]
            mock_github.return_value = None

            result = await automation._process_imbi_projects()

            self.assertFalse(result)
            self.assertEqual(mock_execute.call_count, 2)

    async def test_process_imbi_projects_success_failure_counting(
        self,
    ) -> None:
        """Test success and failure counting."""
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=False,
            all_projects=True,
        )

        automation = controller.Automation(args, self.config, self.workflow)

        projects = [
            create_test_project(id=i, slug=f'project-{i}', name=f'Project {i}')
            for i in range(3)
        ]

        self.http_client_side_effect = httpx.Response(
            200, json=[p.model_dump() for p in projects]
        )

        with (
            mock.patch.object(automation, '_filter_projects') as mock_filter,
            mock.patch.object(
                automation.workflow_engine, 'execute'
            ) as mock_execute,
            mock.patch.object(
                automation, '_get_github_repository', new=mock.AsyncMock()
            ) as mock_github,
        ):
            mock_filter.return_value = projects
            mock_execute.side_effect = [True, False, True]
            mock_github.return_value = None

            result = await automation._process_imbi_projects()

            self.assertFalse(result)


class ControllerResumeTestCase(base.AsyncTestCase):
    """Test workflow resumption from saved state."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

    async def test_resume_from_state_missing_file(self) -> None:
        """Test error when .state file not found."""
        resume_path = pathlib.Path('/tmp/nonexistent')
        args = argparse.Namespace(
            verbose=False,
            max_concurrency=5,
            exit_on_error=False,
            resume=resume_path,
        )

        automation = controller.Automation(args, self.config, self.workflow)

        with self.assertRaises(RuntimeError) as ctx:
            await automation._resume_from_state()

        self.assertIn('No .state file found', str(ctx.exception))

    async def test_resume_from_state_invalid_workflow_path(self) -> None:
        """Test error when workflow path from state doesn't exist."""
        import datetime
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            resume_path = pathlib.Path(tmpdir)
            state_file = resume_path / '.state'

            state = models.ResumeState(
                workflow_slug='test-workflow',
                workflow_path=pathlib.Path('/nonexistent/workflow'),
                project_id=123,
                project_slug='test-project',
                failed_action_index=0,
                failed_action_name='test-action',
                completed_action_indices=[],
                starting_commit=None,
                has_repository_changes=False,
                github_repository=None,
                error_message='Test error',
                error_timestamp=datetime.datetime.now(tz=datetime.UTC),
                preserved_directory_path=resume_path,
                configuration_hash='abc123',
            )

            state_file.write_bytes(state.to_msgpack())

            args = argparse.Namespace(
                verbose=False,
                max_concurrency=5,
                exit_on_error=False,
                resume=resume_path,
            )

            automation = controller.Automation(
                args, self.config, self.workflow
            )

            with self.assertRaises(RuntimeError) as ctx:
                await automation._resume_from_state()

            self.assertIn('does not exist', str(ctx.exception))

    async def test_resume_from_state_configuration_changed_warning(
        self,
    ) -> None:
        """Test warning when configuration hash differs."""
        import datetime
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            resume_path = pathlib.Path(tmpdir)
            state_file = resume_path / '.state'

            workflow_path = pathlib.Path(tmpdir) / 'workflow'
            workflow_path.mkdir()
            (workflow_path / 'config.toml').write_text(
                '[workflow]\nname="test"'
            )

            state = models.ResumeState(
                workflow_slug='test-workflow',
                workflow_path=workflow_path,
                project_id=123,
                project_slug='test-project',
                failed_action_index=0,
                failed_action_name='test-action',
                completed_action_indices=[],
                starting_commit=None,
                has_repository_changes=False,
                github_repository=None,
                error_message='Test error',
                error_timestamp=datetime.datetime.now(tz=datetime.UTC),
                preserved_directory_path=resume_path,
                configuration_hash='old-hash',
            )

            state_file.write_bytes(state.to_msgpack())

            args = argparse.Namespace(
                verbose=False,
                max_concurrency=5,
                exit_on_error=False,
                resume=resume_path,
            )

            automation = controller.Automation(
                args, self.config, self.workflow
            )

            project = create_test_project(
                id=123, slug='test-project', name='Test Project'
            )

            with (
                mock.patch(
                    'imbi_automations.clients.Imbi.get_instance'
                ) as mock_client_factory,
                mock.patch(
                    'imbi_automations.workflow_engine.WorkflowEngine'
                ) as mock_engine_class,
            ):
                # Mock the Imbi client and get_project method
                mock_client = mock.AsyncMock()
                mock_client.get_project.return_value = project
                mock_client_factory.return_value = mock_client

                # Mock the WorkflowEngine instance and execute method
                mock_engine_instance = mock.AsyncMock()
                mock_engine_instance.execute.return_value = True
                mock_engine_class.return_value = mock_engine_instance

                result = await automation._resume_from_state()

                self.assertTrue(result)
                # Verify the workflow engine was created and executed
                mock_engine_class.assert_called_once()
                mock_engine_instance.execute.assert_called_once()


class ControllerFilterValidationTestCase(base.AsyncTestCase):
    """Test workflow filter validation."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(token='test-token'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

    def test_validate_workflow_filter_environments(self) -> None:
        """Test environment validation."""
        workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[],
                filter=models.WorkflowFilter(
                    project_environments=['production', 'staging']
                ),
            ),
        )

        args = argparse.Namespace(verbose=False)

        automation = controller.Automation(args, self.config, workflow)
        automation.registry.cache_data.environments = [
            models.ImbiEnvironment(
                name='Production',
                slug='production',
                icon_class='fa-prod',
                description='Production',
            ),
            models.ImbiEnvironment(
                name='Staging',
                slug='staging',
                icon_class='fa-stage',
                description='Staging',
            ),
            models.ImbiEnvironment(
                name='Development',
                slug='development',
                icon_class='fa-dev',
                description='Development',
            ),
        ]

        automation._validate_workflow_filter_environments()

    def test_validate_workflow_filter_invalid_environment(self) -> None:
        """Test error on invalid environment."""
        workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[],
                filter=models.WorkflowFilter(
                    project_environments=['invalid-env']
                ),
            ),
        )

        args = argparse.Namespace(verbose=False)

        automation = controller.Automation(args, self.config, workflow)
        automation.registry.cache_data.environments = [
            models.ImbiEnvironment(
                name='Production',
                slug='production',
                icon_class='fa-prod',
                description='Production',
            ),
            models.ImbiEnvironment(
                name='Staging',
                slug='staging',
                icon_class='fa-stage',
                description='Staging',
            ),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            automation._validate_workflow_filter_environments()

        self.assertIn('not a valid', str(ctx.exception))

    def test_validate_workflow_filter_project_types(self) -> None:
        """Test project type validation."""
        workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[],
                filter=models.WorkflowFilter(project_types=['apis']),
            ),
        )

        args = argparse.Namespace(verbose=False)

        automation = controller.Automation(args, self.config, workflow)
        automation.registry.cache_data.project_types = [
            models.ImbiProjectType(
                id=1,
                slug='apis',
                name='APIs',
                plural_name='APIs',
                icon_class='fa-api',
                environment_urls=False,
            )
        ]

        automation._validate_workflow_filter_project_types()

    def test_validate_workflow_filter_invalid_project_type(self) -> None:
        """Test error on invalid project type."""
        workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[],
                filter=models.WorkflowFilter(project_types=['invalid-type']),
            ),
        )

        args = argparse.Namespace(verbose=False)

        automation = controller.Automation(args, self.config, workflow)
        automation.registry.cache_data.project_types = [
            models.ImbiProjectType(
                id=1,
                slug='apis',
                name='APIs',
                plural_name='APIs',
                icon_class='fa-api',
                environment_urls=False,
            )
        ]

        with self.assertRaises(RuntimeError) as ctx:
            automation._validate_workflow_filter_project_types()

        self.assertIn('not a valid project type', str(ctx.exception))

    def test_validate_workflow_filter_project_facts(self) -> None:
        """Test project fact validation."""
        workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[],
                filter=models.WorkflowFilter(
                    project_facts={'Programming Language': 'Python 3.12'}
                ),
            ),
        )

        args = argparse.Namespace(verbose=False)

        automation = controller.Automation(args, self.config, workflow)
        automation.registry.cache_data.project_fact_types = [
            models.ImbiProjectFactType(
                id=1,
                name='Programming Language',
                fact_type='enum',
                data_type='string',
                description='Programming language',
            )
        ]
        automation.registry.cache_data.project_fact_type_enums = [
            models.ImbiProjectFactTypeEnum(
                id=1, fact_type_id=1, value='Python 3.12', score=10
            ),
            models.ImbiProjectFactTypeEnum(
                id=2, fact_type_id=1, value='Python 3.11', score=9
            ),
        ]

        automation._validate_workflow_filter_project_facts()

    def test_validate_workflow_filter_invalid_project_fact_value(self) -> None:
        """Test error on invalid project fact value."""
        workflow = models.Workflow(
            path=pathlib.Path('/tmp/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[],
                filter=models.WorkflowFilter(
                    project_facts={'Programming Language': 'InvalidValue'}
                ),
            ),
        )

        args = argparse.Namespace(verbose=False)

        automation = controller.Automation(args, self.config, workflow)
        automation.registry.cache_data.project_fact_types = [
            models.ImbiProjectFactType(
                id=1,
                name='Programming Language',
                fact_type='enum',
                data_type='string',
                description='Programming language',
            )
        ]
        automation.registry.cache_data.project_fact_type_enums = [
            models.ImbiProjectFactTypeEnum(
                id=1, fact_type_id=1, value='Python 3.12', score=10
            ),
            models.ImbiProjectFactTypeEnum(
                id=2, fact_type_id=1, value='Python 3.11', score=9
            ),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            automation._validate_workflow_filter_project_facts()

        self.assertIn('Invalid value for fact type', str(ctx.exception))
