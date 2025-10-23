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

**Status:** ✅ Implemented

Synchronize GitHub repository environments with Imbi project environments.

**Example:**
```toml
[[actions]]
name = "sync-github-envs"
type = "github"
command = "sync_environments"
```

**Behavior:**

- Reads environments from Imbi project (`imbi_project.environments`)
- Compares with existing GitHub repository environments
- Creates missing environments in GitHub
- Deletes extra environments from GitHub (not in Imbi)
- Uses case-insensitive comparison
- Logs all operations (created, deleted, errors)
- Raises error if sync fails

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
