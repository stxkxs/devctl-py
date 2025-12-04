"""Kubernetes deployment commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import K8sError


@click.group()
def deployments() -> None:
    """Deployment operations - list, describe, scale, restart, rollout."""
    pass


@deployments.command("list")
@click.option("-n", "--namespace", default=None, help="Namespace")
@click.option("-A", "--all-namespaces", is_flag=True, help="All namespaces")
@click.option("-l", "--selector", default=None, help="Label selector")
@pass_context
def list_deployments(
    ctx: DevCtlContext,
    namespace: str | None,
    all_namespaces: bool,
    selector: str | None,
) -> None:
    """List deployments.

    \b
    Examples:
        devctl k8s deployments list
        devctl k8s deployments list -n production
        devctl k8s deployments list -A
    """
    try:
        ns = None if all_namespaces else (namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace)

        deployments = ctx.k8s.list_deployments(
            namespace=ns,
            label_selector=selector,
        )

        if not deployments:
            ctx.output.print_info("No deployments found")
            return

        rows = []
        for dep in deployments:
            metadata = dep.get("metadata", {})
            spec = dep.get("spec", {})
            status = dep.get("status", {})

            ready = status.get("readyReplicas", 0)
            desired = spec.get("replicas", 0)
            available = status.get("availableReplicas", 0)

            rows.append({
                "namespace": metadata.get("namespace", ""),
                "name": metadata.get("name", ""),
                "ready": f"{ready}/{desired}",
                "up-to-date": status.get("updatedReplicas", 0),
                "available": available,
                "age": _format_age(metadata.get("creationTimestamp")),
            })

        columns = ["namespace", "name", "ready", "up-to-date", "available", "age"] if all_namespaces else ["name", "ready", "up-to-date", "available", "age"]

        ctx.output.print_table(rows, columns=columns, title="Deployments")

    except K8sError as e:
        ctx.output.print_error(f"Failed to list deployments: {e}")
        raise click.Abort()


@deployments.command("describe")
@click.argument("name")
@click.option("-n", "--namespace", default=None, help="Namespace")
@pass_context
def describe(
    ctx: DevCtlContext,
    name: str,
    namespace: str | None,
) -> None:
    """Describe a deployment.

    \b
    Examples:
        devctl k8s deployments describe nginx
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        dep = ctx.k8s.get_deployment(name=name, namespace=ns)

        metadata = dep.get("metadata", {})
        spec = dep.get("spec", {})
        status = dep.get("status", {})

        ctx.output.print_header(f"Deployment: {metadata.get('name')}")
        ctx.output.print(f"Namespace: {metadata.get('namespace')}")
        ctx.output.print(f"Created: {metadata.get('creationTimestamp')}")

        # Replicas
        ctx.output.print(f"\nReplicas:")
        ctx.output.print(f"  Desired: {spec.get('replicas', 0)}")
        ctx.output.print(f"  Ready: {status.get('readyReplicas', 0)}")
        ctx.output.print(f"  Available: {status.get('availableReplicas', 0)}")
        ctx.output.print(f"  Updated: {status.get('updatedReplicas', 0)}")

        # Strategy
        strategy = spec.get("strategy", {})
        ctx.output.print(f"\nStrategy: {strategy.get('type', 'RollingUpdate')}")
        if strategy.get("type") == "RollingUpdate":
            rolling = strategy.get("rollingUpdate", {})
            ctx.output.print(f"  Max Surge: {rolling.get('maxSurge', '25%')}")
            ctx.output.print(f"  Max Unavailable: {rolling.get('maxUnavailable', '25%')}")

        # Containers
        template = spec.get("template", {}).get("spec", {})
        ctx.output.print("\nContainers:")
        for container in template.get("containers", []):
            ctx.output.print(f"  {container.get('name')}:")
            ctx.output.print(f"    Image: {container.get('image')}")

            # Resources
            resources = container.get("resources", {})
            if resources:
                limits = resources.get("limits", {})
                requests = resources.get("requests", {})
                if limits:
                    ctx.output.print(f"    Limits: cpu={limits.get('cpu', '-')}, memory={limits.get('memory', '-')}")
                if requests:
                    ctx.output.print(f"    Requests: cpu={requests.get('cpu', '-')}, memory={requests.get('memory', '-')}")

        # Conditions
        conditions = status.get("conditions", [])
        if conditions:
            ctx.output.print("\nConditions:")
            for cond in conditions:
                ctx.output.print(f"  {cond.get('type')}: {cond.get('status')} - {cond.get('message', '')}")

    except K8sError as e:
        ctx.output.print_error(f"Failed to describe deployment: {e}")
        raise click.Abort()


