# Configuration File

Imbi Automations uses TOML-based configuration files with Pydantic validation for all settings. This document describes all available configuration options.

## Configuration File Location

By default, the CLI expects a `config.toml` file as the first argument:

```bash
imbi-automations config.toml workflows/workflow-name --all-projects
```

## Complete Configuration Example

```toml
# Global Settings
ai_commits = false
dry_run = false
dry_run_dir = "./dry-runs"
error_dir = "./errors"
preserve_on_error = false

# Anthropic API Configuration
[anthropic]
api_key = "${ANTHROPIC_API_KEY}"  # Or set directly
bedrock = false
model = "claude-haiku-4-5-20251001"

# Claude Agent SDK Configuration
[claude]
executable = "claude"
enabled = true
model = "claude-haiku-4-5"

# Git Configuration
[git]
user_name = "Imbi Automations"
user_email = "automations@imbi.ai"

# GitHub API Configuration
[github]
token = "ghp_your_github_token"
host = "github.com"

# Imbi Project Management Configuration
[imbi]
api_key = "your-imbi-api-key"
hostname = "imbi.example.com"
github_identifier = "github"
github_link = "GitHub Repository"
```

## Global Settings

### ai_commits

Enable AI-powered commit message generation.

**Type:** `boolean`  
**Default:** `false`  

When enabled, uses Anthropic API to generate commit messages based on changes.

```toml
ai_commits = true
```

### error_dir

Directory to store error logs and debugging information when workflows fail.

**Type:** `path`  
**Default:** `./errors`  

```toml
error_dir = "/var/log/imbi-automations/errors"
```

### preserve_on_error

Preserve working directories when errors occur for debugging.

**Type:** `boolean`  
**Default:** `false`  

When `true`, temporary directories are not cleaned up after failures, allowing manual inspection.

```toml
preserve_on_error = true
```

### dry_run

Execute workflows without pushing changes or creating pull requests.

**Type:** `boolean`  
**Default:** `false`  

When enabled, workflows execute completely (clone, actions, commits) but skip remote operations:

```toml
dry_run = true
```

**Behavior:**

✓ Clones repositories  
✓ Runs all actions  
✓ Makes file changes  
✓ Creates commits locally  
✗ Skips pushing to remote  
✗ Skips creating pull requests  

**Use Cases:**

- Testing new workflows safely
- Validating changes before production runs
- Reviewing commit messages and diffs
- Training and demonstration
- CI/CD validation pipelines

Working directories are preserved to `dry_run_dir` for inspection.

**Note:** Can be overridden by `--dry-run` CLI flag.  

### dry_run_dir

Directory for saving repository state during dry-run executions.

**Type:** `path`  
**Default:** `./dry-runs`  

```toml
dry_run_dir = "./review-changes"
```

**Directory Structure:**  
```
./review-changes/
└── workflow-name/
    └── project-slug-timestamp/
        ├── repository/    # Full git repository with commits
        ├── workflow/      # Workflow files and templates
        └── extracted/     # Docker extracted files (if any)
```

**Example Inspection:**  
```bash
# View commits that would have been pushed
cd ./dry-runs/update-deps/my-project-20250103-143052/repository
git log -1
git show HEAD
git diff HEAD~1
```

**Note:** Can be overridden by `--dry-run-dir` CLI flag.  

## Anthropic Configuration

Configuration for Anthropic Claude API used in Claude actions and AI commit generation.

### [anthropic].api_key

Anthropic API key for Claude models.

**Type:** `string` (secret)  
**Default:** `$ANTHROPIC_API_KEY` environment variable  
**Required:** For Claude actions or `ai_commits = true`  

```toml
[anthropic]
api_key = "sk-ant-api03-..."
```

Or use environment variable:
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

### [anthropic].bedrock

Use AWS Bedrock instead of direct Anthropic API.

**Type:** `boolean`  
**Default:** `false`  

```toml
[anthropic]
bedrock = true
```

**Note:** Requires AWS credentials configured separately.  

### [anthropic].model

Claude model to use for API requests.

**Type:** `string`  
**Default:** `claude-haiku-4-5-20251001`  

```toml
[anthropic]
model = "claude-opus-4-5"
```

## Claude Configuration

Configuration for Claude Agent SDK integration.

### [claude].executable

Path or command name for Claude Code executable.

**Type:** `string`
**Default:** `claude`

```toml
[claude]
executable = "/usr/local/bin/claude"
```

### [claude].enabled

Enable Claude Code actions in workflows.

**Type:** `boolean`
**Default:** `true`

Set to `false` to disable all Claude actions:

```toml
[claude]
enabled = false
```

### [claude].model

Claude model to use for Claude Code SDK operations.

