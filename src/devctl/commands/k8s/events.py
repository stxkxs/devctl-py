"""Kubernetes events commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import K8sError


@click.command("events")
@click.option("-n", "--namespace", default=None, help="Namespace")
@click.option("-A", "--all-namespaces", is_flag=True, help="All namespaces")
@click.option("--type", "event_type", default=None, help="Event type (Normal, Warning)")
@click.option("--for", "for_object", default=None, help="Filter for object (e.g., pod/my-pod)")
@click.option("-w", "--watch", is_flag=True, help="Watch events")
@pass_context
def events(
    ctx: DevCtlContext,
    namespace: str | None,
    all_namespaces: bool,
    event_type: str | None,
    for_object: str | None,
    watch: bool,
) -> None:
    """List cluster events.

    \b
    Examples:
        devctl k8s events
        devctl k8s events -n production
        devctl k8s events --type Warning
        devctl k8s events --for pod/my-pod
        devctl k8s events -w
    """
    try:
        ns = None if all_namespaces else (namespace or ctx.config.get_profile(ctx.profile_name).k8s.namespace)

        # Build field selector
        field_selector = None
        if for_object:
            kind, name = for_object.split("/", 1) if "/" in for_object else ("", for_object)
            if kind:
                field_selector = f"involvedObject.kind={kind.capitalize()},involvedObject.name={name}"
            else:
                field_selector = f"involvedObject.name={name}"

        if watch:
            _watch_events(ctx, ns, event_type, field_selector)
        else:
            _list_events(ctx, ns, event_type, field_selector, all_namespaces)

    except K8sError as e:
        ctx.output.print_error(f"Failed to get events: {e}")
        raise click.Abort()


def _list_events(
    ctx: DevCtlContext,
    namespace: str | None,
    event_type: str | None,
    field_selector: str | None,
    all_namespaces: bool,
) -> None:
    """List events."""
    events_list = ctx.k8s.list_events(
        namespace=namespace,
        field_selector=field_selector,
    )

    # Filter by type if specified
    if event_type:
        events_list = [e for e in events_list if e.get("type", "").lower() == event_type.lower()]

    if not events_list:
        ctx.output.print_info("No events found")
        return

    # Sort by last timestamp
    events_list.sort(
        key=lambda e: e.get("lastTimestamp") or e.get("eventTime") or "",
        reverse=True,
    )

    rows = []
    for event in events_list[:50]:  # Limit to 50 most recent
        metadata = event.get("metadata", {})
        involved = event.get("involvedObject", {})

        rows.append({
            "namespace": metadata.get("namespace", ""),
            "last_seen": _format_age(event.get("lastTimestamp") or event.get("eventTime")),
            "type": event.get("type", ""),
            "reason": event.get("reason", ""),
            "object": f"{involved.get('kind', '')}/{involved.get('name', '')}",
            "message": _truncate(event.get("message", ""), 60),
        })

    columns = ["namespace", "last_seen", "type", "reason", "object", "message"] if namespace is None else ["last_seen", "type", "reason", "object", "message"]

    ctx.output.print_table(rows, columns=columns, title="Events")


def _watch_events(
    ctx: DevCtlContext,
    namespace: str | None,
    event_type: str | None,
    field_selector: str | None,
) -> None:
    """Watch events in real-time."""
    ctx.output.print_info("Watching events (Ctrl+C to stop)...")

    try:
        for event in ctx.k8s.watch_events(namespace=namespace, field_selector=field_selector):
            event_data = event.get("object", {})

            # Filter by type if specified
            if event_type and event_data.get("type", "").lower() != event_type.lower():
                continue

            involved = event_data.get("involvedObject", {})
            metadata = event_data.get("metadata", {})

            # Format event line
            event_type_str = event_data.get("type", "Normal")
            reason = event_data.get("reason", "")
            obj = f"{involved.get('kind', '')}/{involved.get('name', '')}"
            message = event_data.get("message", "")
            ns = metadata.get("namespace", "")

            if event_type_str == "Warning":
                ctx.output.print_warning(f"[{ns}] {event_type_str} {reason}: {obj} - {message}")
            else:
                ctx.output.print(f"[{ns}] {event_type_str} {reason}: {obj} - {message}")

    except KeyboardInterrupt:
        ctx.output.print_info("\nStopped watching")


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


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
