"""Command-line interface for Imbi Automations.

Provides the main entry point for the imbi-automations CLI tool, handling
argument parsing, configuration loading, colored logging setup, and
orchestrating workflow execution through the controller.
"""

import argparse
import asyncio
import logging
import pathlib
import sys
import tomllib
import typing

import colorlog
import pydantic

from imbi_automations import controller, models, tracker, utils, version

LOGGER = logging.getLogger(__name__)


def configure_logging(debug: bool) -> None:
    """Configure colored logging for CLI applications."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - '
            '%(message)s',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            },
        )
    )

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO, handlers=[handler]
    )

    for logger_name in ('anthropic', 'claude_agent_sdk', 'httpcore', 'httpx'):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def load_configuration(config_file: typing.TextIO) -> models.Configuration:
    """Load configuration from config file

    Args:
        config_file: Path to the main configuration file or file-like object

    Returns:
        Configuration object with merged data

    Raises:
        tomllib.TOMLDecodeError: If TOML parsing fails
        pydantic.ValidationError: If configuration validation fails

    """
    return models.Configuration.model_validate(utils.load_toml(config_file))


def workflow(path: str) -> models.Workflow:
    """Argument type for parsing a workflow and its configuration."""
    path_obj = pathlib.Path(path)
    if not path_obj.is_dir():
        raise argparse.ArgumentTypeError(
            f'Workflow path is not a directory: {path}'
        )
    for workflow_file in ('workflow.toml', 'config.toml'):
        if (path_obj / workflow_file).is_file():
            if workflow_file == 'config.toml':
                LOGGER.warning('config.toml is deprecated, use workflow.toml')
            return _load_workflow(path_obj / workflow_file)

    raise argparse.ArgumentTypeError(
        f'Missing workflow configuration file in workflow directory: '
        f'{path}\nExpected: workflow.toml'
    )


def _load_workflow(path: pathlib.Path | None) -> models.Workflow:
    with path.open('r') as handle:
        try:
            config_data = utils.load_toml(handle)
        except tomllib.TOMLDecodeError as exc:
            raise argparse.ArgumentTypeError(
                f'Failed to parse workflow config in {path}:\n{exc}'
            ) from exc
    try:
        return models.Workflow(
            path=path.parent,
            configuration=models.WorkflowConfiguration.model_validate(
                config_data
            ),
        )
    except pydantic.ValidationError as exc:
        # Extract the most relevant part of Pydantic validation errors
        error_msg = str(exc)
        lines = error_msg.split('\n')
        main_error = next(
            (line for line in lines if 'Input should be' in line), error_msg
        )
        raise argparse.ArgumentTypeError(
            f'Invalid workflow configuration in {path}:\n{main_error}'
        ) from exc


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for imbi-automations.

    Args:
        args: List of command-line arguments. Defaults to sys.argv if None.

    Returns:
        Parsed argument namespace with configuration, workflow, and
        targeting options.
    """
    parser = argparse.ArgumentParser(
        description='Imbi Automations',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.register('type', 'workflow', workflow)
    parser.add_argument(
        'config',
        type=argparse.FileType('r'),
        metavar='CONFIG',
        help='Configuration file',
        nargs=1,
    )
    parser.add_argument(
        'workflow',
        metavar='WORKFLOW',
        type='workflow',
        help='Path to the directory containing the workflow to run '
        '(expects workflow.toml, falls back to config.toml)',
    )

    # Target argument group - specify how to target repositories
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        '--project-id',
        type=int,
        metavar='ID',
        help='Process a single project by Project ID',
    )
    target_group.add_argument(
        '--project-type',
        metavar='SLUG',
        help='Process all projects of a specific type slug',
    )
    target_group.add_argument(
        '--all-projects', action='store_true', help='Process all projects'
    )
    target_group.add_argument(
        '--github-repository',
        metavar='URL',
        help='Process a single GitHub repository by URL',
    )
    target_group.add_argument(
        '--github-organization',
        metavar='ORG',
        help='Process all repositories in a GitHub organization',
    )
    target_group.add_argument(
        '--all-github-repositories',
        action='store_true',
        help='Process all GitHub repositories across all organizations',
    )
    target_group.add_argument(
        '--resume',
        type=pathlib.Path,
        metavar='ERROR_DIR',
        help='Resume from previous error state directory '
        '(looks for .state file inside)',
    )

    parser.add_argument(
        '--start-from-project',
        metavar='ID_OR_SLUG',
        help='When processing multiple projects, skip all projects up to '
        'and including this project (accepts project ID or slug)',
    )

    parser.add_argument(
        '--max-concurrency',
        type=int,
        default=1,
        help='How many concurrent tasks to run at a time',
    )

    parser.add_argument(
        '--exit-on-error',
        action='store_true',
        help='Exit immediately when any action fails '
        '(default: continue with other projects)',
    )
    parser.add_argument(
        '--preserve-on-error',
        action='store_true',
        help='Preserve working directory on error for debugging '
        '(saved to error-dir/<workflow>/<project>-<timestamp>)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Save repository state to dry-run-dir instead of pushing '
        'changes or creating pull requests',
    )
    parser.add_argument(
        '--cache-dir',
        type=pathlib.Path,
        default=pathlib.Path.home() / '.cache' / 'imbi-automations',
        help='Directory for caching Imbi metadata',
    )
    parser.add_argument(
        '--dry-run-dir',
        type=pathlib.Path,
        default=pathlib.Path('./dry-runs'),
        help='Directory to save repository state when --dry-run is used',
    )
    parser.add_argument(
        '--error-dir',
        type=pathlib.Path,
        default=pathlib.Path('./errors'),
        help='Directory to save error states when --preserve-on-error is used',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Show action start/end INFO messages',
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging (shows all debug messages)',
    )
    parser.add_argument('-V', '--version', action='version', version=version)
    return parser.parse_args(args)


def main() -> None:
    """Main entry point for imbi-automations CLI.

    Parses arguments, loads configuration, validates workflow requirements,
    and executes the automation controller with proper error handling.
    """
    args = parse_args()
    configure_logging(args.debug)

    config = load_configuration(args.config[0])
    args.config[0].close()

    # Override config with CLI args
    if args.cache_dir:
        config.cache_dir = args.cache_dir
    if args.preserve_on_error:
        config.preserve_on_error = True
    if args.error_dir:
        config.error_dir = args.error_dir
    if args.dry_run:
        config.dry_run = True
    if args.dry_run_dir:
        config.dry_run_dir = args.dry_run_dir

    LOGGER.info('Imbi Automations v%s starting', version)
    try:
        automation_controller = controller.Automation(
            args=args, config=config, workflow=args.workflow
        )
    except RuntimeError as err:
        sys.stderr.write(f'ERROR: {err}\n')
        tracker.report()
        sys.exit(1)
    try:
        success = asyncio.run(automation_controller.run())
    except KeyboardInterrupt:
        LOGGER.info('Interrupted, exiting')
        tracker.report()
        sys.exit(2)
    except RuntimeError as err:
        sys.stderr.write(f'Error running automation: {err}\n')
        tracker.report()
        sys.exit(3)
    tracker.report()
    if not success:
        sys.exit(5)
