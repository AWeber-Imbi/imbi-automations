"""Tests for the imbi actions module."""

import pathlib
import tempfile
import unittest
from unittest import mock

import httpx

from imbi_automations import models
from imbi_automations.actions import imbi as imbi_actions
from tests import base, factories


class ImbiActionsTestCase(base.AsyncTestCase):
    """Test cases for :class:`imbi_actions.ImbiActions`."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        (self.working_directory / 'workflow').mkdir()
        (self.working_directory / 'repository').mkdir()

        self.workflow = models.Workflow(
            path=pathlib.Path('/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

        self.mock_registry = mock.MagicMock()
        self.mock_registry.translate_environments = mock.MagicMock(
            return_value=['development', 'staging']
        )

        self.imbi_project = factories.make_project(
            id='proj_123',
            slug='test-project',
            name='Test Project',
            project_type_slugs=['api'],
            identifiers={'github': 'test-org/test-project'},
            attributes={'programming_language': 'Python 3.11'},
        )

        self.context = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=self.imbi_project,
            working_directory=self.working_directory,
            registry=self.mock_registry,
        )

        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-key'  # noqa: S106
            ),
            imbi=models.ImbiConfiguration(
                organization='test-org',
                base_url='https://imbi.test.com',
                api_key='ik_test',
            ),
        )

        self.imbi_executor = imbi_actions.ImbiActions(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    # -- set_project_fact ----------------------------------------------

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_set_project_fact_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='set-fact',
            type='imbi',
            command='set_project_fact',
            attribute_name='programming_language',
            value='Python 3.12',
        )
        await self.imbi_executor.execute(action)
        client.set_project_attribute.assert_awaited_once_with(
            project_id='proj_123',
            name='programming_language',
            value='Python 3.12',
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_set_project_fact_http_error_propagates(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        client.set_project_attribute.side_effect = httpx.HTTPError('boom')
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='set-fact',
            type='imbi',
            command='set_project_fact',
            attribute_name='programming_language',
            value='Python 3.12',
        )
        with self.assertRaises(httpx.HTTPError):
            await self.imbi_executor.execute(action)

    # -- get_project_fact ----------------------------------------------

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_get_project_fact_returns_value(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        client.get_project_attribute.return_value = 'Python 3.12'
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='get-fact',
            type='imbi',
            command='get_project_fact',
            attribute_name='programming_language',
        )
        await self.imbi_executor.execute(action)
        client.get_project_attribute.assert_awaited_once_with(
            project_id='proj_123', name='programming_language'
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_get_project_fact_stores_in_variable(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        client.get_project_attribute.return_value = 'Python 3.12'
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='get-fact',
            type='imbi',
            command='get_project_fact',
            attribute_name='programming_language',
            variable_name='lang',
        )
        await self.imbi_executor.execute(action)
        self.assertEqual(self.context.variables.get('lang'), 'Python 3.12')

    # -- delete_project_fact -------------------------------------------

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_delete_project_fact_when_set(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        client.delete_project_attribute.return_value = True
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='del-fact',
            type='imbi',
            command='delete_project_fact',
            attribute_name='programming_language',
        )
        await self.imbi_executor.execute(action)
        client.delete_project_attribute.assert_awaited_once_with(
            project_id='proj_123', name='programming_language'
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_delete_project_fact_when_not_set(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        client.delete_project_attribute.return_value = False
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='del-fact',
            type='imbi',
            command='delete_project_fact',
            attribute_name='programming_language',
        )
        await self.imbi_executor.execute(action)
        client.delete_project_attribute.assert_awaited_once()

    # -- update_project ------------------------------------------------

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_update_project_success(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='update-project',
            type='imbi',
            command='update_project',
            attributes={'description': 'Updated', 'has_ci': True},
        )
        await self.imbi_executor.execute(action)
        client.set_project_attributes.assert_awaited_once_with(
            project_id='proj_123',
            attributes={'description': 'Updated', 'has_ci': True},
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_update_project_renders_jinja_in_string_attrs(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='update-project',
            type='imbi',
            command='update_project',
            attributes={
                'description': 'Project {{ imbi_project.slug }}',
                'has_ci': True,
            },
        )
        await self.imbi_executor.execute(action)
        kwargs = client.set_project_attributes.await_args.kwargs
        self.assertEqual(
            kwargs['attributes']['description'], 'Project test-project'
        )
        self.assertIs(kwargs['attributes']['has_ci'], True)

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_update_project_http_error_propagates(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        client.set_project_attributes.side_effect = httpx.HTTPError('boom')
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='update-project',
            type='imbi',
            command='update_project',
            attributes={'description': 'Updated'},
        )
        with self.assertRaises(httpx.HTTPError):
            await self.imbi_executor.execute(action)

    # -- update_project_type -------------------------------------------

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_update_project_type_replaces_slugs(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='retype',
            type='imbi',
            command='update_project_type',
            project_types=['api', 'cli'],
        )
        await self.imbi_executor.execute(action)
        client.set_project_types.assert_awaited_once_with(
            project_id='proj_123', slugs=['api', 'cli']
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_update_project_type_http_error_propagates(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        client.set_project_types.side_effect = httpx.HTTPError('boom')
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='retype',
            type='imbi',
            command='update_project_type',
            project_types=['consumer'],
        )
        with self.assertRaises(httpx.HTTPError):
            await self.imbi_executor.execute(action)

    # -- set_environments ---------------------------------------------

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_set_environments_translates_and_calls_client(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='set-envs',
            type='imbi',
            command='set_environments',
            values=['Development', 'Staging'],
        )
        await self.imbi_executor.execute(action)
        self.mock_registry.translate_environments.assert_called_once_with(
            ['Development', 'Staging']
        )
        client.set_project_environments.assert_awaited_once_with(
            project_id='proj_123', env_slugs=['development', 'staging']
        )

    # -- add_project_link ---------------------------------------------

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_add_project_link_with_slug(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='add-link',
            type='imbi',
            command='add_project_link',
            link_definition_slug='github-repository',
            url='https://github.com/test-org/test-project',
        )
        await self.imbi_executor.execute(action)
        client.add_project_link.assert_awaited_once_with(
            project_id='proj_123',
            link_definition_slug='github-repository',
            url='https://github.com/test-org/test-project',
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_add_project_link_renders_url_template(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='add-link',
            type='imbi',
            command='add_project_link',
            link_definition_slug='github-repository',
            url='https://github.com/{{ imbi_project.slug }}',
        )
        await self.imbi_executor.execute(action)
        client.add_project_link.assert_awaited_once_with(
            project_id='proj_123',
            link_definition_slug='github-repository',
            url='https://github.com/test-project',
        )

    # -- add_project_note (creates a document in v2) -------------------

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_add_project_note_creates_document(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='note',
            type='imbi',
            command='add_project_note',
            title='Release Notes',
            content='Body for {{ imbi_project.slug }}',
            tags=['release'],
        )
        await self.imbi_executor.execute(action)
        client.add_project_document.assert_awaited_once_with(
            project_id='proj_123',
            title='Release Notes',
            content='Body for test-project',
            tags=['release'],
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_add_project_note_http_error_propagates(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        client.add_project_document.side_effect = httpx.HTTPError('boom')
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='note',
            type='imbi',
            command='add_project_note',
            title='Title',
            content='Body',
        )
        with self.assertRaises(httpx.HTTPError):
            await self.imbi_executor.execute(action)

    # -- batch_update_facts -------------------------------------------

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_batch_update_facts_calls_set_attributes(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        client = mock.AsyncMock()
        mock_get_instance.return_value = client
        action = models.WorkflowImbiAction(
            name='batch',
            type='imbi',
            command='batch_update_facts',
            facts={'programming_language': 'Python 3.12', 'has_ci': True},
        )
        await self.imbi_executor.execute(action)
        client.set_project_attributes.assert_awaited_once_with(
            project_id='proj_123',
            attributes={'programming_language': 'Python 3.12', 'has_ci': True},
        )

    @mock.patch('imbi_automations.clients.Imbi.get_instance')
    async def test_batch_update_facts_empty_raises(
        self, mock_get_instance: mock.MagicMock
    ) -> None:
        action = models.WorkflowImbiAction(
            name='batch', type='imbi', command='batch_update_facts', facts={}
        )
        with self.assertRaises(ValueError):
            await self.imbi_executor.execute(action)


if __name__ == '__main__':
    unittest.main()
