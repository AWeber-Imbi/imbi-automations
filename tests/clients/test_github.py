"""Tests for clients/github.py - GitHub API client.

Covers repository operations, pull requests, environments, workflows,
and file operations with proper method signatures.
"""

# ruff: noqa: S106, S108

import pathlib
import typing

import httpx

from imbi_automations import errors, models
from imbi_automations.clients import github
from tests import base


def create_test_project(**kwargs: typing.Any) -> models.ImbiProject:  # noqa: ANN401
    """Helper to create test ImbiProject with defaults."""
    defaults = {
        'id': 1,
        'dependencies': None,
        'description': 'Test project',
        'environments': None,
        'facts': None,
        'identifiers': None,
        'links': None,
        'name': 'test-project',
        'namespace': 'test-namespace',
        'namespace_slug': 'test-namespace',
        'project_score': None,
        'project_type': 'API',
        'project_type_slug': 'api',
        'slug': 'test-project',
        'urls': None,
        'imbi_url': 'https://imbi.example.com/projects/1',
    }
    defaults.update(kwargs)
    return models.ImbiProject(**defaults)


def create_test_repository(**kwargs: typing.Any) -> models.GitHubRepository:  # noqa: ANN401
    """Helper to create test GitHubRepository with defaults."""
    defaults = {
        'id': 12345,
        'node_id': 'MDEwOlJlcG9zaXRvcnkxMjM0NQ==',
        'name': 'test-repo',
        'full_name': 'test-org/test-repo',
        'default_branch': 'main',
        'private': False,
        'html_url': 'https://github.com/test-org/test-repo',
        'description': 'Test repository',
        'fork': False,
        'url': 'https://api.github.com/repos/test-org/test-repo',
        'clone_url': 'https://github.com/test-org/test-repo.git',
        'ssh_url': 'git@github.com:test-org/test-repo.git',
        'git_url': 'git://github.com/test-org/test-repo.git',
        'owner': {
            'login': 'test-org',
            'id': 123,
            'node_id': 'MDQ6VXNlcjEyMw==',
            'avatar_url': 'https://avatars.githubusercontent.com/u/123',
            'url': 'https://api.github.com/users/test-org',
            'html_url': 'https://github.com/test-org',
            'type': 'Organization',
        },
    }
    defaults.update(kwargs)
    return models.GitHubRepository(**defaults)


def create_test_workflow_context(
    **kwargs: typing.Any,  # noqa: ANN401
) -> models.WorkflowContext:
    """Helper to create test WorkflowContext with defaults."""
    workflow = models.Workflow(
        path=pathlib.Path('/tmp/workflow'),
        configuration=models.WorkflowConfiguration(
            name='test-workflow', actions=[]
        ),
    )
    defaults = {
        'workflow': workflow,
        'imbi_project': create_test_project(),
        'github_repository': create_test_repository(),
        'working_directory': pathlib.Path('/tmp/work'),
        'starting_commit': 'abc123',
        'variables': {},
    }
    defaults.update(kwargs)
    return models.WorkflowContext(**defaults)


def create_github_repo_response_data(**kwargs: typing.Any) -> dict:  # noqa: ANN401
    """Helper to create GitHub API repository response data."""
    defaults = {
        'id': 12345,
        'node_id': 'MDEwOlJlcG9zaXRvcnkxMjM0NQ==',
        'name': 'test-repo',
        'full_name': 'org/test-repo',
        'default_branch': 'main',
        'private': False,
        'html_url': 'https://github.com/org/test-repo',
        'description': 'Test repository',
        'fork': False,
        'url': 'https://api.github.com/repos/org/test-repo',
        'clone_url': 'https://github.com/org/test-repo.git',
        'ssh_url': 'git@github.com:org/test-repo.git',
        'git_url': 'git://github.com/org/test-repo.git',
        'owner': {
            'login': 'org',
            'id': 123,
            'node_id': 'MDQ6VXNlcjEyMw==',
            'avatar_url': 'https://avatars.githubusercontent.com/u/123',
            'url': 'https://api.github.com/users/org',
            'html_url': 'https://github.com/org',
            'type': 'Organization',
        },
    }
    defaults.update(kwargs)
    return defaults


