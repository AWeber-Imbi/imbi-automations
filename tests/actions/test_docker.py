"""Comprehensive tests for the docker module."""

import pathlib
import tempfile
import unittest
from unittest import mock

from imbi_automations import models
from imbi_automations.actions import docker
from tests import base


class DockerTestCase(base.AsyncTestCase):
    """Test cases for Docker functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        self.extracted_dir = self.working_directory / 'extracted'
        self.extracted_dir.mkdir()

        # Create workflow context
        self.workflow = models.Workflow(
            path=pathlib.Path('/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

        self.context = models.WorkflowContext(
            workflow=self.workflow,
            imbi_project=models.ImbiProject(
                id=123,
                dependencies=None,
                description='Test project',
                environments=None,
                facts=None,
                identifiers=None,
                links=None,
                name='test-project',
                namespace='test-namespace',
                namespace_slug='test-namespace',
                project_score=None,
                project_type='API',
                project_type_slug='api',
                slug='test-project',
                urls=None,
                imbi_url='https://imbi.example.com/projects/123',
            ),
            working_directory=self.working_directory,
        )

        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-key'  # noqa: S106
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.docker_executor = docker.DockerActions(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_extract_success(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test successful docker extract operation."""
        # Mock successful docker commands
        mock_run_docker.side_effect = [
            (0, '', ''),  # docker pull
            (0, 'container_id', ''),  # docker create
            (0, '', ''),  # docker cp
            (0, '', ''),  # docker rm (cleanup)
        ]

        action = models.WorkflowDockerAction(
            name='extract-config',
            type='docker',
            command='extract',
            image='ubuntu',
            tag='20.04',
            source=pathlib.Path('/etc/passwd'),
            destination=pathlib.Path('passwd'),
        )

        await self.docker_executor.execute(action)

        # Verify docker commands were called correctly
        self.assertEqual(mock_run_docker.call_count, 4)

        # Check docker pull command
        pull_call = mock_run_docker.call_args_list[0]
        self.assertEqual(pull_call[0][0], ['docker', 'pull', 'ubuntu:20.04'])

        # Check docker create command
        create_call = mock_run_docker.call_args_list[1]
        self.assertEqual(
            create_call[0][0],
            [
                'docker',
                'create',
                '--name',
                f'imbi-extract-{id(action)}',
                'ubuntu:20.04',
            ],
        )

        # Check docker cp command
        cp_call = mock_run_docker.call_args_list[2]
        expected_cp_cmd = [
            'docker',
            'cp',
            f'imbi-extract-{id(action)}:/etc/passwd',
            str(self.working_directory / 'extracted/passwd'),
        ]
        self.assertEqual(cp_call[0][0], expected_cp_cmd)

        # Check docker rm command (cleanup)
        rm_call = mock_run_docker.call_args_list[3]
        self.assertEqual(
            rm_call[0][0], ['docker', 'rm', f'imbi-extract-{id(action)}']
        )

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_extract_no_tag(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker extract without tag defaults to :latest and pulls."""
        mock_run_docker.side_effect = [
            (0, '', ''),  # docker pull
            (0, 'container_id', ''),  # docker create
            (0, '', ''),  # docker cp
            (0, '', ''),  # docker rm
        ]

        action = models.WorkflowDockerAction(
            name='extract-no-tag',
            type='docker',
            command='extract',
            image='nginx',
            # No tag specified (defaults to latest)
            source=pathlib.Path('/etc/nginx/nginx.conf'),
            destination=pathlib.Path('nginx.conf'),
        )

        await self.docker_executor.execute(action)

        # Verify docker pull and create use nginx:latest
        pull_call = mock_run_docker.call_args_list[0]
        self.assertEqual(pull_call[0][0], ['docker', 'pull', 'nginx:latest'])

        create_call = mock_run_docker.call_args_list[1]
        self.assertEqual(
            create_call[0][0],
            [
                'docker',
                'create',
                '--name',
                f'imbi-extract-{id(action)}',
                'nginx:latest',
            ],
        )

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_extract_create_failure(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker extract with container creation failure."""
        # Mock failed docker create
        mock_run_docker.side_effect = [
            (0, '', ''),  # docker pull
            RuntimeError('Docker create failed'),  # docker create
            (0, '', ''),  # docker rm (cleanup)
        ]

        action = models.WorkflowDockerAction(
            name='extract-fail-create',
            type='docker',
            command='extract',
            image='nonexistent',
            source=pathlib.Path('/file'),
            destination=pathlib.Path('file'),
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.docker_executor.execute(action)

        self.assertIn('Docker create failed', str(exc_context.exception))

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_extract_copy_failure(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker extract with copy failure."""
        # Mock successful pull and create, failed copy, successful cleanup
        mock_run_docker.side_effect = [
            (0, '', ''),  # docker pull
            (0, 'container_id', ''),  # docker create
            RuntimeError('Docker cp failed'),  # docker cp
            (0, '', ''),  # docker rm (cleanup)
        ]

        action = models.WorkflowDockerAction(
            name='extract-fail-copy',
            type='docker',
            command='extract',
            image='ubuntu',
            source=pathlib.Path('/nonexistent'),
            destination=pathlib.Path('file'),
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.docker_executor.execute(action)

        self.assertIn('Docker cp failed', str(exc_context.exception))

        # Verify cleanup was still attempted (including initial pull)
        self.assertEqual(mock_run_docker.call_count, 4)

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_extract_cleanup_failure(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker extract with cleanup failure."""
        # Mock successful pull, create and copy, failed cleanup
        mock_run_docker.side_effect = [
            (0, '', ''),  # docker pull
            (0, 'container_id', ''),  # docker create
            (0, '', ''),  # docker cp
            RuntimeError('Docker rm failed'),  # docker rm (cleanup)
        ]

        action = models.WorkflowDockerAction(
            name='extract-fail-cleanup',
            type='docker',
            command='extract',
            image='ubuntu',
            source=pathlib.Path('/etc/passwd'),
            destination=pathlib.Path('passwd'),
        )

        # Should not raise exception - cleanup failure shouldn't fail operation
        await self.docker_executor.execute(action)

    @mock.patch('asyncio.create_subprocess_exec')
    async def test_run_docker_command_success(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test _run_docker_command with successful execution."""
        mock_process = mock.AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'success output', b'')
        mock_subprocess.return_value = mock_process

        result = await self.docker_executor._run_docker_command(
            ['docker', 'version']
        )

        self.assertEqual(result, (0, 'success output', ''))

    @mock.patch('asyncio.create_subprocess_exec')
    async def test_run_docker_command_failure(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test _run_docker_command with command failure."""
        mock_process = mock.AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b'', b'error output')
        mock_subprocess.return_value = mock_process

        with self.assertRaises(RuntimeError) as exc_context:
            await self.docker_executor._run_docker_command(
                ['docker', 'invalid-command']
            )

        self.assertIn('Docker command failed', str(exc_context.exception))
        self.assertIn('error output', str(exc_context.exception))

    @mock.patch('asyncio.create_subprocess_exec')
    async def test_run_docker_command_failure_not_checked(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test _run_docker_command with failure but check_exit_code=False."""
        mock_process = mock.AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b'', b'error output')
        mock_subprocess.return_value = mock_process

        result = await self.docker_executor._run_docker_command(
            ['docker', 'invalid-command'], check_exit_code=False
        )

        # Should return the result without raising
        self.assertEqual(result, (1, '', 'error output'))

    @mock.patch('asyncio.create_subprocess_exec')
    async def test_run_docker_command_not_found(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test _run_docker_command when docker is not installed."""
        mock_subprocess.side_effect = FileNotFoundError(
            'docker: command not found'
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.docker_executor._run_docker_command(
                ['docker', 'version']
            )

        self.assertIn('Docker command not found', str(exc_context.exception))
        self.assertIn('is Docker installed', str(exc_context.exception))

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_pull_success(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test successful docker pull operation."""
        mock_run_docker.return_value = (0, '', '')

        action = models.WorkflowDockerAction(
            name='pull-image',
            type='docker',
            command='pull',
            image='nginx',
            tag='1.25',
        )

        await self.docker_executor.execute(action)

        mock_run_docker.assert_called_once_with(
            ['docker', 'pull', 'nginx:1.25'], action=action
        )

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_pull_default_tag(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker pull with default tag."""
        mock_run_docker.return_value = (0, '', '')

        action = models.WorkflowDockerAction(
            name='pull-image', type='docker', command='pull', image='ubuntu'
        )

        await self.docker_executor.execute(action)

        mock_run_docker.assert_called_once_with(
            ['docker', 'pull', 'ubuntu:latest'], action=action
        )

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_pull_with_template(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker pull with templated image name."""
        mock_run_docker.return_value = (0, '', '')

        action = models.WorkflowDockerAction(
            name='pull-image',
            type='docker',
            command='pull',
            image='{{ imbi_project.slug }}',
            tag='v1.0',
        )

        await self.docker_executor.execute(action)

        mock_run_docker.assert_called_once_with(
            ['docker', 'pull', 'test-project:v1.0'], action=action
        )

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_pull_failure(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker pull failure."""
        mock_run_docker.side_effect = RuntimeError(
            'Pull failed: access denied'
        )

        action = models.WorkflowDockerAction(
            name='pull-image',
            type='docker',
            command='pull',
            image='private/image',
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.docker_executor.execute(action)

        self.assertIn('Pull failed', str(exc_context.exception))

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_push_success(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test successful docker push operation."""
        mock_run_docker.return_value = (0, '', '')

        action = models.WorkflowDockerAction(
            name='push-image',
            type='docker',
            command='push',
            image='myregistry.com/myimage',
            tag='v2.0',
        )

        await self.docker_executor.execute(action)

        mock_run_docker.assert_called_once_with(
            ['docker', 'push', 'myregistry.com/myimage:v2.0'], action=action
        )

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_push_with_template(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker push with templated image name."""
        mock_run_docker.return_value = (0, '', '')

        action = models.WorkflowDockerAction(
            name='push-image',
            type='docker',
            command='push',
            image='registry.example.com/{{ imbi_project.namespace_slug }}/app',
            tag='latest',
        )

        await self.docker_executor.execute(action)

        mock_run_docker.assert_called_once_with(
            [
                'docker',
                'push',
                'registry.example.com/test-namespace/app:latest',
            ],
            action=action,
        )

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_push_failure(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker push failure."""
        mock_run_docker.side_effect = RuntimeError(
            'Push failed: authentication required'
        )

        action = models.WorkflowDockerAction(
            name='push-image',
            type='docker',
            command='push',
            image='myregistry.com/myimage',
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.docker_executor.execute(action)

        self.assertIn('Push failed', str(exc_context.exception))

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_build_success(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test successful docker build operation."""
        mock_run_docker.return_value = (0, '', '')

        # Create a directory for build context
        build_dir = self.working_directory / 'repository'
        build_dir.mkdir(parents=True)
        (build_dir / 'Dockerfile').write_text('FROM alpine\n')

        action = models.WorkflowDockerAction(
            name='build-image',
            type='docker',
            command='build',
            image='myapp',
            tag='v1.0',
            path=models.ResourceUrl('repository:///'),
        )

        await self.docker_executor.execute(action)

        mock_run_docker.assert_called_once_with(
            ['docker', 'build', '-t', 'myapp:v1.0', str(build_dir)],
            action=action,
        )

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_build_with_template(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker build with templated image name."""
        mock_run_docker.return_value = (0, '', '')

        # Create build context directory
        build_dir = self.working_directory / 'repository'
        build_dir.mkdir(parents=True)
        (build_dir / 'Dockerfile').write_text('FROM python:3.12\n')

        action = models.WorkflowDockerAction(
            name='build-image',
            type='docker',
            command='build',
            image='{{ imbi_project.slug }}',
            tag='latest',
            path=models.ResourceUrl('repository:///'),
        )

        await self.docker_executor.execute(action)

        mock_run_docker.assert_called_once_with(
            ['docker', 'build', '-t', 'test-project:latest', str(build_dir)],
            action=action,
        )

    async def test_execute_build_path_not_exists(self) -> None:
        """Test docker build with non-existent path."""
        action = models.WorkflowDockerAction(
            name='build-image',
            type='docker',
            command='build',
            image='myapp',
            path=models.ResourceUrl('repository:///nonexistent'),
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.docker_executor.execute(action)

        self.assertIn('does not exist', str(exc_context.exception))

    @mock.patch(
        'imbi_automations.actions.docker.DockerActions._run_docker_command'
    )
    async def test_execute_build_failure(
        self, mock_run_docker: mock.AsyncMock
    ) -> None:
        """Test docker build failure."""
        mock_run_docker.side_effect = RuntimeError(
            'Build failed: syntax error'
        )

        # Create build context directory
        build_dir = self.working_directory / 'repository'
        build_dir.mkdir(parents=True)
        (build_dir / 'Dockerfile').write_text('INVALID\n')

        action = models.WorkflowDockerAction(
            name='build-image',
            type='docker',
            command='build',
            image='myapp',
            path=models.ResourceUrl('repository:///'),
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.docker_executor.execute(action)

        self.assertIn('Build failed', str(exc_context.exception))


if __name__ == '__main__':
    unittest.main()
