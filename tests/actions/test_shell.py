"""Comprehensive tests for the shell module."""

import asyncio
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

import jinja2

from imbi_automations import models, prompts
from imbi_automations.actions import shell
from tests import base


class ShellTestCase(base.AsyncTestCase):
    """Test cases for Shell class functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        self.repository_dir = self.working_directory / 'repository'
        self.repository_dir.mkdir()

        # Create mock workflow and context
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

        self.shell_executor = shell.ShellAction(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch('asyncio.create_subprocess_shell')
    async def test_execute_simple_command_success(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test successful execution of simple shell command."""
        # Mock successful process
        mock_process = mock.AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'success output', b'')
        mock_subprocess.return_value = mock_process

        action = models.WorkflowShellAction(
            name='test-echo', type='shell', command='echo "Hello World"'
        )

        await self.shell_executor.execute(action)

        # Verify subprocess was called correctly
        mock_subprocess.assert_called_once_with(
            'echo "Hello World"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.repository_dir,
        )

    @mock.patch('asyncio.create_subprocess_shell')
    async def test_execute_command_failure(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test shell command execution failure."""
        # Mock failed process
        mock_process = mock.AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b'', b'command failed')
        mock_subprocess.return_value = mock_process

        action = models.WorkflowShellAction(
            name='test-fail', type='shell', command='false'
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.shell_executor.execute(action)

        # Verify the chained exception is CalledProcessError
        self.assertIsInstance(
            exc_context.exception.__cause__, subprocess.CalledProcessError
        )
        self.assertEqual(exc_context.exception.__cause__.returncode, 1)

    @mock.patch('asyncio.create_subprocess_shell')
    async def test_execute_command_failure_ignored(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test shell command execution failure with ignore_errors=True."""
        # Mock failed process
        mock_process = mock.AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b'', b'command failed')
        mock_subprocess.return_value = mock_process

        action = models.WorkflowShellAction(
            name='test-fail-ignored',
            type='shell',
            command='false',
            ignore_errors=True,
        )

        # Should not raise exception when ignore_errors=True
        await self.shell_executor.execute(action)

    @mock.patch('asyncio.create_subprocess_shell')
    async def test_execute_command_not_found(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test shell command not found error."""
        mock_subprocess.side_effect = FileNotFoundError(
            'No such file or directory'
        )

        action = models.WorkflowShellAction(
            name='test-nonexistent',
            type='shell',
            command='nonexistent-command',
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.shell_executor.execute(action)

        self.assertIn(
            'Command not found: nonexistent-command',
            str(exc_context.exception),
        )
        # Verify the chained exception is FileNotFoundError
        self.assertIsInstance(
            exc_context.exception.__cause__, FileNotFoundError
        )

    @mock.patch('asyncio.create_subprocess_shell')
    async def test_execute_templated_command(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test execution of command with Jinja2 templating."""
        # Mock successful process
        mock_process = mock.AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'project output', b'')
        mock_subprocess.return_value = mock_process

        action = models.WorkflowShellAction(
            name='test-template',
            type='shell',
            command='echo "Project: {{ imbi_project.name }}"',
        )

        await self.shell_executor.execute(action)

        # Verify the command was templated and executed
        mock_subprocess.assert_called_once_with(
            'echo "Project: test-project"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.repository_dir,
        )

    @mock.patch('asyncio.create_subprocess_shell')
    async def test_execute_complex_templated_command(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test execution of complex command with multiple templates."""
        mock_process = mock.AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_subprocess.return_value = mock_process

        action = models.WorkflowShellAction(
            name='test-complex-template',
            type='shell',
            command=(
                'curl -H "Authorization: Bearer token" '
                '"https://api.example.com/projects/{{ imbi_project.id }}/'
                '{{ imbi_project.slug }}"'
            ),
        )

        await self.shell_executor.execute(action)

        # Verify the command was properly templated
        expected_command = (
            'curl -H "Authorization: Bearer token" '
            '"https://api.example.com/projects/123/test-project"'
        )
        mock_subprocess.assert_called_once_with(
            expected_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.repository_dir,
        )

    def test_has_template_syntax_detection(self) -> None:
        """Test template syntax detection."""
        # Test commands with templating
        templated_commands = [
            'echo "{{ variable }}"',
            'command {% if condition %}--flag{% endif %}',
            'cmd {# comment #} arg',
            'echo "{{ imbi_project.name }}" && echo "{{ workflow.name }}"',
        ]

        for command in templated_commands:
            with self.subTest(command=command):
                self.assertTrue(prompts.has_template_syntax(command))

        # Test commands without templating
        non_templated_commands = [
            'echo "hello world"',
            'ls -la',
            'python script.py',
            'make build',
        ]

        for command in non_templated_commands:
            with self.subTest(command=command):
                self.assertFalse(prompts.has_template_syntax(command))

    def test_render_command_no_templating(self) -> None:
        """Test command rendering when no templating is present."""
        command = 'echo "hello world"'
        action = models.WorkflowShellAction(
            name='test-action', command=command
        )
        result = self.shell_executor._render_command(action, self.context)
        self.assertEqual(result, command)

    def test_render_command_with_templating(self) -> None:
        """Test command rendering with Jinja2 templating."""
        command = 'echo "Project: {{ imbi_project.name }}"'
        action = models.WorkflowShellAction(
            name='test-action', command=command
        )
        result = self.shell_executor._render_command(action, self.context)
        self.assertEqual(result, 'echo "Project: test-project"')

    def test_render_command_template_error(self) -> None:
        """Test command rendering with template error."""
        command = 'echo "{{ nonexistent.field }}"'
        action = models.WorkflowShellAction(
            name='test-action', command=command
        )

        with self.assertRaises(jinja2.exceptions.UndefinedError):
            self.shell_executor._render_command(action, self.context)

    @mock.patch('asyncio.create_subprocess_shell')
    async def test_execute_working_directory_fallback(
        self, mock_subprocess: mock.AsyncMock
    ) -> None:
        """Test working directory fallback when repository doesn't exist."""
        # Remove repository directory
        self.repository_dir.rmdir()

        mock_process = mock.AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_subprocess.return_value = mock_process

        action = models.WorkflowShellAction(
            name='test-cwd-fallback', type='shell', command='pwd'
        )

        await self.shell_executor.execute(action)

        # Should use repository_dir (resolved from repository://)
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        self.assertEqual(call_args.args[0], 'pwd')
        self.assertEqual(call_args.kwargs['cwd'], self.repository_dir)

    # Removed test_execute_no_working_directory - context.working_directory
    # is always required in the refactored architecture since
    # action.working_directory defaults to repository:// which needs resolution

    async def test_invalid_command_syntax(self) -> None:
        """Test invalid shell command syntax handled by shell."""
        # Test command with invalid shell syntax - shell will return error
        action = models.WorkflowShellAction(
            name='test-invalid', type='shell', command='echo "unclosed quote'
        )

        # Shell processes the command and returns non-zero exit code
        with self.assertRaises(RuntimeError) as exc_context:
            await self.shell_executor.execute(action)

        # Verify the chained exception is CalledProcessError
        self.assertIsInstance(
            exc_context.exception.__cause__, subprocess.CalledProcessError
        )

    async def test_empty_command_after_rendering(self) -> None:
        """Test empty command after template rendering succeeds."""
        action = models.WorkflowShellAction(
            name='test-empty',
            type='shell',
            command='{% if false %}echo test{% endif %}',
        )

        # Empty command is valid in shell - it just does nothing
        await self.shell_executor.execute(action)


if __name__ == '__main__':
    unittest.main()
