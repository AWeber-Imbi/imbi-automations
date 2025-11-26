"""Utility operations for workflow execution."""

import typing

import semver

from imbi_automations import mixins, models, prompts


class UtilityActions(mixins.WorkflowLoggerMixin):
    """Executes utility helper operations for common workflow tasks.

    Provides Docker tag parsing, Dockerfile analysis, semantic versioning
    comparison, and Python constraint parsing utilities.
    """

    def __init__(
        self,
        configuration: models.Configuration,
        context: models.WorkflowContext,
        verbose: bool,
    ) -> None:
        super().__init__(verbose)
        self._set_workflow_logger(context.workflow)
        self.configuration = configuration
        self.context = context

    async def execute(self, action: models.WorkflowUtilityAction) -> None:
        match action.command:
            case models.WorkflowUtilityCommands.docker_tag:
                raise NotImplementedError(
                    'Utility docker_tag not yet supported'
                )
            case models.WorkflowUtilityCommands.dockerfile_from:
                raise NotImplementedError(
                    'Utility dockerfile_from not yet supported'
                )
            case models.WorkflowUtilityCommands.compare_semver:
                await self._execute_compare_semver(action)
            case models.WorkflowUtilityCommands.parse_python_constraints:
                raise NotImplementedError(
                    'Utility parse_python_constraints not yet supported'
                )
            case _:
                raise RuntimeError(f'Unsupported command: {action.command}')

    async def _execute_compare_semver(
        self, action: models.WorkflowUtilityAction
    ) -> None:
        """Compare two semantic versions and store result in context.

        Accepts versions via positional args or kwargs:
            args = ["1.2.3", "2.0.0"]
            kwargs = {current_version: "1.2.3", target_version: "2.0.0"}

        Stores result in context.variables using output kwarg (default:
        'semver_result').

        Supports standard semver and versions with build numbers
        (e.g., "3.9.18-4").
        """
        current_version, target_version = self._get_version_args(action)

        # Parse versions
        current_sem, current_build = self._parse_version_with_build(
            current_version
        )
        target_sem, target_build = self._parse_version_with_build(
            target_version
        )

        # Compare versions
        comparison = self._compare_versions(
            current_sem, current_build, target_sem, target_build
        )

        # Build result
        result = models.SemverComparisonResult(
            current_version=current_version,
            target_version=target_version,
            comparison=comparison,
            is_older=comparison < 0,
            is_equal=comparison == 0,
            is_newer=comparison > 0,
            current_major=current_sem.major,
            current_minor=current_sem.minor,
            current_patch=current_sem.patch,
            current_build=current_build,
            target_major=target_sem.major,
            target_minor=target_sem.minor,
            target_patch=target_sem.patch,
            target_build=target_build,
        )

        # Store in context variables
        output_name = action.kwargs.get('output', 'semver_result')
        self.context.variables[output_name] = result.model_dump()

        self.logger.info(
            '%s [%s/%s] %s compared versions: %s vs %s -> %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            current_version,
            target_version,
            'older'
            if result.is_older
            else 'newer'
            if result.is_newer
            else 'equal',
        )

    def _get_version_args(
        self, action: models.WorkflowUtilityAction
    ) -> tuple[str, str]:
        """Extract current and target versions from action args/kwargs."""
        # Try positional args first
        if len(action.args) >= 2:
            current = self._process_arg(action.args[0])
            target = self._process_arg(action.args[1])
            return str(current), str(target)

        # Try kwargs
        current = action.kwargs.get('current_version')
        target = action.kwargs.get('target_version')

        if current is None or target is None:
            raise ValueError(
                'compare_semver requires current_version and target_version '
                'either as positional args or kwargs'
            )

        return (
            str(self._process_arg(current)),
            str(self._process_arg(target)),
        )

    def _process_arg(self, arg: typing.Any) -> typing.Any:
        """Process an argument, rendering templates if present."""
        if isinstance(arg, str) and prompts.has_template_syntax(arg):
            return prompts.render(self.context, template=arg)
        return arg

    def _parse_version_with_build(
        self, version: str
    ) -> tuple[semver.Version, int | None]:
        """Parse a version string, extracting semver and optional build.

        Handles formats like "3.9.18" or "3.9.18-4" where the suffix
        after the hyphen is treated as a build number.
        """
        if '-' in version:
            sem_str, build_str = version.rsplit('-', 1)
            try:
                build = int(build_str)
            except ValueError:
                build = None
        else:
            sem_str = version
            build = None

        try:
            sem_version = semver.Version.parse(sem_str)
        except ValueError as exc:
            raise ValueError(
                f'Invalid semver format: {version!r}. Expected format: '
                f'major.minor.patch or major.minor.patch-build'
            ) from exc

        return sem_version, build

    def _compare_versions(
        self,
        current_sem: semver.Version,
        current_build: int | None,
        target_sem: semver.Version,
        target_build: int | None,
    ) -> int:
        """Compare two versions including build numbers.

        Returns:
            -1 if current < target (older)
             0 if current == target (equal)
             1 if current > target (newer)
        """
        sem_comparison = current_sem.compare(target_sem)

        if sem_comparison != 0:
            return sem_comparison

        # Semantic versions are equal, compare build numbers
        current_b = current_build if current_build is not None else 0
        target_b = target_build if target_build is not None else 0

        if current_b < target_b:
            return -1
        elif current_b > target_b:
            return 1
        return 0
