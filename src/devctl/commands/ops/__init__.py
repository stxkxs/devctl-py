"""Ops command group - cross-service DevOps workflows."""

import click

from devctl.core.context import pass_context, DevCtlContext


@click.group()
@pass_context
def ops(ctx: DevCtlContext) -> None:
    """DevOps operations - health checks, deployments, cost reports.

    \b
    Examples:
        devctl ops health check my-service
        devctl ops cost-report --days 30
        devctl ops status
    """
    pass


# Import and register subcommands
from devctl.commands.ops import health, cost_report

ops.add_command(health.health)
ops.add_command(cost_report.cost_report)
