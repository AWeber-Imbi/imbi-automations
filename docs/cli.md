# Command-Line Interface

Imbi Automations provides a comprehensive CLI for executing workflows across projects with flexible targeting, concurrency control, and debugging capabilities.

## Basic Usage

```bash
imbi-automations CONFIG WORKFLOW [OPTIONS]
```

**Arguments:**

- `CONFIG`: Path to configuration TOML file
- `WORKFLOW`: Path to workflow directory containing config.toml

**Example:**
```bash
imbi-automations config.toml workflows/update-python --all-projects
```

## Complete Syntax

```bash
imbi-automations [-h] [-V] [--debug] [-v]
                 [--max-concurrency N]
                 [--exit-on-error]
                 [--preserve-on-error]
                 [--error-dir DIR]
                 [--dry-run]
                 [--dry-run-dir DIR]
                 [--cache-dir DIR]
                 [--start-from-project ID_OR_SLUG]
                 (--project-id ID |
                  --project-type SLUG |
                  --all-projects |
                  --github-repository URL |
                  --github-organization ORG |
                  --all-github-repositories)
                 CONFIG WORKFLOW
```

## Positional Arguments

### CONFIG

Path to configuration file containing API credentials and settings.

**Type:** File path
**Format:** TOML file  

**Required:** Yes  

**Example:**
```bash
imbi-automations config.toml workflows/my-workflow --all-projects
imbi-automations /etc/imbi/prod.toml workflows/deploy --all-projects
```

**See Also:** [Configuration Documentation](configuration.md)

### WORKFLOW

Path to workflow directory containing workflow configuration file.

**Type:** Directory path
**Required:** Yes
**Must Contain:** `workflow.toml`

**Example:**
```bash
imbi-automations config.toml workflows/update-python --all-projects
imbi-automations config.toml ./my-workflow --project-id 123
```

**Structure:**
```
workflows/my-workflow/
├── workflow.toml        # Required
├── prompts/             # Optional
│   └── prompt.md
└── templates/           # Optional
    └── template.j2
```

## Targeting Options

**Exactly one** targeting option is required to specify which projects/repositories to process.

### --project-id ID

Process a single Imbi project by ID.

**Type:** Integer
**Use Case:** Testing workflows on specific project

**Example:**
```bash
imbi-automations config.toml workflows/fix-config --project-id 123
```

**Output:**
```
Processing: my-project (123)
✓ Completed: my-project
```

### --project-type SLUG

Process all Imbi projects of a specific type.

**Type:** String (project type slug)
**Use Case:** Target specific project categories

**Example:**
```bash
imbi-automations config.toml workflows/update-apis --project-type api
```

**Common Project Types:**

- `api` - API services
- `consumer` - Message consumers
- `scheduled-job` - Scheduled tasks
- `frontend` - Frontend applications
- `library` - Shared libraries

**Output:**
```
Found 47 projects of type 'api'
Processing: api-service-1 (123)
Processing: api-service-2 (124)
...
Completed: 45/47 projects successful
```

### --all-projects

Process all projects in Imbi.

**Type:** Flag (boolean)
**Use Case:** Batch updates across entire organization

**Example:**
```bash
imbi-automations config.toml workflows/update-deps --all-projects
```

**Output:**
```
Found 664 total projects
Processing 664 projects...
✓ Completed: 650/664 successful
```

**Warning:** This processes ALL projects. Use with caution and test workflow first with `--project-id`.

### --github-repository URL

Process a single GitHub repository by URL.

**Type:** URL string
**Format:** `https://github.com/org/repo` or `org/repo`  

**Use Case:** Target specific GitHub repository

**Example:**
```bash
imbi-automations config.toml workflows/fix-actions \
  --github-repository https://github.com/myorg/myrepo
```

**Accepted Formats:**
```bash
--github-repository https://github.com/org/repo
--github-repository github.com/org/repo
--github-repository org/repo
```

### --github-organization ORG

Process all repositories in a GitHub organization.

