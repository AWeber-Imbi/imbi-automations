"""Git commit handling with AI-powered and manual commit support.

Manages git commits for workflow actions, supporting both Claude
AI-powered commit message generation and manual commits with templated
messages.
"""

import logging
import pathlib

from imbi_automations import claude, git, mixins, models, prompts

LOGGER = logging.getLogger(__name__)

BASE_PATH = pathlib.Path(__file__).parent


class Committer(mixins.WorkflowLoggerMixin):
    """Handles git commits for workflow actions.

    Supports both AI-powered commit message generation via Claude and manual
    commits with templated messages.
    """

    def __init__(
        self, configuration: models.Configuration, verbose: bool
    ) -> None:
        super().__init__(verbose)
        self.configuration = configuration
        self.logger = LOGGER

    async def commit(
        self, context: models.WorkflowContext, action: models.WorkflowAction
    ) -> bool:
        """Commit changes for an action.

        Returns:
            True if a commit was made, False if no changes to commit
        """
        self._set_workflow_logger(context.workflow)
        if (
            action.ai_commit
            and self.configuration.ai_commits
            and self.configuration.claude.enabled
        ):
            return await self._claude_commit(context, action)
        else:
            return await self._manual_commit(context, action)

    async def _claude_commit(
        self, context: models.WorkflowContext, action: models.WorkflowAction
    ) -> bool:
        """Leverage Claude Code to commit changes.

        Returns:
            True if a commit was made, False if no changes to commit
        """
        self.logger.info(
            '%s [%s/%s] %s using Claude Code to commit changes',
            context.imbi_project.slug,
            context.current_action_index,
            context.total_actions,
            action.name,
        )
        client = claude.Claude(self.configuration, context, self.verbose)

        # Build the commit prompt from the command template
        commit_template = BASE_PATH / 'prompts' / 'commit.md.j2'
        prompt = prompts.render(
            source=commit_template,
            action_name=action.name,
            **client.prompt_kwargs,
        )

        result = await client.agent_query(prompt)

        # Check if agent indicated no changes to commit
        if result.message:
            for phrase in ['no changes to commit', 'working tree is clean']:
                if phrase in result.message.lower():
                    return False

            # Check if commit failed
            if 'commit failed' in result.message.lower():
                raise RuntimeError(
                    f'Claude Code commit failed: {result.message}'
                )

        # Otherwise assume success
        return True

    async def _manual_commit(
        self, context: models.WorkflowContext, action: models.WorkflowAction
    ) -> bool:
        """Fallback commit implementation without Claude.

        - Stages all pending changes
        - Creates a commit with required format and trailer

        Returns:
            True if a commit was made, False if no changes to commit
        """
        repo_dir = context.working_directory / 'repository'

        # Stage all changes including deletions
        await git.add_files(working_directory=repo_dir)

        # Build commit message
        body = f'{action.commit_message}\n\n' if action.commit_message else ''
        message = (
            f'imbi-automations: {context.workflow.configuration.name} '
            f'- {action.name}\n\n{body}'
            '🤖 Generated with [Imbi Automations]'
            '(https://github.com/AWeber-Imbi/).'
        )
        try:
            commit_sha = await git.commit_changes(
                working_directory=repo_dir,
                message=message,
                user_name=self.configuration.git.user_name,
                user_email=self.configuration.git.user_email,
            )
        except RuntimeError as exc:
            self.logger.error(
                '%s %s git commit failed: %s',
                context.imbi_project.slug,
                action.name,
                exc,
            )
            raise
        else:
            if commit_sha:
                self.logger.info(
                    '%s [%s/%s] %s committed changes: %s',
                    context.imbi_project.slug,
                    context.current_action_index,
                    context.total_actions,
                    action.name,
                    commit_sha,
                )
                return True
            else:
                self.logger.info(
                    '%s [%s/%s] %s no changes to commit',
                    context.imbi_project.slug,
                    context.current_action_index,
                    context.total_actions,
                    action.name,
                )
                return False
