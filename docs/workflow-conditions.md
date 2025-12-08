# Workflow Conditions

Conditions check repository state to determine if workflows or individual actions should execute. They provide fine-grained control over workflow execution based on file existence, file contents, and repository structure.

## Condition Levels

Conditions can be applied at two levels:

### Workflow-Level Conditions
Evaluated once per project before any actions execute. If conditions fail, the entire workflow is skipped.

```toml
[[conditions]]
remote_file_exists = "setup.cfg"
```

### Action-Level Conditions
Evaluated before each action executes. If conditions fail, only that specific action is skipped.

```toml
[[actions]]
name = "update-dockerfile"
type = "file"

[[actions.conditions]]
file_exists = "Dockerfile"
```

## Condition Types

### Remote Conditions (Pre-Clone)

Remote conditions are checked via API before cloning the repository. They are **faster** and more **efficient** than local conditions.

**Advantages:**

- ⚡ No repository cloning required
- 💾 Saves bandwidth and disk space
- 🚀 Faster workflow evaluation
- ✅ Early filtering (fail fast)

**Limitations:**

- Limited to single file content checks
- No glob pattern support for content matching
- API rate limits may apply

#### remote_file_exists

Check if a file exists using the GitHub API.

**Type:** `string` (file path or glob pattern)  


```toml
[[conditions]]
remote_file_exists = "setup.cfg"
```

**Glob pattern support:**
```toml
[[conditions]]
remote_file_exists = "**/*.tf"  # Any Terraform file recursively
```

**Real-world example:**
```toml
[[conditions]]
remote_file_exists = "setup.cfg"
```

**Why?** Workflow migrates projects from setup.cfg to pyproject.toml, so it only runs on projects that still have setup.cfg.

#### remote_file_not_exists

Check if a file does NOT exist using the GitHub API.

**Type:** `string` (file path or glob pattern)  


```toml
[[conditions]]
remote_file_not_exists = "pyproject.toml"
```

**Real-world example:**
```toml
[[conditions]]
remote_file_not_exists = "pyproject.toml"
```

**Why?** Combined with `remote_file_exists = "setup.cfg"`, this targets projects that haven't been migrated yet (have setup.cfg but no pyproject.toml).

#### remote_file_contains + remote_file

Check if a file contains specific text or matches a regex pattern.

**Type:** `string` (pattern to search for)  

**Requires:** `remote_file` field with target file path


```toml
[[conditions]]
remote_file_contains = "python.*3\\.9"
remote_file = "setup.cfg"
```

**Pattern matching:**

1. String search first (fast)
2. Falls back to regex if string not found
3. Use regex escaping: `\\.` for literal `.`, `\\d` for digits

**Example - exact string:**
```toml
[[conditions]]
remote_file_contains = "FROM python:3.9"
remote_file = "Dockerfile"
```

**Example - regex pattern:**
```toml
[[conditions]]
remote_file_contains = "python_requires.*=[\"']>=3\\.(9|10)"
remote_file = "setup.cfg"
```

#### remote_file_doesnt_contain + remote_file

Check if a file does NOT contain a pattern.

```toml
[[conditions]]
remote_file_doesnt_contain = "python.*3\\.12"
remote_file = "pyproject.toml"
```

#### remote_client

Specify which API client to use for remote checks.

**Type:** `string`

**Values:** `"github"` (default)


```toml
[[conditions]]
remote_client = "github"
remote_file_exists = ".github/workflows/ci.yml"
```

### Local Conditions (Post-Clone)

Local conditions are checked after cloning the repository. They have **full filesystem access** and support **glob patterns**.

**Advantages:**

- ✅ Full glob pattern support
- ✅ Access to all files, even .gitignored
- ✅ Complex pattern matching
- ✅ Directory checks

**Disadvantages:**

- 🐌 Requires git clone first
- 💾 Uses bandwidth and disk space
- ⏱️ Slower than remote conditions

#### file_exists

Check if a file or directory exists locally.

