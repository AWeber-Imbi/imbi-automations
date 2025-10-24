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

    The plan field accepts structured objects (dicts with task/description/
    details fields) and flattens them to simple strings for compatibility.
    """

    result: AgentRunResult
    plan: list[str] = []
    analysis: str | None = None

    @pydantic.field_validator('plan', mode='before')
    @classmethod
    def _flatten_plan_items(cls, value: typing.Any) -> list[str]:
        """Flatten structured plan items to simple strings.

        Accepts:
        - list[str]: Pass through unchanged
        - list[dict]: Flatten each dict to a string by combining fields
        - Empty list: Pass through

        Common structured formats:
        - {"step": N, "task": "...", "details": "..."}
        - {"task_id": N, "description": "...", "details": "..."}
        - {"task": "...", "description": "..."}

        This allows planning agents to return structured plan items which
        will be automatically flattened to simple task strings.
        """
        if not value:
            return []

        if not isinstance(value, list):
            return []

        flattened = []
        for item in value:
            if isinstance(item, str):
                # Already a string, keep as-is
                flattened.append(item)
            elif isinstance(item, dict):
                # Flatten dict to string
                parts = []

                # Try common field names in order of preference
                task_field = (
                    item.get('task')
                    or item.get('description')
                    or item.get('name')
                )
                details_field = item.get('details') or item.get('notes')

                if task_field:
                    parts.append(str(task_field))
                if details_field:
                    parts.append(str(details_field))

                # If we didn't find common fields, use all values
                if not parts:
                    parts = [str(v) for v in item.values() if v]

                # Combine parts with separator
                if parts:
                    flattened.append(' - '.join(parts))
            else:
                # Other types: convert to string
                flattened.append(str(item))

        return flattened

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
