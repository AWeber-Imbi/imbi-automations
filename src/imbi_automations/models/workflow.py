"""Workflow definition models with comprehensive action and condition support.

Defines the complete workflow structure including actions (callable, claude,
docker, file, git, github, imbi, shell, template), conditions (local and
remote file checks), filters (project targeting), and workflow context for
execution state management.
"""

import enum
import pathlib
import typing

import pydantic
import pydantic_core
from pydantic import AnyUrl

from . import claude as claude_models
from . import github, imbi, mcp, validators


def _ensure_file_scheme(v: str | pathlib.Path | pydantic.AnyUrl) -> str:
    if isinstance(v, pathlib.Path):
        return f'file:///{v}'
    if isinstance(v, str) and '://' not in v:
        return f'file:///{v}'
    return v


ResourceUrl: type[AnyUrl] = typing.Annotated[
    pydantic.AnyUrl,
    pydantic.BeforeValidator(_ensure_file_scheme),
    pydantic_core.core_schema.url_schema(
        allowed_schemes=[
            'extracted',
            'repository',
            'workflow',
            'file',
            'external',
        ]
    ),
]


class ProjectFieldFilter(pydantic.BaseModel):
    """Filter conditions for project fields with various operators.

    Supports checking for null values, equality, pattern matching, and
    emptiness. Only one operator should be specified per filter.
    """

    is_null: bool | None = None
    is_not_null: bool | None = None
    equals: typing.Any | None = None
    not_equals: typing.Any | None = None
    contains: str | None = None
    regex: str | None = None
    is_empty: bool | None = None

    @pydantic.model_validator(mode='after')
    def validate_single_operator(self) -> 'ProjectFieldFilter':
        """Ensure only one operator is specified."""
        operators = [
            self.is_null,
            self.is_not_null,
            self.equals,
            self.not_equals,
            self.contains,
            self.regex,
            self.is_empty,
        ]
        specified = [op for op in operators if op is not None]
        if len(specified) == 0:
            raise ValueError('At least one filter operator must be specified')
        if len(specified) > 1:
            raise ValueError('Only one filter operator can be specified')
        return self


class WorkflowFilter(pydantic.BaseModel):
    """Filter criteria for targeting specific projects in workflow execution.

    Supports filtering by project IDs, types, facts, environments, and GitHub
    workflow status to efficiently target subsets of projects.

    Note: project_facts keys are automatically normalized to slug format
    (lowercase with underscores) to match OpenSearch data format. Fact values
    can be boolean, integer, float, or string to match Imbi fact data types.
    """

    project_ids: set[int] = set()
    project_types: set[str] = set()
    project_facts: dict[str, bool | int | float | str] = {}
    project_environments: set[str] = set()
    github_identifier_required: bool = False
    github_workflow_status_exclude: set[str] = set()
    exclude_open_workflow_prs: bool | str = False
    project: dict[str, ProjectFieldFilter] = {}

    @pydantic.field_validator('exclude_open_workflow_prs')
    @classmethod
    def validate_exclude_open_workflow_prs(cls, v: bool | str) -> bool | str:
        """Validate exclude_open_workflow_prs field."""
        if isinstance(v, str) and not v:
            raise ValueError(
                'exclude_open_workflow_prs string value cannot be empty'
            )
        return v


class WorkflowActionTypes(enum.StrEnum):
    """Enumeration of available workflow action types.

    Defines all supported action types including callable, claude, docker,
    file, git, github, imbi, shell, and template actions.
    """

    callable = 'callable'
    claude = 'claude'
    docker = 'docker'
    file = 'file'
    git = 'git'
    github = 'github'
    imbi = 'imbi'
    shell = 'shell'
    template = 'template'


class WorkflowConditionType(enum.StrEnum):
    """Condition evaluation strategy for workflows.

    Determines whether all conditions must pass (all) or any single condition
    must pass (any) for workflow execution to proceed.
    """

    all = 'all'
    any = 'any'


