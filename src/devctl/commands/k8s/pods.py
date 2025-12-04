"""Kubernetes pod commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import K8sError


@click.group()
def pods() -> None:
    """Pod operations - list, logs, exec, describe, delete."""
    pass


@pods.command("list")
@click.option("-n", "--namespace", default=None, help="Namespace (default from config)")
@click.option("-l", "--selector", default=None, help="Label selector")
@click.option("-A", "--all-namespaces", is_flag=True, help="All namespaces")
@click.option("--field-selector", default=None, help="Field selector")
@pass_context
def list_pods(
    ctx: DevCtlContext,
    namespace: str | None,
    selector: str | None,
    all_namespaces: bool,
    field_selector: str | None,
) -> None:
    """List pods.

    \b
    Examples:
        devctl k8s pods list
        devctl k8s pods list -n production
        devctl k8s pods list -l app=nginx
        devctl k8s pods list -A
    """
    try:
        ns = None if all_namespaces else (namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace)

        pods = ctx.k8s.list_pods(
            namespace=ns,
            label_selector=selector,
            field_selector=field_selector,
        )

        if not pods:
            ctx.output.print_info("No pods found")
            return

        # Format output
        rows = []
        for pod in pods:
            metadata = pod.get("metadata", {})
            status = pod.get("status", {})
            spec = pod.get("spec", {})

            # Calculate ready containers
            container_statuses = status.get("containerStatuses", [])
            ready = sum(1 for c in container_statuses if c.get("ready", False))
            total = len(spec.get("containers", []))

            # Calculate restarts
            restarts = sum(c.get("restartCount", 0) for c in container_statuses)

            rows.append({
                "namespace": metadata.get("namespace", ""),
                "name": metadata.get("name", ""),
                "ready": f"{ready}/{total}",
                "status": status.get("phase", "Unknown"),
                "restarts": restarts,
                "age": _format_age(metadata.get("creationTimestamp")),
            })

        if all_namespaces:
            ctx.output.print_table(
                rows,
                columns=["namespace", "name", "ready", "status", "restarts", "age"],
                title="Pods",
            )
        else:
            ctx.output.print_table(
                rows,
                columns=["name", "ready", "status", "restarts", "age"],
                title=f"Pods in {ns}",
            )

    except K8sError as e:
        ctx.output.print_error(f"Failed to list pods: {e}")
        raise click.Abort()


@pods.command("logs")
@click.argument("name")
@click.option("-n", "--namespace", default=None, help="Namespace")
@click.option("-c", "--container", default=None, help="Container name")
@click.option("-f", "--follow", is_flag=True, help="Follow log output")
@click.option("--tail", default=100, help="Lines to show from end")
@click.option("--since", default=None, help="Show logs since (e.g., 1h, 30m)")
@click.option("-p", "--previous", is_flag=True, help="Previous container instance")
@pass_context
def logs(
    ctx: DevCtlContext,
    name: str,
    namespace: str | None,
    container: str | None,
    follow: bool,
    tail: int,
    since: str | None,
    previous: bool,
) -> None:
    """Get pod logs.

    \b
    Examples:
        devctl k8s pods logs my-pod
        devctl k8s pods logs my-pod -f
        devctl k8s pods logs my-pod -c nginx --tail 50
        devctl k8s pods logs my-pod --since 1h
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        # Parse since duration
        since_seconds = None
        if since:
            since_seconds = _parse_duration(since)

        if follow:
            # Stream logs
            for line in ctx.k8s.stream_pod_logs(
                name=name,
                namespace=ns,
                container=container,
                tail_lines=tail,
                since_seconds=since_seconds,
            ):
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                ctx.output.print(line.rstrip())
        else:
            # Get logs
            log_output = ctx.k8s.get_pod_logs(
                name=name,
                namespace=ns,
                container=container,
                tail_lines=tail,
                since_seconds=since_seconds,
                previous=previous,
            )

            if log_output:
                ctx.output.print(log_output)
            else:
                ctx.output.print_info("No logs available")

    except K8sError as e:
        ctx.output.print_error(f"Failed to get logs: {e}")
        raise click.Abort()


