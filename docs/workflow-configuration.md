# Workflow Configuration Reference

Complete field reference for workflow configuration files (`workflow.toml`) with detailed descriptions, types, defaults, and examples.

**Tip:** Workflow configuration syntax is validated on startup

## Configuration Structure

A complete workflow configuration includes:

```toml
# Workflow Metadata
name = "workflow-name"
description = "Optional description"
prompt = "workflow:///prompts/base.md"

# Project Filtering
[filter]
project_ids = [123, 456]
project_types = ["api"]
project_facts = {"Programming Language" = "Python 3.12"}
github_identifier_required = true
github_workflow_status_exclude = ["success"]

# Git Configuration
[git]
clone = true
depth = 1
ref = "main"
starting_branch = "main"
ci_skip_checks = false
clone_type = "ssh"  # or "http"

# GitHub Configuration
[github]
create_pull_request = true
replace_branch = false

# Workflow-Level Conditions
condition_type = "all"  # or "any"

[[conditions]]
remote_file_exists = "file.txt"

# Actions
[[actions]]
name = "action-name"
type = "file"
# ... action-specific fields
```

## Workflow Metadata

### name (required)

Workflow display name shown in logs, reports, and pull requests.

**Type:** `string`  


```toml
name = "Update Python Dependencies"
```

### description (optional)

Human-readable description of workflow purpose and goals.

**Type:** `string`  

**Default:** None  


```toml
description = "Updates Python dependencies to latest compatible versions while maintaining compatibility"
```

### prompt (optional)

Base prompt file for Claude Code actions. This prompt is prepended to all Claude actions in the workflow unless they specify their own prompt.

