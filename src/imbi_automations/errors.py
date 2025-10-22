"""Common Exceptions"""


class ActionFailureException(Exception):
    """Exception raised when an action fails with on_failure configuration."""

    def __init__(
        self, action_name: str, restart_from: str, failure_details: str
    ) -> None:
        self.action_name = action_name
        self.restart_from = restart_from
        self.failure_details = failure_details
        super().__init__(
            f'Action {action_name} failed, restart from {restart_from}'
        )


class ConfigurationError(Exception):
    """Raised when there is a configuration error."""

    pass


class GitHubRateLimitError(Exception):
    """Raised when GitHub API rate limit is exceeded."""

    def __init__(self, message: str, reset_time: str | None = None) -> None:
        super().__init__(message)
        self.reset_time = reset_time


class GitHubNotFoundError(Exception):
    """Raised when GitHub repository is not found (404)."""

    pass
