"""GitHub API client for repository operations and integrations.

Provides comprehensive GitHub API integration including repository
management, pull request creation, workflow file detection with pattern
support, environment synchronization, and repository tree operations for
remote file checking.
"""

import logging
import typing

import httpx

from imbi_automations import errors, models

from . import http

LOGGER = logging.getLogger(__name__)


class GitHub(http.BaseURLHTTPClient):
    """GitHub API client for repository operations and integrations.

    Provides comprehensive GitHub API access including repository
    retrieval, pull request creation, workflow management, environment
    operations, and file tree traversal for remote condition checking.
    """

    def __init__(
        self,
        config: models.Configuration,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not config.github:
            raise errors.ConfigurationError('GitHub configuration missing')

        super().__init__(transport)
        self._base_url = f'https://{config.github.host}'
        self.add_header(
            'Authorization', f'Bearer {config.github.token.get_secret_value()}'
        )
        self.add_header('X-GitHub-Api-Version', '2022-11-28')
        self.add_header('Accept', 'application/vnd.github+json')
        self.configuration = config

    async def get_repository(
        self, project: models.ImbiProject
    ) -> models.GitHubRepository | None:
        """Get a repository by name/slug in a specific organization."""
        if not self.configuration.imbi:
            raise errors.ConfigurationError('Imbi configuration missing')

        project_id = (
            project.identifiers.get(self.configuration.imbi.github_identifier)
            if project.identifiers
            else None
        )
        if project_id:
            return await self._get_repository_by_id(project_id)
        if project.links:
            link = project.links.get(self.configuration.imbi.github_link)
            if link:
                return await self.get_repository_by_url(link)
        return None

    async def _get_repository_by_id(
        self, repo_id: int
    ) -> models.GitHubRepository | None:
        """Get a repository by its GitHub repository ID.

        Args:
            repo_id: GitHub repository ID

        Returns:
            GitHubRepository object or None if not found

        Raises:
            httpx.HTTPError: If API request fails (except 404)

        """
        response = await self.get(f'/repositories/{repo_id}')
        if response.status_code == http.HTTPStatus.NOT_FOUND:
            LOGGER.debug('Repository not found for ID %s (404)', repo_id)
            return None
        elif response.status_code == http.HTTPStatus.FORBIDDEN:
            response_data = response.json() if response.content else {}
            message = response_data.get('message', response.text)

            # Check if it's specifically a rate limit error
            if 'rate limit exceeded' in message.lower():
                raise errors.GitHubRateLimitError(message)
            else:
                LOGGER.warning(
                    'Access forbidden for repository ID %s (403): %s',
                    repo_id,
                    message,
                )
                raise errors.GitHubNotFoundError(
                    f'Access denied for repository ID {repo_id}'
                )
        elif not response.is_success:
            LOGGER.error(
                'GitHub API error for repository ID %s (%s): %s',
                repo_id,
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        try:
            return models.GitHubRepository(**response.json())
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            LOGGER.error(
                'Failed to parse repository data for ID %s: %s', repo_id, exc
            )
            raise

    async def get_latest_workflow_run(
        self, org: str, repo_name: str
    ) -> models.GitHubWorkflowRun | None:
        """Get the most recent workflow run for a repository.

        Args:
            org: Organization name
            repo_name: Repository name

        Returns:
            Most recent GitHubWorkflowRun or None if no runs found

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo_name)
        response = await self.get(
            f'{base_path}/actions/runs',
            params={'per_page': 1},  # Get only the most recent run
        )
        response.raise_for_status()

        data = response.json()
        if data.get('workflow_runs') and len(data['workflow_runs']) > 0:
            return models.GitHubWorkflowRun.model_validate(
                data['workflow_runs'][0]
            )
        return None

    async def get_repository_workflow_status(
        self, repository: models.GitHubRepository
    ) -> str | None:
        """Get the status of the most recent GitHub Actions workflow run.

        Args:
            repository: GitHub repository to check workflow status for

        Returns:
            Status string or None if no runs

        """
        # Extract org and repo name from repository
        org, repo_name = repository.full_name.split('/', 1)

        last_run = await self.get_latest_workflow_run(org, repo_name)
        return last_run.conclusion or last_run.status if last_run else None

    async def get_repository_environments(
        self, org: str, repo: str
    ) -> list[models.GitHubEnvironment]:
        """Get all environments for a repository.

        Args:
            org: Organization name
            repo: Repository name

        Returns:
            List of GitHubEnvironment objects

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo)

        try:
            response = await self.get(f'{base_path}/environments')
            response.raise_for_status()

            data = response.json()
            environments = []

            if 'environments' in data:
                for env_data in data['environments']:
                    environments.append(
                        models.GitHubEnvironment.model_validate(env_data)
                    )

            LOGGER.debug(
                'Found %d environments for repository %s/%s: %s',
                len(environments),
                org,
                repo,
                [env.name for env in environments],
            )

            return environments

        except httpx.HTTPError as exc:
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code == http.HTTPStatus.NOT_FOUND
            ):
                LOGGER.debug('Repository %s/%s not found (404)', org, repo)
                raise errors.GitHubNotFoundError(
                    f'Repository {org}/{repo} not found'
                ) from exc
            else:
                LOGGER.error(
                    'Failed to get environments for %s/%s: %s', org, repo, exc
                )
                raise

    async def create_environment(
        self, org: str, repo: str, environment_name: str
    ) -> models.GitHubEnvironment:
        """Create a new environment for a repository.

        Args:
            org: Organization name
            repo: Repository name
            environment_name: Name of the environment to create

        Returns:
            Created GitHubEnvironment object

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo)

        try:
            response = await self.put(
                f'{base_path}/environments/{environment_name}'
            )
            response.raise_for_status()

            env_data = response.json()
            environment = models.GitHubEnvironment.model_validate(env_data)

            LOGGER.info(
                'Created environment "%s" for repository %s/%s',
                environment_name,
                org,
                repo,
            )

            return environment

        except httpx.HTTPError as exc:
            LOGGER.error(
                'Failed to create environment "%s" for %s/%s: %s',
                environment_name,
                org,
                repo,
                exc,
            )
            raise

    async def delete_environment(
        self, org: str, repo: str, environment_name: str
    ) -> bool:
        """Delete an environment from a repository.

        Args:
            org: Organization name
            repo: Repository name
            environment_name: Name of the environment to delete

        Returns:
            True if environment was deleted successfully

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo)

        try:
            response = await self.delete(
                f'{base_path}/environments/{environment_name}'
            )
            response.raise_for_status()

            LOGGER.info(
                'Deleted environment "%s" from repository %s/%s',
                environment_name,
                org,
                repo,
            )

            return True

        except httpx.HTTPError as exc:
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code == http.HTTPStatus.NOT_FOUND
            ):
                LOGGER.warning(
                    'Environment "%s" not found in %s/%s (already deleted?)',
                    environment_name,
                    org,
                    repo,
                )
                return True  # Consider it successful if already gone
            else:
                LOGGER.error(
                    'Failed to delete environment "%s" from %s/%s: %s',
                    environment_name,
                    org,
                    repo,
                    exc,
                )
                raise

    async def create_pull_request(
        self,
        context: 'models.WorkflowContext',
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = 'main',
    ) -> models.GitHubPullRequest:
        """Create a pull request and return the PR object.

        Args:
            context: Workflow context containing GitHub repository info
            title: Pull request title
            body: Pull request description
            head_branch: Source branch name
            base_branch: Target branch name (default: 'main')

        Returns:
            GitHubPullRequest object with full PR details

        Raises:
            httpx.HTTPError: If pull request creation fails

        """
        if not context.github_repository:
            raise ValueError('No GitHub repository in workflow context')

        base_path = self._repository_base_path(context=context)
        org = context.github_repository.owner.login
        repo = context.github_repository.name

        LOGGER.debug(
            'Creating pull request for %s/%s: %s -> %s',
            org,
            repo,
            head_branch,
            base_branch,
        )

        payload = {
            'title': title,
            'body': body,
            'head': head_branch,
            'base': base_branch,
        }

        response = await self.post(f'{base_path}/pulls', json=payload)
        response.raise_for_status()

        pr = models.GitHubPullRequest.model_validate(response.json())

        LOGGER.info(
            'Created pull request #%d for %s/%s: %s',
            pr.number,
            org,
            repo,
            pr.html_url,
        )

        return pr

    async def _get_most_recent_workflow_run_id(
        self, org: str, repo_name: str, branch: str = 'main'
    ) -> int | None:
        """Get the most recent workflow run ID for a repository.

        Args:
            org: Organization name
            repo_name: Repository name
            branch: Optional branch name to filter workflow runs

        Returns:
            Workflow run ID or None if no runs found

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo_name)
        response = await self.get(
            f'{base_path}/actions/runs',
            params={'per_page': 1, 'branch': branch},
        )
        response.raise_for_status()

        data = response.json()
        workflow_runs = data.get('workflow_runs', [])

        if not workflow_runs:
            LOGGER.debug('No workflow runs found for %s/%s', org, repo_name)
            return None

        return workflow_runs[0]['id']

    def _repository_base_path(
        self,
        context: 'models.WorkflowContext | None' = None,
        org: str | None = None,
        repo_name: str | None = None,
        repository: models.GitHubRepository | None = None,
    ) -> str:
        """Build base repository path for GitHub API requests.

        Args:
            context: Workflow context containing GitHub repository
            org: Organization name (alternative to context/repository)
            repo_name: Repository name (alternative to context/repository)
            repository: GitHub repository object (alternative to context)

        Returns:
            Base path string in format /repos/{org}/{repo}

        Raises:
            ValueError: If insufficient parameters provided

        """
        if context and context.github_repository:
            owner = context.github_repository.owner.login
            name = context.github_repository.name
            return f'/repos/{owner}/{name}'
        if repository:
            return f'/repos/{repository.owner.login}/{repository.name}'
        if org and repo_name:
            return f'/repos/{org}/{repo_name}'
        raise ValueError(
            'Must provide context, repository, or org+repo_name parameters'
        )

    async def _get_workflow_run_jobs(
        self, org: str, repo_name: str, run_id: int
    ) -> list[dict]:
        """Get all jobs for a workflow run.

        Args:
            org: Organization name
            repo_name: Repository name
            run_id: Workflow run ID

        Returns:
            List of job dictionaries

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo_name)
        response = await self.get(f'{base_path}/actions/runs/{run_id}/jobs')
        response.raise_for_status()

        data = response.json()
        return data.get('jobs', [])

    async def _get_job_logs(
        self, org: str, repo_name: str, job_id: int, job_name: str
    ) -> str:
        """Get logs for a specific job.

        Args:
            org: Organization name
            repo_name: Repository name
            job_id: Job ID
            job_name: Job name (for logging)

        Returns:
            Log contents as string, empty string if logs unavailable

        """
        base_path = self._repository_base_path(org=org, repo_name=repo_name)
        response = await self.get(
            f'{base_path}/actions/jobs/{job_id}/logs', follow_redirects=True
        )
        response.raise_for_status()

        LOGGER.debug(
            'Retrieved %d bytes of logs for job "%s" (ID: %d)',
            len(response.text),
            job_name,
            job_id,
        )

        return response.text

    async def get_most_recent_job_logs(
        self, repository: models.GitHubRepository, branch: str | None = None
    ) -> dict[str, str]:
        """Get logs for all jobs in the most recent workflow run.

        Args:
            repository: GitHub repository to fetch logs from
            branch: Optional branch name to filter workflow runs

        Returns:
            Dictionary mapping job names to their log contents.
            Jobs with unavailable logs will have empty string values.

        Raises:
            httpx.HTTPError: If API request fails

        """
        org, repo_name = repository.full_name.split('/', 1)

        run_id = await self._get_most_recent_workflow_run_id(
            org, repo_name, branch
        )
        if not run_id:
            return {}

        LOGGER.debug(
            'Fetching logs for workflow run %d in %s/%s',
            run_id,
            org,
            repo_name,
        )

        jobs = await self._get_workflow_run_jobs(org, repo_name, run_id)
        if not jobs:
            LOGGER.debug('No jobs found for workflow run %d', run_id)
            return {}

        job_logs = {}
        for job in jobs:
            job_id = job['id']
            job_name = job['name']

            logs = await self._get_job_logs(org, repo_name, job_id, job_name)
            job_logs[job_name] = logs

        return job_logs

    async def get_file_contents(
        self, context: 'models.WorkflowContext', file_path: str
    ) -> str | None:
        """Get file contents from GitHub repository.

        For files >1MB, GitHub's API doesn't include the content field
        in the response. In such cases, this method automatically downloads
        the content via the download_url field.

        Args:
            context: Workflow context containing GitHub repository info
            file_path: Path to the file in the repository

        Returns:
            File contents as string, or None if file doesn't exist

        Raises:
            ValueError: If no GitHub repository in context
            httpx.HTTPError: If API request fails (other than 404)

        """
        if not context.github_repository:
            raise ValueError('No GitHub repository in workflow context')

        base_path = self._repository_base_path(context=context)
        org = context.github_repository.owner.login
        repo = context.github_repository.name

        LOGGER.debug(
            'Getting file contents for %s from %s/%s', file_path, org, repo
        )

        try:
            response = await self.get(f'{base_path}/contents/{file_path}')
            response.raise_for_status()

            file_data = response.json()

            # Handle file vs directory response
            if isinstance(file_data, list):
                # Path points to directory, not file
                LOGGER.debug(
                    'Path %s is a directory in %s/%s, not a file',
                    file_path,
                    org,
                    repo,
                )
                return None

            # Check if it's a file
            if file_data.get('type') != 'file':
                LOGGER.debug(
                    'Path %s is not a file in %s/%s (type: %s)',
                    file_path,
                    org,
                    repo,
                    file_data.get('type'),
                )
                return None

            # Decode file content
            import base64

            content = file_data.get('content', '')
            if content:
                try:
                    decoded_content = base64.b64decode(content).decode('utf-8')
                    LOGGER.debug(
                        'Retrieved %d bytes from %s in %s/%s',
                        len(decoded_content),
                        file_path,
                        org,
                        repo,
                    )
                    return decoded_content
                except (ValueError, UnicodeDecodeError) as exc:
                    LOGGER.warning(
                        'Failed to decode file %s from %s/%s: %s',
                        file_path,
                        org,
                        repo,
                        exc,
                    )
                    return None

            # For large files (>1MB), GitHub doesn't include content field
            # Use download_url instead
            download_url = file_data.get('download_url')
            if download_url:
                LOGGER.debug(
                    'File %s is large, downloading from %s',
                    file_path,
                    download_url,
                )
                try:
                    download_response = await self.get(download_url)
                    download_response.raise_for_status()
                    file_content = download_response.text
                    LOGGER.debug(
                        'Downloaded %d bytes from %s in %s/%s',
                        len(file_content),
                        file_path,
                        org,
                        repo,
                    )
                    return file_content
                except (httpx.HTTPError, UnicodeDecodeError) as exc:
                    LOGGER.warning(
                        'Failed to download file %s from %s/%s: %s',
                        file_path,
                        org,
                        repo,
                        exc,
                    )
                    return None

            return ''  # Empty file

        except httpx.HTTPError as exc:
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code == http.HTTPStatus.NOT_FOUND
            ):
                LOGGER.debug(
                    'File %s not found in %s/%s', file_path, org, repo
                )
                return None
            else:
                LOGGER.error(
                    'Failed to get file %s from %s/%s: %s',
                    file_path,
                    org,
                    repo,
                    exc,
                )
                raise

    async def get_repository_tree(
        self, context: 'models.WorkflowContext', ref: str | None = None
    ) -> list[str]:
        """Get repository file tree recursively from GitHub.

        Uses Git Trees API to fetch all files in repository efficiently.
        Limited to 100,000 entries / 7MB response size.

        Args:
            context: Workflow context containing GitHub repository info
            ref: Git ref (branch/tag/commit). Defaults to default branch

        Returns:
            List of file paths in the repository

        Raises:
            ValueError: If no GitHub repository in context
            httpx.HTTPError: If API request fails

        """
        if not context.github_repository:
            raise ValueError('No GitHub repository in workflow context')

        base_path = self._repository_base_path(context=context)
        org = context.github_repository.owner.login
        repo = context.github_repository.name
        tree_sha = ref if ref else context.github_repository.default_branch

        LOGGER.debug(
            'Getting repository tree for %s/%s at %s', org, repo, tree_sha
        )

        try:
            response = await self.get(
                f'{base_path}/git/trees/{tree_sha}?recursive=true'
            )
            response.raise_for_status()

            tree_data = response.json()
            tree_entries = tree_data.get('tree', [])

            # Extract file paths (exclude directories)
            file_paths = [
                entry['path']
                for entry in tree_entries
                if entry.get('type') == 'blob'
            ]

            LOGGER.debug(
                'Retrieved %d files from %s/%s tree',
                len(file_paths),
                org,
                repo,
            )

            return file_paths

        except httpx.HTTPError as exc:
            LOGGER.error(
                'Failed to get repository tree for %s/%s: %s', org, repo, exc
            )
            raise

    async def update_repository(
        self, org: str, repo: str, attributes: dict[str, typing.Any]
    ) -> models.GitHubRepository:
        """Update repository attributes via GitHub API.

        Args:
            org: Organization name
            repo: Repository name
            attributes: Dictionary of attributes to update (e.g., description,
                homepage, private, has_issues, has_projects, has_wiki, etc.)

        Returns:
            Updated GitHubRepository object

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo)

        LOGGER.debug(
            'Updating repository %s/%s with attributes: %s',
            org,
            repo,
            attributes,
        )

        try:
            response = await self.patch(base_path, json=attributes)
            response.raise_for_status()

            repo_data = response.json()
            repository = models.GitHubRepository.model_validate(repo_data)

            LOGGER.info('Updated repository %s/%s successfully', org, repo)

            return repository

        except httpx.HTTPError as exc:
            LOGGER.error(
                'Failed to update repository %s/%s: %s', org, repo, exc
            )
            raise

    async def get_pull_request(
        self, org: str, repo: str, pr_number: int
    ) -> models.GitHubPullRequest:
        """Get pull request details by number.

        Args:
            org: Organization name
            repo: Repository name
            pr_number: Pull request number

        Returns:
            GitHubPullRequest with current status

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo)

        response = await self.get(f'{base_path}/pulls/{pr_number}')
        response.raise_for_status()

        return models.GitHubPullRequest.model_validate(response.json())

    async def list_pull_requests(
        self,
        org: str,
        repo: str,
        state: str = 'all',
        head: str | None = None,
        base: str | None = None,
        per_page: int = 100,
    ) -> list[models.GitHubPullRequest]:
        """List pull requests for a repository with optional filtering.

        Uses GitHub API: GET /repos/{owner}/{repo}/pulls

        Args:
            org: Organization name
            repo: Repository name
            state: Filter by state ('open', 'closed', 'all'). Default: 'all'
            head: Filter by head branch (format: 'user:ref-name' or 'ref-name')
            base: Filter by base branch
            per_page: Results per page (max 100, default 100)

        Returns:
            List of GitHubPullRequest objects. Returns empty list if
            repository not found (404).

        Raises:
            httpx.HTTPError: If API request fails (except 404)

        """
        base_path = self._repository_base_path(org=org, repo_name=repo)

        params = {'state': state, 'per_page': per_page}
        if head:
            params['head'] = head
        if base:
            params['base'] = base

        LOGGER.debug(
            'Listing pull requests for %s/%s with params: %s',
            org,
            repo,
            params,
        )

        try:
            response = await self.get(f'{base_path}/pulls', params=params)
            response.raise_for_status()

            data = response.json()

            # Parse all PR objects
            pull_requests = [
                models.GitHubPullRequest.model_validate(pr_data)
                for pr_data in data
            ]

            LOGGER.debug(
                'Found %d pull requests for %s/%s',
                len(pull_requests),
                org,
                repo,
            )

            return pull_requests

        except httpx.HTTPError as exc:
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code == http.HTTPStatus.NOT_FOUND
            ):
                LOGGER.debug('Repository %s/%s not found (404)', org, repo)
                return []
            else:
                LOGGER.error(
                    'Failed to list pull requests for %s/%s: %s',
                    org,
                    repo,
                    exc,
                )
                raise

    async def get_pr_check_runs(
        self, org: str, repo: str, ref: str
    ) -> list[dict[str, typing.Any]]:
        """Get check runs for a commit (typically PR head).

        Args:
            org: Organization name
            repo: Repository name
            ref: Git ref (commit SHA, branch, or tag)

        Returns:
            List of check run dictionaries

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo)

        response = await self.get(f'{base_path}/commits/{ref}/check-runs')
        response.raise_for_status()

        return response.json().get('check_runs', [])

    async def get_pr_reviews(
        self, org: str, repo: str, pr_number: int
    ) -> list[dict[str, typing.Any]]:
        """Get reviews for a pull request.

        Args:
            org: Organization name
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of review dictionaries

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo)

        response = await self.get(f'{base_path}/pulls/{pr_number}/reviews')
        response.raise_for_status()

        return response.json()

    async def get_pr_comments(
        self, org: str, repo: str, pr_number: int
    ) -> list[dict[str, typing.Any]]:
        """Get review comments for a pull request.

        Args:
            org: Organization name
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of comment dictionaries

        Raises:
            httpx.HTTPError: If API request fails

        """
        base_path = self._repository_base_path(org=org, repo_name=repo)

        response = await self.get(f'{base_path}/pulls/{pr_number}/comments')
        response.raise_for_status()

        return response.json()
