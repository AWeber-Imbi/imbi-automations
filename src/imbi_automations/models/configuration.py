"""Configuration models with Pydantic validation.

Defines configuration data models for all external integrations including
Anthropic, GitHub, GitLab, Imbi, Claude Code, and SonarQube. All models
use Pydantic for validation with SecretStr for sensitive data and
environment variable defaults.
"""

import os
import pathlib
import typing

import pydantic


class AnthropicConfiguration(pydantic.BaseModel):
    """Anthropic API configuration for Claude models.

    Supports both direct API access and AWS Bedrock integration with
    configurable model selection and API key from environment variables.
    """

    api_key: pydantic.SecretStr | None = pydantic.Field(
        default=os.environ.get('ANTHROPIC_API_KEY')
    )
    bedrock: bool = False
    model: str = pydantic.Field(default='claude-3-5-haiku-latest')


class GitConfiguration(pydantic.BaseModel):
    """Git configuration for repository operations.

    Controls git commit behavior including additional arguments for signing.
    """

    commit_args: str = ''


class GitHubConfiguration(pydantic.BaseModel):
    """GitHub API configuration.

    Supports both GitHub.com and GitHub Enterprise with API token
    authentication.
    """

    api_key: pydantic.SecretStr
    hostname: str = pydantic.Field(default='github.com')


class GitLabConfiguration(pydantic.BaseModel):
    """GitLab API configuration.

    Supports both GitLab.com and self-hosted instances with private token auth.
    """

    api_key: pydantic.SecretStr
    hostname: str = pydantic.Field(default='gitlab.com')


class ImbiConfiguration(pydantic.BaseModel):
    """Imbi project management system configuration.

    Defines project identifiers and link types for mapping external systems
    (GitHub, GitLab, PagerDuty, SonarQube, Sentry, Grafana) to Imbi projects.
    """

    api_key: pydantic.SecretStr
    hostname: str
    github_identifier: str = 'github'
    gitlab_identifier: str = 'gitlab'
    pagerduty_identifier: str = 'pagerduty'
    sonarqube_identifier: str = 'sonarqube'
    sentry_identifier: str = 'sentry'
    github_link: str = 'GitHub Repository'
    gitlab_link: str = 'GitLab Project'
    grafana_link: str = 'Grafana Dashboard'
    pagerduty_link: str = 'PagerDuty'
    sentry_link: str = 'Sentry'
    sonarqube_link: str = 'SonarQube'


class ClaudeCodeConfiguration(pydantic.BaseModel):
    """Claude Code SDK configuration.

    Configures the Claude Code executable path, base prompt file, and
    whether AI-powered transformations are enabled for workflows.
    """

    executable: str = 'claude'  # Claude Code executable path
    base_prompt: pathlib.Path | None = None
    enabled: bool = True

    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(**kwargs)
        # Set default base_prompt to claude.md in prompts directory
        # if not specified
        if self.base_prompt is None:
            self.base_prompt = (
                pathlib.Path(__file__).parent / 'prompts' / 'claude.md'
            )


class Configuration(pydantic.BaseModel):
    """Main application configuration.

    Root configuration object combining all integration configurations with
    global settings for commits, error handling, and workflow execution.
    """

    ai_commits: bool = False
    anthropic: AnthropicConfiguration = pydantic.Field(
        default_factory=AnthropicConfiguration
    )
    cache_dir: pathlib.Path = (
        pathlib.Path.home() / '.cache' / 'imbi-automations'
    )
    claude_code: ClaudeCodeConfiguration = pydantic.Field(
        default_factory=ClaudeCodeConfiguration
    )
    commit_author: str = 'Imbi Automations <noreply@aweber.com>'
    error_dir: pathlib.Path = pathlib.Path('./errors')
    git: GitConfiguration = pydantic.Field(default_factory=GitConfiguration)
    github: GitHubConfiguration | None = None
    gitlab: GitLabConfiguration | None = None
    imbi: ImbiConfiguration | None = None
    preserve_on_error: bool = False
