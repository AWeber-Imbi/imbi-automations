"""Tests for the utils module."""

import pathlib
import tempfile
import textwrap
import unittest
import uuid

from imbi_automations import models, utils


class UtilsTestCase(unittest.TestCase):
    """Test cases for utils module functions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = pathlib.Path(self.temp_dir.name)

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
            working_directory=self.temp_path,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_temporary_file(
        self, content: str, filename: str | None = None
    ) -> pathlib.Path:
        """Write content to a temporary file and return its path.

        Args:
            content: The content to write to the file
            filename: Optional filename (defaults to random UUID)

        Returns:
            Path to the created temporary file
        """
        file_name = filename or str(uuid.uuid4())
        file_path = self.temp_path / file_name
        file_path.write_text(textwrap.dedent(content).lstrip('\n'))
        return file_path

    def test_extract_image_from_dockerfile_simple(self) -> None:
        """Test extracting simple Docker image from Dockerfile."""
        self.write_temporary_file(
            """
            FROM python:3.12
            RUN pip install requirements.txt
            COPY . /app
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        self.assertEqual(result, 'python:3.12')

    def test_extract_image_from_dockerfile_with_tag(self) -> None:
        """Test extracting Docker image with tag."""
        self.write_temporary_file(
            """
            FROM ubuntu:20.04
            ENV DEBIAN_FRONTEND=noninteractive
            RUN apt-get update
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        self.assertEqual(result, 'ubuntu:20.04')

    def test_extract_image_from_dockerfile_multi_stage(self) -> None:
        """Test extracting Docker image from multi-stage build."""
        self.write_temporary_file(
            """
            FROM node:18 AS builder
            WORKDIR /build
            COPY package.json .

            FROM nginx:alpine AS runtime
            COPY --from=builder /build/dist /usr/share/nginx/html
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        # Should return the first FROM instruction
        self.assertEqual(result, 'node:18')

    def test_extract_image_from_dockerfile_with_comments(self) -> None:
        """Test extracting Docker image with inline comments."""
        self.write_temporary_file(
            """
            # Base image for Python application
            FROM python:3.11-slim  # Using slim variant for smaller size
            LABEL maintainer="test@example.com"
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        self.assertEqual(result, 'python:3.11-slim')

    def test_extract_image_from_dockerfile_case_insensitive(self) -> None:
        """Test extracting Docker image with different case."""
        self.write_temporary_file(
            """
            from alpine:latest
            run apk add --no-cache python3
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        self.assertEqual(result, 'alpine:latest')

    def test_extract_image_from_dockerfile_with_registry(self) -> None:
        """Test extracting Docker image with custom registry."""
        self.write_temporary_file(
            """
            FROM registry.example.com/myorg/python:3.12
            WORKDIR /app
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        self.assertEqual(result, 'registry.example.com/myorg/python:3.12')

    def test_extract_image_from_dockerfile_no_from_instruction(self) -> None:
        """Test extracting Docker image from file without FROM instruction."""
        self.write_temporary_file(
            """
            # This is not a valid Dockerfile
            RUN echo "hello"
            COPY . /app
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        self.assertEqual(result, 'ERROR: FROM not found')

    def test_extract_image_from_dockerfile_empty_file(self) -> None:
        """Test extracting Docker image from empty file."""
        self.write_temporary_file('', filename='Dockerfile')

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        self.assertEqual(result, 'ERROR: FROM not found')

    def test_extract_image_from_dockerfile_comments_only(self) -> None:
        """Test extracting Docker image from file with only comments."""
        self.write_temporary_file(
            """
            # This is a comment
            # FROM python:3.12 (commented out)
            # Another comment
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        self.assertEqual(result, 'ERROR: FROM not found')

    def test_extract_image_from_dockerfile_file_not_found(self) -> None:
        """Test extracting Docker image from non-existent file."""
        # Test with non-existent file
        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('nonexistent')
        )

        self.assertEqual(result, 'ERROR: file_not_found')

    def test_extract_image_from_dockerfile_malformed_from(self) -> None:
        """Test extracting Docker image from malformed FROM instruction."""
        self.write_temporary_file(
            """
            FROM
            RUN echo "hello"
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        self.assertEqual(result, 'ERROR: FROM not found')

    def test_extract_image_from_dockerfile_from_with_build_args(self) -> None:
        """Test extracting Docker image with build args in FROM."""
        self.write_temporary_file(
            """
            ARG BASE_IMAGE=python:3.12
            FROM ${BASE_IMAGE}
            WORKDIR /app
            """,
            filename='Dockerfile',
        )

        result = utils.extract_image_from_dockerfile(
            self.context, pathlib.Path('Dockerfile')
        )

        # Should extract the variable reference
        self.assertEqual(result, '${BASE_IMAGE}')

    def test_extract_image_from_dockerfile_with_resource_url(self) -> None:
        """Test extracting Docker image using ResourceUrl scheme."""
        # Create in repository subdirectory
        repo_dir = self.temp_path / 'repository'
        repo_dir.mkdir()
        dockerfile_path = repo_dir / 'Dockerfile'
        dockerfile_path.write_text(
            textwrap.dedent(
                """
                FROM alpine:3.18
                RUN apk add --no-cache python3
                """
            ).lstrip('\n')
        )

        result = utils.extract_image_from_dockerfile(
            self.context, models.ResourceUrl('repository:///Dockerfile')
        )

        self.assertEqual(result, 'alpine:3.18')

    def test_extract_image_from_dockerfile_with_string_path(self) -> None:
        """Test extracting Docker image with string path (not Path object)."""
        self.write_temporary_file(
            """
            FROM node:18-alpine
            WORKDIR /usr/src/app
            """,
            filename='Dockerfile.node',
        )

        # Pass as string instead of Path object
        result = utils.extract_image_from_dockerfile(
            self.context, 'Dockerfile.node'
        )

        self.assertEqual(result, 'node:18-alpine')

    def test_extract_image_from_dockerfile_with_path_object(self) -> None:
        """Test extracting Docker image with Path object."""
        dockerfile_path = self.write_temporary_file(
            """
            FROM redis:7-alpine
            EXPOSE 6379
            """,
            filename='Dockerfile.redis',
        )

        # Pass as absolute Path object
        result = utils.extract_image_from_dockerfile(
            self.context, dockerfile_path
        )

        self.assertEqual(result, 'redis:7-alpine')

    def test_compare_semver_with_build_numbers_build_upgrade(self) -> None:
        """Test comparing versions with different build numbers."""
        result = utils.compare_semver_with_build_numbers(
            '3.9.18-0', '3.9.18-4'
        )
        self.assertTrue(result)

    def test_compare_semver_with_build_numbers_semver_upgrade(self) -> None:
        """Test comparing versions with different semantic versions."""
        result = utils.compare_semver_with_build_numbers(
            '3.9.17-4', '3.9.18-0'
        )
        self.assertTrue(result)

    def test_compare_semver_with_build_numbers_no_upgrade(self) -> None:
        """Test comparing when current is newer."""
        result = utils.compare_semver_with_build_numbers(
            '3.9.18-4', '3.9.18-0'
        )
        self.assertFalse(result)

    def test_compare_semver_with_build_numbers_equal(self) -> None:
        """Test comparing equal versions."""
        result = utils.compare_semver_with_build_numbers(
            '3.9.18-4', '3.9.18-4'
        )
        self.assertFalse(result)

    def test_compare_semver_with_build_numbers_no_build(self) -> None:
        """Test comparing versions without build numbers."""
        result = utils.compare_semver_with_build_numbers('3.9.17', '3.9.18')
        self.assertTrue(result)

    def test_compare_semver_with_build_numbers_mixed(self) -> None:
        """Test comparing with one build number and one without."""
        result = utils.compare_semver_with_build_numbers('3.9.18', '3.9.18-1')
        self.assertTrue(result)

    def test_compare_semver_with_build_numbers_non_numeric_build(self) -> None:
        """Test comparing with non-numeric build identifiers."""
        result = utils.compare_semver_with_build_numbers(
            '3.9.18-alpha', '3.9.18-beta'
        )
        self.assertFalse(result)  # Both treated as 0

    def test_append_file_success(self) -> None:
        """Test appending content to a file successfully."""
        file_path = self.temp_path / 'test.txt'
        file_path.write_text('initial content\n')

        result = utils.append_file(str(file_path), 'appended content\n')

        self.assertEqual(result, 'success')
        self.assertEqual(
            file_path.read_text(), 'initial content\nappended content\n'
        )

    def test_append_file_new_file(self) -> None:
        """Test appending to a non-existent file creates it."""
        file_path = self.temp_path / 'new_file.txt'

        result = utils.append_file(str(file_path), 'new content\n')

        self.assertEqual(result, 'success')
        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.read_text(), 'new content\n')

    def test_append_file_creates_parent_directory(self) -> None:
        """Test appending to a file creates parent directories."""
        file_path = self.temp_path / 'subdir' / 'test.txt'

        result = utils.append_file(str(file_path), 'content\n')

        self.assertEqual(result, 'success')
        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.read_text(), 'content\n')

    def test_resolve_path_repository_scheme(self) -> None:
        """Test resolving path with repository:// scheme."""
        result = utils.resolve_path(
            self.context, models.ResourceUrl('repository:///file.txt')
        )
        expected = self.temp_path / 'repository' / 'file.txt'
        self.assertEqual(result, expected)

    def test_resolve_path_workflow_scheme(self) -> None:
        """Test resolving path with workflow:// scheme."""
        result = utils.resolve_path(
            self.context, models.ResourceUrl('workflow:///template.j2')
        )
        expected = self.temp_path / 'workflow' / 'template.j2'
        self.assertEqual(result, expected)

    def test_resolve_path_extracted_scheme(self) -> None:
        """Test resolving path with extracted:// scheme."""
        result = utils.resolve_path(
            self.context, models.ResourceUrl('extracted:///data.json')
        )
        expected = self.temp_path / 'extracted' / 'data.json'
        self.assertEqual(result, expected)

    def test_resolve_path_file_scheme(self) -> None:
        """Test resolving path with file:// scheme."""
        result = utils.resolve_path(
            self.context, models.ResourceUrl('file:///local.txt')
        )
        expected = self.temp_path / 'local.txt'
        self.assertEqual(result, expected)

    def test_resolve_path_no_scheme(self) -> None:
        """Test resolving path without scheme (requires file:// prefix)."""
        result = utils.resolve_path(
            self.context, models.ResourceUrl('file:///plain.txt')
        )
        expected = self.temp_path / 'plain.txt'
        self.assertEqual(result, expected)

    def test_resolve_path_with_subdirectories(self) -> None:
        """Test resolving path with subdirectories."""
        result = utils.resolve_path(
            self.context,
            models.ResourceUrl('repository:///src/module/file.py'),
        )
        expected = self.temp_path / 'repository' / 'src' / 'module' / 'file.py'
        self.assertEqual(result, expected)

    def test_resolve_path_none_raises(self) -> None:
        """Test that None path raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            utils.resolve_path(self.context, None)
        self.assertIn('Path cannot be None', str(ctx.exception))

    def test_resolve_path_invalid_scheme_raises(self) -> None:
        """Test that invalid scheme raises RuntimeError."""
        with self.assertRaises(RuntimeError) as ctx:
            utils.resolve_path(
                self.context, models.ResourceUrl('invalid:///file.txt')
            )
        self.assertIn('Invalid path scheme', str(ctx.exception))

    def test_resolve_path_default_scheme(self) -> None:
        """Test resolving path with default_scheme parameter."""
        # Test with no scheme but default_scheme='repository'
        result = utils.resolve_path(
            self.context, 'config.yaml', default_scheme='repository'
        )
        expected = self.temp_path / 'repository' / 'config.yaml'
        self.assertEqual(result, expected)

    def test_resolve_path_default_scheme_file(self) -> None:
        """Test resolving path with default_scheme='file'."""
        result = utils.resolve_path(
            self.context, 'data.json', default_scheme='file'
        )
        expected = self.temp_path / 'data.json'
        self.assertEqual(result, expected)

    def test_sanitize_url_with_password(self) -> None:
        """Test sanitizing URL with password."""
        url = 'https://user:secret123@example.com/path'
        result = utils.sanitize(url)
        self.assertEqual(result, 'https://user:******@example.com/path')

    def test_sanitize_url_without_password(self) -> None:
        """Test sanitizing URL without password."""
        url = 'https://example.com/path'
        result = utils.sanitize(url)
        self.assertEqual(result, 'https://example.com/path')

    def test_sanitize_multiple_urls(self) -> None:
        """Test sanitizing text with multiple URLs."""
        text = 'Connect to https://user:pass@host1.com and ftp://admin:secret@host2.com'
        result = utils.sanitize(text)
        expected = 'Connect to https://user:******@host1.com and ftp://admin:******@host2.com'
        self.assertEqual(result, expected)

    def test_extract_json_plain_json(self) -> None:
        """Test extracting plain JSON."""
        response = '{"result": "success", "message": "Done"}'
        result = utils.extract_json(response)
        self.assertEqual(result, {'result': 'success', 'message': 'Done'})

    def test_extract_json_with_json_code_block(self) -> None:
        """Test extracting JSON from ```json code block."""
        response = """Here is the result:
```json
{"result": "success", "data": [1, 2, 3]}
```
That's all!"""
        result = utils.extract_json(response)
        self.assertEqual(result, {'result': 'success', 'data': [1, 2, 3]})

    def test_extract_json_with_generic_code_block(self) -> None:
        """Test extracting JSON from generic ``` code block."""
        response = """Response:
```
{"status": "ok"}
```"""
        result = utils.extract_json(response)
        self.assertEqual(result, {'status': 'ok'})

    def test_extract_json_embedded_in_text(self) -> None:
        """Test extracting JSON embedded in text."""
        response = 'The result is {"value": 42} and that is final.'
        result = utils.extract_json(response)
        self.assertEqual(result, {'value': 42})

    def test_extract_json_nested_objects(self) -> None:
        """Test extracting nested JSON objects."""
        response = 'Here: {"outer": {"inner": "value"}} end'
        result = utils.extract_json(response)
        self.assertEqual(result, {'outer': {'inner': 'value'}})

    def test_extract_json_invalid_raises(self) -> None:
        """Test that invalid JSON raises ValueError."""
        response = 'This has no JSON at all'
        with self.assertRaises(ValueError) as ctx:
            utils.extract_json(response)
        self.assertIn('No valid JSON found', str(ctx.exception))

    def test_path_to_resource_url_repository(self) -> None:
        """Test converting repository path to resource URL."""
        path = self.temp_path / 'repository' / 'src' / 'main.py'
        result = utils.path_to_resource_url(self.context, path)
        self.assertEqual(
            result, models.ResourceUrl('repository:///src/main.py')
        )

    def test_path_to_resource_url_workflow(self) -> None:
        """Test converting workflow path to resource URL."""
        path = self.temp_path / 'workflow' / 'template.j2'
        result = utils.path_to_resource_url(self.context, path)
        self.assertEqual(result, models.ResourceUrl('workflow:///template.j2'))

    def test_path_to_resource_url_extracted(self) -> None:
        """Test converting extracted path to resource URL."""
        path = self.temp_path / 'extracted' / 'data.json'
        result = utils.path_to_resource_url(self.context, path)
        self.assertEqual(result, models.ResourceUrl('extracted:///data.json'))

    def test_path_to_resource_url_file(self) -> None:
        """Test converting file path to resource URL."""
        path = self.temp_path / 'other.txt'
        result = utils.path_to_resource_url(self.context, path)
        self.assertEqual(result, models.ResourceUrl('file:///other.txt'))

    def test_path_to_resource_url_from_string(self) -> None:
        """Test converting string path to resource URL."""
        path_str = str(self.temp_path / 'repository' / 'file.py')
        result = utils.path_to_resource_url(self.context, path_str)
        self.assertEqual(result, models.ResourceUrl('repository:///file.py'))

    def test_python_init_file_path_hatch(self) -> None:
        """Test finding __init__.py with Hatch configuration."""
        # Create pyproject.toml with Hatch config
        repo_path = self.temp_path / 'repository'
        repo_path.mkdir()
        pyproject_path = repo_path / 'pyproject.toml'
        pyproject_content = """
[tool.hatch.build.targets.wheel]
packages = ["mypackage"]
"""
        pyproject_path.write_text(pyproject_content)

        result = utils.python_init_file_path(self.context)

        self.assertEqual(
            result, models.ResourceUrl('repository:///mypackage/__init__.py')
        )

    def test_python_init_file_path_poetry(self) -> None:
        """Test finding __init__.py with Poetry configuration."""
        # Create pyproject.toml with Poetry config
        repo_path = self.temp_path / 'repository'
        repo_path.mkdir()
        pyproject_path = repo_path / 'pyproject.toml'
        pyproject_content = """
[tool.poetry]
packages = [{include = "my_lib"}]
"""
        pyproject_path.write_text(pyproject_content)

        result = utils.python_init_file_path(self.context)

        self.assertEqual(
            result, models.ResourceUrl('repository:///my_lib/__init__.py')
        )

    def test_python_init_file_path_setuptools(self) -> None:
        """Test finding __init__.py with Setuptools configuration."""
        # Create pyproject.toml with Setuptools config
        repo_path = self.temp_path / 'repository'
        repo_path.mkdir()
        pyproject_path = repo_path / 'pyproject.toml'
        pyproject_content = """
[tool.setuptools]
packages = ["my.package"]
"""
        pyproject_path.write_text(pyproject_content)

        result = utils.python_init_file_path(self.context)

        self.assertEqual(
            result, models.ResourceUrl('repository:///my/package/__init__.py')
        )

    def test_python_init_file_path_fallback_src(self) -> None:
        """Test fallback finding __init__.py in src/ directory."""
        # Create __init__.py in src/mypackage/
        repo_path = self.temp_path / 'repository'
        src_path = repo_path / 'src' / 'mypackage'
        src_path.mkdir(parents=True)
        (src_path / '__init__.py').write_text('')

        result = utils.python_init_file_path(self.context)

        self.assertEqual(
            result,
            models.ResourceUrl('repository:///src/mypackage/__init__.py'),
        )

    def test_python_init_file_path_fallback_root(self) -> None:
        """Test fallback finding __init__.py in root directory."""
        # Create __init__.py in mypackage/ (no src/)
        repo_path = self.temp_path / 'repository'
        pkg_path = repo_path / 'mypackage'
        pkg_path.mkdir(parents=True)
        (pkg_path / '__init__.py').write_text('')

        result = utils.python_init_file_path(self.context)

        self.assertEqual(
            result, models.ResourceUrl('repository:///mypackage/__init__.py')
        )

    def test_python_init_file_path_no_init_raises(self) -> None:
        """Test that missing __init__.py raises RuntimeError."""
        # Create empty repository directory
        repo_path = self.temp_path / 'repository'
        repo_path.mkdir()

        with self.assertRaises(RuntimeError) as ctx:
            utils.python_init_file_path(self.context)
        self.assertIn('Could not find __init__.py', str(ctx.exception))

    def test_imbi_project_hash_contract(self) -> None:
        # Two ImbiProject instances with identical content but different
        # dict key ordering should have equal hashes since they compare
        # as equal. This verifies the hash invariant: a == b implies
        # hash(a) == hash(b).
        #
        # Create two projects with same data but different dict key order
        project1 = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=None,
            facts={'language': 'Python', 'framework': 'FastAPI'},
            identifiers={'github': 'org/repo', 'jira': 'PROJ'},
            links={'docs': 'https://example.com', 'wiki': 'https://wiki.com'},
            name='test-project',
            namespace='test-namespace',
            namespace_slug='test-namespace',
            project_score=None,
            project_type='API',
            project_type_slug='api',
            slug='test-project',
            urls={
                'prod': 'https://prod.com',
                'staging': 'https://staging.com',
            },
            imbi_url='https://imbi.example.com/projects/123',
        )

        # Same data, but dict keys in different order
        project2 = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=None,
            facts={'framework': 'FastAPI', 'language': 'Python'},
            identifiers={'jira': 'PROJ', 'github': 'org/repo'},
            links={'wiki': 'https://wiki.com', 'docs': 'https://example.com'},
            name='test-project',
            namespace='test-namespace',
            namespace_slug='test-namespace',
            project_score=None,
            project_type='API',
            project_type_slug='api',
            slug='test-project',
            urls={
                'staging': 'https://staging.com',
                'prod': 'https://prod.com',
            },
            imbi_url='https://imbi.example.com/projects/123',
        )

        # Verify equality works correctly (should be True)
        self.assertEqual(
            project1, project2, 'Projects with same data should be equal'
        )

        # Hash contract: a == b must imply hash(a) == hash(b)
        self.assertEqual(
            hash(project1),
            hash(project2),
            'Equal projects must have equal hashes (hash invariant)',
        )


if __name__ == '__main__':
    unittest.main()
