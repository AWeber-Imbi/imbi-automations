"""Tests for prompts module."""

import pathlib
import tempfile
import unittest

import pydantic

from imbi_automations import models, prompts


class PromptsTestBase(unittest.TestCase):
    """Base test class with shared fixtures for prompts tests."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.working_dir = pathlib.Path(self.temp_dir)
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
            working_directory=self.working_dir,
        )


class RenderPathTestCase(PromptsTestBase):
    """Tests for render_path function."""

    def test_render_path_with_string_without_templates(self) -> None:
        """Test render_path with plain string (no templates)."""
        path = 'simple/path.txt'
        result = prompts.render_path(self.context, path)
        self.assertEqual(result, 'simple/path.txt')
        self.assertIsInstance(result, str)

    def test_render_path_with_string_with_templates(self) -> None:
        """Test render_path with string containing template syntax."""
        path = 'path/{{ workflow.configuration.name }}/file.txt'
        result = prompts.render_path(self.context, path)
        self.assertEqual(result, 'path/test-workflow/file.txt')
        self.assertIsInstance(result, str)

    def test_render_path_with_anyurl_without_templates(self) -> None:
        """Test render_path with AnyUrl (no templates)."""
        path = models.ResourceUrl('repository:///simple/path.txt')
        result = prompts.render_path(self.context, path)
        self.assertEqual(result, path)
        self.assertIsInstance(result, pydantic.AnyUrl)

    def test_render_path_with_anyurl_with_templates(self) -> None:
        """Test render_path with AnyUrl containing templates."""
        path = models.ResourceUrl(
            'repository:///path/'
            '%7B%7B%20workflow.configuration.name%20%7D%7D/file.txt'
        )
        result = prompts.render_path(self.context, path)
        self.assertEqual(
            str(result), 'repository:///path/test-workflow/file.txt'
        )
        self.assertIsInstance(result, pydantic.AnyUrl)

    def test_render_path_with_invalid_type(self) -> None:
        """Test render_path raises TypeError for invalid types."""
        with self.assertRaises(TypeError) as cm:
            prompts.render_path(self.context, 123)  # type: ignore
        self.assertIn('Invalid path type', str(cm.exception))

    def test_render_path_string_with_conditional_template(self) -> None:
        """Test render_path with string containing conditional template."""
        path = (
            'path/{% if workflow.configuration.name %}'
            '{{ workflow.configuration.name }}{% endif %}'
        )
        result = prompts.render_path(self.context, path)
        self.assertEqual(result, 'path/test-workflow')

    def test_render_path_string_with_comment_template(self) -> None:
        """Test render_path with string containing comment template."""
        path = 'path/{# comment #}file.txt'
        result = prompts.render_path(self.context, path)
        self.assertEqual(result, 'path/file.txt')


class HasTemplateSyntaxTestCase(unittest.TestCase):
    """Tests for has_template_syntax function."""

    def test_has_template_syntax_with_variable(self) -> None:
        """Test detection of variable syntax."""
        self.assertTrue(prompts.has_template_syntax('{{ variable }}'))

    def test_has_template_syntax_with_control_structure(self) -> None:
        """Test detection of control structure syntax."""
        self.assertTrue(prompts.has_template_syntax('{% if condition %}'))

    def test_has_template_syntax_with_comment(self) -> None:
        """Test detection of comment syntax."""
        self.assertTrue(prompts.has_template_syntax('{# comment #}'))

    def test_has_template_syntax_without_templates(self) -> None:
        """Test no false positives on plain text."""
        self.assertFalse(prompts.has_template_syntax('plain text'))

    def test_has_template_syntax_with_partial_syntax(self) -> None:
        """Test no false positives on partial syntax."""
        self.assertFalse(prompts.has_template_syntax('single { brace'))
        self.assertFalse(prompts.has_template_syntax('text with % sign'))


class RenderTestCase(PromptsTestBase):
    """Tests for render function."""

    def test_render_with_template_string(self) -> None:
        """Test render with template string."""
        result = prompts.render(
            self.context, template='Hello {{ workflow.configuration.name }}'
        )
        self.assertEqual(result, 'Hello test-workflow')

    def test_render_with_source_path(self) -> None:
        """Test render with source path."""
        template_file = self.working_dir / 'template.txt'
        template_file.write_text(
            'Name: {{ workflow.configuration.name }}', encoding='utf-8'
        )
        result = prompts.render(self.context, source=template_file)
        self.assertEqual(result, 'Name: test-workflow')

    def test_render_without_source_or_template_raises(self) -> None:
        """Test render raises ValueError without source or template."""
        with self.assertRaises(ValueError) as cm:
            prompts.render(self.context)
        self.assertIn('source or template is required', str(cm.exception))

    def test_render_with_both_source_and_template_raises(self) -> None:
        """Test render raises ValueError with both source and template."""
        with self.assertRaises(ValueError) as cm:
            prompts.render(
                self.context, source='path', template='{{ variable }}'
            )
        self.assertIn(
            'You can not specify both source and template', str(cm.exception)
        )

    def test_render_with_kwargs(self) -> None:
        """Test render with additional kwargs."""
        result = prompts.render(
            self.context,
            template='{{ custom_var }}',
            custom_var='custom_value',
        )
        self.assertEqual(result, 'custom_value')

    def test_render_without_context(self) -> None:
        """Test render without context."""
        result = prompts.render(template='Static template')
        self.assertEqual(result, 'Static template')

    def test_render_with_anyurl_source(self) -> None:
        """Test render with AnyUrl source."""
        # Create a template file
        template_file = self.working_dir / 'template.txt'
        template_file.write_text(
            'URL: {{ workflow.configuration.name }}', encoding='utf-8'
        )

        # Create ResourceUrl pointing to the template (use filename only)
        source_url = models.ResourceUrl(f'file:///{template_file.name}')
        result = prompts.render(self.context, source=source_url)
        self.assertEqual(result, 'URL: test-workflow')

    def test_render_with_string_source_raises_runtime_error(self) -> None:
        """Test render with string source raises RuntimeError."""
        with self.assertRaises(RuntimeError) as cm:
            prompts.render(self.context, source='invalid-string')
        self.assertIn('source is not a Path object', str(cm.exception))

    def test_render_with_extract_package_name_no_args(self) -> None:
        """Test calling extract_package_name_from_pyproject() without args."""
        # Create a pyproject.toml
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        pyproject_path = repo_dir / 'pyproject.toml'
        pyproject_path.write_text(
            '[project]\nname = "test-package"\n', encoding='utf-8'
        )
        self.context.working_directory = self.working_dir

        # Should work when called without arguments (using default path)
        result = prompts.render(
            self.context,
            template='{{ extract_package_name_from_pyproject() }}',
        )
        self.assertEqual(result, 'test-package')

    def test_render_with_extract_package_name_with_args(self) -> None:
        """Test calling extract_package_name_from_pyproject() with path arg."""
        # Create a pyproject.toml at a specific location
        custom_path = self.working_dir / 'custom' / 'pyproject.toml'
        custom_path.parent.mkdir(parents=True, exist_ok=True)
        custom_path.write_text(
            '[project]\nname = "custom-package"\n', encoding='utf-8'
        )
        self.context.working_directory = self.working_dir

        # Should work when called with a path argument
        template = (
            '{{ extract_package_name_from_pyproject('
            '"file:///custom/pyproject.toml") }}'
        )
        result = prompts.render(self.context, template=template)
        self.assertEqual(result, 'custom-package')


class RenderFileTestCase(PromptsTestBase):
    """Tests for render_file function."""

    def test_render_file(self) -> None:
        """Test render_file creates output file with rendered content."""
        source = self.working_dir / 'source.txt'
        source.write_text(
            'Hello {{ workflow.configuration.name }}', encoding='utf-8'
        )
        destination = self.working_dir / 'output.txt'

        prompts.render_file(self.context, source, destination)

        self.assertTrue(destination.exists())
        self.assertEqual(
            destination.read_text(encoding='utf-8'), 'Hello test-workflow'
        )


class CompareSemverTestCase(unittest.TestCase):
    """Tests for compare_semver template function."""

    def test_compare_semver_returns_dict(self) -> None:
        """Test compare_semver returns dict with expected keys."""
        result = prompts.compare_semver('18.2.0', '19.0.0')

        self.assertIsInstance(result, dict)
        expected_keys = {
            'current_version',
            'target_version',
            'comparison',
            'is_older',
            'is_equal',
            'is_newer',
            'current_major',
            'current_minor',
            'current_patch',
            'current_build',
            'target_major',
            'target_minor',
            'target_patch',
            'target_build',
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_compare_semver_is_older(self) -> None:
        """Test compare_semver detects older version."""
        result = prompts.compare_semver('18.2.0', '19.0.0')

        self.assertTrue(result['is_older'])
        self.assertFalse(result['is_equal'])
        self.assertFalse(result['is_newer'])
        self.assertEqual(result['comparison'], -1)

    def test_compare_semver_is_newer(self) -> None:
        """Test compare_semver detects newer version."""
        result = prompts.compare_semver('20.0.0', '19.0.0')

        self.assertFalse(result['is_older'])
        self.assertFalse(result['is_equal'])
        self.assertTrue(result['is_newer'])
        self.assertEqual(result['comparison'], 1)

    def test_compare_semver_is_equal(self) -> None:
        """Test compare_semver detects equal versions."""
        result = prompts.compare_semver('19.0.0', '19.0.0')

        self.assertFalse(result['is_older'])
        self.assertTrue(result['is_equal'])
        self.assertFalse(result['is_newer'])
        self.assertEqual(result['comparison'], 0)

    def test_compare_semver_with_build_numbers(self) -> None:
        """Test compare_semver handles build numbers (e.g., 3.9.18-4)."""
        result = prompts.compare_semver('3.9.18-3', '3.9.18-4')

        self.assertTrue(result['is_older'])
        self.assertEqual(result['current_build'], 3)
        self.assertEqual(result['target_build'], 4)

    def test_compare_semver_with_partial_versions(self) -> None:
        """Test compare_semver handles partial versions (e.g., 3.9)."""
        result = prompts.compare_semver('3.9', '3.10')

        self.assertTrue(result['is_older'])
        self.assertEqual(result['current_minor'], 9)
        self.assertEqual(result['target_minor'], 10)

    def test_compare_semver_strips_prefixes(self) -> None:
        """Test compare_semver strips version prefixes."""
        result = prompts.compare_semver('^18.2.0', '^19.0.0')

        self.assertTrue(result['is_older'])
        self.assertEqual(result['current_major'], 18)
        self.assertEqual(result['target_major'], 19)

    def test_compare_semver_v_prefix(self) -> None:
        """Test compare_semver strips v prefix."""
        result = prompts.compare_semver('v1.2.3', 'v1.2.4')

        self.assertTrue(result['is_older'])

    def test_compare_semver_extracts_components(self) -> None:
        """Test compare_semver extracts major/minor/patch correctly."""
        result = prompts.compare_semver('18.2.1', '19.3.5')

        self.assertEqual(result['current_major'], 18)
        self.assertEqual(result['current_minor'], 2)
        self.assertEqual(result['current_patch'], 1)
        self.assertEqual(result['target_major'], 19)
        self.assertEqual(result['target_minor'], 3)
        self.assertEqual(result['target_patch'], 5)


class GetComponentVersionTestCase(PromptsTestBase):
    """Tests for get_component_version template function."""

    def test_get_component_version_package_json(self) -> None:
        """Test get_component_version from package.json dependencies."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'package.json').write_text(
            '{"dependencies": {"react": "^18.2.0"}}', encoding='utf-8'
        )

        result = prompts.get_component_version(
            self.context, 'repository:///package.json', 'react'
        )

        self.assertEqual(result, '18.2.0')

    def test_get_component_version_package_json_dev_deps(self) -> None:
        """Test get_component_version from package.json devDependencies."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'package.json').write_text(
            '{"devDependencies": {"jest": "~29.7.0"}}', encoding='utf-8'
        )

        result = prompts.get_component_version(
            self.context, 'repository:///package.json', 'jest'
        )

        self.assertEqual(result, '29.7.0')

    def test_get_component_version_pyproject_pep508(self) -> None:
        """Test get_component_version from pyproject.toml PEP 508 format."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'pyproject.toml').write_text(
            '[project]\ndependencies = ["pydantic>=2.5.0"]', encoding='utf-8'
        )

        result = prompts.get_component_version(
            self.context, 'repository:///pyproject.toml', 'pydantic'
        )

        self.assertEqual(result, '2.5.0')

    def test_get_component_version_pyproject_poetry(self) -> None:
        """Test get_component_version from pyproject.toml Poetry format."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'pyproject.toml').write_text(
            '[tool.poetry.dependencies]\npython = "^3.12"\nhttpx = "^0.27.0"',
            encoding='utf-8',
        )

        result = prompts.get_component_version(
            self.context, 'repository:///pyproject.toml', 'httpx'
        )

        self.assertEqual(result, '0.27.0')

    def test_get_component_version_pyproject_optional_deps(self) -> None:
        """Test get_component_version from optional-dependencies."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'pyproject.toml').write_text(
            '[project.optional-dependencies]\ndev = ["pytest>=8.0.0"]',
            encoding='utf-8',
        )

        result = prompts.get_component_version(
            self.context, 'repository:///pyproject.toml', 'pytest'
        )

        self.assertEqual(result, '8.0.0')

    def test_get_component_version_strips_prefixes(self) -> None:
        """Test get_component_version strips version prefixes."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'package.json').write_text(
            '{"dependencies": {"lodash": ">=4.17.21"}}', encoding='utf-8'
        )

        result = prompts.get_component_version(
            self.context, 'repository:///package.json', 'lodash'
        )

        self.assertEqual(result, '4.17.21')

    def test_get_component_version_missing_raises(self) -> None:
        """Test get_component_version raises for missing component."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'package.json').write_text(
            '{"dependencies": {"react": "^18.0.0"}}', encoding='utf-8'
        )

        with self.assertRaises(ValueError) as cm:
            prompts.get_component_version(
                self.context, 'repository:///package.json', 'vue'
            )

        self.assertIn('vue', str(cm.exception))
        self.assertIn('not found', str(cm.exception))

    def test_get_component_version_unsupported_file_raises(self) -> None:
        """Test get_component_version raises for unsupported file types."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'requirements.txt').write_text(
            'pydantic>=2.5.0', encoding='utf-8'
        )

        with self.assertRaises(ValueError) as cm:
            prompts.get_component_version(
                self.context, 'repository:///requirements.txt', 'pydantic'
            )

        self.assertIn('Unsupported file type', str(cm.exception))

    def test_get_component_version_case_insensitive(self) -> None:
        """Test get_component_version is case-insensitive for pyproject."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'pyproject.toml').write_text(
            '[project]\ndependencies = ["Pydantic>=2.5.0"]', encoding='utf-8'
        )

        result = prompts.get_component_version(
            self.context, 'repository:///pyproject.toml', 'pydantic'
        )

        self.assertEqual(result, '2.5.0')


