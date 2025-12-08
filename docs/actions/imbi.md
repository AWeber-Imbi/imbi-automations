# Imbi Actions

Imbi actions provide integration with the Imbi project management system, enabling workflows to interact with and update project metadata, facts, and configurations.

## Configuration

```toml
[[actions]]
name = "action-name"
type = "imbi"
command = "set_project_fact"  # Required
```

## Available Commands

### set_environments

Updates the list of environments for the current project in Imbi.

**Configuration:**
```toml
[[actions]]
name = "set-environments"
type = "imbi"
command = "set_environments"
values = ["testing", "staging", "production"]
```

**Fields:**

- `values` (list of strings, required): List of environment names or slugs to set for the project

**Features:**  

- **Flexible Input**: Accepts both environment names (e.g., "Testing") and slugs (e.g., "testing")
- **Smart Updates**: Only makes API calls when environments actually differ from current state
- **Automatic Translation**: Converts environment slugs to names using ImbiMetadataCache
- **Non-Committable**: Does not create git commits (modifies Imbi state only)

**Use Cases:**  

- Standardize environments across projects
- Sync environment configuration after infrastructure changes
- Set up new projects with standard environment set
- Update environments as part of deployment pipeline setup

**Example:**

```toml
[[actions]]
name = "set-standard-environments"
type = "imbi"
command = "set_environments"
values = ["testing", "staging", "production"]

[[actions]]
name = "sync-to-github"
type = "github"
command = "sync_environments"
```

### update_project

Updates one or more project attributes in Imbi using a generic, flexible approach.

**Configuration:**
```toml
[[actions]]
name = "update-project-metadata"
type = "imbi"
command = "update_project"
attributes = {
    description = "REST API for user authentication and profile management",
    name = "{{ imbi_project.name }} v2"
}
```

**Fields:**

- `attributes` (dict, required): Dictionary of attribute names to new values. Keys should match ImbiProject model fields (e.g., `description`, `name`, `namespace`, etc.). String values support Jinja2 templates.

**Features:**  

- **Generic Updates**: Update any project attribute in a single action
- **Template Support**: String values support full Jinja2 templating with workflow context
- **Smart Updates**: Only sends PATCH requests for attributes that have changed
- **Batch Operations**: Update multiple attributes in a single API call
- **HTTP 304 Handling**: Properly handles "Not Modified" responses
- **Non-Committable**: Does not create git commits (modifies Imbi state only)

**Available Attributes:**

Project attributes that can be updated:
- `description` - Project description text
- `name` - Project display name
- Any other writable field on the ImbiProject model

**Use Cases:**  

- Update project metadata after repository analysis
- Sync project information with repository changes
- Standardize project attributes across organization
- Update multiple fields atomically
- Generate descriptions using AI (Claude actions)

**Basic Example:**
```toml
[[actions]]
name = "update-description"
type = "imbi"
command = "update_project"
attributes = {
    description = "Python API for {{ imbi_project.name }}"
}
```

**With File Reading:**
```toml
[[actions]]
name = "generate-description-with-ai"
type = "claude"
task_prompt = "prompts/generate-description.md"
committable = false

[[actions]]
name = "update-from-generated-file"
type = "imbi"
command = "update_project"
attributes = {
    description = "{{ read_file('repository:///GENERATED_DESCRIPTION.txt').strip() }}"
}

[[actions.conditions]]
file_exists = "repository:///GENERATED_DESCRIPTION.txt"
```

**From README:**
```toml
[[actions]]
name = "sync-metadata-from-repo"
type = "imbi"
command = "update_project"
attributes = {
    description = "{{ read_file('repository:///README.md').split('\\n')[2] }}",
    name = "{{ imbi_project.namespace }} / {{ imbi_project.slug }}"
}
```

**Multiple Attributes:**
```toml
[[actions]]
name = "update-project-info"
type = "imbi"
command = "update_project"
attributes = {
    description = "{{ imbi_project.description | default('No description') }}",
    name = "{{ imbi_project.name }} (Production Ready)"
}
```

### set_project_fact

Updates or creates a fact for the current project in Imbi.

**Configuration:**
```toml
[[actions]]
name = "update-python-version"
type = "imbi"
command = "set_project_fact"
fact_name = "Python Version"
value = "3.12"
```

