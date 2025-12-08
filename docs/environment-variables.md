# Environment Variables

Imbi Automations supports configuration through environment variables. These can be used instead of or in addition to the TOML configuration file. Environment variables take precedence when a configuration section is not explicitly defined in the config file.

## Quick Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | For AI features |
| `GH_TOKEN` | GitHub personal access token | For GitHub workflows |
| `IMBI_API_KEY` | Imbi API authentication key | Always |
| `IMBI_HOSTNAME` | Imbi instance hostname | Always |

## How Environment Variables Work

Each configuration section uses a prefix for its environment variables:

| Section | Prefix | Example |
|---------|--------|---------|
| `[anthropic]` | `ANTHROPIC_` | `ANTHROPIC_API_KEY` |
| `[claude]` | `CLAUDE_` | `CLAUDE_MODEL` |
| `[git]` | `GIT_` | `GIT_USER_NAME` |
| `[github]` | `GH_` | `GH_TOKEN` |
| `[imbi]` | `IMBI_` | `IMBI_API_KEY` |

Environment variables are **case-insensitive** and support `.env` file loading.

## Anthropic Configuration

Environment variables for Anthropic Claude API integration.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ANTHROPIC_API_KEY` | secret | - | Anthropic API key for Claude models |
| `ANTHROPIC_BEDROCK` | boolean | `false` | Use AWS Bedrock instead of direct API |
| `ANTHROPIC_MODEL` | string | `claude-haiku-4-5-20251001` | Claude model to use |

**Example:**
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
export ANTHROPIC_MODEL="claude-sonnet-4-20250514"
```

## Claude Agent SDK Configuration

Environment variables for Claude Agent SDK integration.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `CLAUDE_EXECUTABLE` | string | `claude` | Path to Claude Code executable |
| `CLAUDE_BASE_PROMPT` | path | (built-in) | Custom base prompt file path |
| `CLAUDE_ENABLED` | boolean | `true` | Enable Claude Code actions |
| `CLAUDE_MODEL` | string | `claude-haiku-4-5` | Model for Claude Agent SDK |

**Example:**
```bash
export CLAUDE_EXECUTABLE="/usr/local/bin/claude"
export CLAUDE_MODEL="claude-sonnet-4-5"
export CLAUDE_ENABLED="true"
```

## Git Configuration

Environment variables for git commit operations.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GIT_USER_NAME` | string | `Imbi Automations` | Git commit author name |
| `GIT_USER_EMAIL` | string | `automations@imbi.ai` | Git commit author email |
| `GIT_GPG_SIGN` | boolean | `false` | Enable GPG signing for commits |
| `GIT_GPG_FORMAT` | string | - | Signing format: `gpg`, `ssh`, `x509`, `openpgp` |
| `GIT_SIGNING_KEY` | string | - | GPG or SSH signing key identifier |
| `GIT_SSH_PROGRAM` | string | - | SSH program for signing |
| `GIT_GPG_PROGRAM` | string | - | GPG program path |
| `GIT_COMMIT_ARGS` | string | `""` | Additional git commit arguments |

**Example:**
```bash
export GIT_USER_NAME="CI Bot"
export GIT_USER_EMAIL="ci-bot@example.com"
export GIT_GPG_SIGN="true"
export GIT_GPG_FORMAT="ssh"
export GIT_SIGNING_KEY="~/.ssh/id_ed25519.pub"
```

## GitHub Configuration

Environment variables for GitHub API integration.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GH_TOKEN` | secret | **required** | GitHub personal access token |
| `GH_HOST` | string | `github.com` | GitHub hostname (for Enterprise) |

**Example:**
```bash
export GH_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
export GH_HOST="github.enterprise.com"
```

**Token Permissions Required:**

- `repo` - Full repository access
- `workflow` - Update GitHub Actions workflows
- `admin:org` - Manage organization (for environment sync)

## Imbi Configuration

