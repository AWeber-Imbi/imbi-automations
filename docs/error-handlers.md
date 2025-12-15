# Error Recovery Actions

Error recovery actions provide automated failure handling within workflows. When an action fails, the workflow engine can invoke recovery actions that diagnose issues, apply fixes, and optionally retry the failed operation.

**Tip:** Error handlers use `stage = "on_error"` and can be attached to specific actions or globally with filters.

## Overview

Error recovery supports two attachment mechanisms:

1. **Action-specific handlers**: Attached via `on_error` field to individual actions
2. **Global handlers**: Attached via `error_filter` to match failed actions by type, stage, or exception

After successful recovery, handlers can:

- **Retry** the failed action (up to a configurable limit)
- **Skip** to the next action (continue workflow)
- **Fail** the workflow (for cleanup-only handlers)

## Quick Example

```toml
[[actions]]
name = "run-tests"
type = "shell"
command = "pytest tests/"
on_error = "cleanup-and-retry"

[[actions]]
name = "cleanup-and-retry"
type = "shell"
stage = "on_error"
recovery_behavior = "retry"
max_retry_attempts = 2
command = """
rm -rf .pytest_cache __pycache__
pip install --force-reinstall -e .
"""
```

When `run-tests` fails, `cleanup-and-retry` executes, cleans up state, and retries the tests up to 2 times.

## Configuration

### stage (required for error handlers)

Must be set to `"on_error"` to designate an action as an error handler.

**Type:** `string`

**Valid values:** `"on_error"`

```toml
[[actions]]
name = "my-error-handler"
type = "shell"
stage = "on_error"
command = "echo 'Handling error'"
```

### recovery_behavior

Determines what happens after the error handler executes successfully.

**Type:** `string`

**Default:** `"skip"`

**Valid values:**

- `"retry"`: Re-execute the failed action (respects `max_retry_attempts`)
- `"skip"`: Continue to the next action after recovery
- `"fail"`: Fail the workflow (useful for cleanup-only handlers)

```toml
[[actions]]
name = "diagnostic-handler"
type = "claude"
stage = "on_error"
recovery_behavior = "retry"
task_prompt = "prompts/diagnose-and-fix.md.j2"
```

### max_retry_attempts

Maximum number of times to retry the failed action when `recovery_behavior = "retry"`.

**Type:** `integer`

**Default:** `3`

**Note:** After exhausting retries, the workflow fails.

```toml
[[actions]]
name = "persistent-handler"
type = "shell"
stage = "on_error"
recovery_behavior = "retry"
max_retry_attempts = 5
command = "scripts/reset-environment.sh"
```

### error_filter

Filter specification for global error handlers. Defines which failed actions this handler matches.

**Type:** `object`

**Default:** `None` (must be specified for global handlers)

**Fields:**

- `action_types`: List of action types to match (`["claude", "shell"]`)
- `action_names`: List of action names to match (`["deploy", "test"]`)
- `stages`: List of stages to match (`["primary", "followup"]`)
- `exception_types`: List of exception class names (`["TimeoutError"]`)
- `exception_message_contains`: Text that must be present in exception message (e.g., `"ruff.....Failed"`)
- `condition`: Custom Jinja2 expression (advanced)

```toml
[[actions]]
name = "handle-claude-timeouts"
type = "shell"
stage = "on_error"
recovery_behavior = "skip"
command = "echo 'Claude action timed out, continuing...'"

[actions.error_filter]
action_types = ["claude"]
exception_types = ["TimeoutError", "asyncio.TimeoutError"]
```

**Filter matching:** All specified filters must match for the handler to trigger.

## Attachment Mechanisms

### Action-Specific Handlers

Attach handlers to specific actions using the `on_error` field.

```toml
[[actions]]
name = "deploy-service"
type = "shell"
command = "kubectl apply -f deployment.yaml"
on_error = "rollback-deployment"

[[actions]]
name = "rollback-deployment"
type = "shell"
stage = "on_error"
recovery_behavior = "fail"
command = """
kubectl rollout undo deployment/my-service
kubectl wait --for=condition=available deployment/my-service
"""
```

**Priority:** Action-specific handlers always take precedence over global handlers.

### Global Handlers with Filters

Global handlers match failed actions based on filter criteria.

**Match by action type:**

```toml
[[actions]]
name = "handle-git-failures"
type = "shell"
stage = "on_error"
recovery_behavior = "skip"
command = "git reset --hard HEAD"

[actions.error_filter]
action_types = ["git"]
```

**Match by stage:**

```toml
[[actions]]
name = "followup-error-reporter"
type = "template"
stage = "on_error"
recovery_behavior = "fail"
source = "workflow:///templates/error-report.md.j2"
destination = "ERROR_REPORT.md"

[actions.error_filter]
stages = ["followup"]
```

**Match by exception type:**