**Fields:**

- `fact_name` (string, required): Name of the fact to set
- `value` (string|number|boolean, required): Value to assign to the fact
- `skip_validations` (boolean, optional): Skip fact validation (default: false)

**Use Cases:**

- Update project metadata after automated changes
- Track migration status across projects
- Record version upgrades or dependency changes
- Maintain synchronization between repository state and Imbi

### get_project_fact

Retrieves a fact value from the current project and optionally stores it in a workflow variable for use in subsequent actions.

**Configuration:**
```toml
[[actions]]
name = "get-language"
type = "imbi"
command = "get_project_fact"
fact_name = "Programming Language"
variable_name = "current_language"  # Optional
```

**Fields:**

- `fact_name` (string, required): Name of the fact to retrieve
- `variable_name` (string, optional): Variable name to store the result for use in templates

**Use Cases:**

- Retrieve current fact values for conditional logic
- Store fact values for use in subsequent action templates
- Log or audit current project state before making changes

**Example with Variable:**
```toml
[[actions]]
name = "get-current-version"
type = "imbi"
command = "get_project_fact"
fact_name = "Python Version"
variable_name = "old_version"

[[actions]]
name = "log-upgrade"
type = "shell"
command = "echo 'Upgrading from {{ variables.old_version }} to 3.12'"
```

### delete_project_fact

Removes a fact from the current project.

**Configuration:**
```toml
[[actions]]
name = "remove-obsolete-fact"
type = "imbi"
command = "delete_project_fact"
fact_name = "Legacy Framework"
```

**Fields:**

- `fact_name` (string, required): Name of the fact to delete
- `skip_validations` (boolean, optional): Skip validation (default: false)

**Use Cases:**

- Remove obsolete facts after migrations
- Clean up deprecated metadata
- Reset project facts before re-analysis

**Note:** If the fact doesn't exist, the action completes successfully without error.

### add_project_link

Adds an external link to the current project.

**Configuration:**
```toml
[[actions]]
name = "add-docs-link"
type = "imbi"
command = "add_project_link"
link_type = "Documentation"
url = "https://docs.example.com/{{ imbi_project.slug }}"
```

**Fields:**

- `link_type` (string, required): Type of link (e.g., "Documentation", "Repository", "Dashboard")
- `url` (string, required): URL for the link (supports Jinja2 templates)

**Use Cases:**

- Add documentation links after generating docs
- Link to monitoring dashboards
- Add repository links for new projects
- Connect to external services (PagerDuty, Datadog, etc.)

**Example:**
```toml
[[actions]]
name = "add-github-link"
type = "imbi"
command = "add_project_link"
link_type = "Repository"
url = "https://github.com/{{ github_repository.full_name }}"
```

### update_project_type

Changes the project type classification.

**Configuration:**
```toml
[[actions]]
name = "reclassify-project"
type = "imbi"
command = "update_project_type"
project_type = "consumer"
```

**Fields:**

- `project_type` (string, required): Slug of the new project type

**Use Cases:**

- Reclassify projects after architecture changes
- Correct project type errors
- Migrate projects between categories

**Note:** If the project is already the specified type, the action completes without making changes.

### batch_update_facts

Updates multiple project facts in a single operation.

**Configuration:**
```toml
[[actions]]
name = "update-all-facts"
type = "imbi"
command = "batch_update_facts"
facts = {
    "Python Version" = "3.12",
    "Framework" = "FastAPI",
    "Test Coverage" = 85
}
```

**Fields:**

- `facts` (dict, required): Dictionary mapping fact names to values
- `skip_validations` (boolean, optional): Skip validation for all facts (default: false)

**Use Cases:**

- Update multiple related facts after a migration
- Set initial facts for new projects
- Bulk update facts based on automated analysis

**Example:**
```toml
[[actions]]
name = "record-analysis-results"
type = "imbi"
command = "batch_update_facts"
facts = {
    "Programming Language" = "Python 3.12",
    "Has Tests" = true,
    "Code Quality Score" = 87,
    "Last Analyzed" = "2024-01-15"
}
```

## Context Access

Imbi actions have access to the current project data through the workflow context:

