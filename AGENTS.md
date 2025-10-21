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
  - **Filter Validation**: Automatic validation of project_types and project_facts against ImbiMetadataCache
- **GitHub** (`models/github.py`): GitHub repository and API response models
- **Imbi** (`models/imbi.py`): Imbi project management system models including fact types, environments, and project types
- **Claude** (`models/claude.py`): Claude Code integration models
- **SonarQube** (`models/sonarqube.py`): SonarQube integration models
- **Git** (`models/git.py`): Git operation models
- **Base** (`models/base.py`): Common base models and utilities
- **Validators** (`models/validators.py`): Pydantic field validators

#### Actions Layer (under `actions/`)
- **Callable Actions** (`actions/callablea.py`): Direct Python function/method invocation with async support, template rendering, and dynamic args/kwargs
- **Claude Actions** (`actions/claude.py`): AI-powered transformations using Claude Code SDK
- **Docker Actions** (`actions/docker.py`): Docker container operations and file extractions
- **File Actions** (`actions/filea.py`): File manipulation (copy with glob support, move, delete, regex replacement)
- **Git Actions** (`actions/git.py`): Git operations (revert, extract, branch management)
- **GitHub Actions** (`actions/github.py`): GitHub-specific operations and integrations
- **Imbi Actions** (`actions/imbi.py`): Imbi project fact management (set_project_fact command)
- **Shell Actions** (`actions/shell.py`): Shell command execution with glob expansion via subprocess_shell
- **Template Actions** (`actions/template.py`): Jinja2 template rendering with full workflow context
- **Utility Actions** (`actions/utility.py`): Helper operations for common workflow tasks

#### Supporting Components
- **Imbi Metadata Cache** (`imc.py`): Cache (`ImbiMetadataCache`) for Imbi metadata (fact types, project types, environments) with 15-minute TTL, explicitly initialized via async `refresh_from_cache()` method
- **Git Operations** (`git.py`): Repository cloning, committing, and Git operations
- **Environment Sync** (`environment_sync.py`): GitHub environment synchronization logic
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

# Optional: Override cache directory (default: ~/.cache/imbi-automations)
cache_dir = "/custom/path/to/cache"
```

The `cache_dir` setting can also be overridden via the `--cache-dir` CLI option.

### Transformation Architecture

The system supports multiple transformation types through the workflow action system:

1. **Callable Actions** (`actions/callablea.py`): Direct Python function/method invocation with async support, template rendering, and dynamic args/kwargs
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
- Template context includes: `workflow`, `github_repository`, `imbi_project`, `working_directory`, `starting_commit`

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

### Workflow Conditions

Workflows support conditional execution based on repository state. There are two types of conditions:

#### Local Conditions (Post-Clone)
Evaluated after cloning the repository:
- **`file_exists`**: Check if a file exists (supports exact paths, glob patterns like `**/*.tf`, or regex)
- **`file_not_exists`**: Check if a file does not exist (supports exact paths, glob patterns, or regex)
- **`file_contains`**: Check if a file contains specified text or matches a regex pattern

#### Remote Conditions (Pre-Clone)
Evaluated before cloning using GitHub API, providing performance benefits:
- **`remote_file_exists`**: Check if a file exists (supports exact paths or glob patterns like `**/*.tf`)
- **`remote_file_not_exists`**: Check if a file does not exist (supports exact paths or glob patterns)
- **`remote_file_contains`**: Check if a remote file contains specified text or regex pattern

#### File Contains Conditions (Local and Remote)

Both `file_contains` and `remote_file_contains` support string literals and regular expressions:

```toml
# Local conditions (require git clone)
[[conditions]]
file_exists = "package.json"

[[conditions]]
file_exists = "**/*.tf"  # Glob pattern - any .tf file recursively

[[conditions]]
file_not_exists = "*.pyc"  # Glob pattern - no .pyc files

[[conditions]]
file_contains = "compose.yml"
file = "bootstrap"

# Remote conditions (checked before cloning - more efficient)
[[conditions]]
remote_file_exists = "README.md"

[[conditions]]
remote_file_exists = "**/*.tf"  # Glob pattern - any .tf file recursively

[[conditions]]
remote_file_not_exists = "legacy-config.json"

[[conditions]]
remote_file_contains = "node.*18"
remote_file = ".nvmrc"

# Mixed local and remote conditions
[[conditions]]
remote_file_exists = "package.json"  # Check remotely first

