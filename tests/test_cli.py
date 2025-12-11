"""Tests for cli.py - Command-line interface.

Covers argument parsing, configuration loading, logging setup,
and main execution flow.
"""

# ruff: noqa: S106, S108, SIM117

import argparse
import io
import logging
import pathlib
import tempfile
import tomllib
import unittest
from unittest import mock

import pydantic

from imbi_automations import cli, models


class ConfigureLoggingTestCase(unittest.TestCase):
    """Test logging configuration."""

    def test_configure_logging_info_level(self) -> None:
        """Test logging configuration at INFO level."""
        # Reset logger first
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        cli.configure_logging(debug=False)

        self.assertEqual(root_logger.level, logging.INFO)

    def test_configure_logging_debug_level(self) -> None:
        """Test logging configuration at DEBUG level."""
        # Reset logger first
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        cli.configure_logging(debug=True)

        self.assertEqual(root_logger.level, logging.DEBUG)

    def test_configure_logging_sets_external_loggers_to_warning(self) -> None:
        """Test external loggers set to WARNING level."""
        cli.configure_logging(debug=True)

        for logger_name in (
            'anthropic',
            'claude_agent_sdk',
            'httpcore',
            'httpx',
        ):
            logger = logging.getLogger(logger_name)
            self.assertEqual(logger.level, logging.WARNING)


class LoadConfigurationTestCase(unittest.TestCase):
    """Test configuration loading."""

    def test_load_configuration_valid_toml(self) -> None:
        """Test loading valid configuration from TOML."""
        config_toml = """
[imbi]
hostname = "imbi.example.com"
api_key = "test-key"

[github]
token = "github-token"
"""
        config_file = io.StringIO(config_toml)

        config = cli.load_configuration(config_file)

        self.assertIsInstance(config, models.Configuration)
        self.assertEqual(config.imbi.hostname, 'imbi.example.com')
        self.assertEqual(
            config.github.token.get_secret_value(), 'github-token'
        )

    def test_load_configuration_invalid_toml(self) -> None:
        """Test loading invalid TOML raises TOMLDecodeError."""
        invalid_toml = """
[imbi
invalid syntax
"""
        config_file = io.StringIO(invalid_toml)

        with self.assertRaises(tomllib.TOMLDecodeError):
            cli.load_configuration(config_file)

    def test_load_configuration_validation_error(self) -> None:
        """Test configuration validation errors."""
        # Invalid type for a field
        config_toml = """
[imbi]
hostname = "imbi.example.com"
api_key = 123
"""
        config_file = io.StringIO(config_toml)

        with self.assertRaises(pydantic.ValidationError):
            cli.load_configuration(config_file)


class WorkflowTypeTestCase(unittest.TestCase):
    """Test workflow argument type parsing."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workflow_dir = pathlib.Path(self.temp_dir.name) / 'test-workflow'
        self.workflow_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        super().tearDown()

    def test_workflow_valid_path(self) -> None:
        """Test workflow parser with valid workflow directory."""
        config_file = self.workflow_dir / 'workflow.toml'
        config_file.write_text("""
name = "Test Workflow"
actions = []
""")

        result = cli.workflow(str(self.workflow_dir))

        self.assertIsInstance(result, models.Workflow)
        self.assertEqual(result.path, self.workflow_dir)
        self.assertEqual(result.configuration.name, 'Test Workflow')

    def test_workflow_config_toml_fallback(self) -> None:
        """Test workflow parser falls back to config.toml."""
        config_file = self.workflow_dir / 'config.toml'
        config_file.write_text("""
name = "Test Workflow Fallback"
actions = []
""")

        result = cli.workflow(str(self.workflow_dir))

        self.assertIsInstance(result, models.Workflow)
        self.assertEqual(result.path, self.workflow_dir)
        self.assertEqual(result.configuration.name, 'Test Workflow Fallback')

    def test_workflow_prefers_workflow_toml(self) -> None:
        """Test workflow parser prefers workflow.toml over config.toml."""
        # Create both files
        (self.workflow_dir / 'workflow.toml').write_text("""
name = "Workflow TOML"
actions = []
""")
        (self.workflow_dir / 'config.toml').write_text("""
