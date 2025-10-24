"""Claude Code integration models.

Defines models for Claude Code SDK agent execution results, including
success/failure status and error messages for AI-powered transformation
workflows.
"""

import enum
import json
import typing

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

    Extra fields (like 'plan', 'analysis' from planning agents) are preserved
    and accessible via model_extra.
    """

    model_config = pydantic.ConfigDict(extra='allow')

    result: AgentRunResult
    message: str | None = None
    errors: list[str] = []


class AgentPlan(pydantic.BaseModel):
    """Claude planning agent result with structured plan and analysis.

    Contains the execution result, a list of planned tasks for the task agent
    to complete, and optional analysis/observations about the codebase.

    The analysis field accepts either a string or any JSON-serializable object,
    automatically converting non-string values to JSON strings for consistent
    handling.
    """

    result: AgentRunResult
    plan: list[str] = []
    analysis: str | None = None

    @pydantic.field_validator('analysis', mode='before')
    @classmethod
    def _serialize_analysis(cls, value: typing.Any) -> str | None:
        """Convert analysis to string if it's a dict or other structure.

        Accepts:
        - None: Pass through
        - str: Pass through
        - dict/list/other: Convert to JSON string

        This allows planning agents to return structured analysis that will
        be automatically serialized for consistent string handling.
        """
        if value is None or isinstance(value, str):
            return value
        try:
            return json.dumps(value, indent=2)
        except (TypeError, ValueError):
            # If serialization fails, convert to string
            return str(value)
