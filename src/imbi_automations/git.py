"""Git Related Functionality"""

import asyncio
import datetime
import logging
import pathlib
import re

from imbi_automations import models

LOGGER = logging.getLogger(__name__)


async def _run_git_command(
    command: list[str], cwd: pathlib.Path, timeout_seconds: int = 3600
) -> tuple[int, str, str]:
    """
    Run a git command and return return code, stdout, stderr.

    Args:
        command: Git command and arguments
        cwd: Working directory
        timeout_seconds: Timeout in seconds (None for no timeout)

    """
    LOGGER.debug('Running git command: %s', ' '.join(command))

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
    except TimeoutError:
        LOGGER.warning(
            'Git command timed out after %d seconds: %s',
            timeout_seconds,
            ' '.join(command),
        )
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
        return -1, '', f'Command timed out after {timeout_seconds} seconds'
    else:
        stdout_str = stdout.decode('utf-8')
        stderr_str = stderr.decode('utf-8')

        if stdout_str:
            LOGGER.debug('STDOUT: %s', stdout_str)
        if stderr_str:
            LOGGER.debug('STDERR: %s', stderr_str)

        return process.returncode, stdout_str, stderr_str


async def clone_repository(
    working_directory: pathlib.Path,
    clone_url: str,
    branch: str | None = None,
    depth: int | None = 1,
) -> str:
    """Clone a repository to a temporary directory and return HEAD commit hash.

    Args:
        working_directory: Temp directory to clone into
        clone_url: Repository clone URL (HTTPS or SSH)
        branch: Specific branch to clone (optional)
        depth: Clone depth (default: 1 for shallow clone, None for full clone)

    Returns:
        HEAD commit hash of the cloned repository

    Raises:
        RuntimeError: If git clone fails

    """
    repo_dir = working_directory / 'repository'

    LOGGER.debug('Cloning repository %s to %s', clone_url, repo_dir)

    command = ['git', 'clone']
    if branch:
        command.extend(['--branch', branch])
    if depth is not None:
        command.extend(['--depth', str(depth)])
    command.extend([clone_url, str(repo_dir)])

    try:
        returncode, stdout, stderr = await _run_git_command(
            command,
            cwd=working_directory,
            timeout_seconds=600,  # 10 minute timeout
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f'Failed to clone repository {clone_url}: {exc}'
        ) from exc

    if returncode != 0:
        raise RuntimeError(
            f'Git clone failed (exit code {returncode}): {stderr or stdout}'
        )
    LOGGER.debug('Successfully cloned repository to %s', repo_dir)

    # Get the HEAD commit hash of the cloned repository
    command = ['git', 'rev-parse', 'HEAD']
    returncode, stdout, stderr = await _run_git_command(
        command, cwd=repo_dir, timeout_seconds=30
    )

    if returncode != 0:
        # Check if this is an empty repository
        if 'unknown revision' in stderr or 'ambiguous argument' in stderr:
            LOGGER.debug('Cloned empty repository (no commits)')
            return ''
        raise RuntimeError(
            f'Git rev-parse HEAD failed (exit code {returncode}): '
            f'{stderr or stdout}'
        )

    head_commit = stdout.strip()
    LOGGER.debug('Cloned repository HEAD commit: %s', head_commit[:8])
    return head_commit


