"""Grafana command group."""

import click

from devctl.core.context import pass_context, DevCtlContext


@click.group()
@pass_context
def grafana(ctx: DevCtlContext) -> None:
    """Grafana operations - dashboards, alerts, datasources.

    \b
    Examples:
        devctl grafana dashboards list
        devctl grafana alerts list --state firing
        devctl grafana datasources test my-prometheus
    """
    pass


# Import and register subcommands
from devctl.commands.grafana import dashboards, alerts, datasources, annotations, metrics

grafana.add_command(dashboards.dashboards)
grafana.add_command(alerts.alerts)
grafana.add_command(datasources.datasources)
grafana.add_command(annotations.annotations)
grafana.add_command(metrics.metrics)
