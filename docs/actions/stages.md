# Action Stages

Action stages allow workflows to execute actions in distinct phases, enabling powerful patterns like CI monitoring, automated feedback response, and iterative fixes.

## Overview

Actions support a `stage` field with two values:

| Stage | Execution Time | Use Case |
|-------|---------------|----------|
| `primary` (default) | Before PR creation | Standard workflow actions - code changes, file updates |
| `followup` | After PR creation | CI monitoring, reviewer feedback, automated fixes |

## Execution Flow

```
1. Setup working directory
2. Check conditions, clone repository
3. Execute PRIMARY stage actions (with commits)
4. Create PR or push changes
5. Execute FOLLOWUP stage actions (with cycling)
6. Cleanup
```

### Primary Stage

Primary actions execute sequentially before any PR is created:

```toml
[[actions]]
name = "update-dependencies"
type = "claude"
# stage = "primary"  # Default, can be omitted
task_prompt = "prompts/update-deps.md.j2"

[[actions]]
name = "run-tests"
type = "shell"
command = "pytest tests/"
```

- Execute in order defined in workflow
- Each action can commit changes
- PR created after all primary actions complete

### Followup Stage

Followup actions execute after the PR is created:

```toml
[[actions]]
name = "monitor-ci"
type = "claude"
stage = "followup"
task_prompt = "prompts/monitor-ci.md.j2"
committable = true  # Can commit fixes
```

**Followup Behavior:**  

1. All followup actions execute in sequence
2. If any action commits, changes push to PR branch
3. If commits were made, followup stage cycles again
4. Cycles continue until no commits or max cycles reached
5. If max cycles reached, workflow fails

## Configuration

### Workflow-Level Settings

```toml
name = "update-and-monitor"

# Maximum followup cycles (default: 5)
max_followup_cycles = 3

[github]
create_pull_request = true
```

### Action-Level Settings

```toml
[[actions]]
name = "monitor-ci"
type = "claude"
stage = "followup"           # Execute after PR creation
task_prompt = "prompts/monitor.md.j2"
committable = true           # Allow commits (enables cycling)
ai_commit = true             # AI-generated commit messages
```

## Template Context

Followup actions receive additional context variables:

### `pull_request` (GitHubPullRequest)

Full PR model with fields:

```jinja2
PR Number: {{ pull_request.number }}
PR URL: {{ pull_request.html_url }}
PR State: {{ pull_request.state }}
Head SHA: {{ pull_request.head.sha }}
Head Ref: {{ pull_request.head.ref }}
Base Ref: {{ pull_request.base.ref }}
Mergeable: {{ pull_request.mergeable }}
Mergeable State: {{ pull_request.mergeable_state }}
```

### `pr_branch` (str)

Branch name for the PR:

```jinja2
Branch: {{ pr_branch }}
```

### Example Followup Prompt

```markdown
# Monitor CI and Fix Issues

You are monitoring PR #{{ pull_request.number }} in {{ github_repository.full_name }}.

**PR URL:** {{ pull_request.html_url }}
**Branch:** {{ pr_branch }}
**Head SHA:** {{ pull_request.head.sha }}

## Your Task

1. Check GitHub Actions workflow status for this PR
2. If CI is still running, report status and wait
3. If CI passed, report success (no changes needed)
4. If CI failed:
   - Analyze failure logs
   - Identify root cause
   - Make targeted fixes
   - Commit changes

Use `gh` CLI to check workflow status:
```bash
gh run list --branch {{ pr_branch }} --limit 1
gh run view <run-id> --log-failed
```

If you make fixes, ensure they are minimal and targeted.
```

## Use Cases

### 1. CI Monitoring

Monitor GitHub Actions and fix failures:

```toml
[[actions]]
name = "update-code"
type = "claude"
task_prompt = "prompts/update.md.j2"

[[actions]]
name = "monitor-ci"
type = "claude"
stage = "followup"
task_prompt = "prompts/monitor-ci.md.j2"
committable = true
max_cycles = 5
```

### 2. Reviewer Feedback Response

