"""Pytest fixtures for devctl tests."""

import os
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from devctl.cli import cli
from devctl.config import DevCtlConfig, ProfileConfig, AWSConfig, GrafanaConfig, GitHubConfig
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


@pytest.fixture(autouse=True)
def clean_env() -> Generator[None, None, None]:
    """Clean environment variables before each test."""
    env_vars = [
        "DEVCTL_AWS_PROFILE",
        "DEVCTL_AWS_REGION",
        "DEVCTL_GRAFANA_API_KEY",
        "DEVCTL_GITHUB_TOKEN",
        "AWS_PROFILE",
        "AWS_REGION",
        "GRAFANA_API_KEY",
        "GITHUB_TOKEN",
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
