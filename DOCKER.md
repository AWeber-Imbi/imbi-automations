# Docker Usage Guide

This guide provides comprehensive information about running imbi-automations in Docker containers.

## Quick Start

```bash
# Build the image
docker build -t imbi-automations:latest .

# Run using docker-compose (recommended)
docker-compose run --rm imbi-automations /config/config.toml /workflows/my-workflow --all-projects
```

## Building the Image

### Standard Build

```bash
docker build -t imbi-automations:latest .
```

### Build with Specific Version Tag

```bash
docker build -t imbi-automations:1.0.0 .
```

### Multi-platform Build (for ARM/AMD64)

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t imbi-automations:latest .
```

## Running Workflows

### Using docker-compose (Recommended)

The `docker-compose.yml` file provides an opinionated setup with sensible defaults:

```bash
# Run a specific workflow
docker-compose run --rm imbi-automations \
  /config/config.toml \
  /workflows/python3.12-upgrade \
  --all-projects

# Run with additional CLI options
docker-compose run --rm imbi-automations \
  /config/config.toml \
  /workflows/my-workflow \
  --project-id 123 \
  --preserve-on-error \
  --verbose

# Resume from a specific project
docker-compose run --rm imbi-automations \
  /config/config.toml \
  /workflows/my-workflow \
  --all-projects \
  --start-from-project my-project-slug
```

### Using docker run

For more control over volume mounts and configuration:

```bash
docker run --rm \
  -v $(pwd)/config.toml:/config/config.toml:ro \
  -v $(pwd)/workflows:/workflows:ro \
  -v ~/.ssh:/root/.ssh:ro \
  -v imbi-cache:/cache \
  -v imbi-workspace:/workspace \
  -e GIT_AUTHOR_NAME="Your Name" \
  -e GIT_AUTHOR_EMAIL="your.email@example.com" \
  imbi-automations:latest \
  /config/config.toml \
  /workflows/my-workflow \
  --all-projects
```

## Volume Mounts Explained

### Required Mounts

#### `/config/config.toml`
- **Purpose**: Main configuration file with API keys and settings
- **Recommendation**: Mount as read-only (`:ro`)
- **Example**: `-v $(pwd)/config.toml:/config/config.toml:ro`

#### `/workflows`
- **Purpose**: Directory containing workflow definitions
- **Recommendation**: Mount as read-only (`:ro`)
- **Example**: `-v $(pwd)/workflows:/workflows:ro`

### Optional but Recommended Mounts

#### `/cache`
- **Purpose**: Imbi metadata cache (15-minute TTL)
- **Recommendation**: Use named volume for persistence
- **Example**: `-v imbi-cache:/cache`
- **Benefits**: Faster startup, reduced API calls

#### `/workspace`
- **Purpose**: Temporary directory for repository clones
- **Recommendation**: Use named volume or tmpfs
- **Example**: `-v imbi-workspace:/workspace` or `--tmpfs /workspace:exec`
- **Note**: Data is temporary and can be discarded after runs

#### `/root/.ssh`
- **Purpose**: SSH keys for git operations
- **Requirement**: Required if using SSH URLs for git clone
- **Recommendation**: Mount as read-only (`:ro`)
- **Example**: `-v ~/.ssh:/root/.ssh:ro`
- **Important**: Ensure key permissions are 0600

#### `/root/.gnupg`
- **Purpose**: GPG keys for commit signing
- **Requirement**: Only if using GPG commit signing
- **Recommendation**: Mount as read-only (`:ro`)
- **Example**: `-v ~/.gnupg:/root/.gnupg:ro`

### Advanced Mounts

#### Error Preservation Directory
If using `--preserve-on-error`, mount an external directory for debugging:

```bash
docker run --rm \
  -v $(pwd)/errors:/workspace/errors \
  ...
  imbi-automations:latest \
  /config/config.toml \
  /workflows/my-workflow \
  --all-projects \
  --preserve-on-error
```

## Environment Variables

### Git Configuration

```bash
-e GIT_AUTHOR_NAME="Imbi Automations"
-e GIT_AUTHOR_EMAIL="imbi-automations@example.com"
-e GIT_COMMITTER_NAME="Imbi Automations"
-e GIT_COMMITTER_EMAIL="imbi-automations@example.com"
```

### API Keys (Alternative to config.toml)

```bash
-e ANTHROPIC_API_KEY="your-api-key"
```

**Note**: Prefer putting API keys in `config.toml` for better security and auditability.

### Cache Directory Override

```bash
-e IMBI_AUTOMATIONS_CACHE_DIR=/cache
```

## Known Limitations

### Claude Code Interactive Features

Claude Code expects an interactive terminal (TTY) for certain features. In containerized environments:

- **Planning agents** should work normally (non-interactive)
- **Interactive prompts** may not work as expected
- **File watching** is not available

**Workaround**: Use `docker-compose run` with TTY enabled if interactive features are needed:

```yaml
services:
  imbi-automations:
    stdin_open: true
    tty: true