**Type:** [`ResourceUrl`](actions/index.md#resourceurl-path-system) (path to prompt template file)

**Default:** None  


```toml
prompt = "workflow:///prompts/base-context.md"
```

**Usage:** Provides shared context across all Claude actions in the workflow.

## Git Configuration

The `[git]` section controls repository cloning and commit behavior.

### clone

Whether to clone the repository from the remote.

**Type:** `boolean`  

**Default:** `true`  


```toml
[git]
clone = true
```

**When to use `false`:** API-only workflows that don't need repository access.

### depth

Shallow clone depth (number of commits to fetch).

**Type:** `integer`  

**Default:** `1`  


```toml
[git]
depth = 1  # Shallow clone (fastest)

# OR

[git]
depth = 100  # More history available for git operations
```

**Use cases:**

- `depth = 1`: Fastest, use for most workflows
- `depth = 100+`: When extracting files from commit history

### ref

Git reference (branch, tag, or commit SHA) to clone.

**Type:** `string`  

**Default:** Repository's default branch  


```toml
[git]
ref = "main"

# OR

[git]
ref = "v1.2.3"  # Clone specific tag

# OR

[git]
ref = "abc123"  # Clone specific commit
```

### starting_branch

Branch name to use as starting point for workflow branch.

**Type:** `string`  

**Default:** Repository's default branch  


```toml
[git]
starting_branch = "develop"  # Branch from develop instead of main
```

### ci_skip_checks

Whether to skip CI/CD checks in commit messages.

**Type:** `boolean`  

**Default:** `false`  


```toml
[git]
ci_skip_checks = true  # Adds [skip ci] to commit messages
```

### clone_type

Protocol to use for cloning repositories.

**Type:** `string`  

**Values:** `"ssh"` (default), `"http"`


```toml
[git]
clone_type = "ssh"  # Use SSH keys (default)

# OR

[git]
clone_type = "http"  # Use HTTPS (requires token)
```

## GitHub Configuration

The `[github]` section controls GitHub pull request creation and branch management.

### create_pull_request

Whether to create a pull request after committing changes.

**Type:** `boolean`  

**Default:** `true`  


```toml
[github]
create_pull_request = true
```

**When to use `false`:** Direct commits to main (not recommended), testing workflows.

### replace_branch

Delete and recreate remote branch if it already exists.

**Type:** `boolean`  

**Default:** `false`  


```toml
[github]
create_pull_request = true
replace_branch = true  # Force-replace existing PR branch
```

**Requirements:** `create_pull_request` must be `true`.

**Use cases:**

- Updating failed workflow runs
- Re-running workflows with fixes
- Forcing clean state

**Warning:** Destroys existing PR branch and its history.

## Followup Stage Configuration

### max_followup_cycles

Maximum number of cycles for followup stage execution.

**Type:** `integer`  

**Default:** `5`  

```toml
max_followup_cycles = 3
```

**Behavior:**  

- Followup actions execute after PR creation
- If any followup action commits, the stage cycles again
- If no commits made during a cycle, followup is complete
- If max cycles reached without completion, workflow fails

**Use cases:**

- Limit iterations when monitoring CI
- Control retry behavior for feedback loops
- Prevent infinite loops in automated fixes

See [Action Stages](actions/stages.md) for complete followup stage documentation.

## MCP Server Configuration

The `[mcp_servers]` section allows configuring Model Context Protocol (MCP) servers that will be available to Claude actions during workflow execution. MCP servers provide Claude with access to external tools and data sources.

### Supported Transport Types

Three MCP transport types are supported, matching the Claude Agent SDK:

#### stdio (Standard I/O)

Launch a local MCP server process:

```toml
[mcp_servers.my-postgres]
type = "stdio"
command = "uvx"
args = ["mcp-server-postgres", "${DATABASE_URL}"]
env = { DATABASE_URL = "${DATABASE_URL}" }
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"stdio"` | Yes | Transport type |
| `command` | `string` | Yes | Executable to run |
| `args` | `list[string]` | No | Command arguments (default: `[]`) |
| `env` | `dict[string, string]` | No | Environment variables (default: `{}`) |

#### http (HTTP)

Connect to an HTTP-based MCP server:

```toml
[mcp_servers.my-api]
type = "http"
url = "https://api.example.com/mcp"
headers = { Authorization = "Bearer ${API_TOKEN}" }
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"http"` | Yes | Transport type |
| `url` | `string` | Yes | Server endpoint URL |
| `headers` | `dict[string, string]` | No | HTTP headers (default: `{}`) |

#### sse (Server-Sent Events)

Connect to an SSE-based MCP server:

```toml
[mcp_servers.my-events]
type = "sse"
url = "https://api.example.com/mcp/sse"
headers = { Authorization = "Bearer ${API_TOKEN}" }
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"sse"` | Yes | Transport type |
| `url` | `string` | Yes | SSE endpoint URL |
| `headers` | `dict[string, string]` | No | HTTP headers (default: `{}`) |

### Environment Variable Expansion

MCP server configurations support shell-style environment variable expansion for secure credential injection:

- **`$VAR`** - Basic expansion
- **`${VAR}`** - Braced expansion (recommended)

Environment variables are expanded at runtime when the Claude client is created, not at configuration parse time.

**Example:**

```toml
[mcp_servers.production-db]
type = "stdio"
command = "uvx"
args = ["mcp-server-postgres", "${PROD_DATABASE_URL}"]

[mcp_servers.internal-api]
type = "http"
url = "https://api.internal.example.com/mcp"
headers = { Authorization = "Bearer ${INTERNAL_API_TOKEN}" }
```

**Supported Locations:**

- `args` list values
- `env` dict values
- `url` string
- `headers` dict values

**Error Handling:**

If a referenced environment variable is not set, a clear error is raised:

```
ValueError: Environment variable PROD_DATABASE_URL not set
```

### Complete Example

```toml
name = "Data Analysis Workflow"
description = "Analyze project data using MCP-connected databases"

[mcp_servers.postgres]
type = "stdio"
command = "uvx"
args = ["mcp-server-postgres", "${DATABASE_URL}"]

[mcp_servers.clickhouse]
type = "http"
url = "https://clickhouse.example.com/mcp"
headers = { Authorization = "Bearer ${CLICKHOUSE_TOKEN}" }

[mcp_servers.neo4j]
type = "stdio"
command = "uvx"
args = ["mcp-server-neo4j"]
env = { NEO4J_URL = "${NEO4J_URL}", NEO4J_PASSWORD = "${NEO4J_PASSWORD}" }

[[actions]]
name = "analyze-data"
type = "claude"
task_prompt = "prompts/analyze.md"
```

In Claude actions, these MCP servers are available alongside the built-in `agent_tools` server that provides workflow submission functions.

## Claude Code Plugin Configuration

The `[plugins]` section allows configuring Claude Code plugins and marketplaces at the workflow level. These settings are merged with the main configuration's `[claude_code.plugins]` settings.

### Merge Behavior

| Setting | Merge Behavior |
|---------|----------------|
| `enabled_plugins` | Workflow values override main config |
| `marketplaces` | Workflow values override main config for same keys |
| `local_plugins` | Concatenated (duplicates removed by path) |

### [plugins].enabled_plugins

Enable or disable specific plugins for this workflow.

**Type:** `dict[string, boolean]`  

```toml
[plugins.enabled_plugins]
"workflow-specific-plugin@marketplace" = true
"grafana-mcp@aweber-marketplace" = true  # Override main config
```

### [plugins.marketplaces]

Add workflow-specific marketplace sources.

**Type:** `dict[string, ClaudeMarketplace]`  

```toml
[plugins.marketplaces.workflow-marketplace]
source = "github"
repo = "org/workflow-specific-plugins"

[plugins.marketplaces.local-dev]
source = "directory"
path = "/path/to/dev/marketplace"
```

### [[plugins.local_plugins]]

Add workflow-specific local plugins.

**Type:** `list[ClaudeLocalPlugin]`  

```toml
[[plugins.local_plugins]]
path = "/path/to/workflow/plugin"
```

### Complete Workflow Plugin Example

```toml
name = "Data Analysis Workflow"
description = "Analyze data using specialized plugins"

# Enable workflow-specific plugins
[plugins.enabled_plugins]
"data-analyzer@analytics-marketplace" = true
"grafana-mcp@aweber-marketplace" = true  # Enable for this workflow

# Add workflow-specific marketplace
[plugins.marketplaces.analytics-marketplace]
source = "github"
repo = "company/analytics-plugins"

# Add local development plugin
[[plugins.local_plugins]]
path = "/home/user/data-analysis-plugin"

[[actions]]
name = "analyze-data"
type = "claude"
task_prompt = "prompts/analyze.md"
```

## Workflow-Level Conditions

Workflow conditions determine if the entire workflow should execute for a project. See [Workflow Conditions](workflow-conditions.md) for detailed documentation.

### condition_type

How to evaluate multiple conditions.

**Type:** `string`  

**Values:** `"all"` (AND logic), `"any"` (OR logic)

**Default:** `"all"`  


```toml
condition_type = "all"  # All conditions must pass

[[conditions]]
remote_file_exists = "package.json"

[[conditions]]
remote_file_contains = "node.*18"
remote_file = ".nvmrc"
```

With `condition_type = "all"`, workflow executes only if BOTH conditions pass.

```toml
condition_type = "any"  # Any one condition passing is sufficient

[[conditions]]
remote_file_exists = "requirements.txt"

[[conditions]]
remote_file_exists = "pyproject.toml"
```

With `condition_type = "any"`, workflow executes if EITHER file exists.

### [[conditions]]

Array of condition objects. See [Workflow Conditions](workflow-conditions.md) for complete condition types and examples.

**Condition Types:**

- **Remote conditions** (checked via API before cloning)
  - `remote_file_exists` / `remote_file_not_exists`
  - `remote_file_contains` / `remote_file_doesnt_contain` + `remote_file`

- **Local conditions** (checked after cloning)
  - `file_exists` / `file_not_exists`
  - `file_contains` / `file_doesnt_contain` + `file`

- **Template conditions** (checked after cloning)
  - `when` - Jinja2 expression for complex logic

**Example:**
```toml
[[conditions]]
remote_file_exists = "Dockerfile"

[[conditions]]
remote_file_contains = "FROM python:3"
remote_file = "Dockerfile"

[[conditions]]
when = "{{ compare_semver(get_component_version('repository:///package.json', 'react'), '19.0.0').is_older }}"
```

## Actions

Actions define the operations to perform during workflow execution. Each action has common fields plus type-specific configuration.

### Common Action Fields

All actions support these fields:

#### name (required)

Action identifier for logging and error messages.

**Type:** `string`  


```toml
[[actions]]
name = "copy-gitignore"
```

#### type (required)

Action type determines which operation to perform.

**Type:** `string`  

**Values:** `callable`, `claude`, `docker`, `file`, `git`, `github`, `imbi`, `shell`, `template`


```toml
[[actions]]
type = "file"
```

See [Actions Reference](actions/index.md) for complete documentation of each action type.

#### stage (optional)

Execution stage for this action.

**Type:** `string`  

**Values:** `"primary"` (default), `"followup"`


```toml
[[actions]]
name = "monitor-ci"
type = "claude"
stage = "followup"
task_prompt = "prompts/monitor.md.j2"
```

**Stage behaviors:**

- **`primary`**: Executes before PR creation (default behavior)
- **`followup`**: Executes after PR is created, with access to PR context

**Followup stage features:**

- Receives `pull_request` and `pr_branch` in template context
- Can commit changes that push to PR branch
- Cycles if commits are made (up to `max_followup_cycles`)

See [Action Stages](actions/stages.md) for detailed stage documentation.

#### ai_commit (optional)

Use AI to generate commit message for this action's changes.

**Type:** `boolean`  

**Default:** `false`  

**Requires:** Anthropic API key configured


```toml
[[actions]]
name = "complex-refactor"
type = "claude"
ai_commit = true  # AI-generated commit message
```

#### commit_message (optional)

Specify a custom commit message for this action's changes. Only valid when `ai_commit` is `false` (or unset) and `committable` is `true`.

**Type:** `string`  

**Default:** `null` (uses auto-generated message)  

**Validation:**

- Cannot be set when `ai_commit = true`
- Cannot be set when `committable = false`

**Auto-generated format when not specified:**

```
imbi-automations: workflow-name - action-name

🤖 Generated with [Imbi Automations](https://github.com/AWeber-Imbi/).
```

**Custom message example:**

```toml
[[actions]]
name = "update-dependencies"
type = "file"
command = "copy"
source = "workflow:///requirements.txt"
destination = "repository:///requirements.txt"
commit_message = "Update Python dependencies to latest versions"
```

**Use cases:**

- Semantic commit messages for specific changes
- Conventional commit format enforcement
- Custom formatting for automated changelogs
- Descriptive messages for significant updates

#### committable (optional)

Whether this action's changes should be included in git commits.

**Type:** `boolean`  

**Default:** `true`  


```toml
[[actions]]
name = "temporary-analysis"
type = "file"
command = "write"
committable = false  # Don't commit this file
```

**Use cases:**

- Temporary files for other actions
- Diagnostic output files
- Intermediate processing artifacts

#### on_success (optional)

Action name to jump to if this action succeeds.

**Type:** `string` (action name)  


```toml
[[actions]]
name = "try-fast-method"
type = "shell"
command = "fast-operation"
on_success = "skip-slow-method"

[[actions]]
name = "slow-fallback"
# This will be skipped if fast method succeeds

[[actions]]
name = "skip-slow-method"
# Execution resumes here
```

#### on_failure (optional)

Action name to restart from if this action fails after all retry cycles.

**Type:** `string` (action name)  

**Max Retries:** 3 per action


```toml
[[actions]]
name = "backup-files"
type = "file"
command = "copy"
source = "repository:///src/"
destination = "extracted:///src.backup/"

[[actions]]
name = "risky-transformation"
type = "claude"
prompt = "prompts/transform.md"
on_failure = "restore-backup"

[[actions]]
name = "restore-backup"
type = "file"
command = "move"
source = "extracted:///src.backup/"
destination = "repository:///src/"
```

#### timeout (optional)

Maximum execution time for action in Go time.Duration format.

**Type:** `string`

**Default:** `"1h"` (1 hour)

**Supported formats:**
- Minutes: `"5m"`, `"30m"`
- Hours: `"1h"`, `"2h30m"`
- Seconds: `"90s"`
- Combined: `"1h30m45s"`

**Behavior:**
- **Claude actions**: Timeout applies per-cycle (each planning/task/validation gets the full duration)
- **Shell/Docker actions**: Timeout applies to single execution
- On timeout: Process terminated gracefully (SIGTERM → SIGKILL), workflow fails with error

```toml
[[actions]]
name = "long-running-build"
type = "shell"
command = "make build"
timeout = "2h"  # 2 hours
```

#### filter (optional)

Project filter to apply for this specific action. Uses same filter format as workflow-level `[filter]`.

**Type:** `WorkflowFilter` object


```toml
[[actions]]
name = "api-specific-update"
type = "file"

# Only execute this action for API projects
[actions.filter]
project_types = ["api"]
```

#### condition_type (optional)

How to evaluate multiple action conditions.

**Type:** `string`  

**Values:** `"all"` (default), `"any"`


```toml
[[actions]]
name = "update-python-config"
type = "template"
condition_type = "any"  # Execute if ANY config file exists

[[actions.conditions]]
file_exists = "setup.py"

[[actions.conditions]]
file_exists = "pyproject.toml"

[[actions.conditions]]
file_exists = "requirements.txt"
```

#### [[actions.conditions]]

Array of conditions that must pass for this action to execute. Same condition types as workflow-level conditions.

**Example:**
```toml
[[actions]]
name = "update-dockerfile"
type = "file"

[[actions.conditions]]
file_exists = "Dockerfile"

[[actions.conditions]]
file_contains = "FROM python:3\\.11"
file = "Dockerfile"
```

See [Workflow Conditions](workflow-conditions.md) for detailed condition documentation.

#### data (optional)

Custom data dictionary for action-specific use.

**Type:** `dict[string, any]`  

**Default:** `{}`  


```toml
[[actions]]
name = "custom-action"
type = "callable"

[actions.data]
custom_field = "value"
nested = { key = "value" }
```

### Action-Specific Fields

Each action type has additional required and optional fields. See the [Actions Reference](actions/index.md) for complete documentation:

- [Callable Actions](actions/callable.md) - `import`, `callable`, `args`, `kwargs`
- [Claude Actions](actions/claude.md) - `prompt`, `validation_prompt`, `max_cycles`
- [Docker Actions](actions/docker.md) - `command`, `image`, `tag`, `source`, `destination`
- [File Actions](actions/file.md) - `command`, `path`, `source`, `destination`, `content`, `pattern`
- [Git Actions](actions/git.md) - `command`, `source`, `destination`, `url`, `commit_keyword`
- [GitHub Actions](actions/github.md) - `command`
- [Imbi Actions](actions/imbi.md) - `command`
- [Shell Actions](actions/shell.md) - `command`, `working_directory`, `ignore_errors`
- [Template Actions](actions/template.md) - `source_path`, `destination_path`

## Complete Example

```toml
name = "Python 3.12 Migration"
description = "Migrate Python projects from 3.11 to 3.12"
prompt = "workflow:///prompts/base-python.md"

[filter]
project_types = ["api", "consumer", "daemon"]
project_facts = {"Programming Language" = "Python 3.11"}
github_identifier_required = true
github_workflow_status_exclude = ["success"]

[git]
clone = true
depth = 100  # Need history for git extract actions
starting_branch = "main"
clone_type = "ssh"

[github]
create_pull_request = true
replace_branch = true

condition_type = "all"

[[conditions]]
remote_file_exists = "pyproject.toml"

[[conditions]]
remote_file_contains = "python.*3\\.11"
remote_file = "pyproject.toml"

[[actions]]
name = "backup-pyproject"
type = "file"
command = "copy"
source = "repository:///pyproject.toml"
destination = "extracted:///pyproject.toml.backup"
committable = false

[[actions]]
name = "update-python-version"
type = "claude"
prompt = "prompts/update-python-version.md"
validation_prompt = "prompts/validate-python-version.md"
max_cycles = 3
on_failure = "restore-backup"
ai_commit = true

[[actions]]
name = "run-tests"
type = "shell"
command = "pytest tests/ -v"
working_directory = "repository:///"
timeout = "10m"

[[actions.conditions]]
file_exists = "tests/"

[[actions]]
name = "restore-backup"
type = "file"
command = "move"
source = "extracted:///pyproject.toml.backup"
destination = "repository:///pyproject.toml"
```

## See Also

- [Workflow Filters](workflow-filters.md) - Detailed filter documentation with examples
- [Workflow Conditions](workflow-conditions.md) - Comprehensive condition types and patterns
- [Actions Reference](actions/index.md) - Complete action types documentation
- [Workflows Overview](workflows.md) - High-level workflow concepts and best practices
