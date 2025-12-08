"""Git operation actions for version control within workflows.

Provides git operations including content extraction from history and
repository cloning for workflow automation tasks.
"""

from imbi_automations import git, mixins, models, utils


class GitActions(mixins.WorkflowLoggerMixin):
    """Executes Git version control operations for workflow automation.

    Handles file extraction from commit history, repository cloning, and branch
    management with configurable search strategies.
    """

    def __init__(
        self,
        configuration: models.Configuration,
        context: models.WorkflowContext,
        verbose: bool,
    ) -> None:
        super().__init__(verbose)
        self._set_workflow_logger(context.workflow)
        self.configuration = configuration
        self.context = context

    async def execute(self, action: models.WorkflowGitAction) -> None:
        """Execute the shell action."""
        match action.command:
            case models.WorkflowGitActionCommand.extract:
                destination_file = utils.resolve_path(
                    self.context, action.destination
                )
                self.logger.debug(
                    '%s [%s/%s] %s extracting %s from git history',
                    self.context.imbi_project.slug,
                    self.context.current_action_index,
                    self.context.total_actions,
                    action.name,
                    action.source,
                )
                if (
                    not await git.extract_file_from_commit(
                        working_directory=self.context.working_directory
                        / 'repository',
                        source_file=action.source,
                        destination_file=destination_file,
                        commit_keyword=action.commit_keyword,
                        search_strategy=action.search_strategy
                        or 'before_last_match',
                    )
                    and not action.ignore_errors
                ):
                    raise RuntimeError(
                        f'Git extraction failed for {action.source}'
                    )
                self.logger.info(
                    '%s [%s/%s] %s extracted %s to %s',
                    self.context.imbi_project.slug,
                    self.context.current_action_index,
                    self.context.total_actions,
                    action.name,
                    action.source,
                    destination_file,
                )
            case models.WorkflowGitActionCommand.clone:
                destination_path = utils.resolve_path(
                    self.context, action.destination
                )
                self.logger.debug(
                    '%s [%s/%s] %s cloning repository from %s to %s',
                    self.context.imbi_project.slug,
                    self.context.current_action_index,
                    self.context.total_actions,
                    action.name,
                    action.url,
                    destination_path,
                )
                await git.clone_to_directory(
                    working_directory=self.context.working_directory,
                    clone_url=action.url,
                    destination=destination_path,
                    branch=action.branch,
                    depth=action.depth,
                )
                self.logger.info(
                    '%s [%s/%s] %s cloned repository to %s',
                    self.context.imbi_project.slug,
                    self.context.current_action_index,
                    self.context.total_actions,
                    action.name,
                    destination_path,
                )
            case _:
                raise RuntimeError(f'Unsupported command: {action.command}')
