# TODO - Path to 1.0 Release

This document tracks unfinished functionality, planned features, and known issues
that should be addressed before the 1.0 release.

## Planned Features (Future Enhancements)

These are documented as "planned" but not critical for 1.0:

### Imbi Actions (docs/actions/imbi.md:360-367)

- `get_project_fact` - Retrieve fact values for conditional logic
- `delete_project_fact` - Remove obsolete facts
- `set_project_metadata` - Update project name, description, etc.
- `add_project_link` - Add external links to projects
- `update_project_type` - Change project classification
- `batch_update_facts` - Update multiple facts in one operation

**Current state:** Only `set_project_fact` is implemented.

**Recommendation for 1.0:** Document current limitations; these can be post-1.0.

## Test Coverage Gaps

Several action types lack dedicated unit tests:

| Action Type | Source File | Test File | Status |
|-------------|-------------|-----------|--------|
| `template` | `actions/template.py` | `test_template.py` | Missing |
| `git` | `actions/git.py` | `test_git.py` | Missing |
| `imbi` | `actions/imbi.py` | `test_imbi.py` | Missing |

**Existing tests:** callable, claude, docker, file, github, shell

### Template Actions

**Recommendation:** Add unit tests for:
- Single file template rendering
- Directory template rendering
- Context variable availability in templates
- Error handling (missing source, invalid template syntax)

### Git Actions

**Recommendation:** Add unit tests for:
- `extract` command (extract file from git history)
- `clone` command (clone external repository)
- Error handling for missing files/commits

### Imbi Actions

**Recommendation:** Add unit tests for:
- `set_project_fact` command
- API error handling
- Fact value validation

## Pre-1.0 Checklist

### Must Fix
- [x] Update template action documentation to remove incorrect bug warnings
- [x] Implement docker build/pull/push commands
- [x] Remove unimplemented utility action type (functionality available via template functions)
- [ ] Add unit tests for missing action types (template, git, imbi)

### Should Address
- [x] Remove GitLab references if not implementing GitLab support
- [x] Clarify rollback capabilities in documentation

### Nice to Have
- [ ] Implement additional Imbi actions (get_project_fact, etc.)

## Version History

- **Current:** 1.0.0a13
- **Target:** 1.0.0