def create_github_pr_response_data(**kwargs: typing.Any) -> dict:  # noqa: ANN401
    """Helper to create GitHub API pull request response data."""
    defaults = {
        'id': 999,
        'number': 123,
        'html_url': 'https://github.com/org/repo/pull/123',
        'title': 'Test PR',
        'state': 'open',
        'created_at': '2025-01-01T00:00:00Z',
        'url': 'https://api.github.com/repos/org/repo/pulls/123',
        'user': {
            'login': 'test-user',
            'id': 456,
            'node_id': 'MDQ6VXNlcjQ1Ng==',
            'avatar_url': 'https://avatars.githubusercontent.com/u/456',
            'url': 'https://api.github.com/users/test-user',
            'html_url': 'https://github.com/test-user',
            'type': 'User',
        },
        'head': {'ref': 'feature', 'sha': 'abc123'},
        'base': {'ref': 'main', 'sha': 'def456'},
    }
    defaults.update(kwargs)
    return defaults


def create_github_workflow_run_data(**kwargs: typing.Any) -> dict:  # noqa: ANN401
    """Helper to create GitHub API workflow run response data."""
    defaults = {
        'id': 123,
        'node_id': 'MDEyOldvcmtmbG93UnVuMTIz',
        'run_number': 42,
        'event': 'push',
        'workflow_id': 456,
        'check_suite_id': 789,
        'check_suite_node_id': 'MDEyOkNoZWNrU3VpdGU3ODk=',
        'name': 'CI',
        'status': 'completed',
        'conclusion': 'success',
        'head_branch': 'main',
        'head_sha': 'abc123',
        'path': '.github/workflows/ci.yml',
        'url': 'https://api.github.com/repos/org/repo/actions/runs/123',
        'html_url': 'https://github.com/org/repo/actions/runs/123',
        'created_at': '2025-01-01T00:00:00Z',
    }
    defaults.update(kwargs)
    return defaults


class GitHubRepositoryTestCase(base.AsyncTestCase):
    """Test GitHub repository retrieval methods."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-token', host='api.github.com'
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key',
                hostname='imbi.example.com',
                github_identifier='github',
                github_link='GitHub',
            ),
        )
        self.client = github.GitHub(
            self.config, transport=self.http_client_transport
        )

    async def test_get_repository_by_identifier(self) -> None:
        """Test repository retrieval via project identifier."""
        project = create_test_project(identifiers={'github': 12345})

        repo_data = create_github_repo_response_data()

        self.http_client_side_effect = httpx.Response(200, json=repo_data)

        result = await self.client.get_repository(project)

        self.assertIsNotNone(result)
        self.assertEqual(result.name, 'test-repo')
        self.assertEqual(result.full_name, 'org/test-repo')
        self.assertEqual(result.default_branch, 'main')

    async def test_get_repository_no_identifier_or_link(self) -> None:
        """Test retrieval returns None with no identifier or link."""
        project = create_test_project()  # No identifiers or links

        result = await self.client.get_repository(project)

        self.assertIsNone(result)

    async def test_get_repository_not_found(self) -> None:
        """Test repository not found returns None."""
        project = create_test_project(identifiers={'github': 99999})

        self.http_client_side_effect = httpx.Response(404, json={})

        result = await self.client.get_repository(project)

        self.assertIsNone(result)

    async def test_get_repository_rate_limit(self) -> None:
        """Test rate limit error handling."""
        project = create_test_project(identifiers={'github': 12345})

        self.http_client_side_effect = httpx.Response(
            403, json={'message': 'API rate limit exceeded'}
        )

        with self.assertRaises(errors.GitHubRateLimitError):
            await self.client.get_repository(project)

    async def test_get_repository_forbidden(self) -> None:
        """Test forbidden access error handling."""
        project = create_test_project(identifiers={'github': 12345})

        self.http_client_side_effect = httpx.Response(
            403, json={'message': 'Access forbidden'}
        )

        with self.assertRaises(errors.GitHubNotFoundError):
            await self.client.get_repository(project)


class GitHubEnvironmentsTestCase(base.AsyncTestCase):
    """Test GitHub environment management."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-token', host='api.github.com'
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.client = github.GitHub(
            self.config, transport=self.http_client_transport
        )

    async def test_get_repository_environments(self) -> None:
        """Test listing repository environments."""
        env_data = {
            'total_count': 2,
            'environments': [
                {'name': 'production', 'id': 1},
                {'name': 'staging', 'id': 2},
            ],
        }

        self.http_client_side_effect = httpx.Response(200, json=env_data)

        result = await self.client.get_repository_environments('org', 'repo')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, 'production')
        self.assertEqual(result[1].name, 'staging')

    async def test_create_environment_success(self) -> None:
        """Test environment creation."""
        env_data = {'name': 'production', 'id': 1}

        self.http_client_side_effect = httpx.Response(200, json=env_data)

        result = await self.client.create_environment(
            'org', 'repo', 'production'
        )

        self.assertEqual(result.name, 'production')

    async def test_delete_environment_success(self) -> None:
        """Test environment deletion."""
        self.http_client_side_effect = httpx.Response(204, content=b'')

        result = await self.client.delete_environment('org', 'repo', 'staging')

        self.assertTrue(result)

    async def test_delete_environment_not_found(self) -> None:
        """Test deleting non-existent environment."""
        self.http_client_side_effect = httpx.Response(404, json={})

        # Should return True since it's already gone
        result = await self.client.delete_environment('org', 'repo', 'staging')

        self.assertTrue(result)


