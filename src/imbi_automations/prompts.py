"""Jinja2 template rendering for prompts and dynamic content generation.

Provides template rendering functionality for Claude Code prompts, pull request
messages, commit messages, and other dynamic content using Jinja2 with full
workflow context support.
"""

import json
import logging
import pathlib
import re
import tomllib
import typing
from urllib import parse

import jinja2
import pydantic
import semver

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

    env = jinja2.Environment(
        autoescape=False,  # noqa: S701
        undefined=jinja2.StrictUndefined,
    )
    if context:
        env.globals.update(
            {
                'compare_semver': compare_semver,
                'extract_image_from_dockerfile': (
                    lambda dockerfile: utils.extract_image_from_dockerfile(
                        context, dockerfile
                    )
                ),
                'extract_package_name_from_pyproject': (
                    lambda path=None: (
                        utils.extract_package_name_from_pyproject(
                            context, path
                        )
                    )
                ),
                'get_component_version': (
                    lambda path, component: get_component_version(
                        context, path, component
                    )
                ),
                'python_init_file_path': (
                    lambda: utils.python_init_file_path(context)
                ),
                'read_file': (
                    lambda path: utils.resolve_path(context, path).read_text(
                        encoding='utf-8'
                    )
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


def render_template_string(template_string: str, **kwargs: typing.Any) -> str:
    """Render a template string with provided variables.

    Args:
        template_string: Template string to render.
        **kwargs: Variables to pass to template rendering.

    Returns:
        Rendered string.
    """
    env = jinja2.Environment(
        autoescape=False,  # noqa: S701
        undefined=jinja2.StrictUndefined,
    )

    # Add context if workflow context is provided
    if 'workflow' in kwargs:
        context = models.WorkflowContext(
            workflow=kwargs['workflow'],
            github_repository=kwargs.get('github_repository'),
            imbi_project=kwargs.get('imbi_project'),
            working_directory=kwargs.get('working_directory'),
            starting_commit=kwargs.get('starting_commit'),
        )
        env.globals.update(
            {
                'read_file': (
                    lambda path: utils.resolve_path(context, path).read_text(
                        encoding='utf-8'
                    )
                )
            }
        )

    return env.from_string(template_string).render(**kwargs)


def _parse_version_with_build(
    version: str,
) -> tuple[semver.Version, int | None]:
    """Parse a version string, extracting optional build number.

    Handles versions like "3.9.18-4" where -4 is a build/revision number.

    Args:
        version: Version string to parse.

    Returns:
        Tuple of (semver.Version, optional build number).
    """
    # Clean version string (remove prefixes like v, ^, ~, >=, etc.)
    cleaned = re.sub(r'^[v\^~>=<]+', '', version.strip())

    # Check for build number suffix (e.g., "3.9.18-4")
    build_match = re.match(r'^(\d+\.\d+\.\d+)-(\d+)$', cleaned)
    if build_match:
        base_version = build_match.group(1)
        build_number = int(build_match.group(2))
        return semver.Version.parse(base_version), build_number

    # Handle partial versions (e.g., "3.9" -> "3.9.0")
    parts = cleaned.split('.')
    while len(parts) < 3:
        parts.append('0')
    normalized = '.'.join(parts[:3])

    return semver.Version.parse(normalized), None


def _compare_versions(
    current: semver.Version,
    current_build: int | None,
    target: semver.Version,
    target_build: int | None,
) -> int:
    """Compare two versions with optional build numbers.

    Args:
        current: Current semver version.
        current_build: Optional build number for current version.
        target: Target semver version.
        target_build: Optional build number for target version.

    Returns:
        -1 if current < target, 0 if equal, 1 if current > target.
    """
    if current < target:
        return -1
    elif current > target:
        return 1

    # Versions equal, compare build numbers if present
    if current_build is not None and target_build is not None:
        if current_build < target_build:
            return -1
        elif current_build > target_build:
            return 1
    elif current_build is not None:
        # Current has build, target doesn't - current is newer
        return 1
    elif target_build is not None:
        # Target has build, current doesn't - current is older
        return -1

    return 0


def compare_semver(current: str, target: str) -> dict[str, typing.Any]:
    """Compare two semantic versions, returning a rich result dict.

    This function is exposed as a Jinja2 template function for use in
    workflow conditions.

    Args:
        current: Current version string (e.g., "18.2.0", "3.9.18-4").
        target: Target version string to compare against.

    Returns:
        Dict with comparison results:
            - current_version: Original current version string
            - target_version: Original target version string
            - comparison: -1 (older), 0 (equal), or 1 (newer)
            - is_older: True if current < target
            - is_equal: True if current == target
            - is_newer: True if current > target
            - current_major, current_minor, current_patch, current_build
            - target_major, target_minor, target_patch, target_build
    """
    current_sem, current_build = _parse_version_with_build(current)
    target_sem, target_build = _parse_version_with_build(target)
    comparison = _compare_versions(
        current_sem, current_build, target_sem, target_build
    )

    return {
        'current_version': current,
        'target_version': target,
        'comparison': comparison,
        'is_older': comparison < 0,
        'is_equal': comparison == 0,
        'is_newer': comparison > 0,
        'current_major': current_sem.major,
        'current_minor': current_sem.minor,
        'current_patch': current_sem.patch,
        'current_build': current_build,
        'target_major': target_sem.major,
        'target_minor': target_sem.minor,
        'target_patch': target_sem.patch,
        'target_build': target_build,
    }


def _clean_version_spec(version_spec: str) -> str:
    """Strip version prefixes and constraints to get clean version.

    Handles npm/yarn/pnpm prefixes (^, ~, >=, etc.) and constraint ranges.

    Args:
        version_spec: Version specification string (e.g., "^18.2.0", ">=3.9").

    Returns:
        Clean version string without prefixes or range specifiers.
    """
    # Take first part if there's a comma (range constraint)
    version = version_spec.split(',')[0].strip()
    # Strip common prefixes
    return re.sub(r'^[\^~>=<]+', '', version)


def _extract_from_package_json(path: pathlib.Path, component: str) -> str:
    """Extract a dependency version from package.json.

    Args:
        path: Path to package.json file.
        component: Name of the dependency to find.

    Returns:
        Clean version string.

    Raises:
        ValueError: If component not found in any dependency section.
    """
    data = json.loads(path.read_text(encoding='utf-8'))

    for section in ['dependencies', 'devDependencies', 'peerDependencies']:
        if section in data and component in data[section]:
            return _clean_version_spec(data[section][component])

    raise ValueError(f'Component {component!r} not found in {path}')


def _parse_pep508_name(dep_string: str) -> str:
    """Extract package name from PEP 508 dependency string.

    Args:
        dep_string: PEP 508 dependency string (e.g., "requests>=2.28.0").

    Returns:
        Package name portion.
    """
    # PEP 508: name followed by optional extras, then version specifiers
    match = re.match(r'^([a-zA-Z0-9_-]+)', dep_string)
    return match.group(1) if match else dep_string


def _parse_pep508_version(dep_string: str) -> str:
    """Extract version from PEP 508 dependency string.

    Args:
        dep_string: PEP 508 dependency string (e.g., "requests>=2.28.0").

    Returns:
        Clean version string.

    Raises:
        ValueError: If no version specifier found.
    """
    # Look for version specifier after name/extras
    match = re.search(r'[><=!~]+\s*([0-9][0-9a-zA-Z.*-]*)', dep_string)
    if match:
        return _clean_version_spec(match.group(1))
    raise ValueError(f'No version specifier in {dep_string!r}')


def _extract_from_pyproject(path: pathlib.Path, component: str) -> str:
    """Extract a dependency version from pyproject.toml.

    Supports both PEP 508 format (project.dependencies) and Poetry format
    (tool.poetry.dependencies).

    Args:
        path: Path to pyproject.toml file.
        component: Name of the dependency to find.

    Returns:
        Clean version string.

    Raises:
        ValueError: If component not found in any dependency section.
    """
    data = tomllib.loads(path.read_text(encoding='utf-8'))

    # Check PEP 508 format: project.dependencies
    for dep in data.get('project', {}).get('dependencies', []):
        if _parse_pep508_name(dep).lower() == component.lower():
            return _parse_pep508_version(dep)

    # Check optional dependencies
    for deps in (
        data.get('project', {}).get('optional-dependencies', {}).values()
    ):
        for dep in deps:
            if _parse_pep508_name(dep).lower() == component.lower():
                return _parse_pep508_version(dep)

    # Check Poetry format: tool.poetry.dependencies
    poetry_deps = (
        data.get('tool', {}).get('poetry', {}).get('dependencies', {})
    )
    if component in poetry_deps:
        version = poetry_deps[component]
        if isinstance(version, dict):
            version = version.get('version', '')
        return _clean_version_spec(str(version))

    # Check Poetry dev-dependencies
    poetry_dev = (
        data.get('tool', {}).get('poetry', {}).get('dev-dependencies', {})
    )
    if component in poetry_dev:
        version = poetry_dev[component]
        if isinstance(version, dict):
            version = version.get('version', '')
        return _clean_version_spec(str(version))

    raise ValueError(f'Component {component!r} not found in {path}')


def get_component_version(
    context: models.WorkflowContext, path: str, component: str
) -> str:
    """Extract a dependency version from package.json or pyproject.toml.

    This function is exposed as a Jinja2 template function for use in
    workflow conditions. The context parameter is automatically bound
    when registered as a template function.

    Args:
        context: Workflow context for path resolution.
        path: ResourceUrl path to manifest file (e.g., "repository:///package.json").
        component: Name of the dependency to extract version for.

    Returns:
        Clean version string.

    Raises:
        ValueError: If file type is unsupported or component not found.
    """
    resolved_path = utils.resolve_path(context, models.ResourceUrl(path))

    if resolved_path.name == 'package.json':
        return _extract_from_package_json(resolved_path, component)
    elif resolved_path.name == 'pyproject.toml':
        return _extract_from_pyproject(resolved_path, component)
    else:
        raise ValueError(f'Unsupported file type: {resolved_path.name}')
