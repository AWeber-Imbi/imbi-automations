"""GitHub environment synchronization logic for Imbi projects.

Synchronizes GitHub repository environments with Imbi project environment
definitions, creating, updating, or deleting environments as needed to maintain
consistency between the two systems.
"""

import logging
import typing

import httpx

from imbi_automations import clients, errors, models

LOGGER = logging.getLogger(__name__)


class SyncResult(typing.TypedDict):
    """Result dictionary from environment synchronization."""

    success: bool
    created: list[str]
    deleted: list[str]
    errors: list[str]
    total_operations: int


async def sync_project_environments(
    org: str,
    repo: str,
    imbi_environments: list[str] | str,
    github_client: clients.GitHub,
) -> SyncResult:
    """Synchronize environments between Imbi project and GitHub repository.

    This function ensures that the GitHub repository environments match the
    environments defined in the Imbi project. It will:
    1. Remove GitHub environments that don't exist in Imbi
    2. Create GitHub environments that exist in Imbi but not in GitHub

    Args:
        org: GitHub organization name
        repo: GitHub repository name
        imbi_environments: List of environment names from Imbi project,
            or string representation from template rendering
        github_client: GitHub API client

    Returns:
        Dictionary with sync results including:
        - success: bool - Whether sync completed successfully
        - created: list[str] - Environments created in GitHub
        - deleted: list[str] - Environments deleted from GitHub
        - errors: list[str] - Any errors encountered
        - total_operations: int - Total number of operations performed

    """
    result: SyncResult = {
        'success': False,
        'created': [],
        'deleted': [],
        'errors': [],
        'total_operations': 0,
    }

    try:
        # Parse environments if they come as a string representation
        if isinstance(imbi_environments, str):
            # Handle HTML entities and parse the string representation
            import ast
            import html

            decoded_envs = html.unescape(imbi_environments)
            try:
                parsed_envs = ast.literal_eval(decoded_envs)
                if isinstance(parsed_envs, list):
                    imbi_environments = parsed_envs
                elif parsed_envs is None:
                    imbi_environments = []
                else:
                    LOGGER.warning(
                        'Expected list but got %s: %s',
                        type(parsed_envs),
                        parsed_envs,
                    )
                    imbi_environments = []
            except (ValueError, SyntaxError) as exc:
                LOGGER.error(
                    'Failed to parse environments string "%s": %s',
                    decoded_envs[:100],
                    exc,
                )
                imbi_environments = []

        # Use provided parameters directly
        imbi_env_list = list(imbi_environments or [])

        LOGGER.debug(
            'Starting environment sync for %s/%s. Imbi environments: %s',
            org,
            repo,
            imbi_env_list,
        )

        # Get current GitHub environments
        try:
            github_environments = (
                await github_client.get_repository_environments(org, repo)
            )
            github_env_list = [env.name for env in github_environments]

            LOGGER.debug(
                'Found %d GitHub environments for %s/%s: %s',
                len(github_environments),
                org,
                repo,
                github_env_list,
            )

        except errors.GitHubNotFoundError:
            LOGGER.error(
                'Repository %s/%s not found during environment sync', org, repo
            )
            result['errors'].append(f'Repository {org}/{repo} not found')
            return result

        except httpx.HTTPError as exc:
            error_msg = f'Failed to get GitHub environments: {exc}'
            LOGGER.error(error_msg)
            result['errors'].append(error_msg)
            return result

        # Calculate differences using case-insensitive comparison
        # Create mapping of lowercase names to actual names for both sides
        imbi_env_map = {env.lower(): env for env in imbi_env_list}
        github_env_map = {env.lower(): env for env in github_env_list}

        # Find environments to create/delete using lowercase keys
        imbi_keys = set(imbi_env_map.keys())
        github_keys = set(github_env_map.keys())

        keys_to_create = imbi_keys - github_keys
        keys_to_delete = github_keys - imbi_keys

        # Map back to actual environment names
        environments_to_create = [imbi_env_map[key] for key in keys_to_create]
        environments_to_delete = [
            github_env_map[key] for key in keys_to_delete
        ]

        LOGGER.debug(
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
                LOGGER.info(
                    'Deleted environment "%s" from %s/%s', env_name, org, repo
                )
            except httpx.HTTPError as exc:
                error_msg = f'Failed to delete environment "{env_name}": {exc}'
                LOGGER.error(error_msg)
                result['errors'].append(error_msg)

        # Create missing environments in GitHub
        for env_name in environments_to_create:
            result['total_operations'] += 1
            try:
                await github_client.create_environment(org, repo, env_name)
                result['created'].append(env_name)
                LOGGER.info(
                    'Created environment "%s" in %s/%s', env_name, org, repo
                )
            except httpx.HTTPError as exc:
                error_msg = f'Failed to create environment "{env_name}": {exc}'
                LOGGER.error(error_msg)
                result['errors'].append(error_msg)

        # Determine overall success
        result['success'] = len(result['errors']) == 0

        if result['success']:
            LOGGER.debug(
                'Environment sync completed successfully for %s/%s: '
                'created %d, deleted %d',
                org,
                repo,
                len(result['created']),
                len(result['deleted']),
            )
        else:
            LOGGER.warning(
                'Environment sync completed with errors for %s/%s: '
                'created %d, deleted %d, errors %d',
                org,
                repo,
                len(result['created']),
                len(result['deleted']),
                len(result['errors']),
            )

        return result

    except (ValueError, RuntimeError, KeyError) as exc:
        error_msg = f'Unexpected error during environment sync: {exc}'
        LOGGER.error(error_msg)
        result['errors'].append(error_msg)
        return result


def should_sync_environments(imbi_project: models.ImbiProject) -> bool:
    """Check if a project should have its environments synchronized.

    Args:
        imbi_project: Imbi project to check

    Returns:
        True if the project has environments that should be synced

    """
    # Only sync if the project has environments defined
    environments = imbi_project.environments
    has_environments = environments is not None and len(environments) > 0

    LOGGER.debug(
        'Environment sync check for project %d (%s): '
        'environments=%s, should_sync=%s',
        imbi_project.id,
        imbi_project.name,
        environments,
        has_environments,
    )

    return has_environments


def get_environment_sync_summary(sync_result: dict[str, typing.Any]) -> str:
    """Generate a human-readable summary of environment sync results.

    Args:
        sync_result: Result dictionary from sync_project_environments

    Returns:
        Human-readable summary string

    """
    if not sync_result.get('success', False):
        if sync_result.get('errors'):
            error_summary = '; '.join(sync_result['errors'][:3])  # Limit to 3
            if len(sync_result['errors']) > 3:
                error_count = len(sync_result['errors']) - 3
                error_summary += f' (and {error_count} more)'
            return f'Failed: {error_summary}'
        else:
            return 'Failed: Unknown error'

    operations = sync_result.get('total_operations', 0)
    created = len(sync_result.get('created', []))
    deleted = len(sync_result.get('deleted', []))

    if operations == 0:
        return 'Success: No changes needed'
    else:
        return f'Success: Created {created}, deleted {deleted} environments'
