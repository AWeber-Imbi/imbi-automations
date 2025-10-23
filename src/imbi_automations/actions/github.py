"""GitHub operations for workflow execution."""

import typing

import httpx

from imbi_automations import clients, errors, mixins, models


class GitHubActions(mixins.WorkflowLoggerMixin):
    """Executes GitHub-specific operations via API integration.

    Handles GitHub environment synchronization and repository management
    workflows.
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

    async def execute(self, action: models.WorkflowGitHubAction) -> None:
        match action.command:
            case models.WorkflowGitHubCommand.sync_environments:
                await self._sync_environments(action)
            case _:
                raise RuntimeError(f'Unsupported command: {action.command}')

    async def _sync_environments(
        self, action: models.WorkflowGitHubAction
    ) -> None:
        """Synchronize GitHub repository environments with Imbi project.

        Args:
            action: GitHub action configuration

        Raises:
            ValueError: If github_repository is not in context
            RuntimeError: If sync fails

        """
        if not self.context.github_repository:
            raise ValueError('No GitHub repository in workflow context')

        # Extract org and repo from GitHub repository
        org, repo = self.context.github_repository.full_name.split('/', 1)

        # Get environment slugs from Imbi project
        # Extract slug from each ImbiEnvironment object
        # Sort for consistent ordering in logs and operations
        imbi_environment_slugs = sorted(
            [
                env.slug
                for env in (self.context.imbi_project.environments or [])
            ]
        )

        # Log start of sync
        self.logger.info(
            '%s %s syncing environments for %s/%s: %s',
            self.context.imbi_project.slug,
            action.name,
            org,
            repo,
            imbi_environment_slugs,
        )

        # Check if project has environments to sync
        if not imbi_environment_slugs:
            self.logger.info(
                '%s %s no environments defined in Imbi, skipping sync',
                self.context.imbi_project.slug,
                action.name,
            )
            return

        # Create GitHub client
        github_client = clients.GitHub(self.configuration)

        # Perform sync
        result = await self._sync_project_environments(
            org=org,
            repo=repo,
            imbi_environments=imbi_environment_slugs,
            github_client=github_client,
        )

        # Log results
        if result['success']:
            self._log_verbose_info(
                '%s %s successfully synced environments: '
                'created %d, deleted %d',
                self.context.imbi_project.slug,
                action.name,
                len(result['created']),
                len(result['deleted']),
            )
            if result['created']:
                self.logger.debug(
                    '%s %s created environments: %s',
                    self.context.imbi_project.slug,
                    action.name,
                    ', '.join(result['created']),
                )
            if result['deleted']:
                self.logger.debug(
                    '%s %s deleted environments: %s',
                    self.context.imbi_project.slug,
                    action.name,
                    ', '.join(result['deleted']),
                )
        else:
            error_summary = '; '.join(result['errors'][:3])
            if len(result['errors']) > 3:
                error_summary += f' (and {len(result["errors"]) - 3} more)'
            self.logger.error(
                '%s %s failed to sync environments: %s',
                self.context.imbi_project.slug,
                action.name,
                error_summary,
            )
            raise RuntimeError(f'Environment sync failed: {error_summary}')

    async def _sync_project_environments(
        self,
        org: str,
        repo: str,
        imbi_environments: list[str],
        github_client: clients.GitHub,
    ) -> dict[str, typing.Any]:
        """Synchronize environments between Imbi project and GitHub repository.

        This function ensures that the GitHub repository environments match the
        environments defined in the Imbi project. It will:
        1. Remove GitHub environments that don't exist in Imbi
        2. Create GitHub environments that exist in Imbi but not in GitHub

        Environment names use slugified format (lowercase, hyphens instead of
        spaces) for consistency across systems.

        Args:
            org: GitHub organization name
            repo: GitHub repository name
            imbi_environments: List of environment slugs from Imbi project
                (e.g., ['development', 'staging', 'production'])
            github_client: GitHub API client

        Returns:
            Dictionary with sync results including:
            - success: bool - Whether sync completed successfully
            - created: list[str] - Environments created in GitHub
            - deleted: list[str] - Environments deleted from GitHub
            - errors: list[str] - Any errors encountered
            - total_operations: int - Total number of operations performed

        """
        result: dict[str, typing.Any] = {
            'success': False,
            'created': [],
            'deleted': [],
            'errors': [],
            'total_operations': 0,
        }

        try:
            # Get current GitHub environments
            try:
                github_environments = (
                    await github_client.get_repository_environments(org, repo)
                )
                github_env_list = [env.name for env in github_environments]

                self.logger.debug(
                    'Found %d GitHub environments for %s/%s: %s',
                    len(github_environments),
                    org,
                    repo,
                    github_env_list,
                )

            except errors.GitHubNotFoundError:
                self.logger.error(
                    'Repository %s/%s not found during environment sync',
                    org,
                    repo,
                )
                result['errors'].append(f'Repository {org}/{repo} not found')
                return result

            except httpx.HTTPError as exc:
                error_msg = f'Failed to get GitHub environments: {exc}'
                self.logger.error(error_msg)
                result['errors'].append(error_msg)
                return result

            # Calculate differences (slugs are already lowercase)
            # Note: Using sets here deduplicates any identical slugs.
            # This is expected behavior - Imbi should not allow duplicate
            # environment names in a project, but if it does, we sync
            # the unique set of slugs to GitHub.
            imbi_env_set = set(imbi_environments)
            github_env_set = set(github_env_list)

            # Find environments to create/delete and sort for consistency
            environments_to_create = sorted(imbi_env_set - github_env_set)
            environments_to_delete = sorted(github_env_set - imbi_env_set)

            self.logger.debug(
                'Environment sync plan for %s/%s: create=%s, delete=%s',
                org,
                repo,
                list(environments_to_create),
                list(environments_to_delete),
            )

            # Delete extra environments from GitHub
            for env_name in environments_to_delete:
                result['total_operations'] += 1
                try:
                    await github_client.delete_environment(org, repo, env_name)
                    result['deleted'].append(env_name)
                    self.logger.info(
                        'Deleted environment "%s" from %s/%s',
                        env_name,
                        org,
                        repo,
                    )
                except httpx.HTTPError as exc:
                    error_msg = (
                        f'Failed to delete environment "{env_name}": {exc}'
                    )
                    self.logger.error(error_msg)
                    result['errors'].append(error_msg)

            # Create missing environments in GitHub
            for env_name in environments_to_create:
                result['total_operations'] += 1
                try:
                    await github_client.create_environment(org, repo, env_name)
                    result['created'].append(env_name)
                    self.logger.info(
                        'Created environment "%s" in %s/%s',
                        env_name,
                        org,
                        repo,
                    )
                except httpx.HTTPError as exc:
                    error_msg = (
                        f'Failed to create environment "{env_name}": {exc}'
                    )
                    self.logger.error(error_msg)
                    result['errors'].append(error_msg)

            # Determine overall success
            result['success'] = len(result['errors']) == 0

            if result['success']:
                self.logger.debug(
                    'Environment sync completed successfully for %s/%s: '
                    'created %d, deleted %d',
                    org,
                    repo,
                    len(result['created']),
                    len(result['deleted']),
                )
            else:
                self.logger.warning(
                    'Environment sync completed with errors for %s/%s: '
                    'created %d, deleted %d, errors %d',
                    org,
                    repo,
                    len(result['created']),
                    len(result['deleted']),
                    len(result['errors']),
                )

            return result

        except (ValueError, RuntimeError) as exc:
            error_msg = f'Unexpected error during environment sync: {exc}'
            self.logger.error(error_msg)
            result['errors'].append(error_msg)
            return result