**Type:** [`ResourceUrl`](actions/index.md#resourceurl-path-system) (path relative to repository)

**Supports:** Glob patterns


```toml
[[conditions]]
file_exists = "Dockerfile"
```

**Glob patterns:**
```toml
[[conditions]]
file_exists = "**/*.py"  # Any Python file recursively

[[conditions]]
file_exists = "src/**/__init__.py"  # __init__.py in any src subdirectory
```

**Real-world example from example-workflow (action-level):**
```toml
[[actions]]
name = "extract-constraints"
type = "docker"
command = "extract"
image = "{{ extract_image_from_dockerfile('repository/Dockerfile') }}"
source = "/tmp/constraints.txt"
destination = "extracted:///constraints.txt"

[[actions.conditions]]
file_exists = "Dockerfile"
```

**Why?** Only extract Docker constraints if project has a Dockerfile.

#### file_not_exists

Check if a file or directory does NOT exist locally.

```toml
[[conditions]]
file_not_exists = ".travis.yml"  # No legacy CI
```

**Real-world example from example-workflow (action-level):**
```toml
[[actions]]
name = "extract-original-compose-yml"
type = "git"
command = "extract"
commit_keyword = "migration"
source = "compose.yml"
destination = "extracted:///compose.original.yaml"

[[actions.conditions]]
file_not_exists = "extracted:///compose.original.yaml"
```

**Why?** Only attempt to extract compose.yml from git history if we haven't already extracted it from a previous attempt (compose.yaml).

#### file_contains + file

Check if a file contains specific text or matches a regex pattern.

**Type:** `string` (pattern to search for)  

**Requires:** `file` field with target file path


```toml
[[conditions]]
file_contains = "FROM python:3\\.9"
file = "Dockerfile"
```

**Pattern matching:**

1. String search first (fast)
2. Falls back to regex if string not found
3. Use regex escaping: `\\.` for literal `.`, `\\d` for digits

**Example - Check Python version:**
```toml
[[conditions]]
file_contains = "python.*3\\.(9|10|11)"
file = "pyproject.toml"
```

**Example - Check dependencies:**
```toml
[[conditions]]
file_contains = "fastapi.*==.*0\\."
file = "requirements.txt"
```

#### file_doesnt_contain + file

Check if a file does NOT contain a pattern.

```toml
[[conditions]]
file_doesnt_contain = "python.*2\\."
file = "setup.py"
```

### Template Conditions (Post-Clone)

Template conditions use Jinja2 expressions for complex logic. They have access to template functions like `compare_semver()` and `get_component_version()`.

**Advantages:**

- ✅ Complex conditional logic
- ✅ Version comparison support
- ✅ Access to workflow context
- ✅ Dependency version extraction

**Disadvantages:**

- 🐌 Requires git clone first
- ⏱️ Template evaluation overhead

#### when

Evaluate a Jinja2 template expression. If the result is truthy, the condition passes.

**Type:** `string` (Jinja2 template)  

**Truthiness evaluation:**

- **Truthy:** `True`, `true`, `1`, `yes`, any non-empty string
- **Falsy:** `False`, `false`, `0`, `no`, `none`, empty string

```toml
[[conditions]]
when = "{{ compare_semver(get_component_version('repository:///package.json', 'react'), '19.0.0').is_older }}"
```

**Template functions available:**

- `compare_semver(current, target)` - Compare two semantic versions
- `get_component_version(path, component)` - Extract dependency version from package.json or pyproject.toml

##### compare_semver(current, target)

Compares two semantic versions and returns a dict with comparison results.

**Arguments:**

- `current`: Current version string (e.g., "18.2.0", "3.9.18-4")
- `target`: Target version string to compare against

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

```toml
# Check if React is older than 19.0.0
[[conditions]]
when = "{{ compare_semver('18.2.0', '19.0.0').is_older }}"

# Check major version
[[conditions]]
when = "{{ compare_semver(get_component_version('repository:///package.json', 'react'), '18.0.0').current_major >= 17 }}"
```

##### get_component_version(path, component)

Extracts a dependency version from a manifest file.

**Arguments:**

- `path`: ResourceUrl path to manifest file (e.g., "repository:///package.json")
- `component`: Name of the dependency to extract

**Supported file types:**

- `package.json`: Searches dependencies, devDependencies, peerDependencies
- `pyproject.toml`: Searches project.dependencies, optional-dependencies, Poetry dependencies

**Returns:** Clean version string without prefixes

```toml
# Check React version in package.json
[[conditions]]
when = "{{ compare_semver(get_component_version('repository:///package.json', 'react'), '19.0.0').is_older }}"

# Check Pydantic version in pyproject.toml
[[conditions]]
when = "{{ compare_semver(get_component_version('repository:///pyproject.toml', 'pydantic'), '2.0.0').is_older }}"
```

##### Combined examples

```toml
# Skip upgrade workflow if already on target version
[[conditions]]
when = "{{ compare_semver(get_component_version('repository:///package.json', 'react'), '19.0.0').is_older }}"

# Complex negation
[[conditions]]
when = "{{ not compare_semver(get_component_version('repository:///pyproject.toml', 'pydantic'), '2.0.0').is_newer }}"

# String checks on version
[[conditions]]
when = "{{ get_component_version('repository:///pyproject.toml', 'python').startswith('3.9') }}"

# Access workflow context
[[conditions]]
when = "{{ workflow.configuration.name == 'upgrade-react' }}"
```

**Note:** Template conditions are skipped during remote checks (pre-clone) since they require filesystem access. Use remote conditions for pre-clone filtering.  

## Condition Evaluation

### condition_type

Controls how multiple conditions are evaluated.

**Type:** `string`  

**Values:** `"all"` (AND logic), `"any"` (OR logic)

**Default:** `"all"`  


#### AND Logic (condition_type = "all")

ALL conditions must pass for execution to proceed.

```toml
condition_type = "all"  # All conditions must pass (default)

[[conditions]]
remote_file_exists = "setup.cfg"

[[conditions]]
remote_file_not_exists = "pyproject.toml"
```

**Real-world example:**
```toml
# Workflow level - targets un-migrated projects
[[conditions]]
remote_file_exists = "setup.cfg"

[[conditions]]
remote_file_not_exists = "pyproject.toml"
```

**Result:** Only processes projects that have setup.cfg AND don't have pyproject.toml (haven't been migrated yet).

