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


class ClaudePluginModelTestCase(unittest.TestCase):
    """Test cases for Claude plugin configuration models."""

    def test_marketplace_source_github_valid(self) -> None:
        """Test ClaudeMarketplaceSource with valid github source."""
        source = models.ClaudeMarketplaceSource(
            source=models.ClaudeMarketplaceSourceType.github,
            repo='company/claude-plugins',
        )
        self.assertEqual(
            source.source, models.ClaudeMarketplaceSourceType.github
        )
        self.assertEqual(source.repo, 'company/claude-plugins')
        self.assertIsNone(source.url)
        self.assertIsNone(source.path)

    def test_marketplace_source_github_missing_repo(self) -> None:
        """Test ClaudeMarketplaceSource github requires repo."""
        with self.assertRaises(ValueError) as exc_context:
            models.ClaudeMarketplaceSource(
                source=models.ClaudeMarketplaceSourceType.github
            )
        self.assertIn("'repo' is required", str(exc_context.exception))

    def test_marketplace_source_git_valid(self) -> None:
        """Test ClaudeMarketplaceSource with valid git source."""
        source = models.ClaudeMarketplaceSource(
            source=models.ClaudeMarketplaceSourceType.git,
            url='https://git.example.com/plugins.git',
        )
        self.assertEqual(source.source, models.ClaudeMarketplaceSourceType.git)
        self.assertEqual(source.url, 'https://git.example.com/plugins.git')

    def test_marketplace_source_git_missing_url(self) -> None:
        """Test ClaudeMarketplaceSource git requires url."""
        with self.assertRaises(ValueError) as exc_context:
            models.ClaudeMarketplaceSource(
                source=models.ClaudeMarketplaceSourceType.git
            )
        self.assertIn("'url' is required", str(exc_context.exception))

    def test_marketplace_source_directory_valid(self) -> None:
        """Test ClaudeMarketplaceSource with valid directory source."""
        source = models.ClaudeMarketplaceSource(
            source=models.ClaudeMarketplaceSourceType.directory,
            path='/local/plugins',
        )
        self.assertEqual(
            source.source, models.ClaudeMarketplaceSourceType.directory
        )
        self.assertEqual(source.path, '/local/plugins')

    def test_marketplace_source_directory_missing_path(self) -> None:
        """Test ClaudeMarketplaceSource directory requires path."""
        with self.assertRaises(ValueError) as exc_context:
            models.ClaudeMarketplaceSource(
                source=models.ClaudeMarketplaceSourceType.directory
            )
        self.assertIn("'path' is required", str(exc_context.exception))

    def test_marketplace_shorthand_source_format(self) -> None:
        """Test ClaudeMarketplace accepts shorthand source format."""
        # Shorthand: source and repo at top level
        marketplace = models.ClaudeMarketplace.model_validate(
            {'source': 'github', 'repo': 'org/plugins'}
        )
        self.assertEqual(
            marketplace.source.source,
            models.ClaudeMarketplaceSourceType.github,
        )
        self.assertEqual(marketplace.source.repo, 'org/plugins')

    def test_marketplace_nested_source_format(self) -> None:
        """Test ClaudeMarketplace accepts nested source format."""
        # Nested: source as a dict
        marketplace = models.ClaudeMarketplace.model_validate(
            {
                'source': {
                    'source': 'git',
                    'url': 'https://example.com/plugins.git',
                }
            }
        )
        self.assertEqual(
            marketplace.source.source, models.ClaudeMarketplaceSourceType.git
        )
        self.assertEqual(
            marketplace.source.url, 'https://example.com/plugins.git'
        )

    def test_local_plugin_valid(self) -> None:
        """Test ClaudeLocalPlugin creation."""
        plugin = models.ClaudeLocalPlugin(path='/path/to/plugin')
        self.assertEqual(plugin.path, '/path/to/plugin')

    def test_plugin_config_defaults(self) -> None:
        """Test ClaudePluginConfig default values."""
        config = models.ClaudePluginConfig()
        self.assertEqual(config.enabled_plugins, {})
        self.assertEqual(config.marketplaces, {})
        self.assertEqual(config.local_plugins, [])

    def test_plugin_config_with_values(self) -> None:
        """Test ClaudePluginConfig with actual values."""
        marketplace = models.ClaudeMarketplace(
            source=models.ClaudeMarketplaceSource(
                source=models.ClaudeMarketplaceSourceType.github,
                repo='org/plugins',
            )
        )
        config = models.ClaudePluginConfig(
            enabled_plugins={'plugin@market': True, 'other@market': False},
            marketplaces={'company': marketplace},
            local_plugins=[models.ClaudeLocalPlugin(path='/local/plugin')],
        )
        self.assertEqual(config.enabled_plugins['plugin@market'], True)
        self.assertEqual(config.enabled_plugins['other@market'], False)
        self.assertIn('company', config.marketplaces)
        self.assertEqual(len(config.local_plugins), 1)


