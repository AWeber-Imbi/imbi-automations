"""Workflow execution engine with action orchestration and context management.

The workflow engine executes workflow actions in sequence, managing temporary
directories, git operations, condition checking, and pull request creation with
comprehensive error handling and restart capabilities.
"""

import datetime
import logging
import pathlib
import shutil
import tempfile
import typing

from imbi_automations import (
    actions,
    claude,
    clients,
    committer,
    condition_checker,
    git,
    mixins,
    models,
    prompts,
    tracker,
    workflow_filter,
)

LOGGER = logging.getLogger(__name__)
BASE_PATH = pathlib.Path(__file__).parent


class WorkflowEngine(mixins.WorkflowLoggerMixin):
    """Workflow engine for running workflow actions."""

    def __init__(
        self,
        config: models.Configuration,
        workflow: models.Workflow,
        verbose: bool = False,
        resume_state: models.ResumeState | None = None,
        registry: typing.Any = None,
    ) -> None:
        super().__init__(verbose)
        self.actions = actions.Actions(config, verbose)
        self.committer = committer.Committer(config, verbose)
        self.condition_checker = condition_checker.ConditionChecker(
            config, verbose
        )
        self.configuration = config
        self.github = clients.GitHub.get_instance(config=config)
        self.last_error_path: pathlib.Path | None = None
        self.registry = registry
        self.resume_state = resume_state
        self.tracker = tracker.Tracker.get_instance()
        self.workflow = workflow
        self.workflow_filter = workflow_filter.Filter(
            config, workflow, verbose
        )
        self._set_workflow_logger(workflow)

        if not self.configuration.claude.enabled and (
            self._needs_claude_code
            or workflow.configuration.github.create_pull_request
        ):
            raise RuntimeError(
                'Workflow requires Claude Code, but it is not enabled'
            )

    async def execute(
        self,
        project: models.ImbiProject,
        github_repository: models.GitHubRepository | None = None,
    ) -> bool:
        """Execute the workflow (or resume from saved state)."""
        if self.resume_state:
            # Resume mode: reuse preserved directory (don't auto-cleanup)
            working_directory = tempfile.TemporaryDirectory(delete=False)

            # Copy preserved state to new temp location
            shutil.copytree(
                self.resume_state.preserved_directory_path,
                working_directory.name,
                dirs_exist_ok=True,
                symlinks=True,
            )

            # Restore context from saved state
            context = self._restore_workflow_context(
                working_directory.name, project, github_repository
            )

            # Determine which actions to run (from failed action onwards)
            actions_to_run = list(
                enumerate(self.workflow.configuration.actions)
            )[self.resume_state.failed_action_index :]

            # Set total actions for progress display
            context.total_actions = len(self.workflow.configuration.actions)

            self.logger.info(
                '%s [%d/%d] resuming from action "%s"',
                context.imbi_project.slug,
                self.resume_state.failed_action_index + 1,
                context.total_actions,
                self.resume_state.failed_action_name,
            )
        else:
            # Normal mode: fresh temporary directory
            working_directory = tempfile.TemporaryDirectory()
            context = self._setup_workflow_run(
                project, working_directory.name, github_repository
            )
            actions_to_run = list(
                enumerate(self.workflow.configuration.actions)
            )

        # Skip condition checks if resuming
        if (
            not self.resume_state
            and not await self.condition_checker.check_remote(
                context,
                self.workflow.configuration.condition_type,
                self.workflow.configuration.conditions,
            )
        ):
            self.logger.info(
                '%s remote workflow conditions not met',
                context.imbi_project.slug,
            )
            self.tracker.incr('workflow_remote_conditions_not_met')
            return False

        # Clone only if needed and not resuming
        if self.workflow.configuration.git.clone and not self.resume_state:
            context.starting_commit = await git.clone_repository(
                context.working_directory,
                self._git_clone_url(github_repository),
                self.workflow.configuration.git.starting_branch,
                self.workflow.configuration.git.depth,
            )
            self.tracker.incr('repositories_cloned')

        # Skip local condition checks if resuming
        if not self.resume_state and not self.condition_checker.check(
            context,
            self.workflow.configuration.condition_type,
            self.workflow.configuration.conditions,
        ):
            self.tracker.incr('workflow_conditions_not_met')
            self.logger.info(
                '%s workflow conditions not met', context.imbi_project.slug
            )
            return False

        # Separate actions by stage
        all_actions = list(enumerate(self.workflow.configuration.actions))
        primary_actions = [
            (i, a)
            for i, a in all_actions
            if a.stage == models.WorkflowActionStage.primary
        ]
        followup_actions = [
            (i, a)
            for i, a in all_actions
            if a.stage == models.WorkflowActionStage.followup
        ]

        # Set total actions for progress tracking (primary stage only)
        context.total_actions = len(primary_actions)

        # Filter actions_to_run to only include primary stage actions
        # (for resume mode, we filter the already-subset actions_to_run)
        if self.resume_state:
            primary_actions_to_run = [
                (i, a)
                for i, a in actions_to_run
                if a.stage == models.WorkflowActionStage.primary
            ]
        else:
            primary_actions_to_run = primary_actions

        # Execute PRIMARY stage actions
        for idx, action in primary_actions_to_run:
            # Update current action index for progress tracking
            context.current_action_index = idx + 1

            try:
                executed = await self._execute_action(context, action)

                if executed:
                    self.tracker.incr('actions_executed')
                    self.tracker.incr(f'actions_executed_{action.type}')

                    if action.committable:
                        committed = await self.committer.commit(
                            context, action
                        )
                        if committed:
                            context.has_repository_changes = True
                            self.tracker.incr('actions_committed')
            except Exception as exc:  # noqa: BLE001 - preserve_on_error must handle all exceptions
                self.logger.error(
                    '%s error executing action "%s": %s',
                    context.imbi_project.slug,
                    action.name,
                    exc,
                )
                if self.configuration.preserve_on_error:
                    # Calculate completed indices for this execution
                    if not self.resume_state:
                        # First run: all actions before failure
                        completed_indices = list(range(0, idx))
                    else:
                        # Resume: only actions from failed_action_index to idx
                        # (don't accumulate from previous runs)
                        completed_indices = list(
                            range(self.resume_state.failed_action_index, idx)
                        )
                    self.last_error_path = self._preserve_working_directory(
                        context,
                        working_directory,
                        self.configuration.error_dir,
                        failed_action_index=idx,
                        failed_action_name=action.name,
                        completed_action_indices=completed_indices,
                        error_message=str(exc),
                    )
                working_directory.cleanup()
                raise exc

        # Handle dry-run mode: preserve working directory and skip push/PR
        if self.configuration.dry_run:
            self.logger.info(
                '%s dry-run mode: saving repository state to %s',
                context.imbi_project.slug,
                self.configuration.dry_run_dir,
            )
            if followup_actions:
                self.logger.warning(
                    '%s dry-run mode: skipping %d followup actions '
                    '(no PR created)',
                    context.imbi_project.slug,
                    len(followup_actions),
                )
            self._preserve_working_directory(
                context, working_directory, self.configuration.dry_run_dir
            )
            working_directory.cleanup()
            return True

        # Create PR or push changes
        if context.has_repository_changes:
            if (
                self.workflow.configuration.github.create_pull_request
                and self.configuration.claude.enabled
            ):
                pr, branch_name = await self._create_pull_request(context)
                context.pull_request = pr
                context.pr_branch = branch_name
                self.tracker.incr('pull_requests_created')
            else:
                await git.push_changes(
                    working_directory=context.working_directory / 'repository',
                    remote='origin',
                    branch='main',
                    set_upstream=True,
                )
        else:
            self.logger.debug(
                '%s no repository changes to push or create PR',
                context.imbi_project.slug,
            )

        # Execute FOLLOWUP stage (if followup actions exist)
        if followup_actions:
            await self._execute_followup_stage(
                context, followup_actions, working_directory
            )

        # Clean up successfully resumed state
        if self.resume_state:
            self._cleanup_resume_state(self.resume_state)

        working_directory.cleanup()
        return True

    async def _create_pull_request(
        self, context: models.WorkflowContext
    ) -> tuple[models.GitHubPullRequest, str]:
        """Create a pull request by creating a branch and pushing changes.

        Returns:
            Tuple of (GitHubPullRequest, branch_name)

        """
        repository_dir = context.working_directory / 'repository'

        branch_name = f'imbi-automations/{context.workflow.slug}'

        # Delete remote branch if replace_branch is enabled
        if context.workflow.configuration.github.replace_branch:
            self.logger.info(
                'Deleting remote branch %s if exists for %s '
                '(replace_branch=True)',
                branch_name,
                context.imbi_project.slug,
            )
            await git.delete_remote_branch_if_exists(
                working_directory=repository_dir, branch_name=branch_name
            )

        self.logger.info(
            'Creating pull request branch: %s for %s',
            branch_name,
            context.imbi_project.slug,
        )

        # Create and checkout new branch
        await git.create_branch(
            working_directory=repository_dir,
            branch_name=branch_name,
            checkout=True,
        )

        # Push the new branch to remote
        await git.push_changes(
            working_directory=repository_dir,
            remote='origin',
            branch=branch_name,
            set_upstream=True,
        )

        self.logger.info(
            'Successfully pushed branch %s for pull request for %s',
            branch_name,
            context.imbi_project.slug,
        )

        summary = await git.get_commits_since(
            working_directory=repository_dir,
            starting_commit=context.starting_commit,
        )
        self.logger.debug(
            '%s %i commits made in workflow',
            context.imbi_project.slug,
            len(summary.commits),
        )

        prompt = prompts.render(
            context,
            BASE_PATH / 'prompts' / 'pull-request-summary.md.j2',
            summary=summary.model_dump_json(indent=2),
        )
        self.logger.debug('Prompt: %s', prompt)

        client = claude.Claude(self.configuration, context, self.verbose)
        body = await client.anthropic_query(prompt)

        pr = await self.github.create_pull_request(
            context=context,
            title=f'imbi-automations: {context.workflow.configuration.name}',
            body=body,
            head_branch=branch_name,
        )
        self.logger.info(
            'Created pull request for %s: %s',
            context.imbi_project.slug,
            pr.html_url,
        )

        return pr, branch_name

    async def _execute_followup_stage(
        self,
        context: models.WorkflowContext,
        followup_actions: list[tuple[int, models.WorkflowActions]],
        working_directory: 'tempfile.TemporaryDirectory',
    ) -> None:
        """Execute followup stage actions with commit cycling.

        Followup actions can make commits. After each commit cycle completes,
        if any commits were made, the followup stage restarts to allow
        monitoring of the new changes.

        Args:
            context: Workflow context with PR information
            followup_actions: List of (index, action) tuples for followup stage
            working_directory: Temporary directory for error preservation

        Raises:
            RuntimeError: If max_followup_cycles reached without success

        """
        max_cycles = self.workflow.configuration.max_followup_cycles

        for cycle in range(1, max_cycles + 1):
            self.logger.info(
                '%s followup stage cycle %d/%d',
                context.imbi_project.slug,
                cycle,
                max_cycles,
            )

            cycle_made_commits = False

            for idx, action in followup_actions:
                context.current_action_index = idx + 1

                try:
                    executed = await self._execute_action(context, action)

                    if executed:
                        self.tracker.incr('followup_actions_executed')
                        self.tracker.incr(
                            f'followup_actions_executed_{action.type}'
                        )

                        if action.committable:
                            committed = await self.committer.commit(
                                context, action
                            )
                            if committed:
                                # Push to PR branch or main
                                branch = context.pr_branch or 'main'
                                repo_dir = (
                                    context.working_directory / 'repository'
                                )
                                await git.push_changes(
                                    working_directory=repo_dir,
                                    remote='origin',
                                    branch=branch,
                                    set_upstream=False,
                                )
                                context.has_repository_changes = True
                                cycle_made_commits = True
                                self.tracker.incr('followup_commits')

                except Exception as exc:  # noqa: BLE001
                    self.logger.error(
                        '%s error in followup action "%s": %s',
                        context.imbi_project.slug,
                        action.name,
                        exc,
                    )
                    if self.configuration.preserve_on_error:
                        self.last_error_path = (
                            self._preserve_working_directory(
                                context,
                                working_directory,
                                self.configuration.error_dir,
                                failed_action_index=idx,
                                failed_action_name=action.name,
                                completed_action_indices=[],
                                error_message=str(exc),
                                current_stage='followup',
                                followup_cycle=cycle,
                            )
                        )
                    working_directory.cleanup()
                    raise

            # If no commits were made this cycle, followup is complete
            if not cycle_made_commits:
                self.logger.info(
                    '%s followup stage completed (no commits in cycle %d)',
                    context.imbi_project.slug,
                    cycle,
                )
                return

            # Refresh PR status for next cycle (if PR exists)
            if context.pull_request:
                context.pull_request = await self._refresh_pr_status(context)

        # Max cycles reached - fail the workflow
        raise RuntimeError(
            f'Followup stage reached max cycles ({max_cycles}) for '
            f'{context.imbi_project.slug}'
        )

    async def _refresh_pr_status(
        self, context: models.WorkflowContext
    ) -> models.GitHubPullRequest | None:
        """Refresh PR status from GitHub API.

        Called between followup cycles to get updated check status,
        comments, reviews, etc.

        """
        if not context.pull_request or not context.github_repository:
            return None

        org, repo = context.github_repository.full_name.split('/', 1)
        return await self.github.get_pull_request(
            org, repo, context.pull_request.number
        )

    async def _execute_action(
        self,
        context: models.WorkflowContext,
        action: (
            models.WorkflowCallableAction
            | models.WorkflowClaudeAction
            | models.WorkflowDockerAction
            | models.WorkflowFileAction
            | models.WorkflowGitAction
            | models.WorkflowGitHubAction
            | models.WorkflowShellAction
            | models.WorkflowTemplateAction
        ),
    ) -> bool:
        """Execute an action.

        Returns:
            True if action was executed, False if skipped

        """
        if action.filter and not await self.workflow_filter.filter_project(
            context.imbi_project, action.filter
        ):
            self.logger.debug(
                '%s skipping %s due to action filter',
                context.imbi_project.slug,
                action.name,
            )
            self.tracker.incr('actions_filter_skipped')
            self.tracker.incr(f'actions_filter_skipped_{action.type}')
            return False

        if not self.condition_checker.check(
            context,
            self.workflow.configuration.condition_type,
            action.conditions,
        ):
            self.tracker.incr('actions_condition_skipped')
            self.tracker.incr(f'actions_condition_skipped_{action.type}')
            self.logger.debug(
                '%s skipping %s due to failed condition check',
                context.imbi_project.slug,
                action.name,
            )
            return False
        elif not await self.condition_checker.check_remote(
            context,
            self.workflow.configuration.condition_type,
            action.conditions,
        ):
            self.tracker.incr('actions_remote_condition_skipped')
            self.tracker.incr(
                f'actions_remote_condition_skipped_{action.type}'
            )
            self.logger.info(
                'Skipping action %s due to failed condition check', action.name
            )
            return False
        await self.actions.execute(context, action)
        return True

    def get_last_error_path(self) -> pathlib.Path | None:
        """Return path where error state was last preserved.

        Returns:
            Path to error directory, or None if no error preserved

        """
        return self.last_error_path

    def _preserve_working_directory(
        self,
        context: models.WorkflowContext,
        working_directory: tempfile.TemporaryDirectory,
        target_base_dir: pathlib.Path,
        failed_action_index: int | None = None,
        failed_action_name: str | None = None,
        completed_action_indices: list[int] | None = None,
        error_message: str | None = None,
        current_stage: str = 'primary',
        followup_cycle: int = 0,
    ) -> pathlib.Path | None:
        """Preserve working directory state to a specified directory.

        When error information is provided (failed_action_index, etc.), also
        creates a .state file for workflow resumability.

        Args:
            context: Workflow execution context
            working_directory: Temporary directory to preserve
            target_base_dir: Base directory for preservation (e.g., error_dir
                or dry_run_dir)
            failed_action_index: Optional index of failed action (for .state)
            failed_action_name: Optional name of failed action (for .state)
            completed_action_indices: Optional list of completed indices
            error_message: Optional error message for .state file
            current_stage: Stage where failure occurred ('primary' or
                'followup')
            followup_cycle: Followup cycle number (0 for primary stage)

        Returns:
            Path to preserved directory, or None if preservation failed

        """
        timestamp = datetime.datetime.now(tz=datetime.UTC).strftime(
            '%Y%m%d-%H%M%S'
        )
        workflow_slug = context.workflow.slug or 'unknown'
        project_slug = context.imbi_project.slug

        # Create target directory: <base>/<workflow>/<project>-<timestamp>
        target_path = (
            target_base_dir / workflow_slug / f'{project_slug}-{timestamp}'
        )

        try:
            target_path.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                working_directory.name,
                target_path,
                dirs_exist_ok=True,
                symlinks=True,
            )
            self.logger.info(
                '%s preserved working directory to %s',
                context.imbi_project.slug,
                target_path,
            )

            # Create .state file if error information provided
            if (
                failed_action_index is not None
                and failed_action_name is not None
            ):
                from imbi_automations import utils

                # Extract PR info from context if available
                pr = context.pull_request
                state = models.ResumeState(
                    workflow_slug=workflow_slug,
                    workflow_path=context.workflow.path,
                    project_id=context.imbi_project.id,
                    project_slug=project_slug,
                    failed_action_index=failed_action_index,
                    failed_action_name=failed_action_name,
                    completed_action_indices=completed_action_indices or [],
                    starting_commit=context.starting_commit,
                    has_repository_changes=context.has_repository_changes,
                    github_repository=context.github_repository,
                    error_message=error_message or 'Unknown error',
                    error_timestamp=datetime.datetime.now(tz=datetime.UTC),
                    preserved_directory_path=target_path,
                    configuration_hash=utils.hash_configuration(
                        self.configuration
                    ),
                    current_stage=current_stage,
                    followup_cycle=followup_cycle,
                    pull_request_number=pr.number if pr else None,
                    pull_request_url=pr.html_url if pr else None,
                    pr_branch=context.pr_branch,
                )

                state_file = target_path / '.state'
                state_file.write_bytes(state.to_msgpack())
                self.logger.info(
                    '%s created resume state file: %s',
                    context.imbi_project.slug,
                    state_file,
                )

            return target_path
        except OSError as exc:
            self.logger.error(
                '%s failed to preserve working directory to %s: %s',
                context.imbi_project.slug,
                target_path,
                exc,
            )
            return None

    def _git_clone_url(
        self, github_repository: models.GitHubRepository | None = None
    ) -> str:
        if github_repository:
            if (
                self.workflow.configuration.git.clone_type
                == models.WorkflowGitCloneType.ssh
            ):
                return github_repository.ssh_url
            return github_repository.clone_url
        raise ValueError('No repository provided')

    @property
    def _needs_claude_code(self) -> bool:
        """Will return True if any action requires Claude Code."""
        return any(
            action.type == models.WorkflowActionTypes.claude
            for action in self.workflow.configuration.actions
        )

    def _setup_workflow_run(
        self,
        project: models.ImbiProject,
        working_directory: str,
        github_repository: models.GitHubRepository | None = None,
    ) -> models.WorkflowContext:
        working_directory = pathlib.Path(working_directory)

        # Create the symlink of the workflow to the working directory
        workflow_path = working_directory / 'workflow'
        workflow_path.symlink_to(self.workflow.path.resolve())
        if not workflow_path.is_symlink():
            raise RuntimeError(
                f'Unable to create symlink for workflow: {workflow_path}'
            )

        # Ensure the extracted and repository directories exist
        (working_directory / 'extracted').mkdir(exist_ok=True)
        (working_directory / 'repository').mkdir(exist_ok=True)

        return models.WorkflowContext(
            workflow=self.workflow,
            github_repository=github_repository,
            imbi_project=project,
            starting_commit=None,
            working_directory=working_directory,
            registry=self.registry,
        )

    def _restore_workflow_context(
        self,
        working_directory: str,
        project: models.ImbiProject,
        github_repository: models.GitHubRepository | None,
    ) -> models.WorkflowContext:
        """Restore WorkflowContext from resume state.

        Args:
            working_directory: Path to restored working directory
            project: ImbiProject instance (loaded fresh from API)
            github_repository: Optional GitHub repository model

        Returns:
            Reconstructed WorkflowContext with restored state

        Raises:
            RuntimeError: If resume_state is None or workflow symlink missing

        """
        if self.resume_state is None:
            raise RuntimeError(
                'resume_state must be set when restoring context'
            )

        working_directory_path = pathlib.Path(working_directory)

        # Workflow symlink should already exist in preserved dir
        workflow_path = working_directory_path / 'workflow'
        if not workflow_path.exists():
            raise RuntimeError(
                f'Workflow symlink not found in preserved directory: '
                f'{workflow_path}'
            )

        # Ensure extracted directory exists
        extracted_path = working_directory_path / 'extracted'
        if not extracted_path.exists():
            extracted_path.mkdir(exist_ok=True)

        return models.WorkflowContext(
            workflow=self.workflow,
            github_repository=(
                github_repository or self.resume_state.github_repository
            ),
            imbi_project=project,
            starting_commit=self.resume_state.starting_commit,
            working_directory=working_directory_path,
            has_repository_changes=self.resume_state.has_repository_changes,
            registry=self.registry,
        )

    def _cleanup_resume_state(self, state: models.ResumeState) -> None:
        """Clean up successfully resumed state directory.

        Args:
            state: ResumeState with preserved directory path

        """
        try:
            if state.preserved_directory_path.exists():
                shutil.rmtree(state.preserved_directory_path)
                self.logger.info(
                    'Cleaned up resume state directory: %s',
                    state.preserved_directory_path,
                )
        except OSError as exc:
            self.logger.warning(
                'Failed to clean up resume state directory: %s', exc
            )
