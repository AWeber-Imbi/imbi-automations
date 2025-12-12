"""Shell command execution action with templating and environment support.

Executes shell commands with Jinja2 template variable substitution, working
directory management, and proper async subprocess handling for workflow
automation.

SECURITY NOTE:
--------------
This module uses `asyncio.create_subprocess_shell()` to enable shell features
like glob expansion, pipes, and environment variable expansion. This design
choice is intentional but carries security implications:

1. **Command Injection Risk**: Shell commands are rendered through Jinja2
   templates with workflow context variables. If workflow configurations
   contain untrusted input, malicious commands could be executed.

2. **Mitigation Strategies**:
   - Workflow TOML files should be treated as trusted code (like source code)
   - Store workflows in version control with code review requirements
   - Never dynamically generate workflow files from untrusted user input
   - Jinja2 auto-escaping is disabled for command rendering (by design)

3. **Safe Usage Patterns**:
   - Use explicit paths: `/usr/bin/ls` instead of `ls`
   - Quote variables in TOML: command = "ls '{{ directory }}'"
   - Validate inputs in condition checks before shell actions

4. **Examples**:
   ```toml
   # SAFE: Hardcoded command with controlled expansion
   [[actions]]
   type = "shell"
   command = "rm -f .github/workflows/*.yml"

   # SAFE: Template variable from trusted Imbi data
   [[actions]]
   type = "shell"
   command = "echo 'Processing {{ imbi_project.name }}'"

   # UNSAFE: Raw user input (avoid this pattern)
   # command = "sh -c '{{ user_provided_script }}'"
   ```

For maximum security, consider using `file` or `git` action types instead of
shell commands when possible.
"""

import asyncio
import subprocess

from imbi_automations import mixins, models, prompts, utils


class ShellAction(mixins.WorkflowLoggerMixin):
    """Executes shell commands with Jinja2 template variable substitution.

    Provides async subprocess execution with working directory management and
    optional error handling.
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

    async def execute(self, action: models.WorkflowShellAction) -> None:
        """Execute a shell command with optional template rendering.

        Args:
            action: Shell action containing the command to execute

        Raises:
            subprocess.CalledProcessError: If command execution fails
            ValueError: If cmd syntax is invalid or template rendering fails

        """
        # Render command if it contains templating
        command_str = self._render_command(action, self.context)

        self.logger.debug(
            '%s [%s/%s] %s executing shell command: %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            command_str,
        )

        # Set working directory using resolve_path
        cwd = utils.resolve_path(self.context, action.working_directory)

        try:
            # Execute command through shell to enable glob expansion
            process = await asyncio.create_subprocess_shell(
                command_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            # Parse timeout to seconds
            import pytimeparse2

            timeout_seconds = pytimeparse2.parse(action.timeout)
            if timeout_seconds is None:
                raise ValueError(f'Invalid timeout format: {action.timeout}')

            # Execute with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds
                )
            except TimeoutError:
                # Graceful termination
                self.logger.warning(
                    '%s %s shell command timed out after %s, '
                    'terminating process',
                    self.context.imbi_project.slug,
                    action.name,
                    action.timeout,
                )
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
                    await process.wait()

                raise TimeoutError(
                    f'Shell command timed out after {action.timeout}: '
                    f'{command_str}'
                ) from None

            # Decode output
            stdout_str = stdout.decode('utf-8') if stdout else ''
            stderr_str = stderr.decode('utf-8') if stderr else ''

            self.logger.info(
                '%s [%s/%s] %s shell command completed with exit code %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                process.returncode,
            )

            if stdout_str:
                self.logger.debug(
                    '%s %s command stdout: %s',
                    self.context.imbi_project.slug,
                    action.name,
                    stdout_str,
                )
            if stderr_str:
                self.logger.debug(
                    '%s %s command stderr: %s',
                    self.context.imbi_project.slug,
                    action.name,
                    stderr_str,
                )

            if process.returncode != 0:
                error_output = stderr_str if stderr_str else stdout_str
                if action.ignore_errors:
                    self.logger.debug(
                        '%s %s shell command failed with exit %d (ignored)\n'
                        'Command: %s\nOutput: %s',
                        self.context.imbi_project.slug,
                        action.name,
                        process.returncode,
                        command_str,
                        error_output,
                    )
                else:
                    self.logger.error(
                        '%s %s shell command failed with exit %d\n'
                        'Command: %s\nOutput: %s',
                        self.context.imbi_project.slug,
                        action.name,
                        process.returncode,
                        command_str,
                        error_output,
                    )
                    raise RuntimeError(
                        f'Shell command failed with exit code '
                        f'{process.returncode}: {command_str}'
                    ) from subprocess.CalledProcessError(
                        process.returncode,
                        command_str,
                        output=stdout,
                        stderr=stderr,
                    )

        except FileNotFoundError as exc:
            raise RuntimeError(f'Command not found: {command_str}') from exc

    def _render_command(
        self,
        action: models.WorkflowShellAction,
        context: models.WorkflowContext,
    ) -> str:
        """Render command template if it contains Jinja2 syntax.

        Args:
            action: The action the command is being rendered for
            context: Workflow context for template variables

        Returns:
            Rendered command string

        """
        if prompts.has_template_syntax(action.command):
            self.logger.debug(
                '%s %s rendering templated command: %s',
                self.context.imbi_project.slug,
                action.name,
                action.command,
            )
            return prompts.render(
                context, template=action.command, **context.model_dump()
            )
        return action.command