class TemplateFunctionIntegrationTestCase(PromptsTestBase):
    """Integration tests for template functions in render()."""

    def test_render_with_compare_semver(self) -> None:
        """Test render with compare_semver in template."""
        result = prompts.render(
            self.context,
            template="{{ compare_semver('18.0.0', '19.0.0').is_older }}",
        )

        self.assertEqual(result, 'True')

    def test_render_with_get_component_version(self) -> None:
        """Test render with get_component_version in template."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'package.json').write_text(
            '{"dependencies": {"react": "^18.2.0"}}', encoding='utf-8'
        )

        result = prompts.render(
            self.context,
            template=(
                '{{ get_component_version('
                "'repository:///package.json', 'react') }}"
            ),
        )

        self.assertEqual(result, '18.2.0')

    def test_render_with_combined_functions(self) -> None:
        """Test render with compare_semver and get_component_version."""
        repo_dir = self.working_dir / 'repository'
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / 'package.json').write_text(
            '{"dependencies": {"react": "^18.2.0"}}', encoding='utf-8'
        )

        result = prompts.render(
            self.context,
            template=(
                '{{ compare_semver('
                "get_component_version('repository:///package.json', "
                "'react'), '19.0.0').is_older }}"
            ),
        )

        self.assertEqual(result, 'True')