class GitHubPullRequestTestCase(base.AsyncTestCase):
    """Test GitHub pull request operations."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-token', host='api.github.com'
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.client = github.GitHub(
            self.config, transport=self.http_client_transport
        )

    async def test_create_pull_request_success(self) -> None:
        """Test pull request creation."""
        pr_data = create_github_pr_response_data()

        self.http_client_side_effect = httpx.Response(201, json=pr_data)

        context = create_test_workflow_context()
        result = await self.client.create_pull_request(
            context, 'Test PR', 'PR description', 'feature-branch', 'main'
        )

        self.assertEqual(result.number, 123)
        self.assertIn('/pull/123', result.html_url)

    async def test_get_pull_request(self) -> None:
        """Test retrieving pull request details."""
        pr_data = create_github_pr_response_data()

        self.http_client_side_effect = httpx.Response(200, json=pr_data)

        result = await self.client.get_pull_request('org', 'repo', 123)

        self.assertEqual(result.number, 123)
        self.assertEqual(result.state, 'open')

    async def test_list_pull_requests_success(self) -> None:
        """Test listing pull requests."""
        pr_list = [
            create_github_pr_response_data(number=1, state='open'),
            create_github_pr_response_data(
                number=2, state='closed', merged=True
            ),
        ]

        self.http_client_side_effect = httpx.Response(200, json=pr_list)

        result = await self.client.list_pull_requests('org', 'repo')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].number, 1)
        self.assertEqual(result[0].state, 'open')
        self.assertEqual(result[1].number, 2)
        self.assertEqual(result[1].state, 'closed')

    async def test_list_pull_requests_with_filters(self) -> None:
        """Test listing pull requests with state and head filters."""
        pr_list = [
            create_github_pr_response_data(
                number=123,
                state='open',
                head={'ref': 'imbi-automations/test-workflow', 'sha': 'abc'},
            )
        ]

        self.http_client_side_effect = httpx.Response(200, json=pr_list)

        result = await self.client.list_pull_requests(
            'org', 'repo', state='open', head='imbi-automations/test-workflow'
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].number, 123)
        self.assertEqual(
            result[0].head['ref'], 'imbi-automations/test-workflow'
        )

    async def test_list_pull_requests_empty(self) -> None:
        """Test listing pull requests with no results."""
        self.http_client_side_effect = httpx.Response(200, json=[])

        result = await self.client.list_pull_requests('org', 'repo')

        self.assertEqual(len(result), 0)

    async def test_list_pull_requests_not_found(self) -> None:
        """Test listing pull requests for non-existent repository."""
        self.http_client_side_effect = httpx.Response(404)

        result = await self.client.list_pull_requests('org', 'repo')

        self.assertEqual(len(result), 0)

    async def test_list_pull_requests_error(self) -> None:
        """Test listing pull requests with API error."""
        self.http_client_side_effect = httpx.Response(500)

        with self.assertRaises(httpx.HTTPStatusError):
            await self.client.list_pull_requests('org', 'repo')

    async def test_get_pr_check_runs(self) -> None:
        """Test retrieving PR check runs."""
        checks_data = {
            'total_count': 2,
            'check_runs': [
                {'name': 'test', 'conclusion': 'success'},
                {'name': 'lint', 'conclusion': 'success'},
            ],
        }

        self.http_client_side_effect = httpx.Response(200, json=checks_data)

        result = await self.client.get_pr_check_runs('org', 'repo', 'abc123')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'test')

    async def test_get_pr_reviews(self) -> None:
        """Test retrieving PR reviews."""
        reviews_data = [
            {'id': 1, 'state': 'APPROVED', 'user': {'login': 'reviewer1'}},
            {
                'id': 2,
                'state': 'CHANGES_REQUESTED',
                'user': {'login': 'reviewer2'},
            },
        ]

        self.http_client_side_effect = httpx.Response(200, json=reviews_data)

        result = await self.client.get_pr_reviews('org', 'repo', 123)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['state'], 'APPROVED')

    async def test_get_pr_comments(self) -> None:
        """Test retrieving PR comments."""
        comments_data = [
            {'id': 1, 'body': 'Looks good', 'user': {'login': 'reviewer1'}},
            {'id': 2, 'body': 'Please fix', 'user': {'login': 'reviewer2'}},
        ]

        self.http_client_side_effect = httpx.Response(200, json=comments_data)

        result = await self.client.get_pr_comments('org', 'repo', 123)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['body'], 'Looks good')


class GitHubFileOperationsTestCase(base.AsyncTestCase):
    """Test GitHub file and tree operations."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-token', host='api.github.com'
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.client = github.GitHub(
            self.config, transport=self.http_client_transport
        )

    async def test_get_file_contents_success(self) -> None:
        """Test retrieving file contents."""
        import base64

        content = base64.b64encode(b'Test content').decode('ascii')
        file_data = {
            'name': 'README.md',
            'path': 'README.md',
            'content': content,
            'encoding': 'base64',
            'type': 'file',
        }

        self.http_client_side_effect = httpx.Response(200, json=file_data)

        context = create_test_workflow_context()
        result = await self.client.get_file_contents(context, 'README.md')

        self.assertEqual(result, 'Test content')

    async def test_get_file_contents_not_found(self) -> None:
        """Test file not found returns None."""
        self.http_client_side_effect = httpx.Response(404, json={})

        context = create_test_workflow_context()
        result = await self.client.get_file_contents(context, 'nonexistent.md')

        self.assertIsNone(result)

    async def test_get_file_contents_large_file(self) -> None:
        """Test retrieving large file contents via download_url."""
        from unittest import mock

        # For files >1MB, GitHub doesn't include content field
        file_data = {
            'name': 'package-lock.json',
            'path': 'package-lock.json',
            'type': 'file',
            'size': 1258291,
            'download_url': 'https://raw.githubusercontent.com/test/test/main/package-lock.json',
        }

        large_content = '{"name": "large-project", "dependencies": {}}'

        # Create proper Response objects with requests
        metadata_req = httpx.Request(
            'GET',
            'https://api.github.com/repos/test/test/contents/package-lock.json',
        )
        metadata_resp = httpx.Response(
            200, json=file_data, request=metadata_req
        )

        download_req = httpx.Request('GET', file_data['download_url'])
        download_resp = httpx.Response(
            200, text=large_content, request=download_req
        )

        # Mock the second GET request for download
        with mock.patch.object(
            self.client, 'get', new_callable=mock.AsyncMock
        ) as mock_get:
            # First call returns metadata, second call returns content
            mock_get.side_effect = [metadata_resp, download_resp]

            context = create_test_workflow_context()
            result = await self.client.get_file_contents(
                context, 'package-lock.json'
            )

            self.assertEqual(result, large_content)
            self.assertEqual(mock_get.call_count, 2)

    async def test_get_repository_tree(self) -> None:
        """Test retrieving repository file tree."""
        tree_data = {
            'tree': [
                {'path': 'README.md', 'type': 'blob'},
                {'path': 'src/', 'type': 'tree'},
                {'path': 'src/main.py', 'type': 'blob'},
            ]
        }

        self.http_client_side_effect = httpx.Response(200, json=tree_data)

        context = create_test_workflow_context()
        result = await self.client.get_repository_tree(context, 'main')

        # Should only include blobs, not trees
        self.assertEqual(len(result), 2)
        self.assertIn('README.md', result)
        self.assertIn('src/main.py', result)


