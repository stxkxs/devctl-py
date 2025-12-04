"""PagerDuty incident commands."""

import click
from datetime import datetime, timedelta

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import PagerDutyError


@click.group()
def incidents() -> None:
    """Incident operations - list, create, ack, resolve, escalate."""
    pass


@incidents.command("list")
@click.option("--status", multiple=True, help="Status filter (triggered, acknowledged, resolved)")
@click.option("--urgency", multiple=True, help="Urgency filter (high, low)")
@click.option("--since", default=None, help="Show incidents since (e.g., 1d, 7d)")
@click.option("--service", default=None, help="Filter by service ID")
@click.option("--limit", default=25, help="Max results")
@pass_context
def list_incidents(
    ctx: DevCtlContext,
    status: tuple[str, ...],
    urgency: tuple[str, ...],
    since: str | None,
    service: str | None,
    limit: int,
) -> None:
    """List incidents.

    \b
    Examples:
        devctl pagerduty incidents list
        devctl pagerduty incidents list --status triggered
        devctl pagerduty incidents list --since 7d
    """
    try:
        # Parse since
        since_dt = None
        if since:
            since_dt = _parse_since(since)

        incidents = ctx.pagerduty.list_incidents(
            statuses=list(status) if status else None,
            urgencies=list(urgency) if urgency else None,
            service_ids=[service] if service else None,
            since=since_dt,
            limit=limit,
        )

        if not incidents:
            ctx.output.print_info("No incidents found")
            return

        rows = []
        for inc in incidents:
            rows.append({
                "id": inc.get("id", ""),
                "status": inc.get("status", ""),
                "urgency": inc.get("urgency", ""),
                "title": _truncate(inc.get("title", ""), 50),
                "service": inc.get("service", {}).get("summary", ""),
                "created": _format_time(inc.get("created_at")),
            })

        ctx.output.print_table(
            rows,
            columns=["id", "status", "urgency", "title", "service", "created"],
            title="Incidents",
        )

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to list incidents: {e}")
        raise click.Abort()


@incidents.command("create")
@click.argument("title")
@click.option("--service", required=True, help="Service ID")
@click.option("--urgency", type=click.Choice(["high", "low"]), default="high", help="Urgency")
@click.option("--body", default=None, help="Incident description")
@click.option("--key", default=None, help="Incident dedup key")
@pass_context
def create(
    ctx: DevCtlContext,
    title: str,
    service: str,
    urgency: str,
    body: str | None,
    key: str | None,
) -> None:
    """Create an incident.

    \b
    Examples:
        devctl pagerduty incidents create "Database is down" --service P123ABC
        devctl pagerduty incidents create "High CPU" --service P123ABC --urgency low
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("create incident", {"title": title, "service": service, "urgency": urgency})
            return

        incident = ctx.pagerduty.create_incident(
            title=title,
            service_id=service,
            urgency=urgency,
            body=body,
            incident_key=key,
        )

        ctx.output.print_success(f"Created incident: {incident.get('id')}")
        ctx.output.print(f"Title: {incident.get('title')}")
        ctx.output.print(f"Status: {incident.get('status')}")
        ctx.output.print(f"URL: {incident.get('html_url', '')}")

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to create incident: {e}")
        raise click.Abort()


@incidents.command("ack")
@click.argument("incident_id")
@pass_context
def ack(ctx: DevCtlContext, incident_id: str) -> None:
    """Acknowledge an incident.

    \b
    Examples:
        devctl pagerduty incidents ack P123ABC
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("acknowledge incident", {"id": incident_id})
            return

        incident = ctx.pagerduty.acknowledge_incident(incident_id)
        ctx.output.print_success(f"Acknowledged: {incident.get('id')}")

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to acknowledge incident: {e}")
        raise click.Abort()


@incidents.command("resolve")
@click.argument("incident_id")
@click.option("-r", "--resolution", default=None, help="Resolution note")
@pass_context
def resolve(ctx: DevCtlContext, incident_id: str, resolution: str | None) -> None:
    """Resolve an incident.

    \b
    Examples:
        devctl pagerduty incidents resolve P123ABC
        devctl pagerduty incidents resolve P123ABC -r "Fixed by restarting service"
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("resolve incident", {"id": incident_id, "resolution": resolution})
            return

        incident = ctx.pagerduty.resolve_incident(incident_id, resolution=resolution)
        ctx.output.print_success(f"Resolved: {incident.get('id')}")

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to resolve incident: {e}")
        raise click.Abort()


@incidents.command("escalate")
@click.argument("incident_id")
@click.option("--level", type=int, default=2, help="Escalation level")
@pass_context
def escalate(ctx: DevCtlContext, incident_id: str, level: int) -> None:
    """Escalate an incident.

    \b
    Examples:
        devctl pagerduty incidents escalate P123ABC
        devctl pagerduty incidents escalate P123ABC --level 3
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("escalate incident", {"id": incident_id, "level": level})
            return

        incident = ctx.pagerduty.escalate_incident(incident_id, escalation_level=level)
        ctx.output.print_success(f"Escalated to level {level}: {incident.get('id')}")

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to escalate incident: {e}")
        raise click.Abort()


@incidents.command("note")
@click.argument("incident_id")
@click.argument("content")
@pass_context
def add_note(ctx: DevCtlContext, incident_id: str, content: str) -> None:
    """Add a note to an incident.

    \b
    Examples:
        devctl pagerduty incidents note P123ABC "Investigating database connections"
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("add note", {"id": incident_id, "content": content})
            return

        note = ctx.pagerduty.add_note(incident_id, content)
        ctx.output.print_success("Added note to incident")

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to add note: {e}")
        raise click.Abort()


def _parse_since(since: str) -> datetime:
    """Parse since duration string to datetime."""
    value = int(since[:-1])
    unit = since[-1].lower()

    if unit == "h":
        return datetime.utcnow() - timedelta(hours=value)
    elif unit == "d":
        return datetime.utcnow() - timedelta(days=value)
    elif unit == "w":
        return datetime.utcnow() - timedelta(weeks=value)
    else:
        raise ValueError(f"Invalid time unit: {unit}")


def _format_time(timestamp: str | None) -> str:
    """Format timestamp for display."""
    if not timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return timestamp


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
