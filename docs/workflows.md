# Workflows

Workflows are the core automation units in Imbi Automations. Each workflow defines a sequence of actions to execute across your project repositories, with powerful filtering and conditional execution capabilities.

## What is a Workflow?

A workflow is a directory containing a workflow configuration file that defines:

- **Actions**: Operations to perform (file manipulation, AI transformations, shell commands, etc.)
- **Conditions**: Repository state checks to determine if workflow/actions should run
- **Filters**: Project targeting criteria to select which projects to process
- **Configuration**: Git and GitHub behavior settings

## Workflow Structure

```
workflows/workflow-name/
├── workflow.toml        # Required - workflow configuration
├── prompts/             # Optional - Claude prompt templates
│   ├── task.md.j2
│   └── validator.md.j2
├── templates/           # Optional - Jinja2 templates
│   ├── config.yaml.j2
│   └── README.md.j2
└── files/               # Optional - static resources
    ├── .gitignore
    └── .pre-commit-config.yaml
```

## Minimal Example

The simplest workflow requires only a name and actions:

```toml
name = "update-gitignore"

[[actions]]
name = "copy-gitignore"
type = "file"
command = "copy"
source = "workflow:///.gitignore"
destination = "repository:///.gitignore"
```

This workflow copies a `.gitignore` file from the workflow directory to each repository.

## Three Levels of Project Selection

In addition to the `--project-id`, `--project-type`, and `--all-projects` command-line arguments, Imbi Automations provides three complementary mechanisms to control which projects to process and which actions execute:

### 1. **Project Filters** - Pre-filter before processing

Target specific project subsets using Imbi metadata (project IDs, types, facts, GitHub requirements).

**When:** Before any workflow processing begins

**Effect:** Projects that don't match are never processed

**Use for:** Broad targeting (e.g., "only Python APIs")

### 2. **Workflow Conditions** - Skip entire workflow

Check repository state (remote or local) to determine if workflow should run.

**When:** Once per project, before any actions execute

**Effect:** If conditions fail, entire workflow is skipped for that project

**Use for:** Workflow applicability (e.g., "only if Dockerfile exists")

### 3. **Action Conditions** - Skip individual actions

Check repository state before each action to conditionally execute.

**When:** Before each action executes

**Effect:** If conditions fail, only that specific action is skipped

**Use for:** Conditional behavior (e.g., "update setup.py only if it exists")

### Evaluation Flow

```
1. Apply project filters    → 1000 projects → 50 matching
   [filter] section

2. Check workflow conditions → 50 projects → 30 applicable
   [[conditions]]

3. Clone repository          → Working with 30 repositories

4. For each action:          → Execute only when conditions pass
   Check action conditions
   [[actions.conditions]]
```

## Key Capabilities

### Action Types

Workflows support multiple action types for different operations:

- **File Actions**: Copy, move, delete, write files with glob pattern support
- **Shell Actions**: Execute commands with template variable substitution
- **Template Actions**: Render Jinja2 templates with full project context
- **Claude Actions**: AI-powered code transformations using Claude Code SDK
- **Git Actions**: Extract files from commit history, clone repositories
- **Docker Actions**: Extract files from containers, build images
- **GitHub/Imbi Actions**: API operations on project management platforms

See the [Actions Reference](actions/index.md) for complete documentation.

### Action Stages

Actions can be organized into execution stages:

- **Primary** (default): Execute before PR creation - standard workflow actions
- **Followup**: Execute after PR creation - for monitoring CI, responding to feedback

```toml
[[actions]]
name = "update-deps"
type = "claude"
# stage = "primary"  # Default, can be omitted
task_prompt = "prompts/update.md.j2"

[[actions]]
name = "monitor-ci"
type = "claude"
stage = "followup"
task_prompt = "prompts/monitor.md.j2"
committable = true
```

Followup actions receive PR context (`pull_request.number`, `pull_request.html_url`, `pr_branch`) in templates. See [Action Stages](actions/stages.md) for detailed documentation.

### Conditional Execution

**Remote Conditions** (checked via API before cloning):
```toml
[[conditions]]
remote_file_exists = "package.json"

[[conditions]]
remote_file_contains = "\"node\": \"18\""
remote_file = "package.json"
```

**Local Conditions** (checked after cloning):
```toml
[[conditions]]
file_exists = "**/*.tf"  # Glob pattern support

[[conditions]]
file_contains = "python.*3\\.12"
file = "pyproject.toml"
```

**Action-Level Conditions**:
```toml
[[actions]]
name = "update-setup-py"
type = "file"
command = "write"

[[actions.conditions]]
file_exists = "setup.py"  # Only execute if setup.py exists
```

### Project Filtering

