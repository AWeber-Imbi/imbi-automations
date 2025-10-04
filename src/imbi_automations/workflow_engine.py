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
    ) -> None:
        super().__init__(verbose)
        self.actions = actions.Actions(config, verbose)
        self.committer = committer.Committer(config, verbose)
        self.condition_checker = condition_checker.ConditionChecker(
            config, verbose
        )
        self.configuration = config
        self.github = clients.GitHub.get_instance(config=config.github)
        self.last_error_path: pathlib.Path | None = None
        self.tracker = tracker.Tracker.get_instance()
        self.workflow = workflow
        self.workflow_filter = workflow_filter.Filter(
            config, workflow, verbose
        )
        self._set_workflow_logger(workflow)

        if not self.configuration.claude_code.enabled and (
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
        """Execute the workflow."""
        working_directory = tempfile.TemporaryDirectory()
        context = self._setup_workflow_run(
            project, working_directory.name, github_repository
        )

        if not await self.condition_checker.check_remote(
            context,
            self.workflow.configuration.condition_type,
            self.workflow.configuration.conditions,
        ):
            self.logger.info(
                '%s remote workflow conditions not met',
                context.imbi_project.slug,
            )
            self.tracker.incr('workflow_remote_conditions_not_met')
            return False

        if self.workflow.configuration.git.clone:
            context.starting_commit = await git.clone_repository(
                context.working_directory,
                self._git_clone_url(github_repository),
                self.workflow.configuration.git.starting_branch,
                self.workflow.configuration.git.depth,
            )
            self.tracker.incr('repositories_cloned')

        if not self.condition_checker.check(
            context,
            self.workflow.configuration.condition_type,
            self.workflow.configuration.conditions,
        ):
            self.tracker.incr('workflow_conditions_not_met')
            self.logger.info(
                '%s workflow conditions not met', context.imbi_project.slug
            )
            return False

        for action in self.workflow.configuration.actions:
            try:
                await self._execute_action(context, action)
            except RuntimeError as exc:
                self.logger.error(
                    '%s error executing action "%s": %s',
                    context.imbi_project.slug,
                    action.name,
                    exc,
                )
                if self.configuration.preserve_on_error:
                    self._preserve_error_state(context, working_directory)
                working_directory.cleanup()
                return False

            self.tracker.incr('actions_executed')
            self.tracker.incr(f'actions_executed_{action.type}')

            if action.committable:
                await self.committer.commit(context, action)
                self.tracker.incr('actions_committed')

        if (
            self.workflow.configuration.github.create_pull_request
            and self.configuration.claude_code.enabled
        ):
            await self._create_pull_request(context)
            self.tracker.incr('pull_requests_created')
        else:
            await git.push_changes(
                working_directory=context.working_directory / 'repository',
                remote='origin',
                branch='main',
                set_upstream=True,
            )

        working_directory.cleanup()
        return True

    async def _create_pull_request(
        self, context: models.WorkflowContext
    ) -> None:
        """Create a pull request by creating a branch and pushing changes."""
        repository_dir = context.working_directory / 'repository'

        branch_name = f'imbi-automations/{context.workflow.slug}'

        # Delete remote branch if replace_branch is enabled
        if context.workflow.configuration.github.replace_branch:
            self._log_verbose_info(
                'Deleting remote branch %s if exists for %s '
                '(replace_branch=True)',
                branch_name,
                context.imbi_project.slug,
            )
            await git.delete_remote_branch_if_exists(
                working_directory=repository_dir, branch_name=branch_name
            )

        self._log_verbose_info(
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

        self._log_verbose_info(
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

        pr_url = await self.github.create_pull_request(
            context=context,
            title=f'imbi-automations: {context.workflow.configuration.name}',
            body=body,
            head_branch=branch_name,
        )
        self._log_verbose_info(
            'Created pull request for %s: %s',
            context.imbi_project.slug,
            pr_url,
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
            | models.WorkflowUtilityAction
        ),
    ) -> None:
        """Execute an action."""
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
            return

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
            return
        elif not await self.condition_checker.check_remote(
            context,
            self.workflow.configuration.condition_type,
            action.conditions,
        ):
            self.tracker.incr('actions_remote_condition_skipped')
            self.tracker.incr(
                f'actions_remote_condition_skipped_{action.type}'
            )
            self._log_verbose_info(
                'Skipping action %s due to failed condition check', action.name
            )
            return
        await self.actions.execute(context, action)

    def get_last_error_path(self) -> pathlib.Path | None:
        """Return path where error state was last preserved.

        Returns:
            Path to error directory, or None if no error preserved

        """
        return self.last_error_path

    def _preserve_error_state(
        self,
        context: models.WorkflowContext,
        working_directory: tempfile.TemporaryDirectory,
    ) -> None:
        """Preserve working directory state on error for debugging.

        Args:
            context: Workflow execution context
            working_directory: Temporary directory to preserve

        """
        timestamp = datetime.datetime.now(tz=datetime.UTC).strftime(
            '%Y%m%d-%H%M%S'
        )
        workflow_slug = context.workflow.slug or 'unknown'
        project_slug = context.imbi_project.slug

        # Create error directory: errors/<workflow>/<project>-<timestamp>
        error_path = (
            self.configuration.error_dir
            / workflow_slug
            / f'{project_slug}-{timestamp}'
        )

        try:
            error_path.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                working_directory.name,
                error_path,
                dirs_exist_ok=True,
                symlinks=True,
            )
            self.last_error_path = error_path
            self.logger.info(
                '%s preserved error state to %s for debugging',
                context.imbi_project.slug,
                error_path,
            )
        except OSError as exc:
            self.last_error_path = None
            self.logger.error(
                '%s failed to preserve error state to %s: %s',
                context.imbi_project.slug,
                error_path,
                exc,
            )

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

        # Ensure the extracted directory exists
        (working_directory / 'extracted').mkdir(exist_ok=True)

        return models.WorkflowContext(
            workflow=self.workflow,
            github_repository=github_repository,
            imbi_project=project,
            starting_commit=None,
            working_directory=working_directory,
        )
