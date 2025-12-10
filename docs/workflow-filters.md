# Workflow Filters

Project filters reduce the scope of workflow execution by pre-filtering projects based on Imbi metadata before any workflow processing begins. This is the first and most efficient level of project selection.

## When to Use Filters

**Use filters when you want to:**

- Target specific project types (APIs, consumers, libraries, etc.)
- Select projects with specific technology stacks
- Require GitHub integration
- Exclude projects with passing builds (target only failing ones)
- Process only a specific subset of projects

**Performance benefit:** Filtered-out projects are never processed, saving API calls, cloning, and condition evaluation.

## Filter Configuration

Filters are defined in the `[filter]` section of `config.toml`:

```toml
[filter]
project_ids = [123, 456, 789]
project_types = ["api", "consumer"]
project_facts = {"Programming Language" = "Python 3.12"}
project_environments = ["production", "staging"]
github_identifier_required = true
github_workflow_status_exclude = ["success"]

# New: Flexible field filtering
[filter.project.description]
is_empty = true

[filter.project.name]
regex = "^api-.*"
```

**Filter Logic:** ALL filter criteria must match (AND logic). A project must satisfy every filter to be included.

## Filter Fields

### project_ids

Target specific projects by their Imbi project ID.

**Type:** `list[int]`  

**Default:** `[]` (no ID filtering)  


```toml
[filter]
project_ids = [42, 108, 256]
```

**Use cases:**

- Testing workflows on specific projects
- Fixing issues in known problem projects
- Updating projects that failed in a previous run

**Example from real workflow:**
```toml
# Test workflow on three projects before full rollout
[filter]
project_ids = [123, 456, 789]
```

### project_types

Filter by project type slugs from Imbi.

**Type:** `list[string]`  

**Default:** `[]` (no type filtering)  


**Common project types:**

- `api` / `apis` - REST APIs and web services
- `backend-libraries` - Shared backend libraries
- `bots` - Chat and automation bots
- `cli` / `clis` - Command-line tools
- `consumer` / `consumers` - Message queue consumers
- `daemon` / `daemons` - Background services
- `frontend` - Web frontends
- `plugin` / `plugins` - Extension plugins
- `scheduled-job` / `scheduled-jobs` - Cron-like tasks

```toml
[filter]
project_types = ["api", "consumer", "daemon"]
```

**Real-world example:**
```toml
[filter]
project_types = [
    "apis",
    "backend-libraries",
    "bots",
    "clis",
    "consumers",
    "daemons",
    "plugin",
    "scheduled-jobs"
]
```

**Why this filter?** Excludes frontend projects that don't use Python setup.cfg files.

### project_facts

Filter by exact Imbi project fact values.

**Type:** `dict[string, string]`  

**Default:** `{}` (no fact filtering)  


**Fact matching:**

- Keys are fact names (case-sensitive)
- Values must match exactly
- ALL specified facts must match (AND logic)

```toml
[filter]
project_facts = {
    "Programming Language" = "Python 3.12",
    "Framework" = "FastAPI"
}
```

Only projects with BOTH `Programming Language = "Python 3.12"` AND `Framework = "FastAPI"` will be included.

**Real-world example:**
```toml
[filter]
project_facts = {"programming_language" = "Python 3.9"}
```

**Why this filter?** Targets only Python 3.9 projects that need updating.

**Common fact names:**

- `Programming Language` - e.g., "Python 3.12", "TypeScript", "Go"
- `Framework` - e.g., "FastAPI", "Flask", "Express"
- `Database` - e.g., "PostgreSQL", "MongoDB"
- `Message Queue` - e.g., "RabbitMQ", "SQS"
- `Deployment Platform` - e.g., "Kubernetes", "ECS"

### project_environments

Filter by Imbi project environments.

**Type:** `list[string]`  

**Default:** `[]` (no environment filtering)  


**Environment matching:**

- Supports both environment names ("Production") and slugs ("production")
- ALL specified environments must be present in project (AND logic)
- Matches against both `name` and `slug` fields of `ImbiEnvironment` objects

```toml
[filter]
project_environments = ["production", "staging"]
```

Only projects with BOTH production AND staging environments will be included.

**Real-world example:**
```toml
[filter]
project_environments = ["Production", "Staging", "Development"]
```

