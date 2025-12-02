"""Imbi Metadata Cache for loading and caching Imbi data."""

import asyncio
import datetime
import json
import logging
import pathlib

import pydantic

from imbi_automations import clients
from imbi_automations.models import configuration, imbi

LOGGER = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_MINUTES = 15


class CacheData(pydantic.BaseModel):
    """Cache for data used by the application"""

    last_updated: datetime.datetime = pydantic.Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC)
    )
    environments: list[imbi.ImbiEnvironment] = []
    project_fact_types: list[imbi.ImbiProjectFactType] = []
    project_fact_type_enums: list[imbi.ImbiProjectFactTypeEnum] = []
    project_fact_type_ranges: list[imbi.ImbiProjectFactTypeRange] = []
    project_types: list[imbi.ImbiProjectType] = []


class ImbiMetadataCache:
    """Cache for Imbi metadata with automatic refresh.

    Cache is always populated (empty collections if not refreshed).
    Call refresh_from_cache() to load data from disk or API.
    """

    def __init__(self) -> None:
        """Initialize cache instance with empty data.

        Cache starts with empty collections and can be used immediately.
        Call refresh_from_cache() to populate with actual metadata.
        """
        self.cache_data: CacheData = CacheData()
        self.cache_file: pathlib.Path | None = None
        self.config: configuration.ImbiConfiguration | None = None
        self.imbi_client: clients.Imbi | None = None

    def is_cache_expired(self) -> bool:
        """Check if cache has expired (older than CACHE_TTL_MINUTES)."""
        age = (
            datetime.datetime.now(tz=datetime.UTC)
            - self.cache_data.last_updated
        )
        return age > datetime.timedelta(minutes=CACHE_TTL_MINUTES)

    @property
    def environments(self) -> set[str]:
        return self.environment_slugs.union(self.environment_names)

    @property
    def environment_names(self) -> set[str]:
        return {env.name for env in self.cache_data.environments}

    @property
    def environment_slugs(self) -> set[str]:
        return {env.slug for env in self.cache_data.environments}

    @property
    def project_fact_type_names(self) -> set[str]:
        return {datum.name for datum in self.cache_data.project_fact_types}

    def project_fact_type_values(self, name: str) -> set[str]:
        fact_type_ids = {
            datum.id
            for datum in self.cache_data.project_fact_types
            if datum.name == name
        }
        LOGGER.debug('Fact Type IDs: %s', fact_type_ids)
        return {
            datum.value
            for datum in self.cache_data.project_fact_type_enums
            if datum.fact_type_id in fact_type_ids
        }

    def get_project_fact_type(
        self, name: str
    ) -> imbi.ImbiProjectFactType | None:
        """Get the ImbiProjectFactType for a given fact type name.

        Args:
            name: The name of the fact type

        Returns:
            The ImbiProjectFactType if found, None otherwise

        """
        return next(
            (
                fact_type
                for fact_type in self.cache_data.project_fact_types
                if fact_type.name == name
            ),
            None,
        )

    def validate_project_fact_value(
        self, name: str, value: bool | int | float | str
    ) -> bool:
        """Validate a project fact value against its type definition.

        Args:
            name: The name of the fact type
            value: The value to validate

        Returns:
            True if the value is valid for the fact type

        """
        fact_type = self.get_project_fact_type(name)
        if not fact_type:
            return False

        # For boolean data types, validate boolean values
        if fact_type.data_type == 'boolean':
            return isinstance(value, bool)

        # For enum fact types, check against allowed values
        if fact_type.fact_type == 'enum':
            enum_values = self.project_fact_type_values(name)
            # Convert value to string for comparison with enum values
            return str(value) in enum_values

        # For range fact types, check against min/max values
        if fact_type.fact_type == 'range':
            fact_type_ranges = [
                r
                for r in self.cache_data.project_fact_type_ranges
                if r.fact_type_id == fact_type.id
            ]
            if not fact_type_ranges:
                return False
            # Check if value falls within any of the defined ranges
            if isinstance(value, int | float):
                return any(
                    r.min_value <= value <= r.max_value
                    for r in fact_type_ranges
                )
            return False

        # For free-form fact types, validate against data type
        if fact_type.fact_type == 'free-form':
            if fact_type.data_type == 'integer':
                return isinstance(value, int)
            if fact_type.data_type == 'decimal':
                return isinstance(value, int | float)
            if fact_type.data_type == 'string':
                return isinstance(value, str)
            # Other data types like date, timestamp need more parsing
            return True

        return False

    @property
    def project_types(self) -> set[str]:
        return self.project_type_names.union(self.project_type_slugs)

    @property
    def project_type_names(self) -> set[str]:
        return {
            project_type.name for project_type in self.cache_data.project_types
        }

    @property
    def project_type_slugs(self) -> set[str]:
        return {
            project_type.slug for project_type in self.cache_data.project_types
        }

    def translate_environments(self, values: list[str]) -> list[str]:
        """Translate environment names or slugs to environment names.

        Accepts a list of environment identifiers (names or slugs, mixed
        allowed) and returns the corresponding environment names required
        by the Imbi API.

        Args:
            values: List of environment names or slugs

        Returns:
            List of environment names for Imbi API

        Raises:
            ValueError: If any environment not found in cache

        """
        result = []
        for value in values:
            # Try to find environment by slug or name
            env = next(
                (
                    e
                    for e in self.cache_data.environments
                    if e.slug == value or e.name == value
                ),
                None,
            )
            if not env:
                raise ValueError(f'Environment not found in cache: {value}')
            result.append(env.name)
        return result

    async def refresh_from_cache(
        self, cache_file: pathlib.Path, config: configuration.ImbiConfiguration
    ) -> None:
        """Initialize and refresh cache from file or API.

        Args:
            cache_file: Path to the metadata cache file
            config: Imbi configuration for API access

        """
        self.cache_file = cache_file
        self.config = config
        if self.cache_file.exists():
            with self.cache_file.open('r') as file:
                last_mod = datetime.datetime.fromtimestamp(
                    self.cache_file.stat().st_mtime, tz=datetime.UTC
                )
                try:
                    data = json.load(file)
                except json.JSONDecodeError as err:
                    LOGGER.warning(
                        'Cache file corrupted, regenerating: %s', err
                    )
                    self.cache_file.unlink(missing_ok=True)
                else:
                    data['last_updated'] = last_mod
                    try:
                        self.cache_data = CacheData.model_validate(data)
                    except pydantic.ValidationError as err:
                        LOGGER.warning(
                            'Cache file corrupted, regenerating: %s', err
                        )
                        self.cache_file.unlink(missing_ok=True)
                    else:
                        if not self.is_cache_expired():
                            LOGGER.debug('Using cached Imbi metadata')
                            return

        if not self.imbi_client:
            self.imbi_client = clients.Imbi.get_instance(config=self.config)

        LOGGER.info('Fetching fresh Imbi metadata from API')
        (
            environments,
            project_fact_types,
            project_fact_type_enums,
            project_fact_type_ranges,
            project_types,
        ) = await asyncio.gather(
            self.imbi_client.get_environments(),
            self.imbi_client.get_project_fact_types(),
            self.imbi_client.get_project_fact_type_enums(),
            self.imbi_client.get_project_fact_type_ranges(),
            self.imbi_client.get_project_types(),
        )
        self.cache_data = CacheData(
            environments=environments,
            project_fact_types=project_fact_types,
            project_fact_type_enums=project_fact_type_enums,
            project_fact_type_ranges=project_fact_type_ranges,
            project_types=project_types,
        )
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_file.open('w') as file:
            file.write(self.cache_data.model_dump_json())
        LOGGER.debug('Cached Imbi metadata to %s', self.cache_file)