**Type:** `string`
**Default:** `claude-haiku-4-5`
**Environment Variable:** `CLAUDE_MODEL`

```toml
[claude]
model = "claude-sonnet-4-5"
```

Available models include:

- `claude-haiku-4-5` - Fast, cost-effective (default)
- `claude-sonnet-4-5` - Balanced performance
- `claude-opus-4-5` - Most capable

### [claude].base_prompt

Custom base prompt file for Claude Code sessions.

**Type:** `path`
**Default:** `src/imbi_automations/prompts/claude.md`

```toml
[claude]
base_prompt = "/path/to/custom-prompt.md"
```

### [claude].plugins

Plugin and marketplace configuration for Claude Code. These settings are merged with workflow-level plugin settings (workflow values take precedence).

**Type:** `ClaudePluginConfig` object
**Default:** Empty (no plugins)

#### [claude.plugins].enabled_plugins

Enable or disable specific plugins from marketplaces.

**Type:** `dict[string, boolean]`  
**Format:** `plugin-name@marketplace-name" = true/false`  

```toml
[claude.plugins.enabled_plugins]
"git-repository@aweber-marketplace" = true
"python-developer@aweber-marketplace" = true
"grafana-mcp@aweber-marketplace" = false
```

#### [claude.plugins.marketplaces]

Configure additional marketplace sources for plugins.

**Type:** `dict[string, ClaudeMarketplace]`  

Each marketplace requires a `source` type and corresponding field:

| Source Type | Required Field | Description |
|-------------|----------------|-------------|
| `github` | `repo` | GitHub repository (e.g., `org/repo`) |
| `git` | `url` | Any git URL |
| `directory` | `path` | Local directory (development only) |

```toml
# GitHub marketplace
[claude.plugins.marketplaces.company-tools]
source = "github"
repo = "company-org/claude-plugins"

# Git URL marketplace (e.g., GitHub Enterprise)
[claude.plugins.marketplaces.enterprise-tools]
source = "git"
url = "https://github.enterprise.com/org/claude-plugins.git"

# Local directory (development)
[claude.plugins.marketplaces.dev-plugins]
source = "directory"
path = "/path/to/local/marketplace"
```

#### [[claude.plugins.local_plugins]]

Load local plugin directories directly via the Claude Agent SDK.

**Type:** `list[ClaudeLocalPlugin]`  

```toml
[[claude.plugins.local_plugins]]
path = "/path/to/local/plugin"

[[claude.plugins.local_plugins]]
path = "/another/plugin/directory"
```

#### Complete Plugin Configuration Example

```toml
[claude]
enabled = true
model = "claude-sonnet-4-5"

[claude.plugins.enabled_plugins]
"git-repository@aweber-marketplace" = true
"python-developer@aweber-marketplace" = true
"grafana-mcp@aweber-marketplace" = false

[claude.plugins.marketplaces.aweber-marketplace]
source = "git"
url = "https://github.enterprise.com/claude/marketplace.git"

[claude.plugins.marketplaces.community]
source = "github"
repo = "anthropics/claude-plugins"

[[claude.plugins.local_plugins]]
path = "/home/user/my-custom-plugin"
```

## Git Configuration

Configuration for git commit operations.

### [git].user_name

Git commit author name.

**Type:** `string`
**Default:** `Imbi Automations`

```toml
[git]
user_name = "Bot User"
```

### [git].user_email

Git commit author email address.

**Type:** `string`
**Default:** `automations@imbi.ai`

```toml
[git]
user_email = "bot@example.com"
```

### [git].gpg_sign

Enable GPG signing for commits.

**Type:** `boolean`
**Default:** `false`

```toml
[git]
gpg_sign = true
signing_key = "ABCD1234..."
```

### [git].gpg_format

GPG signing format.

**Type:** `string`
**Default:** `null`
**Options:** `gpg`, `ssh`, `x509`, `openpgp`

```toml
[git]
gpg_format = "ssh"
```

### [git].signing_key

GPG or SSH signing key identifier.

**Type:** `string`
**Default:** `null`

```toml
[git]
signing_key = "~/.ssh/id_ed25519.pub"
```

### [git].ssh_program

SSH program for commit signing (for SSH signing with 1Password, etc.).

**Type:** `string`
**Default:** `null`

```toml
[git]
gpg_format = "ssh"
ssh_program = "/Applications/1Password.app/Contents/MacOS/op-ssh-sign"
```

### [git].gpg_program

GPG program path for traditional GPG signing.

**Type:** `string`
**Default:** `null`

```toml
[git]
gpg_sign = true
gpg_program = "/usr/local/bin/gpg"
```

### [git].commit_args

Additional arguments to pass to git commit commands.

**Type:** `string`
**Default:** `""`

```toml
[git]
commit_args = "--no-verify"
```

## GitHub Configuration

