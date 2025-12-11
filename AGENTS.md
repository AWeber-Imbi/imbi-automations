# AGENTS.md

Guidance for AI agents working with this codebase. Maintain this file when making significant architectural changes.

## Project Overview

CLI framework for executing workflows across repositories with Imbi project management and GitHub integration. Provides AI-powered transformations via Claude Code SDK, automated PR creation, and project fact management.

## Quick Reference

```bash
# Setup
pip install -e .[dev] && pre-commit install

# Run CLI
# Note: Workflow directories should contain workflow.toml (config.toml supported as fallback)
imbi-automations config.toml workflows/workflow-name --all-projects
imbi-automations config.toml workflows/workflow-name --project-id 123
imbi-automations config.toml workflows/workflow-name --resume ./errors/workflow/project-timestamp

# Testing & Quality
pytest                          # Run tests
pytest --cov=src/imbi_automations  # With coverage
ruff format && ruff check --fix # Format and lint
pre-commit run --all-files      # All hooks
```

## Architecture

### Core Components

| Component | File | Purpose |
|-----------|------|---------|
| CLI | `cli.py` | Entry point, argument parsing, logging |
| Controller | `controller.py` | Main automation controller, iterator pattern |
| Workflow Engine | `workflow_engine.py` | Action execution, context management |
| Actions | `actions/__init__.py` | Centralized dispatch via match/case |
| Claude Integration | `claude.py` | Claude Code SDK for AI transformations |
| Committer | `committer.py` | Git commits (AI-powered and manual) |

### Clients (`clients/`)
- `http.py`: Base async HTTP client (singleton pattern)
- `imbi.py`: Imbi API integration with caching
- `github.py`: GitHub API with pattern-aware file detection

### Models (`models/`)
- `workflow.py`: Workflow definition, actions, conditions, filters, stages
- `configuration.py`: TOML config with Pydantic validation
- `github.py`, `imbi.py`: API response models
- `claude.py`, `mcp.py`: Claude and MCP server models
- `resume_state.py`: Workflow resumability state

### Action Types (`actions/`)

| Type | File | Purpose |
|------|------|---------|
| `callable` | `callablea.py` | Python function invocation with async detection |
| `claude` | `claude.py` | AI transformations with planning/validation |
| `docker` | `docker.py` | Container operations, file extraction |
| `file` | `filea.py` | Copy/move/delete with glob support |
| `git` | `git.py` | Extract files from history, branch ops |
| `github` | `github.py` | Environment sync, repository updates |
| `imbi` | `imbi.py` | Project facts, links, type management |
| `shell` | `shell.py` | Command execution with Jinja2 |
| `template` | `template.py` | Jinja2 file generation |

## Workflow Configuration

Each workflow directory should contain `workflow.toml` (or `config.toml` for backward compatibility):

```toml
name = "Example Workflow"
max_followup_cycles = 5  # For followup stage cycling

[filter]
project_types = ["apis", "consumers"]
project_facts = {"Programming Language" = "Python 3.12"}
github_identifier_required = true
exclude_open_workflow_prs = true  # Skip projects with open PRs

[github]
create_pull_request = true

[[conditions]]
remote_file_exists = "pyproject.toml"  # Pre-clone check

[[actions]]
name = "update-code"
type = "claude"
stage = "primary"  # Default - before PR
task_prompt = "prompts/task.md.j2"

[[actions]]
name = "monitor-ci"
type = "claude"
stage = "followup"  # After PR created
task_prompt = "prompts/monitor.md.j2"
committable = true
```

### Action Stages

| Stage | When | Use Case |
|-------|------|----------|
| `primary` | Before PR creation | Standard transformations |
| `followup` | After PR creation | CI monitoring, review feedback |

Followup actions cycle if they commit (up to `max_followup_cycles`). They receive PR context: `{{ pull_request.number }}`, `{{ pull_request.html_url }}`, `{{ pr_branch }}`.

## Action Timeouts

All actions support optional timeouts using Go time.Duration format:

```toml
[[actions]]
name = "example-action"
type = "claude"  # or shell, docker, etc.
timeout = "30m"  # Maximum execution time
```

**Supported Formats:**
- Minutes: "5m", "30m"
- Hours: "1h" (default), "2h30m"
- Seconds: "90s"
- Combined: "1h30m45s"

**Timeout Behavior by Action Type:**

| Action Type | Timeout Scope | Behavior on Timeout |
|-------------|---------------|---------------------|
| **Claude** | Per-cycle | Kills SDK process, fails workflow. Example: 5 cycles × 30m = up to 2.5hrs total |
| **Shell** | Single execution | Terminates subprocess (SIGTERM → SIGKILL), fails workflow |
| **Docker** | Single execution | Terminates docker subprocess, fails workflow |
| **Other actions** | Not enforced | Field ignored (file, template, git, github, imbi) |

**Example - Long-running migration:**
```toml
[[actions]]
name = "migrate-codebase"
type = "claude"
task_prompt = "prompts/migration.md.j2"
max_cycles = 10
timeout = "1h"  # 1 hour per cycle, up to 10 hours total
```

