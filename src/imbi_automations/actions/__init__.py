"""Action execution dispatcher for workflow actions.

Provides centralized routing of workflow actions to their respective
implementation classes using Python 3.12 match/case pattern matching.
The Actions class acts as a facade that delegates action execution to
specialized handlers based on the action type.

Supported action types:
- callable: Direct method calls on client instances
- claude: AI-powered transformations using Claude Code SDK
- docker: Docker container operations and file extractions
- file: File manipulation (copy, move, regex replacement)
- git: Git operations (extract from history, clone repositories)
- github: GitHub-specific operations and API integrations
- imbi: Imbi API operations and integrations
- shell: Shell command execution with templating support
- template: Jinja2 template rendering with full workflow context
"""

import logging

from imbi_automations import mixins, models

from . import (
    callablea,
    claude,
    docker,
    filea,
    git,
    github,
    imbi,
    shell,
    template,
)

LOGGER = logging.getLogger(__name__)


class Actions(mixins.WorkflowLoggerMixin):
    """Centralized dispatcher routing workflow actions to specialized handlers.

    Uses Python 3.12 match/case pattern to delegate action execution based
    on type.
    """

    def __init__(
        self, configuration: models.Configuration, verbose: bool = False
    ) -> None:
        super().__init__(verbose)
        self.logger = LOGGER
        self.configuration = configuration

    async def execute(
        self,
        context: models.WorkflowContext,
        action: (
            models.WorkflowCallableAction
            | models.WorkflowClaudeAction
            | models.WorkflowDockerAction
            | models.WorkflowFileAction
            | models.WorkflowGitAction
            | models.WorkflowGitHubAction
            | models.WorkflowImbiAction
            | models.WorkflowShellAction
            | models.WorkflowTemplateAction
        ),
    ) -> None:
        self._set_workflow_logger(context.workflow)
        match action.type:
            case models.WorkflowActionTypes.callable:
                obj = callablea.CallableAction(
                    self.configuration, context, self.verbose
                )
            case models.WorkflowActionTypes.claude:
                obj = claude.ClaudeAction(
                    self.configuration, context, self.verbose
                )
            case models.WorkflowActionTypes.docker:
                obj = docker.DockerActions(
                    self.configuration, context, self.verbose
                )
            case models.WorkflowActionTypes.file:
                obj = filea.FileActions(
                    self.configuration, context, self.verbose
                )
            case models.WorkflowActionTypes.git:
                obj = git.GitActions(self.configuration, context, self.verbose)
            case models.WorkflowActionTypes.github:
                obj = github.GitHubActions(
                    self.configuration, context, self.verbose
                )
            case models.WorkflowActionTypes.imbi:
                obj = imbi.ImbiActions(
                    self.configuration, context, self.verbose
                )
            case models.WorkflowActionTypes.shell:
                obj = shell.ShellAction(
                    self.configuration, context, self.verbose
                )
            case models.WorkflowActionTypes.template:
                obj = template.TemplateAction(
                    self.configuration, context, self.verbose
                )
            case _:
                raise RuntimeError(f'Unsupported action type: {action.type}')

        await obj.execute(action)


__all__ = ['Actions']
