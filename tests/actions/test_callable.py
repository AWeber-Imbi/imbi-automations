"""Comprehensive tests for the callablea module."""

import asyncio
import pathlib
import tempfile
import typing
import unittest
from unittest import mock

from imbi_automations import models
from imbi_automations.actions import callablea
from tests import base


# Test fixtures - sample callables
def sync_function(arg1: int, arg2: str, keyword_arg: str = 'default') -> str:
    """Sample synchronous function for testing."""
    return f'{arg1}-{arg2}-{keyword_arg}'


async def async_function(
    arg1: int, arg2: str, keyword_arg: str = 'default'
) -> str:
    """Sample asynchronous function for testing."""
    await asyncio.sleep(0.001)  # Simulate async work
    return f'{arg1}-{arg2}-{keyword_arg}'


def failing_function() -> None:
    """Function that always raises an exception."""
    raise ValueError('Intentional test failure')


async def async_failing_function() -> None:
    """Async function that always raises an exception."""
    await asyncio.sleep(0.001)
    raise ValueError('Intentional async test failure')


def type_sensitive_function(
    int_arg: int, str_arg: str, bool_arg: bool, float_arg: float
) -> dict:
    """Function that requires specific types."""
    return {
        'int': (int_arg, type(int_arg).__name__),
        'str': (str_arg, type(str_arg).__name__),
        'bool': (bool_arg, type(bool_arg).__name__),
        'float': (float_arg, type(float_arg).__name__),
    }


