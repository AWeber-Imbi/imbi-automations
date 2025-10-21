"""Claude Code integration models.

Defines models for Claude Code SDK agent execution results, including
success/failure status and error messages for AI-powered transformation
workflows.
"""

import enum

import pydantic


class AgentRunResult(enum.Enum):
    """Claude agent execution result status.

    Indicates whether an agent run completed successfully or failed.
    """

    success = 'success'
    failure = 'failure'


class AgentRun(pydantic.BaseModel):
    """Claude agent execution result with status and error details.

    Contains the execution result, optional message, and list of errors
    encountered during the agent run.
    """

    result: AgentRunResult
    message: str | None = None
    errors: list[str] = []