**Type:** String (organization name)
**Use Case:** Update all repos in an organization

**Example:**
```bash
imbi-automations config.toml workflows/update-workflows \
  --github-organization myorg
```

**Output:**
```
Found 32 repositories in organization 'myorg'
Processing: myorg/repo1
Processing: myorg/repo2
...
Completed: 30/32 successful
```

### --all-github-repositories

Process all GitHub repositories across all organizations.

**Type:** Flag (boolean)
**Use Case:** Organization-wide GitHub updates

**Example:**
```bash
imbi-automations config.toml workflows/security-update \
  --all-github-repositories
```

**Note:** Discovers repositories from all organizations the API key has access to.  

## Execution Control Options

### --start-from-project ID_OR_SLUG

Resume batch processing from a specific project.

**Type:** Integer (ID) or String (slug)
**Use Case:** Resume interrupted batch runs

**Example:**
```bash
# By project ID
imbi-automations config.toml workflows/update-all \
  --all-projects \
  --start-from-project 456

# By project slug
imbi-automations config.toml workflows/update-all \
  --all-projects \
  --start-from-project my-project-slug
```

**Behavior:**  

- Skips all projects up to and including the specified project
- Starts processing from the next project
- Useful for resuming after interruption or failure

**Example Scenario:**
```bash
# Initial run interrupted at project ID 456
imbi-automations config.toml workflows/big-update --all-projects
# ... processes projects 1-456, then interrupted

# Resume from where it left off
imbi-automations config.toml workflows/big-update \
  --all-projects \
  --start-from-project 456
# ... starts from project 457
```

### --max-concurrency N

Set maximum number of concurrent workflow executions.

**Type:** Integer
**Default:** `1` (sequential)  
**Range:** 1-100 (practical limit depends on system resources)

**Example:**
```bash
# Process 5 projects simultaneously
imbi-automations config.toml workflows/update-deps \
  --all-projects \
  --max-concurrency 5
```

**Performance Considerations:**

| Concurrency | Use Case | Memory | Risk |
|-------------|----------|--------|------|
| 1 | Debugging, testing | Low | None |
| 2-5 | Normal batch processing | Medium | Low |
| 10+ | Large-scale updates | High | Higher |
| 20+ | Maximum throughput | Very High | Monitor carefully |

**Example Performance:**
```bash
# Sequential (slower, safer)
--max-concurrency 1
# ~1 project/minute = 664 projects in 11 hours

# Parallel (faster, more resources)
--max-concurrency 10
# ~10 projects/minute = 664 projects in 1.1 hours
```

**Warning:** Higher concurrency increases:

- Memory usage (each workflow uses ~100-500MB)
- API rate limit pressure
- Disk I/O (simultaneous git clones)
- Debugging complexity

### --exit-on-error

Stop immediately when any project fails.

**Type:** Flag (boolean)
**Default:** `false` (continue with other projects)  

**Example:**
```bash
imbi-automations config.toml workflows/critical-update \
  --all-projects \
  --exit-on-error
```

**Behavior:**  

- **Without flag:** Logs error, continues to next project
- **With flag:** Exits immediately with error code

**Use Cases:**  

- CI/CD pipelines requiring atomic success
- Testing workflows before batch runs
- Critical updates that must succeed for all projects
- Debugging specific failure

**Example Comparison:**
```bash
# Default: continues on error
imbi-automations config.toml workflows/update --all-projects
# Processes all 664 projects even if some fail
# Exit code: 0 if any succeeded

# Exits on first error
imbi-automations config.toml workflows/update --all-projects --exit-on-error
# Stops at first failure
# Exit code: 5 on failure
```

## Debugging Options

### --preserve-on-error

Save working directory state when workflows fail.

**Type:** Flag (boolean)
**Default:** `false`  

**Example:**
```bash
imbi-automations config.toml workflows/failing-workflow \
  --project-id 123 \
  --preserve-on-error
```

**What Gets Saved:**

