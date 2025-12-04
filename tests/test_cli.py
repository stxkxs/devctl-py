"""Tests for CLI commands and help output.

Tests that all command groups are properly registered and their help
text is correctly displayed. These are smoke tests to ensure the CLI
structure is intact.
"""

import pytest
from click.testing import CliRunner

from devctl.cli import cli


# =============================================================================
# CLI Entry Point
# =============================================================================


class TestCLIEntryPoint:
    """Tests for main CLI entry point, flags, and options."""

    def test_help(self, cli_runner: CliRunner):
        """Test CLI help output."""
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "DevCtl" in result.output
        # Verify main command groups are listed
        assert "aws" in result.output
        assert "grafana" in result.output
        assert "github" in result.output
        assert "jira" in result.output
        assert "terraform" in result.output

    def test_version(self, cli_runner: CliRunner):
        """Test CLI version output."""
        result = cli_runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "devctl version" in result.output

    def test_dry_run_flag(self, cli_runner: CliRunner):
        """Test dry-run flag is recognized."""
        result = cli_runner.invoke(cli, ["--dry-run", "config"])
        assert "dry-run" in result.output.lower() or result.exit_code == 0

    def test_output_format_json(self, cli_runner: CliRunner):
        """Test JSON output format."""
        result = cli_runner.invoke(cli, ["-o", "json", "config"])
        assert result.exit_code == 0 or "json" in str(result.exception).lower()

    def test_verbose_flag(self, cli_runner: CliRunner):
        """Test verbose flag."""
        result = cli_runner.invoke(cli, ["-v", "--help"])
        assert result.exit_code == 0

    def test_quiet_flag(self, cli_runner: CliRunner):
        """Test quiet flag."""
        result = cli_runner.invoke(cli, ["-q", "--help"])
        assert result.exit_code == 0


# =============================================================================
# AWS Commands
# =============================================================================