name = "Config TOML"
actions = []
""")

        result = cli.workflow(str(self.workflow_dir))

        # Should use workflow.toml
        self.assertEqual(result.configuration.name, 'Workflow TOML')

    def test_workflow_not_a_directory(self) -> None:
        """Test workflow parser with non-directory path."""
        file_path = self.workflow_dir / 'file.txt'
        file_path.write_text('not a directory')

        with self.assertRaises(argparse.ArgumentTypeError) as ctx:
            cli.workflow(str(file_path))

        self.assertIn('not a directory', str(ctx.exception))

    def test_workflow_missing_config_file(self) -> None:
        """Test workflow parser with missing workflow config file."""
        # Workflow dir exists but no workflow.toml or config.toml

        with self.assertRaises(argparse.ArgumentTypeError) as ctx:
            cli.workflow(str(self.workflow_dir))

        self.assertIn('Missing workflow configuration', str(ctx.exception))

    def test_workflow_invalid_config_toml(self) -> None:
        """Test workflow parser with invalid TOML syntax."""
        config_file = self.workflow_dir / 'workflow.toml'
        config_file.write_text('[invalid')

        with self.assertRaises(argparse.ArgumentTypeError) as ctx:
            cli.workflow(str(self.workflow_dir))

        self.assertIn('failed to parse', str(ctx.exception).lower())

    def test_workflow_invalid_config_validation(self) -> None:
        """Test workflow parser with config validation errors."""
        config_file = self.workflow_dir / 'workflow.toml'
        # Missing required 'name' field
        config_file.write_text('actions = []')

        with self.assertRaises(argparse.ArgumentTypeError) as ctx:
            cli.workflow(str(self.workflow_dir))

        self.assertIn('Invalid workflow configuration', str(ctx.exception))


class ParseArgsTestCase(unittest.TestCase):
    """Test command-line argument parsing."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = pathlib.Path(self.temp_dir.name) / 'config.toml'
        self.config_file.write_text("""
[imbi]
hostname = "imbi.example.com"
api_key = "test-key"

[github]
token = "github-token"
""")

        self.workflow_dir = pathlib.Path(self.temp_dir.name) / 'workflow'
        self.workflow_dir.mkdir()
        (self.workflow_dir / 'workflow.toml').write_text("""
name = "Test Workflow"
actions = []
""")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        super().tearDown()

    def test_parse_args_project_id(self) -> None:
        """Test parsing with --project-id."""
        args = cli.parse_args(
            [
                str(self.config_file),
                str(self.workflow_dir),
                '--project-id',
                '123',
            ]
        )

        self.assertEqual(args.project_id, 123)
        self.assertIsInstance(args.workflow, models.Workflow)

    def test_parse_args_project_type(self) -> None:
        """Test parsing with --project-type."""
        args = cli.parse_args(
            [
                str(self.config_file),
                str(self.workflow_dir),
                '--project-type',
                'apis',
            ]
        )

        self.assertEqual(args.project_type, 'apis')

    def test_parse_args_all_projects(self) -> None:
        """Test parsing with --all-projects."""
        args = cli.parse_args(
            [str(self.config_file), str(self.workflow_dir), '--all-projects']
        )

        self.assertTrue(args.all_projects)

    def test_parse_args_resume(self) -> None:
        """Test parsing with --resume."""
        error_dir = pathlib.Path(self.temp_dir.name) / 'errors'
        error_dir.mkdir()

        args = cli.parse_args(
            [
                str(self.config_file),
                str(self.workflow_dir),
                '--resume',
                str(error_dir),
            ]
        )

        self.assertEqual(args.resume, error_dir)

    def test_parse_args_debug_flag(self) -> None:
        """Test parsing with --debug flag."""
        args = cli.parse_args(
            [
                str(self.config_file),
                str(self.workflow_dir),
                '--project-id',
                '1',
                '--debug',
            ]
        )

        self.assertTrue(args.debug)

    def test_parse_args_verbose_flag(self) -> None:
        """Test parsing with --verbose flag."""
        args = cli.parse_args(
            [
                str(self.config_file),
                str(self.workflow_dir),
                '--project-id',
                '1',
                '--verbose',
            ]
        )

        self.assertTrue(args.verbose)

    def test_parse_args_max_concurrency(self) -> None:
        """Test parsing with --max-concurrency."""
        args = cli.parse_args(
            [
                str(self.config_file),
                str(self.workflow_dir),
                '--project-id',
                '1',
                '--max-concurrency',
                '5',
            ]
        )

        self.assertEqual(args.max_concurrency, 5)

    def test_parse_args_preserve_on_error(self) -> None:
        """Test parsing with --preserve-on-error."""
        args = cli.parse_args(
            [
                str(self.config_file),
                str(self.workflow_dir),
                '--project-id',
                '1',
                '--preserve-on-error',
            ]
        )

        self.assertTrue(args.preserve_on_error)

    def test_parse_args_exit_on_error(self) -> None:
        """Test parsing with --exit-on-error."""
        args = cli.parse_args(
            [
                str(self.config_file),
                str(self.workflow_dir),
                '--project-id',
                '1',
                '--exit-on-error',
            ]
        )

        self.assertTrue(args.exit_on_error)

    def test_parse_args_dry_run(self) -> None:
        """Test parsing with --dry-run."""
        args = cli.parse_args(
            [
                str(self.config_file),
                str(self.workflow_dir),
                '--project-id',
                '1',
                '--dry-run',
            ]
        )

        self.assertTrue(args.dry_run)


