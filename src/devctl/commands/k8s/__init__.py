"""Kubernetes command group."""

import click

from devctl.core.context import pass_context, DevCtlContext


@click.group()
@pass_context
def k8s(ctx: DevCtlContext) -> None:
    """Kubernetes operations - pods, deployments, nodes, events.

    \b
    Examples:
        devctl k8s pods list -n production
        devctl k8s pods logs my-pod -f
        devctl k8s deployments list -A
        devctl k8s nodes
        devctl k8s events --watch
    """
    pass


# Import and register subcommands
from devctl.commands.k8s import pods, deployments, nodes, events

k8s.add_command(pods.pods)
k8s.add_command(deployments.deployments)
k8s.add_command(nodes.nodes)
k8s.add_command(events.events)
