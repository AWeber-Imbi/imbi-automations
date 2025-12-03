# File Actions

File actions provide comprehensive file manipulation capabilities including copying, moving, deleting, appending, and writing files with support for glob patterns and multiple encoding options.

## Configuration

```toml
[[actions]]
name = "action-name"
type = "file"
command = "copy|move|rename|delete|append|write"
# Command-specific fields documented below
```

## Commands

### copy

Copy files or directories with glob pattern support.

**Required Fields:**  

- `source`: Source file/directory path or glob pattern
- `destination`: Destination path

**Examples:**  

```toml
# Copy single file
[[actions]]
name = "copy-readme"
type = "file"
command = "copy"
source = "workflow:///README.md"
destination = "repository:///README.md"

# Copy with glob pattern
[[actions]]
name = "copy-yaml-files"
type = "file"
command = "copy"
source = "workflow:///configs/*.yaml"
destination = "repository:///config/"

# Copy directory
[[actions]]
name = "copy-templates"
type = "file"
command = "copy"
source = "workflow:///templates/"
destination = "repository:///.github/templates/"

# Recursive glob pattern
[[actions]]
name = "copy-all-python"
type = "file"
command = "copy"
source = "workflow:///**/*.py"
destination = "repository:///scripts/"
```

**Glob Pattern Support:**  

- `*` - Matches any characters within a filename
- `?` - Matches single character
- `[...]` - Matches character ranges
- `**/` - Recursive directory matching

**Behavior:**  

- Creates destination parent directories automatically
- For glob patterns, destination must be a directory
- Preserves file metadata (timestamps, permissions)
- For directories, uses recursive copy

---

### move

Move (rename across directories) files or directories.

**Required Fields:**  

- `source`: Source file/directory path
- `destination`: Destination path

**Examples:**  

```toml
# Move file to different directory
[[actions]]
name = "relocate-config"
type = "file"
command = "move"
source = "repository:///old-location/config.yaml"
destination = "repository:///config/app.yaml"

# Reorganize directory structure
[[actions]]
name = "move-tests"
type = "file"
command = "move"
source = "repository:///old_tests/"
destination = "repository:///tests/"
```

**Behavior:**  

- Source file/directory is removed after move
- Creates destination parent directories automatically
- Fails if source doesn't exist

---

### rename

Rename files within the same directory or move to different location.

**Required Fields:**  

- `source`: Source file path
- `destination`: Destination file path

**Examples:**  

```toml
# Simple rename
[[actions]]
name = "rename-config"
type = "file"
command = "rename"
source = "repository:///config.yml"
destination = "repository:///config.yaml"

# Rename with path change
[[actions]]
name = "rename-and-move"
type = "file"
command = "rename"
source = "repository:///src/old_module.py"
destination = "repository:///src/new_module.py"
```

**Behavior:**  

- Similar to `move` but semantically for file renaming
- Creates destination parent directories automatically

---

### delete

Delete files or directories, with regex pattern matching support.

**Required Fields:** One of:  

- `path`: Specific file/directory path
- `pattern`: Regex pattern for matching files

**Examples:**  

```toml
# Delete specific file
[[actions]]
name = "remove-old-config"
type = "file"
command = "delete"
path = "repository:///old-config.yaml"

# Delete directory
[[actions]]
name = "remove-cache"
type = "file"
command = "delete"
path = "repository:///__pycache__/"

# Delete with regex pattern
[[actions]]
name = "remove-pyc-files"
type = "file"
command = "delete"
pattern = ".*\\.pyc$"

# Delete temporary files
[[actions]]
name = "cleanup-temps"
type = "file"
command = "delete"
pattern = ".*\\.(tmp|bak|swp)$"
```

**Behavior:**  

- For `path`: Deletes specific file or directory (recursive)
- For `pattern`: Searches recursively and deletes all matching files
- Does not error if path doesn't exist
- Pattern matching uses Python regex syntax (string in TOML, compiled at runtime)

---

### append

Append content to existing files or create new files.

**Required Fields:**  

- `path`: Target file path
- `content`: Content to append (string or bytes)

**Optional Fields:**  

- `encoding`: Character encoding (default: `utf-8`)

**Examples:**  

```toml
# Append text to existing file
[[actions]]
name = "add-to-gitignore"
type = "file"
command = "append"
path = "repository:///.gitignore"
content = """

# Added by automation
*.log
__pycache__/
.env
"""

# Create or append to file
[[actions]]
name = "add-config-section"
type = "file"
command = "append"
path = "repository:///config.ini"
content = """
[new_section]
option = value
"""

# Append with custom encoding
[[actions]]
name = "append-unicode"
type = "file"
command = "append"
path = "repository:///unicode.txt"
content = "Hello 世界\n"
encoding = "utf-16"
```

**Behavior:**  

- Creates file if it doesn't exist
- Creates parent directories automatically
- Appends to end of existing files
- Text mode only (bytes are decoded using specified encoding)

---

### write

Write content to files, overwriting if they exist.

**Required Fields:**  

- `path`: Target file path
- `content`: Content to write (string or bytes)

