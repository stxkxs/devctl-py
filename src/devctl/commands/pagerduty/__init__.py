"""PagerDuty command group."""

import click

from devctl.core.context import pass_context, DevCtlContext


@click.group()
@pass_context
def pagerduty(ctx: DevCtlContext) -> None:
    """PagerDuty operations - incidents, on-call, schedules.

    \b
    Examples:
        devctl pagerduty incidents list --status triggered
        devctl pagerduty incidents ack P123ABC
        devctl pagerduty oncall
        devctl pagerduty schedules list
    """
    pass


# Import and register subcommands
from devctl.commands.pagerduty import incidents, oncall, schedules, services

pagerduty.add_command(incidents.incidents)
pagerduty.add_command(oncall.oncall)
pagerduty.add_command(schedules.schedules)
pagerduty.add_command(services.services)
