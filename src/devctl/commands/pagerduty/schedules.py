"""PagerDuty schedule commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import PagerDutyError


@click.group()
def schedules() -> None:
    """Schedule operations."""
    pass


@schedules.command("list")
@click.option("-q", "--query", default=None, help="Search query")
@pass_context
def list_schedules(ctx: DevCtlContext, query: str | None) -> None:
    """List schedules.

    \b
    Examples:
        devctl pagerduty schedules list
        devctl pagerduty schedules list -q "primary"
    """
    try:
        schedules_list = ctx.pagerduty.list_schedules(query=query)

        if not schedules_list:
            ctx.output.print_info("No schedules found")
            return

        rows = []
        for sched in schedules_list:
            rows.append({
                "id": sched.get("id", ""),
                "name": sched.get("name", ""),
                "time_zone": sched.get("time_zone", ""),
                "users": len(sched.get("users", [])),
            })

        ctx.output.print_table(
            rows,
            columns=["id", "name", "time_zone", "users"],
            title="Schedules",
        )

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to list schedules: {e}")
        raise click.Abort()


@schedules.command("show")
@click.argument("schedule_id")
@pass_context
def show_schedule(ctx: DevCtlContext, schedule_id: str) -> None:
    """Show schedule details.

    \b
    Examples:
        devctl pagerduty schedules show P123ABC
    """
    try:
        schedule = ctx.pagerduty.get_schedule(schedule_id)

        ctx.output.print_header(f"Schedule: {schedule.get('name', '')}")
        ctx.output.print(f"ID: {schedule.get('id', '')}")
        ctx.output.print(f"Time Zone: {schedule.get('time_zone', '')}")
        ctx.output.print(f"Description: {schedule.get('description', '')}")

        # Show users
        users = schedule.get("users", [])
        if users:
            ctx.output.print("\nUsers:")
            for user in users:
                ctx.output.print(f"  - {user.get('summary', '')}")

        # Show final schedule entries
        final = schedule.get("final_schedule", {})
        entries = final.get("rendered_schedule_entries", [])
        if entries:
            ctx.output.print("\nUpcoming on-call:")
            for entry in entries[:5]:
                user = entry.get("user", {})
                ctx.output.print(
                    f"  {user.get('summary', '')}: "
                    f"{_format_time(entry.get('start'))} - {_format_time(entry.get('end'))}"
                )

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to get schedule: {e}")
        raise click.Abort()


def _format_time(timestamp: str | None) -> str:
    """Format timestamp for display."""
    if not timestamp:
        return ""
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return timestamp