class TestAWSCommands:
    """Tests for AWS command group."""

    def test_aws_help(self, cli_runner: CliRunner):
        """Test AWS command group help."""
        result = cli_runner.invoke(cli, ["aws", "--help"])
        assert result.exit_code == 0
        assert "AWS operations" in result.output
        assert "iam" in result.output
        assert "s3" in result.output
        assert "ssm" in result.output

    def test_ssm_help(self, cli_runner: CliRunner):
        """Test AWS SSM command group help."""
        result = cli_runner.invoke(cli, ["aws", "ssm", "--help"])
        assert result.exit_code == 0
        assert "SSM operations" in result.output
        assert "params" in result.output
        assert "run" in result.output
        assert "instances" in result.output

    def test_ssm_params_help(self, cli_runner: CliRunner):
        """Test AWS SSM params help."""
        result = cli_runner.invoke(cli, ["aws", "ssm", "params", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "get" in result.output
        assert "set" in result.output
        assert "delete" in result.output

    def test_ssm_run_help(self, cli_runner: CliRunner):
        """Test AWS SSM run help."""
        result = cli_runner.invoke(cli, ["aws", "ssm", "run", "--help"])
        assert result.exit_code == 0
        assert "--targets" in result.output
        assert "--timeout" in result.output


# =============================================================================
# Grafana Commands
# =============================================================================


class TestGrafanaCommands:
    """Tests for Grafana command group."""

    def test_grafana_help(self, cli_runner: CliRunner):
        """Test Grafana command group help."""
        result = cli_runner.invoke(cli, ["grafana", "--help"])
        assert result.exit_code == 0
        assert "Grafana operations" in result.output
        assert "dashboards" in result.output
        assert "alerts" in result.output
        assert "metrics" in result.output

    def test_metrics_help(self, cli_runner: CliRunner):
        """Test Grafana metrics command group help."""
        result = cli_runner.invoke(cli, ["grafana", "metrics", "--help"])
        assert result.exit_code == 0
        assert "Metrics operations" in result.output
        assert "query" in result.output
        assert "get" in result.output
        assert "check" in result.output

    def test_metrics_query_help(self, cli_runner: CliRunner):
        """Test Grafana metrics query help."""
        result = cli_runner.invoke(cli, ["grafana", "metrics", "query", "--help"])
        assert result.exit_code == 0
        assert "DATASOURCE" in result.output
        assert "QUERY" in result.output
        assert "--since" in result.output

    def test_metrics_check_help(self, cli_runner: CliRunner):
        """Test Grafana metrics check help."""
        result = cli_runner.invoke(cli, ["grafana", "metrics", "check", "--help"])
        assert result.exit_code == 0
        assert "--threshold" in result.output
        assert "--comparison" in result.output
        assert "--exit-code" in result.output

    def test_dashboards_templates_help(self, cli_runner: CliRunner):
        """Test Grafana dashboards templates help."""
        result = cli_runner.invoke(cli, ["grafana", "dashboards", "templates", "--help"])
        assert result.exit_code == 0
        assert "templates" in result.output.lower()


# =============================================================================
# Terraform Commands
# =============================================================================


class TestTerraformCommands:
    """Tests for Terraform command group."""

    def test_terraform_help(self, cli_runner: CliRunner):
        """Test Terraform command group help."""
        result = cli_runner.invoke(cli, ["terraform", "--help"])
        assert result.exit_code == 0
        assert "Terraform operations" in result.output
        assert "plan" in result.output
        assert "apply" in result.output
        assert "state" in result.output
        assert "workspace" in result.output

    def test_plan_help(self, cli_runner: CliRunner):
        """Test Terraform plan help."""
        result = cli_runner.invoke(cli, ["terraform", "plan", "--help"])
        assert result.exit_code == 0
        assert "--var" in result.output
        assert "--target" in result.output
        assert "--out" in result.output

    def test_apply_help(self, cli_runner: CliRunner):
        """Test Terraform apply help."""
        result = cli_runner.invoke(cli, ["terraform", "apply", "--help"])
        assert result.exit_code == 0
        assert "--auto-approve" in result.output
        assert "--var" in result.output

    def test_state_help(self, cli_runner: CliRunner):
        """Test Terraform state help."""
        result = cli_runner.invoke(cli, ["terraform", "state", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "show" in result.output
        assert "mv" in result.output
        assert "rm" in result.output

    def test_workspace_help(self, cli_runner: CliRunner):
        """Test Terraform workspace help."""
        result = cli_runner.invoke(cli, ["terraform", "workspace", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "select" in result.output
        assert "new" in result.output


# =============================================================================
# GitHub Commands
# =============================================================================


class TestGitHubCommands:
    """Tests for GitHub command group."""

    def test_github_help(self, cli_runner: CliRunner):
        """Test GitHub command group help."""
        result = cli_runner.invoke(cli, ["github", "--help"])
        assert result.exit_code == 0
        assert "GitHub operations" in result.output


# =============================================================================
# Jira Commands
# =============================================================================


class TestJiraCommands:
    """Tests for Jira command group."""

    def test_jira_help(self, cli_runner: CliRunner):
        """Test Jira command group help."""
        result = cli_runner.invoke(cli, ["jira", "--help"])
        assert result.exit_code == 0
        assert "Jira" in result.output
        assert "issues" in result.output
        assert "boards" in result.output
        assert "sprints" in result.output

    def test_issues_help(self, cli_runner: CliRunner):
        """Test Jira issues subcommand help."""
        result = cli_runner.invoke(cli, ["jira", "issues", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output
        assert "create" in result.output
        assert "transition" in result.output

    def test_boards_help(self, cli_runner: CliRunner):
        """Test Jira boards subcommand help."""
        result = cli_runner.invoke(cli, ["jira", "boards", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "backlog" in result.output

    def test_sprints_help(self, cli_runner: CliRunner):
        """Test Jira sprints subcommand help."""
        result = cli_runner.invoke(cli, ["jira", "sprints", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "active" in result.output


# =============================================================================
# Kubernetes Commands
# =============================================================================


class TestK8sCommands:
    """Tests for Kubernetes command group."""

    def test_k8s_help(self, cli_runner: CliRunner):
        """Test K8s command group help."""
        result = cli_runner.invoke(cli, ["k8s", "--help"])
        assert result.exit_code == 0
        assert "Kubernetes operations" in result.output
        assert "pods" in result.output
        assert "deployments" in result.output

    def test_pods_help(self, cli_runner: CliRunner):
        """Test K8s pods help."""
        result = cli_runner.invoke(cli, ["k8s", "pods", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "logs" in result.output


# =============================================================================
# PagerDuty Commands
# =============================================================================


class TestPagerDutyCommands:
    """Tests for PagerDuty command group."""

    def test_pagerduty_help(self, cli_runner: CliRunner):
        """Test PagerDuty command group help."""
        result = cli_runner.invoke(cli, ["pagerduty", "--help"])
        assert result.exit_code == 0
        assert "PagerDuty" in result.output
        assert "incidents" in result.output
        assert "oncall" in result.output

    def test_incidents_help(self, cli_runner: CliRunner):
        """Test PagerDuty incidents help."""
        result = cli_runner.invoke(cli, ["pagerduty", "incidents", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "create" in result.output
        assert "ack" in result.output


# =============================================================================
# ArgoCD Commands
# =============================================================================


class TestArgoCDCommands:
    """Tests for ArgoCD command group."""

    def test_argocd_help(self, cli_runner: CliRunner):
        """Test ArgoCD command group help."""
        result = cli_runner.invoke(cli, ["argocd", "--help"])
        assert result.exit_code == 0
        assert "ArgoCD" in result.output
        assert "apps" in result.output

    def test_apps_help(self, cli_runner: CliRunner):
        """Test ArgoCD apps help."""
        result = cli_runner.invoke(cli, ["argocd", "apps", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "sync" in result.output
        assert "diff" in result.output


# =============================================================================
# Other Command Groups
# =============================================================================


class TestOpsCommands:
    """Tests for Ops command group."""

    def test_ops_help(self, cli_runner: CliRunner):
        """Test Ops command group help."""
        result = cli_runner.invoke(cli, ["ops", "--help"])
        assert result.exit_code == 0
        assert "DevOps operations" in result.output


class TestWorkflowCommands:
    """Tests for Workflow command group."""

    def test_workflow_help(self, cli_runner: CliRunner):
        """Test Workflow command group help."""
        result = cli_runner.invoke(cli, ["workflow", "--help"])
        assert result.exit_code == 0
        assert "Workflow operations" in result.output


class TestLogsCommands:
    """Tests for Logs command group."""

    def test_logs_help(self, cli_runner: CliRunner):
        """Test Logs command group help."""
        result = cli_runner.invoke(cli, ["logs", "--help"])
        assert result.exit_code == 0
        assert "Unified log" in result.output
        assert "search" in result.output
        assert "cloudwatch" in result.output


class TestRunbookCommands:
    """Tests for Runbook command group."""

    def test_runbook_help(self, cli_runner: CliRunner):
        """Test Runbook command group help."""
        result = cli_runner.invoke(cli, ["runbook", "--help"])
        assert result.exit_code == 0
        assert "Runbook" in result.output
        assert "run" in result.output
        assert "list" in result.output
        assert "validate" in result.output


class TestDeployCommands:
    """Tests for Deploy command group."""

    def test_deploy_help(self, cli_runner: CliRunner):
        """Test Deploy command group help."""
        result = cli_runner.invoke(cli, ["deploy", "--help"])
        assert result.exit_code == 0
        assert "Deployment" in result.output
        assert "create" in result.output
        assert "status" in result.output
        assert "promote" in result.output
        assert "rollback" in result.output


class TestSlackCommands:
    """Tests for Slack command group."""

    def test_slack_help(self, cli_runner: CliRunner):
        """Test Slack command group help."""
        result = cli_runner.invoke(cli, ["slack", "--help"])
        assert result.exit_code == 0
        assert "Slack" in result.output
        assert "send" in result.output
        assert "notify" in result.output
        assert "channels" in result.output


class TestConfluenceCommands:
    """Tests for Confluence command group."""

    def test_confluence_help(self, cli_runner: CliRunner):
        """Test Confluence command group help."""
        result = cli_runner.invoke(cli, ["confluence", "--help"])
        assert result.exit_code == 0
        assert "Confluence" in result.output
        assert "pages" in result.output
        assert "search" in result.output


class TestComplianceCommands:
    """Tests for Compliance command group."""

    def test_compliance_help(self, cli_runner: CliRunner):
        """Test Compliance command group help."""
        result = cli_runner.invoke(cli, ["compliance", "--help"])
        assert result.exit_code == 0
        assert "Compliance" in result.output or "PCI" in result.output
        assert "pci" in result.output
        assert "access-review" in result.output