class MainExecutionTestCase(unittest.TestCase):
    """Test main execution flow."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = pathlib.Path(self.temp_dir.name) / 'config.toml'
        self.config_file.write_text("""
[imbi]
hostname = "imbi.example.com"
api_key = "test-key"
github_identifier = "github"
github_link = "GitHub"

[github]
token = "github-token"
""")

        self.workflow_dir = pathlib.Path(self.temp_dir.name) / 'workflow'
        self.workflow_dir.mkdir()
        (self.workflow_dir / 'workflow.toml').write_text("""
name = "Test Workflow"
actions = []
""")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        super().tearDown()

    def test_main_successful_execution(self) -> None:
        """Test successful main execution."""
        test_args = [
            str(self.config_file),
            str(self.workflow_dir),
            '--project-id',
            '1',
        ]

        with mock.patch('sys.argv', ['imbi-automations'] + test_args):
            with mock.patch(
                'imbi_automations.cli.parse_args',
                return_value=mock.MagicMock(
                    config=[
                        mock.mock_open(
                            read_data=self.config_file.read_text()
                        )()
                    ],
                    workflow=models.Workflow(
                        path=self.workflow_dir,
                        configuration=models.WorkflowConfiguration(
                            name='Test', actions=[]
                        ),
                    ),
                    cache_dir=None,
                    preserve_on_error=False,
                    error_dir=None,
                    dry_run=False,
                    dry_run_dir=None,
                    debug=False,
                ),
            ):
                with mock.patch(
                    'imbi_automations.controller.Automation'
                ) as mock_automation:
                    mock_instance = mock.MagicMock()
                    mock_instance.run = mock.AsyncMock(return_value=True)
                    mock_automation.return_value = mock_instance

                    cli.main()

                    mock_automation.assert_called_once()

    def test_main_controller_initialization_error(self) -> None:
        """Test main exits on controller initialization error."""
        test_args = [
            str(self.config_file),
            str(self.workflow_dir),
            '--project-id',
            '1',
        ]

        with mock.patch('sys.argv', ['imbi-automations'] + test_args):
            with mock.patch(
                'imbi_automations.cli.parse_args',
                return_value=mock.MagicMock(
                    config=[
                        mock.mock_open(
                            read_data=self.config_file.read_text()
                        )()
                    ],
                    workflow=models.Workflow(
                        path=self.workflow_dir,
                        configuration=models.WorkflowConfiguration(
                            name='Test', actions=[]
                        ),
                    ),
                    cache_dir=None,
                    preserve_on_error=False,
                    error_dir=None,
                    dry_run=False,
                    dry_run_dir=None,
                    debug=False,
                ),
            ):
                with mock.patch(
                    'imbi_automations.controller.Automation',
                    side_effect=RuntimeError('Init error'),
                ):
                    with self.assertRaises(SystemExit) as ctx:
                        cli.main()

                    self.assertEqual(ctx.exception.code, 1)

    def test_main_keyboard_interrupt(self) -> None:
        """Test main handles KeyboardInterrupt."""
        test_args = [
            str(self.config_file),
            str(self.workflow_dir),
            '--project-id',
            '1',
        ]

        with mock.patch('sys.argv', ['imbi-automations'] + test_args):
            with mock.patch(
                'imbi_automations.cli.parse_args',
                return_value=mock.MagicMock(
                    config=[
                        mock.mock_open(
                            read_data=self.config_file.read_text()
                        )()
                    ],
                    workflow=models.Workflow(
                        path=self.workflow_dir,
                        configuration=models.WorkflowConfiguration(
                            name='Test', actions=[]
                        ),
                    ),
                    cache_dir=None,
                    preserve_on_error=False,
                    error_dir=None,
                    dry_run=False,
                    dry_run_dir=None,
                    debug=False,
                ),
            ):
                with mock.patch(
                    'imbi_automations.controller.Automation'
                ) as mock_automation:
                    mock_instance = mock.MagicMock()
                    mock_instance.run = mock.AsyncMock(
                        side_effect=KeyboardInterrupt()
                    )
                    mock_automation.return_value = mock_instance

                    with self.assertRaises(SystemExit) as ctx:
                        cli.main()

                    self.assertEqual(ctx.exception.code, 2)

    def test_main_runtime_error_during_execution(self) -> None:
        """Test main handles RuntimeError during execution."""
        test_args = [
            str(self.config_file),
            str(self.workflow_dir),
            '--project-id',
            '1',
        ]

        with mock.patch('sys.argv', ['imbi-automations'] + test_args):
            with mock.patch(
                'imbi_automations.cli.parse_args',
                return_value=mock.MagicMock(
                    config=[
                        mock.mock_open(
                            read_data=self.config_file.read_text()
                        )()
                    ],
                    workflow=models.Workflow(
                        path=self.workflow_dir,
                        configuration=models.WorkflowConfiguration(
                            name='Test', actions=[]
                        ),
                    ),
                    cache_dir=None,
                    preserve_on_error=False,
                    error_dir=None,
                    dry_run=False,
                    dry_run_dir=None,
                    debug=False,
                ),
            ):
                with mock.patch(
                    'imbi_automations.controller.Automation'
                ) as mock_automation:
                    mock_instance = mock.MagicMock()
                    mock_instance.run = mock.AsyncMock(
                        side_effect=RuntimeError('Execution error')
                    )
                    mock_automation.return_value = mock_instance

                    with self.assertRaises(SystemExit) as ctx:
                        cli.main()

                    self.assertEqual(ctx.exception.code, 3)

    def test_main_unsuccessful_execution(self) -> None:
        """Test main exits with code 5 on unsuccessful execution."""
        test_args = [
            str(self.config_file),
            str(self.workflow_dir),
            '--project-id',
            '1',
        ]

        with mock.patch('sys.argv', ['imbi-automations'] + test_args):
            with mock.patch(
                'imbi_automations.cli.parse_args',
                return_value=mock.MagicMock(
                    config=[
                        mock.mock_open(
                            read_data=self.config_file.read_text()
                        )()
                    ],
                    workflow=models.Workflow(
                        path=self.workflow_dir,
                        configuration=models.WorkflowConfiguration(
                            name='Test', actions=[]
                        ),
                    ),
                    cache_dir=None,
                    preserve_on_error=False,
                    error_dir=None,
                    dry_run=False,
                    dry_run_dir=None,
                    debug=False,
                ),
            ):
                with mock.patch(
                    'imbi_automations.controller.Automation'
                ) as mock_automation:
                    mock_instance = mock.MagicMock()
                    mock_instance.run = mock.AsyncMock(return_value=False)
                    mock_automation.return_value = mock_instance

                    with self.assertRaises(SystemExit) as ctx:
                        cli.main()

                    self.assertEqual(ctx.exception.code, 5)
