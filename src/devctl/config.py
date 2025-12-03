"""Configuration management for devctl using Pydantic."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from devctl.core.exceptions import ConfigError
from devctl.core.output import OutputFormat
from devctl.core.logging import LogLevel


class AWSConfig(BaseModel):
    """AWS configuration."""

    profile: str | None = None
    region: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None
    endpoint_url: str | None = None

    def get_profile(self) -> str | None:
        """Get AWS profile from config or environment."""
        return (
            os.environ.get("DEVCTL_AWS_PROFILE")
            or os.environ.get("AWS_PROFILE")
            or self.profile
        )

    def get_region(self) -> str | None:
        """Get AWS region from config or environment."""
        return (
            os.environ.get("DEVCTL_AWS_REGION")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or self.region
        )


class GrafanaConfig(BaseModel):
    """Grafana configuration."""

    url: str | None = None
    api_key: str | None = None
    org_id: int | None = None
    timeout: int = 30

    def get_url(self) -> str | None:
        """Get Grafana URL from config or environment."""
        return os.environ.get("DEVCTL_GRAFANA_URL") or os.environ.get("GRAFANA_URL") or self.url

    def get_api_key(self) -> str | None:
        """Get API key from config or environment."""
        key = self.api_key
        if key == "from_env" or key is None:
            key = os.environ.get("DEVCTL_GRAFANA_API_KEY") or os.environ.get("GRAFANA_API_KEY")
        return key


class GitHubConfig(BaseModel):
    """GitHub configuration."""

    token: str | None = None
    org: str | None = None
    base_url: str = "https://api.github.com"
    timeout: int = 30

    def get_token(self) -> str | None:
        """Get GitHub token from config or environment."""
        token = self.token
        if token == "from_env" or token is None:
            token = (
                os.environ.get("DEVCTL_GITHUB_TOKEN")
                or os.environ.get("GITHUB_TOKEN")
                or os.environ.get("GH_TOKEN")
            )
        return token

    def get_org(self) -> str | None:
        """Get GitHub org from config or environment."""
        return os.environ.get("DEVCTL_GITHUB_ORG") or os.environ.get("GITHUB_ORG") or self.org


class JiraConfig(BaseModel):
    """Jira Cloud configuration."""

    url: str | None = None
    email: str | None = None
    api_token: str | None = None
    timeout: int = 30

    def get_url(self) -> str | None:
        """Get Jira URL from config or environment."""
        return (
            os.environ.get("DEVCTL_JIRA_URL")
            or os.environ.get("JIRA_URL")
            or self.url
        )

    def get_email(self) -> str | None:
        """Get Jira email from config or environment."""
        return (
            os.environ.get("DEVCTL_JIRA_EMAIL")
            or os.environ.get("JIRA_EMAIL")
            or self.email
        )

    def get_api_token(self) -> str | None:
        """Get Jira API token from config or environment."""
        token = self.api_token
        if token == "from_env" or token is None:
            token = (
                os.environ.get("DEVCTL_JIRA_API_TOKEN")
                or os.environ.get("JIRA_API_TOKEN")
            )
        return token


class ProfileConfig(BaseModel):
    """Profile configuration grouping AWS, Grafana, GitHub, and Jira settings."""

    aws: AWSConfig = Field(default_factory=AWSConfig)
    grafana: GrafanaConfig = Field(default_factory=GrafanaConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    jira: JiraConfig = Field(default_factory=JiraConfig)


class GlobalConfig(BaseModel):
    """Global settings."""

    output_format: OutputFormat = OutputFormat.TABLE
    color: str = "auto"  # auto, always, never
    verbosity: LogLevel = LogLevel.INFO
    dry_run: bool = False
    confirm_destructive: bool = True
    timeout: int = 300

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if v not in ("auto", "always", "never"):
            raise ValueError("color must be 'auto', 'always', or 'never'")
        return v


class WorkflowStep(BaseModel):
    """Single step in a workflow."""

    name: str
    command: str
    params: dict[str, Any] = Field(default_factory=dict)
    on_failure: str = "fail"  # fail, continue, skip
    condition: str | None = None
    timeout: int | None = None


class WorkflowConfig(BaseModel):
    """Workflow definition."""

    description: str = ""
    steps: list[WorkflowStep] = Field(default_factory=list)
    vars: dict[str, Any] = Field(default_factory=dict)


class DevCtlConfig(BaseModel):
    """Main configuration model."""

    model_config = {"populate_by_name": True}

    version: str = "1"
    global_settings: GlobalConfig = Field(default_factory=GlobalConfig, alias="global")
    profiles: dict[str, ProfileConfig] = Field(default_factory=lambda: {"default": ProfileConfig()})
    workflows: dict[str, WorkflowConfig] = Field(default_factory=dict)

    def get_profile(self, name: str | None = None) -> ProfileConfig:
        """Get a profile by name, defaulting to 'default'."""
        profile_name = name or "default"
        if profile_name not in self.profiles:
            raise ConfigError(f"Profile '{profile_name}' not found")
        return self.profiles[profile_name]


class ConfigLoader:
    """Loads and merges configuration from multiple sources."""

    CONFIG_FILENAMES = ["devctl.yaml", "devctl.yml", ".devctl.yaml", ".devctl.yml"]

    def __init__(self):
        self._config: DevCtlConfig | None = None

    def load(
        self,
        config_file: str | Path | None = None,
        profile: str | None = None,
    ) -> DevCtlConfig:
        """Load configuration from files and environment.

        Priority (highest to lowest):
        1. Explicitly specified config file
        2. Project config (./devctl.yaml)
        3. User config (~/.devctl/config.yaml)

        Args:
            config_file: Optional explicit config file path
            profile: Profile name to use

        Returns:
            Merged configuration
        """
        configs: list[dict[str, Any]] = []

        # Load user config
        user_config_path = Path.home() / ".devctl" / "config.yaml"
        if user_config_path.exists():
            configs.append(self._load_yaml_file(user_config_path))

        # Load project config
        project_config = self._find_project_config()
        if project_config:
            configs.append(self._load_yaml_file(project_config))

        # Load explicit config file
        if config_file:
            config_path = Path(config_file)
            if not config_path.exists():
                raise ConfigError(f"Config file not found: {config_file}")
            configs.append(self._load_yaml_file(config_path))

        # Merge all configs
        merged = self._merge_configs(configs)

        # Create config object
        self._config = DevCtlConfig(**merged)
        return self._config

    def _find_project_config(self) -> Path | None:
        """Find project config file in current or parent directories."""
        current = Path.cwd()

        while current != current.parent:
            for filename in self.CONFIG_FILENAMES:
                config_path = current / filename
                if config_path.exists():
                    return config_path
            current = current.parent

        return None

    def _load_yaml_file(self, path: Path) -> dict[str, Any]:
        """Load a YAML config file."""
        try:
            with open(path) as f:
                content = yaml.safe_load(f) or {}
                return content
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {path}: {e}")
        except OSError as e:
            raise ConfigError(f"Cannot read {path}: {e}")

    def _merge_configs(self, configs: list[dict[str, Any]]) -> dict[str, Any]:
        """Deep merge multiple configuration dictionaries."""
        result: dict[str, Any] = {}
        for config in configs:
            result = self._deep_merge(result, config)
        return result

    def _deep_merge(
        self,
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result


# Global config loader instance
_config_loader = ConfigLoader()


def load_config(
    config_file: str | Path | None = None,
    profile: str | None = None,
) -> DevCtlConfig:
    """Load devctl configuration.

    Args:
        config_file: Optional explicit config file path
        profile: Profile name to use

    Returns:
        Loaded configuration
    """
    return _config_loader.load(config_file, profile)


def get_default_config() -> DevCtlConfig:
    """Get default configuration without loading from files."""
    return DevCtlConfig()