#### OR Logic (condition_type = "any")

ANY ONE condition passing is sufficient for execution.

```toml
condition_type = "any"  # Any condition passing is sufficient

[[conditions]]
remote_file_exists = "requirements.txt"

[[conditions]]
remote_file_exists = "pyproject.toml"

[[conditions]]
remote_file_exists = "setup.py"
```

**Result:** Executes if project has ANY Python configuration file.

## Real-World Examples

### Example 1: Workflow-Level Conditions (example-workflow)

```toml
# Only target Python projects that still use setup.cfg
[[conditions]]
remote_file_exists = "setup.cfg"

[[conditions]]
remote_file_not_exists = "pyproject.toml"
```

**What it does:**

1. ✅ Project must have `setup.cfg` (old configuration)
2. ✅ Project must NOT have `pyproject.toml` (not yet migrated)

**Why remote conditions?** These checks happen before cloning, so we avoid cloning projects that don't need migration. For 1000 projects, this might only clone 50 that need fixing.

### Example 2: Action-Level Conditions (Conditional Docker Extraction)

```toml
[[actions]]
name = "extract-constraints"
type = "docker"
command = "extract"
image = "{{ extract_image_from_dockerfile('repository/Dockerfile') }}"
source = "/tmp/constraints.txt"
destination = "extracted:///constraints.txt"

[[actions.conditions]]
file_exists = "Dockerfile"
```

**What it does:**

- Only extracts Docker constraints if project has a Dockerfile
- If no Dockerfile, action is skipped (not a failure)

**Why action-level?** Not all Python projects use Docker, so this action should only run when applicable.

### Example 3: Multiple Action Conditions (Compose File Variations)

```toml
[[actions]]
name = "extract-original-docker-compose-yml"
type = "git"
command = "extract"
commit_keyword = "migration"
source = "docker-compose.yml"
destination = "extracted:///compose.original.yaml"
ignore_errors = true

[[actions.conditions]]
file_not_exists = "extracted:///compose.original.yaml"

[[actions.conditions]]
file_exists = "repository:///compose.yaml"
```

**What it does:**

1. ✅ Only extract if we haven't already extracted a compose file
2. ✅ Only extract if project currently has compose.yaml

**Why both conditions?** Projects might have compose.yaml, compose.yml, docker-compose.yaml, or docker-compose.yml. The workflow tries each variant in sequence, but stops once one succeeds.

### Example 4: Conditional Dockerfile Update

```toml
[[actions]]
name = "generate-dockerfile"
type = "claude"
prompt = "prompts/dockerfile.md.j2"
validation_prompt = "prompts/validate-dockerfile.md.j2"

[[actions.conditions]]
file_exists = "repository:///Dockerfile"
```

**What it does:**

- Only runs Claude to update Dockerfile if project has one
- Projects without Docker are skipped gracefully

**Why ResourceUrl?** The `repository:///` prefix ensures we're checking the cloned repository, not extracted files.

### Example 5: Multiple Condition Fallbacks

This pattern from example-workflow tries multiple compose file names:

```toml
# Try compose.yaml first
[[actions]]
name = "extract-original-compose-yaml"
type = "git"
command = "extract"
source = "compose.yaml"
destination = "extracted:///compose.original.yaml"

# Try compose.yml if compose.yaml wasn't found
[[actions]]
name = "extract-original-compose-yml"
type = "git"
command = "extract"
source = "compose.yml"
destination = "extracted:///compose.original.yaml"

[[actions.conditions]]
file_not_exists = "extracted:///compose.original.yaml"  # Only if previous failed

# Try docker-compose.yaml
[[actions]]
name = "extract-original-docker-compose-yaml"
type = "git"
command = "extract"
source = "docker-compose.yaml"
destination = "extracted:///compose.original.yaml"

[[actions.conditions]]
file_not_exists = "extracted:///compose.original.yaml"

# Try docker-compose.yml
[[actions]]
name = "extract-original-docker-compose-yml"
type = "git"
command = "extract"
source = "docker-compose.yml"
destination = "extracted:///compose.original.yaml"

[[actions.conditions]]
file_not_exists = "extracted:///compose.original.yaml"
```

