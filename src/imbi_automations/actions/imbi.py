"""Imbi actions for workflow execution."""

import httpx

from imbi_automations import clients, mixins, models


class ImbiActions(mixins.WorkflowLoggerMixin):
    """Executes Imbi project management system operations.

    Provides integration with Imbi API for project data access and
    modification.
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

    async def execute(self, action: models.WorkflowImbiAction) -> None:
        """Execute an Imbi action.

        Args:
            action: Imbi action to execute

        Raises:
            RuntimeError: If command is not supported

        """
        match action.command:
            case models.WorkflowImbiActionCommand.set_project_fact:
                await self._set_project_fact(action)
            case models.WorkflowImbiActionCommand.set_environments:
                await self._set_environments(action)
            case _:
                raise RuntimeError(f'Unsupported command: {action.command}')

    async def _set_environments(
        self, action: models.WorkflowImbiAction
    ) -> None:
        """Set environments via Imbi API.

        Args:
            action: Action with values list of environment slugs or names

        Raises:
            ValueError: If values is missing or registry is not available
            httpx.HTTPError: If API request fails

        """
        if not action.values:
            raise ValueError('values is required for set_environments')

        if not self.context.registry:
            raise ValueError(
                'ImbiMetadataCache registry not available in context'
            )

        # Translate environment slugs/names to names
        try:
            environment_names = self.context.registry.translate_environments(
                action.values
            )
        except ValueError as exc:
            self.logger.error(
                '%s %s failed to translate environments: %s',
                self.context.imbi_project.slug,
                action.name,
                exc,
            )
            raise

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        self._log_verbose_info(
            '%s [%s/%s] %s setting environments to %s for project %d (%s)',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            environment_names,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
        )

        try:
            await client.update_project_environments(
                project_id=self.context.imbi_project.id,
                environments=environment_names,
            )
        except httpx.HTTPError as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to set environments for project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            self._log_verbose_info(
                '%s [%s/%s] %s successfully updated environments for '
                'project %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self.context.imbi_project.id,
            )

    async def _set_project_fact(
        self, action: models.WorkflowImbiAction
    ) -> None:
        """Set a project fact via Imbi API.

        Args:
            action: Action with fact_name and value

        Raises:
            ValueError: If fact_name or value is missing
            httpx.HTTPError: If API request fails

        """
        if not action.fact_name or action.value is None:
            raise ValueError(
                'fact_name and value are required for set_project_fact'
            )

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        self._log_verbose_info(
            '%s [%s/%s] %s setting fact "%s" to "%s" for project %d (%s)',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.fact_name,
            action.value,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
        )

        try:
            await client.update_project_fact(
                project_id=self.context.imbi_project.id,
                fact_name=action.fact_name,
                value=action.value,
                skip_validations=action.skip_validations,
            )
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to set fact "%s" for project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.fact_name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            self._log_verbose_info(
                '%s [%s/%s] %s successfully updated fact "%s" for project %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.fact_name,
                self.context.imbi_project.id,
            )
