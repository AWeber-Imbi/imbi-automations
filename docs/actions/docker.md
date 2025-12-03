# Docker Actions

Docker actions provide container operations for extracting files from Docker images.

## Configuration

```toml
[[actions]]
name = "action-name"
type = "docker"
command = "extract"     # Only extract is currently implemented
image = "image:tag"     # Required
# Command-specific fields below
```

## Commands

### extract

Extract files from a Docker container image.

**Status:** ✅ Implemented  

**Required Fields:**  

- `image` (string): Docker image name (tag can be separate or in format `image:tag`)
- `source` ([pathlib.Path][]): Path inside container to extract from
- `destination` ([`ResourceUrl`](index.md#resourceurl-path-system)): Local path to extract to (typically `extracted:///`)

**Optional Fields:**  

- `tag` (string): Image tag (default: `latest`) - only used if image doesn't contain `:tag`

**Example:**
```toml
[[actions]]
name = "extract-python-libs"
type = "docker"
command = "extract"
image = "python"
tag = "3.12-slim"
source = "/usr/local/lib/python3.12/"
destination = "extracted:///python-libs/"
```

**Behavior:**  

1. Pulls the image if not available locally (`docker pull`)
2. Creates temporary container from image (`docker create`)
3. Copies files from container to local filesystem (`docker cp`)
4. Stores in `extracted:///` directory (resolves to `{working_directory}/extracted/`)
5. Automatically cleans up container (`docker rm`)

### build

**Status:** ❌ Not yet implemented (raises NotImplementedError)  

Build a Docker image from a Dockerfile.

**Required Fields:**  

- `image`: Image name to create
- `path`: Path to Dockerfile directory ([`ResourceUrl`](index.md#resourceurl-path-system))

**Optional Fields:**  

- `tag`: Image tag (default: `latest`)

### pull

**Status:** ❌ Not yet implemented (raises NotImplementedError)  

Pull a Docker image from registry.

**Required Fields:**  

- `image`: Image name to pull

**Optional Fields:**  

- `tag`: Image tag (default: `latest`)

### push

**Status:** ❌ Not yet implemented (raises NotImplementedError)  

Push a Docker image to registry.

**Required Fields:**  

- `image`: Image name to push

**Optional Fields:**  

- `tag`: Image tag (default: `latest`)

## Common Use Cases

### Extract Configuration Files

```toml
[[actions]]
name = "extract-nginx-config"
type = "docker"
command = "extract"
image = "nginx"
tag = "latest"
source = "/etc/nginx/"
destination = "extracted:///nginx-config/"

[[actions]]
name = "copy-to-repo"
type = "file"
command = "copy"
source = "extracted:///nginx-config/nginx.conf"
destination = "repository:///config/nginx.conf"
```

### Extract Python Packages

```toml
[[actions]]
name = "extract-site-packages"
type = "docker"
command = "extract"
image = "myapp"
tag = "latest"
source = "/usr/local/lib/python3.12/site-packages/"
destination = "extracted:///packages/"
```

### Extract Multiple Directories

```toml
[[actions]]
name = "extract-app-dir"
type = "docker"
command = "extract"
image = "myapp"
tag = "latest"
source = "/app/"
destination = "extracted:///app/"

[[actions]]
name = "extract-config-dir"
type = "docker"
command = "extract"
image = "myapp"
tag = "latest"
source = "/etc/myapp/"
destination = "extracted:///config/"
```

## Implementation Notes

### Extract Command
- Requires Docker daemon running locally
- Uses `docker` CLI commands (`pull`, `create`, `cp`, `rm`)
- Temporary containers automatically cleaned up after extraction
- Extracted files preserve permissions from container
- Container name format: `imbi-extract-{id}`
- Pulls image automatically if not available locally
- Image names support Jinja2 templating: `image = "{{ project_name }}"`

### Not Implemented Commands
The following commands are defined but not yet implemented:
- `build`: Would build Docker images from Dockerfiles
- `pull`: Would pull images from registry (extract does this automatically)
- `push`: Would push images to registry

Attempting to use these commands will raise `NotImplementedError`.

## Error Handling

- Docker command failures raise `RuntimeError` with exit code and output
- Missing Docker CLI raises helpful error: "Docker command not found - is Docker installed and in PATH?"
- Container cleanup failures are logged but don't fail the action
- Image pull failures propagate as RuntimeError

## Integration with Other Actions

### Docker Extract + File Copy Pattern

```toml
# Extract from container
[[actions]]
name = "extract-config"
type = "docker"
command = "extract"
image = "nginx"
tag = "alpine"
source = "/etc/nginx/nginx.conf"
destination = "extracted:///nginx.conf"

# Copy to repository
[[actions]]
name = "use-extracted-config"
type = "file"
command = "copy"
source = "extracted:///nginx.conf"
destination = "repository:///config/nginx.conf"
```

### Docker Extract + Claude Analysis

```toml
# Extract application code
[[actions]]
name = "extract-app-code"
type = "docker"
command = "extract"
image = "production-app"
tag = "latest"
source = "/app/src/"
destination = "extracted:///prod-code/"

# Analyze with Claude
[[actions]]
name = "analyze-differences"
type = "claude"
prompt = "prompts/analyze-prod-vs-repo.md"
# Prompt can reference both extracted:///prod-code/ and repository:///
```