Configuration for GitHub API integration.

### [github].token

GitHub personal access token or fine-grained token.

**Type:** `string` (secret)
**Required:** For GitHub workflows

**Token Permissions Required:**

- `repo` - Full repository access
- `workflow` - Update GitHub Actions workflows
- `admin:org` - Manage organization (for environment sync)

```toml
[github]
token = "ghp_your_github_personal_access_token"
```

### [github].host

GitHub hostname for Enterprise installations.

**Type:** `string`
**Default:** `github.com`

For GitHub Enterprise:
```toml
[github]
host = "github.enterprise.com"
```

## Imbi Configuration

Configuration for Imbi project management system integration.

### [imbi].api_key

Imbi API authentication key.

**Type:** `string` (secret)  
**Required:** Always (core functionality)  

```toml
[imbi]
api_key = "your-imbi-api-key-uuid"
```

### [imbi].hostname

Imbi instance hostname.

**Type:** `string`  
**Required:** Always  

```toml
[imbi]
hostname = "imbi.example.com"
```

### [imbi].*_identifier

Project identifier field names in Imbi for external systems.

**Type:** `string`  
**Defaults:**  

- `github_identifier = "github`
- `pagerduty_identifier = "pagerduty`
- `sonarqube_identifier = "sonarqube`
- `sentry_identifier = "sentry`

These specify which Imbi project identifier fields contain external system references:

```toml
[imbi]
github_identifier = "github-id"
```

### [imbi].*_link

Link type names in Imbi for external system URLs.

**Type:** `string`  
**Defaults:**  

- `github_link = "GitHub Repository`
- `grafana_link = "Grafana Dashboard`
- `pagerduty_link = "PagerDuty`
- `sentry_link = "Sentry`
- `sonarqube_link = "SonarQube`

These specify the link type names used in Imbi to store external URLs:

```toml
[imbi]
github_link = "GitHub Repo"
```

## Imbi Metadata Cache

The ImbiMetadataCache system caches Imbi metadata locally for improved performance and parse-time validation.

### Cache Location

**Path:** `~/.cache/imbi-automations/metadata.json` (configurable via `cache_dir` setting or `--cache-dir` CLI option)  

**TTL:** 15 minutes  

**Contents:**  

- Environments
- Project type slugs and IDs
- Fact type definitions with enums and ranges
- Enum values for fact validation

### Cache Behavior

The metadata cache is automatically managed and safe by default:

- **First run**: Fetches all metadata from Imbi API
- **Subsequent runs**: Uses cached data if less than 15 minutes old
- **Expired cache**: Auto-refreshes from API
- **Validation**: Enables parse-time validation of workflow filters
- **Uninitialized**: Returns empty collections (graceful degradation)

### Configuring Cache Location

Override the default cache directory in configuration:

```toml
# Optional: Override cache directory
cache_dir = "/custom/path/to/cache"
```

Or via CLI option:

```bash
imbi-automations config.toml workflows/workflow-name \
  --cache-dir /tmp/imbi-cache \
  --all-projects
```

### Manual Cache Management

```bash
# View cache location
ls -lah ~/.cache/imbi-automations/

# Clear cache (forces refresh on next run)
rm ~/.cache/imbi-automations/metadata.json

# View cache contents
cat ~/.cache/imbi-automations/metadata.json | jq .
```

### Benefits

- **Parse-time validation**: Catches typos in `project_types` and `project_facts` before workflow execution
- **Fuzzy suggestions**: Provides helpful suggestions for misspelled values
- **Reduced API calls**: Avoids repeated metadata fetches
- **Fast filter validation**: Instant validation without network calls

## Environment Variables

All configuration sections support automatic environment variable loading via Pydantic Settings. Each section has a prefix:

| Section | Prefix | Example Variable |
|---------|--------|------------------|
| `[anthropic]` | `ANTHROPIC_` | `ANTHROPIC_API_KEY` |
| `[claude]` | `CLAUDE_` | `CLAUDE_MODEL` |
| `[git]` | `GIT_` | `GIT_USER_NAME` |
| `[github]` | `GH_` | `GH_TOKEN` |
| `[imbi]` | `IMBI_` | `IMBI_API_KEY` |

For a complete reference of all available environment variables, see [Environment Variables](environment-variables.md).

### Quick Example

```bash
# Set required environment variables
export GH_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
export IMBI_API_KEY="your-api-key-uuid"
export IMBI_HOSTNAME="imbi.example.com"
```

Then use empty sections in your config to load from environment:

```toml
[github]
[imbi]
```

## Minimal Configuration

The absolute minimum configuration for basic GitHub workflows:

```toml
[github]
token = "ghp_your_token"

[imbi]
api_key = "your-imbi-key"
hostname = "imbi.example.com"
```

