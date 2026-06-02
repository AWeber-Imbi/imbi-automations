"""Tests for docs.py - bundled documentation CLI subcommand.

Covers topic discovery, path resolution, rendering, and the
subcommand entry point.
"""

import contextlib
import io
import pathlib
import tempfile
import unittest
from unittest import mock

import rich.console

from imbi_automations import cli, docs


class DocsRootTestCase(unittest.TestCase):
    """Test documentation root resolution."""

    def test_docs_root_returns_existing_directory(self) -> None:
        """Test docs_root resolves to a directory with topics."""
        root = docs.docs_root()
        self.assertTrue(root.is_dir())
        self.assertTrue((root / 'index.md').is_file())

    def test_docs_root_raises_when_not_found(self) -> None:
        """Test docs_root raises FileNotFoundError when missing."""
        with (
            mock.patch.object(pathlib.Path, 'is_dir', return_value=False),
            self.assertRaises(FileNotFoundError),
        ):
            docs.docs_root()


class TopicsTestCase(unittest.TestCase):
    """Test topic discovery and resolution."""

    def setUp(self) -> None:
        self.root = docs.docs_root()

    def test_available_topics_includes_known_topics(self) -> None:
        """Test known topics appear in the listing."""
        topics = docs.available_topics(self.root)
        for topic in ('index', 'workflows', 'actions/claude'):
            self.assertIn(topic, topics)

    def test_available_topics_excludes_non_markdown(self) -> None:
        """Test non-Markdown files are not listed as topics."""
        topics = docs.available_topics(self.root)
        self.assertNotIn('logo', topics)

    def test_available_topics_excludes_internal_topics(self) -> None:
        """Test contributor-oriented topics are not listed."""
        topics = docs.available_topics(self.root)
        self.assertNotIn('architecture', topics)

    def test_topic_path_rejects_excluded_topic(self) -> None:
        """Test excluded topics raise FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            docs.topic_path(self.root, 'architecture')

    def test_available_topics_groups_top_level_first(self) -> None:
        """Test top-level topics sort before subdirectory topics."""
        topics = docs.available_topics(self.root)
        self.assertLess(
            topics.index('workflows'), topics.index('actions/claude')
        )

    def test_available_topics_sorts_index_first_in_group(self) -> None:
        """Test the index topic sorts first within each group."""
        topics = docs.available_topics(self.root)
        self.assertEqual(topics[0], 'index')
        actions = [t for t in topics if t.startswith('actions/')]
        self.assertEqual(actions[0], 'actions/index')

    def test_topic_path_resolves_without_suffix(self) -> None:
        """Test topic names resolve without the .md suffix."""
        path = docs.topic_path(self.root, 'workflows')
        self.assertEqual(path.name, 'workflows.md')

    def test_topic_path_resolves_with_suffix(self) -> None:
        """Test topic names resolve with an explicit .md suffix."""
        path = docs.topic_path(self.root, 'workflows.md')
        self.assertEqual(path.name, 'workflows.md')

    def test_topic_path_resolves_nested_topics(self) -> None:
        """Test nested topic names resolve correctly."""
        path = docs.topic_path(self.root, 'actions/claude')
        self.assertEqual(path.parent.name, 'actions')

    def test_topic_path_rejects_unknown_topic(self) -> None:
        """Test unknown topics raise FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            docs.topic_path(self.root, 'no-such-topic')

    def test_topic_path_rejects_traversal(self) -> None:
        """Test paths outside the docs root are rejected."""
        with self.assertRaises(FileNotFoundError):
            docs.topic_path(self.root, '../README')

    def test_topic_title_returns_first_heading(self) -> None:
        """Test topic_title extracts the first H1 heading."""
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'example.md'
            path.write_text('intro\n# Example Title\n# Second\n')
            self.assertEqual(docs.topic_title(path), 'Example Title')

    def test_topic_title_returns_empty_without_heading(self) -> None:
        """Test topic_title returns empty string without an H1."""
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'example.md'
            path.write_text('no heading here\n')
            self.assertEqual(docs.topic_title(path), '')


class RenderTestCase(unittest.TestCase):
    """Test listing and rendering output."""

    def setUp(self) -> None:
        self.root = docs.docs_root()
        self.console = rich.console.Console(
            file=io.StringIO(), force_terminal=False, width=100
        )

    def test_list_topics_plain_writes_topic_names(self) -> None:
        """Test plain listing writes one topic per line to stdout."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            docs.list_topics(self.console, self.root, plain=True)
        lines = stdout.getvalue().splitlines()
        self.assertIn('workflows', lines)
        self.assertIn('actions/claude', lines)

    def test_list_topics_rendered_includes_titles(self) -> None:
        """Test rendered listing includes topic names."""
        docs.list_topics(self.console, self.root, plain=False)
        output = self.console.file.getvalue()
        self.assertIn('workflows', output)
        self.assertIn('Documentation Topics', output)

    def test_render_topic_plain_writes_raw_markdown(self) -> None:
        """Test plain rendering writes the raw Markdown source."""
        path = docs.topic_path(self.root, 'workflows')
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            docs.render_topic(self.console, path, plain=True)
        self.assertEqual(stdout.getvalue(), path.read_text())

    def test_render_topic_renders_markdown(self) -> None:
        """Test rendered output is produced via the console."""
        path = docs.topic_path(self.root, 'workflows')
        docs.render_topic(self.console, path, plain=False)
        self.assertTrue(self.console.file.getvalue())


class MainTestCase(unittest.TestCase):
    """Test the docs subcommand entry point."""

    def test_main_without_topic_lists_topics(self) -> None:
        """Test invoking without a topic lists the topics."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            docs.main(['--plain'])
        self.assertIn('workflows', stdout.getvalue())

    def test_main_with_unknown_topic_exits_nonzero(self) -> None:
        """Test unknown topics exit with status 1."""
        stderr = io.StringIO()
        with (
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as ctx,
        ):
            docs.main(['no-such-topic'])
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn('Unknown topic', stderr.getvalue())

    def test_main_with_topic_renders_plain(self) -> None:
        """Test rendering a topic with --plain."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            docs.main(['workflows', '--plain'])
        self.assertIn('# ', stdout.getvalue())

    def test_cli_main_dispatches_docs_subcommand(self) -> None:
        """Test cli.main routes the docs subcommand to docs.main."""
        with (
            mock.patch.object(docs, 'main') as docs_main,
            mock.patch('sys.argv', ['imbi-automations', 'docs', '--plain']),
        ):
            cli.main()
        docs_main.assert_called_once_with(['--plain'])
