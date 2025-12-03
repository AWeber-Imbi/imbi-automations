"""Comprehensive tests for the condition_checker module."""

import pathlib
import tempfile
import unittest
from unittest import mock

from imbi_automations import condition_checker, models
from tests import base


class ConditionCheckerTestCase(base.AsyncTestCase):
    """Test cases for ConditionChecker functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)
        self.repository_dir = self.working_directory / 'repository'
        self.repository_dir.mkdir()

        # Create test files
        (self.repository_dir / 'package.json').write_text(
            '{"name": "test-project", "version": "1.0.0"}'
        )
        (self.repository_dir / 'requirements.txt').write_text(
            'fastapi==0.68.0\nuvicorn==0.15.0'
        )
        (self.repository_dir / 'src').mkdir()
        (self.repository_dir / 'src' / 'main.py').write_text('print("hello")')
        (self.repository_dir / 'tests').mkdir()
        (self.repository_dir / 'tests' / 'test_main.py').write_text(
            'def test(): pass'
        )

        # Create configuration and checker
        self.config = models.Configuration(
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.test.com'
            ),
            github=models.GitHubConfiguration(
                token='test-github-key',  # noqa: S106
                host='github.com',
            ),
        )
        self.checker = condition_checker.ConditionChecker(
            self.config, verbose=True
        )

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

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    def test_check_no_conditions(self) -> None:
        """Test check method with no conditions."""
        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, []
        )
        self.assertTrue(result)

    def test_check_file_exists_success(self) -> None:
        """Test file_exists condition with existing file."""
        condition = models.WorkflowCondition(
            file_exists='repository://package.json'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_check_file_exists_failure(self) -> None:
        """Test file_exists condition with non-existent file."""
        condition = models.WorkflowCondition(
            file_exists='repository://nonexistent.txt'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_check_file_not_exists_success(self) -> None:
        """Test file_not_exists condition with non-existent file."""
        condition = models.WorkflowCondition(
            file_not_exists='repository://nonexistent.txt'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_check_file_not_exists_failure(self) -> None:
        """Test file_not_exists condition with existing file."""
        condition = models.WorkflowCondition(
            file_not_exists='repository://package.json'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_check_file_contains_success(self) -> None:
        """Test file_contains condition with matching content."""
        condition = models.WorkflowCondition(
            file_contains='test-project', file='repository://package.json'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_check_file_contains_failure(self) -> None:
        """Test file_contains condition with non-matching content."""
        condition = models.WorkflowCondition(
            file_contains='nonexistent-content',
            file='repository://package.json',
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_check_file_contains_missing_file(self) -> None:
        """Test file_contains condition with missing file."""
        condition = models.WorkflowCondition(
            file_contains='test', file='repository://missing.txt'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_check_regex_pattern_exists_success(self) -> None:
        """Test file_exists with glob pattern that matches."""
        # Use glob pattern instead of compiled regex
        condition = models.WorkflowCondition(
            file_exists='repository://**/*.py'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(
            result
        )  # Should find src/main.py or tests/test_main.py

    def test_check_regex_pattern_exists_failure(self) -> None:
        """Test file_exists with glob pattern that doesn't match."""
        # Use glob pattern instead of compiled regex
        condition = models.WorkflowCondition(
            file_exists='repository://**/*.go'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)  # No .go files

    def test_check_regex_pattern_not_exists_success(self) -> None:
        """Test file_not_exists with glob pattern that doesn't match."""
        # Use glob pattern instead of compiled regex
        condition = models.WorkflowCondition(
            file_not_exists='repository://**/*.go'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)  # No .go files, so condition passes

    def test_check_regex_pattern_not_exists_failure(self) -> None:
        """Test file_not_exists with glob pattern that matches."""
        # Use glob pattern instead of compiled regex
        condition = models.WorkflowCondition(
            file_not_exists='repository://**/*.py'
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)  # .py files exist, so condition fails

    def test_check_condition_type_any_success(self) -> None:
        """Test condition_type 'any' with mixed conditions."""
        conditions = [
            models.WorkflowCondition(
                file_exists='repository://nonexistent.txt'
            ),  # False
            models.WorkflowCondition(
                file_exists='repository://package.json'
            ),  # True
        ]

        result = self.checker.check(
            self.context, models.WorkflowConditionType.any, conditions
        )

        self.assertTrue(result)  # One condition passes, any() returns True

    def test_check_condition_type_any_failure(self) -> None:
        """Test condition_type 'any' with all failing conditions."""
        conditions = [
            models.WorkflowCondition(
                file_exists='repository://nonexistent1.txt'
            ),  # False
            models.WorkflowCondition(
                file_exists='repository://nonexistent2.txt'
            ),  # False
        ]

        result = self.checker.check(
            self.context, models.WorkflowConditionType.any, conditions
        )

        self.assertFalse(result)  # All conditions fail, any() returns False

    def test_check_condition_type_all_success(self) -> None:
        """Test condition_type 'all' with all passing conditions."""
        conditions = [
            models.WorkflowCondition(
                file_exists='repository://package.json'
            ),  # True
            models.WorkflowCondition(
                file_exists='repository://requirements.txt'
            ),  # True
        ]

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, conditions
        )

        self.assertTrue(result)  # All conditions pass, all() returns True

    def test_check_condition_type_all_failure(self) -> None:
        """Test condition_type 'all' with mixed conditions."""
        conditions = [
            models.WorkflowCondition(
                file_exists='repository://package.json'
            ),  # True
            models.WorkflowCondition(
                file_exists='repository://nonexistent.txt'
            ),  # False
        ]

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, conditions
        )

        self.assertFalse(result)  # One condition fails, all() returns False

    def test_check_file_pattern_exists_string_success(self) -> None:
        """Test _check_file_pattern_exists with string path."""
        resource_url = models.ResourceUrl('repository://package.json')
        file_path = self.repository_dir / 'package.json'
        result = condition_checker.ConditionChecker._check_file_pattern_exists(
            file_path, resource_url
        )
        self.assertTrue(result)

    def test_check_file_pattern_exists_string_failure(self) -> None:
        """Test _check_file_pattern_exists with non-existent string path."""
        resource_url = models.ResourceUrl('repository://nonexistent.txt')
        file_path = self.repository_dir / 'nonexistent.txt'
        result = condition_checker.ConditionChecker._check_file_pattern_exists(
            file_path, resource_url
        )
        self.assertFalse(result)

    def test_check_file_pattern_exists_regex_success(self) -> None:
        """Test _check_file_pattern_exists with glob pattern."""
        resource_url = models.ResourceUrl('repository://**/*.json')
        file_path = self.repository_dir / '**' / '*.json'
        result = condition_checker.ConditionChecker._check_file_pattern_exists(
            file_path, resource_url
        )
        self.assertTrue(result)  # Should find package.json

    def test_check_file_pattern_exists_regex_failure(self) -> None:
        """Test _check_file_pattern_exists with non-matching glob pattern."""
        resource_url = models.ResourceUrl('repository://**/*.go')
        file_path = self.repository_dir / '**' / '*.go'
        result = condition_checker.ConditionChecker._check_file_pattern_exists(
            file_path, resource_url
        )
        self.assertFalse(result)  # No .go files

    def test_check_file_pattern_exists_invalid_regex(self) -> None:
        """Test _check_file_pattern_exists with file that doesn't exist."""
        # Test with a filename that doesn't exist (no special handling needed)
        resource_url = models.ResourceUrl('repository://nonexistent')
        file_path = self.repository_dir / 'nonexistent'
        result = condition_checker.ConditionChecker._check_file_pattern_exists(
            file_path, resource_url
        )
        self.assertFalse(result)  # File doesn't exist

    @mock.patch('imbi_automations.clients.GitHub.get_instance')
    async def test_check_remote_no_conditions(
        self, mock_github: mock.MagicMock
    ) -> None:
        """Test check_remote method with no conditions."""
        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, []
        )
        self.assertTrue(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_exists_success(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_exists condition with existing file."""
        mock_get_file.return_value = 'file content'

        condition = models.WorkflowCondition(remote_file_exists='package.json')

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_exists_failure(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_exists condition with non-existent file."""
        mock_get_file.return_value = None

        condition = models.WorkflowCondition(
            remote_file_exists='nonexistent.txt'
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_not_exists_success(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_not_exists condition with non-existent file."""
        mock_get_file.return_value = None

        condition = models.WorkflowCondition(
            remote_file_not_exists='nonexistent.txt'
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_not_exists_failure(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_not_exists condition with existing file."""
        mock_get_file.return_value = 'file content'

        condition = models.WorkflowCondition(
            remote_file_not_exists='package.json'
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_contains_success(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_contains condition with matching content."""
        mock_get_file.return_value = '{"name": "test-project"}'

        condition = models.WorkflowCondition(
            remote_file_contains='test-project',
            remote_file=pathlib.Path('package.json'),
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_contains_failure(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_contains condition with non-matching content."""
        mock_get_file.return_value = '{"name": "other-project"}'

        condition = models.WorkflowCondition(
            remote_file_contains='test-project',
            remote_file=pathlib.Path('package.json'),
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_contains_regex_success(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_contains with regex pattern that matches."""
        mock_get_file.return_value = 'FROM python:3.9-slim'

        condition = models.WorkflowCondition(
            remote_file_contains=r'python:[3-4]\.\d+',
            remote_file=pathlib.Path('Dockerfile'),
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_contains_regex_failure(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_contains with regex pattern that doesn't match."""
        mock_get_file.return_value = 'FROM python:2.7-slim'

        condition = models.WorkflowCondition(
            remote_file_contains=r'python:[3-4]\.\d+',
            remote_file=pathlib.Path('Dockerfile'),
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_contains_invalid_regex(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_contains with invalid regex pattern."""
        mock_get_file.return_value = 'some content'

        condition = models.WorkflowCondition(
            remote_file_contains=r'[invalid(regex',
            remote_file=pathlib.Path('test.txt'),
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_doesnt_contain_regex_success(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_doesnt_contain with regex that doesn't match."""
        mock_get_file.return_value = 'FROM python:2.7-slim'

        condition = models.WorkflowCondition(
            remote_file_doesnt_contain=r'python:[3-4]\.\d+',
            remote_file=pathlib.Path('Dockerfile'),
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_file_doesnt_contain_regex_failure(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote_file_doesnt_contain with regex that matches."""
        mock_get_file.return_value = 'FROM python:3.9-slim'

        condition = models.WorkflowCondition(
            remote_file_doesnt_contain=r'python:[3-4]\.\d+',
            remote_file=pathlib.Path('Dockerfile'),
        )

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    @mock.patch('imbi_automations.clients.GitHub.get_file_contents')
    async def test_check_remote_condition_type_any(
        self, mock_get_file: mock.AsyncMock
    ) -> None:
        """Test remote conditions with 'any' condition type."""
        mock_get_file.side_effect = [
            None,
            'file content',
        ]  # First call: None, Second call: content

        conditions = [
            models.WorkflowCondition(
                remote_file_exists='nonexistent.txt'
            ),  # False
            models.WorkflowCondition(
                remote_file_exists='existing.txt'
            ),  # True
        ]

        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.any, conditions
        )

        self.assertTrue(result)  # One condition passes

    async def test_check_remote_client_github_missing(self) -> None:
        """Test _check_remote_client with missing GitHub configuration."""
        # Create checker without GitHub config
        config_no_github = models.Configuration(
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.test.com'
            )
        )
        checker_no_github = condition_checker.ConditionChecker(
            config_no_github, verbose=True
        )

        condition = models.WorkflowCondition(
            remote_file_exists='test.txt',
            remote_client=models.WorkflowConditionRemoteClient.github,
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await checker_no_github._check_remote_client(condition)

        self.assertIn('GitHub is not configured', str(exc_context.exception))

    def test_check_file_contains_helper_success(self) -> None:
        """Test _check_file_contains helper method."""
        condition = models.WorkflowCondition(
            file_contains='test-project', file='repository://package.json'
        )
        file_path = self.repository_dir / 'package.json'

        result = self.checker._check_file_contains(file_path, condition)

        self.assertTrue(result)

    def test_check_file_contains_helper_failure(self) -> None:
        """Test _check_file_contains helper with non-matching content."""
        condition = models.WorkflowCondition(
            file_contains='nonexistent', file='repository://package.json'
        )
        file_path = self.repository_dir / 'package.json'

        result = self.checker._check_file_contains(file_path, condition)

        self.assertFalse(result)

    def test_check_file_contains_helper_missing_file(self) -> None:
        """Test _check_file_contains helper method with missing file."""
        condition = models.WorkflowCondition(
            file_contains='test', file='repository://missing.txt'
        )
        file_path = self.repository_dir / 'missing.txt'

        result = self.checker._check_file_contains(file_path, condition)

        self.assertFalse(result)

    def test_check_file_contains_helper_read_error(self) -> None:
        """Test _check_file_contains helper method with file read error."""
        # Create a directory instead of file to cause read error
        (self.repository_dir / 'directory_not_file').mkdir()

        condition = models.WorkflowCondition(
            file_contains='test', file='repository://directory_not_file'
        )
        file_path = self.repository_dir / 'directory_not_file'

        result = self.checker._check_file_contains(file_path, condition)

        self.assertFalse(result)

    def test_check_file_contains_regex_success(self) -> None:
        """Test file_contains with regex pattern that matches."""
        condition = models.WorkflowCondition(
            file_contains=r'fastapi==0\.\d+\.\d+',
            file='repository://requirements.txt',
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_check_file_contains_regex_failure(self) -> None:
        """Test file_contains with regex pattern that doesn't match."""
        condition = models.WorkflowCondition(
            file_contains=r'django==\d+\.\d+\.\d+',
            file='repository://requirements.txt',
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_check_file_contains_invalid_regex(self) -> None:
        """Test file_contains with invalid regex pattern."""
        condition = models.WorkflowCondition(
            file_contains=r'[invalid(regex',
            file='repository://requirements.txt',
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_check_file_doesnt_contain_regex_success(self) -> None:
        """Test file_doesnt_contain with regex that doesn't match."""
        condition = models.WorkflowCondition(
            file_doesnt_contain=r'django==\d+\.\d+\.\d+',
            file='repository://requirements.txt',
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_check_file_doesnt_contain_regex_failure(self) -> None:
        """Test file_doesnt_contain with regex that matches."""
        condition = models.WorkflowCondition(
            file_doesnt_contain=r'fastapi==0\.\d+\.\d+',
            file='repository://requirements.txt',
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_when_true_literal(self) -> None:
        """Test when condition with True literal."""
        condition = models.WorkflowCondition(when='{{ True }}')

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_when_false_literal(self) -> None:
        """Test when condition with False literal."""
        condition = models.WorkflowCondition(when='{{ False }}')

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_when_truthy_string_yes(self) -> None:
        """Test when condition with 'yes' as truthy."""
        condition = models.WorkflowCondition(when="{{ 'yes' }}")

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_when_falsy_string_no(self) -> None:
        """Test when condition with 'no' as falsy."""
        condition = models.WorkflowCondition(when="{{ 'no' }}")

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_when_empty_string_falsy(self) -> None:
        """Test when condition with empty string as falsy."""
        condition = models.WorkflowCondition(when="{{ '' }}")

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_when_falsy_zero(self) -> None:
        """Test when condition with '0' as falsy."""
        condition = models.WorkflowCondition(when='{{ 0 }}')

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_when_truthy_one(self) -> None:
        """Test when condition with '1' as truthy."""
        condition = models.WorkflowCondition(when='{{ 1 }}')

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_when_none_falsy(self) -> None:
        """Test when condition with 'none' as falsy."""
        condition = models.WorkflowCondition(when="{{ 'none' }}")

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_when_compare_semver_is_older(self) -> None:
        """Test when condition with compare_semver() returning is_older."""
        condition = models.WorkflowCondition(
            when="{{ compare_semver('18.2.0', '19.0.0').is_older }}"
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_when_compare_semver_is_newer(self) -> None:
        """Test when condition with compare_semver() returning is_newer."""
        condition = models.WorkflowCondition(
            when="{{ compare_semver('20.0.0', '19.0.0').is_newer }}"
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_when_compare_semver_is_equal(self) -> None:
        """Test when condition with compare_semver() returning is_equal."""
        condition = models.WorkflowCondition(
            when="{{ compare_semver('19.0.0', '19.0.0').is_equal }}"
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_when_compare_semver_not_older(self) -> None:
        """Test when condition with negated compare_semver()."""
        condition = models.WorkflowCondition(
            when="{{ not compare_semver('20.0.0', '19.0.0').is_older }}"
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    def test_when_get_component_version_package_json(self) -> None:
        """Test when with get_component_version() from package.json."""
        # Create a package.json with react dependency
        (self.repository_dir / 'package.json').write_text(
            '{"dependencies": {"react": "^18.2.0"}}'
        )

        condition = models.WorkflowCondition(
            when=(
                '{{ compare_semver('
                "get_component_version('repository:///package.json', "
                "'react'), '19.0.0').is_older }}"
            )
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)  # 18.2.0 is older than 19.0.0

    def test_when_get_component_version_pyproject(self) -> None:
        """Test when with get_component_version() from pyproject.toml."""
        (self.repository_dir / 'pyproject.toml').write_text(
            '[project]\ndependencies = ["pydantic>=2.5.0"]'
        )

        condition = models.WorkflowCondition(
            when=(
                '{{ compare_semver('
                'get_component_version('
                "'repository:///pyproject.toml', 'pydantic'), "
                "'2.0.0').is_newer }}"
            )
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)  # 2.5.0 is newer than 2.0.0

    def test_when_template_error_returns_false(self) -> None:
        """Test when condition gracefully handles template errors."""
        # Undefined variable should cause error and return False
        condition = models.WorkflowCondition(when='{{ undefined_variable }}')

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertFalse(result)

    def test_when_with_context_variable(self) -> None:
        """Test when condition using workflow context variables."""
        condition = models.WorkflowCondition(
            when="{{ workflow.configuration.name == 'test-workflow' }}"
        )

        result = self.checker.check(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        self.assertTrue(result)

    async def test_when_skipped_in_remote(self) -> None:
        """Test that when conditions are skipped in remote checks."""
        condition = models.WorkflowCondition(when='{{ True }}')

        # When conditions should be skipped in remote check
        result = await self.checker.check_remote(
            self.context, models.WorkflowConditionType.all, [condition]
        )

        # Returns True because no remote conditions checked
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
