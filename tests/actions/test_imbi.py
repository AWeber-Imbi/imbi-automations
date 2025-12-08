"""Tests for the imbi action module."""

import pathlib
import tempfile
import unittest
from unittest import mock

import httpx

from imbi_automations import models
from imbi_automations.actions import imbi as imbi_actions
from tests import base


class ImbiActionsTestCase(base.AsyncTestCase):
    """Test cases for ImbiActions functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        # Create workflow and repository directories
        (self.working_directory / 'workflow').mkdir()
        (self.working_directory / 'repository').mkdir()

        # Create workflow context
        self.workflow = models.Workflow(
            path=pathlib.Path('/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

        # Create mock registry
        self.mock_registry = mock.MagicMock()
        self.mock_registry.translate_environments = mock.MagicMock(
            return_value=['Development', 'Staging']
        )

        self.context = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=models.ImbiProject(
                id=123,
                dependencies=None,
                description='Test project',
                environments=None,
                facts={'Language': 'Python'},
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
            registry=self.mock_registry,
        )

        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-key'  # noqa: S106
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.imbi_executor = imbi_actions.ImbiActions(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_set_project_fact_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test successful project fact update."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='set-fact',
            type='imbi',
            command='set_project_fact',
            fact_name='Language',
            value='Python 3.12',
        )

        await self.imbi_executor.execute(action)

        mock_client.update_project_fact.assert_called_once_with(
            project_id=123,
            fact_name='Language',
            value='Python 3.12',
            skip_validations=False,
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_set_project_fact_with_skip_validations(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test project fact update with skip_validations flag."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='set-fact-skip-validation',
            type='imbi',
            command='set_project_fact',
            fact_name='Custom Fact',
            value='any value',
            skip_validations=True,
        )

        await self.imbi_executor.execute(action)

        mock_client.update_project_fact.assert_called_once_with(
            project_id=123,
            fact_name='Custom Fact',
            value='any value',
            skip_validations=True,
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_set_project_fact_http_error(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test project fact update handles HTTP errors."""
        mock_client = mock.AsyncMock()
        mock_client.update_project_fact.side_effect = httpx.HTTPError(
            'API request failed'
        )
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='set-fact-error',
            type='imbi',
            command='set_project_fact',
            fact_name='Language',
            value='Python 3.12',
        )

        with self.assertRaises(httpx.HTTPError):
            await self.imbi_executor.execute(action)

    async def test_execute_set_project_fact_missing_value(self) -> None:
        """Test set_project_fact model validation requires value."""
        # Pydantic model validation catches missing value at construction time
        import pydantic

        with self.assertRaises(pydantic.ValidationError) as exc_context:
            models.WorkflowImbiAction(
                name='set-fact-no-value',
                type='imbi',
                command='set_project_fact',
                fact_name='Language',
                value=None,
            )

        self.assertIn("'value' is required", str(exc_context.exception))

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_set_environments_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test successful environments update."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='set-environments',
            type='imbi',
            command='set_environments',
            values=['development', 'staging'],
        )

        await self.imbi_executor.execute(action)

        # Registry should translate slugs to names
        self.mock_registry.translate_environments.assert_called_once_with(
            ['development', 'staging']
        )

        mock_client.update_project_environments.assert_called_once_with(
            project_id=123, environments=['Development', 'Staging']
        )

    async def test_execute_set_environments_missing_values(self) -> None:
        """Test set_environments raises error when values is empty."""
        action = models.WorkflowImbiAction(
            name='set-environments-empty',
            type='imbi',
            command='set_environments',
            values=[],
        )

        with self.assertRaises(ValueError) as exc_context:
            await self.imbi_executor.execute(action)

        self.assertIn('values is required', str(exc_context.exception))

    async def test_execute_set_environments_missing_registry(self) -> None:
        """Test set_environments raises error when registry is missing."""
        # Create context without registry
        self.context = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=self.context.imbi_project,
            working_directory=self.working_directory,
            registry=None,
        )
        self.imbi_executor = imbi_actions.ImbiActions(
            self.configuration, self.context, verbose=True
        )

        action = models.WorkflowImbiAction(
            name='set-environments-no-registry',
            type='imbi',
            command='set_environments',
            values=['development'],
        )

        with self.assertRaises(ValueError) as exc_context:
            await self.imbi_executor.execute(action)

        self.assertIn('registry not available', str(exc_context.exception))

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_update_project_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test successful project attribute update."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='update-project',
            type='imbi',
            command='update_project',
            attributes={'description': 'New description', 'name': 'New Name'},
        )

        await self.imbi_executor.execute(action)

        mock_client.update_project_attributes.assert_called_once_with(
            project_id=123,
            attributes={'description': 'New description', 'name': 'New Name'},
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_update_project_with_template(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test project update with Jinja2 template in attribute value."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='update-project-template',
            type='imbi',
            command='update_project',
            attributes={'description': 'Project: {{ imbi_project.name }}'},
        )

        await self.imbi_executor.execute(action)

        mock_client.update_project_attributes.assert_called_once_with(
            project_id=123, attributes={'description': 'Project: Test Project'}
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_update_project_with_variables(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test update_project can access workflow variables in templates."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        # Set a variable in context (as get_project_fact would do)
        self.context.variables['old_description'] = 'Legacy API'

        action = models.WorkflowImbiAction(
            name='update-project-with-vars',
            type='imbi',
            command='update_project',
            attributes={
                'description': 'Upgraded from: {{ variables.old_description }}'
            },
        )

        await self.imbi_executor.execute(action)

        mock_client.update_project_attributes.assert_called_once_with(
            project_id=123,
            attributes={'description': 'Upgraded from: Legacy API'},
        )

    async def test_execute_update_project_missing_attributes(self) -> None:
        """Test update_project raises error when attributes is empty."""
        action = models.WorkflowImbiAction(
            name='update-project-empty',
            type='imbi',
            command='update_project',
            attributes={},
        )

        with self.assertRaises(ValueError) as exc_context:
            await self.imbi_executor.execute(action)

        self.assertIn('attributes is required', str(exc_context.exception))

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_update_project_http_error(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test update_project handles HTTP errors."""
        mock_client = mock.AsyncMock()
        mock_client.update_project_attributes.side_effect = httpx.HTTPError(
            'API request failed'
        )
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='update-project-error',
            type='imbi',
            command='update_project',
            attributes={'description': 'New description'},
        )

        with self.assertRaises(httpx.HTTPError):
            await self.imbi_executor.execute(action)

    async def test_execute_unsupported_command(self) -> None:
        """Test execute raises error for unsupported command."""
        # Create a mock action with an invalid command
        action = mock.MagicMock(spec=models.WorkflowImbiAction)
        action.command = 'invalid_command'

        with self.assertRaises(RuntimeError) as exc_context:
            await self.imbi_executor.execute(action)

        self.assertIn('Unsupported command', str(exc_context.exception))

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_get_project_fact_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test successful project fact retrieval."""
        mock_client = mock.AsyncMock()
        mock_client.get_project_fact_value.return_value = 'Python 3.12'
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='get-fact',
            type='imbi',
            command='get_project_fact',
            fact_name='Language',
        )

        await self.imbi_executor.execute(action)

        mock_client.get_project_fact_value.assert_called_once_with(
            project_id=123, fact_name='Language'
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_get_project_fact_with_variable(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test get_project_fact stores value in variable."""
        mock_client = mock.AsyncMock()
        mock_client.get_project_fact_value.return_value = 'Python 3.12'
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='get-fact',
            type='imbi',
            command='get_project_fact',
            fact_name='Language',
            variable_name='language_version',
        )

        await self.imbi_executor.execute(action)

        self.assertEqual(
            self.context.variables['language_version'], 'Python 3.12'
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_delete_project_fact_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test successful project fact deletion."""
        mock_client = mock.AsyncMock()
        mock_client.delete_project_fact.return_value = True
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='delete-fact',
            type='imbi',
            command='delete_project_fact',
            fact_name='Obsolete Fact',
        )

        await self.imbi_executor.execute(action)

        mock_client.delete_project_fact.assert_called_once_with(
            project_id=123, fact_name='Obsolete Fact'
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_delete_project_fact_not_set(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test delete_project_fact when fact doesn't exist."""
        mock_client = mock.AsyncMock()
        mock_client.delete_project_fact.return_value = False
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='delete-fact',
            type='imbi',
            command='delete_project_fact',
            fact_name='Nonexistent Fact',
        )

        # Should not raise, just log that nothing was deleted
        await self.imbi_executor.execute(action)

        mock_client.delete_project_fact.assert_called_once()

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_add_project_link_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test successful project link addition."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='add-link',
            type='imbi',
            command='add_project_link',
            link_type='Documentation',
            url='https://docs.example.com/project',
        )

        await self.imbi_executor.execute(action)

        mock_client.add_project_link.assert_called_once_with(
            project_id=123,
            link_type='Documentation',
            url='https://docs.example.com/project',
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_add_project_link_with_template(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test add_project_link with Jinja2 template in URL."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='add-link-template',
            type='imbi',
            command='add_project_link',
            link_type='Repository',
            url='https://github.com/org/{{ imbi_project.slug }}',
        )

        await self.imbi_executor.execute(action)

        mock_client.add_project_link.assert_called_once_with(
            project_id=123,
            link_type='Repository',
            url='https://github.com/org/test-project',
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_add_project_link_with_variables(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test add_project_link with variables context in URL template."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        # Set a variable in the context (as get_project_fact would)
        self.context.variables['base_url'] = 'https://docs.example.com'

        action = models.WorkflowImbiAction(
            name='add-link-with-var',
            type='imbi',
            command='add_project_link',
            link_type='Documentation',
            url='{{ variables.base_url }}/{{ imbi_project.slug }}',
        )

        await self.imbi_executor.execute(action)

        mock_client.add_project_link.assert_called_once_with(
            project_id=123,
            link_type='Documentation',
            url='https://docs.example.com/test-project',
        )

    async def test_execute_add_project_link_missing_fields(self) -> None:
        """Test add_project_link model validation requires fields."""
        import pydantic

        with self.assertRaises(pydantic.ValidationError):
            models.WorkflowImbiAction(
                name='add-link-missing',
                type='imbi',
                command='add_project_link',
                link_type='Documentation',
                # Missing url
            )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_update_project_type_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test successful project type update."""
        mock_client = mock.AsyncMock()
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='update-type',
            type='imbi',
            command='update_project_type',
            project_type='consumer',
        )

        await self.imbi_executor.execute(action)

        mock_client.update_project_type.assert_called_once_with(
            project_id=123, project_type_slug='consumer'
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_update_project_type_http_error(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test update_project_type handles HTTP errors."""
        mock_client = mock.AsyncMock()
        mock_client.update_project_type.side_effect = httpx.HTTPError(
            'API request failed'
        )
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='update-type-error',
            type='imbi',
            command='update_project_type',
            project_type='invalid-type',
        )

        with self.assertRaises(httpx.HTTPError):
            await self.imbi_executor.execute(action)

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_batch_update_facts_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test successful batch fact update."""
        mock_client = mock.AsyncMock()
        mock_client.get_project_fact_type_id_by_name.side_effect = [1, 2, 3]
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='batch-update',
            type='imbi',
            command='batch_update_facts',
            facts={
                'Language': 'Python 3.12',
                'Framework': 'FastAPI',
                'Test Coverage': 85,
            },
        )

        await self.imbi_executor.execute(action)

        mock_client.update_project_facts.assert_called_once_with(
            project_id=123, facts=[(1, 'Python 3.12'), (2, 'FastAPI'), (3, 85)]
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_execute_batch_update_facts_unknown_fact(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        """Test batch_update_facts raises error for unknown fact type."""
        mock_client = mock.AsyncMock()
        mock_client.get_project_fact_type_id_by_name.return_value = None
        mock_get_instance.return_value = mock_client

        action = models.WorkflowImbiAction(
            name='batch-update-unknown',
            type='imbi',
            command='batch_update_facts',
            facts={'Unknown Fact': 'value'},
        )

        with self.assertRaises(ValueError) as exc_context:
            await self.imbi_executor.execute(action)

        self.assertIn('Fact type not found', str(exc_context.exception))

    async def test_execute_batch_update_facts_empty_facts(self) -> None:
        """Test batch_update_facts raises error when facts is empty."""
        action = models.WorkflowImbiAction(
            name='batch-update-empty',
            type='imbi',
            command='batch_update_facts',
            facts={},
        )

        with self.assertRaises(ValueError) as exc_context:
            await self.imbi_executor.execute(action)

        self.assertIn('facts is required', str(exc_context.exception))


if __name__ == '__main__':
    unittest.main()