**Example - Shell command with timeout:**
```toml
[[actions]]
name = "run-tests"
type = "shell"
command = "pytest --slow"
timeout = "15m"
```

**Notes:**
- Working directory preserved for resumability after timeout
- Timeout errors include action name, cycle info (for Claude), and duration
- Use `--resume` to continue after investigating timeout issues

### ResourceUrl Schemes

| Scheme | Maps To |
|--------|---------|
| `repository:///` | `{working_dir}/repository/` |
| `workflow:///` | `{working_dir}/workflow/` |
| `extracted:///` | `{working_dir}/extracted/` |
| `file:///` | `{working_dir}/` (default) |
| `external:///` | Absolute path (for exports) |

### Conditions

**Remote (pre-clone, faster):** `remote_file_exists`, `remote_file_not_exists`, `remote_file_contains`
**Local (post-clone):** `file_exists`, `file_not_exists`, `file_contains`
**Template:** `when` with Jinja2 expression

## Claude Actions

```toml
[[actions]]
name = "migrate-code"
type = "claude"
planning_prompt = "prompts/planning.md.j2"  # Optional: enables planning phase
task_prompt = "prompts/task.md.j2"          # Required
validation_prompt = "prompts/validate.md.j2" # Optional
max_cycles = 5
ai_commit = true
```

**Execution per cycle:**
1. **Planning** (if configured): Read-only analysis, returns `{plan: [...], analysis: "...", skip_task: bool}`
2. **Task**: Executes changes, runs in `working_directory/repository/`
3. **Validation** (if configured): Verifies work, returns `{validated: bool, errors: [...]}`

Planning agent can set `skip_task=True` to skip task/validation when no work needed.

### MCP Servers

```toml
[mcp_servers.postgres]
type = "stdio"
command = "uvx"
args = ["mcp-server-postgres", "${DATABASE_URL}"]
```

Supports `stdio`, `sse`, `http` transports. Environment variables expanded at runtime.

### Claude Code Plugins

Plugin configuration can be specified in both the main configuration file and workflow files. Workflow settings merge with main config (workflow values take precedence).

**Main configuration (`config.toml`):**
```toml
[claude_code.plugins.enabled_plugins]
"code-formatter@company-tools" = true
"linter@company-tools" = true

[claude_code.plugins.marketplaces.company-tools]
source = "github"
repo = "company-org/claude-plugins"

[[claude_code.plugins.local_plugins]]
path = "/path/to/local/plugin"
```

**Workflow configuration (`workflow.toml`):**
```toml
[plugins.enabled_plugins]
"workflow-specific@marketplace" = true

[plugins.marketplaces.workflow-marketplace]
source = "git"
url = "https://git.example.com/plugins.git"
```

**Marketplace source types:**
| Type | Required Field | Description |
|------|----------------|-------------|
| `github` | `repo` | GitHub repository (e.g., `org/repo`) |
| `git` | `url` | Any git URL |
| `directory` | `path` | Local directory (dev only) |

**Merging behavior:**
- `enabled_plugins`: Merged, workflow overrides main
- `marketplaces`: Merged, workflow overrides same-key entries
- `local_plugins`: Concatenated, duplicates removed by path

## Workflow Resumability

```bash
imbi-automations config.toml workflow --project-id 123 --preserve-on-error
imbi-automations config.toml workflow --resume ./errors/workflow/project-timestamp
```

State saved in `.state` file (MessagePack format) with:
- Workflow/project identification
- Failed action index/name, completed indices
- Stage tracking (`current_stage`, `followup_cycle`, PR info)
- Configuration hash for change detection

## Code Style

- **Line length**: 79 chars (ruff enforced)
- **Python**: 3.12+ with type hints
- **Quotes**: Single preferred, double for docstrings
- **Imports**: Module imports over direct class imports
- **Pydantic**: Use `field: list[int] = []` not `Field(default_factory=list)`

## Testing

- Base class: `AsyncTestCase` (extends `unittest.IsolatedAsyncioTestCase`)
- HTTP mocking: `httpx.MockTransport` with JSON fixtures in `tests/data/`
- 480 tests with full async support

## CI/CD

**Workflows:**
- `test.yml`: pytest, ruff, coverage (on push/PR)
- `docker.yml`: Multi-arch builds, pushes on release
- `publish.yml`: PyPI via trusted publishing

**Release:** Update `pyproject.toml` version → tag `vX.Y.Z` → create GitHub release

## Key Implementation Details

### Imbi Metadata Cache (`imc.py`)
- 15-minute TTL, stored in `~/.cache/imbi-automations/metadata.json`
- Caches: environments, project types, fact types with enums/ranges
- Validates workflow filters at parse time

### GitHub Actions (`actions/github.py`)
- `sync_environments`: Syncs Imbi environments to GitHub
- `update_repository`: Updates repo attributes via Jinja2 templates

### Context Variables (available in templates)
- `workflow`, `imbi_project`, `github_repository`
- `working_directory`, `starting_commit`, `variables`
- Followup stage adds: `pull_request`, `pr_branch`
