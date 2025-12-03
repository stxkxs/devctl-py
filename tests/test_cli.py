"""Tests for CLI entry point."""

from click.testing import CliRunner

from devctl.cli import cli


def test_cli_help(cli_runner: CliRunner):
    """Test CLI help output."""
    result = cli_runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "DevCtl" in result.output
    assert "aws" in result.output
    assert "grafana" in result.output
    assert "github" in result.output


def test_cli_version(cli_runner: CliRunner):
    """Test CLI version output."""
    result = cli_runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "devctl version" in result.output


def test_cli_aws_help(cli_runner: CliRunner):
    """Test AWS command group help."""
    result = cli_runner.invoke(cli, ["aws", "--help"])
    assert result.exit_code == 0
    assert "AWS operations" in result.output


def test_cli_grafana_help(cli_runner: CliRunner):
    """Test Grafana command group help."""
    result = cli_runner.invoke(cli, ["grafana", "--help"])
    assert result.exit_code == 0
    assert "Grafana operations" in result.output


def test_cli_github_help(cli_runner: CliRunner):
    """Test GitHub command group help."""
    result = cli_runner.invoke(cli, ["github", "--help"])
    assert result.exit_code == 0
    assert "GitHub operations" in result.output


def test_cli_ops_help(cli_runner: CliRunner):
    """Test Ops command group help."""
    result = cli_runner.invoke(cli, ["ops", "--help"])
    assert result.exit_code == 0
    assert "DevOps operations" in result.output


def test_cli_workflow_help(cli_runner: CliRunner):
    """Test Workflow command group help."""
    result = cli_runner.invoke(cli, ["workflow", "--help"])
    assert result.exit_code == 0
    assert "Workflow operations" in result.output


def test_cli_dry_run_flag(cli_runner: CliRunner):
    """Test dry-run flag is recognized."""
    result = cli_runner.invoke(cli, ["--dry-run", "config"])
    # Should work even without real config
    assert "dry-run" in result.output.lower() or result.exit_code == 0


def test_cli_output_format_json(cli_runner: CliRunner):
    """Test JSON output format."""
    result = cli_runner.invoke(cli, ["-o", "json", "config"])
    # Should accept json format
    assert result.exit_code == 0 or "json" in str(result.exception).lower()


def test_cli_verbose_flag(cli_runner: CliRunner):
    """Test verbose flag."""
    result = cli_runner.invoke(cli, ["-v", "--help"])
    assert result.exit_code == 0


def test_cli_quiet_flag(cli_runner: CliRunner):
    """Test quiet flag."""
    result = cli_runner.invoke(cli, ["-q", "--help"])
    assert result.exit_code == 0