Environment variables for Imbi project management integration.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMBI_API_KEY` | secret | **required** | Imbi API authentication key |
| `IMBI_HOSTNAME` | string | **required** | Imbi instance hostname |
| `IMBI_GITHUB_IDENTIFIER` | string | `github` | Project identifier field for GitHub |
| `IMBI_PAGERDUTY_IDENTIFIER` | string | `pagerduty` | Project identifier field for PagerDuty |
| `IMBI_SONARQUBE_IDENTIFIER` | string | `sonarqube` | Project identifier field for SonarQube |
| `IMBI_SENTRY_IDENTIFIER` | string | `sentry` | Project identifier field for Sentry |
| `IMBI_GITHUB_LINK` | string | `GitHub Repository` | Link type name for GitHub URLs |
| `IMBI_GRAFANA_LINK` | string | `Grafana Dashboard` | Link type name for Grafana URLs |
| `IMBI_PAGERDUTY_LINK` | string | `PagerDuty` | Link type name for PagerDuty URLs |
| `IMBI_SENTRY_LINK` | string | `Sentry` | Link type name for Sentry URLs |
| `IMBI_SONARQUBE_LINK` | string | `SonarQube` | Link type name for SonarQube URLs |

**Example:**
```bash
export IMBI_API_KEY="your-api-key-uuid"
export IMBI_HOSTNAME="imbi.example.com"
export IMBI_GITHUB_IDENTIFIER="github-id"
```

## Using .env Files

Imbi Automations automatically loads environment variables from a `.env` file in the current directory:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-api03-...
GH_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
IMBI_API_KEY=your-api-key-uuid
IMBI_HOSTNAME=imbi.example.com
```

**Security Note:** Never commit `.env` files to version control. Add `.env` to your `.gitignore`.

## Precedence Rules

Configuration values are resolved in the following order (highest to lowest priority):

1. **Environment variables** - Always checked first
2. **Config file values** - From TOML configuration
3. **Default values** - Built-in defaults

When a configuration section is defined in the TOML file, environment variables serve as defaults for any fields not explicitly set in that section.

**Example:**
```toml
# config.toml
[github]
host = "github.enterprise.com"
# token not set - will use GH_TOKEN environment variable
```

```bash
export GH_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
```

In this case, `host` comes from the config file and `token` comes from the environment variable.

## Minimal Environment Setup

For basic GitHub workflows, set these environment variables:

```bash
export GH_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
export IMBI_API_KEY="your-api-key-uuid"
export IMBI_HOSTNAME="imbi.example.com"
```

Then use a minimal config file:

```toml
# config.toml
[github]
[imbi]
```

## CI/CD Integration

### GitHub Actions

```yaml
env:
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  IMBI_API_KEY: ${{ secrets.IMBI_API_KEY }}
  IMBI_HOSTNAME: imbi.example.com

steps:
  - name: Run workflow
    run: imbi-automations config.toml workflows/update-deps --all-projects
```

### Docker

```bash
docker run -e GH_TOKEN -e IMBI_API_KEY -e IMBI_HOSTNAME \
  imbi-automations config.toml workflows/update-deps --all-projects
```

Or with an env file:

```bash
docker run --env-file .env \
  imbi-automations config.toml workflows/update-deps --all-projects
```

## Troubleshooting

### Variable Not Being Read

1. Check the variable name matches the expected prefix + field name
2. Environment variables are case-insensitive
3. Ensure the config section exists (even if empty) in the TOML file

### Secret Values in Logs

Secret values (`api_key`, `token`) are stored as `SecretStr` and will not appear in logs or error messages. They display as `**********` when printed.

### Checking Current Configuration

Use verbose mode to see which configuration values are being used:

```bash
imbi-automations config.toml workflows/test --all-projects -vvv
```

## See Also

- [Configuration Reference](configuration.md) - Complete TOML configuration options
- [CLI Reference](cli.md) - Command-line options
- [Docker](docker.md) - Running in containers
