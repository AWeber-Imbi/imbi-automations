"""Claude Code integration models.

Defines models for Claude Code SDK agent execution results, including
success/failure status and error messages for AI-powered transformation
workflows.
"""

import enum

import pydantic


class ClaudeAgentType(enum.StrEnum):
    """Claude Code agent types for task execution and validation workflows."""

    planning = 'planning'
    task = 'task'
    validation = 'validation'


class ClaudeAgentPlanningResult(pydantic.BaseModel):
    """Claude planning agent result with structured plan and analysis.

    Contains the execution result, a list of planned tasks for the task agent
    to complete, and optional analysis/observations about the codebase.

    The analysis field accepts either a string or any JSON-serializable object,
    automatically converting non-string values to JSON strings for consistent
    handling.

    The plan field accepts structured objects (dicts with task/description/
    details fields) and flattens them to simple strings for compatibility.

    If skip_task is True, the task and validation agents will be skipped
    entirely, treating the action as successfully completed with no changes
    needed.
    """

    plan: list[str]
    analysis: str
    skip_task: bool = False


class ClaudeAgentTaskResult(pydantic.BaseModel):
    """
    Represents the result of an agent task.

    This class is a Pydantic model used for managing and validating data
    related to the outcome of an agent task. It encapsulates the details and
    message representing the outcome of a specific task processed by an agent.

    :ivar message: The descriptive message about the result of the agent task.
    :type message: str
    """

    message: str


class ClaudeAgentValidationResult(pydantic.BaseModel):
    """
    Represents the validation response for an agent.

    This model is used to encapsulate the results of validating an agent,
    including whether the validation was successful and any associated
    errors if the validation failed.

    :ivar validated: Indicates if the agent passed validation.
    :type validated: bool
    :ivar errors: A list of error messages generated during the validation
        process. Defaults to an empty list if there are no errors.
    :type errors: list[str]
    """

    validated: bool
    errors: list[str] = []
