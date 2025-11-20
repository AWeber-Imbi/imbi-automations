"""Reusable mixins for cross-cutting concerns.

Provides mixin classes for workflow logging functionality that can be composed
with other classes throughout the codebase.
"""

import logging
import typing

from imbi_automations import models


class WorkflowLoggerMixin:
    """Mixin for logging workflow steps."""

    def __init__(
        self, verbose: bool = False, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.verbose = verbose
        super().__init__(*args, **kwargs)

    def _log_verbose_info(
        self, message: str, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        """Log a verbose message if enabled."""
        if self.verbose:
            self.logger.info(message, *args, **kwargs)

    def _set_workflow_logger(self, workflow: models.Workflow) -> None:
        """Set logger name to workflow directory name so it's slugified"""
        self.logger = logging.getLogger(workflow.path.name)
