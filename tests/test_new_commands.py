"""Tests for new CLI commands."""

from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from devctl.cli import cli


class TestK8sCommands:
    """Tests for Kubernetes commands."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_k8s_help(self, cli_runner):
        """Test k8s command group help."""
        result = cli_runner.invoke(cli, ["k8s", "--help"])
        assert result.exit_code == 0
        assert "Kubernetes operations" in result.output
        assert "pods" in result.output
        assert "deployments" in result.output

    def test_k8s_pods_help(self, cli_runner):
        """Test k8s pods help."""
        result = cli_runner.invoke(cli, ["k8s", "pods", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "logs" in result.output


class TestPagerDutyCommands:
    """Tests for PagerDuty commands."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_pagerduty_help(self, cli_runner):
        """Test pagerduty command group help."""
        result = cli_runner.invoke(cli, ["pagerduty", "--help"])
        assert result.exit_code == 0
        assert "PagerDuty" in result.output
        assert "incidents" in result.output
        assert "oncall" in result.output

    def test_pagerduty_incidents_help(self, cli_runner):
        """Test pagerduty incidents help."""
        result = cli_runner.invoke(cli, ["pagerduty", "incidents", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "create" in result.output
        assert "ack" in result.output


class TestArgoCDCommands:
    """Tests for ArgoCD commands."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_argocd_help(self, cli_runner):
        """Test argocd command group help."""
        result = cli_runner.invoke(cli, ["argocd", "--help"])
        assert result.exit_code == 0
        assert "ArgoCD" in result.output
        assert "apps" in result.output

    def test_argocd_apps_help(self, cli_runner):
        """Test argocd apps help."""
        result = cli_runner.invoke(cli, ["argocd", "apps", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "sync" in result.output
        assert "diff" in result.output


class TestLogsCommands:
    """Tests for unified logs commands."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_logs_help(self, cli_runner):
        """Test logs command group help."""
        result = cli_runner.invoke(cli, ["logs", "--help"])
        assert result.exit_code == 0
        assert "Unified log" in result.output
        assert "search" in result.output
        assert "cloudwatch" in result.output


class TestRunbookCommands:
    """Tests for runbook commands."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_runbook_help(self, cli_runner):
        """Test runbook command group help."""
        result = cli_runner.invoke(cli, ["runbook", "--help"])
        assert result.exit_code == 0
        assert "Runbook" in result.output
        assert "run" in result.output
        assert "list" in result.output
        assert "validate" in result.output


class TestDeployCommands:
    """Tests for deployment commands."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_deploy_help(self, cli_runner):
        """Test deploy command group help."""
        result = cli_runner.invoke(cli, ["deploy", "--help"])
        assert result.exit_code == 0
        assert "Deployment" in result.output
        assert "create" in result.output
        assert "status" in result.output
        assert "promote" in result.output
        assert "rollback" in result.output


class TestSlackCommands:
    """Tests for Slack commands."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_slack_help(self, cli_runner):
        """Test slack command group help."""
        result = cli_runner.invoke(cli, ["slack", "--help"])
        assert result.exit_code == 0
        assert "Slack" in result.output
        assert "send" in result.output
        assert "notify" in result.output
        assert "channels" in result.output


class TestConfluenceCommands:
    """Tests for Confluence commands."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_confluence_help(self, cli_runner):
        """Test confluence command group help."""
        result = cli_runner.invoke(cli, ["confluence", "--help"])
        assert result.exit_code == 0
        assert "Confluence" in result.output
        assert "pages" in result.output
        assert "search" in result.output


class TestComplianceCommands:
    """Tests for compliance commands."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_compliance_help(self, cli_runner):
        """Test compliance command group help."""
        result = cli_runner.invoke(cli, ["compliance", "--help"])
        assert result.exit_code == 0
        assert "Compliance" in result.output or "PCI" in result.output
        assert "pci" in result.output
        assert "access-review" in result.output