**Why this filter?** Target only projects with complete environment configurations for deployment workflows.

**Flexible matching:**
```toml
# These are all equivalent:
project_environments = ["Production"]
project_environments = ["production"]
project_environments = ["PRODUCTION"]
```

The filter checks against both the original environment name and the auto-generated slug.

### github_identifier_required

Require projects to have a GitHub repository identifier.

**Type:** `boolean`  

**Default:** `false`  


```toml
[filter]
github_identifier_required = true
```

**Use cases:**

- GitHub-specific workflows (workflow fixes, PR automation)
- Projects that must have CI/CD
- Excluding archived projects without GitHub integration

**Real-world example:**
```toml
[filter]
github_identifier_required = true
```

**Why this filter?** Workflow creates pull requests, so GitHub integration is required.

### project

Filter projects based on arbitrary field conditions with flexible operators.

**Type:** `dict[string, ProjectFieldFilter]`  

**Default:** `{}` (no field filtering)  

**Available operators:**

- `is_null` - Check if field is None
- `is_not_null` - Check if field is not None
- `is_empty` - Check if field is None OR empty string
- `equals` - Exact value match
- `not_equals` - Value must not match
- `contains` - Substring search (strings only)
- `regex` - Pattern matching (strings only)

**Key constraint:** Only ONE operator per field filter.

```toml
# Filter projects without descriptions
[filter.project.description]
is_empty = true

# Filter projects by name pattern
[filter.project.name]
regex = "^api-.*"

# Filter projects with specific archived status
[filter.project.archived]
equals = false
```

**Common use cases:**

**Find projects missing metadata:**
```toml
[filter.project.description]
is_empty = true
```

**Target projects by name pattern:**
```toml
[filter.project.name]
regex = "^(api|service)-"
```

**Exclude archived projects:**
```toml
[filter.project.archived]
equals = false
```

**Find projects with specific text:**
```toml
[filter.project.description]
contains = "legacy"
```

**Available project fields:**

- `name` - Project name
- `slug` - Project slug
- `description` - Project description
- `archived` - Whether project is archived
- `project_type_name` - Project type name
- `project_type_slug` - Project type slug
- `namespace_slug` - Namespace slug
- Any custom fields on `ImbiProject` model

**Real-world example:**
```toml
# Find Python projects without descriptions
[filter]
project_facts = {"Programming Language" = "Python 3.12"}

[filter.project.description]
is_empty = true
```

**Performance:** Field filters evaluate against cached Imbi data, making them very fast.

**Validation:** Fields are checked for existence at runtime. Non-existent fields cause projects to be filtered out with a warning.

### github_workflow_status_exclude

Exclude projects with specific GitHub Actions workflow statuses.

**Type:** `list[string]`

**Default:** `[]` (no status filtering)


**Valid statuses:**

- `"success"` - All workflows passing
- `"failure"` - At least one workflow failing
- `"pending"` - Workflows currently running
- `"skipped"` - Workflows skipped

```toml
[filter]
github_workflow_status_exclude = ["success"]
```

Only projects with failing, pending, or no workflows will be processed.

**Real-world example:**
```toml
[filter]
github_workflow_status_exclude = ["success"]
```

**Why this filter?** No need to process projects with passing builds - they don't need fixes.

**Common patterns:**
```toml
# Only process failing builds
[filter]
github_workflow_status_exclude = ["success", "pending", "skipped"]

# Exclude projects with active/passing workflows
[filter]
github_workflow_status_exclude = ["success", "pending"]

# Only process completely broken projects
[filter]
github_workflow_status_exclude = ["success", "pending"]
```

### exclude_open_workflow_prs

Exclude projects that already have open pull requests for a specific workflow.

**Type:** `bool | string`

**Default:** `false` (no PR filtering)


**Behavior:**

- `false` - Filter disabled (default)
- `true` - Exclude projects with open PRs for the **current workflow**
- `"workflow-slug"` - Exclude projects with open PRs for the **specified workflow**

**PR states that cause exclusion:**

- **Open PRs** (including drafts) - Work still in progress
- **Closed unmerged PRs** - Failed or abandoned changes

**Why exclude closed-unmerged PRs?** They indicate issues or rejected changes that should be resolved before re-running the workflow.

```toml
[filter]
exclude_open_workflow_prs = true
```

