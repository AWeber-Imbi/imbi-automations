# Claude Actions

Claude actions leverage the [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview) for AI-powered code transformations, enabling complex multi-file analysis and intelligent code modifications that would be difficult or error-prone with traditional approaches.

## Configuration

```toml
[[actions]]
name = "action-name"
type = "claude"
planning_prompt = "prompts/planning.md"         # Optional - enables planning phase
task_prompt = "prompts/task.md"                 # Required (formerly 'prompt')
validation_prompt = "prompts/validate.md"       # Optional
max_cycles = 3                                  # Optional, default: 3
on_failure = "cleanup-action"                   # Optional
ai_commit = true                                # Optional, default: true
```

## Fields

### planning_prompt (optional)

Path to Jinja2 template file containing the planning prompt for the planning agent.

**Type:** `string` (path relative to workflow directory)  

**Format:** Jinja2 template (`.j2` extension) or plain markdown  

**Location:** Relative to workflow directory (e.g., `prompts/planning.md`)  

**When Provided:**  

- Enables three-phase execution: Planning → Task → Validation
- Planning agent analyzes codebase before task agent makes changes
- Returns structured plan that gets injected into task prompt
- Plan regenerated fresh at start of each cycle

**Agent Tools:** Read, Glob, Grep, Bash (read-only operations)  

**Response Format:** `mcp__agent_tools__submit_planning_response(plan=[...], analysis="...")`  

### task_prompt (required)

Path to Jinja2 template file containing the task prompt for Claude (formerly named `prompt`).

**Type:** `string` (path relative to workflow directory)  

**Format:** Jinja2 template (`.j2` extension) or plain markdown  

**Location:** Relative to workflow directory (e.g., `prompts/update-python.md`)  

**Working Directory:** Claude SDK runs in `working_directory/repository/` subdirectory  

**Agent Tools:** Read, Write, Edit, Bash (write operations allowed)  

**Response Format:** `mcp__agent_tools__submit_task_response(message="...")`  



### validation_prompt (optional)

Path to validation prompt template. If provided, Claude will run a validation cycle after the task cycle.

**Type:** `string` (path relative to workflow directory)  

**Format:** Jinja2 template (`.j2` extension) or plain markdown  

**Agent Tools:** Read, Bash (read-only verification)  

**Response Format:** `mcp__agent_tools__submit_validation_response(validated=bool, errors=[])`  

**When Provided:**  

- Validation agent checks task agent's work after each cycle
- Returns success (`validated=True`) or failure (`validated=False`) with error list
- Validation failures trigger retry with errors injected into next cycle's prompt
- Validation success completes the action

### max_cycles (optional)

Maximum number of retry cycles if transformation fails validation.

**Type:** `integer`  

**Default:** `3`  

**Behavior:**  

- Each cycle runs: Planning (if enabled) → Task → Validation (if enabled)
- Logs warning at 60% of max cycles (e.g., "Cycle 3 of 5, approaching max_cycles limit")
- If all cycles exhausted, triggers `on_failure` action (if configured)
- Error context from validation failures passed to subsequent cycles


### on_failure (optional)

Action name to restart from if this action fails after all retry cycles.

**Type:** `string` (action name)  


### ai_commit (optional)

Whether to use AI-generated commit messages for changes made by this action.

**Type:** `boolean`  

**Default:** `true`  


## Planning Agent Feature

The planning agent is an optional pre-execution analysis phase that explores the codebase before the task agent makes changes. This provides better context, structured execution, and improved success rates for complex transformations.

### When to Use Planning

**Use planning when:**  

- Transformation requires analysis of multiple files
- Dependencies or patterns need to be identified first
- Task complexity benefits from structured approach
- You want AI to explore before modifying

**Skip planning when:**  

- Simple, single-file modifications
- Task is straightforward and well-defined
- Speed is more important than thorough analysis

### Planning Workflow

**Per-Cycle Execution:**  

1. **Planning Phase** (if `planning_prompt` configured):
   - Planning agent uses read-only tools (Read, Glob, Grep, Bash)
   - Analyzes codebase structure, dependencies, patterns
   - Creates structured plan with specific, actionable task strings
   - Returns `{plan: [...], analysis: "..."}`
   - Plan cleared and regenerated at start of each cycle

