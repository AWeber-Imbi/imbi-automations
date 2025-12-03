"""Comprehensive tests for the file_actions module."""

import pathlib
import re
import tempfile
import unittest

from imbi_automations import models, utils
from imbi_automations.actions import filea
from tests import base


class FileActionsTestCase(base.AsyncTestCase):
    """Test cases for FileActions functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.working_directory = pathlib.Path(self.temp_dir.name)

        # Create test directory structure
        (self.working_directory / 'src').mkdir()
        (self.working_directory / 'tests').mkdir()
        (self.working_directory / 'docs').mkdir()

        # Create test files
        (self.working_directory / 'README.md').write_text('# Test Project\n')
        (self.working_directory / 'src' / 'main.py').write_text(
            'print("hello")\n'
        )
        (self.working_directory / 'tests' / 'test_main.py').write_text(
            'def test(): pass\n'
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

        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-key'  # noqa: S106
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.file_executor = filea.FileActions(
            self.configuration, self.context, verbose=True
        )

    def tearDown(self) -> None:
        super().tearDown()
        self.temp_dir.cleanup()

    async def test_execute_append_success(self) -> None:
        """Test successful file append operation."""
        action = models.WorkflowFileAction(
            name='append-readme',
            type='file',
            command='append',
            path=pathlib.Path('README.md'),
            content='\n## New Section\nAdded content\n',
        )

        await self.file_executor.execute(action)

        # Verify content was appended
        readme_path = self.working_directory / 'README.md'
        content = readme_path.read_text()
        self.assertIn('# Test Project', content)
        self.assertIn('## New Section', content)
        self.assertIn('Added content', content)

    async def test_execute_append_new_file(self) -> None:
        """Test append to non-existent file (creates new file)."""
        action = models.WorkflowFileAction(
            name='append-new',
            type='file',
            command='append',
            path=pathlib.Path('new_file.txt'),
            content='New file content\n',
        )

        await self.file_executor.execute(action)

        # Verify new file was created
        new_file = self.working_directory / 'new_file.txt'
        self.assertTrue(new_file.exists())
        self.assertEqual(new_file.read_text(), 'New file content\n')

    async def test_execute_append_with_encoding(self) -> None:
        """Test append with custom encoding."""
        action = models.WorkflowFileAction(
            name='append-utf16',
            type='file',
            command='append',
            path=pathlib.Path('unicode.txt'),
            content='Hello 世界\n',
            encoding='utf-16',
        )

        await self.file_executor.execute(action)

        # Verify file was written with correct encoding
        unicode_file = self.working_directory / 'unicode.txt'
        content = unicode_file.read_text(encoding='utf-16')
        self.assertEqual(content, 'Hello 世界\n')

    async def test_execute_copy_file_success(self) -> None:
        """Test successful file copy operation."""
        action = models.WorkflowFileAction(
            name='copy-readme',
            type='file',
            command='copy',
            source=pathlib.Path('README.md'),
            destination=pathlib.Path('docs/README_copy.md'),
        )

        await self.file_executor.execute(action)

        # Verify file was copied
        copy_path = self.working_directory / 'docs/README_copy.md'
        self.assertTrue(copy_path.exists())
        self.assertEqual(copy_path.read_text(), '# Test Project\n')

    async def test_execute_copy_directory_success(self) -> None:
        """Test successful directory copy operation."""
        action = models.WorkflowFileAction(
            name='copy-src',
            type='file',
            command='copy',
            source=pathlib.Path('src'),
            destination=pathlib.Path('backup/src'),
        )

        await self.file_executor.execute(action)

        # Verify directory was copied
        backup_path = self.working_directory / 'backup/src'
        self.assertTrue(backup_path.exists())
        self.assertTrue(backup_path.is_dir())
        self.assertTrue((backup_path / 'main.py').exists())

    async def test_execute_copy_source_not_exists(self) -> None:
        """Test copy operation with non-existent source."""
        action = models.WorkflowFileAction(
            name='copy-nonexistent',
            type='file',
            command='copy',
            source=pathlib.Path('nonexistent.txt'),
            destination=pathlib.Path('copy.txt'),
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.file_executor.execute(action)

        self.assertIn('Source file does not exist', str(exc_context.exception))

    async def test_execute_delete_file_success(self) -> None:
        """Test successful file deletion."""
        # Create test file to delete
        test_file = self.working_directory / 'to_delete.txt'
        test_file.write_text('delete me')

        action = models.WorkflowFileAction(
            name='delete-file',
            type='file',
            command='delete',
            path=pathlib.Path('to_delete.txt'),
        )

        await self.file_executor.execute(action)

        # Verify file was deleted
        self.assertFalse(test_file.exists())

    async def test_execute_delete_directory_success(self) -> None:
        """Test successful directory deletion."""
        # Create test directory to delete
        test_dir = self.working_directory / 'to_delete_dir'
        test_dir.mkdir()
        (test_dir / 'file.txt').write_text('content')

        action = models.WorkflowFileAction(
            name='delete-dir',
            type='file',
            command='delete',
            path=pathlib.Path('to_delete_dir'),
        )

        await self.file_executor.execute(action)

        # Verify directory was deleted
        self.assertFalse(test_dir.exists())

    async def test_execute_delete_nonexistent_file(self) -> None:
        """Test deletion of non-existent file (should not error)."""
        action = models.WorkflowFileAction(
            name='delete-nonexistent',
            type='file',
            command='delete',
            path=pathlib.Path('nonexistent.txt'),
        )

        # Should not raise exception
        await self.file_executor.execute(action)

    async def test_execute_delete_pattern_success(self) -> None:
        """Test deletion with pattern matching."""
        # Create files to match pattern
        (self.working_directory / 'temp1.tmp').write_text('temp')
        (self.working_directory / 'temp2.tmp').write_text('temp')
        (self.working_directory / 'keep.txt').write_text('keep')

        action = models.WorkflowFileAction(
            name='delete-temps',
            type='file',
            command='delete',
            pattern=re.compile(r'.*\.tmp$'),
        )

        await self.file_executor.execute(action)

        # Verify .tmp files were deleted but .txt file remains
        self.assertFalse((self.working_directory / 'temp1.tmp').exists())
        self.assertFalse((self.working_directory / 'temp2.tmp').exists())
        self.assertTrue((self.working_directory / 'keep.txt').exists())

    async def test_execute_move_success(self) -> None:
        """Test successful file move operation."""
        action = models.WorkflowFileAction(
            name='move-readme',
            type='file',
            command='move',
            source=pathlib.Path('README.md'),
            destination=pathlib.Path('docs/README.md'),
        )

        await self.file_executor.execute(action)

        # Verify file was moved
        old_path = self.working_directory / 'README.md'
        new_path = self.working_directory / 'docs/README.md'
        self.assertFalse(old_path.exists())
        self.assertTrue(new_path.exists())
        self.assertEqual(new_path.read_text(), '# Test Project\n')

    async def test_execute_move_source_not_exists(self) -> None:
        """Test move operation with non-existent source."""
        action = models.WorkflowFileAction(
            name='move-nonexistent',
            type='file',
            command='move',
            source=pathlib.Path('nonexistent.txt'),
            destination=pathlib.Path('moved.txt'),
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.file_executor.execute(action)

        self.assertIn('Source file does not exist', str(exc_context.exception))

    async def test_execute_rename_success(self) -> None:
        """Test successful file rename operation."""
        action = models.WorkflowFileAction(
            name='rename-readme',
            type='file',
            command='rename',
            source=pathlib.Path('README.md'),
            destination=pathlib.Path('README_renamed.md'),
        )

        await self.file_executor.execute(action)

        # Verify file was renamed
        old_path = self.working_directory / 'README.md'
        new_path = self.working_directory / 'README_renamed.md'
        self.assertFalse(old_path.exists())
        self.assertTrue(new_path.exists())
        self.assertEqual(new_path.read_text(), '# Test Project\n')

    async def test_execute_rename_source_not_exists(self) -> None:
        """Test rename operation with non-existent source."""
        action = models.WorkflowFileAction(
            name='rename-nonexistent',
            type='file',
            command='rename',
            source=pathlib.Path('nonexistent.txt'),
            destination=pathlib.Path('renamed.txt'),
        )

        with self.assertRaises(RuntimeError) as exc_context:
            await self.file_executor.execute(action)

        self.assertIn('Source file does not exist', str(exc_context.exception))

    async def test_execute_write_success(self) -> None:
        """Test successful file write operation."""
        action = models.WorkflowFileAction(
            name='write-config',
            type='file',
            command='write',
            path=pathlib.Path('config.json'),
            content='{"name": "test", "version": "1.0.0"}',
        )

        await self.file_executor.execute(action)

        # Verify file was written
        config_path = self.working_directory / 'config.json'
        self.assertTrue(config_path.exists())
        self.assertEqual(
            config_path.read_text(), '{"name": "test", "version": "1.0.0"}'
        )

    async def test_execute_write_binary_content(self) -> None:
        """Test write operation with binary content."""
        binary_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'

        action = models.WorkflowFileAction(
            name='write-binary',
            type='file',
            command='write',
            path=pathlib.Path('image.png'),
            content=binary_content,
        )

        await self.file_executor.execute(action)

        # Verify binary file was written
        image_path = self.working_directory / 'image.png'
        self.assertTrue(image_path.exists())
        self.assertEqual(image_path.read_bytes(), binary_content)

    async def test_execute_write_with_encoding(self) -> None:
        """Test write operation with custom encoding."""
        action = models.WorkflowFileAction(
            name='write-utf16',
            type='file',
            command='write',
            path=pathlib.Path('unicode.txt'),
            content='Hello 世界',
            encoding='utf-16',
        )

        await self.file_executor.execute(action)

        # Verify file was written with correct encoding
        unicode_file = self.working_directory / 'unicode.txt'
        content = unicode_file.read_text(encoding='utf-16')
        self.assertEqual(content, 'Hello 世界')

    async def test_execute_write_nested_path(self) -> None:
        """Test write operation with nested path creation."""
        action = models.WorkflowFileAction(
            name='write-nested',
            type='file',
            command='write',
            path=pathlib.Path('deep/nested/path/file.txt'),
            content='nested content',
        )

        await self.file_executor.execute(action)

        # Verify nested directories were created
        nested_file = self.working_directory / 'deep/nested/path/file.txt'
        self.assertTrue(nested_file.exists())
        self.assertEqual(nested_file.read_text(), 'nested content')

    def test_resolve_path_relative(self) -> None:
        """Test path resolution for relative paths."""
        # Import ResourceUrl from models
        import pydantic

        from imbi_automations.models import ResourceUrl

        relative_path = 'relative/file.txt'
        resource_url = pydantic.TypeAdapter(ResourceUrl).validate_python(
            relative_path
        )
        resolved = utils.resolve_path(self.context, resource_url)

        expected = self.working_directory / 'relative/file.txt'
        self.assertEqual(resolved, expected)

    def test_resolve_path_absolute(self) -> None:
        """Test path resolution for absolute file:// URLs."""
        # Import ResourceUrl from models
        import pydantic

        from imbi_automations.models import ResourceUrl

        absolute_path = 'file:///absolute/path/file.txt'
        resource_url = pydantic.TypeAdapter(ResourceUrl).validate_python(
            absolute_path
        )
        resolved = utils.resolve_path(self.context, resource_url)

        # file:// URLs should resolve relative to working directory
        # (not as absolute paths)
        expected = self.working_directory / 'absolute/path/file.txt'
        self.assertEqual(resolved, expected)


if __name__ == '__main__':
    unittest.main()