Respond to automated code review comments:

```toml
[[actions]]
name = "refactor-code"
type = "claude"
task_prompt = "prompts/refactor.md.j2"

[[actions]]
name = "respond-to-feedback"
type = "claude"
stage = "followup"
task_prompt = "prompts/respond-feedback.md.j2"
committable = true
```

### 3. Test Verification

Wait for tests and fix any failures:

```toml
[[actions]]
name = "migrate-dependencies"
type = "claude"
task_prompt = "prompts/migrate.md.j2"

[[actions]]
name = "verify-tests"
type = "claude"
stage = "followup"
task_prompt = "prompts/verify-tests.md.j2"
committable = true
max_cycles = 3
```

## Cycling Behavior

### When Cycling Occurs

Followup stage cycles when:

1. A followup action with `committable = true` creates a commit
2. The commit is pushed to the PR branch
3. The stage restarts from the first followup action

### Cycle Completion

A cycle completes successfully when:

- All followup actions execute without error
- No commits are made during the cycle

### Max Cycles

If `max_followup_cycles` is reached:

- Workflow fails with RuntimeError
- Error message indicates max cycles exceeded
- `preserve_on_error` can save state for debugging

```toml
max_followup_cycles = 3  # Fail after 3 cycles with commits
```

## Error Handling

### Primary Stage Failure

If a primary action fails:

- Followup stage is skipped entirely
- Normal error handling applies
- `preserve_on_error` saves state

### Followup Stage Failure

If a followup action fails:

- Workflow fails immediately
- `preserve_on_error` saves state
- PR remains open for manual intervention

### Dry-Run Mode

In `--dry-run` mode:

- Primary actions execute normally
- Followup actions are skipped (no PR exists)
- Warning logged about skipped followup actions

## Best Practices

### 1. Keep Followup Actions Focused

Each followup action should have a single responsibility:

```toml
# Good: Focused actions
[[actions]]
name = "check-ci-status"
stage = "followup"

[[actions]]
name = "fix-lint-errors"
stage = "followup"

# Avoid: Monolithic actions
[[actions]]
name = "monitor-everything"  # Too broad
stage = "followup"
```

### 2. Set Reasonable Max Cycles

Balance automation with safety:

```toml
# Too low: May not complete complex fixes
max_followup_cycles = 1

# Too high: May loop indefinitely on unfixable issues
max_followup_cycles = 20

# Good: Reasonable limit with room for iteration
max_followup_cycles = 5
```

### 3. Use Conditional Commits

Only commit when changes are actually needed:

```markdown
## Instructions

1. Check CI status
2. If all checks pass, report success (no commit needed)
3. Only commit if you made actual fixes
```

### 4. Provide Clear Exit Conditions

Define when followup should stop:

```markdown
## Success Criteria

- All CI checks pass
- No open review comments
- Tests pass

## When to Stop

Return without committing if:
- CI is passing
- No actionable feedback exists
```

## Complete Example

```toml
name = "Update Python Version with CI Monitoring"
description = "Update Python version and monitor CI for failures"
max_followup_cycles = 5

[filter]
project_types = ["api"]
project_facts = {"Programming Language" = "Python 3.11"}

[github]
create_pull_request = true

# Primary stage: Make changes
[[actions]]
name = "update-python-version"
type = "claude"
task_prompt = "prompts/update-python.md.j2"
validation_prompt = "prompts/validate-update.md.j2"

# Followup stage: Monitor and fix
[[actions]]
name = "monitor-ci"
type = "claude"
stage = "followup"
task_prompt = "prompts/monitor-ci.md.j2"
committable = true
ai_commit = true

[[actions]]
name = "respond-to-reviews"
type = "claude"
stage = "followup"
task_prompt = "prompts/respond-reviews.md.j2"
committable = true
ai_commit = true
```

## See Also

- [Workflow Configuration](../workflow-configuration.md) - `max_followup_cycles` setting
- [Claude Actions](claude.md) - AI-powered transformations
- [Templating](../templating.md) - PR context variables
- [Workflows](../workflows.md) - Workflow overview
