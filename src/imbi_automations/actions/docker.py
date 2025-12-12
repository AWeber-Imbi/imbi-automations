"""Docker operations for workflow execution."""

import asyncio

from imbi_automations import mixins, models, prompts, utils


class DockerActions(mixins.WorkflowLoggerMixin):
    """Executes Docker operations including container file extraction.

    Manages Docker container lifecycle for build, extract, pull, and push
    operations with automatic cleanup.
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

    async def execute(self, action: models.WorkflowDockerAction) -> None:
        """Execute a docker action based on the command type.

        Args:
            context: Workflow context
            action: Docker action containing the command and parameters

        Raises:
            RuntimeError: If docker operation fails
            ValueError: If required parameters are missing or invalid

        """
        match action.command:
            case models.WorkflowDockerActionCommand.build:
                await self._execute_build(action)
            case models.WorkflowDockerActionCommand.extract:
                await self._execute_extract(action)
            case models.WorkflowDockerActionCommand.pull:
                await self._execute_pull(action)
            case models.WorkflowDockerActionCommand.push:
                await self._execute_push(action)
            case _:
                raise RuntimeError(
                    f'Unsupported docker command: {action.command}'
                )

    async def _execute_build(
        self, action: models.WorkflowDockerAction
    ) -> None:
        """Execute docker build command to build an image from a Dockerfile."""
        image = (
            prompts.render(self.context, template=str(action.image))
            if prompts.has_template_syntax(action.image)
            else action.image
        )
        image = f'{image}:{action.tag}' if ':' not in image else image

        # Resolve build context path
        build_path = utils.resolve_path(
            self.context,
            prompts.render_path(self.context, action.path),
            default_scheme='repository',
        )

        if not build_path.exists():
            raise RuntimeError(
                f'Build context path does not exist: {build_path}'
            )

        self.logger.info(
            '%s [%s/%s] %s building image %s from %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            image,
            build_path,
        )
        await self._run_docker_command(
            ['docker', 'build', '-t', image, str(build_path)], action=action
        )
        self.logger.info(
            '%s [%s/%s] %s built image %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            image,
        )

    async def _execute_extract(
        self, action: models.WorkflowDockerAction
    ) -> None:
        """Execute docker extract command to copy files from container."""
        image = (
            prompts.render(self.context, template=str(action.image))
            if prompts.has_template_syntax(action.image)
            else action.image
        )
        image = f'{image}:{action.tag}' if ':' not in image else image

        # Build destination path using resolve_path for proper scheme handling
        # Convert file:// scheme to extracted:// for docker extract actions
        dest_url = action.destination
        if str(dest_url).startswith('file:///'):
            dest_url = models.ResourceUrl(
                str(dest_url).replace('file:///', 'extracted:///', 1)
            )
        dest_path = utils.resolve_path(
            self.context, dest_url, default_scheme='extracted'
        )
        self.logger.info(
            '%s [%s/%s] %s extracting %s from container %s to %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.source,
            image,
            dest_path,
        )
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        container_name = f'imbi-extract-{id(action)}'
        try:
            await self._run_docker_command(
                ['docker', 'pull', image], action=action
            )
            await self._run_docker_command(
                ['docker', 'create', '--name', container_name, image],
                action=action,
            )
            await self._run_docker_command(
                [
                    'docker',
                    'cp',
                    f'{container_name}:{action.source}',
                    str(dest_path),
                ],
                action=action,
            )
            self.logger.info(
                '%s [%s/%s] %s extracted %s to %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.source,
                dest_path,
            )
        finally:
            try:
                await self._run_docker_command(
                    ['docker', 'rm', container_name],
                    check_exit_code=False,
                    action=action,
                )
            except RuntimeError as exc:
                self.logger.debug(
                    '%s %s failed to cleanup container %s: %s',
                    self.context.imbi_project.slug,
                    action.name,
                    container_name,
                    exc,
                )

    async def _execute_pull(self, action: models.WorkflowDockerAction) -> None:
        """Execute docker pull command to download an image from a registry."""
        image = (
            prompts.render(self.context, template=str(action.image))
            if prompts.has_template_syntax(action.image)
            else action.image
        )
        image = f'{image}:{action.tag}' if ':' not in image else image

        self.logger.info(
            '%s [%s/%s] %s pulling image %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            image,
        )
        await self._run_docker_command(
            ['docker', 'pull', image], action=action
        )
        self.logger.info(
            '%s [%s/%s] %s pulled image %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            image,
        )

    async def _execute_push(self, action: models.WorkflowDockerAction) -> None:
        """Execute docker push command to upload an image to a registry."""
        image = (
            prompts.render(self.context, template=str(action.image))
            if prompts.has_template_syntax(action.image)
            else action.image
        )
        image = f'{image}:{action.tag}' if ':' not in image else image

        self.logger.info(
            '%s [%s/%s] %s pushing image %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            image,
        )
        await self._run_docker_command(
            ['docker', 'push', image], action=action
        )
        self.logger.info(
            '%s [%s/%s] %s pushed image %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            image,
        )

    async def _run_docker_command(
        self,
        command: list[str],
        check_exit_code: bool = True,
        action: models.WorkflowDockerAction | None = None,
    ) -> tuple[int, str, str]:
        """Run a docker command and return exit code, stdout, stderr.

        Args:
            command: Docker command as list of arguments
            check_exit_code: Whether to raise exception on non-zero exit
            action: Action for logging context (optional)

        Returns:
            Tuple of (exit_code, stdout, stderr)

        Raises:
            RuntimeError: If command fails and check_exit_code is True

        """
        if action:
            self.logger.debug(
                '%s %s running docker command: %s',
                self.context.imbi_project.slug,
                action.name,
                ' '.join(command),
            )
        else:
            self.logger.debug('Running docker command: %s', ' '.join(command))

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Parse timeout to seconds (use action timeout or default)
            import pytimeparse2

            timeout_str = action.timeout if action else '1h'
            timeout_seconds = pytimeparse2.parse(timeout_str)
            if timeout_seconds is None:
                raise ValueError(f'Invalid timeout format: {timeout_str}')

            # Execute with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds
                )
            except TimeoutError:
                # Graceful termination
                if action:
                    self.logger.warning(
                        '%s %s docker command timed out after %s, '
                        'terminating process',
                        self.context.imbi_project.slug,
                        action.name,
                        timeout_str,
                    )
                else:
                    self.logger.warning(
                        'Docker command timed out after %s, '
                        'terminating process',
                        timeout_str,
                    )
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
                    await process.wait()

                raise TimeoutError(
                    f'Docker command timed out after {timeout_str}: '
                    f'{" ".join(command)}'
                ) from None

            stdout_str = stdout.decode('utf-8') if stdout else ''
            stderr_str = stderr.decode('utf-8') if stderr else ''

            if action:
                self.logger.debug(
                    '%s %s docker command completed with exit code %d',
                    self.context.imbi_project.slug,
                    action.name,
                    process.returncode,
                )
            else:
                self.logger.debug(
                    'Docker command completed with exit code %d',
                    process.returncode,
                )

            if stdout_str:
                if action:
                    self.logger.debug(
                        '%s %s docker stdout: %s',
                        self.context.imbi_project.slug,
                        action.name,
                        stdout_str,
                    )
                else:
                    self.logger.debug('Docker stdout: %s', stdout_str)
            if stderr_str:
                if action:
                    self.logger.debug(
                        '%s %s docker stderr: %s',
                        self.context.imbi_project.slug,
                        action.name,
                        stderr_str,
                    )
                else:
                    self.logger.debug('Docker stderr: %s', stderr_str)

            if check_exit_code and process.returncode != 0:
                raise RuntimeError(
                    f'Docker command failed (exit code {process.returncode}): '
                    f'{stderr_str or stdout_str}'
                )

            return process.returncode, stdout_str, stderr_str

        except FileNotFoundError as exc:
            raise RuntimeError(
                'Docker command not found - is Docker installed and in PATH?'
            ) from exc