```toml
[[actions]]
name = "timeout-handler"
type = "claude"
stage = "on_error"
recovery_behavior = "skip"
task_prompt = "workflow:///prompts/timeout-diagnosis.md.j2"

[actions.error_filter]
exception_types = ["TimeoutError", "asyncio.TimeoutError"]
```

**Combine multiple filters:**

```toml
[[actions]]
name = "primary-claude-timeout-handler"
type = "shell"
stage = "on_error"
recovery_behavior = "retry"
max_retry_attempts = 1
command = "echo 'Retrying Claude action after timeout'"

[actions.error_filter]
action_types = ["claude"]
stages = ["primary"]
exception_types = ["TimeoutError"]
```

## Template Variables

Error handlers have access to special template variables describing the failure:

| Variable | Type | Description |
|----------|------|-------------|
| `failed_action` | `object` | The failed action object (includes `.name`, `.type`) |
| `exception` | `string` | Exception message |
| `exception_type` | `string` | Exception class name |
| `retry_attempt` | `integer` | Current retry attempt (1-indexed) |
| `max_retries` | `integer` | Maximum retry attempts configured |

**Example prompt template:**

```markdown
# Diagnose and Fix Error

Action "{{ failed_action.name }}" (type: {{ failed_action.type }}) failed:

**Error:** {{ exception }}
**Type:** {{ exception_type }}
**Retry:** {{ retry_attempt }}/{{ max_retries }}

Analyze the error and make targeted fixes. If the issue is environmental
(missing dependencies, API limits, network issues), explain the problem
so the workflow can fail gracefully.
```

## Use Cases and Patterns

### 1. AI-Powered Error Diagnosis

Use Claude to analyze and fix errors automatically.

```toml
[[actions]]
name = "migrate-codebase"
type = "claude"
task_prompt = "prompts/migration.md.j2"
max_cycles = 5
on_error = "ai-diagnose-and-fix"

[[actions]]
name = "ai-diagnose-and-fix"
type = "claude"
stage = "on_error"
recovery_behavior = "retry"
max_retry_attempts = 3
task_prompt = "prompts/error-diagnosis.md.j2"
max_cycles = 2
```

### 2. Environment Reset and Retry

Reset state before retrying flaky operations.

```toml
[[actions]]
name = "integration-tests"
type = "shell"
command = "pytest tests/integration/"
on_error = "reset-test-environment"

[[actions]]
name = "reset-test-environment"
type = "shell"
stage = "on_error"
recovery_behavior = "retry"
max_retry_attempts = 2
command = """
docker-compose down -v
docker-compose up -d
sleep 10
"""
```

### 3. Pre-commit Hook Auto-fix

Auto-fix lint/format issues caught by pre-commit hooks.

```toml
[[actions]]
name = "update-code"
type = "claude"
task_prompt = "prompts/update.md.j2"
committable = true

[[actions]]
name = "fix-precommit-errors"
type = "shell"
stage = "on_error"
recovery_behavior = "retry"
max_retry_attempts = 1
command = """
cd repository
ruff check --fix --unsafe-fixes .
ruff format .
"""

[actions.error_filter]
exception_message_contains = "ruff.....Failed"
stages = ["primary"]
```

### 4. Type-Specific Global Handlers

Handle all failures of a specific type consistently.

```toml
# Multiple Claude actions in workflow
[[actions]]
name = "update-code"
type = "claude"
task_prompt = "prompts/update.md.j2"

[[actions]]
name = "update-tests"
type = "claude"
task_prompt = "prompts/tests.md.j2"

# Global handler for any Claude failures
[[actions]]
name = "claude-error-reporter"
type = "template"
stage = "on_error"
recovery_behavior = "skip"
source = "workflow:///templates/claude-failure.md.j2"
destination = "CLAUDE_ERROR.md"

[actions.error_filter]
action_types = ["claude"]
```

### 5. Graceful Cleanup on Failure

Ensure resources are cleaned up before failing.

```toml
[[actions]]
name = "deploy-to-staging"
type = "shell"
command = "terraform apply -auto-approve"
on_error = "cleanup-partial-deployment"

[[actions]]
name = "cleanup-partial-deployment"
type = "shell"
stage = "on_error"
recovery_behavior = "fail"
command = """
terraform destroy -auto-approve -target=aws_instance.failed
aws s3 rm s3://staging-bucket/temp/ --recursive
"""
```

### 6. Timeout-Specific Recovery

Handle timeouts differently from other errors.

```toml
[[actions]]
name = "slow-operation"
type = "shell"
command = "scripts/data-processing.sh"
timeout = "1h"

[[actions]]
name = "timeout-reporter"
type = "shell"
stage = "on_error"
recovery_behavior = "skip"
command = """
echo 'Operation timed out after 1 hour' >> timeout.log
curl -X POST https://monitoring.example.com/alert \
  -d '{"type": "timeout", "action": "slow-operation"}'
"""

[actions.error_filter]
exception_types = ["TimeoutError"]
```

