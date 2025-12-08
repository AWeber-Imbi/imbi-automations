# Architecture Guide

This guide provides a comprehensive overview of the Imbi Automations CLI architecture, components, and implementation patterns.

## System Overview

Imbi Automations is built on a modern async Python architecture designed for scalability, maintainability, and extensibility. The system follows a modular design with clear separation of concerns between different layers.

### Core Architecture Principles

- **Async-First**: Full async/await implementation with concurrent processing
- **Modular Design**: Clean separation between clients, models, and business logic
- **Type Safety**: Comprehensive type hints throughout the codebase
- **Configuration-Driven**: TOML-based workflows with Pydantic validation
- **Extensible**: Plugin-ready architecture for new action types and providers

## Component Architecture

### Primary Components

#### CLI Interface (`cli.py`)
The entry point for the application, responsible for:
- Command-line argument parsing and validation
- Colored logging configuration with different levels
- Workflow validation and loading
- Error handling and user feedback

#### Controller (`controller.py`)
Main automation controller implementing the iterator pattern:
- Project iteration and filtering
- Workflow orchestration across multiple targets
- Concurrent processing with proper resource management
- Progress tracking and resumption capabilities

#### Workflow Engine (`workflow_engine.py`)
Core execution engine that handles:
- Action execution with context management
- Temporary directory handling for repository operations
- Error recovery and action restart mechanisms
- Template variable resolution with Jinja2
- Comprehensive logging and status reporting

### Client Layer

The client layer provides abstraction for external service interactions:

#### HTTP Client (`clients/http.py`)
Base async HTTP client with:
- Authentication handling for various providers
- Automatic retry logic with exponential backoff
- Request/response logging with credential sanitization
- Error handling and timeout management

#### Imbi Client (`clients/imbi.py`)
Integration with Imbi project management system:
- Project data retrieval and filtering
- Environment and metadata synchronization
- Fact validation and updates via ImbiMetadataCache
- Pagination handling for large datasets

#### GitHub Client (`clients/github.py`)
GitHub API integration featuring:
- Repository and organization operations
- Pattern-aware workflow file detection
- Environment management
- Pull request creation and management
- Rate limiting and API quota management

### Data Models

All models use Pydantic for validation and type safety:

#### Configuration Models (`models/configuration.py`)

- TOML-based configuration with secret handling
- Provider-specific settings (GitHub, Imbi)
- Claude Code SDK integration settings
- Validation rules and default values

#### Workflow Models (`models/workflow.py`)

Comprehensive workflow definition including:

- **Actions**: Sequence of operations with type validation
- **Conditions**: Repository state requirements (local and remote)
- **Filters**: Project targeting and selection criteria
- **Templates**: Jinja2 template configurations

#### Provider Models

- **GitHub Models** (`models/github.py`): Repository, organization, and API response models
- **Imbi Models** (`models/imbi.py`): Project management system models

### Supporting Components

#### Imbi Metadata Cache (`imc.py`)

Cache (`ImbiMetadataCache`) for Imbi metadata with 15-minute TTL and safe-by-default design:

- Caches environments, project types, fact types
- Always initialized with empty collections (no `None` state)
- Enables parse-time validation of workflow filters
- Stored in `~/.cache/imbi-automations/metadata.json` (configurable)
- Auto-refreshes when expired via `refresh_from_cache()`
- Provides fuzzy-matched suggestions for typos
- Graceful degradation: returns empty sets when unpopulated

#### Actions Dispatcher (`actions/__init__.py`)

Centralized action execution using Python 3.12 match/case:

- Type-safe action routing to specialized handlers
- Callable, Claude, Docker, File, Git, GitHub, Imbi, Shell, Template actions
- Consistent error handling across action types

#### Git Operations (`git.py`)

Comprehensive Git integration:

- Repository cloning with authentication
- Branch management and switching
- Commit creation via Committer class
- Uses `git add --all` for staging
- Tag and version handling

#### Committer (`committer.py`)

Handles git commit operations:

- AI-powered commit message generation
- Manual commit messages with templates
- Proper author attribution
- Commit message formatting standards

#### Condition Checker (`condition_checker.py`)

Workflow condition evaluation:

- Local file system checks (post-clone)
- Remote repository checks via GitHub API (pre-clone)
- Regex pattern matching with string fallback
- Performance optimization with early filtering

#### Actions Layer (`actions/`)

Specialized action handlers:

- **Callable** (`actions/callablea.py`): Direct Python function/method invocation with async support and template rendering
- **Claude** (`actions/claude.py`): AI-powered transformations via Claude Code SDK
- **Docker** (`actions/docker.py`): Container operations and file extraction
- **File** (`actions/filea.py`): Copy (with globs), move, delete, regex replacement
- **Git** (`actions/git.py`): Revert, extract, branch management
- **GitHub** (`actions/github.py`): GitHub-specific operations
- **Imbi** (`actions/imbi.py`): Project fact management with validation
- **Shell** (`actions/shell.py`): Command execution via `subprocess_shell` (supports globs)
- **Template** (`actions/template.py`): Jinja2 rendering with workflow context

## Workflow System

### Workflow Structure

Workflows are defined in TOML configuration files with three main sections:

```toml
# Project filtering
[filter]
project_ids = [123, 456]
project_types = ["apis", "consumers"]
github_identifier_required = true

# Execution conditions
[[conditions]]
remote_file_exists = "package.json"

[[conditions]]
file_contains = "python.*3\\.12"
file = "pyproject.toml"

# Action sequence
[[actions]]
name = "update-dependencies"
type = "claude"
# ... action configuration
```

