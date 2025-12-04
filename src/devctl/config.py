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


class K8sConfig(BaseModel):
    """Kubernetes configuration."""

    kubeconfig: str | None = None
    context: str | None = None
    namespace: str = "default"
    timeout: int = 30

    def get_kubeconfig(self) -> str | None:
        """Get kubeconfig path from config or environment."""
        return (
            os.environ.get("DEVCTL_KUBECONFIG")
            or os.environ.get("KUBECONFIG")
            or self.kubeconfig
        )

    def get_context(self) -> str | None:
        """Get k8s context from config or environment."""
        return (
            os.environ.get("DEVCTL_K8S_CONTEXT")
            or os.environ.get("K8S_CONTEXT")
            or self.context
        )

    def get_namespace(self) -> str:
        """Get default namespace from config or environment."""
        return (
            os.environ.get("DEVCTL_K8S_NAMESPACE")
            or os.environ.get("K8S_NAMESPACE")
            or self.namespace
        )


class PagerDutyConfig(BaseModel):
    """PagerDuty configuration."""

    api_key: str | None = None
    service_id: str | None = None
    email: str | None = None
    timeout: int = 30

    def get_api_key(self) -> str | None:
        """Get API key from config or environment."""
        key = self.api_key
        if key == "from_env" or key is None:
            key = (
                os.environ.get("DEVCTL_PAGERDUTY_API_KEY")
                or os.environ.get("PAGERDUTY_API_KEY")
                or os.environ.get("PD_API_KEY")
            )
        return key

    def get_service_id(self) -> str | None:
        """Get default service ID."""
        return (
            os.environ.get("DEVCTL_PAGERDUTY_SERVICE_ID")
            or os.environ.get("PAGERDUTY_SERVICE_ID")
            or self.service_id
        )

    def get_email(self) -> str | None:
        """Get user email for API requests."""
        return (
            os.environ.get("DEVCTL_PAGERDUTY_EMAIL")
            or os.environ.get("PAGERDUTY_EMAIL")
            or self.email
        )


class LogsConfig(BaseModel):
    """Unified logs configuration."""

    default_source: str = "cloudwatch"  # cloudwatch, loki, eks
    default_time_range: str = "1h"
    max_results: int = 1000
    cloudwatch_log_group_prefix: str | None = None
    loki_datasource_uid: str | None = None
    eks_cluster: str | None = None
    eks_namespace: str = "default"


class ArgoCDConfig(BaseModel):
    """ArgoCD configuration."""

    url: str | None = None
    token: str | None = None
    insecure: bool = False
    timeout: int = 30

    def get_url(self) -> str | None:
        """Get ArgoCD URL from config or environment."""
        return (
            os.environ.get("DEVCTL_ARGOCD_URL")
            or os.environ.get("ARGOCD_SERVER")
            or self.url
        )

    def get_token(self) -> str | None:
        """Get ArgoCD token from config or environment."""
        token = self.token
        if token == "from_env" or token is None:
            token = (
                os.environ.get("DEVCTL_ARGOCD_TOKEN")
                or os.environ.get("ARGOCD_AUTH_TOKEN")
            )
        return token


class CanaryMetricConfig(BaseModel):
    """Canary metric configuration."""

    name: str
    threshold: float
    source: str = "prometheus"
    query: str | None = None


class CanaryStrategyConfig(BaseModel):
    """Canary deployment strategy configuration."""

    initial_weight: int = 10
    increment: int = 15
    interval: int = 300  # seconds
    max_weight: int = 100
    metrics: list[CanaryMetricConfig] = Field(default_factory=list)


class BlueGreenStrategyConfig(BaseModel):
    """Blue/Green deployment strategy configuration."""

    switch_timeout: int = 300
    rollback_window: int = 3600  # Keep blue for 1 hour


class RollingStrategyConfig(BaseModel):
    """Rolling deployment strategy configuration."""

    max_unavailable: str = "25%"
    max_surge: str = "25%"


