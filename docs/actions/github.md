# GitHub Actions

GitHub actions provide GitHub-specific operations like environment synchronization and workflow management.

## Configuration

```toml
[[actions]]
name = "action-name"
type = "github"
command = "sync_environments"
# Command-specific fields
```

## Commands

### sync_environments

Synchronize GitHub repository environments with Imbi project environments.

**Example:**
```toml
[[actions]]
name = "sync-github-envs"
type = "github"
command = "sync_environments"
```

**Behavior:**  

- Reads environment data from Imbi project (`imbi_project.environments: list[ImbiEnvironment]`)
- Extracts slugs directly from `ImbiEnvironment` objects (provided by Imbi API)
- Compares with existing GitHub repository environments
- Creates missing environments in GitHub
- Deletes extra environments from GitHub (not in Imbi)
- Operations sorted alphabetically for deterministic behavior
- Logs all operations (created, deleted, errors)
- Raises error if sync fails

**Environment Slugs:**  

- Slugs are provided by the Imbi API (no local transformation)
- The `ImbiEnvironment` model contains both `name` and `slug` fields
- Slug format is controlled by Imbi (typically lowercase with hyphens)

## Common Use Cases

### Environment Synchronization

```toml
[[conditions]]
remote_file_exists = ".github/workflows/deploy.yml"

[[actions]]
name = "ensure-environments"
type = "github"
command = "sync_environments"
```

### Post-Deployment Updates

```toml
[[actions]]
name = "deploy-code"
type = "shell"
command = "deploy.sh"

[[actions]]
name = "update-environments"
type = "github"
command = "sync_environments"
```

## Implementation Notes

The GitHub action implementation:

- Requires GitHub API access with environment management permissions
- Uses authenticated GitHub client from workflow configuration
- Respects GitHub API rate limits
- Provides idempotent operations (safe to re-run)
- Integrates with Imbi project environment configuration
- No repository cloning needed (API-only operations)
- Skips projects with no environments defined in Imbi

**Type Safety:**  

- Uses `ImbiEnvironment` model objects (not plain strings) for type-safe environment handling
- Each environment has `name`, `slug`, `icon_class`, and optional `description` fields
- Slugs provided directly by Imbi API (no local transformation)
- Imbi client creates `ImbiEnvironment` objects from API response data

**Filter Support:**  

- Workflow filters can target specific environments using `project_environments` field
- Supports both environment names ("Production") and slugs ("production")
- Filter checks against both `name` and `slug` fields for flexibility
- Example: `project_environments = ["production", "staging"]` in workflow config
