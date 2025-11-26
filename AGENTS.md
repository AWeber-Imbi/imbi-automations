# AGENTS.md

This file provides guidance to AI Agents like Claude Code (claude.ai/code) when working with code in this repository.

**Note**: AI assistants should maintain and update this file when making significant changes to the codebase architecture, dependencies, or development processes.

## Project Overview

Imbi Automations is a CLI framework for executing dynamic workflows across software project repositories with deep integration to the Imbi project management system and GitHub. It provides AI-powered transformations using Claude Code SDK for complex multi-file changes, automated PR creation, and comprehensive project fact management.

## Development Commands

### Setup and Dependencies
```bash
# Development setup
pip install -e .[dev]
pre-commit install

# Run the CLI
imbi-automations config.toml workflows/workflow-name --all-projects

# Resume processing from a specific project (useful for large batches)
imbi-automations config.toml workflows/workflow-name --all-projects --start-from-project my-project-slug
# or by project ID
imbi-automations config.toml workflows/workflow-name --all-projects --start-from-project 342

# Development with virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -e .[dev]
```

### Testing
```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src/imbi_automations

# Run single test file
pytest tests/test_http.py
```

### Code Quality
```bash
# Format code
ruff format

# Lint code
ruff check --fix

# Run all pre-commit hooks
pre-commit run --all-files
```

### Docker
```bash
# Build Docker image locally
docker build -t imbi-automations:latest .

# Run with Docker
docker run --rm \
  -v $(pwd)/config.toml:/config/config.toml:ro \
  -v $(pwd)/workflows:/workflows:ro \
  -v ~/.ssh:/root/.ssh:ro \
  aweber/imbi-automations:latest /config/config.toml /workflows/my-workflow --all-projects

# Use docker-compose
docker-compose run --rm aweber/imbi-automations /config/config.toml /workflows/my-workflow --all-projects
```

## CI/CD and Deployment

### GitHub Actions Workflows

The project uses GitHub Actions for automated testing, building, and deployment:

#### Test Workflow (`.github/workflows/test.yml`)
- **Trigger**: Push to main, pull requests
- **Actions**: Runs tests with pytest, linting with ruff, uploads coverage to Codecov
- **Python Versions**: 3.12

#### Docker Build Workflow (`.github/workflows/docker.yml`)
- **Trigger**: Push to main, releases, version tags, pull requests, manual dispatch
- **Actions**: Builds multi-architecture Docker images (amd64, arm64) on all triggers, but only pushes on releases
- **Registries** (releases only):
  - Docker Hub (`aweber/imbi-automations`)
  - GitHub Container Registry (`ghcr.io/aweber-imbi/imbi-automations`)
- **Tags** (releases only):
  - `latest` - Latest release
  - `1.0.0`, `1.0`, `1` - Semantic version tags from releases
- **Build Cache**: Uses GitHub Actions cache for faster builds across all triggers
- **Attestation**: Generates build provenance for both registries on releases

#### PyPI Publish Workflow (`.github/workflows/publish.yml`)
- **Trigger**: GitHub releases
- **Actions**: Builds and publishes Python package to PyPI
- **Authentication**: Uses trusted publishing (OIDC)

### Required GitHub Secrets

For automated deployments, configure these secrets in the GitHub repository:

- **`DOCKERHUB_USERNAME`** - Docker Hub account username
- **`DOCKERHUB_TOKEN`** - Docker Hub access token (from Account Settings → Security → Access Tokens)

PyPI publishing uses trusted publishing and does not require secrets.

### Release Process

1. Update version in `pyproject.toml`
2. Commit changes: `git commit -m "Bump version to X.Y.Z"`
3. Create and push tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
4. Create GitHub release with tag `vX.Y.Z`
5. GitHub Actions automatically:
   - Publishes Python package to PyPI
   - Builds and pushes Docker images with version tags to Docker Hub

## Architecture

### Core Components

#### Primary Architecture
- **CLI Interface** (`cli.py`): Argument parsing, colored logging configuration, entry point with workflow validation
- **Controller** (`controller.py`): Main automation controller implementing iterator pattern for different target types
- **Workflow Engine** (`workflow_engine.py`): Executes workflow actions with context management and temporary directory handling
- **Actions Dispatcher** (`actions/__init__.py`): Centralized action execution using match/case pattern routing
- **Claude Integration** (`claude.py`): Claude Code SDK integration for AI-powered transformations
- **Committer** (`committer.py`): Handles both AI-powered and manual git commits with proper formatting

#### Client Layer (under `clients/`)
- **HTTP Client** (`clients/http.py`): Base async HTTP client with authentication and error handling
- **Imbi Client** (`clients/imbi.py`): Integration with Imbi project management API with caching
- **GitHub Client** (`clients/github.py`): GitHub API integration with pattern-aware workflow file detection

#### Models (under `models/`)
- **Configuration** (`models/configuration.py`): TOML-based configuration with Pydantic validation
- **Workflow** (`models/workflow.py`): Comprehensive workflow definition with actions, conditions, and filters
  - **Action Types**: `callable`, `claude`, `docker`, `git`, `file`, `shell`, `utility`, `template`, `github`, `imbi`
  - **Action Stages**: `primary` (default) executes before PR, `followup` executes after PR creation
  - **Filter Validation**: Automatic validation of project_types and project_facts against ImbiMetadataCache
