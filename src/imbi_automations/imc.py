"""Imbi Metadata Cache for loading and caching Imbi metadata.

Caches per-organization environments, project types, link definitions,
and tags. Blueprint-defined project attributes are no longer cached
here — they vary per project and are resolved against the merged
schema at runtime via :meth:`Imbi.get_project_schema`.
"""

import asyncio
import datetime
import json
import logging
import pathlib

import pydantic

from imbi_automations import clients
from imbi_automations.models import configuration, imbi

LOGGER = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 15
CACHE_SCHEMA_VERSION = 2


class CacheData(pydantic.BaseModel):
    """On-disk cache shape.

    ``schema_version`` is bumped whenever the cache layout changes;
    older files are discarded automatically rather than re-keyed.
    """

    schema_version: int = CACHE_SCHEMA_VERSION
    org_slug: str = ''
    last_updated: datetime.datetime = pydantic.Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC)
    )
    environments: list[imbi.ImbiEnvironment] = []
    project_types: list[imbi.ImbiProjectType] = []
    link_definitions: list[imbi.ImbiLinkDefinition] = []


class ImbiMetadataCache:
    """Cache for Imbi metadata with TTL-based refresh."""

    def __init__(self) -> None:
        self.cache_data: CacheData = CacheData()
        self.cache_file: pathlib.Path | None = None
        self.config: configuration.ImbiConfiguration | None = None
        self.imbi_client: clients.Imbi | None = None

    def is_cache_expired(self) -> bool:
        """Return True if the cache has aged past the TTL."""
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
    def project_types(self) -> set[str]:
        return self.project_type_names.union(self.project_type_slugs)

    @property
    def project_type_names(self) -> set[str]:
        return {pt.name for pt in self.cache_data.project_types}

    @property
    def project_type_slugs(self) -> set[str]:
        return {pt.slug for pt in self.cache_data.project_types}

    @property
    def link_definition_slugs(self) -> set[str]:
        return {ld.slug for ld in self.cache_data.link_definitions}

    def translate_environments(self, values: list[str]) -> list[str]:
        """Map environment identifiers (slug or name) to canonical slugs.

        The API addresses environments by slug on JSON Patch paths
        (``/environments/<slug>``), so we normalize names → slugs here.

        Raises:
            ValueError: If any environment is not found in the cache.

        """
        result: list[str] = []
        for value in values:
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
            result.append(env.slug)
        return result

    async def refresh_from_cache(
        self, cache_file: pathlib.Path, config: configuration.ImbiConfiguration
    ) -> None:
        """Initialize and refresh cache from file or API."""
        self.cache_file = cache_file
        self.config = config

        if self.cache_file.exists():
            data = self._load_cache_file()
            if data is not None and self._cache_matches(data):
                self.cache_data = data
                if not self.is_cache_expired():
                    LOGGER.debug('Using cached Imbi metadata')
                    return

        if not self.imbi_client:
            self.imbi_client = clients.Imbi.get_instance(config=self.config)

        LOGGER.info(
            'Fetching fresh Imbi metadata from API for org %s',
            config.organization,
        )
        environments, project_types, link_definitions = await asyncio.gather(
            self.imbi_client.get_environments(),
            self.imbi_client.get_project_types(),
            self.imbi_client.get_link_definitions(),
        )
        self.cache_data = CacheData(
            org_slug=config.organization,
            environments=environments,
            project_types=project_types,
            link_definitions=link_definitions,
        )
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_file.open('w') as file:
            file.write(self.cache_data.model_dump_json())
        LOGGER.debug('Cached Imbi metadata to %s', self.cache_file)

    def _load_cache_file(self) -> CacheData | None:
        if self.cache_file is None:
            return None
        with self.cache_file.open('r') as file:
            try:
                payload = json.load(file)
            except json.JSONDecodeError as err:
                LOGGER.warning('Cache file corrupted, regenerating: %s', err)
                self.cache_file.unlink(missing_ok=True)
                return None
        if payload.get('schema_version') != CACHE_SCHEMA_VERSION:
            LOGGER.info(
                'Discarding cache with schema version %s != %d',
                payload.get('schema_version'),
                CACHE_SCHEMA_VERSION,
            )
            self.cache_file.unlink(missing_ok=True)
            return None
        last_mod = datetime.datetime.fromtimestamp(
            self.cache_file.stat().st_mtime, tz=datetime.UTC
        )
        payload['last_updated'] = last_mod
        try:
            return CacheData.model_validate(payload)
        except pydantic.ValidationError as err:
            LOGGER.warning('Cache file corrupted, regenerating: %s', err)
            self.cache_file.unlink(missing_ok=True)
            return None

    def _cache_matches(self, data: CacheData) -> bool:
        return (
            self.config is not None
            and data.org_slug == self.config.organization
        )
