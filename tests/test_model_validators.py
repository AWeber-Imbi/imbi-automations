import pathlib
import re
import unittest
from unittest import mock

from imbi_automations.models.configuration import Configuration
from imbi_automations.models.workflow import (
    WorkflowCondition,
    WorkflowDockerAction,
    WorkflowDockerActionCommand,
    WorkflowFileAction,
    WorkflowFileActionCommand,
)
from tests import base


class ModelValidatorsTestCase(unittest.TestCase):
    def test_docker_build_requires_path(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowDockerAction(
                name='d',
                type='docker',
                command=WorkflowDockerActionCommand.build,
                image='x',
            )
        # valid when path is provided
        action = WorkflowDockerAction(
            name='d',
            type='docker',
            command=WorkflowDockerActionCommand.build,
            image='x',
            path=pathlib.Path('Dockerfile'),
        )
        # path is now a ResourceUrl, check string representation
        self.assertEqual(str(action.path), 'file:///Dockerfile')

    def test_docker_pull_forbids_path(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowDockerAction(
                name='d',
                type='docker',
                command=WorkflowDockerActionCommand.pull,
                image='x',
                path=pathlib.Path('.'),
            )

    def test_file_delete_requires_path_or_pattern(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowFileAction(
                name='f', type='file', command=WorkflowFileActionCommand.delete
            )
        # Valid with path
        WorkflowFileAction(
            name='f',
            type='file',
            command=WorkflowFileActionCommand.delete,
            path=pathlib.Path('foo'),
        )
        # Valid with pattern
        WorkflowFileAction(
            name='f',
            type='file',
            command=WorkflowFileActionCommand.delete,
            pattern=re.compile(r'.*'),
        )

    def test_file_append_requires_path_and_content(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowFileAction(
                name='f',
                type='file',
                command=WorkflowFileActionCommand.append,
                path=pathlib.Path('a'),
            )
        with self.assertRaises(ValueError):
            WorkflowFileAction(
                name='f',
                type='file',
                command=WorkflowFileActionCommand.append,
                content='x',
            )
        # valid
        WorkflowFileAction(
            name='f',
            type='file',
            command=WorkflowFileActionCommand.append,
            path=pathlib.Path('a'),
            content='x',
        )

    def test_condition_exactly_one(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowCondition()
        with self.assertRaises(ValueError):
            WorkflowCondition(file_exists='a', remote_file_exists='b')
        # valid: paired
        c = WorkflowCondition(file_contains='x', file=pathlib.Path('f'))
        self.assertIsNotNone(c)

    def test_condition_pairing_errors(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowCondition(file_contains='x')
        with self.assertRaises(ValueError):
            WorkflowCondition(file=pathlib.Path('f'))


class ConfigurationJiraEnvTestCase(base.AsyncTestCase):
    """Jira configuration should be auto-populated from ATLASSIAN_* env vars
    when the user omits a `[jira]` section in config.toml."""

    def test_jira_populated_from_env_vars_without_section(self) -> None:
        env = {
            'ATLASSIAN_DOMAIN': 'example.atlassian.net',
            'ATLASSIAN_EMAIL': 'bot@example.com',
            'ATLASSIAN_API_KEY': 'secret',
            'GH_TOKEN': 'gh-token',
            'IMBI_API_KEY': 'imbi-key',
            'IMBI_HOSTNAME': 'imbi.example.com',
        }
        with mock.patch.dict('os.environ', env, clear=True):
            cfg = Configuration()
        self.assertIsNotNone(cfg.jira)
        self.assertEqual(cfg.jira.domain, 'example.atlassian.net')
        self.assertEqual(cfg.jira.email, 'bot@example.com')
        self.assertEqual(
            cfg.jira.api_key.get_secret_value(), 'secret'
        )

    def test_jira_left_none_when_env_vars_missing(self) -> None:
        env = {
            'GH_TOKEN': 'gh-token',
            'IMBI_API_KEY': 'imbi-key',
            'IMBI_HOSTNAME': 'imbi.example.com',
        }
        with mock.patch.dict('os.environ', env, clear=True):
            cfg = Configuration()
        self.assertIsNone(cfg.jira)


if __name__ == '__main__':
    unittest.main()
