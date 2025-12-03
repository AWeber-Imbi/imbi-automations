# Callable Actions

✅ **IMPLEMENTED**: Callable actions are fully implemented and tested.

Callable actions invoke Python callable objects (functions, methods, coroutines) dynamically with flexible arguments. This enables direct execution of Python code from workflows, including client methods, utility functions, and custom callables.

## Configuration

```toml
[[actions]]
name = "action-name"
type = "callable"
callable = "module.path:function_or_method_name"
args = [1, "string", true]      # Optional positional arguments
kwargs = {key = "value"}         # Optional keyword arguments
ai_commit = true                 # Optional, default: true
```

## Fields

### callable (required)

Python import string specifying the callable to invoke. Uses Pydantic's `ImportString` format.

**Type:** `string` (ImportString format: `"module.path:callable_name"`)  

**Format:** `"package.module:function"` or `"package.module.submodule:ClassName.method"`  

**Examples:**  
```toml
# Function from module
callable = "os.path:join"

# Method from class
callable = "imbi_automations.clients.github:GitHub.create_issue"

# Async function
callable = "asyncio:sleep"

# Custom module
callable = "my_package.utils:process_data"
```

**Import Resolution:**  

- The string before `:` is the module path to import
- The string after `:` is the attribute name to retrieve from the module
- Supports nested attributes (e.g., `Class.method`)
- Automatically detects and awaits async callables (coroutines)

### args (optional)

Positional arguments to pass to the callable. Arguments are passed in order.

**Type:** `list[Any]`  

**Default:** `[]`  

**Supports:**

- Primitive types (int, float, bool, string)
- Lists and dictionaries
- Jinja2 template strings (automatically rendered)
- Mixed types

**Template Rendering:**  
```toml
args = [
    42,                              # Literal integer
    "{{ imbi_project.name }}",       # Template string (rendered)
    true,                            # Literal boolean
    "literal-string"                 # Literal string (no templates)
]
```

**Important:** Positional argument order is preserved. Template strings are rendered before execution.

### kwargs (optional)

Keyword arguments to pass to the callable.

**Type:** `dict[string, Any]`  

**Default:** `{}`  

**Supports:**

- Same types as `args`
- Jinja2 template rendering in string values
- Nested structures

**Template Rendering:**  
```toml
[actions.kwargs]
project_name = "{{ imbi_project.name }}"      # Template (rendered)
project_id = 123                               # Literal integer
enabled = true                                 # Literal boolean
config = {nested = "value"}                    # Nested dict
```

### ai_commit (optional)

Whether to use AI-generated commit messages for repository changes made by this action.

**Type:** `boolean`  

**Default:** `true`  

**Note:** Only relevant if the callable makes repository changes and `committable = true`.  

## Template Context

String arguments support Jinja2 templating with full workflow context:

| Variable | Description | Example |
|----------|-------------|---------|
| `workflow` | Workflow configuration | `{{ workflow.slug }}` |
| `imbi_project` | Imbi project data | `{{ imbi_project.name }}` |
| `github_repository` | GitHub repository (if present) | `{{ github_repository.name }}` |
| `working_directory` | Execution directory path | `{{ working_directory }}` |
| `starting_commit` | Initial commit SHA | `{{ starting_commit }}` |

**Template Detection:**  

- Only `string` values are checked for templates
- Templates must contain `{{`, `{%`, or `{#` syntax
- Non-string types (int, bool, list, dict) pass through unchanged
- Strings without template syntax are not rendered

## Async/Sync Detection

The action automatically detects whether the callable is synchronous or asynchronous using `asyncio.iscoroutinefunction()` and executes accordingly to maintain async safety.

**Async callables:**  
```python
async def my_async_function(arg1: int, arg2: str) -> None:
    await asyncio.sleep(1)
    # ... async work
```

```toml
[[actions]]
name = "call-async"
type = "callable"
callable = "my_module:my_async_function"
args = [42, "hello"]
# Automatically awaited with: await action.callable(*args, **kwargs)
```

**Sync callables:**  
```python
def my_sync_function(arg1: int, arg2: str) -> None:
    # ... sync work (may be blocking)
    time.sleep(1)
```

```toml
[[actions]]
name = "call-sync"
type = "callable"
callable = "my_module:my_sync_function"
args = [42, "hello"]
# Executed in thread pool: await asyncio.to_thread(callable, *args, **kwargs)
```

**Detection and Execution:**  

