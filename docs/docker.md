# Docker

This guide covers running imbi-automations in Docker containers.

## Building the Image

Build the wheel first, then the Docker image:

```bash
pip install build
python -m build --wheel
docker build -t imbi-automations:latest .
```

### Multi-Architecture Build

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
    -t imbi-automations:latest .
```

## Running Workflows

```bash
docker run --rm \
    -v $(pwd)/config.toml:/opt/config/config.toml:ro \
    -v $(pwd)/workflows:/opt/workflows:ro \
    -v ~/.ssh:/home/imbi-automations/.ssh:ro \
    -v imbi-cache:/home/imbi-automations/cache \
    -e GH_TOKEN="ghp_your_token" \
    imbi-automations:latest \
    /opt/config/config.toml \
    /opt/workflows/my-workflow \
    --all-projects
```

## Volume Mounts

| Path | Purpose | Notes |
|------|---------|-------|
| `/opt/config/config.toml` | Configuration file | Mount as read-only |
| `/opt/workflows` | Workflow definitions | Mount as read-only |
| `/home/imbi-automations/.ssh` | SSH keys | Mount as read-only; enables commit signing |
| `/home/imbi-automations/cache` | Metadata cache | Use named volume for persistence |
| `/opt/errors` | Error preservation | Mount if using `--preserve-on-error` |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GIT_USER_NAME` | `Imbi Automations` | Git commit author name |
| `GIT_USER_EMAIL` | `imbi-automations@aweber.com` | Git commit author email |
| `GH_TOKEN` | - | GitHub personal access token |
| `IMBI_AUTOMATIONS_CACHE_DIR` | `/home/imbi-automations/cache` | Cache directory path |
| `IMBI_AUTOMATIONS_CONFIG` | `/home/imbi-automations/config/config.toml` | Default config path |

## SSH Commit Signing

When SSH keys are mounted to `/home/imbi-automations/.ssh`, the entrypoint automatically configures git commit signing:

- Searches for keys in order: `id_ed25519`, `id_rsa`, `id_ecdsa`
- Configures `gpg.format ssh` and `commit.gpgsign true`
- Creates an `allowed_signers` file for verification

Ensure your SSH key permissions are correct before mounting:

```bash
chmod 600 ~/.ssh/id_ed25519
chmod 700 ~/.ssh
```

!!! note
    For GitHub to verify signed commits, add the same SSH key as a "Signing Key" in your GitHub account settings (separate from authentication keys).

## GitHub CLI Authentication

The `gh` CLI is pre-installed. Authentication is configured automatically using one of these methods (in order of precedence):

1. **Environment variable**: Set `GH_TOKEN` when running the container
2. **Token file**: Mount a file containing the token to `/config/gh-token` or `~/.config/gh/token`

### Using Environment Variable

```bash
docker run --rm \
    -e GH_TOKEN="ghp_your_personal_access_token" \
    imbi-automations:latest ...
```

### Using Token File

```bash
# Create token file
echo "ghp_your_token" > gh-token

# Mount it
docker run --rm \
    -v $(pwd)/gh-token:/config/gh-token:ro \
    imbi-automations:latest ...
```

### Required Token Scopes

For full functionality, your token needs:

- `repo` - Repository access
- `read:org` - Organization membership (for org repos)
- `workflow` - GitHub Actions (if syncing workflows)

## Debugging

### Interactive Shell

```bash
docker run --rm -it \
    -v $(pwd)/config.toml:/opt/config/config.toml:ro \
    -v $(pwd)/workflows:/opt/workflows:ro \
    --entrypoint /bin/bash \
    imbi-automations:latest
```

### View Entrypoint Output

The entrypoint logs configuration steps to stderr:

```
Configuring git commit signing with SSH key: /home/imbi-automations/.ssh/id_ed25519
Loaded GitHub token from /config/gh-token
```

### Verify Configuration

Inside the container:

```bash
# Check git signing config
git config --global --list | grep -E "(gpg|sign)"

# Verify gh authentication
gh auth status

# Test SSH connection
ssh -T git@github.com
```

## Performance Tips

### Use tmpfs for Workspace

For faster repository operations:

```bash
docker run --rm \
    --tmpfs /opt/workspace:exec,size=4g \
    imbi-automations:latest ...
```

### Persist Metadata Cache

Use a named volume to avoid re-fetching Imbi metadata:

```bash
docker volume create imbi-cache
docker run --rm \
    -v imbi-cache:/home/imbi-automations/cache \
    imbi-automations:latest ...
```

## Docker Compose Example

```yaml
services:
  imbi-automations:
    image: imbi-automations:latest
    volumes:
      - ./config.toml:/opt/config/config.toml:ro
      - ./workflows:/opt/workflows:ro
      - ~/.ssh:/home/imbi-automations/.ssh:ro
      - imbi-cache:/home/imbi-automations/cache
    environment:
      - GIT_USER_NAME=Imbi Automations
      - GIT_USER_EMAIL=imbi-automations@example.com
      - GH_TOKEN=${GH_TOKEN}

volumes:
  imbi-cache:
```

Run with:

```bash
docker compose run --rm imbi-automations \
    /opt/config/config.toml \
    /opt/workflows/my-workflow \
    --all-projects
```
