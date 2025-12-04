"""PagerDuty on-call commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import PagerDutyError


@click.command("oncall")
@click.option("--schedule", default=None, help="Filter by schedule ID")
@click.option("--user", default=None, help="Filter by user ID")
@click.option("--policy", default=None, help="Filter by escalation policy ID")
@pass_context
def oncall(
    ctx: DevCtlContext,
    schedule: str | None,
    user: str | None,
    policy: str | None,
) -> None:
    """Show who is currently on-call.

    \b
    Examples:
        devctl pagerduty oncall
        devctl pagerduty oncall --schedule P123ABC
        devctl pagerduty oncall --policy P456DEF
    """
    try:
        oncalls = ctx.pagerduty.get_oncalls(
            schedule_ids=[schedule] if schedule else None,
            user_ids=[user] if user else None,
            escalation_policy_ids=[policy] if policy else None,
        )

        if not oncalls:
            ctx.output.print_info("No on-call entries found")
            return

        rows = []
        for oc in oncalls:
            user_info = oc.get("user", {})
            schedule_info = oc.get("schedule", {})
            policy_info = oc.get("escalation_policy", {})
            level = oc.get("escalation_level", 1)

            rows.append({
                "user": user_info.get("summary", ""),
                "email": user_info.get("email", ""),
                "schedule": schedule_info.get("summary", "") if schedule_info else "Direct",
                "policy": policy_info.get("summary", ""),
                "level": level,
                "start": _format_time(oc.get("start")),
                "end": _format_time(oc.get("end")),
            })

        ctx.output.print_table(
            rows,
            columns=["user", "email", "schedule", "policy", "level", "start", "end"],
            title="On-Call",
        )

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to get on-call: {e}")
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