- Complete Git repository state
- Workflow resource files
- Docker extracted files
- All temporary files
- `debug.log` with complete execution trace

**Storage Location:** `./errors/workflow-name/project-slug-timestamp/`

**See Also:** [Debugging Documentation](debugging.md)

### --error-dir DIR

Specify directory for saving error states.

**Type:** Directory path
**Default:** `./errors`  

**Example:**
```bash
imbi-automations config.toml workflows/test \
  --project-id 123 \
  --preserve-on-error \
  --error-dir /tmp/workflow-errors
```

**Directory Structure:**  
```
/tmp/workflow-errors/
└── workflow-name/
    └── project-slug-20250103-143052/
        ├── repository/
        ├── workflow/
        └── debug.log
```

### --dry-run

Execute workflows without pushing changes or creating pull requests.

**Type:** Flag (boolean)
**Default:** `false`  

**Example:**
```bash
imbi-automations config.toml workflows/update-deps \
  --project-id 123 \
  --dry-run
```

**Behavior:**  

When enabled, the workflow executes normally including:
- Cloning repositories
- Running all actions
- Making file changes
- Creating commits locally

**But skips:**

- Pushing commits to remote
- Creating pull requests

**Working directory is preserved to:** `./dry-runs/workflow-name/project-slug-timestamp/`

**Use Cases:**  

- Testing workflows before production runs
- Validating changes without affecting remote repositories
- Reviewing commit messages and file changes
- Debugging workflow logic safely
- Training and demonstration

**Example Output:**
```bash
Processing: my-project (123)
✓ Cloned repository
✓ Executed 5 actions
✓ Created commit: "Update dependencies"
🔍 dry-run mode: saving repository state to ./dry-runs
✓ Completed: my-project (dry-run)
```

**Inspection:**
```bash
# View the commit that would have been pushed
cd dry-runs/update-deps/my-project-20250103-143052/repository
git log -1
git show HEAD

# View all changes
git diff HEAD~1
```

