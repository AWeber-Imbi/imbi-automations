"""Utility action result models.

Provides Pydantic models for utility action results that are stored
in WorkflowContext.variables for inter-action data passing.
"""

import pydantic


class SemverComparisonResult(pydantic.BaseModel):
    """Result of comparing two semantic versions.

    Stores the comparison result along with parsed version components
    for use in subsequent workflow actions via template access.

    Supports standard semver (major.minor.patch) as well as versions
    with build numbers in the format "major.minor.patch-build".
    """

    current_version: str
    target_version: str
    comparison: int  # -1 (older), 0 (equal), 1 (newer)
    is_older: bool
    is_equal: bool
    is_newer: bool
    current_major: int
    current_minor: int
    current_patch: int
    current_build: int | None = None
    target_major: int
    target_minor: int
    target_patch: int
    target_build: int | None = None
