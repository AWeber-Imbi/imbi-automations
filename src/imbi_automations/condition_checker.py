"""Workflow condition evaluation for local and remote repository checks.

Evaluates workflow conditions including file existence, content matching,
and glob patterns, with support for both local (post-clone) and remote
(GitHub API) checks for performance optimization.
"""

import fnmatch
import logging
import pathlib
import re

import httpx
import jinja2

from imbi_automations import clients, mixins, models, prompts, utils

LOGGER = logging.getLogger(__name__)


class ConditionChecker(mixins.WorkflowLoggerMixin):
    """Class for checking conditions."""

    def __init__(
        self, configuration: models.Configuration, verbose: bool
    ) -> None:
        super().__init__(verbose)
        self.configuration = configuration
        self.logger = LOGGER
        self.github: clients.GitHub | None = None
        if configuration.github:
            self.github = clients.GitHub.get_instance(config=configuration)

    def check(
        self,
        context: models.WorkflowContext,
        condition_type: models.WorkflowConditionType,
        conditions: list[models.WorkflowCondition],
    ) -> bool:
        """Run the condition checks"""
        if not conditions:
            return True

        self._set_workflow_logger(context.workflow)

        results = []
        for condition in conditions:
            if condition.file_contains and condition.file:
                file_path = utils.resolve_path(context, condition.file)
                results.append(self._check_file_contains(file_path, condition))
            elif condition.file_doesnt_contain and condition.file:
                file_path = utils.resolve_path(context, condition.file)
                results.append(
                    self._check_file_doesnt_contain(file_path, condition)
                )
            elif condition.file_exists:
                file_path = utils.resolve_path(context, condition.file_exists)
                results.append(
                    self._check_file_pattern_exists(
                        file_path, condition.file_exists
                    )
                )
            elif condition.file_not_exists:
                file_path = utils.resolve_path(
                    context, condition.file_not_exists
                )
                results.append(
                    not self._check_file_pattern_exists(
                        file_path, condition.file_not_exists
                    )
                )
            elif condition.when:
                results.append(self._check_when(context, condition))
        if condition_type == models.WorkflowConditionType.any:
            return any(results)
        return all(results)

    async def check_remote(
        self,
        context: models.WorkflowContext,
        condition_type: models.WorkflowConditionType,
        conditions: list[models.WorkflowCondition],
    ) -> bool:
        """Run the condition checks"""
        if not conditions:
            return True

        self._set_workflow_logger(context.workflow)

        results = []
        for condition in conditions:
            self.logger.debug('%r', condition.model_dump())

            # Skip local-only conditions (file_exists, file_not_exists, when)
            # when conditions require local filesystem access for templates
            if (
                condition.file_exists
                or condition.file_not_exists
                or condition.when
            ):
                continue

            # Handle remote conditions
            if (
                condition.remote_file_exists
                or condition.remote_file_not_exists
                or condition.remote_file_contains
                or condition.remote_file_doesnt_contain
            ):
                client = await self._check_remote_client(condition)
                file_path = (
                    condition.remote_file
                    or condition.remote_file_exists
                    or condition.remote_file_not_exists
                )

                # Check if this is a glob pattern for file existence checks
                if (
                    condition.remote_file_exists
                    or condition.remote_file_not_exists
                ) and self._is_glob_pattern(file_path):
                    result = await self._check_remote_file_glob(
                        context, client, file_path
                    )
                    if condition.remote_file_not_exists:
                        result = not result
                    results.append(result)
                    continue

                # Regular file content check
                content = await client.get_file_contents(context, file_path)

                if condition.remote_file_contains and condition.remote_file:
                    results.append(
                        content is not None
                        and self._match_string_or_regex(
                            condition.remote_file_contains, content
                        )
                    )
                elif (
                    condition.remote_file_doesnt_contain
                    and condition.remote_file
                ):
                    results.append(
                        content is not None
                        and not self._match_string_or_regex(
                            condition.remote_file_doesnt_contain, content
                        )
                    )
                elif condition.remote_file_exists:
                    results.append(content is not None)
                elif condition.remote_file_not_exists:
                    results.append(content is None)

        # If no remote conditions checked, defer to local check
        if not results:
            return True

        if condition_type == models.WorkflowConditionType.any:
            return any(results)
        return all(results)

    @staticmethod
    def _match_string_or_regex(pattern: str, content: str) -> bool:
        """Check if content matches pattern via exact string or regex.

        Tries exact string matching first for performance, then falls back
        to regex pattern matching if no exact match is found.

        Args:
            pattern: String to match (literal or regex pattern)
            content: Content to search within

        Returns:
            True if exact string match or regex match found, False otherwise

        """
        # Try exact string match first (fast)
        if pattern in content:
            return True

        # Fall back to regex pattern matching
        try:
            compiled = re.compile(pattern)
            return compiled.search(content) is not None
        except re.error:
            # Invalid regex, treat as failed match
            return False

    def _check_file_contains(
        self, file_path: pathlib.Path, condition: models.WorkflowCondition
    ) -> bool:
        """Check if a file contains the specified string or regex pattern"""
        if not file_path.is_file():
            self.logger.debug(
                'file %s does not exist for contains check', condition.file
            )
            return False
        try:
            file_content = file_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            self.logger.warning(
                'failed to read file %s for contains check: %s',
                condition.file,
                exc,
            )
            return False

        return self._match_string_or_regex(
            condition.file_contains, file_content
        )

    def _check_file_doesnt_contain(
        self, file_path: pathlib.Path, condition: models.WorkflowCondition
    ) -> bool:
        """Check file exists & does not contain string or regex pattern"""
        if not file_path.is_file():
            self.logger.debug(
                'file %s does not exist for negative contains check',
                condition.file,
            )
            return False
        try:
            file_content = file_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            self.logger.warning(
                'failed to read file %s for negative contains check: %s',
                condition.file,
                exc,
            )
            return False

        return not self._match_string_or_regex(
            condition.file_doesnt_contain, file_content
        )

    def _check_when(
        self,
        context: models.WorkflowContext,
        condition: models.WorkflowCondition,
    ) -> bool:
        """Evaluate a Jinja2 template and check if result is truthy.

        Lenient evaluation:
        - Truthy: 'True', 'true', '1', 'yes', any non-empty string
        - Falsy: 'False', 'false', '0', 'no', 'none', ''

        Args:
            context: Workflow context for template rendering.
            condition: Workflow condition with when field.

        Returns:
            True if template evaluates to truthy value, False otherwise.
        """
        if not condition.when:
            return False

        try:
            rendered = prompts.render(context, template=condition.when).strip()
            self.logger.debug('when condition rendered to: %r', rendered)

            # Falsy: explicit false values; everything else is truthy
            return rendered.lower() not in ('false', '0', 'no', 'none', '')
        except (ValueError, TypeError, jinja2.TemplateError) as exc:
            self.logger.warning('when condition failed: %s', exc)
            return False

    @staticmethod
    def _check_file_pattern_exists(
        file_path: pathlib.Path, resource_url: models.ResourceUrl
    ) -> bool:
        """Check if a file exists using exact path, glob pattern, or regex.

        Args:
            file_path: Resolved file path from utils.resolve_path
            resource_url: Original ResourceUrl for pattern extraction

        Returns:
            True if file exists (string), glob matches (pattern), or
            regex matches any file (Pattern)

        """
        # Extract the path component from the ResourceUrl
        file_str = str(resource_url).split('://', 1)[-1]

        if isinstance(file_str, str):
            # Check if it's a glob pattern (contains *, ?, [, or **)
            if any(char in file_str for char in ['*', '?', '[']):
                # For glob patterns, we need to separate the base directory
                # from the pattern. file_path includes the pattern
                # components, so we need to find the base directory by
                # removing pattern parts

                # Split the pattern to find the first component with glob chars
                parts = file_str.split('/')
                pattern_idx = 0
                for i, part in enumerate(parts):
                    if any(char in part for char in ['*', '?', '[']):
                        pattern_idx = i
                        break

                # Get base directory by going up from file_path
                # The number of times to go up depends on how many parts
                # are in the pattern
                base_path = file_path
                for _ in range(len(parts) - pattern_idx):
                    base_path = base_path.parent

                # Now apply the glob pattern
                if file_str.startswith('**/'):
                    # Recursive glob
                    pattern = file_str[3:]  # Remove **/ prefix
                    matches = base_path.rglob(pattern)
                else:
                    # Regular glob
                    matches = base_path.glob(file_str)

                # Return True if any files match the pattern
                try:
                    next(matches)
                    return True
                except StopIteration:
                    return False

            # Regular file path check
            return file_path.exists()

        try:
            pattern = re.compile(file_str)
        except re.error as exc:
            raise RuntimeError(f'Invalid regex pattern "{file_str}"') from exc

        base_path = file_path.parent
        for path in base_path.rglob('*'):
            relative_path = path.relative_to(base_path)
            if pattern.search(str(relative_path)):
                return True
        return False

    @staticmethod
    def _is_glob_pattern(file_path: str) -> bool:
        """Check if a file path contains glob pattern characters."""
        return any(char in file_path for char in ['*', '?', '['])

    async def _check_remote_file_glob(
        self,
        context: models.WorkflowContext,
        client: clients.GitHub,
        pattern: str,
    ) -> bool:
        """Check if any files match a glob pattern in remote repository.

        Args:
            context: Workflow context
            client: GitHub client
            pattern: Glob pattern to match

        Returns:
            True if any files match the pattern

        """
        # Only GitHub supports tree API for now
        if not isinstance(client, clients.GitHub):
            self.logger.warning(
                'glob patterns for remote_file_exists only supported '
                'for GitHub repositories, falling back to literal check'
            )
            content = await client.get_file_contents(context, pattern)
            return content is not None

        try:
            # Get repository tree
            file_paths = await client.get_repository_tree(context)

            # Match against glob pattern
            if pattern.startswith('**/'):
                # Recursive glob
                pattern_suffix = pattern[3:]
                for file_path in file_paths:
                    if fnmatch.fnmatch(file_path, f'*/{pattern_suffix}'):
                        return True
                    if fnmatch.fnmatch(file_path, pattern_suffix):
                        return True
            else:
                # Regular glob
                for file_path in file_paths:
                    if fnmatch.fnmatch(file_path, pattern):
                        return True

            return False

        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            self.logger.warning(
                'failed to check glob pattern %s remotely: %s', pattern, exc
            )
            # Fall back to literal check
            content = await client.get_file_contents(context, pattern)
            return content is not None

    async def _check_remote_client(
        self, condition: models.WorkflowCondition
    ) -> clients.GitHub:
        """Return the appropriate client for the condition

        :raises: RuntimeError

        """
        if (
            condition.remote_client
            == models.WorkflowConditionRemoteClient.github
        ):
            if not self.github:
                raise RuntimeError(
                    'Remote Action invoked for GitHub, '
                    'but GitHub is not configured'
                )
            return self.github
        raise RuntimeError('Unsupported remote client for condition')