Projects with open PRs for this workflow will be skipped.

**Real-world examples:**

```toml
# Prevent duplicate PRs for same workflow
[filter]
project_types = ["api", "consumer"]
github_identifier_required = true
exclude_open_workflow_prs = true  # Skip if PR already exists
```

```toml
# Cross-workflow dependency
name = "Secondary Workflow"

[filter]
# Only run after primary workflow PR is merged
exclude_open_workflow_prs = "primary-workflow"
```

```toml
# Combined with other filters
[filter]
project_types = ["api"]
project_facts = {"Programming Language" = "Python 3.12"}
github_identifier_required = true
github_workflow_status_exclude = ["success"]
exclude_open_workflow_prs = true  # Skip projects with pending PRs
```

**Why this filter?** Prevents creating duplicate PRs when:
- Projects haven't updated their Imbi facts yet
- PRs haven't been reviewed or merged yet
- Workflow re-runs before previous execution completes

**How it works:**

The filter checks for PRs with head branch matching `imbi-automations/{workflow-slug}`:

1. **Branch identification:** Each workflow creates PRs on branch `imbi-automations/{slug}`
2. **PR state check:** Looks for open, draft, or closed-unmerged PRs
3. **Exclusion logic:** If blocking PR found, skip the project

**Error handling:**

Uses fail-open approach: API failures or errors log warnings but allow the project through. This prevents transient GitHub API issues from blocking valid workflow executions.

**Performance note:**

This filter requires a GitHub API call per project, so it's placed after cheap filters (IDs, types, facts) but before repository cloning. Projects filtered out here avoid the expensive git clone operation.

**Use cases:**

1. **Prevent duplicate work:**
   - Don't re-run if PR already exists
   - Wait for facts to update before next run

2. **Sequential workflows:**
   - Workflow B waits for Workflow A's PR to merge
   - Cross-workflow orchestration

3. **Manual review workflows:**
   - Create PR, wait for approval
   - Don't create new PR until previous is handled

**Example workflow sequence:**

```
Day 1: Workflow runs → Creates PR #42 → Left open for review
Day 2: Workflow runs → Sees open PR #42 → Skips project
Day 3: PR #42 merged → Facts updated → Workflow runs → Allowed
```

## Complete Real-World Example

This is the actual filter from the example-workflow workflow:

```toml
[filter]
github_identifier_required = true
github_workflow_status_exclude = ["success"]
project_facts = {"programming_language" = "Python 3.9"}
project_types = [
    "apis",
    "backend-libraries",
    "bots",
    "clis",
    "consumers",
    "daemons",
    "plugin",
    "scheduled-jobs"
]
```

**What this filter does:**

1. ✅ **Must have GitHub** (`github_identifier_required = true`)
   - Excludes projects without GitHub integration
   - Ensures PR creation will work

2. ✅ **Exclude passing builds** (`github_workflow_status_exclude = ["success"]`)
   - Only processes projects with failing or missing workflows
   - Avoids unnecessary work on healthy projects

3. ✅ **Python 3.9 only** (`project_facts = {"programming_language" = "Python 3.9"}`)
   - Targets exactly Python 3.9 projects
   - Excludes Python 3.10, 3.11, 3.12, etc.

4. ✅ **Backend projects only** (`project_types = [...]`)
   - Includes APIs, libraries, CLIs, consumers, etc.
   - Excludes frontend projects that don't have setup.cfg

**Result:** From 1000 total projects → ~50 projects that need fixing

## Filter Evaluation Flow

```
All Projects (1000)
    ↓
github_identifier_required = true
    ↓ (excludes 200 projects without GitHub)
800 projects remain
    ↓
github_workflow_status_exclude = ["success"]
    ↓ (excludes 600 projects with passing builds)
200 projects remain
    ↓
project_facts = {"programming_language" = "Python 3.9"}
    ↓ (excludes 120 non-Python-3.9 projects)
80 projects remain
    ↓
project_types = ["apis", "consumers", ...]
    ↓ (excludes 30 frontend projects)
50 projects match all filters
```

These 50 projects then proceed to workflow condition evaluation.

## Common Filter Patterns

### Target Specific Technology Stack

```toml
[filter]
project_facts = {
    "Programming Language" = "Python 3.12",
    "Framework" = "FastAPI",
    "Database" = "PostgreSQL"
}
```

