"""Main CLI entry point for devctl."""

import sys
from typing import Any

import click
from rich.console import Console

from devctl import __version__
from devctl.config import load_config
from devctl.core.context import DevCtlContext
from devctl.core.output import OutputFormat
from devctl.core.exceptions import DevCtlError, ConfigError


CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 120,
}


class OutputFormatType(click.ParamType):
    """Custom Click parameter type for output format."""

    name = "format"

    def convert(
        self,
        value: Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> OutputFormat:
        if isinstance(value, OutputFormat):
            return value
        try:
            return OutputFormat(value.lower())
        except ValueError:
            self.fail(
                f"Invalid format '{value}'. Choose from: table, json, yaml, raw",
                param,
                ctx,
            )


OUTPUT_FORMAT = OutputFormatType()


def print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Print version and exit."""
    if not value or ctx.resilient_parsing:
        return
    console = Console()
    console.print(f"devctl version {__version__}")
    ctx.exit()


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "-p",
    "--profile",
    metavar="NAME",
    envvar="DEVCTL_PROFILE",
    help="Configuration profile to use",
)
@click.option(
    "-o",
    "--output",
    "output_format",
    type=OUTPUT_FORMAT,
    metavar="FORMAT",
    help="Output format: table, json, yaml, raw",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity (-v for info, -vv for debug, -vvv for trace)",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Suppress non-essential output",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would happen without making changes",
)
@click.option(
    "--no-color",
    is_flag=True,
    help="Disable colored output",
)
@click.option(
    "-c",
    "--config",
    "config_file",
    type=click.Path(exists=True),
    metavar="FILE",
    envvar="DEVCTL_CONFIG",
    help="Path to config file",
)
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Show version and exit",
)
@click.pass_context
def cli(
    ctx: click.Context,
    profile: str | None,
    output_format: OutputFormat | None,
    verbose: int,
    quiet: bool,
    dry_run: bool,
    no_color: bool,
    config_file: str | None,
) -> None:
    """DevCtl - DevOps CLI for AWS, Grafana, and GitHub.

    A unified CLI tool for DevOps operations.
    Supports multiple profiles and configuration via YAML files.

    \b
    Examples:
        devctl aws iam whoami
        devctl aws s3 ls my-bucket
        devctl grafana dashboards list
        devctl github repos list

    \b
    Configuration:
        ~/.devctl/config.yaml    User configuration
        ./devctl.yaml            Project configuration
        DEVCTL_*                 Environment variables
    """
    try:
        # Load configuration
        config = load_config(config_file, profile)

        # Create context
        ctx.obj = DevCtlContext(
            config=config,
            profile=profile,
            output_format=output_format,
            verbose=verbose,
            quiet=quiet,
            dry_run=dry_run,
            color=not no_color,
        )

        if dry_run and not quiet:
            ctx.obj.output.print_warning("Dry-run mode enabled - no changes will be made")

    except ConfigError as e:
        console = Console(stderr=True)
        console.print(f"[red]Configuration error:[/red] {e}")
        sys.exit(1)


# Import and register command groups
def register_commands() -> None:
    """Register all command groups."""
    from devctl.commands.aws import aws
    from devctl.commands.grafana import grafana
    from devctl.commands.github import github
    from devctl.commands.jira import jira
    from devctl.commands.ops import ops
    from devctl.commands import workflow
    from devctl.commands.k8s import k8s
    from devctl.commands.pagerduty import pagerduty
    from devctl.commands.argocd import argocd
    from devctl.commands.logs import logs
    from devctl.commands.runbooks import runbook
    from devctl.commands.deploy import deploy
    from devctl.commands.slack import slack
    from devctl.commands.confluence import confluence
    from devctl.commands.compliance import compliance
    from devctl.commands.terraform import terraform

    cli.add_command(aws)
    cli.add_command(grafana)
    cli.add_command(github)
    cli.add_command(jira)
    cli.add_command(ops)
    cli.add_command(workflow.workflow)
    cli.add_command(k8s)
    cli.add_command(pagerduty)
    cli.add_command(argocd)
    cli.add_command(logs)
    cli.add_command(runbook)
    cli.add_command(deploy)
    cli.add_command(slack)
    cli.add_command(confluence)
    cli.add_command(compliance)
    cli.add_command(terraform)


# Register commands
register_commands()


@cli.command()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Show current configuration."""
    devctl_ctx: DevCtlContext = ctx.obj
    config_data = {
        "profile": devctl_ctx.profile_name,
        "output_format": devctl_ctx.output_format.value,
        "dry_run": devctl_ctx.dry_run,
        "verbose": devctl_ctx.verbose,
        "aws": {
            "profile": devctl_ctx.profile.aws.get_profile(),
            "region": devctl_ctx.profile.aws.get_region(),
        },
        "grafana": {
            "url": devctl_ctx.profile.grafana.get_url(),
            "has_api_key": bool(devctl_ctx.profile.grafana.get_api_key()),
        },
        "github": {
            "org": devctl_ctx.profile.github.get_org(),
            "has_token": bool(devctl_ctx.profile.github.get_token()),
        },
        "jira": {
            "url": devctl_ctx.profile.jira.get_url(),
            "email": devctl_ctx.profile.jira.get_email(),
            "has_token": bool(devctl_ctx.profile.jira.get_api_token()),
        },
    }
    devctl_ctx.output.print_data(config_data, title="Current Configuration")


def main() -> None:
    """Main entry point."""
    try:
        cli()
    except DevCtlError as e:
        console = Console(stderr=True)
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        console = Console(stderr=True)
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