## Configuration Validation

Configuration is validated at startup using Pydantic. Common errors:

### Missing Required Fields

```
ValidationError: 1 validation error for Configuration
github.token
  field required (type=value_error.missing)
```

**Solution:** Add the required field to your config.toml

### Invalid Token Format

```
ValidationError: 1 validation error for Configuration
github.token
  string does not match regex (type=value_error.str.regex)
```

**Solution:** Check API key format and validity

### Invalid Hostname

```
ValidationError: 1 validation error for Configuration
imbi.hostname
  invalid hostname (type=value_error.url.host)
```

**Solution:** Use valid hostname without protocol (no `https://`)

## Security Best Practices

### API Key Storage

**DO NOT** commit API keys to version control:

```toml
# ❌ BAD - Keys in config file
[github]
token = "ghp_actual_key_here"

# ✅ GOOD - Environment variables
[github]
token = "${GITHUB_TOKEN}"
```

### File Permissions

Restrict config file permissions:

```bash
chmod 600 config.toml
```

### Environment Variables

Set sensitive values via environment:

```bash
export GITHUB_TOKEN="ghp_..."
export ANTHROPIC_API_KEY="sk-ant-..."
export IMBI_API_KEY="uuid-here"

imbi-automations config.toml workflows/workflow-name --all-projects
```

### Separate Configurations

Use different config files for different environments:

```bash
# Development
imbi-automations config.dev.toml workflows/test

# Production
imbi-automations config.prod.toml workflows/deploy
```

## Configuration Examples

### GitHub Only Workflows

```toml
[git]
user_name = "GitHub Bot"
user_email = "bot@example.com"

[github]
token = "${GITHUB_TOKEN}"

[imbi]
api_key = "${IMBI_API_KEY}"
hostname = "imbi.example.com"
```

### GitHub Enterprise

```toml
[github]
token = "${GITHUB_ENTERPRISE_TOKEN}"
host = "github.enterprise.com"

[imbi]
api_key = "${IMBI_API_KEY}"
hostname = "imbi.example.com"
```

### With AI Features

```toml
ai_commits = true

[anthropic]
api_key = "${ANTHROPIC_API_KEY}"
model = "claude-sonnet-4-5-20250514"

[claude]
enabled = true
model = "claude-sonnet-4-5"

[github]
token = "${GITHUB_TOKEN}"

[imbi]
api_key = "${IMBI_API_KEY}"
hostname = "imbi.example.com"
```

### With Debugging

```toml
preserve_on_error = true
error_dir = "/tmp/imbi-errors"

[github]
token = "${GITHUB_TOKEN}"

[imbi]
api_key = "${IMBI_API_KEY}"
hostname = "imbi.example.com"
```

### With Dry Run Mode

```toml
# Enable dry-run globally for safe testing
dry_run = true
dry_run_dir = "./review-changes"

[github]
token = "${GITHUB_TOKEN}"

[imbi]
api_key = "${IMBI_API_KEY}"
hostname = "imbi.example.com"
```

All workflows will execute but skip pushing and PR creation. Review changes in `./review-changes/` before disabling dry-run mode.

## Troubleshooting

### Configuration Not Loading

**Problem:** `FileNotFoundError: config.toml not found`

**Solution:** Provide full path to config file:
```bash
imbi-automations /path/to/config.toml workflows/name --all-projects
```

### Authentication Failures

**Problem:** `401 Unauthorized` errors

**Solutions:**  
1. Verify API key is valid and not expired
2. Check API key has required permissions
3. Ensure environment variables are exported
4. Test API access manually with curl

### Invalid TOML Syntax

**Problem:** `toml.decoder.TomlDecodeError`

**Solutions:**  
1. Validate TOML syntax with online validator
2. Check for missing quotes around strings
3. Verify section headers use `[section]` format
4. Ensure key-value pairs use `key = "value` format

## Advanced Configuration

### Custom Error Directory Structure

```toml
error_dir = "/var/log/imbi-automations/errors"
```

Creates:
```
/var/log/imbi-automations/errors/
└── workflow-name/
    └── project-slug-timestamp/
        ├── repository/
        ├── workflow/
        └── error.log
```

### Custom Git Author Per Workflow

Set in workflow config.toml instead:

```toml
# workflows/my-workflow/config.toml
[git]
user_name = "Workflow Bot"
user_email = "workflow@example.com"
```

Overrides global git author settings for that workflow only.

## See Also

- [Environment Variables](environment-variables.md) - Complete environment variable reference
- [Workflow Actions](actions/index.md) - Complete action configuration reference
- [Architecture](architecture.md) - System design and components
- [GitHub Actions](actions/github.md) - GitHub-specific configuration
- [Claude Actions](actions/claude.md) - AI transformation configuration
