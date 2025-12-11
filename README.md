# Imbi Automations CLI

[![Tests](https://github.com/AWeber-Imbi/imbi-automations/actions/workflows/test.yml/badge.svg)](https://github.com/AWeber-Imbi/imbi-automations/actions/workflows/test.yml)
[![Docker Build](https://github.com/AWeber-Imbi/imbi-automations/actions/workflows/docker.yml/badge.svg)](https://github.com/AWeber-Imbi/imbi-automations/actions/workflows/docker.yml)
[![PyPI Version](https://img.shields.io/pypi/v/imbi-automations.svg)](https://pypi.org/project/imbi-automations/)
[![Docker Hub](https://img.shields.io/docker/v/aweber/imbi-automations?label=docker%20hub&sort=semver)](https://hub.docker.com/r/aweber/imbi-automations)
[![GHCR](https://ghcr-badge.egpl.dev/aweber-imbi/imbi-automations/latest_tag?trim=major&label=ghcr.io)](https://github.com/AWeber-Imbi/imbi-automations/pkgs/container/imbi-automations)

CLI tool for executing automated workflows across Imbi projects with AI-powered transformations and GitHub PR integration.

## Overview

Imbi Automations is a comprehensive CLI framework that enables bulk automation across software project repositories with deep integration to the Imbi project management system. The tool supports multiple workflow types with advanced filtering, conditional execution, and AI-powered transformations.

## Key Features

- **GitHub Integration**: GitHub API integration with comprehensive repository operations
- **Workflow Engine**: Action-based processing with conditional execution
- **AI Integration**: Claude Code SDK for intelligent transformations
- **Batch Processing**: Concurrent processing with resumption capabilities
- **Template System**: Jinja2-based file generation with full project context
- **Advanced Filtering**: Target specific project subsets with multiple criteria

## Action Types

- **Callable Actions**: Direct method calls on client instances
- **Claude Code**: Comprehensive AI-powered code transformations
- **Docker Operations**: Container-based file extraction and manipulation
- **Git Operations**: Version control operations and branch management
- **File Actions**: Copy, move, delete, and regex replacement operations
- **Shell Commands**: Execute arbitrary commands with template variables
- **Template System**: Generate files from Jinja2 templates

## Documentation

Documentation is available at [https://aweber-imbi.github.io/imbi-automations/](https://aweber-imbi.github.io/imbi-automations/).


## Quick Start

```bash
# Run workflows
# Note: Each workflow directory should contain workflow.toml (or config.toml for backward compatibility)
imbi-automations config.toml workflows/workflow-name --all-projects

# Resume from a specific project
imbi-automations config.toml workflows/workflow-name --all-projects --start-from-project my-project-slug

# Run using Docker:

```bash
docker run --rm \
  -v $(pwd)/config.toml:/config/config.toml:ro \
  -v $(pwd)/workflows:/workflows:ro \
  -v ~/.ssh:/root/.ssh:ro \
  -v imbi-cache:/cache \
  aweber/imbi-automations:latest /config/config.toml /workflows/my-workflow --all-projects
````

## Installation

### From PyPI

```bash
pip install imbi-automations
```

### Docker Installation

Pre-built multi-architecture images are automatically published to both **Docker Hub** and **GitHub Container Registry** on every release:

```bash
# Pull from Docker Hub (recommended)
docker pull aweber/imbi-automations:latest

# Or pull from GitHub Container Registry
docker pull ghcr.io/aweber-imbi/imbi-automations:latest

# Or use a specific version
docker pull aweber/imbi-automations:1.0.0
docker pull ghcr.io/aweber-imbi/imbi-automations:1.0.0

# Run with docker-compose (recommended)
docker-compose run --rm aweber/imbi-automations /config/config.toml /workflows/my-workflow --all-projects

# Or run directly with docker (Docker Hub)
docker run --rm \
  -v $(pwd)/config.toml:/config/config.toml:ro \
  -v $(pwd)/workflows:/workflows:ro \
  -v ~/.ssh:/root/.ssh:ro \
  -v imbi-cache:/cache \
  aweber/imbi-automations:latest /config/config.toml /workflows/my-workflow --all-projects

# Or run with GHCR
docker run --rm \
  -v $(pwd)/config.toml:/config/config.toml:ro \
  -v $(pwd)/workflows:/workflows:ro \
  -v ~/.ssh:/root/.ssh:ro \
  -v imbi-cache:/cache \
  ghcr.io/aweber-imbi/imbi-automations:latest /config/config.toml /workflows/my-workflow --all-projects
```

**Build from source:**
```bash
docker build -t imbi-automations:latest .
```

**Docker Volume Mounts:**
- `/config/config.toml` - Configuration file (read-only recommended)
- `/workflows` - Workflows directory (read-only recommended)
- `/cache` - Metadata cache directory (persistent)
- `/workspace` - Temporary working directory for repo clones
- `/root/.ssh` - SSH keys for git operations (read-only)
- `/root/.gnupg` - GPG keys for commit signing (optional, read-only)

**Important Notes:**
- Claude Code in containers may have limitations with interactive features
- Ensure SSH keys have proper permissions (0600) when mounting
- API keys should be in `config.toml` for security
- Use named volumes for cache to improve performance across runs

### Development Setup

```bash
git clone https://github.com/AWeber-Imbi/imbi-automations.git
cd imbi-automations
pip install -e .[dev]
pre-commit install
```