## Validation Rules

The workflow engine enforces these constraints on error actions:

### Error Actions Cannot:

- **Have `on_error` field**: Error handlers cannot have their own error handlers
- **Have `ignore_errors = true`**: Would create ambiguous behavior
- **Have `committable = true`**: Error recovery should not create commits

```toml
# INVALID - will fail validation
[[actions]]
name = "bad-error-handler"
type = "shell"
stage = "on_error"
on_error = "another-handler"  # ERROR: not allowed
committable = true               # ERROR: not allowed
command = "echo 'bad'"
```

### Error Actions Must:

- **Be referenced OR have filter**: Every error action must be attached to the workflow either via another action's `on_error` field or by having an `error_filter`

```toml
# INVALID - orphan error handler
[[actions]]
name = "orphan-handler"
type = "shell"
stage = "on_error"
command = "echo 'orphan'"
# ERROR: Not referenced by on_error and no error_filter

# VALID - has filter
[[actions]]
name = "global-handler"
type = "shell"
stage = "on_error"
command = "echo 'global'"

[actions.error_filter]
action_types = ["shell"]
```

### References Must Be Valid:

- **`on_error` must reference existing action**: The referenced action name must exist
- **Referenced action must have `stage = "on_error"`**: Cannot reference regular actions

```toml
# INVALID - references non-existent handler
[[actions]]
name = "bad-reference"
type = "shell"
command = "echo 'test'"
on_error = "does-not-exist"  # ERROR: handler not found

# INVALID - references wrong stage
[[actions]]
name = "bad-stage-reference"
type = "shell"
command = "echo 'test'"
on_error = "not-an-error-handler"

[[actions]]
name = "not-an-error-handler"
type = "shell"
stage = "primary"  # ERROR: must be stage = "on_error"
command = "echo 'handler'"
```

## Error Handler Execution

### Handler Matching Priority

When an action fails, the engine searches for handlers in this order:

1. **Action-specific handler**: Check if failed action has `on_error` field
2. **First matching global handler**: Check global handlers with `error_filter` in order

**Example with priority:**

```toml
[[actions]]
name = "deploy"
type = "shell"
command = "kubectl apply -f deployment.yaml"
on_error = "specific-rollback"  # This takes priority

[[actions]]
name = "specific-rollback"
type = "shell"
stage = "on_error"
recovery_behavior = "fail"
command = "kubectl rollout undo"

[[actions]]
name = "global-shell-handler"
type = "shell"
stage = "on_error"
recovery_behavior = "skip"
command = "echo 'This never runs for deploy action'"

[actions.error_filter]
action_types = ["shell"]  # Matches but lower priority
```

### Handler Failure Behavior

If an error handler itself fails:

1. Workflow **fails immediately** (fail-fast semantics)
2. Both exceptions are logged (original + handler failure)
3. Working directory is preserved for resumability
4. Resume state includes `handler_failed = true`

**Important:** Error handlers cannot have their own error handlers. Design them to be robust.

### Retry Limit Enforcement

When `recovery_behavior = "retry"`:

```toml
[[actions]]
name = "flaky-test"
type = "shell"
command = "pytest tests/integration/test_flaky.py"
on_error = "retry-handler"

[[actions]]
name = "retry-handler"
type = "shell"
stage = "on_error"
recovery_behavior = "retry"
max_retry_attempts = 3
command = "sleep 5"
```

**Execution flow:**

1. `flaky-test` fails (attempt 1)
2. `retry-handler` runs successfully
3. `flaky-test` retries (attempt 2)
4. If fails again, repeat up to `max_retry_attempts`
5. After 3 retry attempts exhausted, workflow fails

**Logging:** Each retry attempt is logged with current/max count.

## Resumability

Error handler state persists across resume operations:

### Retry Counts Persist

```bash
# First run - fails after 2 retries
imbi-automations config.toml workflow --project-id 123

# Resume - continues from retry count 2
imbi-automations config.toml workflow --resume ./errors/workflow/project-123
```

### Resume State Fields

The `.state` file includes:

- `retry_counts`: Map of action name to current retry count
- `active_error_handler`: Name of handler that was running
- `handler_failed`: Whether handler itself failed
- `original_exception_type`: Exception class name from original failure
- `original_exception_message`: Original exception message

**Note:** You cannot resume through a failed error handler. Fix the issue and resume from the failed action.

## Best Practices

### 1. Keep Handlers Simple and Robust

Error handlers should be more reliable than the actions they recover.

**Good:**

```toml
[[actions]]
name = "cleanup-handler"
type = "shell"
stage = "on_error"
recovery_behavior = "skip"
command = "rm -rf /tmp/workflow-temp || true"
```

