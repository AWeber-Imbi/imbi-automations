# Git Actions

Git actions provide version control operations for extracting files from Git history and cloning repositories.

## Configuration

```toml
[[actions]]
name = "action-name"
type = "git"
command = "extract"  # or "clone"
# Command-specific fields below
```

## Commands

### extract

Extract a specific file from Git commit history. Useful for retrieving old versions of files from before certain changes were made.

**Required Fields:**  


- `source` ([pathlib.Path][]): Path to the file in the repository
- `destination` ([`ResourceUrl`](index.md#resourceurl-path-system)): Where to write the extracted file

**Optional Fields:**  


- `commit_keyword` (string): Keyword to search for in commit messages. If not provided, extracts from current HEAD (default: None)
- `search_strategy` (string): How to find the commit - `before_first_match` or `before_last_match`. Only used when `commit_keyword` is provided (default: `before_last_match`)
- `ignore_errors` (bool): Continue if extraction fails instead of raising RuntimeError (default: false)

**Example:**
```toml
[[actions]]
name = "extract-old-config"
type = "git"
command = "extract"
source = "config.yaml"
destination = "extracted:///old-config.yaml"
commit_keyword = "update config"
search_strategy = "before_last_match"
```

**Search Strategies:**  

- `before_first_match`: Extract file from commit before the first match of keyword
- `before_last_match` (default): Extract file from commit before the last match of keyword

### clone

Clone a Git repository to a specific location.

**Required Fields:**  


- `url` (string): Git repository URL to clone
- `destination` ([`ResourceUrl`](index.md#resourceurl-path-system)): Where to clone the repository

**Optional Fields:**  


- `branch` (string): Specific branch to clone
- `depth` (int): Shallow clone depth (for faster clones)

**Example:**
```toml
[[actions]]
name = "clone-external-repo"
type = "git"
command = "clone"
url = "https://github.com/example/repo.git"
destination = "extracted:///external-repo/"
branch = "main"
depth = 1
```

## Common Use Cases

### Extract File Before Breaking Change

```toml
[[actions]]
name = "get-old-dockerfile"
type = "git"
command = "extract"
source = "Dockerfile"
destination = "extracted:///Dockerfile.old"
commit_keyword = "breaking"
search_strategy = "before_last_match"
ignore_errors = true
```

### Extract Config from Before Migration

```toml
[[actions]]
name = "backup-old-config"
type = "git"
command = "extract"
source = "config/settings.yaml"
destination = "extracted:///settings.yaml.backup"
commit_keyword = "migrate to new config"
search_strategy = "before_first_match"

[[actions]]
name = "merge-configs"
type = "shell"
command = "python scripts/merge-configs.py"
working_directory = "{{ working_directory }}"
```

### Clone Template Repository

```toml
[[actions]]
name = "clone-template"
type = "git"
command = "clone"
url = "https://github.com/myorg/project-template.git"
destination = "extracted:///template/"
branch = "main"
depth = 1

[[actions]]
name = "copy-template-files"
type = "file"
command = "copy"
source = "extracted:///template/configs/*.yaml"
destination = "repository:///configs/"
```

### Extract Multiple Historical Files

```toml
[[actions]]
name = "extract-old-requirements"
type = "git"
command = "extract"
source = "requirements.txt"
destination = "extracted:///requirements.old.txt"
commit_keyword = "update dependencies"
search_strategy = "before_last_match"

[[actions]]
name = "extract-old-dockerfile"
type = "git"
command = "extract"
source = "Dockerfile"
destination = "extracted:///Dockerfile.old"
commit_keyword = "update base image"
search_strategy = "before_last_match"

[[actions]]
name = "compare-versions"
type = "shell"
command = "diff -u extracted/requirements.old.txt repository/requirements.txt || true"
working_directory = "{{ working_directory }}"
```

## Integration with Other Actions

### Git Extract + File Copy Pattern

```toml
# Extract old version from git history
[[actions]]
name = "get-legacy-config"
type = "git"
command = "extract"
source = ".github/workflows/ci.yml"
destination = "extracted:///ci.yml.legacy"
commit_keyword = "migrate to v2"
search_strategy = "before_first_match"

# Copy to repository for comparison
[[actions]]
name = "save-for-reference"
type = "file"
command = "copy"
source = "extracted:///ci.yml.legacy"
destination = "repository:///.github/workflows/ci.yml.legacy"
```

### Git Clone + Template Pattern

```toml
# Clone shared configuration repo
[[actions]]
name = "clone-shared-configs"
type = "git"
command = "clone"
url = "https://github.com/myorg/shared-configs.git"
destination = "extracted:///shared/"
branch = "main"

# Render templates from cloned repo
[[actions]]
name = "render-config"
type = "template"
source_path = "extracted:///shared/templates/"
destination_path = "repository:///config/"
```

## Implementation Notes

**Extract command**:

- If `commit_keyword` provided: Searches git log for commits matching keyword and extracts from the commit **before** the match
- If no `commit_keyword`: Extracts file from current HEAD
- Uses `git show COMMIT:PATH` to retrieve file contents
- Returns false if file or commit not found (unless `ignore_errors` is true)
- Works within the cloned repository directory (`{working_directory}/repository/`)
- File must exist at the target commit (raises RuntimeError if not found)

**Clone command**:

- Uses `git clone` with optional branch and depth parameters
- Shallow clones (`depth=1`) are faster for large repositories
- Cloned repository placed at destination path
- Full git history available unless depth is specified

**Search strategies**:

- `before_first_match`: Useful for finding original version before any changes
- `before_last_match`: Useful for finding most recent version before latest change

**Path resolution**:

- `source` paths are relative to repository root
- `destination` supports all [`ResourceUrl`](index.md#resourceurl-path-system) schemes (`extracted:///`, `repository:///`, etc.)
- Destination directories created automatically if needed