class CallableActionTestCase(base.AsyncTestCase):
    """Test cases for CallableAction functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

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

        self.callable_executor = callablea.CallableAction(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_execute_sync_callable_no_args(self) -> None:
        """Test execution of synchronous callable with no arguments."""
        mock_callable = mock.Mock(return_value='success')

        action = models.WorkflowCallableAction(
            name='test-sync-no-args', type='callable', callable=mock_callable
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_called_once_with()

    async def test_execute_sync_callable_with_args(self) -> None:
        """Test execution of synchronous callable with positional args."""
        mock_callable = mock.Mock(return_value='result')

        action = models.WorkflowCallableAction(
            name='test-sync-args',
            type='callable',
            callable=mock_callable,
            args=[42, 'hello', True],
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_called_once_with(42, 'hello', True)

    async def test_execute_sync_callable_with_kwargs(self) -> None:
        """Test execution of synchronous callable with keyword arguments."""
        mock_callable = mock.Mock(return_value='result')

        action = models.WorkflowCallableAction(
            name='test-sync-kwargs',
            type='callable',
            callable=mock_callable,
            kwargs={'name': 'test', 'count': 5, 'enabled': True},
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_called_once_with(
            name='test', count=5, enabled=True
        )

    async def test_execute_sync_callable_with_args_and_kwargs(self) -> None:
        """Test execution of synchronous callable with both args and kwargs."""
        mock_callable = mock.Mock(return_value='result')

        action = models.WorkflowCallableAction(
            name='test-sync-mixed',
            type='callable',
            callable=mock_callable,
            args=[1, 2, 3],
            kwargs={'multiplier': 10, 'offset': 5},
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_called_once_with(1, 2, 3, multiplier=10, offset=5)

    async def test_execute_async_callable_no_args(self) -> None:
        """Test execution of asynchronous callable with no arguments."""
        mock_callable = mock.AsyncMock(return_value='async_success')

        action = models.WorkflowCallableAction(
            name='test-async-no-args', type='callable', callable=mock_callable
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_awaited_once_with()

    async def test_execute_async_callable_with_args(self) -> None:
        """Test execution of asynchronous callable with arguments."""
        mock_callable = mock.AsyncMock(return_value='async_result')

        action = models.WorkflowCallableAction(
            name='test-async-args',
            type='callable',
            callable=mock_callable,
            args=[99, 'async', False],
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_awaited_once_with(99, 'async', False)

    async def test_execute_templated_args(self) -> None:
        """Test execution with Jinja2-templated positional arguments."""
        mock_callable = mock.Mock(return_value='success')

        action = models.WorkflowCallableAction(
            name='test-templated-args',
            type='callable',
            callable=mock_callable,
            args=[
                '{{ imbi_project.name }}',
                '{{ imbi_project.id }}',
                '{{ workflow.slug }}',
            ],
        )

        await self.callable_executor.execute(action)

        # Template rendering converts to strings
        mock_callable.assert_called_once_with('test-project', '123', 'test')

    async def test_execute_templated_kwargs(self) -> None:
        """Test execution with Jinja2-templated keyword arguments."""
        mock_callable = mock.Mock(return_value='success')

        action = models.WorkflowCallableAction(
            name='test-templated-kwargs',
            type='callable',
            callable=mock_callable,
            kwargs={
                'project_name': '{{ imbi_project.name }}',
                'project_slug': '{{ imbi_project.slug }}',
                'project_type': '{{ imbi_project.project_type }}',
            },
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_called_once_with(
            project_name='test-project',
            project_slug='test-project',
            project_type='API',
        )

    async def test_execute_mixed_templated_and_literal_args(self) -> None:
        """Test execution with mix of templated and literal arguments."""
        mock_callable = mock.Mock(return_value='success')

        action = models.WorkflowCallableAction(
            name='test-mixed',
            type='callable',
            callable=mock_callable,
            args=[
                42,  # Literal int
                '{{ imbi_project.name }}',  # Templated string
                True,  # Literal bool
                'literal-string',  # Literal string
            ],
            kwargs={
                'count': 10,  # Literal int
                'name': '{{ imbi_project.slug }}',  # Templated
                'enabled': False,  # Literal bool
            },
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_called_once_with(
            42,
            'test-project',
            True,
            'literal-string',
            count=10,
            name='test-project',
            enabled=False,
        )

    async def test_execute_preserves_arg_order(self) -> None:
        """Test that positional argument order is preserved."""
        result_list: list = []

        def order_sensitive_function(*args: typing.Any) -> None:
            result_list.extend(args)

        action = models.WorkflowCallableAction(
            name='test-order',
            type='callable',
            callable=order_sensitive_function,
            args=['first', 'second', 'third', 'fourth', 'fifth'],
        )

        await self.callable_executor.execute(action)

        # Verify order is preserved
        self.assertEqual(
            result_list, ['first', 'second', 'third', 'fourth', 'fifth']
        )

    async def test_execute_sync_callable_raises_exception(self) -> None:
        """Test exception handling for synchronous callable failures."""
        action = models.WorkflowCallableAction(
            name='test-sync-fail', type='callable', callable=failing_function
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.callable_executor.execute(action)

        # Verify the RuntimeError wraps the original exception
        self.assertEqual(
            str(exc_context.exception), 'Intentional test failure'
        )
        self.assertIsInstance(exc_context.exception.__cause__, ValueError)

    async def test_execute_async_callable_raises_exception(self) -> None:
        """Test exception handling for asynchronous callable failures."""
        action = models.WorkflowCallableAction(
            name='test-async-fail',
            type='callable',
            callable=async_failing_function,
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.callable_executor.execute(action)

        # Verify the RuntimeError wraps the original exception
        self.assertEqual(
            str(exc_context.exception), 'Intentional async test failure'
        )
        self.assertIsInstance(exc_context.exception.__cause__, ValueError)

    async def test_execute_with_non_string_types(self) -> None:
        """Test that non-string types are not template-rendered."""
        mock_callable = mock.Mock(return_value='success')

        action = models.WorkflowCallableAction(
            name='test-types',
            type='callable',
            callable=mock_callable,
            args=[
                123,  # int
                45.67,  # float
                True,  # bool
                None,  # None
                ['list', 'of', 'items'],  # list
                {'key': 'value'},  # dict
            ],
        )

        await self.callable_executor.execute(action)

        # Verify non-string types are passed as-is
        mock_callable.assert_called_once_with(
            123, 45.67, True, None, ['list', 'of', 'items'], {'key': 'value'}
        )

    async def test_execute_empty_args_and_kwargs(self) -> None:
        """Test execution with empty args and kwargs (defaults)."""
        mock_callable = mock.Mock(return_value='success')

        action = models.WorkflowCallableAction(
            name='test-empty',
            type='callable',
            callable=mock_callable,
            args=[],
            kwargs={},
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_called_once_with()

    async def test_execute_string_without_template_syntax(self) -> None:
        """Test that strings without template syntax are not rendered."""
        mock_callable = mock.Mock(return_value='success')

        action = models.WorkflowCallableAction(
            name='test-no-template',
            type='callable',
            callable=mock_callable,
            args=['plain string', 'another plain string'],
            kwargs={
                'key1': 'value without templates',
                'key2': 'just a normal string',
            },
        )

        await self.callable_executor.execute(action)

        # Strings without template syntax should pass through unchanged
        mock_callable.assert_called_once_with(
            'plain string',
            'another plain string',
            key1='value without templates',
            key2='just a normal string',
        )

    async def test_execute_callable_with_complex_template_expression(
        self,
    ) -> None:
        """Test execution with complex Jinja2 expressions."""
        mock_callable = mock.Mock(return_value='success')

        action = models.WorkflowCallableAction(
            name='test-complex-template',
            type='callable',
            callable=mock_callable,
            args=[
                '{{ imbi_project.namespace }}/{{ imbi_project.name }}',
                '{{ imbi_project.id | int }}',
                (
                    '{% if imbi_project.id > 100 %}'
                    'large{% else %}small{% endif %}'
                ),
            ],
        )

        await self.callable_executor.execute(action)

        mock_callable.assert_called_once_with(
            'test-namespace/test-project', '123', 'large'
        )

    async def test_execute_logs_debug_message(self) -> None:
        """Test that execution logs debug message with callable and args."""
        mock_callable = mock.Mock(return_value='success')

        action = models.WorkflowCallableAction(
            name='test-logging',
            type='callable',
            callable=mock_callable,
            args=[1, 2],
            kwargs={'key': 'value'},
        )

        with mock.patch.object(
            self.callable_executor, 'logger'
        ) as mock_logger:
            await self.callable_executor.execute(action)

            # Verify debug logging occurred
            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args[0]
            self.assertIn('executing callable', call_args[0])

    async def test_execute_logs_exception_on_failure(self) -> None:
        """Test that exceptions are logged before re-raising."""
        action = models.WorkflowCallableAction(
            name='test-logging-exception',
            type='callable',
            callable=failing_function,
        )

        with mock.patch.object(
            self.callable_executor, 'logger'
        ) as mock_logger:
            with self.assertRaises(RuntimeError):
                await self.callable_executor.execute(action)

            # Verify exception logging occurred
            mock_logger.exception.assert_called_once()
            call_args = mock_logger.exception.call_args[0]
            self.assertIn('Error invoking callable', call_args[0])

    async def test_callable_return_value_not_captured(self) -> None:
        """Test that return values from callables are not captured.

        This is by design - CallableAction executes for side effects,
        not return values.
        """

        def callable_with_return() -> str:
            return 'important_result'

        action = models.WorkflowCallableAction(
            name='test-return', type='callable', callable=callable_with_return
        )

        # Execute and verify it doesn't raise, but return value is lost
        result = await self.callable_executor.execute(action)

        # Execute returns None by design
        self.assertIsNone(result)

    async def test_execute_real_async_function(self) -> None:
        """Test execution with real async function (not mocked)."""
        action = models.WorkflowCallableAction(
            name='test-real-async',
            type='callable',
            callable=async_function,
            args=[42, 'test'],
            kwargs={'keyword_arg': 'custom'},
        )

        # Should complete without raising
        await self.callable_executor.execute(action)

    async def test_execute_real_sync_function(self) -> None:
        """Test execution with real sync function (not mocked)."""
        action = models.WorkflowCallableAction(
            name='test-real-sync',
            type='callable',
            callable=sync_function,
            args=[99, 'hello'],
            kwargs={'keyword_arg': 'world'},
        )

        # Should complete without raising
        await self.callable_executor.execute(action)

    async def test_asyncio_detection_for_sync_function(self) -> None:
        """Test that sync functions are correctly identified."""
        # Test with real sync function
        self.assertFalse(asyncio.iscoroutinefunction(sync_function))

        # Create action and execute
        action = models.WorkflowCallableAction(
            name='test-sync-detection',
            type='callable',
            callable=sync_function,
            args=[1, 'test'],
        )

        # Should execute without trying to await
        await self.callable_executor.execute(action)

    async def test_asyncio_detection_for_async_function(self) -> None:
        """Test that async functions are correctly identified."""
        # Test with real async function
        self.assertTrue(asyncio.iscoroutinefunction(async_function))

        # Create action and execute
        action = models.WorkflowCallableAction(
            name='test-async-detection',
            type='callable',
            callable=async_function,
            args=[1, 'test'],
        )

        # Should await properly
        await self.callable_executor.execute(action)

    async def test_execute_with_resourceurl_args(self) -> None:
        """Test execution with ResourceUrl arguments that get resolved."""
        mock_callable = mock.Mock(return_value='success')

        # Create repository directory
        repo_dir = self.working_directory / 'repository'
        repo_dir.mkdir()
        test_file = repo_dir / 'config.yaml'
        test_file.write_text('config: test')

        action = models.WorkflowCallableAction(
            name='test-resourceurl',
            type='callable',
            callable=mock_callable,
            args=[
                models.ResourceUrl('repository:///config.yaml'),
                'literal-string',
            ],
        )

        await self.callable_executor.execute(action)

        # Verify ResourceUrl was resolved to pathlib.Path
        call_args = mock_callable.call_args[0]
        self.assertIsInstance(call_args[0], pathlib.Path)
        self.assertEqual(call_args[0], repo_dir / 'config.yaml')
        self.assertEqual(call_args[1], 'literal-string')

    async def test_execute_with_resourceurl_kwargs(self) -> None:
        """Test execution with ResourceUrl in keyword arguments."""
        mock_callable = mock.Mock(return_value='success')

        # Create extracted directory for testing
        extracted_dir = self.working_directory / 'extracted'
        extracted_dir.mkdir(exist_ok=True)
        extracted_file = extracted_dir / 'data.csv'
        extracted_file.write_text('col1,col2\nval1,val2')

        action = models.WorkflowCallableAction(
            name='test-resourceurl-kwargs',
            type='callable',
            callable=mock_callable,
            kwargs={
                'data_path': models.ResourceUrl('extracted:///data.csv'),
                'count': 42,
            },
        )

        await self.callable_executor.execute(action)

        # Verify ResourceUrl was resolved in kwargs
        call_kwargs = mock_callable.call_args[1]
        self.assertIsInstance(call_kwargs['data_path'], pathlib.Path)
        self.assertEqual(call_kwargs['data_path'], extracted_file)
        self.assertEqual(call_kwargs['count'], 42)

    async def test_execute_with_mixed_resourceurl_and_templates(self) -> None:
        """Test execution with both ResourceUrl and template strings."""
        mock_callable = mock.Mock(return_value='success')

        # Create test files
        repo_dir = self.working_directory / 'repository'
        repo_dir.mkdir(exist_ok=True)
        (repo_dir / 'data.json').write_text('{}')

        action = models.WorkflowCallableAction(
            name='test-mixed',
            type='callable',
            callable=mock_callable,
            args=[
                models.ResourceUrl('repository:///data.json'),
                '{{ imbi_project.name }}',  # Template
                42,  # Literal
            ],
        )

        await self.callable_executor.execute(action)

        call_args = mock_callable.call_args[0]
        # ResourceUrl resolved to Path
        self.assertIsInstance(call_args[0], pathlib.Path)
        # Template rendered to string
        self.assertEqual(call_args[1], 'test-project')
        # Literal preserved
        self.assertEqual(call_args[2], 42)

    async def test_execute_with_multiple_resourceurl_schemes(self) -> None:
        """Test execution with different ResourceUrl schemes."""
        mock_callable = mock.Mock(return_value='success')

        # Create directories for different schemes
        (self.working_directory / 'repository').mkdir(exist_ok=True)
        (self.working_directory / 'extracted').mkdir(exist_ok=True)

        (self.working_directory / 'repository' / 'input.txt').write_text(
            'input'
        )
        (self.working_directory / 'extracted' / 'output.txt').write_text(
            'output'
        )

        action = models.WorkflowCallableAction(
            name='test-multiple-schemes',
            type='callable',
            callable=mock_callable,
            args=[
                models.ResourceUrl('repository:///input.txt'),
                models.ResourceUrl('extracted:///output.txt'),
            ],
        )

        await self.callable_executor.execute(action)

        call_args = mock_callable.call_args[0]
        self.assertEqual(
            call_args[0], self.working_directory / 'repository' / 'input.txt'
        )
        self.assertEqual(
            call_args[1], self.working_directory / 'extracted' / 'output.txt'
        )


if __name__ == '__main__':
    unittest.main()
