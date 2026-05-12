# Migrating from Imbi v1

Imbi Automations switched from the flat Imbi v1 API to the org-scoped Imbi
v2 API in release **1.0.0b15** ([PR #118][pr-118]). The API surface,
configuration shape, workflow field names, and project identifiers all
changed. This document is the checklist for moving a working v1
deployment forward.

If you only run `imbi-automations` against `imbi.example.com`, you only
need to touch the **configuration file** and your **workflow TOMLs**. If
you have saved resume state or scripts that pass `--project-id`, read
the [CLI](#cli) and [resume state](#resume-state) sections too.

[pr-118]: https://github.com/AWeber-Imbi/imbi-automations/pull/118

## What changed at a glance

| Area | v1 | v2 |
| --- | --- | --- |
| API path prefix | `/api/projects/...` | `/api/organizations/{org}/projects/...` |
| Project IDs | Integers (`123`) | Nano-ID strings (`proj_8FwQ1aN3`) |
| `[imbi]` config | `hostname = "imbi.example.com"` | `organization = "..."` + `base_url = "https://imbi.example.com"` |
| Auth | `api_key` only | `[imbi.auth]` block (api_key / client_credentials / password); `api_key` retained as shortcut |
| Imbi action `fact_name` | `fact_name = "Programming Language"` | `attribute_name = "programming_language"` |
| Imbi action `link_type` | `link_type = "github-repository"` | `link_definition_slug = "github-repository"` |
| `update_project_type` field | `project_type = "api"` | `project_types = ["api"]` (list) |
| Filter `project_ids` | `[123, 456]` | `["proj_abc", "proj_def"]` |
| Filter `project_facts` keys | Display names ("Programming Language") | Blueprint attribute slugs ("programming_language") |
| Project facts in templates | `imbi_project.facts["Programming Language"]` | `imbi_project.programming_language` (blueprint extras) |
| Resume state schema | `schema_version = 1` | `schema_version = 2` — old `.state` files rejected |

## Configuration file

### Replace `hostname` with `base_url`

The `[imbi].hostname` field is gone. Use `base_url` with the full URL
(scheme included; do **not** include `/api`):

```toml
# v1
[imbi]
api_key = "ik_..."
hostname = "imbi.example.com"
```

```toml
# v2
[imbi]
organization = "platform"
base_url = "https://imbi.example.com"
api_key = "ik_..."
```

### Add `organization`

Every v2 request is scoped to a single organization slug. `organization`
is required.

If you operate against multiple orgs, run one `config.toml` per org.
There is no per-workflow override yet.

### Auth: keep `api_key` or switch to `[imbi.auth]`

The plain `api_key` shortcut still works and is folded into an API-key
auth variant internally. No change required for API-key users.

For OAuth2 client credentials or username/password (dev only), use the
new discriminated block:

```toml
[imbi.auth]
type = "client_credentials"
client_id = "cc_..."
client_secret = "..."

# or

[imbi.auth]
type = "password"
email = "user@example.com"
password = "..."
```

If both `api_key` and `[imbi.auth]` are set, `[imbi.auth]` wins.

JWTs from `client_credentials` and `password` auth are refreshed in the
background; on a 401 the client calls `POST /api/auth/token/refresh`
and retries the original request once. No user action needed.

## Workflow TOMLs

### Imbi action field renames

| Command | v1 field | v2 field |
| --- | --- | --- |
| `set_project_fact`, `get_project_fact`, `delete_project_fact` | `fact_name` | `attribute_name` |
| `add_project_link` | `link_type` | `link_definition_slug` |
| `update_project_type` | `project_type` (string) | `project_types` (list) |

```toml
# v1
[[actions]]
type = "imbi"
command = "set_project_fact"
fact_name = "Programming Language"
value = "Python 3.12"

[[actions]]
type = "imbi"
command = "add_project_link"
link_type = "github-repository"
url = "https://github.com/org/repo"

[[actions]]
type = "imbi"
command = "update_project_type"
project_type = "api"
```

```toml
# v2
[[actions]]
type = "imbi"
command = "set_project_fact"
attribute_name = "programming_language"
value = "Python 3.12"

[[actions]]
type = "imbi"
command = "add_project_link"
link_definition_slug = "github-repository"
url = "https://github.com/org/repo"

[[actions]]
type = "imbi"
command = "update_project_type"
project_types = ["api"]   # list, even with one entry
```

Note that v2 attribute names are **blueprint attribute slugs** (typically
snake_case), not display labels. Run a project through Imbi's UI or the
`/projects/{id}/schema` endpoint to discover the slugs your org has
defined. The new `update_project` command takes an `attributes = { ... }`
dict and is the more idiomatic v2 way to write multiple attributes at
once — see [Imbi actions](actions/imbi.md).

### Filter changes

`project_ids` and `exclude_project_ids` are now Nano-ID strings:

```toml
# v1
[filter]
project_ids = [42, 108, 256]
exclude_project_ids = [999]
```

```toml
# v2
[filter]
project_ids = ["proj_abc123", "proj_def456", "proj_ghi789"]
exclude_project_ids = ["proj_xyz999"]
```

`project_facts` keys must now match blueprint attribute slugs rather
than display labels:

```toml
# v1
[filter]
project_facts = {"Programming Language" = "Python 3.12"}
```

```toml
# v2
[filter]
project_facts = {"programming_language" = "Python 3.12"}
```

The exact slug depends on your org's blueprints; the metadata cache
will validate at parse time and emit fuzzy suggestions for typos.

### Project fact access in Jinja2 templates

v1 stored facts in `imbi_project.facts` as a dict keyed by display name.
v2 spreads blueprint attributes onto `ImbiProject` as model extras
(Pydantic `extra='allow'`), accessed by slug:

```jinja
{# v1 #}
{{ imbi_project.facts["Programming Language"] }}

{# v2 #}
{{ imbi_project.programming_language }}
{# or, defensively #}
{{ imbi_project.model_extra.get("programming_language", "unknown") }}
```

`imbi_project.project_type` (singular) is gone. Use the new
`project_types` list:

```jinja
{# v2 #}
{{ imbi_project.project_types[0].slug }}
{% if 'api' in imbi_project.project_types | map(attribute='slug') | list %}
  ...
{% endif %}
```

`imbi_project.team.slug` and `imbi_project.environments` work the same
way (list of `{name, slug}` objects).

## CLI

`--project-id` now accepts a Nano-ID string:

```bash
# v1
imbi-automations config.toml workflows/upgrade-python --project-id 123

# v2
imbi-automations config.toml workflows/upgrade-python --project-id proj_8FwQ1aN3
```

`--project-type` is unchanged (still a slug string).

## Resume state

The resume `.state` file format bumped to schema version 2 (project IDs
are strings, plus other internal changes). v1 `.state` files are
rejected at load time with a clear error.

If you have in-flight workflow runs you wanted to resume across the
upgrade, you have to **start them over**. There is no automatic
upgrader for `.state` files.

```bash
# Drop any pre-upgrade error directories
rm -rf ./errors/<workflow>/<project>-<timestamp>/
```

This is also a good moment to delete stale error directories from before
the upgrade — most of the content (project model, action serialization)
won't deserialize on v2 anyway.

## Imbi metadata cache

The cache at `~/.cache/imbi-automations/metadata.json` has its own
`schema_version` and an org-slug gate. v1 caches are detected and
discarded automatically on the next run — no manual action is required.

If you want to force a refresh anyway:

```bash
rm ~/.cache/imbi-automations/metadata.json
```

## Server-side prerequisites

A few things must be true of your Imbi server before the v2 CLI can do
useful work against it:

- The Imbi server itself is on the org-scoped v2 release.
- An organization exists with the slug you configure as
  `[imbi].organization`.
- Project blueprints are loaded for every project type you target.
  The CLI resolves `attribute_name` values against the per-project
  schema served at `GET /projects/{id}/schema`; if blueprints aren't
  loaded, you'll get `attribute not allowed` errors on writes.

If you are also running the Imbi v1 → v2 server migration, load
blueprints **before** migrating project data. The Imbi orchestrator's
`just migrate-all` recipe handles ordering automatically.

## Migration checklist

Run through these for each environment where `imbi-automations` is
configured:

- [ ] Update `[imbi].hostname` → `[imbi].base_url` (full URL, no `/api`)
- [ ] Add `[imbi].organization`
- [ ] (Optional) Switch to `[imbi.auth]` block for OAuth2 / password auth
- [ ] In each workflow TOML:
    - [ ] Rename `fact_name` → `attribute_name` (and update values to
          slug form if they were display names)
    - [ ] Rename `link_type` → `link_definition_slug` in
          `add_project_link` actions
    - [ ] Rename `project_type` → `project_types` (list) in
          `update_project_type` actions
    - [ ] Update `[filter].project_ids` /
          `[filter].exclude_project_ids` to Nano-ID strings
    - [ ] Update `[filter].project_facts` keys to blueprint attribute
          slugs
- [ ] In each Jinja2 prompt/template:
    - [ ] Replace `imbi_project.facts["..."]` lookups with
          `imbi_project.<slug>` (or `model_extra.get(...)`)
    - [ ] Replace `imbi_project.project_type` with
          `imbi_project.project_types[*]`
- [ ] Update any scripts that pass `--project-id` to use Nano-IDs
- [ ] Delete or accept loss of old `.state` files under `./errors/`
- [ ] Bump the installed version: `pip install -U imbi-automations` or
      `uv pip install -U imbi-automations`
- [ ] Smoke test: `imbi-automations config.toml workflows/<one>
      --project-id proj_<known-id>` and confirm the run reaches at
      least the clone phase

## See also

- [Configuration File](configuration.md) — full reference for the
  v2 `[imbi]` block and `[imbi.auth]` variants
- [Workflow Filters](workflow-filters.md) — current filter fields
- [Imbi Actions](actions/imbi.md) — all `command = "..."` variants
  and their fields