class WorkflowActionStage(enum.StrEnum):
    """Execution stage for workflow actions.

    Primary actions execute first and can create repository changes.
    Followup actions execute after PR creation and can monitor/respond.
    """

    primary = 'primary'
    followup = 'followup'


class WorkflowAction(pydantic.BaseModel):
    """Base class for workflow actions with common configuration.

    Provides shared fields for action identification, conditional execution,
    commit behavior, timeout management, and control flow options.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str
    type: WorkflowActionTypes = WorkflowActionTypes.callable
    stage: WorkflowActionStage = WorkflowActionStage.primary
    ai_commit: bool = False
    commit_message: str | None = None
    conditions: list['WorkflowCondition'] = []
    condition_type: WorkflowConditionType = WorkflowConditionType.all
    committable: bool = True
    filter: WorkflowFilter | None = None
    on_success: str | None = None
    on_failure: str | None = None
    ignore_errors: bool = False
    timeout: str = '1h'
    data: dict[str, typing.Any] = {}

    @pydantic.field_validator('timeout')
    @classmethod
    def validate_timeout(cls, v: str) -> str:
        """Validate timeout uses Go time.Duration format."""
        try:
            import pytimeparse2

            seconds = pytimeparse2.parse(v)
            if seconds is None:
                raise ValueError(
                    f'Invalid timeout format: {v}. '
                    f'Use Go time.Duration format '
                    f'(e.g., "5m", "1h", "1h30m", "90s")'
                )
            if seconds <= 0:
                raise ValueError(
                    f'Invalid timeout value: {v}. '
                    f'Timeout must be greater than zero'
                )
        except ImportError:
            raise ValueError(
                'pytimeparse2 required for timeout parsing'
            ) from None
        return v

    @pydantic.model_validator(mode='after')
    def validate_commit_message(self) -> 'WorkflowAction':
        """Validate that commit_message is only set when ai_commit=False
        and committable=True.

        """
        if self.commit_message is not None:
            if self.ai_commit:
                raise ValueError(
                    'commit_message cannot be set when ai_commit is True'
                )
            if not self.committable:
                raise ValueError(
                    'commit_message cannot be set when committable is False'
                )
        return self


class WorkflowCallableAction(WorkflowAction):
    """Action for direct method calls on client instances.

    Executes callable methods with dynamic args and kwargs, supporting direct
    API calls and client operations with AI-powered commit messages.
    """

    type: typing.Literal['callable'] = 'callable'
    callable: pydantic.ImportString  # Expects "module.path:function_name"
    args: list[typing.Any] = []
    kwargs: dict[str, typing.Any] = {}
    ai_commit: bool = True


class WorkflowClaudeAction(WorkflowAction):
    """Action for AI-powered code transformations using Claude Code SDK.

    Executes complex multi-file analysis and transformation with prompt-based
    instructions, optional planning phase, validation cycles, and AI-generated
    commit messages.
    """

    type: typing.Literal['claude'] = 'claude'
    task_prompt: str
    planning_prompt: str | None = None
    validation_prompt: str | None = None
    max_cycles: int = 3
    ai_commit: bool = True


class WorkflowDockerActionCommand(enum.StrEnum):
    """Docker operation commands for container management.

    Defines available Docker operations including build, extract, pull,
    and push.
    """

    build = 'build'
    extract = 'extract'
    pull = 'pull'
    push = 'push'


class WorkflowDockerAction(validators.CommandRulesMixin, WorkflowAction):
    """Action for Docker container operations and file extraction.

    Supports building images, extracting files from containers, and
    pushing/pulling images with command-specific field validation.
    """

    type: typing.Literal['docker'] = 'docker'
    command: WorkflowDockerActionCommand
    image: str
    tag: str = 'latest'
    path: ResourceUrl | None = None
    source: str | pathlib.Path | None = None
    destination: ResourceUrl | None = None
    committable: bool = False

    # CommandRulesMixin configuration
    command_field: typing.ClassVar[str] = 'command'
    required_fields: typing.ClassVar[dict[object, set[str]]] = {
        WorkflowDockerActionCommand.build: {'path'},
        WorkflowDockerActionCommand.extract: {'source', 'destination'},
        WorkflowDockerActionCommand.pull: set(),
        WorkflowDockerActionCommand.push: set(),
    }
    # image and tag are always allowed; include them accordingly
    allowed_fields: typing.ClassVar[dict[object, set[str]]] = {
        WorkflowDockerActionCommand.build: {'image', 'tag', 'path'},
        WorkflowDockerActionCommand.extract: {
            'image',
            'tag',
            'source',
            'destination',
        },
        WorkflowDockerActionCommand.pull: {'image', 'tag'},
        WorkflowDockerActionCommand.push: {'image', 'tag'},
    }


class WorkflowFileActionCommand(enum.StrEnum):
    """File operation commands for manipulation and management.

    Defines available file operations including append, copy, delete, move,
    rename, and write.
    """

    append = 'append'
    copy = 'copy'
    delete = 'delete'
    move = 'move'
    rename = 'rename'
    write = 'write'


def _file_delete_requires_path_or_pattern(model: 'WorkflowFileAction') -> None:
    if (
        model.command == WorkflowFileActionCommand.delete
        and model.path is None
        and model.pattern is None
    ):
        raise ValueError(
            "Field 'path' or 'pattern' is required for command 'delete'"
        )


class WorkflowFileAction(validators.CommandRulesMixin, WorkflowAction):
    """Action for file manipulation with glob pattern support.

    Supports copying, moving, deleting, appending, and writing files with
    glob patterns, regex matching, and command-specific field validation.
    """

    type: typing.Literal['file'] = 'file'
    command: WorkflowFileActionCommand
    path: ResourceUrl | None = None
    pattern: typing.Pattern | None = None
    source: ResourceUrl | None = None
    destination: ResourceUrl | None = None
    content: str | bytes | None = None
    encoding: str = 'utf-8'

    # CommandRulesMixin configuration
    command_field: typing.ClassVar[str] = 'command'
    required_fields: typing.ClassVar[dict[object, set[str]]] = {
        WorkflowFileActionCommand.append: {'path', 'content'},
        WorkflowFileActionCommand.copy: {'source', 'destination'},
        WorkflowFileActionCommand.delete: set(),
        WorkflowFileActionCommand.move: {'source', 'destination'},
        WorkflowFileActionCommand.rename: {'source', 'destination'},
        WorkflowFileActionCommand.write: {'path', 'content'},
    }
    allowed_fields: typing.ClassVar[dict[object, set[str]]] = {
        WorkflowFileActionCommand.append: {'path', 'content', 'encoding'},
        WorkflowFileActionCommand.copy: {'source', 'destination'},
        WorkflowFileActionCommand.delete: {'path', 'pattern'},
        WorkflowFileActionCommand.move: {'source', 'destination'},
        WorkflowFileActionCommand.rename: {'source', 'destination'},
        WorkflowFileActionCommand.write: {'path', 'content', 'encoding'},
    }
    validators: typing.ClassVar[tuple] = (
        _file_delete_requires_path_or_pattern,
    )


class WorkflowGitActionCommand(enum.StrEnum):
    """Git operation commands for repository management.

    Defines available Git operations including extract and clone.
    """

    extract = 'extract'
    clone = 'clone'


class WorkflowGitActionCommitMatchStrategy(enum.StrEnum):
    """Strategy for matching commits when extracting from Git history.

    Determines whether to extract before the first or last matching commit
    when searching Git history by keyword.
    """

    before_first_match = 'before_first_match'
    before_last_match = 'before_last_match'


class WorkflowGitAction(WorkflowAction):
    """Action for Git repository operations and version control.

    Supports cloning repositories and extracting files from Git history with
    commit matching strategies and branch management.
    """

    type: typing.Literal['git'] = 'git'
    command: WorkflowGitActionCommand
    source: pathlib.Path | None = None
    destination: ResourceUrl | None = None
    url: str | None = None
    branch: str | None = None
    depth: int | None = None
    commit_keyword: str | None = None
    search_strategy: WorkflowGitActionCommitMatchStrategy | None = None
    committable: bool = False

    @pydantic.model_validator(mode='after')
    def validate_git_action_fields(self) -> 'WorkflowGitAction':
        """Validate required fields based on command type."""
        if self.command == WorkflowGitActionCommand.extract:
            self.committable = False
            if not self.source or not self.destination:
                raise ValueError(
                    'extract command requires source and destination'
                )
        elif self.command == WorkflowGitActionCommand.clone:
            self.committable = False
            if not self.url or not self.destination:
                raise ValueError('clone command requires url and destination')
        return self


class WorkflowGitHubCommand(enum.StrEnum):
    """GitHub-specific operation commands.

    Defines available GitHub operations including environment synchronization
    and repository attribute updates.
    """

    sync_environments = 'sync_environments'
    update_repository = 'update_repository'


class WorkflowGitHubAction(WorkflowAction):
    """Action for GitHub-specific operations and integrations.

    Executes GitHub API operations including environment synchronization and
    repository management.
    """

    type: typing.Literal['github'] = 'github'
    command: WorkflowGitHubCommand
    committable: bool = False

    # Fields for update_repository command
    attributes: dict[str, typing.Any] = {}


class WorkflowImbiActionCommand(enum.StrEnum):
    """Imbi project management system operation commands.

    Defines available Imbi operations including project fact management
    and generic project attribute updates.
    """

    add_project_link = 'add_project_link'
    batch_update_facts = 'batch_update_facts'
    delete_project_fact = 'delete_project_fact'
    get_project_fact = 'get_project_fact'
    set_environments = 'set_environments'
    set_project_fact = 'set_project_fact'
    update_project = 'update_project'
    update_project_type = 'update_project_type'


class WorkflowImbiAction(validators.CommandRulesMixin, WorkflowAction):
    """Action for Imbi project management system operations.

    Executes Imbi API operations including setting project facts and managing
    project metadata. These actions don't modify repository files, so
    committable defaults to False.
    """

    type: typing.Literal['imbi'] = 'imbi'
    command: WorkflowImbiActionCommand
    committable: bool = False

    # Fields for set_project_fact, get_project_fact, delete_project_fact
    fact_name: str | None = None
    value: bool | int | float | str | None = None
    skip_validations: bool = False

    # Fields for get_project_fact - variable to store the result
    variable_name: str | None = None

    # Fields for set_environments command
    values: list[str] = []

    # Fields for update_project command
    attributes: dict[str, typing.Any] = {}

    # Fields for batch_update_facts command
    facts: dict[str, bool | int | float | str] = {}

    # Fields for add_project_link command
    link_type: str | None = None
    url: str | None = None

    # Fields for update_project_type command
    project_type: str | None = None

    # CommandRulesMixin configuration
    command_field: typing.ClassVar[str] = 'command'
    required_fields: typing.ClassVar[dict[object, set[str]]] = {
        WorkflowImbiActionCommand.add_project_link: {'link_type', 'url'},
        WorkflowImbiActionCommand.batch_update_facts: {'facts'},
        WorkflowImbiActionCommand.delete_project_fact: {'fact_name'},
        WorkflowImbiActionCommand.get_project_fact: {'fact_name'},
        WorkflowImbiActionCommand.set_environments: {'values'},
        WorkflowImbiActionCommand.set_project_fact: {'fact_name', 'value'},
        WorkflowImbiActionCommand.update_project: {'attributes'},
        WorkflowImbiActionCommand.update_project_type: {'project_type'},
    }
    allowed_fields: typing.ClassVar[dict[object, set[str]]] = {
        WorkflowImbiActionCommand.add_project_link: {'link_type', 'url'},
        WorkflowImbiActionCommand.batch_update_facts: {
            'facts',
            'skip_validations',
        },
        WorkflowImbiActionCommand.delete_project_fact: {
            'fact_name',
            'skip_validations',
        },
        WorkflowImbiActionCommand.get_project_fact: {
            'fact_name',
            'variable_name',
        },
        WorkflowImbiActionCommand.set_environments: {'values'},
        WorkflowImbiActionCommand.set_project_fact: {
            'fact_name',
            'value',
            'skip_validations',
        },
        WorkflowImbiActionCommand.update_project: {'attributes'},
        WorkflowImbiActionCommand.update_project_type: {'project_type'},
    }


class WorkflowShellAction(WorkflowAction):
    """Action for shell command execution with templating support.

    Executes arbitrary shell commands with Jinja2 templating, working directory
    control, and optional error handling.
    """

    type: typing.Literal['shell'] = 'shell'
    command: str
    ignore_errors: bool = False
    working_directory: ResourceUrl = ResourceUrl('repository:///')


class WorkflowTemplateAction(WorkflowAction):
    """Action for Jinja2 template rendering with full workflow context.

    Renders template files or directories with access to workflow, repository,
    project data, and working directory paths.
    """

    type: typing.Literal['template'] = 'template'
    source: ResourceUrl | str
    destination: ResourceUrl | str


WorkflowActions = typing.Annotated[
    (
        WorkflowCallableAction
        | WorkflowClaudeAction
        | WorkflowDockerAction
        | WorkflowFileAction
        | WorkflowGitAction
        | WorkflowGitHubAction
        | WorkflowImbiAction
        | WorkflowShellAction
        | WorkflowTemplateAction
    ),
    pydantic.Field(discriminator='type'),
]


class WorkflowConditionRemoteClient(enum.StrEnum):
    """Remote client types for condition checking.

    Specifies which API client to use for remote file condition checks.
    """

    github = 'github'


class WorkflowCondition(validators.ExclusiveGroupsMixin, pydantic.BaseModel):
    """Workflow execution condition with local, remote, and template checks.

    Supports both local (post-clone) and remote (pre-clone) file existence,
    absence, and content matching with glob patterns and regex support.
    Also supports template-based conditions via the `when` field.
    """

    # Local (post-clone) file conditions
    file_exists: ResourceUrl | str | None = None
    file_not_exists: ResourceUrl | str | None = None
    file_contains: str | None = None
    file_doesnt_contain: str | None = None
    file: ResourceUrl | str | None = None

    # Template-based condition (Ansible-style)
    when: str | None = None  # Jinja2 template that must evaluate to truthy

    # Remote (pre-clone) conditions
    remote_client: WorkflowConditionRemoteClient = (
        WorkflowConditionRemoteClient.github
    )
    remote_file_exists: str | None = None
    remote_file_not_exists: str | None = None
    remote_file_contains: str | None = None
    remote_file_doesnt_contain: str | None = None
    remote_file: pathlib.Path | None = None

    # ExclusiveGroupsMixin configuration
    variants_a: typing.ClassVar[tuple[validators.Variant, ...]] = (
        validators.Variant(name='file_exists', requires_all=('file_exists',)),
        validators.Variant(
            name='file_not_exists', requires_all=('file_not_exists',)
        ),
        validators.Variant(
            name='file_contains',
            requires_all=('file_contains', 'file'),
            paired=(('file_contains', 'file'),),
        ),
        validators.Variant(
            name='file_doesnt_contain',
            requires_all=('file_doesnt_contain', 'file'),
            paired=(('file_doesnt_contain', 'file'),),
        ),
        validators.Variant(name='when', requires_all=('when',)),
    )

    variants_b: typing.ClassVar[tuple[validators.Variant, ...]] = (
        validators.Variant(
            name='remote_file_exists', requires_all=('remote_file_exists',)
        ),
        validators.Variant(
            name='remote_file_not_exists',
            requires_all=('remote_file_not_exists',),
        ),
        validators.Variant(
            name='remote_file_contains',
            requires_all=('remote_file_contains', 'remote_file'),
            paired=(('remote_file_contains', 'remote_file'),),
        ),
        validators.Variant(
            name='remote_file_doesnt_contain',
            requires_all=('remote_file_doesnt_contain', 'remote_file'),
            paired=(('remote_file_doesnt_contain', 'remote_file'),),
        ),
    )


class WorkflowGitCloneType(enum.StrEnum):
    """Git clone protocol type.

    Specifies the protocol to use for cloning repositories (HTTP or SSH).
    """

    http = 'http'
    ssh = 'ssh'


class WorkflowGit(pydantic.BaseModel):
    """Git configuration for workflow repository operations.

    Controls repository cloning behavior including depth, branch selection,
    protocol type, and CI skip check handling.
    """

    clone: bool = True
    depth: int = 1
    ref: str | None = None
    starting_branch: str | None = None
    ci_skip_checks: bool = False
    clone_type: WorkflowGitCloneType = WorkflowGitCloneType.ssh


class WorkflowGitHub(pydantic.BaseModel):
    """GitHub workflow configuration for pull request management.

    Controls pull request creation and branch replacement behavior with
    validation ensuring consistent configuration.
    """

    create_pull_request: bool = True
    replace_branch: bool = False

    @pydantic.model_validator(mode='after')
    def validate_replace_branch(self) -> 'WorkflowGitHub':
        if self.replace_branch and not self.create_pull_request:
            raise ValueError(
                'replace_branch requires create_pull_request to be True'
            )
        return self


class WorkflowConfiguration(pydantic.BaseModel):
    """Complete workflow configuration with actions, conditions, and filters.

    Defines the full workflow structure including provider configurations,
    execution conditions, filtering criteria, action sequences, and
    Claude Code plugin settings.

    Workflow-level plugin configuration merges with main config settings:
    - enabled_plugins: Merged with main config (workflow can enable/disable)
    - marketplaces: Merged with main config (workflow can add more)
    - local_plugins: Concatenated with main config plugins

    Example TOML:
        [plugins.enabled_plugins]
        "workflow-specific-plugin@marketplace" = true

        [plugins.marketplaces.workflow-marketplace]
        source = "github"
        repo = "org/workflow-plugins"
    """

    name: str
    description: str | None = None
    prompt: ResourceUrl | None = None
    git: WorkflowGit = pydantic.Field(default_factory=WorkflowGit)
    github: WorkflowGitHub = pydantic.Field(default_factory=WorkflowGitHub)
    filter: WorkflowFilter | None = None
    mcp_servers: dict[str, mcp.McpServerConfig] = {}
    plugins: claude_models.ClaudePluginConfig = pydantic.Field(
        default_factory=claude_models.ClaudePluginConfig
    )
    use_devcontainers: bool = False
    max_followup_cycles: int = 5

    condition_type: WorkflowConditionType = WorkflowConditionType.all
    conditions: list[WorkflowCondition] = []
    actions: list[WorkflowActions] = []


class WorkflowActionResult(pydantic.BaseModel):
    """Result information for a completed workflow action.

    Contains the action name for tracking and reporting execution results.
    """

    name: str


class Workflow(pydantic.BaseModel):
    """Complete workflow definition with path, configuration, and slug.

    Represents a loaded workflow from disk with automatic slug generation
    from the directory name if not explicitly provided.
    """

    path: pathlib.Path
    configuration: WorkflowConfiguration
    slug: str | None = None

    @pydantic.model_validator(mode='after')
    def _set_slug(self) -> 'Workflow':
        if not self.slug:
            self.slug = self.path.name.lower().replace('_', '-')
        return self


class WorkflowContext(pydantic.BaseModel):
    """Template context for workflow execution with type safety."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    workflow: Workflow
    github_repository: github.GitHubRepository | None = None
    imbi_project: imbi.ImbiProject
    working_directory: pathlib.Path
    starting_commit: str | None = None
    has_repository_changes: bool = False
    registry: typing.Any = None  # ImbiMetadataCache (avoid circular import)
    current_action_index: int | None = None  # 1-indexed position in workflow
    total_actions: int | None = None  # Total actions in workflow

    # PR information (populated after PR creation, available in followup stage)
    pull_request: github.GitHubPullRequest | None = None
    pr_branch: str | None = None

    # Custom variables set by actions (e.g., get_project_fact)
    variables: dict[str, typing.Any] = {}
