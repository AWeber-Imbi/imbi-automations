"""Project filtering and targeting logic for workflow execution.

Provides filtering capabilities to target specific subsets of projects
based on IDs, types, facts, GitHub identifiers, and workflow statuses for
efficient batch processing.
"""

import logging
import re

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
        self.workflow = workflow
        self._set_workflow_logger(workflow)

    async def filter_project(
        self,
        project: models.ImbiProject,
        workflow_filter: models.WorkflowFilter | None,
    ) -> models.ImbiProject | None:
        """Filter projects based on workflow configuration

        project_ids: set[int] = pydantic.Field(default_factory=set)
        project_types: set[str] = pydantic.Field(default_factory=set)
        project_facts: dict[str, bool | int | float | str] = (
            pydantic.Field(default_factory=dict)
        )
        project_environments: set[str] = pydantic.Field(default_factory=set)
        github_identifier_required: bool = False
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
            or (
                workflow_filter.project
                and not self._filter_project_fields(project, workflow_filter)
            )
        ):
            return None

        # Dynamic Filters Should happen _after_ easily applied ones

        if workflow_filter.github_workflow_status_exclude:
            status = await self._filter_github_action_status(project)
            if status in workflow_filter.github_workflow_status_exclude:
                return None

        # Check for open workflow PRs
        if workflow_filter.exclude_open_workflow_prs:
            has_open_pr = await self._filter_open_workflow_pr(
                project, workflow_filter
            )
            if has_open_pr:
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
    ) -> str | None:
        client = clients.GitHub.get_instance(config=self.configuration)
        repository = await client.get_repository(project)
        if repository is None:
            return None
        return await client.get_repository_workflow_status(repository)

    async def _filter_open_workflow_pr(
        self,
        project: models.ImbiProject,
        workflow_filter: models.WorkflowFilter,
    ) -> bool:
        """Check if project has open PRs for the workflow.

        Returns:
            True if project should be EXCLUDED (has open PRs)
            False if project should be included (no open PRs)

        """
        # Determine workflow slug to check
        workflow_slug: str
        if isinstance(workflow_filter.exclude_open_workflow_prs, str):
            workflow_slug = workflow_filter.exclude_open_workflow_prs
        elif workflow_filter.exclude_open_workflow_prs is True:
            workflow_slug = self.workflow.slug
        else:
            return False

        # Get GitHub repository
        client = clients.GitHub.get_instance(config=self.configuration)
        repository = await client.get_repository(project)

        if repository is None:
            LOGGER.debug(
                'No GitHub repository found for project %s, allowing',
                project.slug,
            )
            return False

        org, repo_name = repository.full_name.split('/', 1)
        branch_name = f'imbi-automations/{workflow_slug}'

        try:
            # List PRs with matching branch
            pull_requests = await client.list_pull_requests(
                org=org, repo=repo_name, state='all', head=branch_name
            )

            # Check for blocking PR states
            for pr in pull_requests:
                pr_head_branch = (
                    pr.head.get('ref') if isinstance(pr.head, dict) else None
                )

                if pr_head_branch != branch_name:
                    continue

                # Exclude if open (including drafts)
                if pr.state == 'open':
                    LOGGER.debug(
                        'Project %s has open PR #%d (draft=%s), excluding',
                        project.slug,
                        pr.number,
                        pr.draft,
                    )
                    return True

                # Exclude if closed but not merged
                if pr.state == 'closed' and not pr.merged:
                    LOGGER.debug(
                        'Project %s has closed unmerged PR #%d, excluding',
                        project.slug,
                        pr.number,
                    )
                    return True

            return False

        except (ValueError, KeyError, AttributeError, TypeError) as exc:
            # Fail-open: allow project on errors parsing PR data
            LOGGER.warning(
                'Error checking PRs for project %s: %s. Allowing project.',
                project.slug,
                exc,
            )
            return False

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

    @staticmethod
    def _filter_project_fields(
        project: models.ImbiProject, workflow_filter: models.WorkflowFilter
    ) -> models.ImbiProject | None:
        """Filter projects based on arbitrary field conditions.

        Supports various operators: is_null, is_not_null, equals, not_equals,
        contains, regex, and is_empty.
        """
        for field_name, field_filter in workflow_filter.project.items():
            # Get the field value from the project
            if not hasattr(project, field_name):
                LOGGER.warning(
                    'Project field "%s" does not exist, skipping filter',
                    field_name,
                )
                return None

            field_value = getattr(project, field_name)

            # Apply the filter operator
            if field_filter.is_null is not None:
                if field_filter.is_null and field_value is not None:
                    LOGGER.debug(
                        'Field %s is not null (value: %s)',
                        field_name,
                        field_value,
                    )
                    return None
                if not field_filter.is_null and field_value is None:
                    LOGGER.debug('Field %s is null', field_name)
                    return None

            elif field_filter.is_not_null is not None:
                if field_filter.is_not_null and field_value is None:
                    LOGGER.debug('Field %s is null', field_name)
                    return None
                if not field_filter.is_not_null and field_value is not None:
                    LOGGER.debug(
                        'Field %s is not null (value: %s)',
                        field_name,
                        field_value,
                    )
                    return None

            elif field_filter.is_empty is not None:
                is_empty = field_value is None or (
                    isinstance(field_value, str) and field_value.strip() == ''
                )
                if field_filter.is_empty and not is_empty:
                    LOGGER.debug(
                        'Field %s is not empty (value: %s)',
                        field_name,
                        field_value,
                    )
                    return None
                if not field_filter.is_empty and is_empty:
                    LOGGER.debug('Field %s is empty', field_name)
                    return None

            elif field_filter.equals is not None:
                if field_value != field_filter.equals:
                    LOGGER.debug(
                        'Field %s value "%s" does not equal "%s"',
                        field_name,
                        field_value,
                        field_filter.equals,
                    )
                    return None

            elif field_filter.not_equals is not None:
                if field_value == field_filter.not_equals:
                    LOGGER.debug(
                        'Field %s value "%s" equals "%s" (expected not equal)',
                        field_name,
                        field_value,
                        field_filter.not_equals,
                    )
                    return None

            elif field_filter.contains is not None:
                if not isinstance(field_value, str):
                    LOGGER.debug(
                        'Field %s is not a string (type: %s)',
                        field_name,
                        type(field_value),
                    )
                    return None
                if field_filter.contains not in field_value:
                    LOGGER.debug(
                        'Field %s value "%s" does not contain "%s"',
                        field_name,
                        field_value,
                        field_filter.contains,
                    )
                    return None

            elif field_filter.regex is not None:
                if not isinstance(field_value, str):
                    LOGGER.debug(
                        'Field %s is not a string (type: %s)',
                        field_name,
                        type(field_value),
                    )
                    return None
                try:
                    if not re.search(field_filter.regex, field_value):
                        LOGGER.debug(
                            'Field %s value "%s" does not match regex "%s"',
                            field_name,
                            field_value,
                            field_filter.regex,
                        )
                        return None
                except re.error as exc:
                    LOGGER.error(
                        'Invalid regex pattern "%s": %s',
                        field_filter.regex,
                        exc,
                    )
                    return None

        return project