- **GitHub** (`models/github.py`): GitHub repository and API response models
- **Imbi** (`models/imbi.py`): Imbi project management system models including fact types, environments, and project types
  - **ImbiEnvironment**: Environment model with auto-slug generation (sanitizes special chars, normalizes spaces)
  - **ImbiProject**: Project model with `environments: list[ImbiEnvironment]` for type-safe environment handling
- **Claude** (`models/claude.py`): Claude Code integration models
- **MCP** (`models/mcp.py`): MCP (Model Context Protocol) server configuration models for workflow-defined MCP servers
- **SonarQube** (`models/sonarqube.py`): SonarQube integration models
- **Git** (`models/git.py`): Git operation models
- **Base** (`models/base.py`): Common base models and utilities
- **Validators** (`models/validators.py`): Pydantic field validators

#### Actions Layer (under `actions/`)
- **Callable Actions** (`actions/callablea.py`): Direct Python function/method invocation with intelligent async/sync detection, Jinja2 template rendering, ResourceUrl path resolution, and dynamic args/kwargs (uses `asyncio.to_thread()` for sync callables to prevent event loop blocking)
- **Claude Actions** (`actions/claude.py`): AI-powered transformations using Claude Code SDK with optional planning phase, multi-cycle validation, and intelligent error recovery
- **Docker Actions** (`actions/docker.py`): Docker container operations and file extractions
- **File Actions** (`actions/filea.py`): File manipulation (copy with glob support, move, delete, regex replacement)
- **Git Actions** (`actions/git.py`): Git operations (revert, extract, branch management)
- **GitHub Actions** (`actions/github.py`): GitHub-specific operations and integrations (sync_environments, update_repository commands)
- **Imbi Actions** (`actions/imbi.py`): Imbi project fact management (set_project_fact command)
- **Shell Actions** (`actions/shell.py`): Shell command execution with glob expansion via subprocess_shell
- **Template Actions** (`actions/template.py`): Jinja2 template rendering with full workflow context
- **Utility Actions** (`actions/utility.py`): Helper operations for common workflow tasks

#### Supporting Components
- **Imbi Metadata Cache** (`imc.py`): Cache (`ImbiMetadataCache`) for Imbi metadata (fact types, project types, environments) with 15-minute TTL, explicitly initialized via async `refresh_from_cache()` method
- **Git Operations** (`git.py`): Repository cloning, committing, and Git operations
- **Condition Checker** (`condition_checker.py`): Workflow condition evaluation system
- **Per-Project Logging** (`per_project_logging.py`): Project-specific log file management
- **Utilities** (`utils.py`): Configuration loading, directory management, URL sanitization
- **Error Handling** (`errors.py`): Custom exception classes
- **Mixins** (`mixins.py`): Reusable workflow logging functionality
- **Prompts** (`prompts.py`): AI prompt management and Jinja2 template rendering
- **Prompts Templates** (`prompts/`): Jinja2 template files for Claude Code prompts and PR generation
- **Claude Code Standards** (`claude-code/CLAUDE.md`): Standards and conventions for Claude Code actions
- **Claude Code Agents** (`claude-code/agents/`): Agent discovery and configuration files
- **Workflow Filter** (`workflow_filter.py`): Project filtering with environment and fact validation

### Configuration Structure

The tool uses TOML configuration files with Pydantic validation:

```toml
[github]
api_key = "ghp_..."
hostname = "github.com"  # Optional, defaults to github.com

[imbi]
api_key = "uuid-here"
hostname = "imbi.example.com"

[claude_code]
executable = "claude"  # Optional, defaults to 'claude'

[git]
# Optional: Git commit signing (SSH or GPG formats supported)
gpg_sign = true
gpg_format = "ssh"  # or "gpg"
signing_key = "ssh-ed25519 AAAA..."
ssh_program = "/path/to/op-ssh-sign"  # Optional for SSH signing

# Optional: Cache directory (default: ~/.cache/imbi-automations)
cache_dir = "/custom/path/to/cache"
```

**Note**: Git signing only applies to Claude Code actions. Override cache via `--cache-dir` CLI option.

### Transformation Architecture

The system supports multiple transformation types through the workflow action system:

1. **Callable Actions** (`actions/callablea.py`): Direct Python function/method invocation with intelligent async/sync detection (`asyncio.iscoroutinefunction()`), Jinja2 template rendering for string arguments, ResourceUrl path resolution, and flexible args/kwargs handling (sync callables executed via `asyncio.to_thread()` for async safety)
2. **Claude Actions** (`actions/claude.py`): Complex multi-file analysis and transformation using Claude Code SDK
3. **Docker Actions** (`actions/docker.py`): Container-based file extraction and manipulation
4. **File Actions** (`actions/filea.py`): Direct file manipulation (copy with glob patterns, move, delete, regex replacement)
5. **Git Actions** (`actions/git.py`): Version control operations (revert, extract, branch management)
6. **GitHub Actions** (`actions/github.py`): GitHub-specific operations and API integrations
7. **Imbi Actions** (`actions/imbi.py`): Imbi project fact management with validated fact names and enum values
8. **Shell Actions** (`actions/shell.py`): Shell command execution with glob expansion (uses subprocess_shell for pattern support)
9. **Template Actions** (`actions/template.py`): Jinja2-based file generation with full project context
10. **Utility Actions** (`actions/utility.py`): Helper operations for common workflow tasks