async def clone_to_directory(
    working_directory: pathlib.Path,
    clone_url: str,
    destination: pathlib.Path,
    branch: str | None = None,
    depth: int | None = None,
) -> str:
    """Clone a repository to a specific destination directory.

    Args:
        working_directory: Base working directory
        clone_url: Repository clone URL (HTTPS or SSH)
        destination: Destination subdirectory relative to working_directory
        branch: Specific branch to clone (optional)
        depth: Clone depth (None for full clone, int for shallow clone)

    Returns:
        HEAD commit hash of the cloned repository

    Raises:
        RuntimeError: If git clone fails

    """
    dest_dir = working_directory / destination

    LOGGER.debug('Cloning repository %s to %s', clone_url, dest_dir)

    command = ['git', 'clone']
    if branch:
        command.extend(['--branch', branch])
    if depth is not None:
        command.extend(['--depth', str(depth)])
    command.extend([clone_url, str(dest_dir)])

    try:
        returncode, stdout, stderr = await _run_git_command(
            command,
            cwd=working_directory,
            timeout_seconds=600,  # 10 minute timeout
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f'Failed to clone repository {clone_url}: {exc}'
        ) from exc

    if returncode != 0:
        raise RuntimeError(
            f'Git clone failed (exit code {returncode}): {stderr or stdout}'
        )
    LOGGER.debug('Successfully cloned repository to %s', dest_dir)

    # Get the HEAD commit hash of the cloned repository
    command = ['git', 'rev-parse', 'HEAD']
    returncode, stdout, stderr = await _run_git_command(
        command, cwd=dest_dir, timeout_seconds=30
    )

    if returncode != 0:
        # Check if this is an empty repository
        if 'unknown revision' in stderr or 'ambiguous argument' in stderr:
            LOGGER.debug('Cloned empty repository (no commits)')
            return ''
        raise RuntimeError(
            f'Git rev-parse HEAD failed (exit code {returncode}): '
            f'{stderr or stdout}'
        )

    head_commit = stdout.strip()
    LOGGER.debug('Cloned repository HEAD commit: %s', head_commit[:8])
    return head_commit


async def add_files(working_directory: pathlib.Path) -> None:
    """Add files to git staging area.

    Args:
        working_directory: Git repository working directory

    Raises:
        RuntimeError: If git add fails

    """
    LOGGER.debug('Working directory: %s', working_directory)
    command = ['git', 'add', '--all']
    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=60
    )
    LOGGER.debug('STDOUT: %s', stdout)
    if returncode != 0:
        LOGGER.error('STDERR: %s', stderr)
        raise RuntimeError(
            f'Git add failed (exit code {returncode}): {stderr or stdout}'
        )


async def remove_files(
    working_directory: pathlib.Path, files: list[str]
) -> None:
    """Remove files from git tracking and staging area.

    Args:
        working_directory: Git repository working directory
        files: List of file paths relative to working directory

    Raises:
        RuntimeError: If git rm fails

    """
    if not files:
        LOGGER.debug('No files to remove from git tracking')
        return

    LOGGER.debug('Removing %d files from git tracking', len(files))

    # Use git rm with multiple files
    command = ['git', 'rm'] + files

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=60
    )

    if returncode != 0:
        raise RuntimeError(
            f'Git rm failed (exit code {returncode}): {stderr or stdout}'
        )

    LOGGER.debug('Successfully removed %d files from git tracking', len(files))


async def commit_changes(
    working_directory: pathlib.Path,
    message: str,
    user_name: str | None = None,
    user_email: str | None = None,
) -> str:
    """Commit staged changes to git repository.

    Args:
        working_directory: Git repository working directory
        message: Commit message
        user_name: Commit author name (default: None)
        user_email: Commit author email (default: None)

    Returns:
        Commit SHA hash

    Raises:
        RuntimeError: If git commit fails

    """
    # Ensure commit message has imbi-automations prefix
    if not message.startswith('imbi-automations:'):
        message = f'imbi-automations: {message}'

    with (working_directory.parent / 'commit-msg.txt').open('w') as f:
        f.write(message)

    command = ['git', 'commit', '-F', '../commit-msg.txt']

    # Add author information if provided
    if user_name and user_email:
        command.extend(['--author', f'"{user_name} <{user_email}>"'])

    command += ['--all']

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=60
    )

    if returncode != 0:
        # Check if it's just "nothing to commit"
        if 'nothing to commit' in stderr or 'nothing to commit' in stdout:
            LOGGER.debug('No changes to commit')
            return ''

        raise RuntimeError(
            f'Git commit failed (exit code {returncode}): {stderr or stdout}'
        )

    # Extract commit SHA from output
    commit_sha = ''
    if stdout:
        # Git commit output typically starts with [branch commit_sha]
        sha_match = re.search(r'\[.*?([a-f0-9]{7,40})\]', stdout)
        if sha_match:
            commit_sha = sha_match.group(1)

    LOGGER.debug(
        'Successfully committed changes: %s', commit_sha or 'unknown SHA'
    )
    return commit_sha


