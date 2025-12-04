"""Slack command group."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import SlackError


@click.group()
@pass_context
def slack(ctx: DevCtlContext) -> None:
    """Slack operations - messages, channels, notifications.

    \b
    Examples:
        devctl slack send "#devops" "Deployment complete"
        devctl slack notify --type deployment --service my-app
        devctl slack channels list
    """
    pass


@slack.command("send")
@click.argument("channel")
@click.argument("message")
@click.option("--thread", default=None, help="Thread timestamp to reply to")
@pass_context
def send(ctx: DevCtlContext, channel: str, message: str, thread: str | None) -> None:
    """Send a message.

    \b
    Examples:
        devctl slack send "#devops" "Hello from devctl"
        devctl slack send "#alerts" "Incident resolved" --thread 1234567890.123456
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("send message", {"channel": channel, "message": message[:50]})
            return

        result = ctx.slack.post_message(channel, message, thread_ts=thread)

        ctx.output.print_success(f"Message sent to {channel}")
        if result.get("ts"):
            ctx.output.print(f"Timestamp: {result.get('ts')}")

    except SlackError as e:
        ctx.output.print_error(f"Failed to send message: {e}")
        raise click.Abort()


@slack.command("notify")
@click.option("--type", "notify_type", type=click.Choice(["deployment", "incident", "build"]), required=True, help="Notification type")
@click.option("--channel", default=None, help="Channel (uses default if not specified)")
@click.option("--service", default=None, help="Service name")
@click.option("--version", default=None, help="Version")
@click.option("--environment", default=None, help="Environment")
@click.option("--status", default="started", help="Status")
@click.option("--url", default=None, help="Details URL")
@click.option("--title", default=None, help="Title (for incidents)")
@click.option("--severity", default=None, help="Severity (for incidents)")
@pass_context
def notify(
    ctx: DevCtlContext,
    notify_type: str,
    channel: str | None,
    service: str | None,
    version: str | None,
    environment: str | None,
    status: str,
    url: str | None,
    title: str | None,
    severity: str | None,
) -> None:
    """Send a formatted notification.

    \b
    Examples:
        devctl slack notify --type deployment --service my-app --version v1.2.3 --environment production --status succeeded
        devctl slack notify --type incident --title "Database down" --severity critical --status triggered
        devctl slack notify --type build --service my-app --status succeeded
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("notify", {"type": notify_type, "channel": channel})
            return

        result = ctx.slack.send_notification(
            notification_type=notify_type,
            channel=channel,
            service=service or "unknown",
            version=version or "unknown",
            environment=environment or "unknown",
            status=status,
            url=url,
            title=title or "Notification",
            severity=severity or "medium",
        )

        ctx.output.print_success(f"Notification sent ({notify_type})")

    except SlackError as e:
        ctx.output.print_error(f"Failed to send notification: {e}")
        raise click.Abort()


@slack.group("channels")
def channels() -> None:
    """Channel operations."""
    pass


@channels.command("list")
@click.option("--include-archived", is_flag=True, help="Include archived channels")
@click.option("--limit", default=100, help="Max results")
@pass_context
def list_channels(ctx: DevCtlContext, include_archived: bool, limit: int) -> None:
    """List channels.

    \b
    Examples:
        devctl slack channels list
    """
    try:
        result = ctx.slack.list_channels(
            exclude_archived=not include_archived,
            limit=limit,
        )

        channels_list = result.get("channels", [])

        if not channels_list:
            ctx.output.print_info("No channels found")
            return

        rows = []
        for ch in channels_list:
            rows.append({
                "id": ch.get("id", ""),
                "name": ch.get("name", ""),
                "members": ch.get("num_members", 0),
                "private": "Yes" if ch.get("is_private") else "No",
                "archived": "Yes" if ch.get("is_archived") else "No",
            })

        ctx.output.print_table(rows, columns=["id", "name", "members", "private", "archived"], title="Channels")

    except SlackError as e:
        ctx.output.print_error(f"Failed to list channels: {e}")
        raise click.Abort()


@channels.command("create")
@click.argument("name")
@click.option("--private", is_flag=True, help="Create private channel")
@pass_context
def create_channel(ctx: DevCtlContext, name: str, private: bool) -> None:
    """Create a channel.

    \b
    Examples:
        devctl slack channels create incident-2024-01-15
        devctl slack channels create team-private --private
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("create channel", {"name": name, "private": private})
            return

        result = ctx.slack.create_channel(name, is_private=private)

        ctx.output.print_success(f"Created channel: {result.get('name', name)}")
        ctx.output.print(f"ID: {result.get('id', '')}")

    except SlackError as e:
        ctx.output.print_error(f"Failed to create channel: {e}")
        raise click.Abort()


@channels.command("archive")
@click.argument("channel")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@pass_context
def archive_channel(ctx: DevCtlContext, channel: str, yes: bool) -> None:
    """Archive a channel.

    \b
    Examples:
        devctl slack channels archive incident-2024-01-15
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("archive channel", {"channel": channel})
            return

        if not yes and not ctx.confirm(f"Archive channel {channel}?"):
            ctx.output.print_info("Cancelled")
            return

        ctx.slack.archive_channel(channel)
        ctx.output.print_success(f"Archived channel: {channel}")

    except SlackError as e:
        ctx.output.print_error(f"Failed to archive channel: {e}")
        raise click.Abort()


@slack.group("users")
def users() -> None:
    """User operations."""
    pass


@users.command("list")
@click.option("--limit", default=100, help="Max results")
@pass_context
def list_users(ctx: DevCtlContext, limit: int) -> None:
    """List users.

    \b
    Examples:
        devctl slack users list
    """
    try:
        result = ctx.slack.list_users(limit=limit)

        members = result.get("members", [])
        # Filter out bots and deleted users
        members = [m for m in members if not m.get("is_bot") and not m.get("deleted")]

        if not members:
            ctx.output.print_info("No users found")
            return

        rows = []
        for user in members:
            profile = user.get("profile", {})
            rows.append({
                "id": user.get("id", ""),
                "name": user.get("name", ""),
                "real_name": profile.get("real_name", ""),
                "email": profile.get("email", ""),
            })

        ctx.output.print_table(rows, columns=["id", "name", "real_name", "email"], title="Users")

    except SlackError as e:
        ctx.output.print_error(f"Failed to list users: {e}")
        raise click.Abort()


@slack.command("thread")
@click.argument("channel")
@click.argument("thread_ts")
@click.argument("message")
@pass_context
def thread_reply(ctx: DevCtlContext, channel: str, thread_ts: str, message: str) -> None:
    """Reply to a thread.

    \b
    Examples:
        devctl slack thread "#devops" 1234567890.123456 "Following up on this"
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("thread reply", {"channel": channel, "thread": thread_ts})
            return

        result = ctx.slack.reply_to_thread(channel, thread_ts, message)

        ctx.output.print_success("Reply sent")

    except SlackError as e:
        ctx.output.print_error(f"Failed to send reply: {e}")
        raise click.Abort()