All actions are dispatched through the centralized `Actions` class (`actions/__init__.py`) which uses Python 3.12's match/case pattern for type-safe routing.

#### File Action Usage

File actions manipulate files with glob pattern support:

```toml
# Copy single file from workflow to repository
[[actions]]
name = "copy-gitignore"
type = "file"
command = "copy"
source = "workflow/.gitignore"              # From workflow directory
destination = "repository/.gitignore"       # To cloned repository

# Copy multiple files with glob pattern
[[actions]]
name = "copy-terraform-workflows"
type = "file"
command = "copy"
source = "workflow/terraform-*.yml"         # Glob pattern
destination = "repository/.github/workflows/"  # Directory

# Move file within repository
[[actions]]
name = "move-config"
type = "file"
command = "move"
source = "repository/old-config.yml"
destination = "repository/config/new-config.yml"
```

**Important Notes:**
- `source` and `destination` use ResourceUrl schemes (e.g., `repository:///`, `workflow:///`)
- Supported schemes: `repository:///`, `workflow:///`, `extracted:///`, `file:///`, `external:///`
- `external:///` scheme allows writing to absolute paths outside working directory (for exports/extracts)
- Glob patterns supported: `*`, `?`, `[...]`, `**/` for recursive
- For glob patterns, destination must be a directory
- When using `external:///`, set `committable = false` (no repository changes)

#### Template Action Usage

Template actions render Jinja2 templates with full workflow context:

```toml
[[actions]]
name = "render-config"
type = "template"
source_path = "templates"                   # Directory (recursively renders all files)
# OR
source_path = "config.yaml.j2"              # Single file
destination_path = "repository/config/"     # Relative to working directory
```

**Important Notes:**
- `source_path` is relative to workflow directory
- `destination_path` is relative to working directory (temp directory root)
- For directories, use `"ci"` not `"ci/*"` (directory rendering is automatic)
- Template context includes: `workflow`, `github_repository`, `imbi_project`, `working_directory`, `starting_commit`, `variables`

#### Utility Action Usage

Utility actions provide helper operations for common workflow tasks:

```toml
[[actions]]
name = "check-version"
type = "utility"
command = "compare_semver"
committable = false
args = ["3.9.18", "3.12.0"]
kwargs = { output = "version_check" }
```

**Available Commands:**
- `compare_semver` - Compare two semantic versions (implemented)
- `docker_tag` - Parse Docker image tags (not implemented)
- `dockerfile_from` - Extract FROM directive from Dockerfile (not implemented)
- `parse_python_constraints` - Parse Python version constraints (not implemented)

**compare_semver Command:**

Compares two semantic versions and stores a rich result object in `context.variables` for access by subsequent actions via Jinja2 templates.

**Arguments:**
- Positional: `args = ["current_version", "target_version"]`
- Or keyword: `kwargs = { current_version = "1.0.0", target_version = "2.0.0" }`
- `output` (optional): Variable name to store result (default: `semver_result`)

**Supports:**
- Standard semver: `1.2.3`, `2.0.0`
- Build numbers: `3.9.18-0`, `3.9.18-4`
- Jinja2 templates in version strings: `"{{ imbi_project.facts.get('Python Version') }}"`

**Result Object (SemverComparisonResult):**
```python
{
    "current_version": "3.9.18-0",     # Original input
    "target_version": "3.12.0",         # Original input
    "comparison": -1,                   # -1=older, 0=equal, 1=newer
    "is_older": True,                   # Convenience boolean
    "is_equal": False,                  # Convenience boolean
    "is_newer": False,                  # Convenience boolean
    "current_major": 3,                 # Parsed components
    "current_minor": 9,
    "current_patch": 18,
    "current_build": 0,                 # Build number (None if not present)
    "target_major": 3,
    "target_minor": 12,
    "target_patch": 0,
    "target_build": None
}
```

**Template Access:**
```jinja2
{% if variables.version_check.is_older %}
Upgrade needed from {{ variables.version_check.current_version }}
to {{ variables.version_check.target_version }}
{% endif %}
```

### Workflow Structure

Workflows are organized in a directory structure with TOML configuration files:

```
workflows/
├── workflow-name/
│   ├── config.toml                # Workflow definition with actions, conditions, and filters
│   └── files/                     # Optional: Template files and resources
└── another-workflow/
    └── config.toml
```

Each workflow's `config.toml` file contains:
- **Actions**: Sequence of operations to perform
- **Conditions**: Repository state requirements for execution
- **Filters**: Project targeting and filtering criteria
- **MCP Servers**: Optional MCP servers for Claude actions (see MCP Server Configuration below)