```

### Docker-in-Docker

Some workflows may use Docker actions. To support this:

#### Option 1: Mount Docker Socket (Less Secure)

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ...
  imbi-automations:latest
```

**Warning**: This grants the container full Docker control.

#### Option 2: Use DinD (Docker-in-Docker)

```yaml
services:
  imbi-automations:
    privileged: true
    volumes:
      - docker-in-docker:/var/lib/docker
```

**Warning**: Requires privileged mode.

### File Permissions

When mounting SSH keys or GPG keys:

```bash
# Ensure correct permissions before mounting
chmod 600 ~/.ssh/id_rsa
chmod 700 ~/.ssh
```

### Resume State Limitations

The `--resume` functionality has limitations in Docker:

- **Absolute paths**: Resume state files contain absolute paths
- **Same container**: Resume must occur in the same container instance
- **Volume preservation**: Workspace volume must not be cleared between runs

**Recommendation**: For resume functionality, use a persistent workspace volume.

## Debugging

### Get a Shell in the Container

```bash
# Using docker-compose
docker-compose run --rm --entrypoint /bin/bash imbi-automations

# Using docker run
docker run --rm -it \
  -v $(pwd)/config.toml:/config/config.toml:ro \
  -v $(pwd)/workflows:/workflows:ro \
  --entrypoint /bin/bash \
  imbi-automations:latest
```

### View Logs

```bash
# Run with verbose logging
docker-compose run --rm imbi-automations \
  /config/config.toml \
  /workflows/my-workflow \
  --all-projects \
  --verbose

# Check per-project logs (if using error preservation)
docker run --rm \
  -v $(pwd)/errors:/workspace/errors \
  imbi-automations:latest \
  /bin/bash -c "cat /workspace/errors/my-workflow/*/imbi-automations.log"
```

### Inspect Named Volumes

```bash
# List volumes
docker volume ls

# Inspect cache volume
docker volume inspect imbi-cache

# View cache contents
docker run --rm -v imbi-cache:/cache alpine ls -la /cache
```

### Clean Up Volumes

```bash
# Remove specific volume
docker volume rm imbi-cache

# Remove all unused volumes
docker volume prune
```

## Performance Optimization

### Use tmpfs for Workspace

For faster repository cloning and operations:

```bash
docker run --rm \
  --tmpfs /workspace:exec,size=4g \
  ...
  imbi-automations:latest
```

**Note**: Adjust size based on repository sizes and available RAM.

### Cache Docker Layers

Ensure you're not invalidating cache unnecessarily:

```bash
# Build with BuildKit for better caching
DOCKER_BUILDKIT=1 docker build -t imbi-automations:latest .
```

### Pre-populate Cache

Run a lightweight workflow first to populate the metadata cache:

```bash
# Populate cache with a single project
docker-compose run --rm imbi-automations \
  /config/config.toml \
  /workflows/simple-workflow \
  --project-id 1

# Then run full batch
docker-compose run --rm imbi-automations \
  /config/config.toml \
  /workflows/my-workflow \
  --all-projects
```

## Security Best Practices

1. **Read-only Mounts**: Always mount config and workflows as read-only
2. **API Keys**: Use `config.toml` instead of environment variables
3. **SSH Keys**: Mount as read-only with correct permissions
4. **Non-root User**: Consider running as non-root (requires Dockerfile modification)
5. **Network Isolation**: Use Docker networks to limit container access
6. **Secrets Management**: Use Docker secrets for production deployments

## Example Configurations

### Minimal Production Setup

```yaml
version: '3.8'

services:
  imbi-automations:
    image: imbi-automations:latest
    volumes:
      - ./config.toml:/config/config.toml:ro
      - ./workflows:/workflows:ro
      - imbi-cache:/cache
    environment:
      - GIT_AUTHOR_NAME=Imbi Automations
      - GIT_AUTHOR_EMAIL=imbi-automations@example.com

volumes:
  imbi-cache:
```

### Development Setup with Debugging

```yaml
version: '3.8'

services:
  imbi-automations:
    build: .
    volumes:
      - ./config.toml:/config/config.toml:ro
      - ./workflows:/workflows:ro
      - ./errors:/workspace/errors
      - ~/.ssh:/root/.ssh:ro
      - imbi-cache:/cache
      - imbi-workspace:/workspace
    environment:
      - GIT_AUTHOR_NAME=Dev User
      - GIT_AUTHOR_EMAIL=dev@example.com
    stdin_open: true
    tty: true

volumes:
  imbi-cache:
  imbi-workspace:
```

### CI/CD Setup

