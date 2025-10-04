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
            case models.WorkflowImbiCommands.set_project_fact:
                await self._set_project_fact(action)
            case _:
                raise RuntimeError(f'Unsupported command: {action.command}')

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

        imbi_client = clients.Imbi.get_instance(config=self.configuration.imbi)
        project_id = self.context.imbi_project.id

        self.logger.info(
            '%s %s setting fact "%s" to "%s" for project %d (%s)',
            self.context.imbi_project.slug,
            action.name,
            action.fact_name,
            action.value,
            project_id,
            self.context.imbi_project.name,
        )

        try:
            await imbi_client.update_project_fact(
                project_id=project_id,
                fact_name=action.fact_name,
                value=action.value,
                skip_validations=action.skip_validations,
            )
            self.logger.debug(
                '%s %s successfully updated fact "%s" for project %d',
                self.context.imbi_project.slug,
                action.name,
                action.fact_name,
                project_id,
            )
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            self.logger.error(
                '%s %s failed to set fact "%s" for project %d: %s',
                self.context.imbi_project.slug,
                action.name,
                action.fact_name,
                project_id,
                exc,
            )
            raise