class DeployConfig(BaseModel):
    """Deployment orchestration configuration."""

    cluster: str | None = None
    namespace: str = "default"
    kubeconfig: str | None = None
    canary: CanaryStrategyConfig = Field(default_factory=CanaryStrategyConfig)
    blue_green: BlueGreenStrategyConfig = Field(default_factory=BlueGreenStrategyConfig)
    rolling: RollingStrategyConfig = Field(default_factory=RollingStrategyConfig)

    def get_cluster(self) -> str | None:
        """Get cluster from config or environment."""
        return os.environ.get("DEVCTL_DEPLOY_CLUSTER") or self.cluster


class SlackConfig(BaseModel):
    """Slack configuration."""

    token: str | None = None
    default_channel: str = "#devops"
    username: str = "DevCtl Bot"
    icon_emoji: str = ":robot_face:"
    timeout: int = 30

    def get_token(self) -> str | None:
        """Get Slack bot token from config or environment."""
        token = self.token
        if token == "from_env" or token is None:
            token = (
                os.environ.get("DEVCTL_SLACK_TOKEN")
                or os.environ.get("SLACK_BOT_TOKEN")
                or os.environ.get("SLACK_TOKEN")
            )
        return token


class ConfluenceConfig(BaseModel):
    """Confluence Cloud configuration."""

    url: str | None = None
    email: str | None = None
    api_token: str | None = None
    default_space: str | None = None
    timeout: int = 30

    def get_url(self) -> str | None:
        """Get Confluence URL from config or environment."""
        return (
            os.environ.get("DEVCTL_CONFLUENCE_URL")
            or os.environ.get("CONFLUENCE_URL")
            or self.url
        )

    def get_email(self) -> str | None:
        """Get Confluence email from config or environment."""
        return (
            os.environ.get("DEVCTL_CONFLUENCE_EMAIL")
            or os.environ.get("CONFLUENCE_EMAIL")
            or self.email
        )

    def get_api_token(self) -> str | None:
        """Get Confluence API token from config or environment."""
        token = self.api_token
        if token == "from_env" or token is None:
            token = (
                os.environ.get("DEVCTL_CONFLUENCE_API_TOKEN")
                or os.environ.get("CONFLUENCE_API_TOKEN")
            )
        return token


class PCIComplianceConfig(BaseModel):
    """PCI DSS compliance configuration."""

    enabled_controls: list[str] | str = "all"  # all or list of control IDs
    exclude_resources: list[str] = Field(default_factory=list)  # ARNs to skip
    report_bucket: str | None = None  # S3 bucket for reports
    severity_threshold: str = "low"  # minimum severity to report


class ComplianceNotificationConfig(BaseModel):
    """Compliance notification configuration."""

    slack_channel: str | None = None
    email: str | None = None


class ComplianceConfig(BaseModel):
    """Compliance configuration."""

    pci: PCIComplianceConfig = Field(default_factory=PCIComplianceConfig)
    notifications: ComplianceNotificationConfig = Field(default_factory=ComplianceNotificationConfig)


class ProfileConfig(BaseModel):
    """Profile configuration grouping all service settings."""

    aws: AWSConfig = Field(default_factory=AWSConfig)
    grafana: GrafanaConfig = Field(default_factory=GrafanaConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    jira: JiraConfig = Field(default_factory=JiraConfig)
    k8s: K8sConfig = Field(default_factory=K8sConfig)
    pagerduty: PagerDutyConfig = Field(default_factory=PagerDutyConfig)
    logs: LogsConfig = Field(default_factory=LogsConfig)
    argocd: ArgoCDConfig = Field(default_factory=ArgoCDConfig)
    deploy: DeployConfig = Field(default_factory=DeployConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    confluence: ConfluenceConfig = Field(default_factory=ConfluenceConfig)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)


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
