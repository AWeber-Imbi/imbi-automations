"""Imbi project management system API client.

Provides integration with the Imbi project management system API for
retrieving projects, project types, environments, and other project
metadata used throughout the automation workflows.
"""

import copy
import logging
import typing

import async_lru
import httpx

from imbi_automations import models

from . import http

LOGGER = logging.getLogger(__name__)


class Imbi(http.BaseURLHTTPClient):
    """Imbi project management system API client.

    Provides access to the Imbi API for retrieving projects, project
    types, environments, facts, and other project metadata used for
    workflow targeting and context enrichment. Supports OpenSearch-based
    project queries.
    """

    def __init__(
        self,
        config: models.ImbiConfiguration,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(transport=transport)
        self._base_url = f'https://{config.hostname}'
        self.add_header('Private-Token', config.api_key.get_secret_value())

    @async_lru.alru_cache(maxsize=1)
    async def get_environments(self) -> list[models.ImbiEnvironment]:
        """Get all project fact types.

        Returns:
            List of all project fact types

        Raises:
            httpx.HTTPError: If API request fails

        """
        response = await self.get('/environments')
        response.raise_for_status()
        return [
            models.ImbiEnvironment.model_validate(datum)
            for datum in response.json()
        ]

    async def get_project(self, project_id: int) -> models.ImbiProject | None:
        result = await self._opensearch_projects(
            self._search_project_id(project_id)
        )
        return result[0] if result else None

    async def get_project_fact_type_enums(
        self,
    ) -> list[models.ImbiProjectFactTypeEnum]:
        """Get all of the project fact types.

        Returns:
            List of project fact type enums

        Raises:
            httpx.HTTPError: If API request fails

        """
        response = await self.get('/project-fact-type-enums')
        response.raise_for_status()
        return [
            models.ImbiProjectFactTypeEnum.model_validate(fact)
            for fact in response.json()
        ]

    async def get_project_fact_type_id_by_name(
        self, fact_name: str
    ) -> int | None:
        """Get fact type ID by name.

        Args:
            fact_name: Name of the fact type

        Returns:
            Fact type ID or None if not found

        """
        fact_types = await self.get_project_fact_types()
        for fact_type in fact_types:
            if fact_type.name == fact_name:
                return fact_type.id
        return None

    async def get_project_fact_type_ranges(
        self,
    ) -> list[models.ImbiProjectFactTypeRange]:
        """Get all of the project fact types.

        Returns:
            List of project fact type ranges

        Raises:
            httpx.HTTPError: If API request fails

        """
        response = await self.get('/project-fact-type-ranges')
        response.raise_for_status()
        return [
            models.ImbiProjectFactTypeRange.model_validate(fact)
            for fact in response.json()
        ]

    async def get_project_fact_types(self) -> list[models.ImbiProjectFactType]:
        """Get all of the project fact types.

        Returns:
            List of project fact types

        Raises:
            httpx.HTTPError: If API request fails

        """
        response = await self.get('/project-fact-types')
        response.raise_for_status()
        return [
            models.ImbiProjectFactType.model_validate(fact)
            for fact in response.json()
        ]

    async def get_project_fact_value(
        self, project_id: int, fact_name: str
    ) -> str | None:
        """Get current value of a specific project fact.

        Args:
            project_id: Imbi project ID
            fact_name: Name of the fact to retrieve

        Returns:
            Current fact value or None if not set

        """
        facts = await self.get_project_facts(project_id)
        for fact in facts:
            if fact.fact_name == fact_name:
                return str(fact.value) if fact.value is not None else None
        return None

    async def get_project_facts(
        self, project_id: int
    ) -> list[models.ImbiProjectFact]:
        """Get all facts for a project.

        Args:
            project_id: Imbi project ID

        Returns:
            List of project facts

        Raises:
            httpx.HTTPError: If API request fails

        """
        response = await self.get(f'/projects/{project_id}/facts')
        response.raise_for_status()
        return [
            models.ImbiProjectFact.model_validate(fact)
            for fact in response.json()
        ]

    async def get_project_types(self) -> list[models.ImbiProjectType]:
        """Get all project types.

        Returns:
            List of all project types

        Raises:
            httpx.HTTPError: If API request fails

        """
        response = await self.get('/project-types')
        response.raise_for_status()
        return [
            models.ImbiProjectType.model_validate(project_type)
            for project_type in response.json()
        ]

    async def get_projects(self) -> list[models.ImbiProject]:
        """Get all active Imbi projects.

        Returns:
            List of all active Imbi projects

        """
        all_projects = []
        page_size = 100
        start_from = 0

        while True:
            query = self._opensearch_payload()
            query['query'] = {'match': {'archived': False}}
            query['from'] = start_from
            query['size'] = page_size

            page_projects = await self._opensearch_projects(query)
            if not page_projects:
                break

            all_projects.extend(page_projects)
            start_from += page_size

            # Break if we got fewer results than page_size (last page)
            if len(page_projects) < page_size:
                break

        LOGGER.debug('Found %d total active projects', len(all_projects))

        # Sort by project slug for deterministic results
        all_projects.sort(key=lambda project: project.slug)

        return all_projects

    async def get_projects_by_type(
        self, project_type_slug: str
    ) -> list[models.ImbiProject]:
        """Get all projects of a specific project type using slug."""
        all_projects = []
        page_size = 100  # OpenSearch default is usually 10, increase to 100
        start_from = 0

        while True:
            query = self._search_project_type_slug(project_type_slug)
            # Add pagination parameters
            query['from'] = start_from
            query['size'] = page_size

            LOGGER.debug(
                'Fetching projects page: from=%d, size=%d, slug=%s',
                start_from,
                page_size,
                project_type_slug,
            )

            page_results = await self._opensearch_projects(query)

            if not page_results:
                # No more results
                break

            all_projects.extend(page_results)

            # If we got fewer results than page_size, we've reached the end
            if len(page_results) < page_size:
                break

            start_from += page_size

        LOGGER.debug(
            'Found %d total projects with project_type_slug: %s',
            len(all_projects),
            project_type_slug,
        )

        # Sort by project slug for deterministic results
        all_projects.sort(key=lambda project: project.slug)

        return all_projects

    async def search_projects_by_github_url(
        self, github_url: str
    ) -> list[models.ImbiProject]:
        """Search for Imbi projects by GitHub repository URL in project links.

        Args:
            github_url: GitHub repository URL to search for

        Returns:
            List of matching Imbi projects

        """
        query = self._opensearch_payload()
        query['query'] = {
            'bool': {
                'must': [
                    {'match': {'archived': False}},
                    {
                        'nested': {
                            'path': 'links',
                            'query': {
                                'bool': {
                                    'must': [
                                        {'match': {'links.url': github_url}}
                                    ]
                                }
                            },
                        }
                    },
                ]
            }
        }
        return await self._opensearch_projects(query)

    async def update_project_fact(
        self,
        project_id: int,
        fact_name: str | None = None,
        fact_type_id: int | None = None,
        value: bool | int | float | str | None = None,
        skip_validations: bool = False,
    ) -> None:
        """Update a single project fact by name or ID.

        Args:
            project_id: Imbi project ID
            fact_name: Name of the fact to update (alternative to fact_type_id)
            fact_type_id: ID of the fact type (alternative to fact_name)
            value: New value for the fact, or "unset" to remove the fact
            skip_validations: Skip project type and current value validations

        Raises:
            ValueError: If neither fact_name nor fact_type_id provided
            httpx.HTTPError: If API request fails

        """
        if not fact_name and not fact_type_id:
            raise ValueError(
                'Either fact_name or fact_type_id must be provided'
            )

        # If fact_name is provided, look up the fact_type_id
        if fact_name and not fact_type_id:
            fact_type_id = await self.get_project_fact_type_id_by_name(
                fact_name
            )
            if not fact_type_id:
                raise ValueError(f'Fact type not found: {fact_name}')

        # Perform enhanced validations unless explicitly skipped
        if not skip_validations:
            # Get project information to validate project type compatibility
            project = await self.get_project(project_id)
            if not project:
                raise ValueError(f'Project not found: {project_id}')

            # Validate that the fact type supports this project's type
            fact_types = await self.get_project_fact_types()
            fact_type = next(
                (ft for ft in fact_types if ft.id == fact_type_id), None
            )

            if fact_type and fact_type.project_type_ids:
                # Get project type ID from project_type_slug
                project_types = await self.get_project_types()
                project_type = next(
                    (
                        pt
                        for pt in project_types
                        if pt.slug == project.project_type_slug
                    ),
                    None,
                )

                if (
                    project_type
                    and project_type.id not in fact_type.project_type_ids
                ):
                    LOGGER.debug(
                        'Skipping fact update for project %d (%s) - '
                        'fact type "%s" not supported for project type "%s"',
                        project_id,
                        project.name,
                        fact_name or fact_type_id,
                        project.project_type_slug,
                    )
                    return

            # Check if current value is the same to avoid unnecessary updates
            current_value = await self.get_project_fact_value(
                project_id, fact_name or str(fact_type_id)
            )

            # Convert values to strings for comparison (API stores as strings)
            current_str = (
                str(current_value) if current_value is not None else None
            )
            new_str = str(value) if value is not None else None

            if current_str == new_str:
                LOGGER.debug(
                    'Skipping fact update for project %d - '
                    'value unchanged (%s = %s)',
                    project_id,
                    fact_name or fact_type_id,
                    value,
                )
                return

        # Handle "null" value by setting to null
        if value == 'null':
            LOGGER.debug(
                'Setting fact %s to null for project %d',
                fact_name or fact_type_id,
                project_id,
            )
            # Skip null updates if Imbi doesn't support them (avoid 400 errors)
            LOGGER.warning(
                'Skipping null fact update for project %d', project_id
            )
            return

        LOGGER.debug(
            'Updating fact %s to %s for project %d (fact_type_id=%s)',
            fact_name or fact_type_id,
            value,
            project_id,
            fact_type_id,
        )

        payload = [{'fact_type_id': fact_type_id, 'value': value}]
        LOGGER.debug('Sending payload: %s', payload)
        response = await self.post(
            f'/projects/{project_id}/facts', json=payload
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                error_body = response.text
            except (AttributeError, UnicodeDecodeError):
                error_body = '<unable to read response body>'
            LOGGER.error(
                'Failed to update fact %s for project %d: HTTP %d - %s',
                fact_name or fact_type_id,
                project_id,
                response.status_code,
                error_body,
            )
            raise

    async def update_project_facts(
        self,
        project_id: int,
        facts: list[tuple[int, bool | int | float | str]],
    ) -> None:
        """Update multiple project facts in a single request.

        Args:
            project_id: Imbi project ID
            facts: List of (fact_type_id, value) tuples

        Raises:
            httpx.HTTPError: If API request fails

        """
        payload = [
            {'fact_type_id': fact_type_id, 'value': value}
            for fact_type_id, value in facts
        ]
        LOGGER.debug(
            'Sending facts payload for project %d: %s', project_id, payload
        )
        response = await self.post(
            f'/projects/{project_id}/facts', json=payload
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                error_body = response.text
            except (AttributeError, UnicodeDecodeError):
                error_body = '<unable to read response body>'
            LOGGER.error(
                'Failed to update facts for project %d: HTTP %d - %s',
                project_id,
                response.status_code,
                error_body,
            )
            raise

    async def delete_project_fact(
        self,
        project_id: int,
        fact_name: str | None = None,
        fact_type_id: int | None = None,
    ) -> bool:
        """Delete a project fact by setting its value to null.

        Args:
            project_id: Imbi project ID
            fact_name: Name of the fact to delete (alternative to fact_type_id)
            fact_type_id: ID of the fact type (alternative to fact_name)

        Returns:
            True if fact was deleted, False if fact didn't exist

        Raises:
            ValueError: If neither fact_name nor fact_type_id provided
            httpx.HTTPError: If API request fails

        """
        if not fact_name and not fact_type_id:
            raise ValueError(
                'Either fact_name or fact_type_id must be provided'
            )

        # If fact_name is provided, look up the fact_type_id
        if fact_name and not fact_type_id:
            fact_type_id = await self.get_project_fact_type_id_by_name(
                fact_name
            )
            if not fact_type_id:
                raise ValueError(f'Fact type not found: {fact_name}')

        # Check if fact currently exists
        current_value = await self.get_project_fact_value(
            project_id, fact_name or str(fact_type_id)
        )
        if current_value is None:
            LOGGER.debug(
                'Fact %s not set for project %d, nothing to delete',
                fact_name or fact_type_id,
                project_id,
            )
            return False

        LOGGER.debug(
            'Deleting fact %s for project %d (fact_type_id=%s)',
            fact_name or fact_type_id,
            project_id,
            fact_type_id,
        )

        # Delete by sending empty value
        response = await self.delete(
            f'/projects/{project_id}/facts/{fact_type_id}'
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            # 404 means fact doesn't exist, which is fine for delete
            if response.status_code == 404:
                return False
            try:
                error_body = response.text
            except (AttributeError, UnicodeDecodeError):
                error_body = '<unable to read response body>'
            LOGGER.error(
                'Failed to delete fact %s for project %d: HTTP %d - %s',
                fact_name or fact_type_id,
                project_id,
                response.status_code,
                error_body,
            )
            raise
        return True

    async def add_project_link(
        self, project_id: int, link_type: str, url: str
    ) -> None:
        """Add a link to a project.

        Args:
            project_id: Imbi project ID
            link_type: Type of link (e.g., 'Repository', 'Documentation')
            url: URL for the link

        Raises:
            ValueError: If link_type not found
            httpx.HTTPError: If API request fails

        """
        # Get link type ID from name
        link_types = await self.get_link_types()
        link_type_obj = next(
            (lt for lt in link_types if lt.name == link_type), None
        )
        if not link_type_obj:
            raise ValueError(f'Link type not found: {link_type}')

        LOGGER.debug(
            'Adding %s link to project %d: %s', link_type, project_id, url
        )

        payload = {'link_type_id': link_type_obj.id, 'url': url}
        response = await self.post(
            f'/projects/{project_id}/links', json=payload
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                error_body = response.text
            except (AttributeError, UnicodeDecodeError):
                error_body = '<unable to read response body>'
            LOGGER.error(
                'Failed to add link to project %d: HTTP %d - %s',
                project_id,
                response.status_code,
                error_body,
            )
            raise

    async def get_link_types(self) -> list[models.ImbiLinkType]:
        """Get all link types.

        Returns:
            List of link types

        Raises:
            httpx.HTTPError: If API request fails

        """
        response = await self.get('/project-link-types')
        response.raise_for_status()
        return [
            models.ImbiLinkType.model_validate(link_type)
            for link_type in response.json()
        ]

    async def update_project_type(
        self, project_id: int, project_type_slug: str
    ) -> None:
        """Update the project type for a project.

        Args:
            project_id: Imbi project ID
            project_type_slug: Slug of the new project type

        Raises:
            ValueError: If project not found or project type not found
            httpx.HTTPError: If API request fails

        """
        # Verify project exists
        project = await self.get_project(project_id)
        if not project:
            raise ValueError(f'Project not found: {project_id}')

        # Skip if already the same type
        if project.project_type_slug == project_type_slug:
            LOGGER.debug(
                'Project %d already has project_type_slug %s, skipping',
                project_id,
                project_type_slug,
            )
            return

        # Verify project type exists
        project_types = await self.get_project_types()
        project_type = next(
            (pt for pt in project_types if pt.slug == project_type_slug), None
        )
        if not project_type:
            raise ValueError(f'Project type not found: {project_type_slug}')

        LOGGER.debug(
            'Updating project %d type from %s to %s',
            project_id,
            project.project_type_slug,
            project_type_slug,
        )

        payload = [
            {
                'op': 'replace',
                'path': '/project_type_id',
                'value': project_type.id,
            }
        ]
        response = await self.patch(f'/projects/{project_id}', json=payload)

        if response.status_code == 304:
            LOGGER.debug(
                'Project type already set for project %d (HTTP 304)',
                project_id,
            )
            return

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                error_body = response.text
            except (AttributeError, UnicodeDecodeError):
                error_body = '<unable to read response body>'
            LOGGER.error(
                'Failed to update project type for project %d: HTTP %d - %s',
                project_id,
                response.status_code,
                error_body,
            )
            raise

    async def update_project_environments(
        self, project_id: int, environments: list[str]
    ) -> None:
        """Update environments for a project using JSON Patch.

        Args:
            project_id: Imbi project ID
            environments: List of environment names (e.g., ["Testing"])

        Raises:
            httpx.HTTPError: If API request fails

        """
        # Get current project data to check existing environments
        project = await self.get_project(project_id)
        if not project:
            raise ValueError(f'Project not found: {project_id}')

        # Extract current environment names
        current_env_names = (
            sorted([env.name for env in project.environments])
            if project.environments
            else []
        )
        new_env_names = sorted(environments)

        # Skip update if environments are unchanged
        if current_env_names == new_env_names:
            LOGGER.debug(
                'Environments unchanged for project %d, skipping update',
                project_id,
            )
            return

        LOGGER.debug(
            'Updating environments for project %d from %s to %s',
            project_id,
            current_env_names,
            new_env_names,
        )

        payload = [
            {'op': 'replace', 'path': '/environments', 'value': environments}
        ]
        response = await self.patch(f'/projects/{project_id}', json=payload)

        # HTTP 304 Not Modified is success (no changes needed)
        if response.status_code == 304:
            LOGGER.debug(
                'Environments already set for project %d (HTTP 304)',
                project_id,
            )
            return

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                error_body = response.text
            except (AttributeError, UnicodeDecodeError):
                error_body = '<unable to read response body>'
            LOGGER.error(
                'Failed to update environments for project %d: HTTP %d - %s',
                project_id,
                response.status_code,
                error_body,
            )
            raise

    async def update_project_attributes(
        self, project_id: int, attributes: dict[str, typing.Any]
    ) -> None:
        """Update project attributes using JSON Patch.

        Generic method for updating any project attributes. Constructs JSON
        Patch operations for changed attributes, skipping unchanged values.

        Args:
            project_id: Imbi project ID
            attributes: Dict of attribute names to new values. Keys should
                match ImbiProject model field names (e.g., 'description',
                'name', etc.). Values support any JSON-serializable type.

        Raises:
            ValueError: If project not found or no attributes provided
            httpx.HTTPError: If API request fails

        Example:
            await client.update_project_attributes(
                project_id=123,
                attributes={
                    'description': 'New description',
                    'name': 'Updated Name',
                }
            )

        """
        if not attributes:
            raise ValueError('attributes dict cannot be empty')

        # Get current project data to check existing values
        project = await self.get_project(project_id)
        if not project:
            raise ValueError(f'Project not found: {project_id}')

        # Build JSON Patch operations for changed attributes
        patch_ops = []
        for attr_name, new_value in attributes.items():
            # Get current value from project (use getattr for safety)
            current_value = getattr(project, attr_name, None)

            # Skip if value unchanged
            if current_value == new_value:
                LOGGER.debug(
                    'Attribute "%s" unchanged for project %d, skipping',
                    attr_name,
                    project_id,
                )
                continue

            LOGGER.debug(
                'Updating %s for project %d from "%s" to "%s"',
                attr_name,
                project_id,
                current_value,
                new_value,
            )

            patch_ops.append(
                {'op': 'replace', 'path': f'/{attr_name}', 'value': new_value}
            )

        # Skip API call if no changes needed
        if not patch_ops:
            LOGGER.debug(
                'No attribute changes for project %d, skipping update',
                project_id,
            )
            return

        LOGGER.debug(
            'Sending PATCH to project %d with %d operations: %s',
            project_id,
            len(patch_ops),
            patch_ops,
        )

        response = await self.patch(f'/projects/{project_id}', json=patch_ops)

        # HTTP 304 Not Modified is success (no changes needed)
        if response.status_code == 304:
            LOGGER.debug(
                'Attributes already set for project %d (HTTP 304)', project_id
            )
            return

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                error_body = response.text
            except (AttributeError, UnicodeDecodeError):
                error_body = '<unable to read response body>'
            LOGGER.error(
                'Failed to update attributes for project %d: HTTP %d - %s',
                project_id,
                response.status_code,
                error_body,
            )
            raise

    async def update_project_github_identifier(
        self, project_id: int, identifier_name: str, value: int | str | None
    ) -> None:
        """Update GitHub identifier for a project only if different.

        Args:
            project_id: Imbi project ID
            identifier_name: Name of the identifier (typically "github")
            value: New identifier value

        Raises:
            httpx.HTTPError: If API request fails

        """
        # Get current project data to check existing identifier
        project = await self.get_project(project_id)
        if not project:
            raise ValueError(f'Project not found: {project_id}')

        current_value = None
        if project.identifiers and identifier_name in project.identifiers:
            current_value = project.identifiers[identifier_name]

        # Convert both values to integers for comparison if possible
        try:
            current_int = (
                int(current_value) if current_value is not None else None
            )
            new_int = int(value) if value is not None else None

            if current_int == new_int:
                LOGGER.debug(
                    'Identifier %s unchanged for project %d, skipping update',
                    identifier_name,
                    project_id,
                )
                return
        except (ValueError, TypeError):
            # Fall back to string comparison if conversion fails
            current_str = (
                str(current_value) if current_value is not None else None
            )
            new_str = str(value) if value is not None else None

            if current_str == new_str:
                LOGGER.debug(
                    'Identifier %s unchanged for project %d, skipping update',
                    identifier_name,
                    project_id,
                )
                return

        LOGGER.info(
            'Updating %s identifier from %s to %s for project %d (%s)',
            identifier_name,
            current_value,
            value,
            project_id,
            project.name,
        )

        # Update identifier via API
        if value is None:
            # Delete identifier
            response = await self.delete(
                f'/projects/{project_id}/identifiers/{identifier_name}'
            )
        elif current_value is None:
            # Create new identifier
            payload = {
                'integration_name': identifier_name,
                'external_id': str(value),
            }
            response = await self.post(
                f'/projects/{project_id}/identifiers', json=payload
            )
        else:
            # Update existing identifier using JSON Patch
            payload = [
                {'op': 'replace', 'path': '/external_id', 'value': str(value)}
            ]
            response = await self.patch(
                f'/projects/{project_id}/identifiers/{identifier_name}',
                json=payload,
            )

        response.raise_for_status()

    async def _add_imbi_url(
        self, project: dict[str, typing.Any]
    ) -> models.ImbiProject:
        value = project['_source'].copy()
        value['imbi_url'] = f'{self.base_url}/ui/projects/{value["id"]}'
        environments = set({})
        imbi_environments = await self.get_environments()
        for environment in value.get('environments') or []:
            for imbi_environment in imbi_environments:
                if (
                    environment == imbi_environment.name
                    or environment == imbi_environment.slug
                ):
                    environments.add(imbi_environment)
        if environments:
            value['environments'] = environments
        return models.ImbiProject.model_validate(value)

    async def _opensearch_projects(
        self, query: dict[str, typing.Any]
    ) -> list[models.ImbiProject]:
        try:
            data = await self._opensearch_request(
                '/opensearch/projects', query
            )
        except (httpx.RequestError, httpx.HTTPStatusError) as err:
            LOGGER.error(
                'Error searching Imbi projects: Request error %s', err
            )
            return []
        if not data or 'hits' not in data or 'hits' not in data['hits']:
            return []
        projects = []
        for project in data['hits']['hits']:
            projects.append(await self._add_imbi_url(project))
        return projects

    def _search_project_id(self, value: int) -> dict[str, typing.Any]:
        """Return a query payload for searching by project ID."""
        payload = self._opensearch_payload()
        payload['query'] = {
            'bool': {'filter': [{'term': {'_id': f'{value}'}}]}
        }
        return payload

    def _search_project_type_slug(self, value: str) -> dict[str, typing.Any]:
        """Return a query payload for searching by project_type_slug."""
        payload = self._opensearch_payload()
        payload['query'] = {
            'bool': {
                'must': [
                    {'match': {'archived': False}},
                    {'term': {'project_type_slug.keyword': value}},
                ]
            }
        }
        return payload

    def _search_projects(self, value: str) -> dict[str, typing.Any]:
        payload = self._opensearch_payload()
        slug_value = value.lower().replace(' ', '-')
        payload['query'] = {
            'bool': {
                'must': [{'match': {'archived': False}}],
                'should': [
                    {
                        'term': {
                            'name': {'value': value, 'case_insensitive': True}
                        }
                    },
                    {'fuzzy': {'name': {'value': value}}},
                    {'match_phrase': {'name': {'query': value}}},
                    {
                        'term': {
                            'slug': {
                                'value': slug_value,
                                'case_insensitive': True,
                            }
                        }
                    },
                ],
                'minimum_should_match': 1,
            }
        }
        return payload

    @staticmethod
    def _opensearch_payload() -> dict[str, typing.Any]:
        return copy.deepcopy(
            {
                '_source': {
                    'exclude': ['archived', 'component_versions', 'components']
                },
                'query': {'bool': {'must': {'term': {'archived': False}}}},
            }
        )

    async def _opensearch_request(
        self, url: str, query: dict[str, typing.Any]
    ) -> dict[str, typing.Any]:
        LOGGER.debug('Query: %r', query)
        response = await self.post(url, json=query)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            LOGGER.error('Error searching Imbi projects: %s', err)
            LOGGER.debug('Response: %r', response.content)
            raise err
        try:
            return response.json() if response.content else {}
        except ValueError as err:
            LOGGER.error('Error deserializing the response: %s', err)
            raise err
