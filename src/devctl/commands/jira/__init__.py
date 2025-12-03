"""Jira command group."""

import click

from devctl.core.context import pass_context, DevCtlContext


@click.group()
@pass_context
def jira(ctx: DevCtlContext) -> None:
    """Jira Cloud operations - issues, boards, sprints.

    \b
    Examples:
        devctl jira issues search "project = PROJ AND status = Open"
        devctl jira issues create PROJ "Fix login bug" --type Bug
        devctl jira sprints list --board 123 --state active
        devctl jira boards list --project PROJ
    """
    pass


# Import and register subcommands
from devctl.commands.jira import issues, boards, sprints

jira.add_command(issues.issues)
jira.add_command(boards.boards)
jira.add_command(sprints.sprints)