### Action Stages

Actions support a `stage` field that controls when they execute relative to PR creation:

**Stage Values:**
- **`primary`** (default): Execute before PR creation. Standard workflow actions.
- **`followup`**: Execute after PR is created. Used for monitoring CI, responding to reviewer feedback.

**Execution Flow:**
1. Primary stage actions execute sequentially with commits
2. PR is created (if `create_pull_request=true` and changes exist)
3. Followup stage actions execute with commit cycling

**Followup Stage Behavior:**
- Followup actions can commit changes (push to PR branch)
- If any followup action commits, the followup stage cycles again
- Cycles continue until no commits are made or `max_followup_cycles` is reached
- If max cycles reached without success, workflow fails

**Configuration:**
```toml
# Top-level workflow configuration
max_followup_cycles = 5  # Default: 5

[[actions]]
name = "update-deps"
type = "claude"
stage = "primary"  # Default, can be omitted
task_prompt = "prompts/update.md.j2"

[[actions]]
name = "monitor-ci"
type = "claude"
stage = "followup"
task_prompt = "prompts/monitor.md.j2"
committable = true  # Enable commits for fixes
```

**Template Context for Followup Actions:**

Followup actions receive PR information in the template context:
```jinja2
PR Number: {{ pull_request.number }}
PR URL: {{ pull_request.html_url }}
PR Branch: {{ pr_branch }}
PR State: {{ pull_request.state }}
Head SHA: {{ pull_request.head.sha }}
```

**Use Cases:**
- Monitor GitHub Actions workflow status
- Wait for CI to complete and fix failures
- Respond to automated code review comments
- Handle PR reviewer feedback

### MCP Server Configuration

Workflows can define MCP (Model Context Protocol) servers that are available to Claude Code during `claude` type action execution. MCP servers are configured at the workflow level and are automatically merged with the internal `agent_tools` MCP server.

**Supported Transport Types:**
- **stdio**: Launch MCP server as subprocess (command + args + env)
- **sse**: Connect via Server-Sent Events (url + headers)
- **http**: Connect via HTTP (url + headers)

**Environment Variable Expansion:**
MCP server configurations support shell-style environment variable expansion using `$VAR` or `${VAR}` syntax. This allows secrets and credentials to be injected from the environment rather than hardcoded in workflow files.

```toml
# Environment variables are expanded at runtime
[mcp_servers.my-postgres]
type = "stdio"
command = "uvx"
args = ["mcp-server-postgres", "${DATABASE_URL}"]

[mcp_servers.my-api]
type = "http"
url = "https://api.example.com/mcp"
headers = { Authorization = "Bearer ${API_KEY}" }
```

If a referenced environment variable is not set, a `ValueError` is raised with a clear error message.

**Example Configuration:**
```toml
name = "data-analysis-workflow"
description = "Workflow with database MCP access"

# Define MCP servers available to Claude actions
[mcp_servers.my-postgres]
type = "stdio"
command = "uvx"
args = ["mcp-server-postgres", "${DATABASE_URL}"]
env = { PG_PASSWORD = "${PG_PASSWORD}" }

[mcp_servers.my-api]
type = "http"
url = "https://api.example.com/mcp"
headers = { Authorization = "Bearer ${API_KEY}" }

[mcp_servers.my-sse-server]
type = "sse"
url = "https://api.example.com/mcp/sse"

[[actions]]
name = "analyze-data"
type = "claude"
task_prompt = "prompts/task.md.j2"
```

**Implementation Details:**
- MCP servers are defined in `models/mcp.py` with Pydantic discriminated unions
- Environment variable expansion is handled by `_expand_mcp_config()` in `claude.py`
- Servers are merged into `ClaudeAgentOptions.mcp_servers` in `claude.py`
- The `agent_tools` MCP server (for submit_planning/task/validation_response) is always included automatically
- MCP server configurations are converted to SDK-compatible dicts via `model_dump()`

### Workflow Conditions

Workflows support conditional execution based on repository state. There are two types of conditions:

#### Local Conditions (Post-Clone)
Evaluated after cloning the repository:
- **`file_exists`**: Check if a file exists (supports exact paths, glob patterns like `**/*.tf`, or regex)
- **`file_not_exists`**: Check if a file does not exist (supports exact paths, glob patterns, or regex)
- **`file_contains`**: Check if a file contains specified text or matches a regex pattern

#### Template Conditions (Post-Clone)
Evaluated after cloning using Jinja2 template expressions:
- **`when`**: Evaluate a Jinja2 template expression - if truthy, condition passes

**Template Functions Available in `when`:**
- `compare_semver(current, target)`: Compare semantic versions, returns dict with `is_older`, `is_equal`, `is_newer`
- `get_component_version(path, component)`: Extract dependency version from package.json or pyproject.toml

**Example:**
```toml
[[conditions]]
when = "{{ compare_semver(get_component_version('repository:///package.json', 'react'), '19.0.0').is_older }}"
```

