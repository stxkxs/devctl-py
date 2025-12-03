"""GitHub command group."""

import click

from devctl.core.context import pass_context, DevCtlContext


@click.group()
@pass_context
def github(ctx: DevCtlContext) -> None:
    """GitHub operations - repos, actions, PRs, releases.

    \b
    Examples:
        devctl github repos list
        devctl github actions list owner/repo
        devctl github prs list owner/repo
    """
    pass


# Import and register subcommands
from devctl.commands.github import repos, actions, prs, releases

github.add_command(repos.repos)
github.add_command(actions.actions)
github.add_command(prs.prs)
github.add_command(releases.releases)
