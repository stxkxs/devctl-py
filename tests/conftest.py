"""Pytest fixtures for devctl tests."""

import os
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from devctl.cli import cli
from devctl.config import (
    DevCtlConfig,
    ProfileConfig,
    AWSConfig,
    GrafanaConfig,
    GitHubConfig,
    JiraConfig,
    K8sConfig,
    PagerDutyConfig,
    ArgoCDConfig,
    SlackConfig,
    ConfluenceConfig,
    LogsConfig,
    DeployConfig,
    ComplianceConfig,
)
from devctl.core.context import DevCtlContext
from devctl.core.output import OutputFormat


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_config() -> DevCtlConfig:
    """Create a mock configuration."""
    return DevCtlConfig(
        profiles={
            "default": ProfileConfig(
                aws=AWSConfig(profile="test", region="us-east-1"),
                grafana=GrafanaConfig(url="https://test.grafana.net"),
                github=GitHubConfig(org="test-org"),
                jira=JiraConfig(url="https://test.atlassian.net"),
                k8s=K8sConfig(namespace="default"),
                pagerduty=PagerDutyConfig(api_key="test-key"),
                argocd=ArgoCDConfig(url="https://argocd.test.com"),
                slack=SlackConfig(token="xoxb-test"),
                confluence=ConfluenceConfig(url="https://test.atlassian.net/wiki"),
                logs=LogsConfig(),
                deploy=DeployConfig(),
                compliance=ComplianceConfig(),
            )
        }
    )


@pytest.fixture
def mock_context(mock_config: DevCtlConfig) -> DevCtlContext:
    """Create a mock DevCtl context."""
    return DevCtlContext(
        config=mock_config,
        profile="default",
        output_format=OutputFormat.TABLE,
        verbose=0,
        quiet=False,
        dry_run=False,
        color=False,
    )


@pytest.fixture
def mock_aws_client() -> Generator[MagicMock, None, None]:
    """Mock boto3 client."""
    with patch("boto3.Session") as mock_session:
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_grafana_client() -> Generator[MagicMock, None, None]:
    """Mock Grafana HTTP client."""
    with patch("httpx.Client") as mock_client:
        yield mock_client.return_value


@pytest.fixture
def mock_github_client() -> Generator[MagicMock, None, None]:
    """Mock GitHub HTTP client."""
    with patch("httpx.Client") as mock_client:
        yield mock_client.return_value


@pytest.fixture
def mock_k8s_client() -> Generator[MagicMock, None, None]:
    """Mock Kubernetes client."""
    with patch("kubernetes.client.CoreV1Api") as mock_core, \
         patch("kubernetes.client.AppsV1Api") as mock_apps, \
         patch("kubernetes.config.load_kube_config"):
        mock_core_instance = MagicMock()
        mock_apps_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_apps.return_value = mock_apps_instance
        yield {"core": mock_core_instance, "apps": mock_apps_instance}


@pytest.fixture
def mock_pagerduty_client() -> Generator[MagicMock, None, None]:
    """Mock PagerDuty HTTP client."""
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_argocd_client() -> Generator[MagicMock, None, None]:
    """Mock ArgoCD HTTP client."""
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_slack_client() -> Generator[MagicMock, None, None]:
    """Mock Slack HTTP client."""
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_confluence_client() -> Generator[MagicMock, None, None]:
    """Mock Confluence HTTP client."""
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture(autouse=True)
def clean_env() -> Generator[None, None, None]:
    """Clean environment variables before each test."""
    env_vars = [
        "DEVCTL_AWS_PROFILE",
        "DEVCTL_AWS_REGION",
        "DEVCTL_GRAFANA_API_KEY",
        "DEVCTL_GITHUB_TOKEN",
        "DEVCTL_JIRA_API_TOKEN",
        "DEVCTL_PAGERDUTY_API_KEY",
        "DEVCTL_ARGOCD_TOKEN",
        "DEVCTL_SLACK_TOKEN",
        "DEVCTL_CONFLUENCE_API_TOKEN",
        "AWS_PROFILE",
        "AWS_REGION",
        "GRAFANA_API_KEY",
        "GITHUB_TOKEN",
        "KUBECONFIG",
    ]

    original = {k: os.environ.get(k) for k in env_vars}

    # Remove vars for clean test
    for k in env_vars:
        os.environ.pop(k, None)

    yield

    # Restore original values
    for k, v in original.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file."""
    config_content = """
version: "1"
global:
  output_format: table
profiles:
  default:
    aws:
      profile: test
      region: us-east-1
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)
    return str(config_file)