```yaml
version: '3.8'

services:
  imbi-automations:
    image: imbi-automations:${VERSION:-latest}
    volumes:
      - /config/config.toml:/config/config.toml:ro
      - /workflows:/workflows:ro
    environment:
      - GIT_AUTHOR_NAME=CI Bot
      - GIT_AUTHOR_EMAIL=ci@example.com
    secrets:
      - github_token
      - imbi_token

secrets:
  github_token:
    external: true
  imbi_token:
    external: true
```

## Troubleshooting

### Issue: Claude Code Not Found

**Symptom**: Error about `claude` command not found

**Solution**: The Dockerfile installs Claude Code using the official installer:

```dockerfile
RUN curl -fsSL https://claude.ai/install.sh | sh
```

If this fails, verify the installer is available and working. You can test manually:

```bash
docker run --rm python:3.12-trixie bash -c "curl -fsSL https://claude.ai/install.sh | sh && claude --version"
```

### Issue: SSH Authentication Failures

**Symptom**: Git clone fails with authentication errors

**Solutions**:
1. Verify SSH keys are mounted: `docker exec <container> ls -la /root/.ssh`
2. Check key permissions: `chmod 600 ~/.ssh/id_rsa`
3. Test SSH connection: `docker exec <container> ssh -T git@github.com`
4. Ensure SSH agent forwarding if needed

### Issue: Slow Performance

**Symptoms**: Slow repository cloning or file operations

**Solutions**:
1. Use tmpfs for workspace: `--tmpfs /workspace:exec,size=4g`
2. Use named volumes instead of bind mounts
3. Ensure BuildKit caching is enabled
4. Check available disk space: `df -h`

### Issue: Permission Denied Errors

**Symptom**: Cannot write to mounted volumes

**Solutions**:
1. Check volume mount permissions
2. Run container as non-root (requires Dockerfile changes)
3. Use named volumes instead of bind mounts for writable directories

## Automated Docker Builds

The project uses GitHub Actions to automatically build and push Docker images to **both Docker Hub and GitHub Container Registry (GHCR)**.

### Image Registries

Images are published to two registries for redundancy and flexibility:

- **Docker Hub**: `aweber/imbi-automations` (public, no authentication required to pull)
- **GitHub Container Registry**: `ghcr.io/aweber-imbi/imbi-automations` (public, no authentication required to pull)

**Which registry should I use?**
- **Docker Hub** - Traditional registry, better for compatibility
- **GHCR** - Tighter GitHub integration, no rate limiting for GitHub Actions

### Workflow Triggers

The Docker build workflow (`.github/workflows/docker.yml`) is triggered by:

- **Releases**: When a new GitHub release is created
- **Main Branch**: On every push to the main branch (tagged as `latest`)
- **Tags**: On version tags (e.g., `v1.0.0`)
- **Pull Requests**: Builds but doesn't push (for testing)
- **Manual**: Via workflow_dispatch

### Image Tags

Images are automatically tagged identically on both registries:

| Tag Pattern | Example | Description |
|-------------|---------|-------------|
| `latest` | `aweber/imbi-automations:latest` | Latest commit on main branch |
| `{version}` | `aweber/imbi-automations:1.0.0` | Semantic version from release |
| `{major}.{minor}` | `aweber/imbi-automations:1.0` | Major.minor version |
| `{major}` | `aweber/imbi-automations:1` | Major version |
| `main-{sha}` | `aweber/imbi-automations:main-abc1234` | Short commit SHA |
| `pr-{number}` | `aweber/imbi-automations:pr-123` | PR builds (not pushed) |

### Multi-Architecture Support

Images are built for multiple platforms:
- `linux/amd64` (x86_64)
- `linux/arm64` (ARM64/Apple Silicon)

### Required GitHub Secrets

To enable automated builds to Docker Hub, configure these secrets:

1. **`DOCKERHUB_USERNAME`** - Docker Hub username
2. **`DOCKERHUB_TOKEN`** - Docker Hub access token (not password)

**Note**: GHCR uses `GITHUB_TOKEN` which is automatically provided by GitHub Actions - no additional secrets needed.

**Setting up Docker Hub token:**
1. Log in to Docker Hub
2. Go to Account Settings → Security → Access Tokens
3. Create a new access token with "Read, Write, Delete" permissions
4. Add the token to GitHub repository secrets

### Manual Build and Push

To manually trigger a build:

1. Go to GitHub Actions → "Build and Push Docker Image"
2. Click "Run workflow"
3. Select the branch
4. Click "Run workflow"

Both registries will be updated automatically.

## Additional Resources

- [Main Documentation](README.md)
- [Architecture Guide](AGENTS.md)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Docker Security Best Practices](https://docs.docker.com/develop/security-best-practices/)
- [GitHub Actions Docker Documentation](https://docs.docker.com/build/ci/github-actions/)