```python
context.imbi_project.id           # Project ID
context.imbi_project.name         # Project name
context.imbi_project.namespace    # Project namespace
context.imbi_project.project_type # Project type
context.imbi_project.facts        # Current project facts
```

## Examples

### Set Standard Environments

```toml
# Standardize environments across all frontend projects
[filter]
project_types = ["frontend-applications"]
github_identifier_required = true

[[actions]]
name = "set-environments"
type = "imbi"
command = "set_environments"
values = ["testing", "staging", "production"]

[[actions]]
name = "sync-to-github"
type = "github"
command = "sync_environments"
```

### Update Python Version Fact

```toml
[[actions]]
name = "upgrade-python"
type = "claude"
prompt = "workflow:///prompts/upgrade-python.md"

[[actions]]
name = "record-python-version"
type = "imbi"
command = "set_project_fact"
fact_name = "Programming Language"
fact_value = "Python 3.12"
```

### Track Migration Status

```toml
[[actions]]
name = "migrate-config"
type = "file"
command = "copy"
source = "workflow:///new-config.yaml"
destination = "repository:///config.yaml"

[[actions]]
name = "mark-migration-complete"
type = "imbi"
command = "set_project_fact"
fact_name = "Config Migration Status"
fact_value = "Completed"
```

### Record Docker Image Version

```toml
[[actions]]
name = "update-dockerfile"
type = "claude"
prompt = "workflow:///prompts/update-docker.md"

[[actions]]
name = "record-base-image"
type = "imbi"
command = "set_project_fact"
fact_name = "Docker Base Image"
fact_value = "python:3.12-slim"
```

## Common Patterns

### Post-Migration Tracking

```toml
# Perform migration
[[actions]]
name = "migrate-to-new-framework"
type = "claude"
prompt = "workflow:///prompts/framework-migration.md"

# Record successful migration
[[actions]]
name = "update-framework-fact"
type = "imbi"
command = "set_project_fact"
fact_name = "Framework"
fact_value = "FastAPI 0.110"
```

### Conditional Updates Based on Facts

Use workflow filters to target projects by existing facts, then update after transformation:

```toml
# In workflow config.toml
[filter]
project_facts = {"Framework" = "Flask"}

# Actions update to FastAPI and record change
[[actions]]
name = "migrate-flask-to-fastapi"
type = "claude"
prompt = "workflow:///prompts/flask-to-fastapi.md"

[[actions]]
name = "update-framework-fact"
type = "imbi"
command = "set_project_fact"
fact_name = "Framework"
fact_value = "FastAPI"
```

## Available Commands Summary

| Command | Description |
|---------|-------------|
| `add_project_link` | Add external links to projects |
| `batch_update_facts` | Update multiple facts in a single operation |
| `delete_project_fact` | Remove obsolete project facts |
| `get_project_fact` | Retrieve fact values for conditional logic |
| `set_environments` | Update project environments with smart validation |
| `set_project_fact` | Update or create project facts with validation |
| `update_project` | Update any project attributes with template support |
| `update_project_type` | Change project classification |

## Integration with Other Actions

### With Claude Actions

```toml
[[actions]]
name = "ai-dependency-update"
type = "claude"
prompt = "workflow:///prompts/update-deps.md"

[[actions]]
name = "record-dependency-version"
type = "imbi"
command = "set_project_fact"
fact_name = "Primary Dependencies"
fact_value = "httpx>=0.27, pydantic>=2.0"
```

### With Shell Actions

```toml
[[actions]]
name = "detect-python-version"
type = "shell"
command = "python --version | cut -d' ' -f2"
working_directory = "repository:///"

[[actions]]
name = "record-detected-version"
type = "imbi"
command = "set_project_fact"
fact_name = "Python Version"
fact_value = "{{ shell_output }}"  # From previous action
```

## Best Practices

1. **Use After Transformations**: Record changes after successful transformations
2. **Semantic Fact Names**: Use clear, descriptive fact names that match Imbi's schema
3. **Version Tracking**: Record version numbers for dependencies and tools
4. **Status Tracking**: Use facts to track migration/upgrade status across projects
5. **Conditional Execution**: Combine with workflow filters to target specific project states

## See Also

- [Callable Actions](callable.md) - Direct Imbi API method calls (alternative approach)
- [Workflow Configuration](../workflows.md) - Using project facts in filters
