# TODO - Path to 1.0 Release

This document tracks unfinished functionality, planned features, and known issues
that should be addressed before the 1.0 release.

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
- [x] Implement additional Imbi actions (get_project_fact, etc.)

## Completed Features

### Imbi Actions (All Implemented)

Eight commands now available:
- `add_project_link` - Add external links to projects
- `batch_update_facts` - Update multiple facts in one operation
- `delete_project_fact` - Remove obsolete facts
- `get_project_fact` - Retrieve fact values for conditional logic
- `set_environments` - Update project environments
- `set_project_fact` - Set a project fact value
- `update_project` - Update project attributes (name, description, etc.)
- `update_project_type` - Change project classification

## Version History

- **Current:** 1.0.0a13
- **Next Release:** 1.0.0b1
- **Target:** 1.0.0