@deployments.command("scale")
@click.argument("name")
@click.argument("replicas", type=int)
@click.option("-n", "--namespace", default=None, help="Namespace")
@pass_context
def scale(
    ctx: DevCtlContext,
    name: str,
    replicas: int,
    namespace: str | None,
) -> None:
    """Scale a deployment.

    \b
    Examples:
        devctl k8s deployments scale nginx 5
        devctl k8s deployments scale nginx 0 -n staging
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        if ctx.dry_run:
            ctx.log_dry_run("scale", {"deployment": name, "replicas": replicas, "namespace": ns})
            return

        ctx.k8s.scale_deployment(name=name, namespace=ns, replicas=replicas)
        ctx.output.print_success(f"Scaled {name} to {replicas} replicas")

    except K8sError as e:
        ctx.output.print_error(f"Failed to scale deployment: {e}")
        raise click.Abort()


@deployments.command("restart")
@click.argument("name")
@click.option("-n", "--namespace", default=None, help="Namespace")
@pass_context
def restart(
    ctx: DevCtlContext,
    name: str,
    namespace: str | None,
) -> None:
    """Restart a deployment (rolling restart).

    \b
    Examples:
        devctl k8s deployments restart nginx
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        if ctx.dry_run:
            ctx.log_dry_run("restart", {"deployment": name, "namespace": ns})
            return

        ctx.k8s.restart_deployment(name=name, namespace=ns)
        ctx.output.print_success(f"Initiated rolling restart for {name}")

    except K8sError as e:
        ctx.output.print_error(f"Failed to restart deployment: {e}")
        raise click.Abort()


@deployments.group("rollout")
def rollout() -> None:
    """Rollout management - status, history, undo."""
    pass


@rollout.command("status")
@click.argument("name")
@click.option("-n", "--namespace", default=None, help="Namespace")
@click.option("-w", "--watch", is_flag=True, help="Watch status")
@pass_context
def rollout_status(
    ctx: DevCtlContext,
    name: str,
    namespace: str | None,
    watch: bool,
) -> None:
    """Show rollout status.

    \b
    Examples:
        devctl k8s deployments rollout status nginx
        devctl k8s deployments rollout status nginx -w
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        if watch:
            import time

            while True:
                status = ctx.k8s.get_rollout_status(name=name, namespace=ns)

                # Clear screen and print status
                click.clear()
                ctx.output.print_header(f"Rollout Status: {name}")
                ctx.output.print(f"Replicas: {status.get('replicas', 0)}")
                ctx.output.print(f"Ready: {status.get('ready_replicas', 0)}")
                ctx.output.print(f"Updated: {status.get('updated_replicas', 0)}")
                ctx.output.print(f"Available: {status.get('available_replicas', 0)}")

                if status.get("ready", False):
                    ctx.output.print_success("\nRollout complete!")
                    break

                time.sleep(2)
        else:
            status = ctx.k8s.get_rollout_status(name=name, namespace=ns)

            ctx.output.print_header(f"Rollout Status: {name}")
            ctx.output.print(f"Replicas: {status.get('replicas', 0)}")
            ctx.output.print(f"Ready: {status.get('ready_replicas', 0)}")
            ctx.output.print(f"Updated: {status.get('updated_replicas', 0)}")
            ctx.output.print(f"Available: {status.get('available_replicas', 0)}")

            if status.get("ready", False):
                ctx.output.print_success("Rollout complete")
            else:
                ctx.output.print_warning("Rollout in progress...")

    except K8sError as e:
        ctx.output.print_error(f"Failed to get rollout status: {e}")
        raise click.Abort()


@rollout.command("history")
@click.argument("name")
@click.option("-n", "--namespace", default=None, help="Namespace")
@pass_context
def rollout_history(
    ctx: DevCtlContext,
    name: str,
    namespace: str | None,
) -> None:
    """Show rollout history.

    \b
    Examples:
        devctl k8s deployments rollout history nginx
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        history = ctx.k8s.get_rollout_history(name=name, namespace=ns)

        if not history:
            ctx.output.print_info("No rollout history found")
            return

        rows = []
        for entry in history:
            rows.append({
                "revision": entry.get("revision", ""),
                "change-cause": entry.get("change_cause", "<none>"),
            })

        ctx.output.print_table(rows, columns=["revision", "change-cause"], title=f"Rollout History: {name}")

    except K8sError as e:
        ctx.output.print_error(f"Failed to get rollout history: {e}")
        raise click.Abort()


@rollout.command("undo")
@click.argument("name")
@click.option("-n", "--namespace", default=None, help="Namespace")
@click.option("--to-revision", type=int, default=None, help="Rollback to specific revision")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@pass_context
def rollout_undo(
    ctx: DevCtlContext,
    name: str,
    namespace: str | None,
    to_revision: int | None,
    yes: bool,
) -> None:
    """Undo a rollout.

    \b
    Examples:
        devctl k8s deployments rollout undo nginx
        devctl k8s deployments rollout undo nginx --to-revision 2
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        if ctx.dry_run:
            ctx.log_dry_run("rollout undo", {"deployment": name, "namespace": ns, "revision": to_revision})
            return

        msg = f"Rollback {name}"
        if to_revision:
            msg += f" to revision {to_revision}"
        msg += "?"

        if not yes and not ctx.confirm(msg):
            ctx.output.print_info("Cancelled")
            return

        ctx.k8s.rollback_deployment(name=name, namespace=ns, revision=to_revision)
        ctx.output.print_success(f"Rolled back {name}")

    except K8sError as e:
        ctx.output.print_error(f"Failed to rollback deployment: {e}")
        raise click.Abort()


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
