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
            '[package]\nname = "test-package"\n', encoding='utf-8'
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
            '[package]\nname = "custom-package"\n', encoding='utf-8'
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
