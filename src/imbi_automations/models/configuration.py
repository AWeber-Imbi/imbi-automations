"""Configuration models with Pydantic validation.

Defines configuration data models for all external integrations including
Anthropic, GitHub, Imbi, Claude Code, and SonarQube. All models use Pydantic
for validation with SecretStr for sensitive data and environment variable
defaults.
"""

import pathlib
import typing

import pydantic
import pydantic_settings

from . import claude as claude_models

BASE_SETTINGS = {
    'case_sensitive': False,
    'env_file': '.env',
    'env_file_encoding': 'utf-8',
    'extra': 'ignore',
}


class AnthropicConfiguration(pydantic_settings.BaseSettings):
    """Anthropic API configuration for Claude models.

    Supports both direct API access and AWS Bedrock integration with
    configurable model selection and API key from environment variables.
    """

    model_config = pydantic_settings.SettingsConfigDict(
        env_prefix='ANTHROPIC_', **BASE_SETTINGS
    )

    api_key: pydantic.SecretStr | None = None
    bedrock: bool = False
    model: str = 'claude-haiku-4-5-20251001'


class ClaudeAgentConfiguration(pydantic_settings.BaseSettings):
    """Claude Agent SDK configuration.

    Configures the Claude Agent SDK executable path, base prompt file, model
    selection, whether AI-powered transformations are enabled, and
    marketplace/plugin settings.

    Plugin configuration supports:
    - enabled_plugins: Map of "plugin@marketplace" to enabled state
    - marketplaces: Additional marketplace sources to register
    - local_plugins: Local plugin directories loaded via SDK

    Example TOML:
        [claude]
        model = "claude-sonnet-4"

        [claude.plugins.enabled_plugins]
        "code-formatter@team-tools" = true

        [claude.plugins.marketplaces.team-tools]
        source = "github"
        repo = "company/claude-plugins"

        [[claude.plugins.local_plugins]]
        path = "/path/to/local/plugin"
    """

    model_config = pydantic_settings.SettingsConfigDict(
        env_prefix='CLAUDE_', **BASE_SETTINGS
    )

    executable: str = 'claude'  # Claude Code executable path
    base_prompt: pathlib.Path | None = None
    enabled: bool = True
    model: str = pydantic.Field(default='claude-haiku-4-5')
    plugins: claude_models.ClaudePluginConfig = pydantic.Field(
        default_factory=claude_models.ClaudePluginConfig
    )

    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(**kwargs)
        if self.base_prompt is None:
            self.base_prompt = (
                pathlib.Path(__file__).parent / 'prompts' / 'claude.md'
            )


class GitConfiguration(pydantic_settings.BaseSettings):
    """Git configuration for repository operations.

    Controls git commit behavior including signing with GPG or SSH keys.
    Supports multiple signing formats: 'gpg', 'ssh', 'x509', 'openpgp'.
    """

    model_config = pydantic_settings.SettingsConfigDict(
        env_prefix='GIT_', **BASE_SETTINGS
    )

    commit_args: str = ''
    gpg_sign: bool = False
    gpg_format: str | None = None
    signing_key: str | None = None
    ssh_program: str | None = None
    gpg_program: str | None = None
    user_name: str = 'Imbi Automations'
    user_email: str = 'automations@imbi.ai'


class GitHubConfiguration(pydantic_settings.BaseSettings):
    """GitHub API configuration.

    Supports both GitHub.com and GitHub Enterprise with API token
    authentication.
    """

    model_config = pydantic_settings.SettingsConfigDict(
        env_prefix='GH_', **BASE_SETTINGS
    )

    host: str = pydantic.Field(default='github.com')
    token: pydantic.SecretStr


class ImbiConfiguration(pydantic_settings.BaseSettings):
    """Imbi project management system configuration.

    Defines project identifiers and link types for mapping external systems
    (GitHub, GitLab, PagerDuty, SonarQube, Sentry, Grafana) to Imbi projects.
    """

    model_config = pydantic_settings.SettingsConfigDict(
        env_prefix='IMBI_', **BASE_SETTINGS
    )

    api_key: pydantic.SecretStr
    hostname: str
    github_identifier: str = 'github'
    pagerduty_identifier: str = 'pagerduty'
    sonarqube_identifier: str = 'sonarqube'
    sentry_identifier: str = 'sentry'
    github_link: str = 'GitHub Repository'
    grafana_link: str = 'Grafana Dashboard'
    pagerduty_link: str = 'PagerDuty'
    sentry_link: str = 'Sentry'
    sonarqube_link: str = 'SonarQube'


class Configuration(pydantic.BaseModel):
    """Main application configuration.

    Root configuration object combining all integration configurations with
    global settings for commits, error handling, and workflow execution.

    Uses a model validator to properly merge environment variables with
    config file values. When a nested settings section is provided in the
    config file, environment variables serve as defaults for any fields
    not explicitly set in the file.
    """

    @pydantic.model_validator(mode='before')
    @classmethod
    def merge_env_with_config(
        cls, data: dict[str, typing.Any]
    ) -> dict[str, typing.Any]:
        """Merge environment variables with config file data.

        For each BaseSettings submodel, instantiate it with the config file
        data as kwargs. This allows BaseSettings to use environment variables
        as defaults for any fields not provided in the config file.

        Args:
            data: Raw config data from TOML file

        Returns:
            Config data with BaseSettings instances properly constructed

        """
        settings_fields: dict[str, type[pydantic_settings.BaseSettings]] = {
            'anthropic': AnthropicConfiguration,
            'claude': ClaudeAgentConfiguration,
            'git': GitConfiguration,
            'github': GitHubConfiguration,
            'imbi': ImbiConfiguration,
        }
        for field, settings_cls in settings_fields.items():
            if field in data and data[field] is not None:
                # Skip if already an instance (e.g., from direct construction)
                if isinstance(data[field], settings_cls):
                    continue
                data[field] = settings_cls(**data[field])
        return data

    ai_commits: bool = False
    anthropic: AnthropicConfiguration = pydantic.Field(
        default_factory=AnthropicConfiguration
    )
    cache_dir: pathlib.Path = (
        pathlib.Path.home() / '.cache' / 'imbi-automations'
    )
    claude: ClaudeAgentConfiguration = pydantic.Field(
        default_factory=ClaudeAgentConfiguration
    )
    dry_run: bool = False
    dry_run_dir: pathlib.Path = pathlib.Path('./dry-runs')
    error_dir: pathlib.Path = pathlib.Path('./errors')
    git: GitConfiguration = pydantic.Field(default_factory=GitConfiguration)
    github: GitHubConfiguration | None = None
    imbi: ImbiConfiguration | None = None
    preserve_on_error: bool = False