class GitHubWorkflowTestCase(base.AsyncTestCase):
    """Test GitHub workflow operations."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-token', host='api.github.com'
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.client = github.GitHub(
            self.config, transport=self.http_client_transport
        )

    async def test_get_repository_workflow_status(self) -> None:
        """Test retrieving workflow status."""
        workflow_run = create_github_workflow_run_data()
        workflows_data = {'workflow_runs': [workflow_run]}

        self.http_client_side_effect = httpx.Response(200, json=workflows_data)

        repository = create_test_repository(full_name='org/repo')
        result = await self.client.get_repository_workflow_status(repository)

        self.assertEqual(result, 'success')

    async def test_get_latest_workflow_run(self) -> None:
        """Test retrieving latest workflow run."""
        workflow_run = create_github_workflow_run_data()
        runs_data = {'workflow_runs': [workflow_run]}

        self.http_client_side_effect = httpx.Response(200, json=runs_data)

        result = await self.client.get_latest_workflow_run('org', 'repo')

        self.assertIsNotNone(result)
        self.assertEqual(result.id, 123)
        self.assertEqual(result.conclusion, 'success')


class GitHubRepositoryUpdateTestCase(base.AsyncTestCase):
    """Test GitHub repository update operations."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-token', host='api.github.com'
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.client = github.GitHub(
            self.config, transport=self.http_client_transport
        )

    async def test_update_repository_success(self) -> None:
        """Test repository update."""
        repo_data = create_github_repo_response_data(
            description='Updated description', private=False
        )

        self.http_client_side_effect = httpx.Response(200, json=repo_data)

        attributes = {'description': 'Updated description', 'private': False}

        result = await self.client.update_repository(
            'org', 'test-repo', attributes
        )

        self.assertEqual(result.description, 'Updated description')
        self.assertFalse(result.private)


