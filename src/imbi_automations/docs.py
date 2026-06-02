"""Expose bundled documentation via the command-line interface.

Implements the ``imbi-automations docs`` subcommand for listing and
rendering the Markdown documentation that ships with the package.
"""

import argparse
import importlib.resources
import pathlib
import sys

import rich.console
import rich.markdown
import rich.table

# Contributor-oriented topics that are not relevant to using the CLI
EXCLUDED_TOPICS = frozenset({'architecture'})


def docs_root() -> pathlib.Path:
    """Return the directory containing the bundled documentation.

    Prefers the documentation bundled inside the installed package,
    falling back to the repository ``docs/`` directory for editable
    development installs.

    Raises:
        FileNotFoundError: If no documentation directory can be found.

    """
    bundled = pathlib.Path(
        str(importlib.resources.files('imbi_automations') / 'docs')
    )
    if bundled.is_dir():
        return bundled
    repo_docs = pathlib.Path(__file__).parents[2] / 'docs'
    if repo_docs.is_dir():
        return repo_docs
    raise FileNotFoundError('Bundled documentation not found')


def topic_sort_key(topic: str) -> tuple[str, bool, str]:
    """Group topics by directory, overview (index) pages first.

    Top-level topics sort before subdirectory topics, and within each
    group the ``index`` page sorts first.
    """
    parent, _, name = topic.rpartition('/')
    return parent, name != 'index', name


def available_topics(root: pathlib.Path) -> list[str]:
    """Return topic names relative to the documentation root.

    Topics are grouped by directory with overview pages first within
    each group (see :func:`topic_sort_key`). Contributor-oriented
    topics (:data:`EXCLUDED_TOPICS`) are omitted.
    """
    return sorted(
        (
            topic
            for path in root.rglob('*.md')
            if (topic := str(path.relative_to(root).with_suffix('')))
            not in EXCLUDED_TOPICS
        ),
        key=topic_sort_key,
    )


def topic_path(root: pathlib.Path, topic: str) -> pathlib.Path:
    """Resolve a topic name to its Markdown file.

    Accepts topic names with or without the ``.md`` suffix and rejects
    excluded topics and paths that resolve outside of the
    documentation root.

    Raises:
        FileNotFoundError: If the topic does not exist or is excluded.

    """
    name = topic.removesuffix('.md')
    if name in EXCLUDED_TOPICS:
        raise FileNotFoundError(topic)
    candidate = (root / f'{name}.md').resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise FileNotFoundError(topic)
    if not candidate.is_file():
        raise FileNotFoundError(topic)
    return candidate


def topic_title(path: pathlib.Path) -> str:
    """Return the first Markdown H1 heading in the file, if any."""
    with path.open() as handle:
        for line in handle:
            if line.startswith('# '):
                return line[2:].strip()
    return ''


def list_topics(
    console: rich.console.Console, root: pathlib.Path, plain: bool
) -> None:
    """Print the available documentation topics.

    Rendered output separates each directory of topics into its own
    table section.
    """
    topics = available_topics(root)
    if plain:
        sys.stdout.write('\n'.join(topics) + '\n')
        return
    table = rich.table.Table(title='Documentation Topics')
    table.add_column('Topic', style='cyan', no_wrap=True)
    table.add_column('Title')
    group = ''
    for topic in topics:
        parent = topic.rpartition('/')[0]
        if parent != group:
            table.add_section()
            group = parent
        table.add_row(topic, topic_title(root / f'{topic}.md'))
    console.print(table)
    console.print(
        'Render a topic with: imbi-automations docs TOPIC', style='dim'
    )


def render_topic(
    console: rich.console.Console, path: pathlib.Path, plain: bool
) -> None:
    """Render a documentation file to the terminal."""
    source = path.read_text(encoding='utf-8')
    if plain:
        sys.stdout.write(source)
        return
    console.print(rich.markdown.Markdown(source))


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the docs subcommand."""
    parser = argparse.ArgumentParser(
        prog='imbi-automations docs',
        description='List and render the bundled documentation in the '
        'terminal',
    )
    parser.add_argument(
        'topic',
        nargs='?',
        metavar='TOPIC',
        help='Documentation topic to render (omit to list all topics)',
    )
    parser.add_argument(
        '--plain',
        action='store_true',
        help='Output raw Markdown instead of rendered output',
    )
    return parser.parse_args(args)


def main(args: list[str] | None = None) -> None:
    """Entry point for the ``imbi-automations docs`` subcommand."""
    parsed = parse_args(args)
    root = docs_root()
    console = rich.console.Console()
    if not parsed.topic:
        list_topics(console, root, parsed.plain)
        return
    try:
        path = topic_path(root, parsed.topic)
    except FileNotFoundError:
        sys.stderr.write(
            f'Unknown topic: {parsed.topic}\n'
            f'Run "imbi-automations docs" to list available topics.\n'
        )
        sys.exit(1)
    render_topic(console, path, parsed.plain)