- **Detection Method:** Uses `asyncio.iscoroutinefunction()` to detect async callables
- **Async Execution:** Coroutines are directly awaited: `await callable(*args, **kwargs)`
- **Sync Execution:** Regular functions run in thread pool via `asyncio.to_thread()` to prevent blocking the event loop
- **Thread Pool Benefit:** Sync callables can perform blocking I/O without freezing async workflows

**Recent Fix (commit dc48d25):**

- Sync callables now properly use `asyncio.to_thread()` instead of direct execution
- Prevents blocking the event loop when sync callables perform blocking operations
- Maintains async safety across all callable types

## Examples

### Call Standard Library Function

```toml
[[actions]]
name = "create-directory"
type = "callable"
callable = "os:makedirs"
args = ["{{ working_directory }}/output"]
kwargs = {exist_ok = true}
committable = false
```

### Call GitHub Client Method

```toml
[[actions]]
name = "create-github-label"
type = "callable"
callable = "imbi_automations.clients.github:GitHub.create_label"
kwargs = {
    name = "automated",
    color = "00ff00",
    description = "Created by automation"
}
```

### Call Utility Function with Templates

```toml
[[actions]]
name = "process-project-data"
type = "callable"
callable = "my_utils:process_data"
args = [
    "{{ imbi_project.slug }}",
    "{{ imbi_project.project_type }}",
    "{{ imbi_project.namespace }}"
]
kwargs = {
    output_dir = "{{ working_directory }}/processed",
    verbose = true
}
```

### Call Method with Mixed Arguments

```toml
[[actions]]
name = "update-project-fact"
type = "callable"
callable = "imbi_automations.clients.imbi:Imbi.set_project_fact"
args = [
    123,                             # project_id (literal)
    "{{ workflow.slug }}",           # fact_name (template)
    "completed"                      # fact_value (literal)
]
```

### Call Custom Function

```toml
[[actions]]
name = "validate-config"
type = "callable"
callable = "validators.config:validate_yaml"
args = ["{{ working_directory }}/repository/config.yaml"]
kwargs = {
    schema = "config-schema.json",
    strict = true
}
ignore_errors = false
```

### Async Function Call

```toml
[[actions]]
name = "async-api-call"
type = "callable"
callable = "my_api.client:fetch_data"
args = ["https://api.example.com/data"]
kwargs = {
    timeout = 30,
    retry = 3
}
# Automatically awaited due to async detection
```

## Advanced Usage

### Complex Template Expressions

```toml
[[actions]]
name = "conditional-processing"
type = "callable"
callable = "processors:handle_project"
args = [
    "{{ imbi_project.namespace }}/{{ imbi_project.name }}",
    "{{ imbi_project.id | int }}",
    "{% if imbi_project.id > 100 %}large{% else %}small{% endif %}"
]
```

### Non-String Template Values

```toml
[[actions]]
name = "structured-data"
type = "callable"
callable = "handlers:process_metadata"
kwargs = {
    project_name = "{{ imbi_project.name }}",  # Rendered template (string)
    project_id = 123,                           # Literal integer (not rendered)
    enabled = true,                             # Literal boolean (not rendered)
    tags = ["api", "production"],               # Literal list (not rendered)
    metadata = {
        env = "prod",                           # Nested dict (not rendered)
        region = "us-east-1"
    }
}
```

### Error Handling with ignore_errors

```toml
[[actions]]
name = "optional-operation"
type = "callable"
callable = "optional_tasks:try_operation"
args = ["{{ imbi_project.slug }}"]
ignore_errors = true  # Continue workflow even if callable fails
```

### Conditional Execution

```toml
[[actions]]
name = "python-only-task"
type = "callable"
callable = "python_utils:analyze_dependencies"
args = ["{{ working_directory }}/repository"]

# Only run for Python projects
[[actions.conditions]]
file_exists = "requirements.txt"
```

## Return Values

**Important:** Callable actions execute for **side effects only**. Return values are **not captured** or made available to subsequent actions.

If you need to capture output:
1. Have the callable write to a file in the working directory
2. Use a subsequent file action to read the output
3. Use the `data` field to pass information between actions (if needed)

Example:
```toml
[[actions]]
name = "generate-report"
type = "callable"
callable = "reporters:generate_report"
kwargs = {
    project = "{{ imbi_project.slug }}",
    output_file = "{{ working_directory }}/report.json"
}

[[actions]]
name = "read-report"
type = "shell"
command = "cat {{ working_directory }}/report.json"
```

## Error Handling

### Exception Handling

All exceptions raised by callables are caught and wrapped in `RuntimeError`:

```python
# In callable
def my_function():
    raise ValueError("Something went wrong")

# In workflow logs
# RuntimeError: Something went wrong
#   Caused by: ValueError: Something went wrong
```

