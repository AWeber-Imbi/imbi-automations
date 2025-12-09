"""Tests for Imbi Metadata Cache (IMC)."""

import datetime
import json
import os
import pathlib
import tempfile
from unittest import mock

from imbi_automations import clients, imc, models
from tests import base


class ImbiMetadataCacheTestCase(base.AsyncTestCase):
    """Test cases for ImbiMetadataCache class."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.ImbiConfiguration(
            api_key='test-key', hostname='imbi.example.com'
        )
        self.cache = imc.ImbiMetadataCache()

        # Create sample test data
        self.sample_environments = [
            models.ImbiEnvironment(
                name='Production',
                slug='production',
                icon_class='fa-prod',
                description='Production environment',
            ),
            models.ImbiEnvironment(
                name='Staging',
                slug='staging',
                icon_class='fa-stage',
                description='Staging environment',
            ),
        ]

        self.sample_project_types = [
            models.ImbiProjectType(
                id=1,
                name='API',
                plural_name='APIs',
                slug='api',
                icon_class='fa-api',
                description='API services',
            ),
            models.ImbiProjectType(
                id=2,
                name='Consumer',
                plural_name='Consumers',
                slug='consumer',
                icon_class='fa-consumer',
                description='Message consumers',
            ),
        ]

        self.sample_fact_types = [
            models.ImbiProjectFactType(
                id=1,
                name='Programming Language',
                fact_type='enum',
                data_type='string',
                description='Programming language',
            ),
            models.ImbiProjectFactType(
                id=2,
                name='Test Coverage',
                fact_type='range',
                data_type='integer',
                description='Test coverage percentage',
            ),
            models.ImbiProjectFactType(
                id=3,
                name='Has Tests',
                fact_type='free-form',
                data_type='boolean',
                description='Has automated tests',
            ),
            models.ImbiProjectFactType(
                id=4,
                name='API Version',
                fact_type='free-form',
                data_type='decimal',
                description='API version number',
            ),
        ]

        self.sample_fact_type_enums = [
            models.ImbiProjectFactTypeEnum(
                id=1, fact_type_id=1, value='Python 3.12', score=10
            ),
            models.ImbiProjectFactTypeEnum(
                id=2, fact_type_id=1, value='Python 3.11', score=8
            ),
            models.ImbiProjectFactTypeEnum(
                id=3, fact_type_id=1, value='Go 1.21', score=10
            ),
        ]

        self.sample_fact_type_ranges = [
            models.ImbiProjectFactTypeRange(
                id=1, fact_type_id=2, min_value=80, max_value=100, score=10
            ),
            models.ImbiProjectFactTypeRange(
                id=2, fact_type_id=2, min_value=60, max_value=79, score=5
            ),
        ]

    # Initialization Tests

    def test_init_empty_cache(self) -> None:
        """Test that cache initializes with empty data."""
        cache = imc.ImbiMetadataCache()
        self.assertIsInstance(cache.cache_data, imc.CacheData)
        self.assertEqual(len(cache.cache_data.environments), 0)
        self.assertEqual(len(cache.cache_data.project_types), 0)
        self.assertEqual(len(cache.cache_data.project_fact_types), 0)
        self.assertIsNone(cache.cache_file)
        self.assertIsNone(cache.config)

    def test_is_cache_expired_fresh(self) -> None:
        """Test cache expiry check for fresh cache."""
        cache = imc.ImbiMetadataCache()
        cache.cache_data.last_updated = datetime.datetime.now(tz=datetime.UTC)
        self.assertFalse(cache.is_cache_expired())

    def test_is_cache_expired_old(self) -> None:
        """Test cache expiry check for expired cache."""
        cache = imc.ImbiMetadataCache()
        cache.cache_data.last_updated = datetime.datetime.now(
            tz=datetime.UTC
        ) - datetime.timedelta(minutes=imc.CACHE_TTL_MINUTES + 1)
        self.assertTrue(cache.is_cache_expired())

    # Property Tests

    def test_environments_property(self) -> None:
        """Test environments property returns both names and slugs."""
        self.cache.cache_data.environments = self.sample_environments
        envs = self.cache.environments
        self.assertIn('Production', envs)
        self.assertIn('production', envs)
        self.assertIn('Staging', envs)
        self.assertIn('staging', envs)
        self.assertEqual(len(envs), 4)

    def test_environment_names_property(self) -> None:
        """Test environment_names property returns only names."""
        self.cache.cache_data.environments = self.sample_environments
        names = self.cache.environment_names
        self.assertIn('Production', names)
        self.assertIn('Staging', names)
        self.assertNotIn('production', names)
        self.assertEqual(len(names), 2)

    def test_environment_slugs_property(self) -> None:
        """Test environment_slugs property returns only slugs."""
        self.cache.cache_data.environments = self.sample_environments
        slugs = self.cache.environment_slugs
        self.assertIn('production', slugs)
        self.assertIn('staging', slugs)
        self.assertNotIn('Production', slugs)
        self.assertEqual(len(slugs), 2)

    def test_project_types_property(self) -> None:
        """Test project_types property returns both names and slugs."""
        self.cache.cache_data.project_types = self.sample_project_types
        types = self.cache.project_types
        self.assertIn('API', types)
        self.assertIn('api', types)
        self.assertIn('Consumer', types)
        self.assertIn('consumer', types)
        self.assertEqual(len(types), 4)

    def test_project_type_names_property(self) -> None:
        """Test project_type_names property returns only names."""
        self.cache.cache_data.project_types = self.sample_project_types
        names = self.cache.project_type_names
        self.assertIn('API', names)
        self.assertIn('Consumer', names)
        self.assertNotIn('api', names)
        self.assertEqual(len(names), 2)

    def test_project_type_slugs_property(self) -> None:
        """Test project_type_slugs property returns only slugs."""
        self.cache.cache_data.project_types = self.sample_project_types
        slugs = self.cache.project_type_slugs
        self.assertIn('api', slugs)
        self.assertIn('consumer', slugs)
        self.assertNotIn('API', slugs)
        self.assertEqual(len(slugs), 2)

    def test_project_fact_type_names_property(self) -> None:
        """Test project_fact_type_names property returns fact type names."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        names = self.cache.project_fact_type_names
        self.assertIn('Programming Language', names)
        self.assertIn('Test Coverage', names)
        self.assertEqual(len(names), 4)

    def test_project_fact_type_values(self) -> None:
        """Test project_fact_type_values returns enum values for fact type."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        self.cache.cache_data.project_fact_type_enums = (
            self.sample_fact_type_enums
        )

        values = self.cache.project_fact_type_values('Programming Language')
        self.assertIn('Python 3.12', values)
        self.assertIn('Python 3.11', values)
        self.assertIn('Go 1.21', values)
        self.assertEqual(len(values), 3)

    def test_project_fact_type_values_not_found(self) -> None:
        """Test project_fact_type_values returns empty set for unknown fact."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        values = self.cache.project_fact_type_values('Unknown Fact')
        self.assertEqual(len(values), 0)

    # Fact Type Retrieval Tests

    def test_get_project_fact_type_found(self) -> None:
        """Test get_project_fact_type returns fact type when found."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        fact_type = self.cache.get_project_fact_type('Programming Language')
        self.assertIsNotNone(fact_type)
        self.assertEqual(fact_type.name, 'Programming Language')
        self.assertEqual(fact_type.fact_type, 'enum')

    def test_get_project_fact_type_not_found(self) -> None:
        """Test get_project_fact_type returns None when not found."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        fact_type = self.cache.get_project_fact_type('Unknown Fact')
        self.assertIsNone(fact_type)

    # Fact Value Validation Tests

    def test_validate_project_fact_value_enum_valid(self) -> None:
        """Test validation of valid enum fact value."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        self.cache.cache_data.project_fact_type_enums = (
            self.sample_fact_type_enums
        )

        result = self.cache.validate_project_fact_value(
            'Programming Language', 'Python 3.12'
        )
        self.assertTrue(result)

    def test_validate_project_fact_value_enum_invalid(self) -> None:
        """Test validation of invalid enum fact value."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        self.cache.cache_data.project_fact_type_enums = (
            self.sample_fact_type_enums
        )

        result = self.cache.validate_project_fact_value(
            'Programming Language', 'Ruby 3.0'
        )
        self.assertFalse(result)

    def test_validate_project_fact_value_enum_number_as_string(self) -> None:
        """Test enum validation converts numbers to strings."""
        # Add a numeric enum value
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        self.cache.cache_data.project_fact_type_enums = [
            models.ImbiProjectFactTypeEnum(
                id=1, fact_type_id=1, value='100', score=10
            )
        ]

        result = self.cache.validate_project_fact_value(
            'Programming Language', 100
        )
        self.assertTrue(result)

    def test_validate_project_fact_value_range_valid(self) -> None:
        """Test validation of valid range fact value."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        self.cache.cache_data.project_fact_type_ranges = (
            self.sample_fact_type_ranges
        )

        result = self.cache.validate_project_fact_value('Test Coverage', 85)
        self.assertTrue(result)

    def test_validate_project_fact_value_range_invalid_low(self) -> None:
        """Test validation of range value below minimum."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        self.cache.cache_data.project_fact_type_ranges = (
            self.sample_fact_type_ranges
        )

        result = self.cache.validate_project_fact_value('Test Coverage', 50)
        self.assertFalse(result)

    def test_validate_project_fact_value_range_invalid_high(self) -> None:
        """Test validation of range value above maximum."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        self.cache.cache_data.project_fact_type_ranges = (
            self.sample_fact_type_ranges
        )

        result = self.cache.validate_project_fact_value('Test Coverage', 101)
        self.assertFalse(result)

    def test_validate_project_fact_value_range_no_ranges(self) -> None:
        """Test validation of range value when no ranges defined."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        self.cache.cache_data.project_fact_type_ranges = []

        result = self.cache.validate_project_fact_value('Test Coverage', 85)
        self.assertFalse(result)

    def test_validate_project_fact_value_range_non_numeric(self) -> None:
        """Test validation of non-numeric value for range fact."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types
        self.cache.cache_data.project_fact_type_ranges = (
            self.sample_fact_type_ranges
        )

        result = self.cache.validate_project_fact_value(
            'Test Coverage', 'not a number'
        )
        self.assertFalse(result)

    def test_validate_project_fact_value_boolean_valid(self) -> None:
        """Test validation of valid boolean fact value."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types

        result = self.cache.validate_project_fact_value('Has Tests', True)
        self.assertTrue(result)

    def test_validate_project_fact_value_boolean_invalid(self) -> None:
        """Test validation of invalid boolean fact value."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types

        result = self.cache.validate_project_fact_value('Has Tests', 'true')
        self.assertFalse(result)

    def test_validate_project_fact_value_free_form_integer(self) -> None:
        """Test validation of integer free-form fact value."""
        fact_type = models.ImbiProjectFactType(
            id=10,
            name='Port Number',
            fact_type='free-form',
            data_type='integer',
        )
        self.cache.cache_data.project_fact_types = [fact_type]

        result = self.cache.validate_project_fact_value('Port Number', 8080)
        self.assertTrue(result)

        result = self.cache.validate_project_fact_value('Port Number', 8080.5)
        self.assertFalse(result)

    def test_validate_project_fact_value_free_form_decimal(self) -> None:
        """Test validation of decimal free-form fact value."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types

        result = self.cache.validate_project_fact_value('API Version', 1.5)
        self.assertTrue(result)

        result = self.cache.validate_project_fact_value('API Version', 2)
        self.assertTrue(result)

        result = self.cache.validate_project_fact_value('API Version', 'v1.5')
        self.assertFalse(result)

    def test_validate_project_fact_value_free_form_string(self) -> None:
        """Test validation of string free-form fact value."""
        fact_type = models.ImbiProjectFactType(
            id=10,
            name='Description',
            fact_type='free-form',
            data_type='string',
        )
        self.cache.cache_data.project_fact_types = [fact_type]

        result = self.cache.validate_project_fact_value(
            'Description', 'Test description'
        )
        self.assertTrue(result)

        result = self.cache.validate_project_fact_value('Description', 123)
        self.assertFalse(result)

    def test_validate_project_fact_value_unknown_fact(self) -> None:
        """Test validation of unknown fact type."""
        self.cache.cache_data.project_fact_types = self.sample_fact_types

        result = self.cache.validate_project_fact_value(
            'Unknown Fact', 'value'
        )
        self.assertFalse(result)

    # Environment Translation Tests

    def test_translate_environments_by_name(self) -> None:
        """Test translating environments by name."""
        self.cache.cache_data.environments = self.sample_environments
        result = self.cache.translate_environments(['Production', 'Staging'])
        self.assertEqual(result, ['Production', 'Staging'])

    def test_translate_environments_by_slug(self) -> None:
        """Test translating environments by slug."""
        self.cache.cache_data.environments = self.sample_environments
        result = self.cache.translate_environments(['production', 'staging'])
        self.assertEqual(result, ['Production', 'Staging'])

    def test_translate_environments_mixed(self) -> None:
        """Test translating mixed environment names and slugs."""
        self.cache.cache_data.environments = self.sample_environments
        result = self.cache.translate_environments(['Production', 'staging'])
        self.assertEqual(result, ['Production', 'Staging'])

    def test_translate_environments_not_found(self) -> None:
        """Test translating unknown environment raises ValueError."""
        self.cache.cache_data.environments = self.sample_environments
        with self.assertRaises(ValueError) as ctx:
            self.cache.translate_environments(['unknown'])
        self.assertIn('Environment not found', str(ctx.exception))

    # Cache File Operations Tests

    async def test_refresh_from_cache_file_valid(self) -> None:
        """Test refreshing cache from valid cache file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'

            # Write valid cache data
            cache_data = imc.CacheData(
                environments=self.sample_environments,
                project_types=self.sample_project_types,
                project_fact_types=self.sample_fact_types,
                project_fact_type_enums=self.sample_fact_type_enums,
                project_fact_type_ranges=self.sample_fact_type_ranges,
            )
            with cache_file.open('w') as f:
                f.write(cache_data.model_dump_json())

            await self.cache.refresh_from_cache(cache_file, self.config)

            self.assertEqual(len(self.cache.cache_data.environments), 2)
            self.assertEqual(len(self.cache.cache_data.project_types), 2)
            self.assertEqual(len(self.cache.cache_data.project_fact_types), 4)

    async def test_refresh_from_cache_file_expired(self) -> None:
        """Test refreshing from expired cache triggers API fetch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'

            # Write cache data
            cache_data = imc.CacheData(environments=self.sample_environments)
            with cache_file.open('w') as f:
                f.write(cache_data.model_dump_json())

            # Make file old to trigger expiration
            old_time = (
                datetime.datetime.now(tz=datetime.UTC)
                - datetime.timedelta(minutes=imc.CACHE_TTL_MINUTES + 5)
            ).timestamp()
            cache_file.touch()
            cache_file.chmod(0o644)
            os.utime(cache_file, (old_time, old_time))

            # Mock Imbi client
            mock_client = mock.AsyncMock()
            mock_client.get_environments = mock.AsyncMock(
                return_value=self.sample_environments
            )
            mock_client.get_project_types = mock.AsyncMock(
                return_value=self.sample_project_types
            )
            mock_client.get_project_fact_types = mock.AsyncMock(
                return_value=self.sample_fact_types
            )
            mock_client.get_project_fact_type_enums = mock.AsyncMock(
                return_value=self.sample_fact_type_enums
            )
            mock_client.get_project_fact_type_ranges = mock.AsyncMock(
                return_value=self.sample_fact_type_ranges
            )

            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=mock_client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            # Verify API was called
            mock_client.get_environments.assert_called_once()
            mock_client.get_project_types.assert_called_once()

    async def test_refresh_from_cache_file_corrupted_json(self) -> None:
        """Test refreshing from corrupted JSON file triggers API fetch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'

            # Write invalid JSON
            with cache_file.open('w') as f:
                f.write('{ invalid json')

            # Mock Imbi client
            mock_client = mock.AsyncMock()
            mock_client.get_environments = mock.AsyncMock(
                return_value=self.sample_environments
            )
            mock_client.get_project_types = mock.AsyncMock(
                return_value=self.sample_project_types
            )
            mock_client.get_project_fact_types = mock.AsyncMock(
                return_value=self.sample_fact_types
            )
            mock_client.get_project_fact_type_enums = mock.AsyncMock(
                return_value=self.sample_fact_type_enums
            )
            mock_client.get_project_fact_type_ranges = mock.AsyncMock(
                return_value=self.sample_fact_type_ranges
            )

            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=mock_client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            # Verify API was called and file was deleted
            mock_client.get_environments.assert_called_once()
            self.assertTrue(cache_file.exists())  # New cache written

    async def test_refresh_from_cache_file_invalid_data(self) -> None:
        """Test refreshing from file with invalid schema triggers API fetch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'

            # Write data that will fail Pydantic validation
            # (environments should be list, not string)
            with cache_file.open('w') as f:
                json.dump(
                    {'environments': 'not a list', 'project_types': []}, f
                )

            # Mock Imbi client
            mock_client = mock.AsyncMock()
            mock_client.get_environments = mock.AsyncMock(
                return_value=self.sample_environments
            )
            mock_client.get_project_types = mock.AsyncMock(
                return_value=self.sample_project_types
            )
            mock_client.get_project_fact_types = mock.AsyncMock(
                return_value=self.sample_fact_types
            )
            mock_client.get_project_fact_type_enums = mock.AsyncMock(
                return_value=self.sample_fact_type_enums
            )
            mock_client.get_project_fact_type_ranges = mock.AsyncMock(
                return_value=self.sample_fact_type_ranges
            )

            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=mock_client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            # Verify API was called
            mock_client.get_environments.assert_called_once()

    async def test_refresh_from_cache_no_file(self) -> None:
        """Test refreshing when cache file doesn't exist fetches from API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'metadata.json'

            # Mock Imbi client
            mock_client = mock.AsyncMock()
            mock_client.get_environments = mock.AsyncMock(
                return_value=self.sample_environments
            )
            mock_client.get_project_types = mock.AsyncMock(
                return_value=self.sample_project_types
            )
            mock_client.get_project_fact_types = mock.AsyncMock(
                return_value=self.sample_fact_types
            )
            mock_client.get_project_fact_type_enums = mock.AsyncMock(
                return_value=self.sample_fact_type_enums
            )
            mock_client.get_project_fact_type_ranges = mock.AsyncMock(
                return_value=self.sample_fact_type_ranges
            )

            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=mock_client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            # Verify API was called and cache file was created
            mock_client.get_environments.assert_called_once()
            self.assertTrue(cache_file.exists())

            # Verify written data
            with cache_file.open('r') as f:
                data = json.load(f)
            self.assertEqual(len(data['environments']), 2)
            self.assertEqual(len(data['project_types']), 2)

    async def test_refresh_from_cache_creates_parent_directory(self) -> None:
        """Test that refresh creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = pathlib.Path(tmpdir) / 'subdir' / 'metadata.json'

            # Mock Imbi client
            mock_client = mock.AsyncMock()
            mock_client.get_environments = mock.AsyncMock(
                return_value=self.sample_environments
            )
            mock_client.get_project_types = mock.AsyncMock(
                return_value=self.sample_project_types
            )
            mock_client.get_project_fact_types = mock.AsyncMock(
                return_value=self.sample_fact_types
            )
            mock_client.get_project_fact_type_enums = mock.AsyncMock(
                return_value=self.sample_fact_type_enums
            )
            mock_client.get_project_fact_type_ranges = mock.AsyncMock(
                return_value=self.sample_fact_type_ranges
            )

            with mock.patch.object(
                clients.Imbi, 'get_instance', return_value=mock_client
            ):
                await self.cache.refresh_from_cache(cache_file, self.config)

            # Verify parent directory was created
            self.assertTrue(cache_file.parent.exists())
            self.assertTrue(cache_file.exists())