2. **Task Phase**:
   - Task agent receives plan injected into prompt via `with-plan.md.j2` template
   - Follows numbered plan with full context from analysis
   - Uses write tools (Read, Write, Edit, Bash)
   - Works in `working_directory/repository/` directory
   - Can access `../workflow/` and `../extracted/` directories

3. **Validation Phase** (if `validation_prompt` configured):
   - Validation agent verifies task agent's work
   - Returns `{validated: bool, errors: [...]}`
   - Errors injected into next cycle if validation fails

### Planning Error Handling

**When planning fails:** Cycle aborts immediately (no task execution)  

**When validation fails:**  

- Planning agent receives `planning-with-errors.md.j2` template
- Explicitly instructed to create NEW PLAN (not fix errors directly)
- Re-analyzes with context of what failed previously

**Critical Fix (commit 561909f):**

- Planning agent was incorrectly trying to fix errors itself
- Now properly re-plans based on validation failures
- Creates new strategy each cycle

### Example with Planning

```toml
[[actions]]
name = "migrate-to-pydantic-v2"
type = "claude"
planning_prompt = "prompts/planning.md.j2"
task_prompt = "prompts/task.md.j2"
validation_prompt = "prompts/validate.md.j2"
max_cycles = 5
```

**Planning Prompt (`prompts/planning.md.j2`):**
```markdown
# Analyze Pydantic Usage

Analyze this codebase to identify all Pydantic v1 usage.

## Analysis Tasks

1. Find all files importing from `pydantic`
2. Identify Pydantic models (classes inheriting BaseModel)
3. Locate validators using `@validator`
4. Find `.dict()` and `.json()` method calls
5. Identify Config classes that need migration

## Output

Return a structured plan with:
- Specific files to update
- Order of operations (dependencies first)
- Potential breaking changes to watch for

Be thorough in your analysis. Check recursively in all Python files.
```

**Task Prompt (`prompts/task.md.j2`):**
```markdown
# Migrate to Pydantic V2

Follow the plan provided to migrate this codebase from Pydantic v1 to v2.

Execute each task in order, making the necessary changes.

Ensure all imports, validators, and method calls are updated.
```

**Validation Prompt (`prompts/validate.md.j2`):**
```markdown
# Validate Pydantic V2 Migration

Verify the migration was successful:

1. Check all imports use Pydantic v2 syntax
2. Verify Config classes converted to model_config
3. Confirm validators use field_validator
4. Ensure .dict()/.json() replaced with .model_dump()/.model_dump_json()
5. Run tests if they exist

Return validated=true if all checks pass, otherwise list specific errors.
```

## Prompt Context

Prompts have access to all workflow context variables:

| Variable | Description |
|----------|-------------|
| `workflow` | Workflow configuration |
| `imbi_project` | Imbi project data |
| `github_repository` | GitHub repository (if applicable) |
| `working_directory` | Execution directory path (task agent runs in `repository/` subdirectory) |
| `starting_commit` | Initial commit SHA |
| `commit_author` | Git commit author string (e.g., "Name <email>") |
| `commit_author_name` | Git author name (from `git.user_name`) |
| `commit_author_address` | Git author email (from `git.user_email`) |
| `workflow_name` | Current workflow name |

## Examples

### Basic Code Transformation (Without Planning)

**Workflow config:**
```toml
[[actions]]
name = "update-python-version"
type = "claude"
task_prompt = "prompts/update-python.md"
```