async def push_changes(
    working_directory: pathlib.Path,
    remote: str = 'origin',
    branch: str | None = None,
    force: bool = False,
    set_upstream: bool = False,
) -> None:
    """Push committed changes to remote repository.

    Args:
        working_directory: Git repository working directory
        remote: Remote name (default: 'origin')
        branch: Branch to push (default: current branch)
        force: Force push (default: False, auto-enabled for imbi-automations/*
            branches)
        set_upstream: Set upstream tracking for new branches (default: False)

    Raises:
        RuntimeError: If git push fails

    """
    command = ['git', 'push']

    # Auto-enable force push for imbi-automations branches
    if branch and branch.startswith('imbi-automations/'):
        force = True

    if force:
        command.append('--force')

    if set_upstream:
        command.extend(['--set-upstream', remote])
        if branch:
            command.append(branch)
    else:
        command.append(remote)
        if branch:
            command.append(branch)

    LOGGER.debug(
        'Pushing changes to %s %s', remote, branch or 'current branch'
    )

    returncode, stdout, stderr = await _run_git_command(
        command,
        cwd=working_directory,
        timeout_seconds=300,  # 5 minute timeout
    )

    if returncode != 0:
        raise RuntimeError(
            f'Git push failed (exit code {returncode}): {stderr or stdout}'
        )

    LOGGER.debug(
        'Successfully pushed changes to %s %s',
        remote,
        branch or 'current branch',
    )


async def create_branch(
    working_directory: pathlib.Path, branch_name: str, checkout: bool = True
) -> None:
    """Create a new git branch.

    Args:
        working_directory: Git repository working directory
        branch_name: Name of the new branch to create
        checkout: Whether to checkout the new branch (default: True)

    Raises:
        RuntimeError: If git branch creation fails

    """
    command = (
        ['git', 'checkout', '-b', branch_name]
        if checkout
        else ['git', 'branch', branch_name]
    )

    LOGGER.debug(
        'Creating branch %s in %s (checkout: %s)',
        branch_name,
        working_directory,
        checkout,
    )

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=30
    )

    if returncode != 0:
        raise RuntimeError(
            f'Git branch creation failed (exit code {returncode}): '
            f'{stderr or stdout}'
        )

    LOGGER.debug('Successfully created branch %s', branch_name)


async def get_current_branch(working_directory: pathlib.Path) -> str:
    """Get the current git branch name.

    Args:
        working_directory: Git repository working directory

    Returns:
        Current branch name

    Raises:
        RuntimeError: If git branch query fails

    """
    command = ['git', 'branch', '--show-current']

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=30
    )

    if returncode != 0:
        raise RuntimeError(
            f'Git branch query failed (exit code {returncode}): '
            f'{stderr or stdout}'
        )

    branch_name = stdout.strip()
    LOGGER.debug('Current branch: %s', branch_name)
    return branch_name


async def get_commit_messages_since_branch(
    working_directory: pathlib.Path, base_branch: str = 'main'
) -> list[str]:
    """Get commit messages since branching from base branch.

    Args:
        working_directory: Git repository working directory
        base_branch: Base branch to compare against (default: 'main')

    Returns:
        List of commit messages since branching

    Raises:
        RuntimeError: If git log fails

    """
    command = ['git', 'log', f'{base_branch}..HEAD', '--pretty=format:%s']

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=30
    )

    if returncode != 0:
        # If base_branch doesn't exist, try origin/main
        if 'unknown revision' in stderr.lower():
            command = [
                'git',
                'log',
                f'origin/{base_branch}..HEAD',
                '--pretty=format:%s',
            ]
            returncode, stdout, stderr = await _run_git_command(
                command, cwd=working_directory, timeout_seconds=30
            )

        if returncode != 0:
            raise RuntimeError(
                f'Git log failed (exit code {returncode}): {stderr or stdout}'
            )

    if not stdout.strip():
        return []

    commit_messages = [
        msg.strip() for msg in stdout.split('\n') if msg.strip()
    ]
    LOGGER.debug(
        'Found %d commit messages since %s', len(commit_messages), base_branch
    )
    return commit_messages


