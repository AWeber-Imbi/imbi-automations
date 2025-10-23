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
        return self.environment_slugs + self.environment_names

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

    @property
    def project_types(self) -> set[str]:
        return self.project_type_names + self.project_type_slugs

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
                st = self.cache_file.stat()
                last_mod = datetime.datetime.fromtimestamp(
                    st.st_mtime, tz=datetime.UTC
                )

                try:
                    data = json.load(file)
                    data['last_updated'] = last_mod
                    self.cache_data = CacheData.model_validate(data)
                except (json.JSONDecodeError, pydantic.ValidationError) as err:
                    LOGGER.warning(
                        'Cache file corrupted, regenerating: %s', err
                    )
                    # Delete corrupted cache file
                    self.cache_file.unlink(missing_ok=True)
                else:
                    # Check if cache is still fresh
                    if not self.is_cache_expired():
                        LOGGER.debug('Using cached Imbi metadata')
                        return

        # Get or create Imbi client for this event loop
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
