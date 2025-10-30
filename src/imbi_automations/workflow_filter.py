"""Project filtering and targeting logic for workflow execution.

Provides filtering capabilities to target specific subsets of projects
based on IDs, types, facts, GitHub identifiers, and workflow statuses for
efficient batch processing.
"""

import logging

from imbi_automations import clients, mixins, models

LOGGER = logging.getLogger(__name__)


class Filter(mixins.WorkflowLoggerMixin):
    """Filter for workflows and actions."""

    def __init__(
        self,
        configuration: models.Configuration,
        workflow: models.Workflow,
        verbose: bool,
    ) -> None:
        super().__init__(verbose)
        self.configuration = configuration
        self._set_workflow_logger(workflow)

    async def filter_project(
        self,
        project: models.ImbiProject,
        workflow_filter: models.WorkflowFilter | None,
    ) -> models.ImbiProject | None:
        """Filter projects based on workflow configuration

        project_ids: set[int] = pydantic.Field(default_factory=set)
        project_types: set[str] = pydantic.Field(default_factory=set)
        project_facts: dict[str, str] = pydantic.Field(default_factory=dict)
        project_environments: set[str] = pydantic.Field(default_factory=set)
        requires_github_identifier: bool = False
        exclude_github_workflow_status: set[str] = pydantic.Field(
            default_factory=set
        )

        """
        if workflow_filter is None:
            return project

        if (
            (
                workflow_filter.github_identifier_required
                and self.configuration.imbi
                and (
                    not project.identifiers
                    or not project.identifiers.get(
                        self.configuration.imbi.github_identifier
                    )
                )
            )
            or (
                workflow_filter.project_ids
                and project.id not in workflow_filter.project_ids
            )
            or (
                workflow_filter.project_environments
                and not self._filter_environments(project, workflow_filter)
            )
            or (
                workflow_filter.project_facts
                and not self._filter_project_facts(project, workflow_filter)
            )
            or (
                workflow_filter.project_types
                and project.project_type_slug
                not in workflow_filter.project_types
            )
        ):
            return None

        # Dynamic Filters Should happen _after_ easily applied ones

        if workflow_filter.github_workflow_status_exclude:
            status = await self._filter_github_action_status(project)
            if status in workflow_filter.github_workflow_status_exclude:
                return None

        return project

    @staticmethod
    def _filter_environments(
        project: models.ImbiProject, workflow_filter: models.WorkflowFilter
    ) -> models.ImbiProject | None:
        """Filter projects based on environments.

        Checks against both environment name and slug to support both
        'Production' and 'production' in configuration.
        """
        if not project.environments:
            return None
        for env in workflow_filter.project_environments:
            # Check if filter value matches any environment name or slug
            if env not in [
                e.name for e in project.environments
            ] and env not in [e.slug for e in project.environments]:
                return None
        return project

    async def _filter_github_action_status(
        self, project: models.ImbiProject
    ) -> str:
        client = clients.GitHub.get_instance(config=self.configuration.github)
        repository = await client.get_repository(project)
        return await client.get_repository_workflow_status(repository)

    @staticmethod
    def _filter_project_facts(
        project: models.ImbiProject, workflow_filter: models.WorkflowFilter
    ) -> models.ImbiProject | None:
        """Filter projects based on project facts."""
        if not project.facts:
            return None
        for name, value in workflow_filter.project_facts.items():
            LOGGER.debug('Validating %s is %s', name, value)
            # OpenSearch facts are lowercased and underscore delimited
            slug = name.lower().replace(' ', '_')
            if project.facts.get(slug) != value:
                LOGGER.debug(
                    'Project fact %s value of "%s" is not "%s"',
                    name,
                    project.facts.get(slug),
                    value,
                )
                return None
        return project