The original exception is preserved via `__cause__` for debugging.

### Logging

**Debug logging:**  
```
DEBUG: Executing my_module:my_function([1, 2], {'key': 'value'})
```

**Exception logging:**  
```
ERROR: Error invoking callable: Something went wrong
<full exception traceback>
```

### Ignore Errors

```toml
[[actions]]
name = "best-effort-task"
type = "callable"
callable = "optional:task"
ignore_errors = true  # Continue workflow even if callable raises exception
```

## Integration with Other Actions

### Sequential Callable Chain

```toml
[[actions]]
name = "fetch-data"
type = "callable"
callable = "api.client:fetch_project_data"
args = ["{{ imbi_project.id }}"]

[[actions]]
name = "process-data"
type = "callable"
callable = "processors:transform_data"
args = ["{{ working_directory }}/data.json"]

[[actions]]
name = "upload-results"
type = "callable"
callable = "api.client:upload_results"
args = ["{{ working_directory }}/results.json"]
```

### Callable + Shell (Verification)

```toml
[[actions]]
name = "run-python-script"
type = "callable"
callable = "scripts.migration:run_migration"
kwargs = {db_url = "{{ config.database_url }}"}

[[actions]]
name = "verify-migration"
type = "shell"
command = "python scripts/verify.py"
working_directory = "repository:///"
```

### Callable + File (Data Processing)

```toml
[[actions]]
name = "generate-config"
type = "callable"
callable = "config_gen:create_config"
kwargs = {
    project = "{{ imbi_project.slug }}",
    output = "{{ working_directory }}/config.yaml"
}

[[actions]]
name = "copy-to-repo"
type = "file"
command = "copy"
source = "{{ working_directory }}/config.yaml"
destination = "repository:///config/generated.yaml"
```

## Performance Considerations

- **Import Time**: First call imports the module (cached by Python thereafter)
- **Execution Time**: Depends on callable implementation
- **Async Overhead**: Minimal for properly async callables (directly awaited)
- **Sync Thread Pool Overhead**: Minor context switch cost for sync callables via `asyncio.to_thread()`
- **Template Rendering**: Only performed for string arguments with template syntax (detected via regex)
- **ResourceUrl Resolution**: Path resolution performed for each ResourceUrl argument (cached by `pathlib.Path`)

## Security Considerations

- **Code Execution**: Callables execute with full Python interpreter access
- **Import Safety**: Only import from trusted modules
- **Argument Validation**: Callables should validate input arguments
- **Error Information**: Exception messages may contain sensitive data

## Best Practices

### ✅ Do

- Use callable actions for Python-native operations
- Validate arguments in your callable implementations
- Use templates for dynamic values
- Document expected callable signatures
- Handle exceptions gracefully in callables
- Write to files for persistent output

### ❌ Don't

- Don't rely on return values (they're not captured)
- Don't use for operations better suited to specialized actions (file, git, github)
- Don't pass sensitive data in literal arguments (use environment variables or config)
- Don't use blocking sync operations in async callables

## Implementation Details

- **Module:** `src/imbi_automations/actions/callablea.py` (656 lines of implementation + tests)
- **Model:** `src/imbi_automations/models/workflow.py:WorkflowCallableAction`
- **Tests:** `tests/actions/test_callable.py` (30 comprehensive test cases, full coverage)
- **Import Format:** Uses Pydantic's `ImportString` validator for safe dynamic imports
- **Async Detection:** Uses `asyncio.iscoroutinefunction()` to detect coroutines
- **Sync Execution:** Uses `asyncio.to_thread(callable, *args, **kwargs)` for thread pool execution
- **Template Rendering:** Uses `prompts.render()` with Jinja2, only for strings with `{{`, `{%`, or `{#`
- **Template Detection:** Uses `prompts.has_template_syntax()` regex check
- **ResourceUrl Resolution:** Uses `utils.resolve_path()` for path scheme handling
- **Error Wrapping:** All exceptions wrapped in `RuntimeError` with original as `__cause__` for exception chaining

## Migration from Shell Actions

If you were using shell actions to run Python code, consider migrating to callable actions:

**Before (shell action):**
```toml
[[actions]]
name = "run-python"
type = "shell"
command = "python -c 'from mymodule import func; func(\"arg1\", \"arg2\")'"
```

**After (callable action):**
```toml
[[actions]]
name = "run-python"
type = "callable"
callable = "mymodule:func"
args = ["arg1", "arg2"]
```

**Benefits:**

- Type safety and validation
- Better error messages
- No shell escaping issues
- Template support for arguments
- Async/await support
- Cleaner syntax
