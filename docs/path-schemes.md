# Path Schemes

Path schemes (ResourceUrls) provide a consistent way to reference files and directories across different contexts in workflow actions. They use a URI-like syntax to specify the base location for file operations.

## Overview

Many workflow actions accept `source`, `destination`, or `path` parameters. These parameters use **path schemes** to indicate where files are located relative to the workflow execution environment.

**Format**: `scheme:///path/to/file`

**Example**: `repository:///config.yaml`

## Available Schemes

### `repository:///`

**Base Directory**: Cloned git repository

**Use Case**: Files within the project repository being processed

**Examples**:
```toml
# Read from repository
source = "repository:///src/config.yaml"

# Write to repository
destination = "repository:///.github/workflows/ci.yml"

# Delete from repository
path = "repository:///legacy-config.json"
```

**Common Patterns**:
- Reading existing project files
- Modifying repository contents
- Creating new files in the repository
- Any operation that should be committed and pushed

---

### `workflow:///`

**Base Directory**: Workflow directory (where `config.toml` lives)

**Use Case**: Template files, configuration files, and resources bundled with the workflow

**Examples**:
```toml
# Copy template from workflow to repository
[[actions]]
type = "file"
command = "copy"
source = "workflow:///templates/.gitignore"
destination = "repository:///.gitignore"

# Render template from workflow
[[actions]]
type = "template"
source_path = "workflow:///config.yaml.j2"
destination_path = "repository:///config.yaml"
```

**Typical Structure**:
```
workflows/my-workflow/
├── config.toml
├── templates/
│   ├── .gitignore
│   ├── ci.yml
│   └── config.yaml.j2
└── scripts/
    └── setup.sh
```

---

### `extracted:///`

**Base Directory**: Extracted files directory (typically from Docker operations)

**Use Case**: Files extracted from Docker containers

**Examples**:
```toml
# Extract from Docker image
[[actions]]
type = "docker"
command = "extract"
image = "myapp"
source = "/app/dist/"
destination = "extracted:///dist/"

# Copy extracted files to repository
[[actions]]
type = "file"
command = "copy"
source = "extracted:///dist/bundle.js"
destination = "repository:///public/bundle.js"
```

**Workflow**:
1. Docker action extracts files to `extracted:///`
2. Subsequent actions can reference those files
3. Files can be copied to repository or used for processing

---

### `external:///`

**Base Directory**: Absolute filesystem path (outside working directory)

**Use Case**: Exporting files, creating collections, writing to known locations

**Examples**:
```toml
# Extract configuration for analysis
[[actions]]
name = "export-config"
type = "file"
command = "copy"
source = "repository:///config.yaml"
destination = "external:///tmp/project-configs/{{ imbi_project.slug }}/config.yaml"
committable = false

# Build a collection across projects
[[actions]]
name = "collect-dockerfiles"
type = "file"
command = "copy"
source = "repository:///Dockerfile"
destination = "external:///var/exports/dockerfiles/{{ imbi_project.slug }}/Dockerfile"
committable = false
```

**Important Notes**:
- Always set `committable = false` for external operations
- Paths are absolute (e.g., `/tmp/`, `/var/`, `/Users/...`)
- Useful for extract-only workflows that don't modify repositories
- Workflow engine skips push/PR creation when only external operations occur

---

### `file:///` (or no scheme)

**Base Directory**: Working directory root (temporary directory)

**Use Case**: Temporary files, intermediate processing

**Examples**:
```toml
# Write temporary file (both forms equivalent)
path = "file:///temp-data.json"
path = "temp-data.json"

# Process temporary files
source = "intermediate-results.csv"
```

**Notes**:
- Rarely used directly in workflows
- Defaults to working directory
- Files created here are automatically cleaned up after workflow execution

---

## Usage by Action Type

### File Actions

All file commands (`copy`, `move`, `delete`, `append`, `write`) support all schemes:

```toml
[[actions]]
type = "file"
command = "copy"
source = "workflow:///template.txt"      # Any scheme
destination = "repository:///output.txt"  # Any scheme
```

### Template Actions

```toml
[[actions]]
type = "template"
source_path = "workflow:///config.j2"      # Typically workflow:///
destination_path = "repository:///config"   # Typically repository:///
```

### Docker Actions

```toml
[[actions]]
type = "docker"
command = "extract"
source = "/container/path"                  # Container path (no scheme)
destination = "extracted:///local/path"     # extracted:/// for local storage
```

### Git Actions

```toml
[[actions]]
type = "git"
command = "extract"
url = "https://github.com/org/repo.git"
destination = "extracted:///repo-files"     # extracted:/// for git extracts
```

### Shell Actions

```toml
[[actions]]
type = "shell"
command = "ls -la"
working_directory = "repository:///"         # Execute in repository
```

---

## Template Variables

All path schemes support Jinja2 template variables:

```toml
# Project-specific paths
destination = "external:///exports/{{ imbi_project.slug }}/config.yaml"

# Conditional paths
source = "workflow:///{{ imbi_project.project_type }}/template.j2"

# Dynamic naming
path = "repository:///output-{{ github_repository.default_branch }}.txt"
```

