# Utility Actions

Utility actions provide helper operations for Docker tag parsing, Dockerfile analysis, semantic versioning comparison, and Python constraint parsing.

## Configuration

```toml
[[actions]]
name = "action-name"
type = "utility"
command = "docker_tag|dockerfile_from|compare_semver|parse_python_constraints"
path = "repository:///path/to/file"  # Optional
args = []      # Optional
kwargs = {}    # Optional
```

## Fields

### command (required)

The utility operation to perform.

**Type:** `string`

**Options:**

- `compare_semver` - Compare semantic version strings ✅ **Implemented**
- `docker_tag` - Parse Docker image tags (not implemented)
- `dockerfile_from` - Extract FROM directive from Dockerfile (not implemented)
- `parse_python_constraints` - Parse Python version constraints (not implemented)

### path (optional)

File path for operations that require file input.

**Type:** [`ResourceUrl`](index.md#resourceurl-path-system) (string path)

**Default:** None


### args (optional)

Positional arguments for the utility operation.

**Type:** `list`

**Default:** `[]`


### kwargs (optional)

Keyword arguments for the utility operation.

**Type:** `dict`

**Default:** `{}`


## Commands

### compare_semver

**Status:** ✅ Implemented

Compare two semantic version strings and store the result in workflow variables for access by subsequent actions.

**Arguments:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `current_version` | string | Yes | The current/source version to compare |
| `target_version` | string | Yes | The target version to compare against |
| `output` | string | No | Variable name to store result (default: `semver_result`) |

Arguments can be passed as positional args or keyword args:

```toml
# Using positional args
args = ["1.2.3", "2.0.0"]

# Using keyword args
kwargs = { current_version = "1.2.3", target_version = "2.0.0", output = "version_check" }
```

**Supported Version Formats:**

- Standard semver: `1.2.3`, `2.0.0`, `10.20.30`
- With build numbers: `3.9.18-0`, `3.9.18-4`
- Jinja2 templates: `"{{ imbi_project.facts.get('Python Version') }}"`

**Result Object (SemverComparisonResult):**

The result is stored in `context.variables[output_name]` as a dictionary:

| Field | Type | Description |
|-------|------|-------------|
| `current_version` | string | Original current version input |
| `target_version` | string | Original target version input |
| `comparison` | int | -1 (older), 0 (equal), or 1 (newer) |
| `is_older` | bool | True if current < target |
| `is_equal` | bool | True if current == target |
| `is_newer` | bool | True if current > target |
| `current_major` | int | Parsed major version of current |
| `current_minor` | int | Parsed minor version of current |
| `current_patch` | int | Parsed patch version of current |
| `current_build` | int \| None | Build number if present (e.g., 4 from "3.9.18-4") |
| `target_major` | int | Parsed major version of target |
| `target_minor` | int | Parsed minor version of target |
| `target_patch` | int | Parsed patch version of target |
| `target_build` | int \| None | Build number if present |

**Example - Basic Usage:**

```toml
[[actions]]
name = "check-python-version"
type = "utility"
command = "compare_semver"
args = ["3.9.18", "3.12.0"]
kwargs = { output = "python_version_check" }
```

**Example - With Jinja2 Templates:**

```toml
[[actions]]
name = "compare-project-version"
type = "utility"
command = "compare_semver"
kwargs = {
    current_version = "{{ imbi_project.facts.get('Python Version', '3.9.0') }}",
    target_version = "3.12.0",
    output = "version_check"
}
```

**Example - Accessing Results in Subsequent Actions:**

```toml
# First, compare versions
[[actions]]
name = "check-version"
type = "utility"
command = "compare_semver"
args = ["3.9.18-0", "3.12.0"]
kwargs = { output = "version_check" }

# Then use the result in a Claude prompt
[[actions]]
name = "upgrade-if-needed"
type = "claude"
task_prompt = "prompts/upgrade.md.j2"
```

**Prompt template (`prompts/upgrade.md.j2`):**

```jinja2
# Python Version Upgrade

{% if variables.version_check.is_older %}
The project is using Python {{ variables.version_check.current_version }}
which is older than the target {{ variables.version_check.target_version }}.

Please upgrade:
1. Update pyproject.toml requires-python
2. Update Dockerfile base image
3. Update CI/CD workflows
{% elif variables.version_check.is_newer %}
The project is already on a newer version - no action needed.
{% else %}
Versions are equal - no upgrade required.
{% endif %}
```

**Example - Conditional Action Execution (React Upgrade):**

Check if the React version in package.json is older than 19.2.0, and if so, run an upgrade action:

```toml
# Extract current React version from package.json
[[actions]]
name = "get-react-version"
type = "shell"
command = "node -p \"require('./package.json').dependencies.react.replace(/[^0-9.]/g, '')\""
working_directory = "repository:///"

# Compare versions (use the extracted version from a project fact or hardcode for demo)
[[actions]]
name = "check-react-version"
type = "utility"
command = "compare_semver"
kwargs = {
    current_version = "18.2.0",  # Or use {{ imbi_project.facts.get('React Version') }}
    target_version = "19.2.0",
    output = "react_check"
}

# Only run upgrade if React version is older than 19.2.0
[[actions]]
name = "upgrade-react"
type = "claude"
task_prompt = "prompts/upgrade-react.md.j2"

[[actions.conditions]]
file_contains = "True"
file = "{{ variables.react_check.is_older }}"
```

**Prompt template (`prompts/upgrade-react.md.j2`):**

```jinja2
# Upgrade React to 19.2.0

The project is using React {{ variables.react_check.current_version }} which is
older than the target version {{ variables.react_check.target_version }}.

Please upgrade:
1. Update `react` and `react-dom` in package.json to ^19.2.0
2. Review and update any deprecated API usage
3. Run `npm install` to update package-lock.json
4. Fix any TypeScript errors related to the upgrade
```

**Example - Build Number Comparison:**

```toml
[[actions]]
name = "check-build"
type = "utility"
command = "compare_semver"
args = ["3.9.18-0", "3.9.18-4"]
kwargs = { output = "build_check" }
```

Result:
```python
{
    "current_version": "3.9.18-0",
    "target_version": "3.9.18-4",
    "comparison": -1,
    "is_older": True,  # Build 0 < Build 4
    "is_equal": False,
    "is_newer": False,
    "current_major": 3,
    "current_minor": 9,
    "current_patch": 18,
    "current_build": 0,
    "target_major": 3,
    "target_minor": 9,
    "target_patch": 18,
    "target_build": 4
}
```

**Error Handling:**

- Invalid semver format raises `ValueError` with descriptive message
- Missing required arguments raises `ValueError`
- Non-numeric build identifiers (e.g., "alpha", "beta") are treated as `None`

### docker_tag

**Status:** ❌ Not implemented (raises NotImplementedError)

Parse and manipulate Docker image tags.

**Intended Usage:**
```toml
[[actions]]
name = "parse-docker-tag"
type = "utility"
command = "docker_tag"
args = ["python:3.12-slim"]
```

### dockerfile_from

**Status:** ❌ Not implemented (raises NotImplementedError)

Extract the base image FROM directive from a Dockerfile.

**Intended Usage:**
```toml
[[actions]]
name = "get-base-image"
type = "utility"
command = "dockerfile_from"
path = "repository:///Dockerfile"
```

### parse_python_constraints

**Status:** ❌ Not implemented (raises NotImplementedError)

Parse Python version constraint strings (e.g., `>=3.8,<4.0`).

**Intended Usage:**
```toml
[[actions]]
name = "parse-constraints"
type = "utility"
command = "parse_python_constraints"
args = [">=3.8,<4.0"]
```

## Workflow Variables

Utility actions that produce output (like `compare_semver`) store results in `context.variables`, which is accessible in:

- Subsequent action Jinja2 templates via `{{ variables.variable_name }}`
- Claude Code prompts via `{{ variables.variable_name }}`
- Template action files via `{{ variables.variable_name }}`

This enables data flow between actions without writing to files.

## Workarounds for Unimplemented Commands

Until the remaining utility commands are implemented, use alternative approaches:

1. **Docker tag parsing**: Use shell action with `docker inspect` or regex
2. **Dockerfile FROM**: Use the built-in template function `extract_image_from_dockerfile()` or shell action with `grep`
3. **Python constraints**: Use shell action with Python's `packaging` library

## Implementation Notes

- **Module:** `src/imbi_automations/actions/utility.py`
- **Model:** `src/imbi_automations/models/workflow.py` (WorkflowUtilityAction)
- **Result Model:** `src/imbi_automations/models/utility.py` (SemverComparisonResult)
- **Tests:** `tests/actions/test_utility.py`
- Results stored in `context.variables` are serialized as dictionaries
