"""ArgoCD command group."""

import click

from devctl.core.context import pass_context, DevCtlContext


@click.group()
@pass_context
def argocd(ctx: DevCtlContext) -> None:
    """ArgoCD operations - applications, sync, diff.

    \b
    Examples:
        devctl argocd apps list
        devctl argocd apps sync my-app
        devctl argocd apps status my-app
    """
    pass


# Import and register subcommands
from devctl.commands.argocd import apps

argocd.add_command(apps.apps)