**What it does:**

1. Try `compose.yaml` (modern name)
2. If that fails, try `compose.yml`
3. If that fails, try `docker-compose.yaml`
4. If that fails, try `docker-compose.yml`
5. Stop at first success

**Why this pattern?** Docker Compose supports multiple filenames, and different projects use different conventions. This ensures we find the file regardless of naming.

## Best Practices

### 1. Use Remote Conditions First

```toml
# ✅ Good - check remotely before cloning
[[conditions]]
remote_file_exists = "package.json"

[[conditions]]
remote_file_contains = "node.*18"
remote_file = ".nvmrc"

# ❌ Slower - clones every repository
[[conditions]]
file_exists = "package.json"

[[conditions]]
file_contains = "node.*18"
file = ".nvmrc"
```

**Performance impact:** For 1000 projects, remote conditions might process 50, while local conditions require cloning all 1000 first.

### 2. Combine AND Logic for Precision

```toml
condition_type = "all"  # All must pass (default)

[[conditions]]
remote_file_exists = "Dockerfile"

[[conditions]]
remote_file_contains = "FROM python:3\\.9"
remote_file = "Dockerfile"

[[conditions]]
remote_file_not_exists = "pyproject.toml"
```

**Result:** Only Python 3.9 Docker projects without pyproject.toml.

### 3. Use OR Logic for Flexibility

```toml
condition_type = "any"  # Any one passing is sufficient

[[conditions]]
remote_file_exists = "setup.py"

[[conditions]]
remote_file_exists = "setup.cfg"

[[conditions]]
remote_file_exists = "pyproject.toml"
```

**Result:** Any Python project with configuration.

### 4. Action Conditions for Optional Steps

```toml
[[actions]]
name = "update-dockerfile"
type = "file"

[[actions.conditions]]
file_exists = "Dockerfile"  # Skip if no Docker

[[actions]]
name = "run-tests"
type = "shell"
command = "pytest tests/"

[[actions.conditions]]
file_exists = "tests/"  # Skip if no tests
```

**Why?** Not all projects need all actions. Conditions allow graceful degradation.

### 5. Avoid Over-Filtering

```toml
# ❌ Too restrictive - might miss valid projects
[[conditions]]
remote_file_contains = "python_requires.*=.*['\"]3\\.9['\"]"
remote_file = "setup.cfg"

# ✅ Better - allows variations
[[conditions]]
remote_file_contains = "python.*3\\.9"
remote_file = "setup.cfg"
```

**Why?** The second pattern matches more variations in how version might be specified.

## Condition vs Filter

| Feature | Filters | Remote Conditions | Local Conditions |
|---------|---------|------------------|------------------|
| **When evaluated** | Before processing | Before cloning | After cloning |
| **Data source** | Imbi metadata | GitHub API | Local filesystem |
| **Speed** | ⚡⚡⚡ Fastest | ⚡⚡ Fast | ⚡ Slower |
| **Use for** | Project metadata | File existence/content | Complex patterns |
| **Glob support** | No | Limited | Full |
| **Bandwidth** | None | Minimal | High |

**Best practice:** Use all three in combination:

1. **Filters** for broad technology targeting
2. **Remote conditions** for file-based applicability
3. **Local conditions** for complex repository checks

## Complete Example

This is the actual condition strategy from example-workflow:

```toml
# Filter: Broad targeting
[filter]
project_types = ["apis", "consumers", ...]
project_facts = {"programming_language" = "Python 3.9"}
github_identifier_required = true
github_workflow_status_exclude = ["success"]

# Workflow conditions: Migration applicability
[[conditions]]
remote_file_exists = "setup.cfg"

[[conditions]]
remote_file_not_exists = "pyproject.toml"

# Action conditions: Optional steps
[[actions]]
name = "extract-constraints"
type = "docker"

[[actions.conditions]]
file_exists = "Dockerfile"  # Only if Docker is used

[[actions]]
name = "ensure-correct-pins"
type = "claude"

[[actions.conditions]]
file_exists = "Dockerfile"  # Only if Docker is used

[[actions]]
name = "generate-dockerfile"
type = "claude"

[[actions.conditions]]
file_exists = "repository:///Dockerfile"  # Only if Dockerfile exists
```

**Result:**

1. Filter reduces 1000 projects → 50 Python 3.9 projects with failing builds
2. Remote conditions reduce 50 projects → 30 projects needing migration (have setup.cfg, no pyproject.toml)
3. Action conditions skip Docker-related actions for non-Docker projects

## See Also

- [Workflow Filters](workflow-filters.md) - Pre-filtering projects by metadata
- [Workflow Configuration](workflow-configuration.md) - Complete configuration reference
- [Workflows Overview](workflows.md) - High-level concepts and best practices