**Optional Fields:**  

- `encoding`: Character encoding (default: `utf-8`)

**Examples:**  

```toml
# Write text file
[[actions]]
name = "create-readme"
type = "file"
command = "write"
path = "repository:///README.md"
content = """
# My Project

Description here

## Installation

````bash
pip install my-project
````
"""

# Write JSON configuration
[[actions]]
name = "write-config"
type = "file"
command = "write"
path = "repository:///config.json"
content = """
{
  "name": "my-project",
  "version": "1.0.0",
  "type": "library"
}
"""

# Write with custom encoding
[[actions]]
name = "write-utf16"
type = "file"
command = "write"
path = "repository:///data.txt"
content = "Unicode content: 你好"
encoding = "utf-16"
```

**Behavior:**  

- Overwrites existing files
- Creates file if it doesn't exist
- Creates parent directories automatically
- Text mode (string) or binary mode (bytes) - detected automatically
- Does NOT support Jinja2 templating (use `template` action instead)

---

## Path Resolution

!!! info "Comprehensive Path Schemes Documentation"
    For detailed information about all path schemes, including usage patterns, best practices, and troubleshooting, see the [Path Schemes](../path-schemes.md) guide.

File actions support all ResourceUrl schemes:

| Scheme | Base Directory | Use Case |
|--------|---------------|----------|
| `file:///` or no scheme | Working directory | Temporary files |
| `repository:///` | Cloned repository | Repository files |
| `workflow:///` | Workflow resources | Template files |
| `extracted:///` | Docker extracts | Extracted files |
| `external:///` | Absolute path | Files outside working directory |

**Examples:**  

```toml
# Repository to repository
[[actions]]
type = "file"
command = "copy"
source = "repository:///README.md"
destination = "repository:///docs/README.md"

# Workflow to repository
[[actions]]
type = "file"
command = "copy"
source = "workflow:///templates/.gitignore"
destination = "repository:///.gitignore"

# Extracted to repository
[[actions]]
type = "file"
command = "copy"
source = "extracted:///configs/app.yaml"
destination = "repository:///config/app.yaml"

# Repository to external location (extract/export files)
[[actions]]
type = "file"
command = "copy"
source = "repository:///config.yaml"
destination = "external:///tmp/project-configs/{{ imbi_project.slug }}/config.yaml"
committable = false

# Simple paths (relative to working directory)
[[actions]]
type = "file"
command = "write"
path = "temp-file.txt"  # Same as file:///temp-file.txt
content = "temporary data"
```

**Note:** The `external:///` scheme allows writing files to absolute paths outside the temporary working directory. This is useful for:  

- Extracting configuration files for analysis
- Exporting reports or artifacts
- Creating backups in known locations
- Building collections of files from multiple repositories

When using `external:///`, set `committable = false` as these operations don't modify the repository.

## Common Patterns

### Backup and Replace Pattern

```toml
[[actions]]
name = "backup-original"
type = "file"
command = "copy"
source = "repository:///config.yaml"
destination = "repository:///config.yaml.bak"

[[actions]]
name = "write-new-config"
type = "file"
command = "write"
path = "repository:///config.yaml"
content = """
database:
  host: localhost
  port: 5432
"""
```

### Template Deployment Pattern

```toml
[[actions]]
name = "copy-gitignore"
type = "file"
command = "copy"
source = "workflow:///.gitignore"
destination = "repository:///.gitignore"

[[actions]]
name = "copy-pre-commit"
type = "file"
command = "copy"
source = "workflow:///.pre-commit-config.yaml"
destination = "repository:///.pre-commit-config.yaml"
```

### Cleanup Pattern

```toml
[[actions]]
name = "remove-legacy-configs"
type = "file"
command = "delete"
pattern = ".*\\.legacy\\.yaml$"

[[actions]]
name = "remove-cache-dirs"
type = "file"
command = "delete"
path = "repository:///__pycache__/"
```

### Glob Copy Pattern

```toml
[[actions]]
name = "copy-all-workflows"
type = "file"
command = "copy"
source = "workflow:///.github/workflows/*.yml"
destination = "repository:///.github/workflows/"

[[actions]]
name = "copy-python-modules"
type = "file"
command = "copy"
source = "workflow:///src/**/*.py"
destination = "repository:///src/"
```

## Error Handling

File actions raise `RuntimeError` in these situations:

- `copy`/`move`/`rename`: Source file doesn't exist
- `delete`: No errors (gracefully handles missing files)
- `append`/`write`: I/O errors, permission denied

## Implementation Notes

- All operations create parent directories automatically
- File metadata (permissions, timestamps) preserved in copy operations via `shutil.copy2`
- Glob patterns resolved relative to source base directory
- Empty glob results raise `RuntimeError`
- Binary content detected automatically (bytes vs string) in `write` command
- `append` command converts bytes to text using encoding (text mode only)
- Encoding applies only to text operations (default: `utf-8`)
- Pattern field accepts regex strings in TOML, compiled to `re.Pattern` at runtime
- Content does NOT support Jinja2 templating - use `template` action type for that