**URL Encoding**: Template variables in schemes are automatically URL-decoded before rendering:
- `%7B%7B` → `{{`
- `%20` → space
- Configuration values are stored URL-encoded, decoded at runtime

---

## Path Resolution

### Absolute vs Relative

| Scheme | Resolution | Example |
|--------|-----------|---------|
| `repository:///` | Relative to repo | `repository:///src/main.py` → `{temp}/repository/src/main.py` |
| `workflow:///` | Relative to workflow | `workflow:///files/config` → `{workflow-dir}/files/config` |
| `extracted:///` | Relative to extracted | `extracted:///dist/app.js` → `{temp}/extracted/dist/app.js` |
| `external:///` | Absolute path | `external:///tmp/data.json` → `/tmp/data.json` |
| `file:///` | Relative to working | `file:///temp.txt` → `{temp}/temp.txt` |

### Directory Structure

During execution, the working directory structure looks like:

```
{temporary-directory}/
├── repository/        # Cloned git repository (repository:///)
├── workflow/          # Symlink to workflow directory (workflow:///)
├── extracted/         # Docker/git extracts (extracted:///)
└── temp-files         # Temporary files (file:///)
```

---

## Best Practices

### 1. Use Appropriate Schemes

```toml
# ✓ Good - Clear intent
source = "workflow:///templates/.gitignore"
destination = "repository:///.gitignore"

# ✗ Avoid - Confusing relative paths
source = "../workflow/templates/.gitignore"
```

### 2. Set committable = false for External Operations

```toml
# ✓ Good - Extract without committing
[[actions]]
type = "file"
command = "copy"
source = "repository:///config.yaml"
destination = "external:///tmp/configs/{{ imbi_project.slug }}/config.yaml"
committable = false

# ✗ Bad - Will fail trying to commit external changes
[[actions]]
type = "file"
command = "copy"
source = "repository:///config.yaml"
destination = "external:///tmp/configs/config.yaml"
# Missing: committable = false
```

### 3. Organize Workflow Files

```toml
# ✓ Good - Organized structure
source = "workflow:///templates/backend/.gitignore"
source = "workflow:///templates/frontend/.gitignore"
source = "workflow:///scripts/setup.sh"

# ✗ Avoid - Flat structure
source = "workflow:///backend-gitignore"
source = "workflow:///frontend-gitignore"
```

### 4. Use Glob Patterns with Repository Scheme

```toml
# ✓ Good - Copy multiple files
[[actions]]
type = "file"
command = "copy"
source = "workflow:///configs/*.yaml"
destination = "repository:///config/"

# ✓ Good - Recursive patterns
source = "repository:///src/**/*.py"
destination = "extracted:///python-files/"
```

---

## Common Patterns

### Pattern 1: Template Deployment

```toml
[[actions]]
name = "deploy-ci-template"
type = "file"
command = "copy"
source = "workflow:///ci-templates/python.yml"
destination = "repository:///.github/workflows/ci.yml"
```

### Pattern 2: Docker Extract and Copy

```toml
[[actions]]
name = "extract-build-artifacts"
type = "docker"
command = "extract"
image = "myapp:latest"
source = "/app/dist/"
destination = "extracted:///dist/"

[[actions]]
name = "copy-to-repo"
type = "file"
command = "copy"
source = "extracted:///dist/"
destination = "repository:///public/"
```

### Pattern 3: Export for Analysis

```toml
[[actions]]
name = "export-dependencies"
type = "file"
command = "copy"
source = "repository:///requirements.txt"
destination = "external:///tmp/dependency-analysis/{{ imbi_project.slug }}/requirements.txt"
committable = false
```

### Pattern 4: Template Rendering

```toml
[[actions]]
name = "render-config"
type = "template"
source_path = "workflow:///templates/config.yaml.j2"
destination_path = "repository:///config/app.yaml"
```

---

## Troubleshooting

### Issue: "Invalid path scheme"

**Error**: `RuntimeError: Invalid path scheme: xyz`

**Solution**: Use one of the supported schemes: `repository`, `workflow`, `extracted`, `external`, `file`

```toml
# ✗ Wrong
source = "myscheme:///file.txt"

# ✓ Correct
source = "repository:///file.txt"
```

### Issue: Template variables not rendering

**Error**: Path contains literal `{{ imbi_project.slug }}` instead of actual slug

**Solution**: Ensure the path is stored as a string in TOML, not pre-processed

```toml
# ✓ Correct - Will be rendered at runtime
destination = "external:///tmp/{{ imbi_project.slug }}/config.yaml"

# ✗ Wrong - Already URL-encoded won't render
# (This shouldn't happen with proper configuration)
```

### Issue: "No changes to commit" with external operations

**Symptom**: Workflow tries to create commits but no repository changes were made

**Solution**: Add `committable = false` to actions using `external:///`

```toml
# ✓ Correct
[[actions]]
type = "file"
command = "copy"
source = "repository:///config.yaml"
destination = "external:///tmp/config.yaml"
committable = false  # Don't try to commit
```

---

## See Also

- [File Actions](actions/file.md) - File manipulation with path schemes
- [Template Actions](actions/template.md) - Template rendering with schemes
- [Docker Actions](actions/docker.md) - Docker operations and extracted files
- [Templating](templating.md) - Using Jinja2 variables in paths
