"""Main automation controller for executing workflows across projects.

The controller implements an iterator pattern for processing different
target types (GitHub repositories, Imbi projects) with workflow execution,
concurrency control, and comprehensive error handling.
"""

import argparse
import asyncio
import collections
import datetime
import enum
import logging
import pathlib
import tempfile

import async_lru

from imbi_automations import (
    clients,
    git,
    imc,
    mixins,
    models,
    per_project_logging,
    utils,
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
        self._workflow_engine: workflow_engine.WorkflowEngine | None = None
        self.workflow_filter = workflow_filter.Filter(
            config, workflow, args.verbose
        )
        self._set_workflow_logger(workflow)

    @property
    def workflow_engine(self) -> workflow_engine.WorkflowEngine:
        """Lazy-initialize workflow engine when first accessed.

        Returns:
            WorkflowEngine instance (created on first access)

        """
        if self._workflow_engine is None:
            self._workflow_engine = workflow_engine.WorkflowEngine(
                config=self.configuration,
                workflow=self.workflow,
                verbose=self.args.verbose,
                registry=self.registry,
            )
        return self._workflow_engine

    @property
    def iterator(self) -> AutomationIterator | None:
        """Determine the iterator type based on CLI arguments.

        Returns:
            AutomationIterator enum value corresponding to the target type

        """
        if self.args.resume or self.args.rerun_followup:
            return None
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

        if self.args.resume:
            return await self._resume_from_state()
        if self.args.rerun_followup:
            return await self._rerun_followup_stage()

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
            case _:
                self.logger.debug('No target type specified, exiting')

    async def _resume_from_state(self) -> bool:
        """Resume workflow from preserved error state.

        Returns:
            True if workflow completed successfully, False otherwise

        Raises:
            RuntimeError: If .state file not found, workflow path invalid,
                or workflow configuration incompatible

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

        # Update preserved_directory_path to use the actual path provided
        # by user (state file may contain relative or outdated path)
        state.preserved_directory_path = self.args.resume.resolve()

        self.logger.info(
            'Resuming workflow "%s" for project %s from action "%s" '
            '(index %d)',
            state.workflow_slug,
            state.project_slug,
            state.failed_action_name,
            state.failed_action_index,
        )

        # Validate workflow path from state file exists and is valid
        if not state.workflow_path.exists():
            raise RuntimeError(
                f'Workflow path from state file does not exist: '
                f'{state.workflow_path}'
            )

        state_config_file = state.workflow_path / 'config.toml'
        if not state_config_file.exists():
            raise RuntimeError(
                f'Workflow from state file missing config.toml: '
                f'{state_config_file}'
            )

        # Validate workflow compatibility
        if state.workflow_path != self.workflow.path:
            self.logger.warning(
                'Resume state workflow path (%s) differs from current (%s)',
                state.workflow_path,
                self.workflow.path,
            )

        current_hash = utils.hash_configuration(self.configuration)
        if state.configuration_hash != current_hash:
            self.logger.warning(
                'Configuration has changed since error occurred. '
                'Resume may behave unexpectedly.'
            )

        client = clients.Imbi.get_instance(config=self.configuration.imbi)
        project = await client.get_project(state.project_id)

        # Initialize workflow engine with resume state
        self._workflow_engine = workflow_engine.WorkflowEngine(
            config=self.configuration,
            workflow=self.workflow,
            verbose=self.args.verbose,
            resume_state=state,
            registry=self.registry,
        )

        # Execute with resume
        success = await self.workflow_engine.execute(
            project, state.github_repository
        )

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

    async def _rerun_followup_stage(self) -> bool:
        """Re-run the followup stage for a project with an existing PR.

        Creates a synthetic resume state targeting the first followup
        action, clones the repository on the PR branch, and executes
        the workflow engine in resume mode.

        Returns:
            True if workflow completed successfully, False otherwise

        Raises:
            RuntimeError: If --pr-number not provided, no followup
                actions exist, or project/repository lookup fails

        """
        if not self.args.pr_number:
            raise RuntimeError('--pr-number is required with --rerun-followup')

        project_id = self.args.rerun_followup
        pr_number = self.args.pr_number

        # Fetch project and GitHub repository
        client = clients.Imbi.get_instance(config=self.configuration.imbi)
        project = await client.get_project(project_id)
        github_repository = await self._get_github_repository(project)

        if not github_repository:
            raise RuntimeError(
                f'No GitHub repository found for project {project.slug}'
            )

        # Find followup actions and primary action indices
        all_actions = list(enumerate(self.workflow.configuration.actions))
        primary_indices = [
            i
            for i, a in all_actions
            if a.stage == models.WorkflowActionStage.primary
        ]
        followup_actions = [
            (i, a)
            for i, a in all_actions
            if a.stage == models.WorkflowActionStage.followup
        ]

        if not followup_actions:
            raise RuntimeError(
                f'Workflow "{self.workflow.configuration.name}" has no '
                f'followup actions to re-run'
            )

        first_followup_idx, first_followup_action = followup_actions[0]

        # Determine PR branch name
        pr_branch = f'imbi-automations/{self.workflow.slug}'

        self.logger.info(
            'Re-running followup stage for project %s (PR #%d on branch %s)',
            project.slug,
            pr_number,
            pr_branch,
        )

        # Create temp directory with standard structure
        temp_dir = tempfile.mkdtemp(prefix=f'imbi-rerun-{project.slug}-')
        temp_path = pathlib.Path(temp_dir)

        # Create workflow symlink and extracted directory
        (temp_path / 'workflow').symlink_to(self.workflow.path.resolve())
        (temp_path / 'extracted').mkdir(exist_ok=True)

        # Determine clone URL based on workflow clone type
        if (
            self.workflow.configuration.git.clone_type
            == models.WorkflowGitCloneType.ssh
        ):
            clone_url = github_repository.ssh_url
        else:
            clone_url = github_repository.clone_url

        # Clone repository on the PR branch
        starting_commit = await git.clone_repository(
            temp_path,
            clone_url,
            branch=pr_branch,
            depth=self.workflow.configuration.git.depth,
        )

        # Construct synthetic ResumeState
        state = models.ResumeState(
            workflow_slug=self.workflow.slug,
            workflow_path=self.workflow.path,
            project_id=project.id,
            project_slug=project.slug,
            failed_action_index=first_followup_idx,
            failed_action_name=first_followup_action.name,
            completed_action_indices=primary_indices,
            current_stage='followup',
            starting_commit=starting_commit,
            has_repository_changes=True,
            github_repository=github_repository,
            pull_request_number=pr_number,
            pull_request_url=None,
            pr_branch=pr_branch,
            error_message='Synthetic state for --rerun-followup',
            error_timestamp=datetime.datetime.now(tz=datetime.UTC),
            preserved_directory_path=temp_path,
            configuration_hash=utils.hash_configuration(self.configuration),
        )

        # Initialize workflow engine with synthetic resume state
        self._workflow_engine = workflow_engine.WorkflowEngine(
            config=self.configuration,
            workflow=self.workflow,
            verbose=self.args.verbose,
            resume_state=state,
            registry=self.registry,
        )

        # Execute workflow in resume mode
        success = await self.workflow_engine.execute(
            project, github_repository
        )

        if success:
            self.logger.info(
                'Successfully completed followup re-run for %s', project.slug
            )
        else:
            self.logger.error('Followup re-run failed for %s', project.slug)

        return success

    async def _filter_projects(
        self, projects: list[models.ImbiProject]
    ) -> list[models.ImbiProject]:
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
        self._validate_project_type_slug(self.args.project_type)

        client = clients.Imbi.get_instance(config=self.configuration.imbi)
        projects = await client.get_projects_by_type(self.args.project_type)
        self.logger.debug('Found %d total active projects', len(projects))
        return await self._process_imbi_projects_common(projects)

    async def _process_imbi_projects(self) -> bool:
        client = clients.Imbi.get_instance(config=self.configuration.imbi)
        projects = await client.get_projects()
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
                ],
                return_exceptions=True,
            )

        # Count successes and failures
        successes = sum(1 for r in results if r is True)
        failures = sum(
            1 for r in results if r is False or isinstance(r, Exception)
        )

        if failures > 0:
            self.logger.warning(
                'Completed batch processing: %d succeeded, %d failed',
                successes,
                failures,
            )

        return all(r is True for r in results)

    async def _process_workflow_from_imbi_project(
        self, project: models.ImbiProject
    ) -> bool:
        self.logger.info(
            'Processing Project %i - %s', project.id, project.slug
        )
        github_repository = await self._get_github_repository(project)

        if self.configuration.preserve_on_error:
            log_capture = per_project_logging.ProjectLogCapture(project.id)
            token = log_capture.start()
        else:
            log_capture, token = None, None

        try:
            result = await self.workflow_engine.execute(
                project, github_repository
            )
            if not result:
                if self.args.exit_on_error:
                    raise RuntimeError(
                        f'Workflow failed for {project.name} ({project.id})'
                    )
                return False

            self.logger.info(
                'Completed processing %s (%i)', project.name, project.id
            )
            return True
        finally:
            # Write debug logs if error occurred (error_path set by engine)
            if log_capture and token:
                error_path = self.workflow_engine.get_last_error_path()
                if error_path:
                    log_capture.write_to_file(error_path / 'debug.log')
                    self.logger.info(
                        'Wrote debug logs to %s', error_path / 'debug.log'
                    )
                log_capture.cleanup(token)

    def _validate_workflow_filter_environments(self) -> None:
        """Validate workflow filter environments against cache if available.

        :raises: RuntimeError

        """
        self._validate_workflow_filter_set_values(
            'environments',
            self.workflow.configuration.filter.project_environments,
            self.registry.environments,
        )

    def _validate_workflow_filter_project_facts(self) -> None:
        """Validate workflow filter project facts against cache if available.

        :raises: RuntimeError

        """
        self._validate_workflow_filter_set_values(
            'project fact type',
            set(self.workflow.configuration.filter.project_facts.keys()),
            self.registry.project_fact_type_names,
        )
        for name in self.workflow.configuration.filter.project_facts:
            value = self.workflow.configuration.filter.project_facts[name]
            if not self.registry.validate_project_fact_value(name, value):
                fact_type = self.registry.get_project_fact_type(name)
                if fact_type:
                    raise RuntimeError(
                        f'Invalid value for fact type {name}: "{value}" '
                        f'(expected {fact_type.data_type} '
                        f'{fact_type.fact_type})'
                    )
                else:
                    raise RuntimeError(
                        f'Invalid value for fact type {name}: "{value}"'
                    )

    def _validate_workflow_filter_project_types(self) -> None:
        """Validate workflow filter environments against Imbi values

        :raises: RuntimeError

        """
        self._validate_workflow_filter_set_values(
            'project type',
            set(self.workflow.configuration.filter.project_types),
            set(self.registry.project_types),
        )

    def _validate_workflow_filter_set_values(
        self, field: str, filter: set[str], expectations: set[str]
    ) -> None:
        """Raise a RuntimeError if a filter value is invalid."""
        if filter and filter - expectations:
            missing = filter - expectations
            invalid = ', '.join(missing)
            if len(missing) > 1:
                raise RuntimeError(f'{invalid} are not valid {field}s')
            raise RuntimeError(f'{invalid} is not a valid {field}')

    def _validate_workflow_filters(self) -> None:
        """Validate workflow filters against cache if available."""
        if not self.workflow.configuration.filter:
            return
        LOGGER.debug(
            'Validating workflow filters: %r',
            self.workflow.configuration.filter.model_dump(),
        )

        LOGGER.debug(
            '%r > %r = %r',
            self.workflow.configuration.filter.project_types,
            self.registry.project_type_slugs,
            self.workflow.configuration.filter.project_types
            <= self.registry.project_type_slugs,
        )

        self._validate_workflow_filter_environments()
        self._validate_workflow_filter_project_facts()
        self._validate_workflow_filter_project_types()

    def _validate_project_type_slug(self, slug: str) -> None:
        """Validate project type slug against Imbi data if available.

        Args:
            slug: Project type slug to validate

        Raises:
            RuntimeError: If slug is invalid

        """
        if slug not in self.registry.project_type_slugs:
            raise RuntimeError(f'Invalid project type slug `{slug}`')
