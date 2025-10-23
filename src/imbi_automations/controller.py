"""Main automation controller for executing workflows across projects.

The controller implements an iterator pattern for processing different
target types (GitHub repositories, Imbi projects) with workflow execution,
concurrency control, and comprehensive error handling.
"""

import argparse
import asyncio
import collections
import enum
import logging

import async_lru

from imbi_automations import (
    clients,
    imc,
    mixins,
    models,
    per_project_logging,
    workflow_engine,
    workflow_filter,
)

LOGGER = logging.getLogger(__name__)


class AutomationIterator(enum.Enum):
    """Enumeration of automation target types.

    Defines supported iteration patterns for GitHub repositories and Imbi
    project types and projects.
    """

    github_repositories = 1
    github_organization = 2
    github_project = 3
    imbi_project_type = 4
    imbi_project = 5
    imbi_projects = 6


class Automation(mixins.WorkflowLoggerMixin):
    """Main automation controller for executing workflows across projects.

    Orchestrates workflow execution with iterator pattern support for
    different target types, project filtering, concurrency control, and
    resumable processing.
    """

    def __init__(
        self,
        args: argparse.Namespace,
        config: models.Configuration,
        workflow: models.Workflow,
    ) -> None:
        super().__init__(args.verbose)
        self.args = args
        self.configuration = config
        self.counter = collections.Counter()
        self.logger = LOGGER
        self.registry = imc.ImbiMetadataCache()
        self.workflow = workflow
        self.workflow_engine = workflow_engine.WorkflowEngine(
            config=self.configuration, workflow=workflow, verbose=args.verbose
        )
        self.workflow_filter = workflow_filter.Filter(
            config, workflow, args.verbose
        )
        self._set_workflow_logger(workflow)

    @property
    def iterator(self) -> AutomationIterator:
        """Determine the iterator type based on CLI arguments.

        Returns:
            AutomationIterator enum value corresponding to the target type

        """
        if self.args.resume:
            # Resume mode doesn't use iterator pattern
            return None  # type: ignore[return-value]
        elif self.args.project_id:
            return AutomationIterator.imbi_project
        elif self.args.project_type:
            return AutomationIterator.imbi_project_type
        elif self.args.all_projects:
            return AutomationIterator.imbi_projects
        elif self.args.github_repository:
            return AutomationIterator.github_project
        elif self.args.github_organization:
            return AutomationIterator.github_organization
        elif self.args.all_github_repositories:
            return AutomationIterator.github_repositories
        else:
            raise ValueError('No valid target argument provided')

    async def run(self) -> bool:
        # Initialize Imbi metadata cache
        cache_file = self.configuration.cache_dir / 'metadata.json'
        await self.registry.refresh_from_cache(
            cache_file, self.configuration.imbi
        )

        # Handle resume mode separately
        if self.args.resume:
            return await self._resume_from_state()

        self._validate_workflow_filters()
        match self.iterator:
            case AutomationIterator.github_repositories:
                return await self._process_github_repositories()
            case AutomationIterator.github_organization:
                return await self._process_github_organization()
            case AutomationIterator.github_project:
                return await self._process_github_project()
            case AutomationIterator.imbi_project_type:
                return await self._process_imbi_project_type()
            case AutomationIterator.imbi_project:
                return await self._process_imbi_project()
            case AutomationIterator.imbi_projects:
                return await self._process_imbi_projects()

    async def _resume_from_state(self) -> bool:
        """Resume workflow from preserved error state.

        Returns:
            True if workflow completed successfully, False otherwise

        Raises:
            RuntimeError: If .state file not found or workflow incompatible

        """
        state_file = self.args.resume / '.state'

        if not state_file.exists():
            raise RuntimeError(
                f'No .state file found in {self.args.resume}. '
                f'Expected: {state_file}'
            )

        # Load and validate state
        try:
            state = models.ResumeState.from_msgpack(state_file.read_bytes())
        except Exception as exc:
            raise RuntimeError(
                f'Failed to load resume state from {state_file}: {exc}'
            ) from exc

        self.logger.info(
            'Resuming workflow "%s" for project %s from action "%s" '
            '(index %d)',
            state.workflow_slug,
            state.project_slug,
            state.failed_action_name,
            state.failed_action_index,
        )

        # Validate workflow compatibility
        if state.workflow_path != self.workflow.path:
            self.logger.warning(
                'Resume state workflow path (%s) differs from current (%s)',
                state.workflow_path,
                self.workflow.path,
            )

        # Warn about config changes
        from imbi_automations import utils

        current_hash = utils.hash_configuration(self.configuration)
        if state.configuration_hash != current_hash:
            self.logger.warning(
                'Configuration has changed since error occurred. '
                'Resume may behave unexpectedly.'
            )

        # Load the Imbi project
        client = clients.Imbi.get_instance(config=self.configuration.imbi)
        project = await client.get_project(state.project_id)

        # Create workflow engine with resume state
        engine = workflow_engine.WorkflowEngine(
            config=self.configuration,
            workflow=self.workflow,
            verbose=self.args.verbose,
            resume_state=state,
        )

        # Execute with resume
        success = await engine.execute(project, state.github_repository)

        if success:
            self.logger.info(
                'Successfully resumed and completed workflow for %s',
                state.project_slug,
            )
        else:
            self.logger.error(
                'Workflow resume failed for %s', state.project_slug
            )

        return success

    async def _filter_projects(
        self, projects: list[models.ImbiProject]
    ) -> list[models.ImbiProject]:
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
        if not self.workflow_filter:
            return projects

        original_count = len(projects)
        semaphore = asyncio.Semaphore(self.args.max_concurrency)

        async def filter_project(
            project: models.ImbiProject,
        ) -> models.ImbiProject | None:
            async with semaphore:
                return await self.workflow_filter.filter_project(
                    project, self.workflow.configuration.filter
                )

        projects = [
            project
            for project in await asyncio.gather(
                *[filter_project(project) for project in projects]
            )
            if project is not None
        ]
        self.logger.debug(
            'Filtered %d projects out of %d total',
            original_count - len(projects),
            original_count,
        )
        return projects

    @async_lru.alru_cache(maxsize=1024)
    async def _get_github_repository(
        self, project: models.ImbiProject
    ) -> models.GitHubRepository | None:
        if not self.configuration.github:
            return None
        client = clients.GitHub.get_instance(config=self.configuration)
        return await client.get_repository(project)

    async def _process_github_repositories(self) -> bool: ...

    async def _process_github_organization(self) -> bool: ...

    async def _process_github_project(self) -> bool: ...

    async def _process_imbi_project(self) -> bool:
        client = clients.Imbi.get_instance(config=self.configuration.imbi)
        project = await client.get_project(self.args.project_id)
        return await self._process_workflow_from_imbi_project(project)

    async def _process_imbi_project_type(self) -> bool:
        # Validate project type slug if cache available
        self._validate_project_type_slug(self.args.project_type)

        client = clients.Imbi.get_instance(config=self.configuration.imbi)
        projects = await client.get_projects_by_type(self.args.project_type)
        self.logger.debug('Found %d total active projects', len(projects))
        return await self._process_imbi_projects_common(projects)

    def _validate_workflow_filters(self) -> None:
        """Validate workflow filters against cache if available."""
        if not self.workflow.configuration.filter:
            return
        wfilter = self.workflow.configuration.filter
        LOGGER.debug('Validating workflow filters: %r', wfilter.model_dump())

        LOGGER.debug(
            '%r > %r = %r',
            wfilter.project_types,
            self.registry.project_type_slugs,
            wfilter.project_types <= self.registry.project_type_slugs,
        )

        if (
            wfilter.project_types
            and wfilter.project_types - self.registry.project_type_slugs
        ):
            missing = wfilter.project_types - self.registry.project_type_slugs
            invalid = ', '.join(missing)
            if len(missing) > 1:
                raise RuntimeError(f'{invalid} are not valid project types')
            raise RuntimeError(f'{invalid} is not a valid project type')

        if (
            wfilter.project_environments
            and {env.lower() for env in wfilter.project_environments}
            - self.registry.environments
        ):
            missing = {
                env.lower() for env in wfilter.project_environments
            } - self.registry.environments
            invalid = ', '.join(missing)
            if len(missing) > 1:
                raise RuntimeError(f'{invalid} are not valid environments')
            raise RuntimeError(f'{invalid} is not a valid environment')

        # Skip out early if no project facts are specified
        if not wfilter.project_facts:
            return

        # First check all the keys
        fact_names = set(wfilter.project_facts.keys())
        if fact_names - self.registry.project_fact_type_names:
            missing = fact_names - self.registry.project_fact_type_names
            invalid = ', '.join(missing)
            if len(missing) > 1:
                raise RuntimeError(
                    f'{invalid} are not valid project fact types'
                )
            raise RuntimeError(f'{invalid} is not a valid project fact type')

        # Check the values
        for name in fact_names:
            if wfilter.project_facts[
                name
            ] not in self.registry.project_fact_type_values(name):
                raise RuntimeError(
                    f'Invalid value for fact type {name}: '
                    f'"{wfilter.project_facts[name]}"'
                )

    def _validate_project_type_slug(self, slug: str) -> None:
        """Validate project type slug against cache if available.

        Args:
            slug: Project type slug to validate

        Raises:
            RuntimeError: If slug is invalid

        """
        if slug not in self.registry.project_type_slugs:
            raise RuntimeError(f'Invalid project type slug `{slug}`')

    async def _process_imbi_projects(self) -> bool:
        client = clients.Imbi.get_instance(config=self.configuration.imbi)
        projects = await client.get_all_projects()
        return await self._process_imbi_projects_common(projects)

    async def _process_imbi_projects_common(
        self, projects: list[models.ImbiProject]
    ) -> bool:
        self.logger.debug('Found %d total active projects', len(projects))
        filtered = await self._filter_projects(projects)

        semaphore = asyncio.Semaphore(self.args.max_concurrency)

        async def limited_process(project: models.ImbiProject) -> bool:
            async with semaphore:
                return await self._process_workflow_from_imbi_project(project)

        if self.args.exit_on_error:
            tasks = []
            async with asyncio.TaskGroup() as task_group:
                for project in filtered:
                    tasks.append(
                        task_group.create_task(limited_process(project))
                    )
            results = [task.result() for task in tasks]
        else:
            results = await asyncio.gather(
                *[
                    asyncio.create_task(limited_process(project))
                    for project in filtered
                ]
            )
        return all(results)

    async def _process_workflow_from_imbi_project(
        self, project: models.ImbiProject
    ) -> bool:
        # Set up per-project log capture if error preservation is enabled
        log_capture = None
        token = None
        if self.configuration.preserve_on_error:
            log_capture = per_project_logging.ProjectLogCapture(project.id)
            token = log_capture.start()

        try:
            github_repository = await self._get_github_repository(project)
            self._log_verbose_info(
                'Processing Project %i - %s', project.id, project.slug
            )

            success = await self.workflow_engine.execute(
                project, github_repository
            )

            if not success:
                # Write debug logs to error directory
                if log_capture:
                    error_path = self.workflow_engine.get_last_error_path()
                    if error_path:
                        log_capture.write_to_file(error_path / 'debug.log')
                        self.logger.info(
                            'Wrote debug logs to %s', error_path / 'debug.log'
                        )

                if self.args.exit_on_error:
                    raise RuntimeError(
                        f'Workflow execution failed for {project.name} '
                        f'({project.id}) - check logs above for details'
                    )
                # Error details already logged by workflow_engine
                return False

            self._log_verbose_info(
                'Completed processing %s (%i)', project.name, project.id
            )
            return True
        finally:
            # Always cleanup log capture to prevent memory leaks
            if log_capture and token:
                log_capture.cleanup(token)