async def _get_commits_with_keyword(
    working_directory: pathlib.Path, keyword: str
) -> list[tuple[str, str]]:
    """Get all commits containing the specified keyword.

    Args:
        working_directory: Git repository working directory
        keyword: Keyword to search for in commit messages

    Returns:
        List of tuples (commit_hash, message) for matching commits

    Raises:
        RuntimeError: If git operations fail

    """
    command = [
        'git',
        'log',
        '--grep',
        keyword,
        '--format=%H %s',  # Full hash and subject
        '--all',  # Search all branches
    ]

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=30
    )

    if returncode != 0:
        raise RuntimeError(
            f'Git log failed (exit code {returncode}): {stderr or stdout}'
        )

    if not stdout.strip():
        return []

    # Parse commit lines
    matching_commits = []
    for line in stdout.strip().split('\n'):
        if line.strip():
            parts = line.strip().split(' ', 1)
            if len(parts) >= 2:
                commit_hash, message = parts[0], parts[1]
                matching_commits.append((commit_hash, message))

    return matching_commits


def _select_target_commit(
    matching_commits: list[tuple[str, str]], strategy: str
) -> str:
    """Select the target commit based on strategy.

    Args:
        matching_commits: List of (commit_hash, message) tuples
        strategy: 'before_first_match' or 'before_last_match'

    Returns:
        Target commit hash

    """
    if strategy == 'before_first_match':
        # Last in list = first chronologically
        return matching_commits[-1][0]
    else:  # before_last_match (default)
        # First in list = last chronologically
        return matching_commits[0][0]


async def _get_parent_commit(
    working_directory: pathlib.Path, commit_hash: str
) -> str | None:
    """Get the parent commit of the specified commit.

    Args:
        working_directory: Git repository working directory
        commit_hash: Commit hash to get parent of

    Returns:
        Parent commit hash, or None if no parent exists

    """
    command = ['git', 'rev-parse', f'{commit_hash}^']

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=30
    )

    if returncode != 0:
        if 'unknown revision' in stderr or 'bad revision' in stderr:
            LOGGER.warning(
                'Commit %s has no parent (likely first commit in repository)',
                commit_hash[:8],
            )
        else:
            LOGGER.warning(
                'Could not find commit before %s: %s',
                commit_hash[:8],
                stderr or stdout,
            )
        return None

    return stdout.strip() or None


async def find_commit_before_keyword(
    working_directory: pathlib.Path,
    keyword: str,
    strategy: str = 'before_last_match',
) -> str | None:
    """Find the commit hash before the last commit containing a keyword.

    Args:
        working_directory: Git repository working directory
        keyword: Keyword to search for in commit messages
        strategy: 'before_first_match' or 'before_last_match'

    Returns:
        Commit hash before the keyword match, or None if not found

    Raises:
        RuntimeError: If git operations fail

    """
    LOGGER.debug(
        'Searching for commit before "%s" keyword with strategy: %s',
        keyword,
        strategy,
    )

    # Get all commits containing the keyword
    matching_commits = await _get_commits_with_keyword(
        working_directory, keyword
    )

    if not matching_commits:
        LOGGER.debug('No commits found with keyword "%s"', keyword)
        return None

    # Select target commit based on strategy
    target_commit = _select_target_commit(matching_commits, strategy)

    LOGGER.debug(
        'Found %d commits with keyword "%s", using commit %s with strategy %s',
        len(matching_commits),
        keyword,
        target_commit[:8],
        strategy,
    )

    # Get the parent commit
    before_commit = await _get_parent_commit(working_directory, target_commit)

    if before_commit:
        LOGGER.debug(
            'Found commit before keyword match: %s (before %s)',
            before_commit[:8],
            target_commit[:8],
        )

    return before_commit