**Truthiness evaluation:** `True`, `1`, `yes` → truthy; `False`, `0`, `no`, `none`, `""` → falsy

#### Remote Conditions (Pre-Clone)
Evaluated before cloning using GitHub API, providing performance benefits:
- **`remote_file_exists`**: Check if a file exists (supports exact paths or glob patterns like `**/*.tf`)
- **`remote_file_not_exists`**: Check if a file does not exist (supports exact paths or glob patterns)
- **`remote_file_contains`**: Check if a remote file contains specified text or regex pattern

**Example:**
```toml
[[conditions]]
remote_file_exists = "**/*.tf"           # Glob: any .tf file
remote_file_contains = "python:[3-4]"    # Regex supported
remote_file = "Dockerfile"

[[conditions]]
file_contains = "compose.yml"            # Local check after clone
file = "bootstrap"
```

**Performance:** Remote conditions use GitHub API (faster than clone). Use remote for filtering, local for complex analysis. Glob patterns supported via Git Trees API (100k file limit).

### Workflow Filtering

Workflows support filtering projects before execution to improve performance and target specific subsets:

```toml
[filter]
# Filter by specific project IDs
project_ids = [123, 456, 789]

# Filter by project types
project_types = ["apis", "consumers", "scheduled-jobs"]

# Filter by project facts (supports real names or slugs, validated against Registry)
project_facts = {
    "Programming Language" = "Python 3.12"  # Auto-normalized to "programming_language"
    "Framework" = "FastAPI"                 # Enum values validated at parse time
}

# Require GitHub identifier to be present
github_identifier_required = true

# Exclude projects with specific GitHub workflow statuses
exclude_github_workflow_status = ["success"]
```

**Performance:** Pre-filtering before execution. All criteria use AND logic. Fields validated at parse time using Registry cache.

### Workflow Resumability

When workflows fail with `--preserve-on-error` enabled, the system creates a `.state` file in the error directory containing all context needed to resume execution from the point of failure.

**State File Format:**
- **Format**: MessagePack binary serialization (`.state` file) using `msgpack.packb(use_bin_type=True)`
- **Purpose**: Discourage manual editing while remaining debuggable with tools like `msgpack-tools`
- **Location**: `<error-dir>/<workflow>/<project>-<timestamp>/.state`
- **Model**: `ResumeState` Pydantic model serialized to JSON-compatible dict then packed to binary

**Resume Usage:**
```bash
# Run workflow with error preservation
imbi-automations config.toml workflows/my-workflow --project-id 123 --preserve-on-error

# If workflow fails, resume from the error directory
imbi-automations config.toml workflows/my-workflow --resume ./errors/my-workflow/test-project-20251023-150000
```

**Resume State Contents** (`models/resume_state.py`):
- Workflow identification (slug, path)
- Project information (ID, slug)
- Execution state (failed action index, failed action name, completed action indices list)
- Stage tracking (current_stage: 'primary' or 'followup', followup_cycle number)
- WorkflowContext restoration data (starting commit, repository changes flag, GitHub repository model)
- PR information for followup resumption (pull_request_number, pull_request_url, pr_branch)
- Error details (message, timestamp)
- Preserved directory path (absolute path to working directory copy)
- Configuration hash (SHA256 first 16 chars to detect config changes between runs)

