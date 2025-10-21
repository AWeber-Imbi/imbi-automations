"""Jinja2 template rendering for prompts and dynamic content generation.

Provides template rendering functionality for Claude Code prompts, pull request
messages, commit messages, and other dynamic content using Jinja2 with full
workflow context support.
"""

import logging
import pathlib
import typing
from urllib import parse

import jinja2
import pydantic

from imbi_automations import models, utils

LOGGER = logging.getLogger(__name__)


def render(
    context: models.WorkflowContext | None = None,
    source: models.ResourceUrl | pathlib.Path | str | None = None,
    template: str | None = None,
    **kwargs: typing.Any,
) -> str:
    """Render a Jinja2 template with workflow context and variables.

    Args:
        context: Workflow context for global variables and path resolution.
        source: Template source as URL, path, or string content.
        template: Template string to use instead of a source file.
        **kwargs: Additional variables to pass to template rendering.

    Returns:
        Rendered template as string.

    Raises:
        ValueError: If source is not provided.
    """
    if not source and not template:
        raise ValueError('source or template is required')
    if source and template:
        raise ValueError('You can not specify both source and template')
    elif isinstance(source, pydantic.AnyUrl):
        source = utils.resolve_path(context, source)
    if source and not isinstance(source, pathlib.Path):
        raise RuntimeError(f'source is not a Path object: {type(source)}')

    LOGGER.debug('Template: %s', template)

    env = jinja2.Environment(
        autoescape=False,  # noqa: S701
        undefined=jinja2.StrictUndefined,
    )
    if context:
        env.globals.update(
            {
                'extract_image_from_dockerfile': (
                    lambda dockerfile: utils.extract_image_from_dockerfile(
                        context, dockerfile
                    )
                ),
                'extract_package_name_from_pyproject': (
                    lambda path: utils.extract_package_name_from_pyproject(
                        context, path
                    )
                ),
                'python_init_file_path': (
                    lambda: utils.python_init_file_path(context)
                ),
            }
        )
        kwargs.update(context.model_dump())

    if isinstance(source, pathlib.Path) and not template:
        template = source.read_text(encoding='utf-8')
    return env.from_string(template).render(**kwargs)


def render_file(
    context: models.WorkflowContext,
    source: pathlib.Path,
    destination: pathlib.Path,
    **kwargs: typing.Any,
) -> None:
    """Render a file from source to destination."""
    logging.info('Rendering %s to %s', source, destination)
    destination.write_text(render(context, source, **kwargs), encoding='utf-8')


def render_path(
    context: models.WorkflowContext, path: pydantic.AnyUrl | str
) -> pydantic.AnyUrl | str:
    if isinstance(path, pydantic.AnyUrl):
        path_str = parse.unquote(path.path)
    elif isinstance(path, str):
        path_str = path
    else:
        raise TypeError(f'Invalid path type: {type(path)}')
    if has_template_syntax(path_str):
        value = render(context, template=path_str)
        LOGGER.debug('Rendered path: %s', value)
        if isinstance(path, pydantic.AnyUrl):
            return models.ResourceUrl(f'{path.scheme}://{value}')
        else:
            return value
    return path


def has_template_syntax(value: str) -> bool:
    """Check if value contains Jinja2 templating syntax."""
    template_patterns = [
        '{{',  # Variable substitution
        '{%',  # Control structures
        '{#',  # Comments
    ]
    return any(pattern in value for pattern in template_patterns)
