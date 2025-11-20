"""File action operations for workflow execution."""

import pathlib
import re
import shutil

from imbi_automations import mixins, models, prompts, utils


class FileActions(mixins.WorkflowLoggerMixin):
    """Executes file manipulation operations with glob pattern support.

    Handles copy, move, rename, delete, append, and write operations with
    automatic directory creation and pattern matching.
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

    async def execute(self, action: models.WorkflowFileAction) -> None:
        """Execute a file action based on the command type.

        Args:
            action: File action containing the command and parameters

        Raises:
            RuntimeError: If file operation fails
            ValueError: If required parameters are missing or invalid

        """
        match action.command:
            case models.WorkflowFileActionCommand.append:
                await self._execute_append(action)
            case models.WorkflowFileActionCommand.copy:
                await self._execute_copy(action)
            case models.WorkflowFileActionCommand.delete:
                await self._execute_delete(action)
            case models.WorkflowFileActionCommand.move:
                await self._execute_move(action)
            case models.WorkflowFileActionCommand.rename:
                await self._execute_rename(action)
            case models.WorkflowFileActionCommand.write:
                await self._execute_write(action)
            case _:
                raise RuntimeError(
                    f'Unsupported file command: {action.command}'
                )

    async def _execute_append(self, action: models.WorkflowFileAction) -> None:
        """Execute append file action."""
        file_path = utils.resolve_path(
            self.context, prompts.render_path(self.context, action.path)
        )
        self.logger.debug(
            '%s [%s/%s] %s appending to file: %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.path,
        )

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Append content to file
        with file_path.open('a', encoding=action.encoding) as f:
            if isinstance(action.content, bytes):
                f.write(action.content.decode(action.encoding))
            else:
                f.write(action.content)

        self.logger.info(
            '%s [%s/%s] %s appended to %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.path,
        )

    async def _execute_copy(self, action: models.WorkflowFileAction) -> None:
        """Execute copy file action with glob pattern support."""
        source_path = utils.resolve_path(
            self.context, prompts.render_path(self.context, action.source)
        )
        dest_path = utils.resolve_path(
            self.context, prompts.render_path(self.context, action.destination)
        )
        self.logger.debug(
            '%s [%s/%s] %s copying %s to %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.source,
            action.destination,
        )

        # Check if source contains glob patterns
        if any(char in str(source_path) for char in ['*', '?', '[']):
            await self._execute_copy_glob(source_path, dest_path)
        else:
            await self._execute_copy_single(source_path, dest_path)
        self.logger.info(
            '%s [%s/%s] %s copied from %s to %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            utils.path_to_resource_url(self.context, source_path),
            utils.path_to_resource_url(self.context, dest_path),
        )

    @staticmethod
    async def _execute_copy_single(
        source_path: pathlib.Path, dest_path: pathlib.Path
    ) -> None:
        """Copy a single file or directory."""
        if not source_path.exists():
            raise RuntimeError(f'Source file does not exist: {source_path}')

        # Ensure destination directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if source_path.is_file():
            shutil.copy2(source_path, dest_path)
        elif source_path.is_dir():
            shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
        else:
            raise RuntimeError(
                f'Source path is neither file nor directory: {source_path}'
            )

    async def _execute_copy_glob(
        self, source: pathlib.Path, dest_path: pathlib.Path
    ) -> None:
        """Copy multiple files matching a glob pattern."""
        # Resolve source relative to working directory if not absolute
        if source.is_absolute():
            base_path = source.parent
            pattern = source.name
        else:
            base_path = self.context.working_directory
            pattern = str(source)

        # Find matching files
        if pattern.startswith('**/'):
            matches = list(base_path.rglob(pattern[3:]))
        else:
            matches = list(base_path.glob(pattern))

        if not matches:
            raise RuntimeError(f'No files match the source pattern: {source}')

        # Ensure destination directory exists
        dest_path.mkdir(parents=True, exist_ok=True)

        # Copy each matching file
        for match in matches:
            if match.is_file():
                dest_file = dest_path / match.name
                shutil.copy2(match, dest_file)
                self.logger.debug(
                    '%s copied %s to %s',
                    self.context.imbi_project.slug,
                    utils.path_to_resource_url(self.context, match),
                    utils.path_to_resource_url(self.context, dest_file),
                )

    async def _execute_delete(self, action: models.WorkflowFileAction) -> None:
        """Execute delete file action."""
        if action.path:
            await self._delete_by_path(action)
        elif action.pattern:
            await self._delete_by_pattern(action)

    async def _delete_by_path(self, action: models.WorkflowFileAction) -> None:
        """Delete a specific file or directory by path."""
        file_path = utils.resolve_path(
            self.context, prompts.render_path(self.context, action.path)
        )
        self.logger.debug(
            '%s %s deleting file: %s',
            self.context.imbi_project.slug,
            action.name,
            action.path,
        )

        if file_path.exists():
            if file_path.is_file():
                file_path.unlink()
            elif file_path.is_dir():
                shutil.rmtree(file_path)
            self.logger.info(
                '%s %s deleted %s',
                self.context.imbi_project.slug,
                action.name,
                utils.path_to_resource_url(self.context, file_path),
            )
        else:
            self.logger.warning(
                '%s %s did not find file to delete: %s',
                self.context.imbi_project.slug,
                action.name,
                utils.path_to_resource_url(self.context, file_path),
            )

    async def _delete_by_pattern(
        self, action: models.WorkflowFileAction
    ) -> None:
        """Delete files matching a regex pattern."""
        base_path = self.context.working_directory

        self.logger.debug(
            '%s %s deleting files matching pattern: %s',
            self.context.imbi_project.slug,
            action.name,
            action.pattern,
        )

        # Compile pattern if it's a string
        if isinstance(action.pattern, str):
            pattern = re.compile(action.pattern)
        else:
            pattern = action.pattern
            if pattern is None:
                return

        deleted_count = 0
        for file_path in base_path.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(base_path)
                if pattern.search(str(relative_path)):
                    self.logger.debug(
                        '%s %s deleting file matching pattern: %s',
                        self.context.imbi_project.slug,
                        action.name,
                        file_path,
                    )
                    file_path.unlink()
                    deleted_count += 1

        self.logger.info(
            '%s %s deleted %d files matching pattern',
            self.context.imbi_project.slug,
            action.name,
            deleted_count,
        )

    async def _execute_move(self, action: models.WorkflowFileAction) -> None:
        """Execute move file action."""
        source_path = utils.resolve_path(
            self.context, prompts.render_path(self.context, action.source)
        )
        dest_path = utils.resolve_path(
            self.context, prompts.render_path(self.context, action.destination)
        )
        self.logger.debug(
            '%s [%s/%s] %s moving %s to %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.source,
            action.destination,
        )

        if not source_path.exists():
            raise RuntimeError(f'Source file does not exist: {source_path}')

        # Ensure destination directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(source_path), str(dest_path))

        self.logger.info(
            '%s [%s/%s] %s moved %s to %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            utils.path_to_resource_url(self.context, source_path),
            utils.path_to_resource_url(self.context, dest_path),
        )

    async def _execute_rename(self, action: models.WorkflowFileAction) -> None:
        """Execute rename file action."""
        source_path = utils.resolve_path(
            self.context, prompts.render_path(self.context, action.source)
        )
        dest_path = utils.resolve_path(
            self.context, prompts.render_path(self.context, action.destination)
        )
        self.logger.debug(
            '%s [%s/%s] %s renaming %s to %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.source,
            action.destination,
        )

        if not source_path.exists():
            raise RuntimeError(f'Source file does not exist: {source_path}')

        # Ensure destination directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        source_path.rename(dest_path)

        self.logger.info(
            '%s [%s/%s] %s renamed %s to %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            utils.path_to_resource_url(self.context, source_path),
            utils.path_to_resource_url(self.context, dest_path),
        )

    async def _execute_write(self, action: models.WorkflowFileAction) -> None:
        """Execute write file action."""
        file_path = utils.resolve_path(
            self.context, prompts.render_path(self.context, action.path)
        )
        self.logger.debug(
            '%s [%s/%s] %s writing to file: %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.path,
        )

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content to file
        if isinstance(action.content, bytes):
            with file_path.open('wb') as f:
                f.write(action.content)
        else:
            with file_path.open('w', encoding=action.encoding) as f:
                f.write(action.content)

        self.logger.info(
            '%s [%s/%s] %s wrote to %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.path,
        )