@pods.command("exec")
@click.argument("name")
@click.argument("command", nargs=-1, required=True)
@click.option("-n", "--namespace", default=None, help="Namespace")
@click.option("-c", "--container", default=None, help="Container name")
@pass_context
def exec_pod(
    ctx: DevCtlContext,
    name: str,
    command: tuple[str, ...],
    namespace: str | None,
    container: str | None,
) -> None:
    """Execute command in pod.

    \b
    Examples:
        devctl k8s pods exec my-pod -- ls -la
        devctl k8s pods exec my-pod -c nginx -- cat /etc/nginx/nginx.conf
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        if ctx.dry_run:
            ctx.log_dry_run("exec", {"pod": name, "namespace": ns, "command": " ".join(command)})
            return

        output = ctx.k8s.exec_pod(
            name=name,
            namespace=ns,
            command=list(command),
            container=container,
        )

        ctx.output.print(output)

    except K8sError as e:
        ctx.output.print_error(f"Failed to exec: {e}")
        raise click.Abort()


@pods.command("describe")
@click.argument("name")
@click.option("-n", "--namespace", default=None, help="Namespace")
@pass_context
def describe(
    ctx: DevCtlContext,
    name: str,
    namespace: str | None,
) -> None:
    """Describe a pod.

    \b
    Examples:
        devctl k8s pods describe my-pod
        devctl k8s pods describe my-pod -n production
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        pod = ctx.k8s.get_pod(name=name, namespace=ns)

        metadata = pod.get("metadata", {})
        spec = pod.get("spec", {})
        status = pod.get("status", {})

        ctx.output.print_header(f"Pod: {metadata.get('name')}")
        ctx.output.print(f"Namespace: {metadata.get('namespace')}")
        ctx.output.print(f"Node: {spec.get('nodeName', 'N/A')}")
        ctx.output.print(f"Status: {status.get('phase')}")
        ctx.output.print(f"IP: {status.get('podIP', 'N/A')}")
        ctx.output.print(f"Created: {metadata.get('creationTimestamp')}")

        # Labels
        labels = metadata.get("labels", {})
        if labels:
            ctx.output.print("\nLabels:")
            for k, v in labels.items():
                ctx.output.print(f"  {k}: {v}")

        # Containers
        ctx.output.print("\nContainers:")
        for container in spec.get("containers", []):
            ctx.output.print(f"  {container.get('name')}:")
            ctx.output.print(f"    Image: {container.get('image')}")

            # Find container status
            for cs in status.get("containerStatuses", []):
                if cs.get("name") == container.get("name"):
                    ctx.output.print(f"    Ready: {cs.get('ready', False)}")
                    ctx.output.print(f"    Restarts: {cs.get('restartCount', 0)}")
                    break

        # Events (if available)
        ctx.output.print("\n[Use 'devctl k8s events' for pod events]")

    except K8sError as e:
        ctx.output.print_error(f"Failed to describe pod: {e}")
        raise click.Abort()


@pods.command("delete")
@click.argument("name")
@click.option("-n", "--namespace", default=None, help="Namespace")
@click.option("--force", is_flag=True, help="Force delete")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@pass_context
def delete(
    ctx: DevCtlContext,
    name: str,
    namespace: str | None,
    force: bool,
    yes: bool,
) -> None:
    """Delete a pod.

    \b
    Examples:
        devctl k8s pods delete my-pod
        devctl k8s pods delete my-pod --force
    """
    try:
        ns = namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace

        if ctx.dry_run:
            ctx.log_dry_run("delete pod", {"name": name, "namespace": ns, "force": force})
            return

        if not yes and not ctx.confirm(f"Delete pod {name} in {ns}?"):
            ctx.output.print_info("Cancelled")
            return

        ctx.k8s.delete_pod(name=name, namespace=ns, force=force)
        ctx.output.print_success(f"Pod {name} deleted")

    except K8sError as e:
        ctx.output.print_error(f"Failed to delete pod: {e}")
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


def _parse_duration(duration: str) -> int:
    """Parse duration string to seconds."""
    value = int(duration[:-1])
    unit = duration[-1].lower()

    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    elif unit == "d":
        return value * 86400
    else:
        raise ValueError(f"Invalid duration unit: {unit}")