**Resume Behavior:**
- **Reuses preserved directory**: Exact copy of working directory with `shutil.copytree()` including symlinks
- **Retries failed action**: Starts from the action that failed (`failed_action_index`), not the next one
- **Skips condition checks**: Remote and local conditions already validated in original run
- **Skips git clone**: Repository already cloned in preserved state (only skips if resuming)
- **Configuration change detection**: Compares configuration hash, warns if differs (doesn't fail - allows recovery attempts)
- **Automatic cleanup**: Successfully resumed states cleaned up via `shutil.rmtree()` after completion
- **Action index tracking**: Completed indices tracked **per execution attempt** to avoid accumulation across retries

**Recent Critical Fixes (October 2025):**
1. **Git Commit Failure Handling** (commit 802fab7):
   - Moved git commit operation inside exception handler
   - Now preserves state when pre-commit hooks fail (e.g., ruff-format errors)
   - Previously only caught action execution failures, not subsequent commit failures

2. **Action Index Accumulation Bug** (commit 9bbf6a7):
   - Fixed `completed_action_indices` to track only actions from current execution
   - Previously accumulated indices from all previous resume attempts
   - Now correctly calculates: `range(resume_state.failed_action_index, current_idx)` for resumed runs

3. **State Preservation Order**:
   - Proper exception handling order: log error → preserve state → cleanup → raise
   - Ensures state always saved before cleanup/exit

**Benefits:** Debug failed workflows, retry after external fixes, no re-execution of successful actions, per-project debug logs in error directory.

**Limitations:** Same machine only (absolute paths), single-project only, config changes cause warnings.

## Code Style and Standards

- **Line length**: 79 characters (enforced by ruff)
- **Python version**: 3.12+ required
- **Type hints**: Required for all functions and methods
- **Quotes**: Single quotes preferred, double quotes for docstrings
- **Import organization**: Use module imports over direct class/function imports
- **Logging**: Use module-level LOGGER, colored logging for CLI applications
- **Error handling**: Use specific exception types, include context in log messages
- **Pydantic defaults**: Use mutable default literals (e.g., `field: list[int] = []`) instead of `Field(default_factory=list)` for Pydantic v2 models

## Testing Infrastructure

- **Base class**: `AsyncTestCase` inherits from `unittest.IsolatedAsyncioTestCase`
- **HTTP mocking**: Uses `httpx.MockTransport` with JSON fixture files in `tests/data/`
- **Mock data**: Path-based JSON files matching URL endpoints
- **Async support**: Full asyncio test support with proper teardown
- **Test isolation**: HTTP client instances cleared between tests

## Key Implementation Notes

- **HTTP Client Pattern**: Singleton pattern with instance caching (`_instances.clear()`)
- **URL Sanitization**: Passwords masked in logs using regex pattern replacement
- **Configuration Loading**: TOML files loaded with tomllib, validated with Pydantic
- **Colored Logging**: Uses colorlog for CLI output with different colors per log level
- **Directory Management**: Automatic parent directory creation with proper error handling
- **Authentication**: Secret string handling for API keys in configuration
- **Pattern-Aware File Detection**: GitHub client supports both exact file paths and regex patterns for workflow file detection
- **Resumable Processing**: `--start-from-project` CLI option allows resuming batch processing from a specific project slug; `--resume` flag provides full workflow resume capability (see Workflow Resumability section for details)

## Dependencies

### Runtime Dependencies
- `anthropic`: Anthropic API client for Claude integration
- `async_lru`: Async LRU cache for performance optimization
- `claude-agent-sdk`: Claude Agent SDK for AI-powered transformations
- `colorlog`: Colored logging for CLI applications
- `httpx`: Modern async HTTP client
- `jinja2`: Template engine for file generation and variable substitution
- `msgpack`: MessagePack serialization for resume state files
- `pydantic`: Data validation and configuration management
- `rich`: Rich text and progress displays
- `semver`: Semantic versioning utilities
- `truststore`: SSL certificate handling
- `yarl`: URL parsing and manipulation

### Development Dependencies
- `build`: Package building
- `coverage[toml]`: Test coverage with TOML configuration
- `mkdocs`: Documentation site generation
- `mkdocs-material`: Material theme for MkDocs
- `mkdocstrings[python]`: Auto-generated API documentation
- `pre-commit`: Git hooks for code quality
- `pytest`: Test framework
- `pytest-cov`: Test coverage integration with pytest
- `ruff`: Fast Python linter and formatter

## Claude Code Standards

All Claude Code actions follow standards defined in the `prompts/CLAUDE.md` file, including:

- **Failure Indication**: Create failure files (`ACTION_FAILED`, `{ACTION_NAME}_FAILED`, etc.) to signal workflow abortion
- **Success Indication**: No action required - successful completion is implicit when no failure files are created
- **Template Variables**: Ensure all Jinja2 variables are properly resolved in generated content
- **Error Details**: Include specific, actionable error information in failure files
- **Failure Restart**: Actions with `on_failure = "action-name"` will restart from the specified action when failure files are detected (up to 3 attempts per action)

### Planning Agent Feature

Claude actions support an optional planning phase using a dedicated planning agent that analyzes the codebase before the task agent executes changes.

**Configuration:**
```toml
[[actions]]
name = "update-python-version"
type = "claude"
planning_prompt = "prompts/planning.md.j2"  # Optional - enables planning phase
task_prompt = "prompts/task.md.j2"          # Required - task instructions (renamed from 'prompt')
validation_prompt = "prompts/validate.md.j2"  # Optional - validation instructions
max_cycles = 3
```

**Execution Flow (per cycle):**
1. **Planning Phase** (if `planning_prompt` is set):
   - Planning agent analyzes codebase using Read, Glob, Grep, Bash tools (read-only)
   - Creates structured todo list with specific, actionable task strings (not objects)
   - Provides analysis/observations about codebase structure and dependencies
   - Can signal "no work needed" by setting `skip_task=True` to skip task and validation entirely
   - Returns via `mcp__agent_tools__submit_planning_response(plan=[...], analysis="...", skip_task=False)`
   - Returns `ClaudeAgentPlanningResult` with `plan: list[str]`, `analysis: str`, and `skip_task: bool`

2. **Task Phase** (if `skip_task=False`):
   - Task agent receives plan injected into task prompt via `with-plan.md.j2` template
   - Executes changes following the structured, numbered plan
   - Has full context from planning agent's analysis
   - Claude SDK runs in `working_directory/repository/` (can access `../workflow/` and `../extracted/`)
   - Returns via `mcp__agent_tools__submit_task_response(message="...")`
   - **Skipped entirely if planning agent sets `skip_task=True`**

3. **Validation Phase** (if `validation_prompt` is set and `skip_task=False`):
   - Validator agent checks the task agent's work (read-only)
   - Returns via `mcp__agent_tools__submit_validation_response(validated=bool, errors=list)`
   - Returns `ClaudeAgentValidationResult` with `validated: bool` and `errors: list[str]`

**Key Behaviors:**
- **Plan Reset**: Task plan cleared (`self.task_plan = None`) and regenerated at the start of each cycle
- **Fresh Planning**: Each cycle gets a new plan based on current repository state (adapts to changes)
- **Skip Task**: Planning agent can set `skip_task=True` to skip task/validation when no work is needed
- **Failure Handling**: Planning failures abort the cycle immediately (no task execution)
- **Plan Injection**: Plan injected into task prompt via `with-plan.md.j2` template (similar to error injection)
- **Error Recovery**: Planning agent gets `planning-with-errors.md.j2` template instructing it to create NEW PLAN (not fix errors directly)
- **Cycle Warning**: Logs warning at 60% of max cycles (e.g., cycle 3 of 5) to indicate approaching limit

**Planning Agent Response Schema:**
```json
{
  "plan": [
    "First specific task to complete",
    "Second specific task to complete"
  ],
  "analysis": "Observations about codebase structure, patterns, dependencies, and potential challenges",
  "skip_task": false
}
```

**When to use skip_task:**
- Repository already in desired state
- Required changes already implemented
- Action not applicable to this project
- Configuration already correct
- Prevents unnecessary task execution and commits

**Recent Critical Fixes:**
1. **Batch Processing Error Handling** (November 2025 - CRITICAL):
   - Fixed `asyncio.gather()` to include `return_exceptions=True` for continue-on-error behavior
   - Previously, batch processing would abort entire run when any single project failed
   - Now properly continues processing remaining projects when `--exit-on-error` is NOT set
   - Added warning message showing success/failure counts after batch completion
   - Location: `controller.py:_process_imbi_projects_common()`

2. **Planning Agent Error Handling** (commit 561909f - CRITICAL):
   - Created `planning-with-errors.md.j2` template that explicitly instructs: "Create a NEW PLAN, do NOT fix errors yourself"
   - Planning agent was previously trying to fix errors directly instead of re-planning
   - Now properly re-analyzes and creates new task list each cycle when validation fails

3. **Claude SDK Working Directory** (commit 561909f - CRITICAL):
   - Changed SDK CWD from `working_directory` to `working_directory/repository`
   - Claude Code now operates directly in repository where modifications occur
   - Workflow and extracted directories accessible via `../workflow/` and `../extracted/`

4. **preserve_on_error Bug Fix** (commit 561909f):
   - Fixed unreachable code where `raise exc` was before preservation logic
   - Proper order now: log error → preserve if enabled → cleanup → raise
   - Error states now properly preserved for debugging

**Error Categorization:**
The `_categorize_failure()` method provides diagnostics when all cycles fail:
- `dependency_unavailable`: Package/dependency not found errors
- `constraint_conflict`: Version conflicts, incompatible requirements
- `prohibited_action`: Workflow constraints preventing action
- `test_failure`: Test failures, assertion errors
- `unknown`: No keywords matched

**Agent Files:** `claude-code/agents/{planning,task,validation}.md.j2`, `actions/prompts/{with-plan,planning-with-errors,last-error}.md.j2`

## Current Implementation Status

### Completed Features
- **Workflow Engine**: Full workflow execution with action-based processing
- **GitHub Integration**: GitHub API client with repository operations and workflow status detection
- **Imbi Integration**: Project fact management with Registry-based validation and caching
- **Batch Processing**: Concurrent processing with resumption from specific projects
- **File Operations**: Copy with glob patterns, move, delete, regex replacement, and template generation
- **AI Integration**: Claude Code SDK integration with prompt management and multi-cycle validation
- **Git Operations**: Repository cloning, branch management, and version control with git add --all
- **Configuration System**: TOML-based configuration with comprehensive validation and filter checking
- **Registry System**: Singleton cache for Imbi metadata (15-minute TTL) with parse-time validation
- **Error Handling**: Robust error recovery with action restart capabilities and per-project logging
- **Testing Infrastructure**: Comprehensive test suite (255 tests) with async support and HTTP mocking

### Future Enhancement Areas
- Transaction rollback, workflow templates, advanced filtering, monitoring integration, plugin system

## Key Implementation Details

### Imbi Metadata Cache System
The `ImbiMetadataCache` class (`imc.py`) provides caching of Imbi metadata with safe-by-default empty initialization:

**Cached Data** (stored in `~/.cache/imbi-automations/metadata.json` by default):
- **Environments**: All Imbi environments for filter validation
- **Project Types**: All project type slugs with IDs
- **Fact Types**: Complete fact type definitions with project_type_ids
- **Fact Type Enums**: All enum values for enum-type facts
- **Fact Type Ranges**: Min/max bounds for range-type facts

**Features**:
- **Safe by Default**: Cache is always populated (empty collections if not refreshed)
- **15-minute TTL**: Auto-refreshes when expired
- **Optional Initialization**: Call `await cache.refresh_from_cache(cache_file, config)` to populate from disk/API
- **Configurable Cache Location**: Override via `cache_dir` in config TOML or `--cache-dir` CLI option
- **Parse-Time Validation**: Validates filters before workflow execution
- **Handles Duplicates**: Multiple fact types with same name (different project types)
- **Property Access**: `cache.project_type_slugs`, `cache.environments`, `cache.project_fact_type_names` (returns empty sets if unpopulated)

**Usage in Validation**:
- Cache is refreshed at the start of `Automation.run()` before any validation
- WorkflowFilter validates project_types and project_facts using the cache
- Controller validates --project-type CLI argument before processing
- Provides helpful suggestions for typos
- If not refreshed, properties return empty sets (graceful degradation)

### Imbi Fact Management
Project facts support three validation modes:

1. **Enum Facts**: Values validated against allowed enum list
   - Example: "Programming Language" with values ["Python 3.9", "Python 3.12", "ES2015+", ...]
   - Multiple definitions per name (different project types get different enums)
   - Validation uses combined enum values from all definitions

2. **Range Facts**: Numeric values validated against min/max bounds
   - Example: "Test Coverage" range 0-100
   - Requires decimal or integer data type

3. **Free-Form Facts**: Type coercion only, no value constraints
   - Example: Custom notes, timestamps, version strings

**Data Types Supported**: boolean, date, decimal, integer, string, timestamp

### GitHub Environment Synchronization
The GitHub Actions module syncs repository environments with Imbi project definitions:

**Implementation** (`actions/github.py:_sync_environments`):
- Extracts environment slugs from `ImbiProject.environments` (list of `ImbiEnvironment` objects)
- Compares with existing GitHub repository environments via API
- Creates missing environments in GitHub
- Deletes extra environments from GitHub (not in Imbi)
- Uses slugified names for consistent matching (lowercase, hyphenated)

**Environment Slug Generation** (`models/imbi.py:ImbiEnvironment._set_slug`):
- Auto-generates slug from name: lowercase, sanitize special chars, normalize spaces/hyphens
- Example: "Prod (US/East)" → "prod-us-east"

**Filter Support** (`workflow_filter.py:_filter_environments`):
- Filters by environment using name OR slug matching (AND logic for multiple filters)

### GitHub Repository Updates
The GitHub Actions module provides generic repository attribute updates via the `update_repository` command:

**Implementation** (`actions/github.py:_update_repository`):
- Updates any GitHub repository attribute (description, homepage, topics, has_issues, etc.)
- Supports Jinja2 templates in attribute values (e.g., `"{{ imbi_project.description }}"`)
- Compares new values with current repository state and skips update if unchanged
- Only sends attributes that differ from current values to minimize API calls
- Uses GitHub PATCH `/repos/{org}/{repo}` endpoint

**Available Attributes**:
- `description`: Repository description
- `homepage`: Repository homepage URL
- `private`: Whether repository is private (boolean)
- `has_issues`, `has_projects`, `has_wiki`: Feature toggles (boolean)
- `default_branch`: Default branch name
- `topics`: Repository topics (array of strings)
- And other repository settings supported by GitHub API

**Workflow Example** (`workflows/sync-description/config.toml`):
```toml
[[actions]]
name = "sync-description"
type = "github"
command = "update_repository"
committable = false  # No repository changes, only API operations

[actions.attributes]
description = "{{ imbi_project.description }}"
homepage = "{{ imbi_project.urls.homepage }}"
```

**Skip Logic**: The action automatically skips updates when the new value matches the current repository attribute, logging the skip at debug level. Only changed attributes are sent in the API request.

### Shell Actions and Git Operations
- **Shell Actions**: Use `subprocess_shell` for glob expansion, env vars, pipes, Jinja2 templates
- **Git Operations**: `git add --all`, depth/branch cloning (SSH/HTTPS), AI-powered/manual commits via Committer

### External Scheme and Repository Change Tracking

**External Scheme** (`external:///`):
- Allows writing files to absolute paths outside the temporary working directory
- Useful for extracting configuration files, building collections, exporting reports
- Example: `external:///tmp/extracted-configs/{{ imbi_project.slug }}/config.yaml`
- Template variables are URL-decoded before rendering (e.g., `%7B%7B` → `{{`)
- Set `committable = false` for actions using external scheme (no repo changes)

**Repository Change Tracking**:
- `WorkflowContext.has_repository_changes` tracks if any commits were made
- `WorkflowContext.pull_request` contains GitHubPullRequest after PR creation (for followup stage)
- `WorkflowContext.pr_branch` contains branch name for PR operations
- `Committer.commit()` returns `bool` indicating if a commit was created
- Workflow engine only pushes/creates PR when `has_repository_changes = True`
- Prevents unnecessary git operations for extract-only workflows
- Skips failed push attempts when no repository modifications occurred

**Usage Example**:
```toml
# Extract configuration files for analysis
[filter]
project_types = ["apis", "consumers"]
github_identifier_required = true

[[conditions]]
remote_file_exists = "config.yaml"

[[actions]]
name = "extract-config"
type = "file"
command = "copy"
source = "repository:///config.yaml"
destination = "external:///tmp/project-configs/{{ imbi_project.slug }}/config.yaml"
committable = false  # No repository changes, so don't try to commit
```
