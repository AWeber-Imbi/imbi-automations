"""Workflow definition models with comprehensive action and condition support.

Defines the complete workflow structure including actions (callable, claude,
docker, file, git, github, shell, template, utility), conditions (local and
remote file checks), filters (project targeting), and workflow context for
execution state management.
"""

import enum
import pathlib
import typing

import pydantic
import pydantic_core
from pydantic import AnyUrl

from . import github, imbi, validators


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


class WorkflowFilter(pydantic.BaseModel):
    """Filter criteria for targeting specific projects in workflow execution.

    Supports filtering by project IDs, types, facts, environments, and GitHub
    workflow status to efficiently target subsets of projects.

    Note: project_facts keys are automatically normalized to slug format
    (lowercase with underscores) to match OpenSearch data format.
    """

    project_ids: set[int] = set()
    project_types: set[str] = set()
    project_facts: dict[str, str] = {}
    project_environments: set[str] = set()
    github_identifier_required: bool = False
    github_workflow_status_exclude: set[str] = set()


class WorkflowActionTypes(enum.StrEnum):
    """Enumeration of available workflow action types.

    Defines all supported action types including callable, claude, docker,
    file, git, github, imbi, shell, template, and utility actions.
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
    utility = 'utility'


class WorkflowConditionType(enum.StrEnum):
    """Condition evaluation strategy for workflows.

    Determines whether all conditions must pass (all) or any single condition
    must pass (any) for workflow execution to proceed.
    """

    all = 'all'
    any = 'any'


class WorkflowAction(pydantic.BaseModel):
    """Base class for workflow actions with common configuration.

    Provides shared fields for action identification, conditional execution,
    commit behavior, timeout management, and control flow options.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str
    type: WorkflowActionTypes = WorkflowActionTypes.callable
    ai_commit: bool = False
    commit_message: str | None = None
    conditions: list['WorkflowCondition'] = []
    condition_type: WorkflowConditionType = WorkflowConditionType.all
    committable: bool = True
    filter: WorkflowFilter | None = None
    on_success: str | None = None
    on_failure: str | None = None
    ignore_errors: bool = False
    timeout: int = 3600
    data: dict[str, typing.Any] = {}

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

    Defines available GitHub operations including environment synchronization.
    """

    sync_environments = 'sync_environments'


class WorkflowGitHubAction(WorkflowAction):
    """Action for GitHub-specific operations and integrations.

    Executes GitHub API operations including environment synchronization and
    repository management.
    """

    type: typing.Literal['github'] = 'github'
    command: WorkflowGitHubCommand
    committable: bool = False


class WorkflowImbiActionCommand(enum.StrEnum):
    """Imbi project management system operation commands.

    Defines available Imbi operations including project fact management.
    """

    set_environments = 'set_environments'
    set_project_fact = 'set_project_fact'


class WorkflowImbiAction(validators.CommandRulesMixin, WorkflowAction):
    """Action for Imbi project management system operations.

    Executes Imbi API operations including setting project facts and managing
    project metadata. These actions don't modify repository files, so
    committable defaults to False.
    """

    type: typing.Literal['imbi'] = 'imbi'
    command: WorkflowImbiActionCommand
    committable: bool = False

    # Fields for set_project_fact command
    fact_name: str | None = None
    value: bool | int | float | str | None = None
    skip_validations: bool = False

    # Attributes for set_environments command
    values: list[str] = []

    # CommandRulesMixin configuration
    command_field: typing.ClassVar[str] = 'command'
    required_fields: typing.ClassVar[dict[object, set[str]]] = {
        WorkflowImbiActionCommand.set_environments: {'values'},
        WorkflowImbiActionCommand.set_project_fact: {'fact_name', 'value'},
    }
    allowed_fields: typing.ClassVar[dict[object, set[str]]] = {
        WorkflowImbiActionCommand.set_environments: {'values'},
        WorkflowImbiActionCommand.set_project_fact: {
            'fact_name',
            'value',
            'skip_validations',
        },
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


class WorkflowUtilityCommands(enum.StrEnum):
    """Utility helper operation commands.

    Defines available utility operations including docker tag parsing,
    Dockerfile base image extraction, semver comparison, and Python
    constraint parsing.
    """

    docker_tag = 'docker_tag'
    dockerfile_from = 'dockerfile_from'
    compare_semver = 'compare_semver'
    parse_python_constraints = 'parse_python_constraints'


class WorkflowUtilityAction(WorkflowAction):
    """Action for utility helper operations and common workflow tasks.

    Provides helper operations for Docker tag parsing, Dockerfile analysis,
    version comparison, and constraint parsing with flexible arguments.
    """

    type: typing.Literal['utility'] = 'utility'
    command: WorkflowUtilityCommands
    path: ResourceUrl | None = None
    args: list[typing.Any] = []
    kwargs: dict[str, typing.Any] = {}


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
        | WorkflowUtilityAction
    ),
    pydantic.Field(discriminator='type'),
]


class WorkflowConditionRemoteClient(enum.StrEnum):
    """Remote client types for condition checking.

    Specifies which API client to use for remote file condition checks.
    """

    github = 'github'


class WorkflowCondition(validators.ExclusiveGroupsMixin, pydantic.BaseModel):
    """Workflow execution condition with local and remote file checks.

    Supports both local (post-clone) and remote (pre-clone) file existence,
    absence, and content matching with glob patterns and regex support.
    """

    file_exists: ResourceUrl | str | None = None
    file_not_exists: ResourceUrl | str | None = None
    file_contains: str | None = None
    file_doesnt_contain: str | None = None
    file: ResourceUrl | str | None = None

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
    execution conditions, filtering criteria, and action sequences.
    """

    name: str
    description: str | None = None
    prompt: ResourceUrl | None = None
    git: WorkflowGit = pydantic.Field(default_factory=WorkflowGit)
    github: WorkflowGitHub = pydantic.Field(default_factory=WorkflowGitHub)
    filter: WorkflowFilter | None = None
    use_devcontainers: bool = False

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
