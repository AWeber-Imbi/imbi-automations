"""Claude Code integration models.

Defines models for Claude Code SDK agent execution results, including
success/failure status and error messages for AI-powered transformation
workflows. Also includes marketplace and plugin configuration models.
"""

import enum
import typing

import pydantic


class ClaudeMarketplaceSourceType(enum.StrEnum):
    """Source types for Claude Code marketplaces.

    Defines how marketplace plugin catalogs are retrieved:
    - github: Uses a GitHub repository as the source
    - git: Uses any git URL as the source
    - directory: Uses a local directory path (development only)
    """

    github = 'github'
    git = 'git'
    directory = 'directory'


class ClaudeMarketplaceSource(pydantic.BaseModel):
    """Source configuration for a Claude Code marketplace.

    Defines where to fetch the marketplace plugin catalog from.
    Only one of repo, url, or path should be specified based on source type.
    """

    source: ClaudeMarketplaceSourceType
    repo: str | None = None  # For 'github' source type
    url: str | None = None  # For 'git' source type
    path: str | None = None  # For 'directory' source type

    @pydantic.model_validator(mode='after')
    def validate_source_fields(self) -> 'ClaudeMarketplaceSource':
        """Validate that the correct field is set for the source type."""
        if self.source == ClaudeMarketplaceSourceType.github and not self.repo:
            raise ValueError("'repo' is required for 'github' source type")
        if self.source == ClaudeMarketplaceSourceType.git and not self.url:
            raise ValueError("'url' is required for 'git' source type")
        if (
            self.source == ClaudeMarketplaceSourceType.directory
            and not self.path
        ):
            raise ValueError("'path' is required for 'directory' source type")
        return self


class ClaudeMarketplace(pydantic.BaseModel):
    """Claude Code marketplace configuration.

    Defines a marketplace that provides plugins for Claude Code.

    Example:
        [marketplaces.company-tools]
        source = "github"
        repo = "company-org/claude-plugins"
    """

    source: ClaudeMarketplaceSource

    @pydantic.model_validator(mode='before')
    @classmethod
    def wrap_source(cls, data: typing.Any) -> typing.Any:
        """Allow shorthand source specification.

        Supports both:
            source = { source = "github", repo = "..." }
        And:
            source = "github"
            repo = "..."
        """
        if (
            isinstance(data, dict)
            and 'source' in data
            and isinstance(data['source'], str)
        ):
            # Shorthand format: source, repo/url/path at top level
            source_type = data.pop('source')
            source_dict = {'source': source_type}
            for key in ('repo', 'url', 'path'):
                if key in data:
                    source_dict[key] = data.pop(key)
            data['source'] = source_dict
        return data


class ClaudeLocalPlugin(pydantic.BaseModel):
    """Local plugin configuration for Claude Code SDK.

    Specifies a local plugin directory to load directly into the SDK.

    Example:
        [[local_plugins]]
        path = "/path/to/plugin"
    """

    path: str


class ClaudePluginConfig(pydantic.BaseModel):
    """Combined marketplace and plugin configuration.

    Contains all plugin-related settings for Claude Code including:
    - enabled_plugins: Map of "plugin@marketplace" to enabled state
    - marketplaces: Additional marketplace sources
    - local_plugins: Local plugin directories to load via SDK
    """

    enabled_plugins: dict[str, bool] = {}
    marketplaces: dict[str, ClaudeMarketplace] = {}
    local_plugins: list[ClaudeLocalPlugin] = []


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


class ClaudeAgentResponse(pydantic.BaseModel):
    """Unified response model for all Claude Code agents via MCP tool.

    This single model replaces SDK's structured output system with a
    tool-based approach. All fields are optional - agents populate fields
    relevant to their type.

    Field usage by agent type:
    - Planning: plan, analysis, skip_task (all optional)
    - Task: message (required)
    - Validation: validated, errors (validated required)

    The model uses extra='forbid' to catch typos and model_validate to convert
    tool args into typed Python objects.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    # Planning agent fields
    plan: list[str] | None = None
    analysis: str | None = None
    skip_task: bool = False

    # Task agent fields
    message: str | None = None

    # Validation agent fields
    validated: bool | None = None
    errors: list[str] = []