async def get_commits_since(
    working_directory: pathlib.Path, starting_commit: str | None
) -> models.GitCommitSummary:
    """Get detailed information about all commits since the starting commit.

    Args:
        working_directory: Git repository working directory
        starting_commit: Starting commit hash to compare from (None for
            no comparison)

    Returns:
        GitCommitSummary with detailed commit information and file changes

    Raises:
        RuntimeError: If git operations fail

    """
    LOGGER.debug(
        'Getting commits since %s in %s',
        starting_commit[:8] if starting_commit else 'None',
        working_directory,
    )

    # Get current HEAD commit
    current_commit = await _get_current_head_commit(working_directory)

    if not starting_commit:
        # No starting commit to compare from, return empty summary
        return models.GitCommitSummary(
            total_commits=0,
            commits=[],
            files_affected=[],
            commit_range=f'None..{current_commit}',
        )

    if current_commit == starting_commit:
        # No new commits
        return models.GitCommitSummary(
            total_commits=0,
            commits=[],
            files_affected=[],
            commit_range=f'{starting_commit}..{current_commit}',
        )

    # Get commit log with detailed format
    command = [
        'git',
        'log',
        f'{starting_commit}..HEAD',
        '--pretty=format:%H|%an|%ae|%cn|%ce|%at|%ct|%s|%b',
        '--name-status',
    ]

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=60
    )

    if returncode != 0:
        raise RuntimeError(
            f'Git log failed (exit code {returncode}): {stderr or stdout}'
        )

    if not stdout.strip():
        return models.GitCommitSummary(
            total_commits=0,
            commits=[],
            files_affected=[],
            commit_range=f'{starting_commit}..{current_commit}',
        )

    # Parse commits from output
    commits = _parse_commit_log_output(stdout)

    # Get diffs for each commit
    for commit in commits:
        await _add_diffs_to_commit(working_directory, commit)

    # Collect unique files affected
    files_affected = []
    for commit in commits:
        for file_change in commit.files_changed:
            if file_change.file_path not in files_affected:
                files_affected.append(file_change.file_path)

    return models.GitCommitSummary(
        total_commits=len(commits),
        commits=commits,
        files_affected=files_affected,
        commit_range=f'{starting_commit}..{current_commit}',
    )


async def _get_current_head_commit(working_directory: pathlib.Path) -> str:
    """Get the current HEAD commit hash."""
    command = ['git', 'rev-parse', 'HEAD']
    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=30
    )

    if returncode != 0:
        raise RuntimeError(
            f'Git rev-parse HEAD failed (exit code {returncode}): '
            f'{stderr or stdout}'
        )

    return stdout.strip()


async def _add_diffs_to_commit(
    working_directory: pathlib.Path, commit: models.GitCommit
) -> None:
    """Add diff content to each file change in a commit."""
    if not commit.files_changed:
        return

    # Get the diff for this specific commit
    command = ['git', 'show', '--format=', commit.hash]
    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=60
    )

    if returncode != 0:
        LOGGER.warning(
            'Failed to get diff for commit %s: %s',
            commit.hash[:8],
            stderr or stdout,
        )
        return

    # Parse the diff output to match with file changes
    diff_sections = _parse_diff_output(stdout)

    # Match diffs to file changes
    for file_change in commit.files_changed:
        # Look for diff section for this file
        file_diff = diff_sections.get(file_change.file_path)
        if file_diff:
            file_change.diff = file_diff


def _parse_diff_output(diff_output: str) -> dict[str, str]:
    """Parse git diff output into file-specific diffs."""
    file_diffs = {}
    if not diff_output.strip():
        return file_diffs

    lines = diff_output.split('\n')
    current_file = None
    current_diff_lines = []

    for line in lines:
        if line.startswith('diff --git'):
            # Save previous file's diff if any
            if current_file and current_diff_lines:
                file_diffs[current_file] = '\n'.join(current_diff_lines)

            # Extract file path from diff header
            # Format: diff --git a/path/file.py b/path/file.py
            parts = line.split(' ')
            if len(parts) >= 4:
                # Remove 'a/' prefix from path
                current_file = (
                    parts[2][2:] if parts[2].startswith('a/') else parts[2]
                )
            else:
                current_file = None
            current_diff_lines = [line]
        elif current_file:
            current_diff_lines.append(line)

    # Don't forget the last file
    if current_file and current_diff_lines:
        file_diffs[current_file] = '\n'.join(current_diff_lines)

    return file_diffs


