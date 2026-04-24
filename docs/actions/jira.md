# Jira Actions

Jira actions create tickets in Jira Cloud via an agentic Claude session. The
action invokes Claude Agent SDK with a configurable task prompt and an
in-process MCP tool that posts to the Jira Cloud REST v3 API. Claude authors
the ticket summary and description; the workflow config supplies the
project, issue type, labels, and components — Claude cannot override those.

Typical use case: a workflow runs an in-depth review (security, dependency,
compliance) and needs to file a human-readable ticket summarising findings.

## Configuration

```toml
[jira]
# Reads ATLASSIAN_DOMAIN, ATLASSIAN_EMAIL, ATLASSIAN_API_KEY from env by
# default. Any of these may also be set here explicitly.
# domain = "example.atlassian.net"
# email = "you@example.com"
# api_key = "..."

[[actions]]
name = "action-name"
type = "jira"
command = "create_ticket"  # Required
```

The `[jira]` section is optional if the environment variables are set.

### Authentication

Uses Jira Cloud Basic auth (email + API token). Environment variable names
are shared with other Atlassian tools to avoid duplication:

- `ATLASSIAN_DOMAIN` — e.g. `example.atlassian.net` (no scheme)
- `ATLASSIAN_EMAIL` — the account email
- `ATLASSIAN_API_KEY` — API token from
  <https://id.atlassian.com/manage-profile/security/api-tokens>

## Available Commands

### create_ticket

Creates a Jira ticket driven by a Claude Agent SDK session.

**Configuration:**
```toml
[[actions]]
name = "file-security-findings"
type = "jira"
command = "create_ticket"
project_key = "SEC"
issue_type = "Task"
labels = ["security-review", "automated", "{{ imbi_project.slug }}"]
components = ["Application Security"]
priority = "High"
prompt = "workflow:///prompts/file-security-ticket.md.j2"
max_cycles = 3
timeout = "5m"
variable_name = "ticket"
```

**Fields:**

- `project_key` (string, required): Jira project key (e.g. `"SEC"`).
- `prompt` (ResourceUrl, required): Path to a Jinja2 template with the task
  prompt for Claude. Receives full workflow context (`workflow`,
  `imbi_project`, `github_repository`, `variables`, `starting_commit`) plus
  action-config passthroughs (`project_key`, `issue_type`, `labels`,
  `components`, `priority`).
- `issue_type` (string, optional, default `"Task"`): Jira issue type name.
- `labels` (list of strings, optional): Labels to attach. List entries
  support Jinja2 templates.
- `components` (list of strings, optional): Component names to attach. Must
  already exist in the Jira project; the action does not create them.
- `priority` (string, optional): Priority name (e.g. `"High"`).
- `variable_name` (string, optional): If set, stores a dict of the created
  ticket under `context.variables[variable_name]` with keys `id`, `key`,
  `url` (REST API URL), and `browse_url` (human-facing link). Downstream
  actions can reference these via `{{ variables.<name>.browse_url }}`.
- `max_cycles` (integer, optional, default `3`): Number of attempts. If the
  Jira API rejects the first attempt (e.g., summary too long), the error is
  surfaced to Claude in the retry prompt so it can revise and try again.
- `timeout` (Go-duration string, optional, default `"5m"`): Per-cycle
  timeout.

**Features:**

- **Agentic authoring**: Claude reads the prompt and any available skills
  (including marketplace-packaged ones), then composes the ticket
  summary/description itself.
- **Markdown descriptions**: The client accepts a plain-text or markdown
  description and wraps it into a minimal Atlassian Document Format (ADF)
  envelope. Workflow authors never hand-author ADF.
- **Fixed metadata**: `project_key`, `issue_type`, `labels`, `components`,
  and `priority` come from the workflow config and are injected by the
  tool closure. The agent cannot change them.
- **Narrow tool surface**: The session allows only `Read`, `Skill`, and the
  `create_jira_issue` MCP tool. The agent cannot touch the repository or
  call other tools.
- **Non-committable**: Does not create git commits.
- **Retry on API errors**: Jira 4xx responses are surfaced to Claude in the
  next cycle's prompt; content-shape errors (summary too long, invalid
  markdown formatting) can often self-heal. Config errors (bad
  `project_key`, missing component) will exhaust cycles and fail.

**Use Cases:**

- File a ticket summarising AI-generated security-review findings.
- Open a tracking issue for a migration that requires human follow-up.
- Escalate automation failures that need human triage.

**Example — linking the created ticket back to the project:**

```toml
[[actions]]
name = "file-ticket"
type = "jira"
command = "create_ticket"
project_key = "SEC"
issue_type = "Task"
labels = ["security-review"]
components = ["Application Security"]
prompt = "workflow:///prompts/security-ticket.md.j2"
variable_name = "ticket"

[[actions]]
name = "link-ticket-on-project"
type = "imbi"
command = "add_project_link"
link_type = "Issue Tracker"
url = "{{ variables.ticket.browse_url }}"
```

**Prompt template context (`prompts/security-ticket.md.j2`):**

```markdown
# File a security-review ticket

You must call `create_jira_issue` exactly once. Use the skill available
for guidance on how to write a good ticket.

## Context

- Project: {{ imbi_project.name }} ({{ imbi_project.slug }})
- Repository: {{ github_repository.full_name if github_repository else 'n/a' }}
- Labels to apply: {{ labels | join(', ') }}
- Components to apply: {{ components | join(', ') }}

## Findings to summarise

{{ variables.security_findings }}

## Required

- `summary`: one line, plain text, < 120 chars.
- `description`: markdown; use paragraphs separated by blank lines.
```

## Skill and plugin loading

Claude-Code skills are loaded through the existing plugin mechanism. To make
a Jira-writing skill available to the action:

1. Package it as a plugin in a marketplace.
2. Configure the marketplace in the main `config.toml` or the workflow
   `workflow.toml` under `[claude_code.plugins]` / `[plugins]`.
3. Enable the plugin.

The Jira action shares the same plugin-install path as the `claude` action,
so plugins installed by an earlier `claude` action in the same workflow are
reused for free.

## Error handling

- **Missing Jira config**: `ValueError` at action start.
- **Jira API 4xx**: surfaced to Claude in the next cycle's prompt. If
  `max_cycles` exhausts without a successful `create_jira_issue` call, the
  action raises `RuntimeError`.
- **Timeout**: per-cycle timeout; raises `RuntimeError` wrapping a
  `TimeoutError`.

Standard workflow error handling applies: attach an `on_error` action or
define an `error_filter` with `stage = "on_error"` to recover.

## Out of scope (future commands)

The following are intentionally not part of the first release. Expect
dedicated commands in follow-up work:

- `add_comment` — append a comment to an existing issue.
- `transition_ticket` — change an issue's workflow state.
- `link_issue` — create issue-to-issue links.
- Assignee/reporter selection — current action cannot set either.
- Attachments — not supported.
- Custom-field writes beyond what's exposed via `labels`, `components`,
  and `priority`.