Target specific project subsets efficiently:

```toml
[filter]
project_types = ["api", "consumer"]
project_facts = {"Programming Language" = "Python 3.12"}
github_identifier_required = true
github_workflow_status_exclude = ["success"]  # Only failing/missing workflows
```

### AI-Powered Transformations

Use Claude Code for complex multi-file transformations:

```toml
[[actions]]
name = "migrate-to-pydantic-v2"
type = "claude"
prompt = "workflow:///prompts/pydantic-migration.md"
max_cycles = 5
ai_commit = true  # AI-generated commit messages
```

### Pull Request Automation

Automatically create PRs for workflow changes:

```toml
[github]
create_pull_request = true
replace_branch = true  # Force-replace existing PR branch
```

## Example Workflows

### Simple File Copy

```toml
name = "Deploy Standard .gitignore"

[[conditions]]
remote_file_exists = ".git"

[[actions]]
name = "copy-gitignore"
type = "file"
command = "copy"
source = "workflow:///.gitignore"
destination = "repository:///.gitignore"
```

### AI-Powered Migration

```toml
name = "Migrate to Pydantic V2"

[filter]
project_types = ["api"]
project_facts = {"Programming Language" = "Python 3.12"}

[[conditions]]
remote_file_contains = "pydantic"
remote_file = "pyproject.toml"

[[actions]]
name = "migrate-pydantic"
type = "claude"
prompt = "workflow:///prompts/pydantic-v2.md"
max_cycles = 5
on_failure = "restore-backup"
ai_commit = true
```

### Conditional Updates

```toml
name = "Update Python Files"

[[actions]]
name = "update-setup-py"
type = "template"
source_path = "workflow:///setup.py.j2"
destination_path = "repository:///setup.py"

[[actions.conditions]]
file_exists = "setup.py"

[[actions]]
name = "update-pyproject"
type = "template"
source_path = "workflow:///pyproject.toml.j2"
destination_path = "repository:///pyproject.toml"

[[actions.conditions]]
file_exists = "pyproject.toml"
```

## Running Workflows

Execute workflows across all your projects:

```bash
# Run on all projects
imbi-automations config.toml workflows/workflow-name --all-projects

# Run on specific project types
imbi-automations config.toml workflows/workflow-name --project-type api

# Run on specific project
imbi-automations config.toml workflows/workflow-name --project-id 123

# Resume from specific project (useful for large batches)
imbi-automations config.toml workflows/workflow-name --all-projects \
  --start-from-project my-project-slug
```

See the [CLI Reference](cli.md) for complete command-line options.

## Included Workflows

Imbi Automations includes 25+ pre-built workflows for common tasks:

**Infrastructure & Tooling:**

- Docker image updates and health checks
- Terraform CI/CD pipelines
- Frontend build and deployment
- Compose configuration fixes

**Code Quality:**

- CI/CD pipeline enforcement
- GitHub Actions workflow fixes
- SonarQube quality gate fixes

**Project Maintenance:**

- Standard .gitignore deployment
- GitHub team synchronization
- Environment synchronization
- Project validation

See the `workflows/` directory in the repository for all available workflows.

## Best Practices

### Use Remote Conditions First

Remote conditions are faster and avoid unnecessary cloning:

```toml
# ✅ Good - check remotely before cloning
[[conditions]]
remote_file_exists = "package.json"

# ❌ Slower - clones every repository
[[conditions]]
file_exists = "package.json"
```

### Filter Early, Filter Often

Use workflow-level filters to reduce processing scope:

```toml
# ✅ Good - filter at workflow level
[filter]
project_types = ["api"]
project_facts = {"Programming Language" = "Python 3.12"}

# ❌ Less efficient - evaluates conditions on all projects
[[conditions]]
# checking conditions on 1000 projects instead of 50
```

### Design Idempotent Workflows

Make workflows safely re-runnable:

```toml
[[actions.conditions]]
file_not_exists = "config/app.yaml"  # Only create if missing
```

### Use Action Conditions for Variation

Different projects need different actions:

```toml
[[actions]]
name = "update-setup-py"
[[actions.conditions]]
file_exists = "setup.py"

[[actions]]
name = "update-pyproject"
[[actions.conditions]]
file_exists = "pyproject.toml"
```

## Learn More

- **[Workflow Configuration](workflow-configuration.md)** - Detailed configuration reference with all fields and options
- **[Action Stages](actions/stages.md)** - Primary and followup stage execution for CI monitoring
- **[Actions Reference](actions/index.md)** - Complete action types documentation
- **[Debugging Workflows](debugging.md)** - Troubleshooting and debugging techniques
- **[CLI Reference](cli.md)** - Command-line options and usage
