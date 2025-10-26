"""Comprehensive tests for the claude module."""

import json
import pathlib
import tempfile
import unittest
from unittest import mock

import claude_agent_sdk
import pydantic

from imbi_automations import claude, models
from tests import base


def _test_response_validator(message: str) -> str:
    """Test helper function that validates agent responses.

    Validates against ClaudeAgentPlanningResult, ClaudeAgentTaskResult,
    or ClaudeAgentValidationResult schemas.
    """
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return 'Payload not validate as JSON'

    # Try ClaudeAgentPlanningResult first (planning agents)
    try:
        models.ClaudeAgentPlanningResult.model_validate(payload)
        return 'Response is valid'
    except pydantic.ValidationError:
        pass

    # Try ClaudeAgentTaskResult (task agents)
    try:
        models.ClaudeAgentTaskResult.model_validate(payload)
        return 'Response is valid'
    except pydantic.ValidationError:
        pass

    # Try ClaudeAgentValidationResult (validation agents)
    try:
        models.ClaudeAgentValidationResult.model_validate(payload)
        return 'Response is valid'
    except pydantic.ValidationError as exc:
        return str(exc)

    return 'Response is valid'


def _create_mock_result_message_usage() -> dict:
    """Create mock usage dict with all required fields for tracker."""
    return {
        'cache_creation': {},
        'cache_creation_input_tokens': 0,
        'cache_read_input_tokens': 0,
        'input_tokens': 100,
        'output_tokens': 50,
        'service_tier': 'default',
        'server_tool_use': {},
    }


class ResponseValidatorTestCase(unittest.TestCase):
    """Test cases for the response_validator function logic."""

    def test_response_validator_valid_json_task_result(self) -> None:
        """Test response_validator with valid TaskResult JSON."""
        valid_payload = {'message': 'Test successful'}
        json_message = json.dumps(valid_payload)

        result = _test_response_validator(json_message)

        self.assertEqual(result, 'Response is valid')

    def test_response_validator_valid_json_validation_result(self) -> None:
        """Test response_validator with valid ValidationResult JSON."""
        valid_payload = {'validated': True, 'errors': []}
        json_message = json.dumps(valid_payload)

        result = _test_response_validator(json_message)

        self.assertEqual(result, 'Response is valid')

    def test_response_validator_invalid_json(self) -> None:
        """Test response_validator with invalid JSON."""
        invalid_json = '{"invalid": json syntax'

        result = _test_response_validator(invalid_json)

        self.assertEqual(result, 'Payload not validate as JSON')

    def test_response_validator_invalid_schema(self) -> None:
        """Test response_validator with invalid AgentRun schema."""
        invalid_payload = {'wrong_field': 'invalid', 'missing_result': True}
        json_message = json.dumps(invalid_payload)

        result = _test_response_validator(json_message)

        self.assertIn('validation error', result)

    def test_response_validator_planning_agent_response(self) -> None:
        """Test response_validator accepts planning agent responses."""
        planning_payload = {
            'plan': ['Task 1', 'Task 2', 'Task 3'],
            'analysis': 'Detailed analysis',
        }
        json_message = json.dumps(planning_payload)

        result = _test_response_validator(json_message)

        self.assertEqual(result, 'Response is valid')

    def test_response_validator_planning_agent_structured_analysis(
        self,
    ) -> None:
        """Test response_validator with structured analysis."""
        planning_payload = {
            'plan': ['Task 1', 'Task 2'],
            'analysis': json.dumps(
                {
                    'original_base_image': 'python:3.9-slim',
                    'target_base_image': 'python:3.12-slim',
                    'apk_packages': ['musl-dev', 'gcc'],
                }
            ),
        }
        json_message = json.dumps(planning_payload)

        result = _test_response_validator(json_message)

        self.assertEqual(result, 'Response is valid')


class AgentPlanTestCase(unittest.TestCase):
    """Test cases for ClaudeAgentPlanningResult model."""

    def test_agent_plan_string_analysis(self) -> None:
        """Test ClaudeAgentPlanningResult with string analysis."""
        plan = models.ClaudeAgentPlanningResult(
            plan=['Task 1', 'Task 2'], analysis='Simple string analysis'
        )
        self.assertEqual(plan.analysis, 'Simple string analysis')

    def test_agent_plan_dict_analysis(self) -> None:
        """Test ClaudeAgentPlanningResult with dict analysis as JSON."""
        analysis_dict = {
            'base_image': 'python:3.9',
            'packages': ['gcc', 'musl-dev'],
        }
        plan = models.ClaudeAgentPlanningResult(
            plan=['Task 1'],
            analysis=json.dumps(analysis_dict),  # Must be JSON string
        )
        # Should be a string
        self.assertIsInstance(plan.analysis, str)
        # Should be valid JSON
        parsed = json.loads(plan.analysis)
        self.assertEqual(parsed['base_image'], 'python:3.9')

    def test_agent_plan_empty_analysis(self) -> None:
        """Test ClaudeAgentPlanningResult with empty string analysis."""
        plan = models.ClaudeAgentPlanningResult(plan=['Task 1'], analysis='')
        self.assertEqual(plan.analysis, '')

    def test_agent_plan_multiple_tasks(self) -> None:
        """Test ClaudeAgentPlanningResult with multiple tasks."""
        plan = models.ClaudeAgentPlanningResult(
            plan=['Do first thing', 'Do second thing', 'Do third thing'],
            analysis='Test analysis',
        )
        self.assertEqual(len(plan.plan), 3)
        self.assertEqual(plan.plan[0], 'Do first thing')
        self.assertEqual(plan.plan[1], 'Do second thing')
        self.assertEqual(plan.plan[2], 'Do third thing')

    def test_agent_plan_empty_list(self) -> None:
        """Test ClaudeAgentPlanningResult with empty plan list."""
        plan = models.ClaudeAgentPlanningResult(plan=[], analysis='No tasks')
        self.assertEqual(plan.plan, [])