**See Also:** [Debugging - Dry Run Mode](debugging.md#dry-run-mode)

### --dry-run-dir DIR

Specify directory for saving dry-run repository states.

**Type:** Directory path
**Default:** `./dry-runs`

**Example:**
```bash
imbi-automations config.toml workflows/update \
  --all-projects \
  --dry-run \
  --dry-run-dir /tmp/review-changes
```

**Docker:** When running in Docker, use `--dry-run-dir /opt/dry-runs` and mount a host directory to `/opt/dry-runs` to persist dry-run artifacts outside the container.

**Directory Structure:**  
```
/tmp/review-changes/
└── workflow-name/
    └── project-slug-20250103-143052/
        ├── repository/        # Full git repository with commits
        ├── workflow/          # Workflow files and templates
        └── extracted/         # Docker extracted files (if any)
```

**Use Cases:**  

- Organize dry runs by date or workflow
- Review changes across multiple projects
- Share results with team for review
- Temporary storage for CI/CD validation
- Custom inspection pipelines

**Example with Batch Review:**
```bash
# Run dry-run on all projects
imbi-automations config.toml workflows/security-patch \
  --all-projects \
  --dry-run \
  --dry-run-dir ./review/$(date +%Y%m%d)

# Review all changes
for dir in ./review/*/workflow-name/*/repository; do
    echo "=== $(basename $(dirname $dir)) ==="
    cd "$dir"
    git log -1 --oneline
    git diff HEAD~1 --stat
done
```

### --cache-dir DIR

Specify directory for Imbi metadata cache storage.

**Type:** Directory path
**Default:** `~/.cache/imbi-automations`  

**Example:**
```bash
imbi-automations config.toml workflows/update \
  --all-projects \
  --cache-dir /tmp/imbi-cache
```

**Use Cases:**  

- Custom cache location for multi-user systems
- Temporary cache for testing
- Network-mounted cache for shared environments
- CI/CD pipeline isolation

**Cache Contents:**

The cache directory will contain `metadata.json` with Imbi metadata including environments, project types, and fact type definitions. This cache is automatically refreshed every 15 minutes.

**See Also:** [Configuration - Imbi Metadata Cache](configuration.md#imbi-metadata-cache)

### --debug

Enable DEBUG level logging for all components.

**Type:** Flag (boolean)
**Default:** `false` (INFO level)  

**Example:**
```bash
imbi-automations config.toml workflows/test \
  --project-id 123 \
  --debug
```

**Output:**
```
2025-01-03 14:30:52 - imbi_automations.workflow_engine - DEBUG - Executing action: copy-files
2025-01-03 14:30:52 - imbi_automations.actions.filea - DEBUG - Copying workflow:///template to repository:///config
2025-01-03 14:30:52 - imbi_automations.utils - DEBUG - Resolved path: /tmp/workflow123/workflow/template
```

**Log Categories:**

- Action execution details
- HTTP requests/responses (API calls)
- Git operations
- File operations
- Template rendering
- Condition evaluation

**See Also:** [Debugging Documentation](debugging.md)

### -v, --verbose

Show action start/end INFO messages.

**Type:** Flag (boolean)
**Default:** `false`  

**Example:**
```bash
imbi-automations config.toml workflows/update \
  --project-id 123 \
  --verbose
```

**Output:**
```
2025-01-03 14:30:50 - INFO - Starting action: backup-files
2025-01-03 14:30:52 - INFO - Completed action: backup-files
2025-01-03 14:30:52 - INFO - Starting action: update-configs
```

**Difference from --debug:**

- `--verbose`: Action-level progress (cleaner output)
- `--debug`: Everything (very detailed)

## General Options

### -h, --help

Show help message and exit.

**Example:**
```bash
imbi-automations --help
```

### -V, --version

Show version number and exit.

**Example:**
```bash
imbi-automations --version
```

**Output:**
```
0.1.0
```

## Common Usage Patterns

### Test on Single Project

Test workflow before batch execution:

```bash
imbi-automations config.toml workflows/new-workflow \
  --project-id 123 \
  --preserve-on-error \
  --debug
```

### Dry Run Testing

Test workflow without making remote changes:

```bash
# Single project dry run
imbi-automations config.toml workflows/new-feature \
  --project-id 123 \
  --dry-run \
  --debug

# Batch dry run for review
imbi-automations config.toml workflows/update-all \
  --all-projects \
  --dry-run \
  --dry-run-dir ./review \
  --max-concurrency 5
```

### Batch Update with Debugging

Process all projects with error preservation:

```bash
imbi-automations config.toml workflows/update-deps \
  --all-projects \
  --max-concurrency 5 \
  --preserve-on-error \
  --error-dir ./errors \
  --verbose
```

### Resume Interrupted Run

Continue from where you left off:

```bash
imbi-automations config.toml workflows/large-update \
  --all-projects \
  --start-from-project 456 \
  --max-concurrency 5
```

### GitHub Organization Update

Update all repos in an organization:

```bash
imbi-automations config.toml workflows/update-actions \
  --github-organization myorg \
  --max-concurrency 3 \
  --verbose
```

### Critical Production Update

Ensure all or nothing success:

```bash
imbi-automations config.toml workflows/security-patch \
  --all-projects \
  --exit-on-error \
  --preserve-on-error \
  --verbose
```

### Debugging Specific Failure

Deep dive into a failing project:

```bash
imbi-automations config.toml workflows/failing \
  --project-id 123 \
  --preserve-on-error \
  --error-dir ./debug \
  --debug \
  --verbose \
  --exit-on-error
```

### Project Type Targeted Update

Update only APIs:

```bash
imbi-automations config.toml workflows/update-api-configs \
  --project-type api \
  --max-concurrency 5 \
  --verbose
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - all workflows completed successfully |
| 1 | Configuration error (invalid config, missing workflow) |
| 2 | Interrupted (Ctrl+C) |
| 3 | Runtime error (unexpected exception) |
| 5 | Workflow failure (one or more projects failed) |

**Example Usage in Scripts:**
```bash
#!/bin/bash
imbi-automations config.toml workflows/update --all-projects

if [ $? -eq 0 ]; then
    echo "All projects updated successfully"
elif [ $? -eq 5 ]; then
    echo "Some projects failed - check logs"
    exit 1
else
    echo "Fatal error - check configuration"
    exit 1
fi
```

## Environment Variables

While not CLI switches, these environment variables affect behavior:

| Variable | Purpose | Example |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | `sk-ant-api03-...` |
| `GITHUB_TOKEN` | GitHub API token (if not in config) | `ghp_...` |
| `IMBI_API_KEY` | Imbi API key (if not in config) | `uuid-here` |

**Example:**
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
export GITHUB_TOKEN="ghp_..."

imbi-automations config.toml workflows/ai-workflow --all-projects
```

## Performance Tips

### Optimize Concurrency

Start conservative, increase gradually:

```bash
# Test with 1
--max-concurrency 1

# Increase to 5
--max-concurrency 5

# Monitor system resources, adjust
--max-concurrency 10
```

### Use Filtering

Reduce scope with workflow filters in `config.toml`:

```toml
[filter]
project_types = ["api", "consumer"]
github_identifier_required = true
```

### Batch Smartly

Split large runs into chunks:

```bash
# Process 100 at a time
--all-projects --max-concurrency 5 --start-from-project 0
# ... after completion
--all-projects --max-concurrency 5 --start-from-project 100
```

## Troubleshooting

### "No module named imbi_automations"

**Problem:** CLI not installed or not in PATH

**Solution:**
```bash
pip install -e .
# or
pip install imbi-automations
```

### "Workflow path is not a directory"

**Problem:** Incorrect workflow path

**Solution:**
```bash
# Correct - path to directory
imbi-automations config.toml workflows/my-workflow --all-projects

# Incorrect - don't include config.toml
imbi-automations config.toml workflows/my-workflow/config.toml --all-projects
```

### "Exactly one targeting option required"

**Problem:** No targeting flag specified

**Solution:**
```bash
# Must include one of:
--project-id 123
--project-type api
--all-projects
--github-repository org/repo
# etc.
```

### "Configuration validation failed"

**Problem:** Invalid or missing config values

**Solution:**
```bash
# Validate config separately
python -c "from imbi_automations.cli import load_configuration; load_configuration(open('config.toml'))"
```

## Advanced Examples

### Parallel Processing with Error Handling

```bash
imbi-automations config.toml workflows/complex-update \
  --all-projects \
  --max-concurrency 10 \
  --preserve-on-error \
  --error-dir /var/log/imbi-errors \
  --verbose \
  2>&1 | tee workflow.log
```

### Conditional Batch Processing

```bash
#!/bin/bash
# Process projects by type with different concurrency
for type in api consumer scheduled-job; do
    echo "Processing $type projects..."
    imbi-automations config.toml workflows/update \
        --project-type $type \
        --max-concurrency 5 \
        --verbose
done
```

### Error Analysis Pipeline

```bash
#!/bin/bash
# Run workflow with error preservation
imbi-automations config.toml workflows/update \
    --all-projects \
    --preserve-on-error \
    --error-dir ./errors

# Analyze errors
echo "Failed projects:"
find ./errors -name "debug.log" -exec grep -l "ERROR" {} \; | \
    sed 's|.*/\(.*\)-[0-9]*-[0-9]*/debug.log|\1|'

# Count by error type
echo "\nError types:"
find ./errors -name "debug.log" -exec grep "ERROR" {} \; | \
    cut -d: -f4 | sort | uniq -c
```

## See Also

- [Configuration](configuration.md) - Configure API keys and settings
- [Debugging](debugging.md) - Detailed debugging guide
- [Actions](actions/index.md) - Workflow action reference
- [Architecture](architecture.md) - System design and components