**Prompt (`prompts/update-python.md`):**
```markdown
# Update Python Version to 3.12

Update all Python version references in this repository to Python 3.12.

## Files to Update

1. `pyproject.toml` - Update `requires-python` field
2. `.github/workflows/*.yml` - Update GitHub Actions Python version
3. `Dockerfile` - Update base image to python:3.12
4. `README.md` - Update installation instructions if they mention Python version

## Requirements

- Maintain backwards compatibility where possible
- Update all version strings consistently
- Preserve existing configuration structure
- Do not modify other unrelated settings

## Project Context

- **Project**: {{ imbi_project.name }}
- **Type**: {{ imbi_project.project_type }}
- **Current Python**: {{ imbi_project.facts.get('Programming Language', 'unknown') }}

## Success Criteria

Create a commit with all Python version references updated to 3.12.

## Failure Indication

If you cannot complete this task, return failure with details about what prevented completion.
```

### Multi-Cycle Transformation with Retry

**Workflow config:**
```toml
[[actions]]
name = "refactor-codebase"
type = "claude"
task_prompt = "prompts/refactor.md"
max_cycles = 5
on_failure = "create-issue"  # Create GitHub issue if fails
```

### With Validator (No Planning)

**Workflow config:**
```toml
[[actions]]
name = "update-dependencies"
type = "claude"
task_prompt = "prompts/update-deps.md"
validation_prompt = "prompts/validate-deps.md"
```

**Validator prompt:**
```markdown
# Validate Dependency Updates

Verify that the dependency updates were successful:

1. Check that `requirements.txt` or `pyproject.toml` has been updated
2. Verify no breaking changes were introduced
3. Confirm all imports still resolve correctly
4. Check that version constraints are reasonable

Return success if validation passes, failure otherwise with specific errors.
```

### Complex Transformation (Without Planning)

**Workflow config:**
```toml
[[actions]]
name = "migrate-to-pydantic-v2"
type = "claude"
task_prompt = "prompts/pydantic-migration.md"
max_cycles = 10
```

**Task Prompt:**
```markdown
# Migrate to Pydantic V2

Migrate this codebase from Pydantic v1 to Pydantic v2.

## Migration Steps

1. **Update imports**: Change `pydantic` imports to v2 syntax
2. **Config classes**: Convert `Config` class to `model_config` dict
3. **Validators**: Update `@validator` to `@field_validator`
4. **Field definitions**: Update `Field(...)` syntax changes
5. **JSON methods**: Replace `.dict()` with `.model_dump()`, `.json()` with `.model_dump_json()`

## Files to Process

Scan the repository for Python files containing:
- `from pydantic import`
- `class.*\\(.*BaseModel\\)`
- `@validator`
- `.dict()` or `.json()` calls on Pydantic models

## Testing

After making changes:
1. Run tests if they exist: `pytest tests/`
2. Check for import errors
3. Verify all models still validate correctly

## Commit Message

````
Migrate from Pydantic v1 to v2

- Update imports to v2 syntax
- Convert Config classes to model_config
- Update validators to field_validator
- Replace .dict()/.json() with .model_dump()/.model_dump_json()

Project: {{ imbi_project.name }}
````

## Failure Conditions

Return failure if:
- Unable to identify Pydantic usage patterns
- Migration would break existing functionality
- Tests fail after migration
- Manual intervention required

Include specific error details and affected files in the failure response.
```

## Prompt Best Practices

### Clear Objectives

```markdown
# Update Docker Base Image

**Goal**: Update the Dockerfile to use python:3.12-slim as the base image.

**Files**: `Dockerfile`, `docker-compose.yml`

**Requirements**:
- Change base image in all Dockerfiles
- Maintain multi-stage build structure if present
- Update docker-compose.yml references
- Keep existing COPY, RUN, CMD instructions
```

### Specific Instructions

```markdown
## Step-by-Step Process

1. Locate all Dockerfile* files in the repository
2. For each Dockerfile:
   a. Find the `FROM` instruction
   b. Replace with `FROM python:3.12-slim`
   c. Keep any `AS builder` or stage names
3. Update docker-compose.yml if it hardcodes Python version
4. Commit changes with message: "Update Python base image to 3.12"
```

### Success/Failure Criteria

```markdown
## Success Criteria

You must:
✓ Update all Dockerfiles  
✓ Maintain working configuration  
✓ Create a git commit  
✓ Include descriptive commit message  

## Failure Indication

Return failure if:
- No Dockerfile found in repository
- Unable to parse existing Dockerfile syntax
- Changes would break the build process
- Multiple conflicting Dockerfile versions exist

Include the specific error and list of files examined in the failure response.
```

### Project Context Usage

```markdown
## Project-Specific Considerations

- **Project**: {{ imbi_project.name }}
- **Type**: {{ imbi_project.project_type }}
- **Namespace**: {{ imbi_project.namespace }}

{% if imbi_project.project_type == 'api' %}
This is an API project - ensure uvicorn/fastapi configurations are preserved.
{% elif imbi_project.project_type == 'consumer' %}
This is a consumer - ensure message handling configurations are intact.
{% endif %}

{% if imbi_project.facts %}
## Known Facts
{% for key, value in imbi_project.facts.items() %}
- **{{ key }}**: {{ value }}
{% endfor %}
{% endif %}
```

## Failure Handling

### Failure Files

Claude actions detect failure through specific files created in the working directory:

| File Name | Meaning |
|-----------|---------|
| `ACTION_FAILED` | Generic action failure |
| `{ACTION_NAME}_FAILED` | Specific action failure |
| Custom names | Custom failure indicators |

**Prompt instructions for failure:**
```markdown
## Failure Indication

If you cannot complete this task, return failure with:

1. **Reason**: Why the task failed
2. **Files Examined**: List of files you checked
3. **Errors Encountered**: Specific error messages
4. **Manual Steps**: What a human would need to do
5. **Context**: Any relevant information for debugging

Example failure response:
````
Unable to parse pyproject.toml due to syntax error

Files examined: pyproject.toml, requirements.txt
Error: toml.decoder.TomlDecodeError at line 15
Manual steps: Fix toml syntax error in pyproject.toml line 15
````
```

### Retry Mechanism

```toml
[[actions]]
name = "fragile-transformation"
type = "claude"
prompt = "prompts/transform.md"
max_cycles = 5        # Try up to 5 times
on_failure = "cleanup" # Run cleanup action if all cycles fail
```

**Cycle behavior:**  

1. Execute transformation
2. Check for failure files
3. If failure detected and cycles remaining, retry
4. If all cycles exhausted, trigger `on_failure` action
5. Pass error context to retry attempts

### Error Context in Retries

On retry, the prompt receives additional context:

```python
# Appended to prompt automatically:
"""
---
You need to fix problems identified from a previous run.
The errors for context are:

{
  "result": "failure",
  "message": "Unable to update dependencies",
  "errors": ["Package X not found", "Version conflict with Y"]
}
"""
```

## Advanced Usage

### Conditional Prompts

**Workflow:**
```toml
[[actions]]
name = "language-specific-update"
type = "claude"
task_prompt = "prompts/{{ imbi_project.facts.get('Programming Language', 'unknown') | lower }}-update.md"
```

### Multi-Stage Transformations

```toml
[[actions]]
name = "stage1-refactor"
type = "claude"
task_prompt = "prompts/stage1.md"

[[actions]]
name = "stage2-optimize"
type = "claude"
task_prompt = "prompts/stage2.md"

[[actions]]
name = "stage3-document"
type = "claude"
task_prompt = "prompts/stage3.md"
```

### With Pre/Post Actions

```toml
[[actions]]
name = "backup-files"
type = "file"
command = "copy"
source = "repository:///src/"
destination = "repository:///src.backup/"

[[actions]]
name = "ai-refactor"
type = "claude"
task_prompt = "prompts/refactor.md"
on_failure = "restore-backup"

[[actions]]
name = "run-tests"
type = "shell"
command = "pytest tests/"
working_directory = "repository:///"

[[actions]]
name = "restore-backup"
type = "file"
command = "move"
source = "repository:///src.backup/"
destination = "repository:///src/"
```

## Integration with Other Actions

### Claude + Shell (Test Verification)

```toml
[[actions]]
name = "ai-code-update"
type = "claude"
task_prompt = "prompts/update.md"

[[actions]]
name = "verify-tests"
type = "shell"
command = "pytest tests/ -v"
working_directory = "repository:///"
```

### Claude + File (Template Application)

```toml
[[actions]]
name = "generate-base-config"
type = "template"
source_path = "config.yaml.j2"
destination_path = "repository:///config.yaml"

[[actions]]
name = "customize-config"
type = "claude"
task_prompt = "prompts/customize-config.md"
```

### Claude + Git (Commit Verification)

```toml
[[actions]]
name = "ai-transformation"
type = "claude"
task_prompt = "prompts/transform.md"

[[actions]]
name = "verify-commit"
type = "shell"
command = "git log -1 --pretty=%B"
working_directory = "repository:///"
```

## MCP Servers

Claude actions automatically have access to MCP (Model Context Protocol) servers configured at the workflow level. These servers provide Claude with tools to access external data sources and APIs during task execution.

### Configuration

MCP servers are configured in the workflow's `config.toml` file under the `[mcp_servers]` section. See [MCP Server Configuration](../workflow-configuration.md#mcp-server-configuration) for full documentation.

### Available Servers

During Claude action execution, the following MCP servers are available:

1. **`agent_tools`** (built-in): Provides workflow submission functions:
   - `mcp__agent_tools__submit_planning_response()` - For planning agents
   - `mcp__agent_tools__submit_task_response()` - For task agents
   - `mcp__agent_tools__submit_validation_response()` - For validation agents

2. **Workflow-configured servers**: Any MCP servers defined in `[mcp_servers.*]` sections

### Example: Database Access

```toml
# Workflow config.toml
[mcp_servers.postgres]
type = "stdio"
command = "uvx"
args = ["mcp-server-postgres", "${DATABASE_URL}"]

[[actions]]
name = "analyze-schema"
type = "claude"
task_prompt = "prompts/analyze-schema.md"
```

**Prompt (`prompts/analyze-schema.md`):**
```markdown
# Analyze Database Schema

Use the postgres MCP server to analyze the database schema.

1. List all tables in the database
2. Identify relationships between tables
3. Generate a summary of the schema structure

Use the `mcp__postgres__*` tools to query the database.
```

### Environment Variables in MCP Configs

MCP server configurations support shell-style environment variable expansion (`$VAR` or `${VAR}`) for secure credential injection. Variables are expanded at runtime when the Claude client is created.

```toml
[mcp_servers.secure-api]
type = "http"
url = "https://api.example.com/mcp"
headers = { Authorization = "Bearer ${API_TOKEN}" }
```

If a referenced environment variable is not set, a clear error is raised before execution begins.

## Performance Considerations

- **API Costs**: Each cycle makes Claude API calls
- **Execution Time**: Complex transformations can take several minutes
- **Context Size**: Large repositories may hit context limits
- **Rate Limiting**: Respect Anthropic API rate limits

## Security Considerations

- **Code Execution**: Claude can execute arbitrary code in the repository context
- **Sensitive Data**: Prompts and code are sent to Anthropic API
- **API Keys**: Ensure API keys are properly secured
- **Verification**: Always verify AI-generated changes before merging

## Implementation Notes

- **Module:** `src/imbi_automations/actions/claude.py` and `src/imbi_automations/claude.py`
- **Models:** `src/imbi_automations/models/claude.py` (agent types, response models)
- **Tests:** `tests/test_claude.py` and `tests/actions/test_claude.py` (376 passing tests)
- **Working Directory:** Task agent runs in `working_directory/repository/` subdirectory
- **Agent Locations:** `claude-code/agents/{planning,task,validation}.md.j2`
- **Prompt Templates:** `actions/prompts/{with-plan,planning-with-errors,last-error}.md.j2`
- **Tool Submission:** Agents use MCP agent_tools for structured responses
- **Automatic Cleanup:** Working directories cleaned on success or failure
- **Full Logging:** Claude API interactions logged at DEBUG level
- **Cycle Warning:** Warning logged at 60% of max_cycles (e.g., cycle 3 of 5)
- **Error Categorization:** Failures categorized as dependency_unavailable, constraint_conflict, prohibited_action, test_failure, or unknown

**Recent Critical Fixes (October 2025):**
1. **Planning Agent Error Handling** (commit 561909f): Fixed planning agent to create NEW PLAN instead of fixing errors directly when validation fails
2. **Claude SDK CWD Fix** (commit 561909f): Changed working directory from root to `repository/` subdirectory for correct file operations
3. **preserve_on_error Fix** (commit 561909f): Fixed unreachable preservation code, now properly saves error states
4. **Test Suite Update** (commit 561909f): Fixed 28 broken tests, all 376 tests now passing
