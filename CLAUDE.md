@AGENTS.md

- Remember to check for updates in AGENTS.md when making changes. This file is for AI Assistants like Claude Code so I expect that you maintain it as well.

## Versioning

**pyproject.toml (PyPI format):**
- Pre-release versions MUST NOT use a hyphen before the pre-release identifier
- Examples: `1.0.0b5`, `1.0.0a13`, `1.0.0rc1`
- NOT: `1.0.0-b5`, `1.0.0-a13` (hyphen is incorrect for PyPI)

**Git Tags and GitHub Releases:**
- Pre-release versions MUST use a hyphen before the pre-release identifier
- Examples: `v1.0.0-b5`, `v1.0.0-a13`, `v1.0.0-rc1`
- NOT: `v1.0.0b5`, `v1.0.0a13` (no hyphen breaks Docker workflow)

**Why the difference:**
- PyPI requires no hyphen in version strings (PEP 440)
- GitHub Docker workflow expects hyphenated versions in tags/releases
- When bumping versions, update pyproject.toml first, then tag with hyphenated format
