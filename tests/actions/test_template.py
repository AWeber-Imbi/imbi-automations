"""Tests for the template action module."""

import pathlib
import tempfile
import unittest

from imbi_automations import models
from imbi_automations.actions import template
from tests import base


class TemplateActionsTestCase(base.AsyncTestCase):
    """Test cases for TemplateAction functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        # Create workflow and repository directories
        (self.working_directory / 'workflow').mkdir()
        (self.working_directory / 'repository').mkdir()

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
                description='Test project description',
                environments=[
                    models.ImbiEnvironment(
                        name='Development',
                        slug='development',
                        icon_class='fas fa-bug',
                    ),
                    models.ImbiEnvironment(
                        name='Production',
                        slug='production',
                        icon_class='fas fa-globe',
                    ),
                ],
                facts={'Programming Language': 'Python 3.12'},
                identifiers={'github': 'test-org/test-project'},
                links=None,
                name='Test Project',
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

        self.template_executor = template.TemplateAction(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_execute_single_file_template(self) -> None:
        """Test rendering a single file template."""
        # Create template source
        source_file = self.working_directory / 'workflow' / 'config.yml.j2'
        source_file.write_text(
            'project_name: {{ imbi_project.name }}\n'
            'slug: {{ imbi_project.slug }}\n'
        )

        action = models.WorkflowTemplateAction(
            name='render-config',
            type='template',
            source='workflow:///config.yml.j2',
            destination='repository:///config.yml',
        )

        await self.template_executor.execute(action)

        # Verify rendered output
        dest_file = self.working_directory / 'repository' / 'config.yml'
        self.assertTrue(dest_file.exists())
        content = dest_file.read_text()
        self.assertIn('project_name: Test Project', content)
        self.assertIn('slug: test-project', content)

    async def test_execute_template_with_facts(self) -> None:
        """Test template rendering with project facts."""
        source_file = self.working_directory / 'workflow' / 'pyproject.toml.j2'
        source_file.write_text(
            '[project]\n'
            'name = "{{ imbi_project.slug }}"\n'
            'requires-python = ">={{ imbi_project.facts'
            '["Programming Language"].split()[-1] }}"\n'
        )

        action = models.WorkflowTemplateAction(
            name='render-pyproject',
            type='template',
            source='workflow:///pyproject.toml.j2',
            destination='repository:///pyproject.toml',
        )

        await self.template_executor.execute(action)

        dest_file = self.working_directory / 'repository' / 'pyproject.toml'
        content = dest_file.read_text()
        self.assertIn('name = "test-project"', content)
        self.assertIn('requires-python = ">=3.12"', content)

    async def test_execute_template_with_environments(self) -> None:
        """Test template rendering with project environments."""
        source_file = self.working_directory / 'workflow' / 'deploy.yml.j2'
        source_file.write_text(
            'environments:\n'
            '{% for env in imbi_project.environments %}'
            '  - {{ env.slug }}\n'
            '{% endfor %}'
        )

        action = models.WorkflowTemplateAction(
            name='render-deploy',
            type='template',
            source='workflow:///deploy.yml.j2',
            destination='repository:///deploy.yml',
        )

        await self.template_executor.execute(action)

        dest_file = self.working_directory / 'repository' / 'deploy.yml'
        content = dest_file.read_text()
        self.assertIn('- development', content)
        self.assertIn('- production', content)

    async def test_execute_directory_template(self) -> None:
        """Test rendering a directory of templates."""
        # Create template directory structure
        template_dir = self.working_directory / 'workflow' / 'templates'
        template_dir.mkdir()
        (template_dir / 'subdir').mkdir()

        (template_dir / 'readme.md.j2').write_text(
            '# {{ imbi_project.name }}\n\n{{ imbi_project.description }}\n'
        )
        (template_dir / 'config.json.j2').write_text(
            '{"name": "{{ imbi_project.slug }}"}\n'
        )
        (template_dir / 'subdir' / 'nested.txt.j2').write_text(
            'Namespace: {{ imbi_project.namespace }}\n'
        )

        action = models.WorkflowTemplateAction(
            name='render-templates',
            type='template',
            source='workflow:///templates',
            destination='repository:///output',
        )

        await self.template_executor.execute(action)

        # Verify all files were rendered
        output_dir = self.working_directory / 'repository' / 'output'
        self.assertTrue(output_dir.exists())

        readme = output_dir / 'readme.md.j2'
        self.assertTrue(readme.exists())
        self.assertIn('# Test Project', readme.read_text())

        config = output_dir / 'config.json.j2'
        self.assertTrue(config.exists())
        self.assertIn('"name": "test-project"', config.read_text())

        nested = output_dir / 'subdir' / 'nested.txt.j2'
        self.assertTrue(nested.exists())
        self.assertIn('Namespace: test-namespace', nested.read_text())

    async def test_execute_source_not_exists(self) -> None:
        """Test error when template source doesn't exist."""
        action = models.WorkflowTemplateAction(
            name='render-missing',
            type='template',
            source='workflow:///nonexistent.j2',
            destination='repository:///output.txt',
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.template_executor.execute(action)

        self.assertIn('does not exist', str(exc_context.exception))

    async def test_execute_template_to_subdirectory(self) -> None:
        """Test rendering template to existing subdirectory."""
        # Create the parent directory (required for single file templates)
        (self.working_directory / 'repository' / 'config').mkdir(parents=True)

        source_file = self.working_directory / 'workflow' / 'template.txt.j2'
        source_file.write_text('Hello {{ imbi_project.name }}\n')

        action = models.WorkflowTemplateAction(
            name='render-to-subdir',
            type='template',
            source='workflow:///template.txt.j2',
            destination='repository:///config/output.txt',
        )

        await self.template_executor.execute(action)

        dest_file = (
            self.working_directory / 'repository' / 'config' / 'output.txt'
        )
        self.assertTrue(dest_file.exists())
        self.assertIn('Hello Test Project', dest_file.read_text())

    async def test_execute_template_with_conditionals(self) -> None:
        """Test template rendering with Jinja2 conditionals."""
        source_file = self.working_directory / 'workflow' / 'conditional.j2'
        source_file.write_text(
            '{% if imbi_project.project_type == "API" %}'
            'This is an API project\n'
            '{% else %}'
            'This is not an API project\n'
            '{% endif %}'
        )

        action = models.WorkflowTemplateAction(
            name='render-conditional',
            type='template',
            source='workflow:///conditional.j2',
            destination='repository:///result.txt',
        )

        await self.template_executor.execute(action)

        dest_file = self.working_directory / 'repository' / 'result.txt'
        content = dest_file.read_text()
        self.assertIn('This is an API project', content)
        self.assertNotIn('This is not an API', content)

    async def test_execute_template_overwrites_existing(self) -> None:
        """Test that templates overwrite existing files."""
        # Create existing file
        dest_file = self.working_directory / 'repository' / 'existing.txt'
        dest_file.write_text('Original content\n')

        source_file = self.working_directory / 'workflow' / 'new.j2'
        source_file.write_text('New content from {{ imbi_project.slug }}\n')

        action = models.WorkflowTemplateAction(
            name='render-overwrite',
            type='template',
            source='workflow:///new.j2',
            destination='repository:///existing.txt',
        )

        await self.template_executor.execute(action)

        content = dest_file.read_text()
        self.assertNotIn('Original content', content)
        self.assertIn('New content from test-project', content)

    async def test_execute_template_with_workflow_context(self) -> None:
        """Test template has access to workflow context."""
        source_file = self.working_directory / 'workflow' / 'workflow.j2'
        source_file.write_text(
            'Workflow: {{ workflow.configuration.name }}\n'
            'Working Dir: {{ working_directory }}\n'
        )

        action = models.WorkflowTemplateAction(
            name='render-workflow-context',
            type='template',
            source='workflow:///workflow.j2',
            destination='repository:///workflow-info.txt',
        )

        await self.template_executor.execute(action)

        dest_file = self.working_directory / 'repository' / 'workflow-info.txt'
        content = dest_file.read_text()
        self.assertIn('Workflow: test-workflow', content)
        self.assertIn(str(self.working_directory), content)


if __name__ == '__main__':
    unittest.main()
