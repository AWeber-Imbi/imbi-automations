# TODO - Path to 1.0 Release

This document tracks unfinished functionality, planned features, and known issues
that should be addressed before the 1.0 release.

## Planned Features (Future Enhancements)

These are documented as "planned" but not critical for 1.0:

### Imbi Actions (docs/actions/imbi.md:360-367)

- `get_project_fact` - Retrieve fact values for conditional logic
- `delete_project_fact` - Remove obsolete facts
- `add_project_link` - Add external links to projects
- `update_project_type` - Change project classification
- `batch_update_facts` - Update multiple facts in one operation

**Current state:** Three commands implemented:
- `set_project_fact` - Set a project fact value
- `set_environments` - Update project environments
- `update_project` - Update project attributes (name, description, etc.)

**Recommendation for 1.0:** Document current limitations; remaining actions can be post-1.0.

## Pre-1.0 Checklist

### Must Fix
- [x] Update template action documentation to remove incorrect bug warnings
- [x] Implement docker build/pull/push commands
- [x] Remove unimplemented utility action type (functionality available via template functions)
- [x] Add unit tests for missing action types (template, git, imbi)

### Should Address
- [x] Remove GitLab references if not implementing GitLab support
- [x] Clarify rollback capabilities in documentation

### Nice to Have
- [ ] Implement additional Imbi actions (get_project_fact, etc.)

## Version History

- **Current:** 1.0.0a13
- **Next Release:** 1.0.0b1
- **Target:** 1.0.0