class ClaudeTestCase(base.AsyncTestCase):
    """Test cases for the Claude class."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        self.config = models.Configuration(
            claude_code=models.ClaudeCodeConfiguration(executable='claude'),
            anthropic=models.AnthropicConfiguration(),
            imbi=models.ImbiConfiguration(api_key='test', hostname='test.com'),
            commit_author='Test Author <test@example.com>',
        )

        # Create required directory structure
        (self.working_directory / 'workflow').mkdir()
        (self.working_directory / 'extracted').mkdir()
        (self.working_directory / 'repository').mkdir()

        # Create mock workflow and context
        self.workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
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

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    @mock.patch('claude_agent_sdk.ClaudeSDKClient')
    @mock.patch('claude_agent_sdk.create_sdk_mcp_server')
    @mock.patch(
        'builtins.open',
        new_callable=mock.mock_open,
        read_data='Mock system prompt',
    )
    def test_claude_init(
        self,
        mock_file: mock.MagicMock,
        mock_create_server: mock.MagicMock,
        mock_client_class: mock.MagicMock,
    ) -> None:
        """Test Claude initialization."""
        mock_server = mock.MagicMock()
        mock_create_server.return_value = mock_server
        mock_client_instance = mock.MagicMock()
        mock_client_class.return_value = mock_client_instance

        claude_instance = claude.Claude(
            config=self.config, context=self.context, verbose=True
        )

        # Verify initialization
        self.assertEqual(claude_instance.configuration, self.config)
        self.assertEqual(
            claude_instance.context.working_directory, self.working_directory
        )
        self.assertEqual(claude_instance.context.workflow, self.workflow)
        self.assertTrue(claude_instance.verbose)
        self.assertIsNone(claude_instance.session_id)

        # Verify client creation was called
        mock_client_class.assert_called_once()
        mock_create_server.assert_called_once()

    # Note: Removed obsolete _parse_message tests that tested return values.
    # The _parse_message method was refactored to return None and work via
    # side effects.

    def test_parse_message_assistant_message(self) -> None:
        """Test _parse_message with AssistantMessage."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        message = mock.MagicMock(spec=claude_agent_sdk.AssistantMessage)
        message.content = [mock.MagicMock(spec=claude_agent_sdk.TextBlock)]

        with mock.patch.object(claude_instance, '_log_message') as mock_log:
            result = claude_instance._parse_message(message)

        self.assertIsNone(result)
        mock_log.assert_called_once_with('Claude Assistant', message.content)

    def test_parse_message_system_message(self) -> None:
        """Test _parse_message with SystemMessage."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        message = mock.MagicMock(spec=claude_agent_sdk.SystemMessage)
        message.data = 'System message'

        result = claude_instance._parse_message(message)

        self.assertIsNone(result)

    def test_parse_message_user_message(self) -> None:
        """Test _parse_message with UserMessage."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        message = mock.MagicMock(spec=claude_agent_sdk.UserMessage)
        message.content = [mock.MagicMock(spec=claude_agent_sdk.TextBlock)]

        with mock.patch.object(claude_instance, '_log_message') as mock_log:
            result = claude_instance._parse_message(message)

        self.assertIsNone(result)
        mock_log.assert_called_once_with('Claude User', message.content)

    def test_log_message_with_text_list(self) -> None:
        """Test _log_message method with list of text blocks."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        text_block1 = mock.MagicMock(spec=claude_agent_sdk.TextBlock)
        text_block1.text = 'First message'
        text_block2 = mock.MagicMock(spec=claude_agent_sdk.TextBlock)
        text_block2.text = 'Second message'
        tool_block = mock.MagicMock(spec=claude_agent_sdk.ToolUseBlock)

        content = [text_block1, text_block2, tool_block]

        with mock.patch.object(claude_instance.logger, 'debug') as mock_debug:
            claude_instance._log_message('Test Type', content)

        # Verify only text blocks were logged
        self.assertEqual(mock_debug.call_count, 2)
        mock_debug.assert_has_calls(
            [
                mock.call(
                    '[%s] %s: %s', 'test-project', 'Test Type', 'First message'
                ),
                mock.call(
                    '[%s] %s: %s',
                    'test-project',
                    'Test Type',
                    'Second message',
                ),
            ]
        )

    def test_log_message_with_string(self) -> None:
        """Test _log_message method with string content."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        with mock.patch.object(claude_instance.logger, 'debug') as mock_debug:
            claude_instance._log_message('Test Type', 'Simple string message')

        mock_debug.assert_called_once_with(
            '[%s] %s: %s', 'test-project', 'Test Type', 'Simple string message'
        )

    def test_log_message_with_unknown_block_type(self) -> None:
        """Test _log_message method with unknown block type."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch('claude_agent_sdk.create_sdk_mcp_server'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        # Create a mock unknown block type
        unknown_block = mock.MagicMock()
        unknown_block.__class__.__name__ = 'UnknownBlock'
        content = [unknown_block]

        with self.assertRaises(RuntimeError) as exc_context:
            claude_instance._log_message('Test Type', content)

        self.assertIn('Unknown message type', str(exc_context.exception))

    # Note: execute-related tests moved to tests/actions/test_claude.py
    # Note: Removed obsolete session_id update tests - _parse_message now
    # returns None


if __name__ == '__main__':
    unittest.main()