[[conditions]]
file_contains = "test.*script"       # Then check locally after clone
file = "package.json"
```

#### Advanced Pattern Examples

```toml
# Version checking with regex
[[conditions]]
remote_file_contains = "\"version\":\\s*\"\\d+\\.\\d+\\.\\d+\""
remote_file = "package.json"

# Docker base image checking
[[conditions]]
remote_file_contains = "FROM python:[3-4]\\.[0-9]+"
remote_file = "Dockerfile"

# GitHub Actions workflow detection
[[conditions]]
remote_file_exists = ".github/workflows/ci.yml"

# Legacy file cleanup detection
[[conditions]]
remote_file_not_exists = ".travis.yml"  # No Travis CI
[[conditions]]
remote_file_exists = ".github/workflows"  # Has GitHub Actions
```

#### Performance Benefits

**Remote Conditions:**
- ⚡ **Faster**: GitHub API calls are faster than git clone
- 💾 **Bandwidth efficient**: Skip clone entirely for non-matching repos
- 🔄 **Early filtering**: Fail fast before expensive operations
- 🌐 **Glob support**: `remote_file_exists` and `remote_file_not_exists` support glob patterns via Git Trees API

**Best Practices:**
- Use remote conditions for initial filtering (file existence, basic content checks)
- Use local conditions for complex file analysis requiring full repository access
- Remote glob patterns (`**/*.tf`) use Git Trees API (100k file limit)
- String search is performed first (fast), with regex fallback only when string search fails
- Invalid regex patterns gracefully fall back to string search behavior

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
requires_github_identifier = true

# Exclude projects with specific GitHub workflow statuses
exclude_github_workflow_status = ["success"]
```

**Performance Benefits:**
- **Pre-filtering**: Projects are filtered before processing, not during each iteration
- **Batch efficiency**: "Found 664 total projects" → "Processing 50 filtered projects"
- **Multiple criteria**: All filter criteria must match (AND logic)
- **Early Validation**: Filter fields validated at parse time using Registry cache (catches typos before processing)

**Common Use Cases:**
```toml
# Target only Python 3.12 projects
[filter]
project_facts = {"Programming Language" = "Python 3.12"}

# Target APIs and consumers with GitHub repos
[filter]
project_types = ["apis", "consumers"]
requires_github_identifier = true

# Only process projects with failing builds (exclude working ones)
[filter]
exclude_github_workflow_status = ["success"]
```

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
- **Resumable Processing**: `--start-from-project` CLI option allows resuming batch processing from a specific project slug

## Dependencies

### Runtime Dependencies
- `anthropic`: Anthropic API client for Claude integration
- `async_lru`: Async LRU cache for performance optimization
- `claude-agent-sdk`: Claude Agent SDK for AI-powered transformations
- `colorlog`: Colored logging for CLI applications
- `httpx`: Modern async HTTP client
- `jinja2`: Template engine for file generation and variable substitution
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

## Available Workflows

The system includes 20 pre-built workflows organized by category:

### Infrastructure and Tooling (9 workflows)
- **docker-image-update**: Update base images and container configurations
- **docker-healthchecker**: Add health check configurations to Docker containers
- **dockerfile-wheel-fix**: Fix wheel installation patterns in Dockerfiles
- **python39-project-fix**: Update Python 3.9 specific configurations
- **compose-fix**: Fix Docker Compose configuration issues
- **compose-volume-fix**: Fix Docker Compose volume mount issues
- **infrastructure-services**: Infrastructure service configuration updates
- **frontend-actions**: Frontend build and deployment action updates
- **terraform-ci**: Terraform CI/CD pipeline configurations

### Code Quality and Standards (4 workflows)
- **enforce-ci-pipelines**: Ensure CI pipeline configurations are present
- **fix-workflow**: Fix broken GitHub Actions workflows
- **failing-sonarqube**: Fix failing SonarQube quality gates
- **remove-extra-ci-files**: Clean up redundant CI configuration files

### Project Maintenance (7 workflows)
- **backend-gitignore**: Apply standard backend .gitignore templates
- **frontend-gitignore**: Apply standard frontend .gitignore templates
- **restore-gitignore**: Restore .gitignore files from templates
- **ensure-github-teams**: Synchronize GitHub team access with Imbi
- **sync-project-environments**: Synchronize GitHub environments with Imbi
- **validate-github-identifier**: Validate GitHub identifier consistency
- **github-actions-status**: Check and report GitHub Actions workflow status

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

### Recent Architecture Improvements (2025)
- **GitLab Removal**: Removed GitLab client, models, and CLI arguments (GitHub-only integration)
- **Registry System**: New singleton `Registry` class for Imbi metadata caching with 15-minute TTL
- **Filter Validation**: Parse-time validation of project_types and project_facts against Registry
- **Imbi Actions**: Implemented set_project_fact command with enum/range/free-form validation
- **Shell Action Fix**: Changed to subprocess_shell for proper glob pattern expansion
- **Controller Refactoring**: Replaced `AutomationEngine` with modern `Automation` controller
- **Modular Structure**: Organized codebase into logical modules (`clients/`, `models/`, `actions/`)
- **Async Optimization**: Full async/await implementation with concurrency controls
- **Memory Optimization**: LRU caching for expensive operations
- **Type Safety**: Comprehensive type hints and Pydantic models throughout
- **External Scheme**: Added `external:///` ResourceUrl scheme for writing files outside working directory
- **Repository Change Tracking**: Workflow engine tracks repository changes, skips push/PR when no changes made

### Future Enhancement Areas
- **Transaction Rollback**: Atomic workflow operations with rollback capabilities
- **Workflow Templates**: Reusable workflow components and templates
- **Advanced Filtering**: More sophisticated project filtering and targeting
- **Monitoring Integration**: Enhanced logging and metrics collection
- **Plugin System**: Extensible action types and client providers

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

### Shell Actions
Shell actions use `subprocess_shell` instead of `subprocess_exec` to enable:
- **Glob pattern expansion**: `.github/workflows/*.yml` expands to actual files
- **Environment variable expansion**: `$HOME`, `$PATH`, etc.
- **Command chaining**: Pipes, redirects, and shell operators
- **Template support**: Jinja2 templating with workflow context

### Git Operations
- **add_files()**: Uses `git add --all` (no file list parameter)
- **Cloning**: Supports depth, branch, and SSH/HTTPS clone types
- **Commits**: Handled by Committer class (AI-powered or manual)
- **Branch Management**: Create, checkout, delete remote branches

## Recent Refactoring Summary (October 2025)

**Major Changes**:
- **GitLab Removal**: Removed all GitLab support (client, models, CLI args) - GitHub-only
- **IMC Pattern**: Introduced ImbiMetadataCache class with explicit async initialization for metadata caching
- **Cache Initialization Fix**: Removed singleton pattern, added explicit `refresh_from_cache()` method called in `Automation.run()`
- **Configurable Cache Directory**: Added `cache_dir` to Configuration model and `--cache-dir` CLI option
- **Filter Validation**: Added parse-time validation for project_types, project_facts, and environments
- **Imbi Actions**: Implemented set_project_fact with full enum/range/free-form support
- **Shell Execution Fix**: Changed from subprocess_exec to subprocess_shell for glob support
- **Controller Simplification**: Removed GitLab iterator types, streamlined validation
- **Imbi Client Updates**: Removed internal caching, simplified to use ImbiMetadataCache
- **Workflow Filter Refactor**: Split filter logic into helper methods for clarity

**Architecture Benefits**:
- **Simpler Codebase**: Removed ~2000 lines of unused GitLab code
- **Faster Validation**: ImbiMetadataCache enables instant filter validation
- **Better UX**: Helpful error messages with fuzzy-matched suggestions
- **Maintainability**: Cleaner separation with IMC handling all Imbi metadata, no singleton complexity
- **Type Safety**: Comprehensive validation at parse time prevents runtime errors
- **Performance**: 15-minute cache reduces API calls, subprocess_shell enables shell features
- **Explicit Initialization**: Clear async initialization point eliminates awkward lazy loading

### External Scheme and Repository Change Tracking (October 2025)

**External Scheme** (`external:///`):
- Allows writing files to absolute paths outside the temporary working directory
- Useful for extracting configuration files, building collections, exporting reports
- Example: `external:///tmp/extracted-configs/{{ imbi_project.slug }}/config.yaml`
- Template variables are URL-decoded before rendering (e.g., `%7B%7B` → `{{`)
- Set `committable = false` for actions using external scheme (no repo changes)

**Repository Change Tracking**:
- `WorkflowContext.has_repository_changes` tracks if any commits were made
- `Committer.commit()` returns `bool` indicating if a commit was created
- Workflow engine only pushes/creates PR when `has_repository_changes = True`
- Prevents unnecessary git operations for extract-only workflows
- Skips failed push attempts when no repository modifications occurred

**Usage Example**:
```toml
# Extract configuration files for analysis
[filter]
project_types = ["apis", "consumers"]
requires_github_identifier = true

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
