# Jinja2 Templating System

Imbi Automations uses [Jinja2](https://jinja.palletsprojects.com/) as its template engine to provide dynamic content generation across workflows, prompts, and file actions. This document describes the templating system, available context variables, and usage examples.

## Overview

The templating system enables:

- Dynamic workflow prompts with project-specific context
- Template-based file generation with full project metadata
- AI prompt customization using project facts and repository data
- Pull request and commit message generation
- Variable substitution in shell commands and Docker operations

## Template Context

All templates receive a `WorkflowContext` object that provides access to:

### Core Context Variables

#### `workflow` (Workflow)
Complete workflow definition and configuration.

**Available fields:**

- `workflow.configuration.name` - Workflow name
- `workflow.configuration.description` - Workflow description
- `workflow.configuration.prompt` - Workflow-level prompt URL/path
- `workflow.configuration.git.*` - Git configuration (checkout, depth, branch)
- `workflow.configuration.github.*` - GitHub settings (create_pull_request)
- `workflow.configuration.filter.*` - Workflow filter criteria

**Example:**
```jinja2
# Workflow: {{ workflow.configuration.name }}
{{ workflow.configuration.description }}
```

#### `imbi_project` (ImbiProject)
Complete project metadata from Imbi project management system.

**Core fields:**

- `imbi_project.id` - Project ID (integer)
- `imbi_project.name` - Human-readable project name
- `imbi_project.slug` - URL-safe project identifier (kebab-case)
- `imbi_project.description` - Project description (may be None)
- `imbi_project.namespace` - Project namespace name
- `imbi_project.namespace_slug` - Namespace slug
- `imbi_project.project_type` - Human-readable project type
- `imbi_project.project_type_slug` - Project type slug
- `imbi_project.imbi_url` - URL to project in Imbi

**Project metadata:**

- `imbi_project.dependencies` - List of dependent project IDs
- `imbi_project.environments` - List of environment names (e.g., `["development", "production"]`)
- `imbi_project.facts` - Dictionary of project facts (key-value pairs)
- `imbi_project.identifiers` - External system identifiers (GitHub, GitLab, etc.)
- `imbi_project.links` - Dictionary of external links
- `imbi_project.urls` - Dictionary of project URLs
- `imbi_project.project_score` - Project health score

**Example:**
```jinja2
Project: {{ imbi_project.name }}
Slug: {{ imbi_project.slug }}
Type: {{ imbi_project.project_type }}

{% if imbi_project.description %}
Description: {{ imbi_project.description }}
{% endif %}

{% if imbi_project.facts %}
Facts:
{% for key, value in imbi_project.facts.items() %}
  - {{ key }}: {{ value }}
{% endfor %}
{% endif %}
```

#### `github_repository` (GitHubRepository | None)
GitHub repository metadata (only available when GitHub identifier exists).

**Core fields:**

- `github_repository.id` - Repository ID
- `github_repository.name` - Repository name
- `github_repository.full_name` - Full name (org/repo)
- `github_repository.owner.login` - Owner username
- `github_repository.private` - Boolean: is private
- `github_repository.description` - Repository description
- `github_repository.html_url` - GitHub web URL
- `github_repository.ssh_url` - SSH clone URL
- `github_repository.clone_url` - HTTPS clone URL

**Additional fields:**

- `github_repository.fork` - Boolean: is fork
- `github_repository.created_at` - Creation timestamp
- `github_repository.updated_at` - Last update timestamp
- `github_repository.pushed_at` - Last push timestamp
- `github_repository.size` - Repository size in KB
- `github_repository.stargazers_count` - Star count
- `github_repository.watchers_count` - Watcher count
- `github_repository.language` - Primary language
- `github_repository.has_issues` - Boolean: issues enabled
- `github_repository.has_projects` - Boolean: projects enabled
- `github_repository.has_wiki` - Boolean: wiki enabled
- `github_repository.archived` - Boolean: is archived
- `github_repository.disabled` - Boolean: is disabled
- `github_repository.default_branch` - Default branch name

**Example:**
```jinja2
{% if github_repository %}
Repository: {{ github_repository.full_name }}
URL: {{ github_repository.html_url }}
Language: {{ github_repository.language }}
Default Branch: {{ github_repository.default_branch }}
{% endif %}
```

#### `working_directory` (pathlib.Path | None)
Absolute path to the temporary working directory containing the cloned repository.

**Example:**
```jinja2
Working directory: {{ working_directory }}
Repository location: {{ working_directory }}/repository
```

#### `starting_commit` (str | None)
Git commit SHA of the repository HEAD when workflow execution started.

**Example:**
```jinja2
Starting commit: {{ starting_commit }}
```

#### `pull_request` (GitHubPullRequest | None)
Pull request information, available only in followup stage actions after PR creation.

**Available fields:**

- `pull_request.number` - PR number (integer)
- `pull_request.html_url` - PR URL on GitHub
- `pull_request.state` - PR state ("open", "closed", "merged")
- `pull_request.title` - PR title
- `pull_request.head.sha` - Head commit SHA
- `pull_request.head.ref` - Head branch name
- `pull_request.base.ref` - Base branch name
- `pull_request.mergeable` - Whether PR can be merged (boolean or None)
- `pull_request.mergeable_state` - Merge state ("clean", "dirty", "blocked", etc.)

**Example:**
```jinja2
{% if pull_request %}
PR #{{ pull_request.number }}: {{ pull_request.html_url }}
Head SHA: {{ pull_request.head.sha }}
State: {{ pull_request.state }}
{% endif %}
```

#### `pr_branch` (str | None)
Branch name for the pull request, available only in followup stage actions.

**Example:**
```jinja2
{% if pr_branch %}
PR Branch: {{ pr_branch }}
{% endif %}
```

See [Action Stages](actions/stages.md) for followup stage documentation.

### Custom Template Functions

The templating system provides custom functions accessible within templates:

#### `read_file(file_path)`

Reads the contents of a file and returns it as a string.

**Parameters:**

- `file_path` - Path to file (supports ResourceUrl schemes: `repository:///`, `workflow:///`, `extracted:///`, etc.)

**Returns:** File contents as string

**Example:**
```jinja2
Description: {{ read_file('repository:///DESCRIPTION.txt').strip() }}
```

**Usage in Imbi actions:**
```toml
[[actions]]
name = "update-from-generated-file"
type = "imbi"
command = "update_project"
attributes = {
    description = "{{ read_file('repository:///GENERATED_DESCRIPTION.txt').strip() }}"
}
```

**Use cases:**

- Load AI-generated content from files
- Read README excerpts for descriptions
- Extract version strings from files
- Load configuration snippets

**Available in:** Template actions, Imbi action fields, Claude prompts

#### `extract_image_from_dockerfile(dockerfile_path)`
Extracts the base Docker image from a Dockerfile.

**Parameters:**

- `dockerfile_path` - Path to Dockerfile (supports `repository:///` URL scheme)

**Returns:** Base image name (e.g., `python:3.12-slim`)

**Example:**
```jinja2
Base image: {{ extract_image_from_dockerfile('repository:///Dockerfile') }}
```

**Usage in workflow:**
```toml
[[actions]]
name = "extract-constraints"
type = "docker"
command = "extract"
image = "{{ extract_image_from_dockerfile('repository:///Dockerfile') }}"
source = "/tmp/constraints.txt"
destination = "extracted:///constraints.txt"
```

#### `compare_semver(current, target)`
Compares two semantic versions and returns a dict with comparison results.

**Parameters:**

- `current` - Current version string (e.g., "18.2.0", "3.9.18-4")
- `target` - Target version string to compare against

**Returns:** Dict with:

- `is_older`: True if current < target
- `is_equal`: True if current == target
- `is_newer`: True if current > target
- `comparison`: -1 (older), 0 (equal), or 1 (newer)
- `current_major`, `current_minor`, `current_patch`, `current_build`
- `target_major`, `target_minor`, `target_patch`, `target_build`

**Version handling:**

- Strips prefixes like `v`, `^`, `~`, `>=`
- Handles partial versions (e.g., "3.9" → "3.9.0")
- Supports build numbers (e.g., "3.9.18-4")

**Example:**
```jinja2
{% set result = compare_semver('18.2.0', '19.0.0') %}
{% if result.is_older %}
Current version {{ result.current_version }} is older than {{ result.target_version }}
{% endif %}
```

**Available in:** All templates, `when` conditions

#### `get_component_version(path, component)`
Extracts a dependency version from a manifest file.

**Parameters:**

- `path` - ResourceUrl path to manifest file (e.g., "repository:///package.json")
- `component` - Name of the dependency to extract

**Supported file types:**

- `package.json`: Searches dependencies, devDependencies, peerDependencies
- `pyproject.toml`: Searches project.dependencies, optional-dependencies, Poetry dependencies

**Returns:** Clean version string without prefixes

**Example:**
```jinja2
React version: {{ get_component_version('repository:///package.json', 'react') }}
Pydantic version: {{ get_component_version('repository:///pyproject.toml', 'pydantic') }}
```

**Combined with compare_semver:**
```jinja2
{% set react_version = get_component_version('repository:///package.json', 'react') %}
{% set comparison = compare_semver(react_version, '19.0.0') %}
{% if comparison.is_older %}
React {{ react_version }} is older than 19.0.0 - upgrade recommended
{% endif %}
```

**Available in:** All templates, `when` conditions

## Template Usage

### 1. Claude Action Prompts

Claude actions use Jinja2 templates for AI prompts:

```toml
[[actions]]
name = "standardize-dunder-init"
type = "claude"
prompt = "prompts/init.md.j2"
validation_prompt = "prompts/validate-init.md.j2"
```

**Example prompt template (`prompts/init.md.j2`):**
```jinja2
# Python Package __init__.py Version Standardization

Update the package's `__init__.py` file to standardize version handling.

## Context Variables
- Project name: `{{ imbi_project.name }}`
- Package name: `{{ imbi_project.slug }}`
- Project description: `{{ imbi_project.description }}`

## Current Facts
{% if imbi_project.facts %}
{% for key, value in imbi_project.facts.items() %}
- {{ key }}: {{ value }}
{% endfor %}
{% endif %}

## Repository Information
{% if github_repository %}
- Repository: {{ github_repository.full_name }}
- Primary language: {{ github_repository.language }}
{% endif %}
```

### 2. Template Actions

Template actions render entire files or directories:

```toml
[[actions]]
name = "render-config"
type = "template"
source_path = "templates/config.yaml.j2"
destination_path = "repository:///config/app.yaml"
```

**Example template file (`templates/config.yaml.j2`):**
```jinja2
application:
  name: {{ imbi_project.name }}
  slug: {{ imbi_project.slug }}
  version: "{{ imbi_project.facts.get('Version', '0.0.0') }}"

{% if imbi_project.environments %}
environments:
{% for env in imbi_project.environments %}
  - {{ env }}
{% endfor %}
{% endif %}

{% if github_repository %}
repository:
  url: {{ github_repository.html_url }}
  default_branch: {{ github_repository.default_branch }}
{% endif %}
```

### 3. Shell Command Templating

Shell commands support inline Jinja2 templating:

```toml
[[actions]]
name = "update-version"
type = "shell"
command = "sed -i '' 's/version = .*/version = \"{{ imbi_project.facts.Version }}\"/' pyproject.toml"
```

### 4. Docker Image Extraction

Use `extract_image_from_dockerfile()` in Docker actions:

```toml
[[actions]]
name = "extract-constraints"
type = "docker"
command = "extract"
image = "{{ extract_image_from_dockerfile('repository:///Dockerfile') }}"
source = "/tmp/constraints.txt"
destination = "extracted:///constraints.txt"
```

### 5. Pull Request Generation

Pull request summaries are generated from templates with commit context:

**Template (`prompts/pull-request-summary.md.j2`):**
```jinja2
# {{ workflow.configuration.name }}

{{ workflow.configuration.description }}

## Project Details
- **Project**: {{ imbi_project.name }}
- **Type**: {{ imbi_project.project_type }}
- **Imbi URL**: {{ imbi_project.imbi_url }}

{% if github_repository %}
## Repository
- **Name**: {{ github_repository.full_name }}
- **Language**: {{ github_repository.language }}
{% endif %}

## Changes Summary
{{ summary }}
```

### 6. Directory Templates

Template actions can render entire directories recursively:

```toml
[[actions]]
name = "enforce-ci-scripts"
type = "template"
source_path = "templates/ci"
destination_path = "repository:///ci/"
```

All files in `templates/ci/` are rendered with full context and written to `repository:///ci/`.

## Resource URL Schemes

The templating system supports custom URL schemes for path resolution:

- **`repository:///`** - Files in the cloned git repository
- **`workflow:///`** - Files in the workflow directory
- **`extracted:///`** - Files extracted during workflow execution
- **`file:///`** - Absolute file system paths

**Example:**
```toml
[[actions]]
name = "copy-gitignore"
type = "file"
command = "copy"
source = "workflow:///.gitignore"
destination = "repository:///.gitignore"
```

## Jinja2 Configuration

The templating environment uses:
- **`autoescape=False`** - No HTML escaping (templates are code, not HTML)
- **`undefined=jinja2.StrictUndefined`** - Raises errors for undefined variables (fail fast)

This ensures templates fail early if variables are missing rather than silently producing incorrect output.

## Common Patterns

### Conditional Sections

```jinja2
{% if imbi_project.facts.get('Framework') %}
This project uses {{ imbi_project.facts.Framework }}.
{% endif %}

{% if github_repository and github_repository.language == 'Python' %}
Python-specific instructions...
{% endif %}
```

### Iterating Over Collections

```jinja2
{% if imbi_project.environments %}
Environments:
{% for env in imbi_project.environments %}
  - {{ env }}
{% endfor %}
{% endif %}

{% if imbi_project.facts %}
Project Facts:
{% for key, value in imbi_project.facts.items() %}
  {{ key }}: {{ value }}
{% endfor %}
{% endif %}
```

### Default Values

```jinja2
Project: {{ imbi_project.name }}
Description: {{ imbi_project.description or "No description available" }}
Version: {{ imbi_project.facts.get('Version', '0.0.0') }}
```

### Multi-line Strings

```jinja2
"""
{{ imbi_project.name }}
{{ "=" * imbi_project.name|length }}
{{ imbi_project.description or "No description" }}

"""
```

### Template Inheritance

While not commonly used in this system, Jinja2 supports template inheritance:

```jinja2
{% extends "base.md.j2" %}

{% block content %}
Project-specific content here
{% endblock %}
```

## Best Practices

1. **Use strict undefined checking** - Let templates fail on missing variables
2. **Provide defaults** - Use `or` operator or `get()` method for optional fields
3. **Check for None** - Many fields can be `None`, always check before accessing
4. **Use descriptive variable names** - Context is self-documenting
5. **Keep templates readable** - Use whitespace and comments liberally
6. **Validate template output** - Use validation prompts for Claude actions
7. **Test with multiple projects** - Different project types have different facts

## Debugging Templates

### Enable Verbose Logging

Run workflows with verbose flag to see rendered templates:

```bash
imbi-automations config.toml workflows/my-workflow --verbose --project my-project
```

### Check Template Syntax

Use `has_template_syntax()` to detect Jinja2 patterns:

```python
from imbi_automations import prompts

if prompts.has_template_syntax(command):
    # Command contains {{ }}, {% %}, or {# #}
    rendered = prompts.render(context, command, **context.model_dump())
```

### Common Errors

**`UndefinedError: 'None' has no attribute 'name'`**
- Check if object exists before accessing attributes
- Use conditional checks: `{% if github_repository %}...{% endif %}`

**`UndefinedError: 'dict object' has no attribute 'Programming_Language'`**
- Use `.get()` method for dictionary access: `imbi_project.facts.get('Programming Language')`
- Facts use spaces, not underscores in keys

**Template renders empty string**
- Check that source file exists and is readable
- Verify URL scheme is correct (`repository:///`, not `repository://`)

## Examples

### Complete Claude Action Example

**Workflow configuration:**
```toml
[[actions]]
name = "update-readme"
type = "claude"
prompt = "prompts/update-readme.md.j2"
```

**Prompt template (`prompts/update-readme.md.j2`):**
```jinja2
# README Update Task

Update the README.md file for {{ imbi_project.name }}.

## Project Information
- **Name**: {{ imbi_project.name }}
- **Type**: {{ imbi_project.project_type }}
- **Description**: {{ imbi_project.description or "No description available" }}

{% if imbi_project.facts %}
## Project Facts
{% for key, value in imbi_project.facts.items() %}
- **{{ key }}**: {{ value }}
{% endfor %}
{% endif %}

{% if github_repository %}
## Repository
- **URL**: {{ github_repository.html_url }}
- **Language**: {{ github_repository.language }}
- **Default Branch**: {{ github_repository.default_branch }}
{% endif %}

## Task
Update the README.md to reflect the current project state, including:
1. Project name and description
2. Programming language and framework
3. Build and test instructions
4. Links to relevant documentation
```

### Complete Template Action Example

**Workflow configuration:**
```toml
[[actions]]
name = "render-compose"
type = "template"
source_path = "templates/compose.yaml.j2"
destination_path = "repository:///compose.yaml"
```

**Template file (`templates/compose.yaml.j2`):**
```jinja2
version: '3.8'

services:
  {{ imbi_project.slug }}:
    build:
      context: .
      dockerfile: Dockerfile
    image: {{ imbi_project.slug }}:latest
    container_name: {{ imbi_project.slug }}

    environment:
      - APP_NAME={{ imbi_project.name }}
      - APP_SLUG={{ imbi_project.slug }}
      {% if imbi_project.facts.get('Framework') %}
      - FRAMEWORK={{ imbi_project.facts.Framework }}
      {% endif %}

    {% if imbi_project.project_type_slug in ['apis', 'web-applications'] %}
    ports:
      - "8080:8080"
    {% endif %}

    {% if imbi_project.facts.get('Database') %}
    depends_on:
      - database
    {% endif %}

    volumes:
      - .:/app

    {% if imbi_project.environments %}
    # Configured environments: {{ imbi_project.environments|join(', ') }}
    {% endif %}

{% if imbi_project.facts.get('Database') == 'PostgreSQL' %}
  database:
    image: postgres:15
    environment:
      - POSTGRES_DB={{ imbi_project.slug }}
      - POSTGRES_USER=app
      - POSTGRES_PASSWORD=secret
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  postgres-data:
{% endif %}
```

## See Also

- [Jinja2 Documentation](https://jinja.palletsprojects.com/)
- [Workflow Configuration](workflow-configuration.md) - Complete workflow configuration reference
- [Actions Reference](actions/index.md) - Action implementations and usage
