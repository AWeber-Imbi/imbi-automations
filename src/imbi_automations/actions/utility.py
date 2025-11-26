"""Utility operations for workflow execution."""

from imbi_automations import mixins, models


class UtilityActions(mixins.WorkflowLoggerMixin):
    """Executes utility helper operations for common workflow tasks.

    Provides Docker tag parsing, Dockerfile analysis, and Python
    constraint parsing utilities.
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
            case models.WorkflowUtilityCommands.parse_python_constraints:
                raise NotImplementedError(
                    'Utility parse_python_constraints not yet supported'
                )
            case _:
                raise RuntimeError(f'Unsupported command: {action.command}')