def _parse_commit_log_output(output: str) -> list[models.GitCommit]:
    """Parse git log output into GitCommit objects."""
    commits = []
    lines = output.strip().split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Parse commit metadata line
        parts = line.split('|', 8)
        if len(parts) < 8:
            i += 1
            continue

        (
            commit_hash,
            author_name,
            author_email,
            committer_name,
            committer_email,
            author_ts,
            commit_ts,
            subject,
        ) = parts[:8]
        initial_body = parts[8] if len(parts) > 8 else ''

        # Parse timestamps
        author_date = datetime.datetime.fromtimestamp(
            int(author_ts), tz=datetime.UTC
        )
        commit_date = datetime.datetime.fromtimestamp(
            int(commit_ts), tz=datetime.UTC
        )

        # Collect body lines (everything until file changes or next commit)
        i += 1
        body_lines = [initial_body] if initial_body else []

        while i < len(lines):
            line = lines[i].strip()
            # Stop if we hit file status line or next commit metadata line
            if not line or '\t' in line or '|' in line:
                break
            body_lines.append(line)
            i += 1

        # Parse commit message body and trailers
        full_body = '\n'.join(body_lines).strip()
        commit_body, trailers = _parse_commit_body_and_trailers(full_body)

        # Parse file changes for this commit
        files_changed = []
        while i < len(lines) and lines[i].strip() and '\t' in lines[i]:
            file_line = lines[i].strip()
            file_change = _parse_file_change_line(file_line)
            if file_change:
                files_changed.append(file_change)
            i += 1

        commits.append(
            models.GitCommit(
                hash=commit_hash,
                author_name=author_name,
                author_email=author_email,
                committer_name=committer_name,
                committer_email=committer_email,
                author_date=author_date,
                commit_date=commit_date,
                subject=subject,
                body=commit_body,
                trailers=trailers,
                files_changed=files_changed,
            )
        )

    return commits


def _parse_commit_body_and_trailers(body: str) -> tuple[str, dict[str, str]]:
    """Parse commit body into body text and trailers."""
    if not body.strip():
        return '', {}

    lines = body.strip().split('\n')
    trailers = {}
    body_lines = []

    # Find trailers (lines with "Key: Value" format at end of commit)
    for line in reversed(lines):
        line = line.strip()
        if ':' in line and not line.startswith(' '):
            key, value = line.split(':', 1)
            trailers[key.strip()] = value.strip()
        else:
            # Not a trailer, rest is body
            body_lines = lines[: len(lines) - len(trailers)]
            break

    return '\n'.join(body_lines).strip(), trailers


def _parse_file_change_line(line: str) -> models.GitFileChange | None:
    """Parse a git --name-status file change line."""
    if not line.strip():
        return None

    parts = line.split('\t')
    if len(parts) < 2:
        return None

    status = parts[0]

    if status.startswith('R') and len(parts) >= 3:
        # For renames: R100 old_path new_path
        old_path = parts[1]
        file_path = parts[2]
    else:
        # For other changes: M file_path
        file_path = parts[1]
        old_path = None

    return models.GitFileChange(
        status=status, file_path=file_path, old_path=old_path
    )