### Python Projects with Failing Builds

```toml
[filter]
project_types = ["api", "consumer", "daemon"]
project_facts = {"Programming Language" = "Python 3.12"}
github_identifier_required = true
github_workflow_status_exclude = ["success"]
```

### Specific Project Type Without GitHub

```toml
[filter]
project_types = ["backend-libraries"]
# No github_identifier_required - includes non-GitHub projects
```

### Testing Filter (Small Subset)

```toml
[filter]
project_ids = [42, 108, 256]  # Test on 3 projects first
```

### All Python Projects

```toml
[filter]
# Use facts to match any Python version
project_facts = {"Programming Language" = "Python"}  # Won't work - needs exact match

# Better: Use multiple workflows or no filter + conditions
```

**Note:** Fact filtering requires exact matches. For partial matching, use workflow conditions with regex.  

### Projects Needing GitHub Actions

```toml
[filter]
github_identifier_required = true
# Then use conditions to check for specific workflow files
```

## Filter Performance

**Filters are the most efficient project selection mechanism:**

- ✅ **No API calls** - Uses cached Imbi data
- ✅ **No git operations** - No cloning or remote checks
- ✅ **Fast evaluation** - Simple equality checks
- ✅ **Early elimination** - Reduces downstream processing

**Performance comparison for 1000 projects:**

| Method | Projects Processed | API Calls | Git Clones |
|--------|-------------------|-----------|------------|
| No filters | 1000 | 1000+ | 1000 |
| With filters | 50 | 50+ | 50 |

**Best practice:** Use filters to get close to your target set, then use workflow conditions for fine-grained selection.

## Filter vs Condition vs CLI Argument

### CLI Arguments
**Scope:** Initial project selection
**Speed:** ⚡⚡⚡ Fastest
**Use for:** One-off targeting, testing

```bash
--project-id 123
--project-type api
--all-projects
```

### Filters
**Scope:** Workflow-level pre-filtering
**Speed:** ⚡⚡ Very fast
**Use for:** Broad targeting, technology stack selection

```toml
[filter]
project_types = ["api"]
project_facts = {"Programming Language" = "Python 3.12"}
```

### Workflow Conditions
**Scope:** Repository state checks
**Speed:** ⚡ Fast (remote) or 🐌 Slow (local)
**Use for:** File existence, content checking

```toml
[[conditions]]
remote_file_exists = "package.json"
```

### Action Conditions
**Scope:** Per-action execution control
**Speed:** ⚡ Fast (already cloned)
**Use for:** Conditional behavior within workflow

```toml
[[actions.conditions]]
file_exists = "setup.py"
```

## Combining Filters with Other Mechanisms

### Filter + Workflow Conditions

```toml
# Filter: Broad technology targeting
[filter]
project_types = ["api"]
project_facts = {"Programming Language" = "Python 3.12"}

# Conditions: Specific repository requirements
[[conditions]]
remote_file_exists = "pyproject.toml"

[[conditions]]
remote_file_contains = "fastapi"
remote_file = "pyproject.toml"
```

**Result:** FastAPI projects using Python 3.12 with pyproject.toml

### Filter + CLI Arguments

```bash
# CLI: Specific project type
imbi-automations config.toml workflows/update-python --project-type api

# Workflow filter: Further refinement
[filter]
project_facts = {"Programming Language" = "Python 3.12"}
github_identifier_required = true
```

**Result:** Python 3.12 APIs with GitHub integration

### Filter + Action Conditions

```toml
# Filter: Python projects
[filter]
project_facts = {"Programming Language" = "Python 3.12"}

[[actions]]
name = "update-setup-py"
type = "file"

# Action condition: Only if setup.py exists
[[actions.conditions]]
file_exists = "setup.py"

[[actions]]
name = "update-pyproject"
type = "file"

# Action condition: Only if pyproject.toml exists
[[actions.conditions]]
file_exists = "pyproject.toml"
```

**Result:** Python 3.12 projects, with different actions for setup.py vs pyproject.toml

## See Also

- [Workflow Conditions](workflow-conditions.md) - File existence and content checking
- [Workflow Configuration](workflow-configuration.md) - Complete configuration reference
- [Workflows Overview](workflows.md) - High-level concepts and best practices
