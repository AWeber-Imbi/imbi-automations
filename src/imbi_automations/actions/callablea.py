"""Callable operations for workflow execution."""

import asyncio
import typing

from imbi_automations import mixins, models, prompts, utils


class CallableAction(mixins.WorkflowLoggerMixin):
    """Executes direct method calls on client instances.

    Enables dynamic invocation of client methods with flexible arguments for
    workflow integration.
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

    async def execute(self, action: models.WorkflowCallableAction) -> None:
        """Execute a callable action based on provided configuration."""
        args = [self._process_arg(arg) for arg in action.args]
        kwargs = {
            key: self._process_arg(value)
            for key, value in action.kwargs.items()
        }
        self.logger.debug(
            'Executing %s(%r, %r)', action.callable, args, kwargs
        )
        try:
            if asyncio.iscoroutinefunction(action.callable):
                await action.callable(*args, **kwargs)
            else:
                action.callable(*args, **kwargs)
        except Exception as exc:
            self.logger.exception('Error invoking callable: %s', exc)
            raise RuntimeError(str(exc)) from exc

    def _process_arg(self, arg: typing.Any) -> typing.Any:
        """Process an argument for use in a callable."""
        if isinstance(arg, str) and prompts.has_template_syntax(arg):
            arg = prompts.render(self.context, template=arg)
        if utils.has_path_scheme(arg):
            return utils.resolve_path(self.context, arg)
        return arg