async def extract_file_from_commit(
    working_directory: pathlib.Path,
    source_file: pathlib.Path,
    destination_file: pathlib.Path,
    commit_keyword: str | None = None,
    search_strategy: str = 'before_last_match',
) -> bool:
    """Extract a file from a git commit to a destination path.

    Args:
        working_directory: Git repository working directory
        source_file: Path to the file in the repository
        destination_file: Path where to write the extracted file
        commit_keyword: Keyword to search for in commit messages (optional)
        search_strategy: 'before_first_match' or 'before_last_match'

    Raises:
        RuntimeError: If commit not found, file doesn't exist, or git
            operations fail

    """
    # Find the commit to extract from
    if commit_keyword:
        target_commit = await find_commit_before_keyword(
            working_directory, commit_keyword, search_strategy
        )
        if not target_commit:
            raise RuntimeError(
                f'No commit found before keyword "{commit_keyword}" '
                f'using strategy "{search_strategy}"'
            )
    else:
        # If no keyword specified, use HEAD (current commit)
        target_commit = 'HEAD'

    LOGGER.debug(
        'Extracting %s from commit %s to %s',
        source_file,
        target_commit[:8] if target_commit != 'HEAD' else 'HEAD',
        destination_file,
    )

    # Extract the file content from the target commit
    file_content = await get_file_at_commit(
        working_directory, str(source_file), target_commit
    )

    if file_content is None:
        commit_display = (
            target_commit[:8] if target_commit != 'HEAD' else 'HEAD'
        )
        LOGGER.debug(
            'File "%s" does not exist at commit %s',
            source_file,
            commit_display,
        )
        return False

    # Ensure destination directory exists
    destination_file.parent.mkdir(parents=True, exist_ok=True)

    # Write the extracted content to destination
    destination_file.write_text(file_content, encoding='utf-8')

    LOGGER.debug(
        'Successfully extracted %s (%d bytes) to %s',
        source_file,
        len(file_content),
        destination_file,
    )
    return True


async def get_file_at_commit(
    working_directory: pathlib.Path, file_path: str, commit_hash: str
) -> str | None:
    """Get the content of a file at a specific commit.

    Args:
        working_directory: Git repository working directory
        file_path: Path to the file relative to repository root
        commit_hash: Git commit hash

    Returns:
        File content as string, or None if file doesn't exist at that commit

    Raises:
        RuntimeError: If git operations fail

    """
    LOGGER.debug(
        'Getting content of %s at commit %s', file_path, commit_hash[:8]
    )

    command = ['git', 'show', f'{commit_hash}:{file_path}']

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=30
    )

    if returncode != 0:
        if 'does not exist' in stderr or 'exists on disk' in stderr:
            LOGGER.debug(
                'File %s does not exist at commit %s',
                file_path,
                commit_hash[:8],
            )
            return None
        else:
            raise RuntimeError(
                f'Git show failed (exit code {returncode}): {stderr or stdout}'
            )

    LOGGER.debug(
        'Retrieved %d bytes of content for %s at commit %s',
        len(stdout),
        file_path,
        commit_hash[:8],
    )

    return stdout


async def delete_remote_branch_if_exists(
    working_directory: pathlib.Path, branch_name: str, remote: str = 'origin'
) -> bool:
    """Delete a remote branch if it exists.

    Args:
        working_directory: Git repository working directory
        branch_name: Name of the branch to delete
        remote: Remote name (default: 'origin')

    Returns:
        True if branch was deleted or didn't exist, False if deletion failed

    """
    LOGGER.debug(
        'Checking if remote branch %s/%s exists for deletion',
        remote,
        branch_name,
    )

    # Check if remote branch exists
    command = ['git', 'ls-remote', '--heads', remote, branch_name]

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=30
    )

    if returncode != 0:
        LOGGER.debug(
            'Could not check remote branch %s/%s: %s',
            remote,
            branch_name,
            stderr or stdout,
        )
        return True  # Assume it doesn't exist

    if not stdout.strip():
        LOGGER.debug('Remote branch %s/%s does not exist', remote, branch_name)
        return True  # Branch doesn't exist, nothing to delete

    # Branch exists, delete it
    LOGGER.info('Deleting existing remote branch %s/%s', remote, branch_name)

    command = ['git', 'push', remote, '--delete', branch_name]

    returncode, stdout, stderr = await _run_git_command(
        command, cwd=working_directory, timeout_seconds=60
    )

    if returncode == 0:
        LOGGER.debug(
            'Successfully deleted remote branch %s/%s', remote, branch_name
        )
        return True
    else:
        LOGGER.warning(
            'Failed to delete remote branch %s/%s: %s',
            remote,
            branch_name,
            stderr or stdout,
        )
        return False
