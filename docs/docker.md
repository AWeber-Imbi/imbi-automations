# Docker

This guide covers running imbi-automations in Docker containers.

Pre-built images are available from Docker Hub and GitHub Container Registry:

- `aweber/imbi-automations:latest`
- `ghcr.io/aweber-imbi/imbi-automations:latest`

## Running Workflows

```bash
docker run --rm \
    -v $(pwd)/config.toml:/opt/config/config.toml:ro \
    -v $(pwd)/workflows:/opt/workflows:ro \
    -v ~/.ssh:/home/imbi-automations/.ssh:ro \
    -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    -e IMBI_API_KEY="$IMBI_API_KEY" \
    -e GH_TOKEN="$GH_TOKEN" \
    aweber/imbi-automations:latest \
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
| `/opt/errors` | Error preservation | Mount if using `--preserve-on-error` |
| `/docker-entrypoint-init.d` | Initialization scripts | See [Initialization Directory](#initialization-directory) |

## Environment Variables

### Required Variables

The following environment variables **must** be set when running the container. The entrypoint will exit with an error if any are missing:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `IMBI_API_KEY` | Imbi API key |
| `GH_TOKEN` | GitHub personal access token |

!!! note
    These variables are required even if the same values are specified in the configuration file. When running in Docker, the configuration file does not need to include `anthropic.api_key`, `imbi.api_key`, or `github.token` - they are automatically loaded from environment variables via pydantic-settings.

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GIT_USER_NAME` | `Imbi Automations` | Git commit author name |
| `GIT_USER_EMAIL` | `imbi-automations@aweber.com` | Git commit author email |
| `GH_HOST` | `github.com` | GitHub hostname (for GitHub Enterprise) |

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
    aweber/imbi-automations:latest ...
```

### Using Token File

```bash
# Create token file
echo "ghp_your_token" > gh-token

# Mount it
docker run --rm \
    -v $(pwd)/gh-token:/config/gh-token:ro \
    aweber/imbi-automations:latest ...
```

### Required Token Scopes

For full functionality, your token needs:

- `repo` - Repository access
- `read:org` - Organization membership (for org repos)
- `workflow` - GitHub Actions (if syncing workflows)

## Initialization Directory

The container supports an initialization directory at `/docker-entrypoint-init.d/` for installing additional packages or running setup scripts at container startup. This pattern is similar to database images like PostgreSQL's `/docker-entrypoint-initdb.d`.

Files are processed in sorted order (use numeric prefixes for ordering) and support three extensions:

| Extension | Purpose | Processing |
|-----------|---------|------------|
| `.apt` | System packages | Installed via `apt-get install` |
| `.pip` | Python packages | Installed via `pip install -r` |
| `.sh` | Shell scripts | Executed with `bash` |

### Example Files

**`10-system.apt`** - System packages (one per line, comments supported):

```
# Build dependencies
build-essential
libpq-dev

# Other tools
jq
```

**`20-python.pip`** - Python packages (standard requirements format):

```
pandas>=2.0
sqlalchemy
requests
```

**`30-custom.sh`** - Custom setup script:

```bash
#!/bin/bash
npm install -g some-tool
```

### Usage

Mount individual files:

```bash
docker run --rm \
    -v ./my-packages.apt:/docker-entrypoint-init.d/10-packages.apt:ro \
    -v ./requirements.pip:/docker-entrypoint-init.d/20-python.pip:ro \
    aweber/imbi-automations:latest ...
```

Or mount a directory containing multiple init files:

```bash
docker run --rm \
    -v ./init.d:/docker-entrypoint-init.d:ro \
    aweber/imbi-automations:latest ...
```

### Docker Compose Example

```yaml
services:
  imbi-automations:
    image: aweber/imbi-automations:latest
    volumes:
      - ./config.toml:/opt/config/config.toml:ro
      - ./workflows:/opt/workflows:ro
      - ./init.d:/docker-entrypoint-init.d:ro
```

!!! note
    Initialization runs on every container start. For production workflows with
    many dependencies, consider building a custom image instead.

## Debugging

### Interactive Shell

```bash
docker run --rm -it \
    -v $(pwd)/config.toml:/opt/config/config.toml:ro \
    -v $(pwd)/workflows:/opt/workflows:ro \
    --entrypoint /bin/bash \
    aweber/imbi-automations:latest
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

## Docker Compose Example

```yaml
services:
  imbi-automations:
    image: aweber/imbi-automations:latest
    volumes:
      - ./config.toml:/opt/config/config.toml:ro
      - ./workflows:/opt/workflows:ro
      - ~/.ssh:/home/imbi-automations/.ssh:ro
    environment:
      # Required
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - IMBI_API_KEY=${IMBI_API_KEY}
      - GH_TOKEN=${GH_TOKEN}
      # Optional
      - GIT_USER_NAME=Imbi Automations
      - GIT_USER_EMAIL=imbi-automations@example.com
```

Run with:

```bash
docker compose run --rm imbi-automations \
    /opt/config/config.toml \
    /opt/workflows/my-workflow \
    --all-projects
```
