"""Kubernetes node commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import K8sError


@click.command("nodes")
@click.option("-l", "--selector", default=None, help="Label selector")
@click.option("--show-labels", is_flag=True, help="Show labels")
@pass_context
def nodes(
    ctx: DevCtlContext,
    selector: str | None,
    show_labels: bool,
) -> None:
    """List cluster nodes.

    \b
    Examples:
        devctl k8s nodes
        devctl k8s nodes -l node-role.kubernetes.io/worker=
        devctl k8s nodes --show-labels
    """
    try:
        node_list = ctx.k8s.list_nodes(label_selector=selector)

        if not node_list:
            ctx.output.print_info("No nodes found")
            return

        rows = []
        for node in node_list:
            metadata = node.get("metadata", {})
            status = node.get("status", {})

            # Get node status
            conditions = status.get("conditions", [])
            node_status = "Unknown"
            for cond in conditions:
                if cond.get("type") == "Ready":
                    node_status = "Ready" if cond.get("status") == "True" else "NotReady"
                    break

            # Get node info
            node_info = status.get("nodeInfo", {})

            # Get capacity
            capacity = status.get("capacity", {})
            allocatable = status.get("allocatable", {})

            row = {
                "name": metadata.get("name", ""),
                "status": node_status,
                "roles": _get_node_roles(metadata.get("labels", {})),
                "age": _format_age(metadata.get("creationTimestamp")),
                "version": node_info.get("kubeletVersion", ""),
                "cpu": allocatable.get("cpu", ""),
                "memory": _format_memory(allocatable.get("memory", "")),
            }

            if show_labels:
                labels = metadata.get("labels", {})
                row["labels"] = ", ".join(f"{k}={v}" for k, v in labels.items())

            rows.append(row)

        columns = ["name", "status", "roles", "age", "version", "cpu", "memory"]
        if show_labels:
            columns.append("labels")

        ctx.output.print_table(rows, columns=columns, title="Nodes")

    except K8sError as e:
        ctx.output.print_error(f"Failed to list nodes: {e}")
        raise click.Abort()


def _get_node_roles(labels: dict[str, str]) -> str:
    """Extract node roles from labels."""
    roles = []
    for key in labels:
        if key.startswith("node-role.kubernetes.io/"):
            role = key.split("/")[-1]
            roles.append(role)

    return ",".join(roles) if roles else "<none>"


def _format_age(timestamp: str | None) -> str:
    """Format age from timestamp."""
    if not timestamp:
        return "Unknown"

    from datetime import datetime

    try:
        created = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now = datetime.now(created.tzinfo)
        delta = now - created

        if delta.days > 0:
            return f"{delta.days}d"
        elif delta.seconds >= 3600:
            return f"{delta.seconds // 3600}h"
        elif delta.seconds >= 60:
            return f"{delta.seconds // 60}m"
        else:
            return f"{delta.seconds}s"
    except Exception:
        return "Unknown"


def _format_memory(memory: str) -> str:
    """Format memory string for display."""
    if not memory:
        return ""

    # Handle Ki suffix
    if memory.endswith("Ki"):
        ki = int(memory[:-2])
        gi = ki / (1024 * 1024)
        return f"{gi:.1f}Gi"

    return memory
