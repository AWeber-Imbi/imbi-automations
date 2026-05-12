"""Tests for the v2 Imbi Metadata Cache."""

import datetime
import json
import os
import pathlib
import tempfile
from unittest import mock

from imbi_automations import clients, imc, models
from tests import base


def _env(name: str, slug: str) -> models.ImbiEnvironment:
    return models.ImbiEnvironment(name=name, slug=slug)


def _project_type(name: str, slug: str) -> models.ImbiProjectType:
    return models.ImbiProjectType(name=name, slug=slug)


def _link_def(name: str, slug: str) -> models.ImbiLinkDefinition:
    return models.ImbiLinkDefinition(name=name, slug=slug)


class ImbiMetadataCacheTestCase(base.AsyncTestCase):
    """Tests for :class:`imc.ImbiMetadataCache`."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.ImbiConfiguration(
            organization='test-org',
            base_url='https://imbi.test.com',
            api_key='ik_test',
        )
        self.cache = imc.ImbiMetadataCache()
        self.environments = [
            _env('Production', 'production'),
            _env('Staging', 'staging'),
        ]
        self.project_types = [
            _project_type('API', 'api'),
            _project_type('Consumer', 'consumer'),
        ]
        self.link_definitions = [
            _link_def('GitHub Repository', 'github-repository'),
            _link_def('Grafana Dashboard', 'grafana-dashboard'),
        ]

    # -- Initialization --------------------------------------------------

    def test_init_empty_cache(self) -> None:
        cache = imc.ImbiMetadataCache()
        self.assertIsInstance(cache.cache_data, imc.CacheData)
        self.assertEqual(len(cache.cache_data.environments), 0)
        self.assertEqual(len(cache.cache_data.project_types), 0)
        self.assertEqual(len(cache.cache_data.link_definitions), 0)
        self.assertIsNone(cache.cache_file)
        self.assertIsNone(cache.config)

    def test_is_cache_expired_fresh(self) -> None:
        self.cache.cache_data.last_updated = datetime.datetime.now(
            tz=datetime.UTC
        )
        self.assertFalse(self.cache.is_cache_expired())

    def test_is_cache_expired_old(self) -> None:
        self.cache.cache_data.last_updated = datetime.datetime.now(
            tz=datetime.UTC
        ) - datetime.timedelta(minutes=imc.CACHE_TTL_MINUTES + 1)
        self.assertTrue(self.cache.is_cache_expired())

    # -- Properties ------------------------------------------------------

    def test_environments_property_combines_names_and_slugs(self) -> None:
        self.cache.cache_data.environments = self.environments
        envs = self.cache.environments
        self.assertEqual(
            envs, {'Production', 'production', 'Staging', 'staging'}
        )

    def test_environment_names_property(self) -> None:
        self.cache.cache_data.environments = self.environments
        self.assertEqual(
            self.cache.environment_names, {'Production', 'Staging'}
        )

    def test_environment_slugs_property(self) -> None:
        self.cache.cache_data.environments = self.environments
        self.assertEqual(
            self.cache.environment_slugs, {'production', 'staging'}
        )

    def test_project_types_property_combines_names_and_slugs(self) -> None:
        self.cache.cache_data.project_types = self.project_types
        types = self.cache.project_types
        self.assertEqual(types, {'API', 'api', 'Consumer', 'consumer'})

    def test_project_type_names_property(self) -> None:
        self.cache.cache_data.project_types = self.project_types
        self.assertEqual(self.cache.project_type_names, {'API', 'Consumer'})

    def test_project_type_slugs_property(self) -> None:
        self.cache.cache_data.project_types = self.project_types
        self.assertEqual(self.cache.project_type_slugs, {'api', 'consumer'})

    def test_link_definition_slugs_property(self) -> None:
        self.cache.cache_data.link_definitions = self.link_definitions
        self.assertEqual(
            self.cache.link_definition_slugs,
            {'github-repository', 'grafana-dashboard'},
        )

    # -- Environment translation ----------------------------------------

    def test_translate_environments_by_name_returns_slugs(self) -> None:
        self.cache.cache_data.environments = self.environments
        result = self.cache.translate_environments(['Production', 'Staging'])
        self.assertEqual(result, ['production', 'staging'])

    def test_translate_environments_by_slug_returns_slugs(self) -> None:
        self.cache.cache_data.environments = self.environments
        result = self.cache.translate_environments(['production', 'staging'])
        self.assertEqual(result, ['production', 'staging'])

    def test_translate_environments_mixed(self) -> None:
        self.cache.cache_data.environments = self.environments
        result = self.cache.translate_environments(['Production', 'staging'])
        self.assertEqual(result, ['production', 'staging'])

    def test_translate_environments_not_found(self) -> None:
        self.cache.cache_data.environments = self.environments
        with self.assertRaises(ValueError) as ctx:
            self.cache.translate_environments(['unknown'])
        self.assertIn('Environment not found', str(ctx.exception))

    # -- Cache file operations ------------------------------------------

    def _mock_client(self) -> mock.AsyncMock:
        client = mock.AsyncMock()
        client.get_environments = mock.AsyncMock(
            return_value=self.environments
        )
        client.get_project_types = mock.AsyncMock(
            return_value=self.project_types
        )
        client.get_link_definitions = mock.AsyncMock(
            return_value=self.link_definitions
        )
        return client

    async def test_refresh_from_cache_file_valid_uses_cached_data(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'
            cache_data = imc.CacheData(
                schema_version=imc.CACHE_SCHEMA_VERSION,
                org_slug=self.config.organization,
                environments=self.environments,
                project_types=self.project_types,
                link_definitions=self.link_definitions,
            )
            cache_file.write_text(cache_data.model_dump_json())

            client = self._mock_client()
            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            client.get_environments.assert_not_called()
            self.assertEqual(len(self.cache.cache_data.environments), 2)
            self.assertEqual(len(self.cache.cache_data.project_types), 2)
            self.assertEqual(len(self.cache.cache_data.link_definitions), 2)

    async def test_refresh_from_cache_file_expired_fetches_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'
            cache_data = imc.CacheData(
                schema_version=imc.CACHE_SCHEMA_VERSION,
                org_slug=self.config.organization,
                environments=self.environments,
            )
            cache_file.write_text(cache_data.model_dump_json())

            old = (
                datetime.datetime.now(tz=datetime.UTC)
                - datetime.timedelta(minutes=imc.CACHE_TTL_MINUTES + 5)
            ).timestamp()
            os.utime(cache_file, (old, old))

            client = self._mock_client()
            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            client.get_environments.assert_called_once()
            client.get_project_types.assert_called_once()
            client.get_link_definitions.assert_called_once()

    async def test_refresh_from_cache_org_mismatch_fetches_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'
            cache_data = imc.CacheData(
                schema_version=imc.CACHE_SCHEMA_VERSION,
                org_slug='different-org',
                environments=self.environments,
            )
            cache_file.write_text(cache_data.model_dump_json())

            client = self._mock_client()
            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            client.get_environments.assert_called_once()

    async def test_refresh_from_cache_old_schema_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'
            cache_file.write_text(
                json.dumps(
                    {
                        'schema_version': 1,
                        'org_slug': self.config.organization,
                        'environments': [],
                    }
                )
            )

            client = self._mock_client()
            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            client.get_environments.assert_called_once()

    async def test_refresh_from_cache_file_corrupted_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'
            cache_file.write_text('{ invalid json')

            client = self._mock_client()
            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            client.get_environments.assert_called_once()
            self.assertTrue(cache_file.exists())

    async def test_refresh_from_cache_file_invalid_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'
            cache_file.write_text(
                json.dumps(
                    {
                        'schema_version': imc.CACHE_SCHEMA_VERSION,
                        'org_slug': self.config.organization,
                        'environments': 'not a list',
                    }
                )
            )

            client = self._mock_client()
            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            client.get_environments.assert_called_once()

    async def test_refresh_from_cache_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'

            client = self._mock_client()
            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            client.get_environments.assert_called_once()
            self.assertTrue(cache_file.exists())
            with cache_file.open('r') as f:
                data = json.load(f)
            self.assertEqual(data['schema_version'], imc.CACHE_SCHEMA_VERSION)
            self.assertEqual(data['org_slug'], self.config.organization)
            self.assertEqual(len(data['environments']), 2)
            self.assertEqual(len(data['project_types']), 2)
            self.assertEqual(len(data['link_definitions']), 2)

    async def test_refresh_from_cache_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'subdir' / 'metadata.json'

            client = self._mock_client()
            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            self.assertTrue(cache_file.parent.exists())
            self.assertTrue(cache_file.exists())