### Action Types

#### 1. Callable Actions
Direct Python function/method invocation with async support:
```toml
[[actions]]
name = "update-fact"
type = "callable"
callable = "imbi_automations.clients.imbi:Imbi.set_fact"
args = [123, "deployment_status", "completed"]
kwargs = {notes = "{{ workflow.name }} finished"}
ai_commit = true
```

#### 2. Claude Code Integration
AI-powered transformations:
```toml
[[actions]]
type = "claude"
task_prompt = "prompts/update-readme.md"
```

#### 3. File Operations
Direct file manipulation:
```toml
[[actions]]
type = "file"
command = "copy"
source = "templates/config.yml"
destination = "repository:///config/production.yml"
```

#### 4. Shell Commands
Arbitrary command execution:
```toml
[[actions]]
type = "shell"
command = "python -m pytest tests/"
working_directory = "repository:///"
```

### Condition System

#### Remote Conditions (Pre-Clone)
Evaluated using provider APIs before repository cloning:

- **Performance Benefit**: Skip cloning for non-matching repositories
- **Bandwidth Efficient**: Reduce network usage for large batch operations
- **Early Filtering**: Fail fast before expensive operations

```toml
[[conditions]]
remote_file_exists = ".github/workflows/ci.yml"

[[conditions]]
remote_file_contains = "python.*3\\.[0-9]+"
remote_file = "pyproject.toml"
```

#### Local Conditions (Post-Clone)
Evaluated after repository cloning for complex analysis:

- **Full Access**: Complete repository content available
- **Complex Patterns**: Multi-file analysis and cross-references
- **File Content Analysis**: Deep inspection of file contents

```toml
[[conditions]]
file_exists = "docker-compose.yml"

[[conditions]]
file_contains = "FROM python:3\\.[0-9]+"
file = "Dockerfile"
```

### Template System

Jinja2-based template engine with full project context:

#### Available Variables

- `{{ imbi_project }}`: Complete Imbi project data
- `{{ github_repository }}`: GitHub repository information
- `{{ workflow_name }}`: Current workflow identifier
- `{{ repository_path }}`: Local repository path
- `{{ timestamp }}`: Execution timestamp

#### Template Files

```jinja2
# Pull Request Template
## Summary
Updating {{ imbi_project.name }} to use Python {{ target_version }}

## Changes
- Updated pyproject.toml Python version requirement
- Modified GitHub Actions workflow
- Updated Dockerfile base image

Generated by: {{ workflow_name }}
Date: {{ timestamp }}
```

## Error Handling and Recovery

### Action Restart Mechanism
Actions support automatic restart on failure:
```toml
[[actions]]
name = "fragile-operation"
on_failure = "cleanup-action"  # Restart from this action
max_retries = 3
```

### Failure Indication

- **Failure Files**: Create specific failure files to signal workflow abortion
- **Detailed Logging**: Include actionable error information
- **Recovery Strategies**: Configurable retry mechanisms and `on_failure` action chains

### Resource Management

- **Temporary Directory Cleanup**: Automatic cleanup on success or failure
- **Connection Pooling**: Efficient HTTP connection reuse
- **Memory Management**: LRU caching for expensive operations

## Performance Optimizations

### Concurrent Processing

- **Batch Operations**: Process multiple projects concurrently
- **Connection Pooling**: Reuse HTTP connections across requests
- **Async Operations**: Non-blocking I/O throughout the system

### Caching Strategy

- **LRU Caching**: Cache expensive API calls and computations
- **Repository State**: Cache repository metadata between operations
- **Template Compilation**: Pre-compile Jinja2 templates

### Early Filtering

- **Remote Conditions**: Filter projects before cloning
- **Project Filtering**: Apply filters before workflow execution
- **Resumption**: Skip already processed projects

## Testing Architecture

### Test Infrastructure

- **Base Class**: `AsyncTestCase` for async test support
- **HTTP Mocking**: `httpx.MockTransport` with JSON fixtures
- **Test Isolation**: Clean state between test runs
- **Coverage Requirements**: Comprehensive test coverage with exclusions

### Mock Data Strategy

- **Path-Based Fixtures**: JSON files matching URL patterns
- **Realistic Data**: Production-like test data
- **Edge Cases**: Comprehensive error condition testing

### Integration Testing

- **End-to-End Workflows**: Complete workflow execution tests
- **Provider Integration**: Real API integration tests (optional)
- **Performance Testing**: Load and concurrency testing

## Security Considerations

### Credential Management

- **Secret Strings**: Automatic credential masking in logs
- **Configuration Validation**: Secure handling of API keys
- **Environment Variables**: Support for environment-based configuration

### API Security

- **Authentication**: Proper token and key management
- **Rate Limiting**: Respect provider API limits
- **SSL/TLS**: Secure communication with all external services

### Repository Security

- **Temporary Directories**: Secure cleanup of cloned repositories
- **File Permissions**: Proper permission handling
- **Branch Protection**: Safe branch and tag operations

## Extensibility

### Adding New Action Types
1. Create action handler in appropriate module
2. Add action type to workflow model validation
3. Implement action execution logic
4. Add comprehensive tests

### Adding New Providers
1. Implement client interface in `clients/`
2. Create provider-specific models
3. Add configuration support
4. Implement authentication and API integration

### Custom Workflows
1. Create workflow directory structure
2. Define `config.toml` with actions and conditions
3. Add template files if needed
4. Test with target projects

This architecture provides a solid foundation for scalable automation across software projects while maintaining flexibility for future enhancements and integrations.
