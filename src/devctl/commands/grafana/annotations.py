"""Grafana annotation commands."""

import time
from datetime import datetime
from typing import Any

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import GrafanaError
from devctl.core.utils import parse_time


@click.group()
@pass_context
def annotations(ctx: DevCtlContext) -> None:
    """Annotation operations - create, list.

    \b
    Examples:
        devctl grafana annotations create "Deployment v1.2.3"
        devctl grafana annotations list --tags deployment
    """
    pass


@annotations.command("create")
@click.argument("text")
@click.option("--dashboard", "-d", help="Dashboard UID")
@click.option("--panel", "-p", type=int, help="Panel ID")
@click.option("--tags", "-t", multiple=True, help="Tags for the annotation")
@click.option("--time", "time_str", help="Annotation time (default: now)")
@click.option("--end-time", help="End time for range annotation")
@pass_context
def create_annotation(
    ctx: DevCtlContext,
    text: str,
    dashboard: str | None,
    panel: int | None,
    tags: tuple[str, ...],
    time_str: str | None,
    end_time: str | None,
) -> None:
    """Create an annotation.

    TEXT is the annotation text/description.
    """
    if ctx.dry_run:
        ctx.log_dry_run("create annotation", {
            "text": text,
            "dashboard": dashboard,
            "tags": list(tags),
        })
        return

    try:
        client = ctx.grafana

        # Parse times
        annotation_time = None
        annotation_end = None

        if time_str:
            dt = parse_time(time_str)
            annotation_time = int(dt.timestamp() * 1000)

        if end_time:
            dt = parse_time(end_time)
            annotation_end = int(dt.timestamp() * 1000)

        result = client.create_annotation(
            text=text,
            tags=list(tags) if tags else None,
            dashboard_uid=dashboard,
            panel_id=panel,
            time=annotation_time,
            time_end=annotation_end,
        )

        ctx.output.print_success(f"Annotation created: {result.get('id')}")

    except Exception as e:
        raise GrafanaError(f"Failed to create annotation: {e}")


@annotations.command("list")
@click.option("--dashboard", "-d", help="Filter by dashboard UID")
@click.option("--tags", "-t", multiple=True, help="Filter by tags")
@click.option("--from", "from_time", help="Start time (e.g., -1h, -1d)")
@click.option("--to", "to_time", help="End time")
@click.option("--limit", type=int, default=100, help="Maximum annotations to return")
@pass_context
def list_annotations(
    ctx: DevCtlContext,
    dashboard: str | None,
    tags: tuple[str, ...],
    from_time: str | None,
    to_time: str | None,
    limit: int,
) -> None:
    """List annotations."""
    try:
        client = ctx.grafana

        # Parse times
        from_ts = None
        to_ts = None

        if from_time:
            dt = parse_time(from_time)
            from_ts = int(dt.timestamp() * 1000)
        else:
            # Default to last 24 hours
            from_ts = int((datetime.utcnow().timestamp() - 86400) * 1000)

        if to_time:
            dt = parse_time(to_time)
            to_ts = int(dt.timestamp() * 1000)

        annotations_list = client.list_annotations(
            dashboard_uid=dashboard,
            from_time=from_ts,
            to_time=to_ts,
            tags=list(tags) if tags else None,
        )

        if not annotations_list:
            ctx.output.print_info("No annotations found")
            return

        data = []
        for ann in annotations_list[:limit]:
            ts = ann.get("time", 0)
            if ts:
                dt = datetime.fromtimestamp(ts / 1000)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                time_str = "-"

            data.append({
                "ID": ann.get("id", "-"),
                "Time": time_str,
                "Text": ann.get("text", "-")[:40],
                "Tags": ", ".join(ann.get("tags", []))[:20],
                "Dashboard": ann.get("dashboardUID", "-")[:15] if ann.get("dashboardUID") else "Global",
            })

        ctx.output.print_data(
            data,
            headers=["ID", "Time", "Text", "Tags", "Dashboard"],
            title=f"Annotations ({len(data)} shown)",
        )

    except Exception as e:
        raise GrafanaError(f"Failed to list annotations: {e}")


@annotations.command("delete")
@click.argument("annotation_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@pass_context
def delete_annotation(ctx: DevCtlContext, annotation_id: int, yes: bool) -> None:
    """Delete an annotation by ID."""
    if ctx.dry_run:
        ctx.log_dry_run("delete annotation", {"id": annotation_id})
        return

    if not yes:
        if not ctx.confirm(f"Delete annotation {annotation_id}?"):
            ctx.output.print_info("Cancelled")
            return

    try:
        client = ctx.grafana
        client.delete(f"/api/annotations/{annotation_id}")
        ctx.output.print_success(f"Annotation {annotation_id} deleted")

    except Exception as e:
        raise GrafanaError(f"Failed to delete annotation: {e}")