class MergePluginConfigsTestCase(unittest.TestCase):
    """Test cases for _merge_plugin_configs function."""

    def test_merge_empty_configs(self) -> None:
        """Test merging two empty configs."""
        main = models.ClaudePluginConfig()
        workflow = models.ClaudePluginConfig()

        result = claude._merge_plugin_configs(main, workflow)

        self.assertEqual(result.enabled_plugins, {})
        self.assertEqual(result.marketplaces, {})
        self.assertEqual(result.local_plugins, [])

    def test_merge_enabled_plugins_workflow_overrides(self) -> None:
        """Test workflow enabled_plugins override main config."""
        main = models.ClaudePluginConfig(
            enabled_plugins={'plugin@market': True, 'other@market': True}
        )
        workflow = models.ClaudePluginConfig(
            enabled_plugins={'plugin@market': False, 'new@market': True}
        )

        result = claude._merge_plugin_configs(main, workflow)

        # Workflow overrides main
        self.assertEqual(result.enabled_plugins['plugin@market'], False)
        # Main value preserved
        self.assertEqual(result.enabled_plugins['other@market'], True)
        # New workflow value added
        self.assertEqual(result.enabled_plugins['new@market'], True)

    def test_merge_marketplaces(self) -> None:
        """Test marketplaces are merged with workflow taking precedence."""
        main_marketplace = models.ClaudeMarketplace(
            source=models.ClaudeMarketplaceSource(
                source=models.ClaudeMarketplaceSourceType.github,
                repo='main-org/plugins',
            )
        )
        workflow_marketplace = models.ClaudeMarketplace(
            source=models.ClaudeMarketplaceSource(
                source=models.ClaudeMarketplaceSourceType.github,
                repo='workflow-org/plugins',
            )
        )
        main = models.ClaudePluginConfig(
            marketplaces={
                'shared': main_marketplace,
                'main-only': main_marketplace,
            }
        )
        workflow = models.ClaudePluginConfig(
            marketplaces={
                'shared': workflow_marketplace,
                'workflow-only': workflow_marketplace,
            }
        )

        result = claude._merge_plugin_configs(main, workflow)

        # Workflow overrides shared key
        self.assertEqual(
            result.marketplaces['shared'].source.repo, 'workflow-org/plugins'
        )
        # Main-only preserved
        self.assertIn('main-only', result.marketplaces)
        # Workflow-only added
        self.assertIn('workflow-only', result.marketplaces)

    def test_merge_local_plugins_concatenated(self) -> None:
        """Test local plugins are concatenated."""
        main = models.ClaudePluginConfig(
            local_plugins=[
                models.ClaudeLocalPlugin(path='/main/plugin1'),
                models.ClaudeLocalPlugin(path='/main/plugin2'),
            ]
        )
        workflow = models.ClaudePluginConfig(
            local_plugins=[models.ClaudeLocalPlugin(path='/workflow/plugin')]
        )

        result = claude._merge_plugin_configs(main, workflow)

        self.assertEqual(len(result.local_plugins), 3)
        paths = [p.path for p in result.local_plugins]
        self.assertIn('/main/plugin1', paths)
        self.assertIn('/main/plugin2', paths)
        self.assertIn('/workflow/plugin', paths)

    def test_merge_local_plugins_deduplicates(self) -> None:
        """Test duplicate local plugin paths are removed."""
        main = models.ClaudePluginConfig(
            local_plugins=[models.ClaudeLocalPlugin(path='/shared/plugin')]
        )
        workflow = models.ClaudePluginConfig(
            local_plugins=[
                models.ClaudeLocalPlugin(path='/shared/plugin'),
                models.ClaudeLocalPlugin(path='/unique/plugin'),
            ]
        )

        result = claude._merge_plugin_configs(main, workflow)

        self.assertEqual(len(result.local_plugins), 2)
        paths = [p.path for p in result.local_plugins]
        self.assertIn('/shared/plugin', paths)
        self.assertIn('/unique/plugin', paths)


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
            claude=models.ClaudeAgentConfiguration(executable='claude'),
            anthropic=models.AnthropicConfiguration(),
            git=models.GitConfiguration(
                user_name='Test Author', user_email='test@example.com'
            ),
            imbi=models.ImbiConfiguration(api_key='test', hostname='test.com'),
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
    @mock.patch(
        'builtins.open',
        new_callable=mock.mock_open,
        read_data='Mock system prompt',
    )
    def test_claude_init(
        self, mock_file: mock.MagicMock, mock_client_class: mock.MagicMock
    ) -> None:
        """Test Claude initialization."""
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

    # Note: Removed obsolete _parse_message tests that tested return values.
    # The _parse_message method was refactored to return None and work via
    # side effects.

    def test_parse_message_assistant_message(self) -> None:
        """Test _parse_message with AssistantMessage."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
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

    def test_parse_message_result_with_success(self) -> None:
        """Test _parse_message handles successful ResultMessage."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        # Create a proper ResultMessage-like object
        message = claude_agent_sdk.ResultMessage(
            subtype='success',
            duration_ms=100,
            duration_api_ms=90,
            is_error=False,
            num_turns=1,
            session_id='test-session',
            total_cost_usd=0.01,
            usage=_create_mock_result_message_usage(),
            result='Success',
            structured_output=None,
        )

        # Parse message should not raise
        claude_instance._parse_message(message)

        # Verify session_id was captured
        self.assertEqual(claude_instance.session_id, 'test-session')

    def test_parse_message_result_with_error(self) -> None:
        """Test _parse_message handles error ResultMessage."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        # Create a proper ResultMessage-like object with error
        message = claude_agent_sdk.ResultMessage(
            subtype='error',
            duration_ms=100,
            duration_api_ms=90,
            is_error=True,
            num_turns=1,
            session_id='test-session',
            total_cost_usd=0.01,
            usage=_create_mock_result_message_usage(),
            result='Error occurred',
            structured_output=None,
        )

        # Parse message should log error but not raise
        claude_instance._parse_message(message)

    def test_get_agent_prompt_returns_prompt(self) -> None:
        """Test get_agent_prompt returns the agent's prompt content."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        # Set up agents with prompt content using AgentDefinition dataclass
        from claude_agent_sdk import types

        claude_instance.agents['task'] = types.AgentDefinition(
            description='Test agent',
            prompt='# TASK AGENT\n\nExecute the task.',
            tools=['Read', 'Write'],
            model='inherit',
        )

        result = claude_instance.get_agent_prompt(models.ClaudeAgentType.task)

        self.assertEqual(result, '# TASK AGENT\n\nExecute the task.')

    def test_get_agent_prompt_raises_for_missing_agent(self) -> None:
        """Test get_agent_prompt raises ValueError for missing agent."""
        with (
            mock.patch('claude_agent_sdk.ClaudeSDKClient'),
            mock.patch(
                'builtins.open',
                new_callable=mock.mock_open,
                read_data='Mock system prompt',
            ),
        ):
            claude_instance = claude.Claude(
                config=self.config, context=self.context
            )

        # Ensure the agent is None (default from Agents TypedDict)
        claude_instance.agents['planning'] = None

        with self.assertRaises(ValueError) as exc_context:
            claude_instance.get_agent_prompt(models.ClaudeAgentType.planning)

        self.assertIn('No agent definition', str(exc_context.exception))


if __name__ == '__main__':
    unittest.main()
