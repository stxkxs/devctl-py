"""Tests for configuration management."""

import os
from pathlib import Path

import pytest
import yaml

from devctl.config import (
    DevCtlConfig,
    ProfileConfig,
    AWSConfig,
    GrafanaConfig,
    GitHubConfig,
    GlobalConfig,
    ConfigLoader,
    load_config,
    get_default_config,
)
from devctl.core.exceptions import ConfigError
from devctl.core.output import OutputFormat


class TestAWSConfig:
    """Tests for AWSConfig."""

    def test_default_values(self):
        config = AWSConfig()
        assert config.profile is None
        assert config.region is None

    def test_get_profile_from_config(self):
        config = AWSConfig(profile="test-profile")
        assert config.get_profile() == "test-profile"

    def test_get_profile_from_env(self):
        os.environ["DEVCTL_AWS_PROFILE"] = "env-profile"
        config = AWSConfig(profile="config-profile")
        assert config.get_profile() == "env-profile"
        del os.environ["DEVCTL_AWS_PROFILE"]

    def test_get_region_from_config(self):
        config = AWSConfig(region="us-west-2")
        assert config.get_region() == "us-west-2"

    def test_get_region_from_env(self):
        os.environ["DEVCTL_AWS_REGION"] = "eu-west-1"
        config = AWSConfig(region="us-east-1")
        assert config.get_region() == "eu-west-1"
        del os.environ["DEVCTL_AWS_REGION"]


class TestGrafanaConfig:
    """Tests for GrafanaConfig."""

    def test_default_values(self):
        config = GrafanaConfig()
        assert config.url is None
        assert config.api_key is None
        assert config.timeout == 30

    def test_get_url_from_config(self):
        config = GrafanaConfig(url="https://test.grafana.net")
        assert config.get_url() == "https://test.grafana.net"

    def test_get_api_key_from_env(self):
        os.environ["GRAFANA_API_KEY"] = "test-key"
        config = GrafanaConfig(api_key="from_env")
        assert config.get_api_key() == "test-key"
        del os.environ["GRAFANA_API_KEY"]


class TestGitHubConfig:
    """Tests for GitHubConfig."""

    def test_default_values(self):
        config = GitHubConfig()
        assert config.token is None
        assert config.org is None
        assert config.base_url == "https://api.github.com"

    def test_get_token_from_env(self):
        os.environ["GITHUB_TOKEN"] = "ghp_test"
        config = GitHubConfig(token="from_env")
        assert config.get_token() == "ghp_test"
        del os.environ["GITHUB_TOKEN"]

    def test_get_org_from_config(self):
        config = GitHubConfig(org="test-org")
        assert config.get_org() == "test-org"


class TestGlobalConfig:
    """Tests for GlobalConfig."""

    def test_default_values(self):
        config = GlobalConfig()
        assert config.output_format == OutputFormat.TABLE
        assert config.color == "auto"
        assert config.dry_run is False
        assert config.confirm_destructive is True

    def test_invalid_color(self):
        with pytest.raises(ValueError):
            GlobalConfig(color="invalid")


class TestDevCtlConfig:
    """Tests for DevCtlConfig."""

    def test_default_profile(self):
        config = DevCtlConfig()
        assert "default" in config.profiles
        profile = config.get_profile()
        assert isinstance(profile, ProfileConfig)

    def test_get_profile_not_found(self):
        config = DevCtlConfig()
        with pytest.raises(ConfigError):
            config.get_profile("nonexistent")

    def test_multiple_profiles(self):
        config = DevCtlConfig(
            profiles={
                "default": ProfileConfig(),
                "production": ProfileConfig(
                    aws=AWSConfig(profile="prod", region="us-west-2")
                ),
            }
        )
        prod = config.get_profile("production")
        assert prod.aws.profile == "prod"


class TestConfigLoader:
    """Tests for ConfigLoader."""

    def test_load_from_file(self, tmp_path: Path):
        config_content = {
            "version": "1",
            "global": {"output_format": "json"},
            "profiles": {
                "default": {
                    "aws": {"profile": "test", "region": "us-east-1"}
                }
            },
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_content))

        loader = ConfigLoader()
        config = loader.load(str(config_file))

        assert config.global_settings.output_format == OutputFormat.JSON
        assert config.profiles["default"].aws.profile == "test"

    def test_load_invalid_yaml(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: content:")

        loader = ConfigLoader()
        with pytest.raises(ConfigError):
            loader.load(str(config_file))

    def test_load_nonexistent_file(self):
        loader = ConfigLoader()
        with pytest.raises(ConfigError):
            loader.load("/nonexistent/config.yaml")


class TestConfigFunctions:
    """Tests for config module functions."""

    def test_get_default_config(self):
        config = get_default_config()
        assert isinstance(config, DevCtlConfig)
        assert "default" in config.profiles

    def test_load_config_with_file(self, tmp_path: Path):
        config_content = {"version": "1", "profiles": {"default": {}}}
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_content))

        config = load_config(str(config_file))
        assert isinstance(config, DevCtlConfig)
