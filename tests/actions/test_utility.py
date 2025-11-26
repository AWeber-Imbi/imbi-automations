"""Tests for utility actions module."""

import pathlib
import tempfile
import unittest

from imbi_automations import models
from imbi_automations.actions import utility
from tests import base


class CompareSemverTestCase(base.AsyncTestCase):
    """Test cases for compare_semver utility action."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

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
                facts={'Python Version': '3.9.18'},
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
            current_action_index=1,
            total_actions=1,
        )

        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(api_key='test-key'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.utility_executor = utility.UtilityActions(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_compare_semver_with_positional_args(self) -> None:
        """Test compare_semver with positional arguments."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['1.2.3', '2.0.0'],
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        self.assertEqual(result['current_version'], '1.2.3')
        self.assertEqual(result['target_version'], '2.0.0')
        self.assertEqual(result['comparison'], -1)
        self.assertTrue(result['is_older'])
        self.assertFalse(result['is_equal'])
        self.assertFalse(result['is_newer'])

    async def test_compare_semver_with_kwargs(self) -> None:
        """Test compare_semver with keyword arguments."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            kwargs={'current_version': '2.0.0', 'target_version': '1.5.0'},
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        self.assertTrue(result['is_newer'])
        self.assertFalse(result['is_older'])
        self.assertFalse(result['is_equal'])
        self.assertEqual(result['comparison'], 1)

    async def test_compare_semver_equal_versions(self) -> None:
        """Test compare_semver with equal versions."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['3.0.0', '3.0.0'],
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        self.assertTrue(result['is_equal'])
        self.assertFalse(result['is_older'])
        self.assertFalse(result['is_newer'])
        self.assertEqual(result['comparison'], 0)

    async def test_compare_semver_with_build_numbers(self) -> None:
        """Test compare_semver with build numbers."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['3.9.18-0', '3.9.18-4'],
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        self.assertTrue(result['is_older'])
        self.assertEqual(result['current_build'], 0)
        self.assertEqual(result['target_build'], 4)

    async def test_compare_semver_build_numbers_newer(self) -> None:
        """Test compare_semver where current build is newer."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['3.9.18-5', '3.9.18-2'],
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        self.assertTrue(result['is_newer'])
        self.assertEqual(result['comparison'], 1)

    async def test_compare_semver_mixed_build_formats(self) -> None:
        """Test compare_semver with mixed build number formats."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['3.9.17-4', '3.9.18'],
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        self.assertTrue(result['is_older'])
        self.assertEqual(result['current_build'], 4)
        self.assertIsNone(result['target_build'])

    async def test_compare_semver_custom_output_name(self) -> None:
        """Test compare_semver with custom output variable name."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['1.0.0', '2.0.0'],
            kwargs={'output': 'version_check'},
        )

        await self.utility_executor.execute(action)

        self.assertIn('version_check', self.context.variables)
        self.assertNotIn('semver_result', self.context.variables)
        result = self.context.variables['version_check']
        self.assertTrue(result['is_older'])

    async def test_compare_semver_parsed_components(self) -> None:
        """Test that version components are correctly parsed."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['1.2.3', '4.5.6'],
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        self.assertEqual(result['current_major'], 1)
        self.assertEqual(result['current_minor'], 2)
        self.assertEqual(result['current_patch'], 3)
        self.assertEqual(result['target_major'], 4)
        self.assertEqual(result['target_minor'], 5)
        self.assertEqual(result['target_patch'], 6)

    async def test_compare_semver_with_template_args(self) -> None:
        """Test compare_semver with Jinja2 templated arguments."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            kwargs={
                'current_version': (
                    "{{ imbi_project.facts.get('Python Version') }}"
                ),
                'target_version': '3.12.0',
            },
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        self.assertEqual(result['current_version'], '3.9.18')
        self.assertEqual(result['target_version'], '3.12.0')
        self.assertTrue(result['is_older'])

    async def test_compare_semver_missing_args_raises(self) -> None:
        """Test that missing arguments raises ValueError."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['1.0.0'],  # Only one version provided
        )

        with self.assertRaises(ValueError) as exc_context:
            await self.utility_executor.execute(action)

        self.assertIn('current_version', str(exc_context.exception))
        self.assertIn('target_version', str(exc_context.exception))

    async def test_compare_semver_invalid_version_raises(self) -> None:
        """Test that invalid semver format raises ValueError."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['not-a-version', '1.0.0'],
        )

        with self.assertRaises(ValueError) as exc_context:
            await self.utility_executor.execute(action)

        self.assertIn('Invalid semver format', str(exc_context.exception))

    async def test_compare_semver_non_numeric_build(self) -> None:
        """Test that non-numeric build identifiers are treated as None."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['3.9.18-alpha', '3.9.18-beta'],
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        # Non-numeric builds are treated as None (equal for comparison)
        self.assertIsNone(result['current_build'])
        self.assertIsNone(result['target_build'])
        self.assertTrue(result['is_equal'])

    async def test_compare_semver_result_is_dict(self) -> None:
        """Test that result stored in variables is a dict (serializable)."""
        action = models.WorkflowUtilityAction(
            name='test-compare',
            type='utility',
            command=models.WorkflowUtilityCommands.compare_semver,
            args=['1.0.0', '2.0.0'],
        )

        await self.utility_executor.execute(action)

        result = self.context.variables['semver_result']
        self.assertIsInstance(result, dict)


class UtilityActionsUnimplementedTestCase(base.AsyncTestCase):
    """Test cases for unimplemented utility commands."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

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
            github=models.GitHubConfiguration(api_key='test-key'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.utility_executor = utility.UtilityActions(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_docker_tag_not_implemented(self) -> None:
        """Test that docker_tag raises NotImplementedError."""
        action = models.WorkflowUtilityAction(
            name='test-docker-tag',
            type='utility',
            command=models.WorkflowUtilityCommands.docker_tag,
        )

        with self.assertRaises(NotImplementedError):
            await self.utility_executor.execute(action)

    async def test_dockerfile_from_not_implemented(self) -> None:
        """Test that dockerfile_from raises NotImplementedError."""
        action = models.WorkflowUtilityAction(
            name='test-dockerfile-from',
            type='utility',
            command=models.WorkflowUtilityCommands.dockerfile_from,
        )

        with self.assertRaises(NotImplementedError):
            await self.utility_executor.execute(action)

    async def test_parse_python_constraints_not_implemented(self) -> None:
        """Test that parse_python_constraints raises NotImplementedError."""
        action = models.WorkflowUtilityAction(
            name='test-parse-constraints',
            type='utility',
            command=models.WorkflowUtilityCommands.parse_python_constraints,
        )

        with self.assertRaises(NotImplementedError):
            await self.utility_executor.execute(action)


if __name__ == '__main__':
    unittest.main()