class GitHubJobLogsTestCase(base.AsyncTestCase):
    """Test GitHub job logs retrieval."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-token', host='api.github.com'
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )
        self.client = github.GitHub(
            self.config, transport=self.http_client_transport
        )

    async def test_get_most_recent_job_logs(self) -> None:
        """Test retrieving job logs from most recent workflow run."""

        def mock_handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if '/actions/runs' in url and '/jobs' not in url:
                # Workflow runs list
                return httpx.Response(
                    200,
                    json={
                        'workflow_runs': [
                            {
                                'id': 123,
                                'status': 'completed',
                                'conclusion': 'success',
                            }
                        ]
                    },
                )
            elif '/actions/runs/123/jobs' in url:
                # Jobs list
                return httpx.Response(
                    200,
                    json={
                        'jobs': [
                            {'id': 1, 'name': 'test'},
                            {'id': 2, 'name': 'lint'},
                        ]
                    },
                )
            elif '/actions/jobs/1/logs' in url:
                return httpx.Response(200, text='Test job logs')
            elif '/actions/jobs/2/logs' in url:
                return httpx.Response(200, text='Lint job logs')
            return httpx.Response(404)

        self.http_client_transport = httpx.MockTransport(mock_handler)
        self.client = github.GitHub(
            self.config, transport=self.http_client_transport
        )

        repository = create_test_repository(full_name='org/repo')
        result = await self.client.get_most_recent_job_logs(repository, 'main')

        self.assertEqual(len(result), 2)
        self.assertIn('test', result)
        self.assertIn('lint', result)
        self.assertEqual(result['test'], 'Test job logs')
        self.assertEqual(result['lint'], 'Lint job logs')
