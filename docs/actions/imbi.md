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

### set_project_description

Updates the description field for the current project in Imbi.

**Configuration:**
```toml
[[actions]]
name = "update-description"
type = "imbi"
command = "set_project_description"
description = "REST API for user authentication and profile management"
```

**Fields:**

- `description` (string, required): New description text (supports Jinja2 templates)

**Features:**

- **Template Support**: Description field supports full Jinja2 templating with workflow context
- **Read File Function**: Use `read_file()` to load descriptions from files
- **Smart Updates**: Only makes API calls when description differs from current value
- **HTTP 304 Handling**: Properly handles "Not Modified" responses
- **Non-Committable**: Does not create git commits (modifies Imbi state only)

**Use Cases:**

- Generate project descriptions using AI (Claude actions)
- Standardize description formats across projects
- Update descriptions from repository README files
- Auto-generate descriptions from code analysis

**Basic Example:**
```toml
[[actions]]
name = "set-description"
type = "imbi"
command = "set_project_description"
description = "Python API for {{ imbi_project.name }}"
```

**With File Reading:**
```toml
[[actions]]
name = "generate-description-with-ai"
type = "claude"
task_prompt = "prompts/generate-description.md"
committable = false

[[actions]]
name = "update-description-from-file"
type = "imbi"
command = "set_project_description"
description = "{{ read_file('repository:///GENERATED_DESCRIPTION.txt').strip() }}"

[[actions.conditions]]
file_exists = "repository:///GENERATED_DESCRIPTION.txt"
```

**From README:**
```toml
[[actions]]
name = "extract-description-from-readme"
type = "shell"
command = "head -n 3 README.md | tail -n 1"
working_directory = "repository:///"
committable = false

[[actions]]
name = "set-description-from-readme"
type = "imbi"
command = "set_project_description"
description = "{{ read_file('repository:///README.md').split('\\n')[2] }}"
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
| `set_environments` | Update project environments with smart validation |
| `set_project_fact` | Update or create project facts with validation |
| `set_project_description` | Update project description with template support |

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

## Future Enhancements

Planned additions to Imbi action functionality:

- **get_project_fact**: Retrieve fact values for conditional logic
- **delete_project_fact**: Remove obsolete facts
- **set_project_metadata**: Update project name, description, etc.
- **add_project_link**: Add external links to projects
- **update_project_type**: Change project classification
- **batch_update_facts**: Update multiple facts in one operation

## Best Practices

1. **Use After Transformations**: Record changes after successful transformations
2. **Semantic Fact Names**: Use clear, descriptive fact names that match Imbi's schema
3. **Version Tracking**: Record version numbers for dependencies and tools
4. **Status Tracking**: Use facts to track migration/upgrade status across projects
5. **Conditional Execution**: Combine with workflow filters to target specific project states

## See Also

- [Callable Actions](callable.md) - Direct Imbi API method calls (alternative approach)
- [Workflow Configuration](../workflows.md) - Using project facts in filters
- [Utility Actions](utility.md) - Logging and state management