**Avoid:** Complex handlers that could fail themselves.

### 2. Use Appropriate Recovery Behavior

- `retry`: For transient failures (network, rate limits, flaky tests)
- `skip`: For non-critical failures where workflow can continue
- `fail`: For cleanup before failing (resource deallocation)

### 3. Set Reasonable Retry Limits

```toml
# Good for flaky tests
max_retry_attempts = 3

# Good for rate-limited APIs
max_retry_attempts = 5

# Avoid - too many retries
max_retry_attempts = 20
```

### 4. Provide Context in AI Handlers

Give Claude enough information to diagnose issues:

```markdown
# Error Diagnosis Prompt

## Failed Action
- **Name:** {{ failed_action.name }}
- **Type:** {{ failed_action.type }}
- **Stage:** {{ failed_action.stage }}

## Error Details
- **Exception:** {{ exception_type }}
- **Message:** {{ exception }}
- **Retry:** {{ retry_attempt }}/{{ max_retries }}

## Task
Analyze the error and determine if it's fixable. If it's a code issue,
make targeted fixes. If it's environmental (missing deps, API limits),
explain why it cannot be fixed automatically.
```

### 5. Use Global Handlers for Common Patterns

Instead of duplicating error handlers:

```toml
# Bad - repetitive
[[actions]]
name = "update-code"
type = "claude"
on_error = "claude-handler-1"

[[actions]]
name = "update-tests"
type = "claude"
on_error = "claude-handler-2"

# Good - single global handler
[[actions]]
name = "update-code"
type = "claude"
task_prompt = "prompts/update.md.j2"

[[actions]]
name = "update-tests"
type = "claude"
task_prompt = "prompts/tests.md.j2"

[[actions]]
name = "claude-error-handler"
type = "claude"
stage = "on_error"
recovery_behavior = "skip"
task_prompt = "prompts/diagnose.md.j2"

[actions.error_filter]
action_types = ["claude"]
```

## Troubleshooting

### Error Handler Never Triggers

**Check:**

1. Handler has correct `stage = "on_error"`
2. Handler is referenced by `on_error` OR has `error_filter`
3. Filter criteria match the failed action
4. Failed action does not have `ignore_errors = true`

### Infinite Retry Loop

**Cause:** Handler succeeds but underlying issue persists.

**Solution:** Lower `max_retry_attempts` or change `recovery_behavior` to `"skip"`.

### Handler Fails Immediately

**Check:**

1. Handler command/script is valid
2. Required environment variables are set
3. Handler has access to necessary resources

**Tip:** Test handlers independently before adding to workflow.

### Validation Errors

**Common issues:**

```
Error: Error action "X" cannot have on_error
→ Remove on_error from error actions

Error: Error action "X" cannot be committable
→ Set committable = false or remove field

Error: Action "Y" references non-existent error handler "X"
→ Ensure handler exists and has stage = "on_error"

Error: Error action "X" must be either referenced or have error_filter
→ Add on_error reference or error_filter
```

## Metrics and Tracking

The workflow engine automatically tracks error handler invocations and includes them in the final run summary. This helps you understand:

- How often error handlers are being triggered
- Which specific handlers are most active
- Success vs. failure rates for recovery attempts

### Tracked Metrics

**Global Counters:**
- `Error Handlers Invoked`: Total number of times any error handler was triggered
- `Error Handlers Succeeded`: Number of handlers that completed successfully
- `Error Handlers Failed`: Number of handlers that failed during execution

**Per-Handler Counters:**
- `Error Handler Invoked {name}`: Number of times a specific handler was triggered
- `Error Handler Succeeded {name}`: Number of times a specific handler succeeded
- `Error Handler Failed {name}`: Number of times a specific handler failed

### Example Output

```
Automation Engine Run Details:
Actions Executed: 25
Actions Committed: 18
Error Handlers Invoked: 3
Error Handler Invoked Fix Precommit Errors: 3
Error Handlers Succeeded: 2
Error Handler Succeeded Fix Precommit Errors: 2
Error Handlers Failed: 1
Error Handler Failed Fix Precommit Errors: 1
```

This shows that the `fix-precommit-errors` handler was triggered 3 times, succeeded twice, and failed once.

### Using Metrics

These metrics help you:

1. **Identify problematic actions**: If a handler runs frequently, the underlying action may need improvement
2. **Tune retry limits**: Adjust `max_retry_attempts` based on actual success rates
3. **Validate handlers**: Ensure handlers are working as expected
4. **Track workflow health**: Monitor error recovery trends across runs

## See Also

- [Workflow Configuration](workflow-configuration.md) - Complete workflow config reference
- [Templating](templating.md) - Jinja2 template syntax and variables
- [CLI Reference](cli.md) - Resume and preserve-on-error options
- [Debugging](debugging.md) - Debugging failed workflows
