"""Git-related data models."""

import datetime

from . import base


class GitFileChange(base.BaseModel):
    """Represents a file change in a git commit."""

    status: str  # A (added), M (modified), D (deleted), R (renamed), etc.
    file_path: str
    old_path: str | None = None  # For renames
    diff: str | None = None  # Full diff content for the file


class GitCommit(base.BaseModel):
    """Represents a git commit with parsed message and file changes."""

    hash: str
    author_name: str
    author_email: str
    committer_name: str
    committer_email: str
    author_date: datetime.datetime
    commit_date: datetime.datetime
    subject: str
    body: str
    trailers: dict[str, str] = {}
    files_changed: list[GitFileChange] = []


class GitCommitSummary(base.BaseModel):
    """Summary of multiple commits for workflow analysis."""

    total_commits: int
    commits: list[GitCommit]
    files_affected: list[str]  # Unique list of all files modified
    commit_range: str  # Format: "start_hash..end_hash"
