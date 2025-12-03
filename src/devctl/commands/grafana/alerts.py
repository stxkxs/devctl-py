"""Grafana alert commands."""

import json
from datetime import datetime, timedelta
from typing import Any

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import GrafanaError
from devctl.core.utils import parse_duration


@click.group()
@pass_context
def alerts(ctx: DevCtlContext) -> None:
    """Alert operations - rules, silences, status.

    \b
    Examples:
        devctl grafana alerts list --state firing
        devctl grafana alerts silence rule-uid --duration 1h
        devctl grafana alerts rules list
    """
    pass


@alerts.command("list")
@click.option("--state", type=click.Choice(["firing", "pending", "normal", "nodata", "error"]), help="Filter by state")
@pass_context
def list_alerts(ctx: DevCtlContext, state: str | None) -> None:
    """List alert instances."""
    try:
        client = ctx.grafana

        # Get alert instances from Alertmanager API
        response = client.get("/api/alertmanager/grafana/api/v2/alerts")

        if state:
            response = [a for a in response if a.get("status", {}).get("state") == state]

        if not response:
            ctx.output.print_info("No alerts found")
            return

        data = []
        for alert in response:
            labels = alert.get("labels", {})
            status = alert.get("status", {})

            state_value = status.get("state", "-")
            state_color = {
                "firing": "[red]FIRING[/red]",
                "pending": "[yellow]PENDING[/yellow]",
                "normal": "[green]NORMAL[/green]",
            }.get(state_value, state_value)

            data.append({
                "AlertName": labels.get("alertname", "-")[:30],
                "State": state_color,
                "Severity": labels.get("severity", "-"),
                "Summary": alert.get("annotations", {}).get("summary", "-")[:40],
                "StartsAt": alert.get("startsAt", "-")[:19],
            })

        ctx.output.print_data(
            data,
            headers=["AlertName", "State", "Severity", "Summary", "StartsAt"],
            title=f"Alert Instances ({len(data)} found)",
        )

    except Exception as e:
        raise GrafanaError(f"Failed to list alerts: {e}")


@alerts.command("silence")
@click.argument("rule_uid")
@click.option("--duration", "-d", default="1h", help="Silence duration (e.g., 30m, 2h, 1d)")
@click.option("--comment", "-c", default="Silenced via devctl", help="Comment for the silence")
@pass_context
def silence_alert(ctx: DevCtlContext, rule_uid: str, duration: str, comment: str) -> None:
    """Silence an alert rule."""
    if ctx.dry_run:
        ctx.log_dry_run("silence alert", {"rule_uid": rule_uid, "duration": duration})
        return

    try:
        client = ctx.grafana

        # Parse duration
        delta = parse_duration(duration)
        starts_at = datetime.utcnow()
        ends_at = starts_at + delta

        # Create silence
        matchers = [{"name": "rule_uid", "value": rule_uid, "isRegex": False}]

        result = client.create_silence(
            matchers=matchers,
            starts_at=starts_at.isoformat() + "Z",
            ends_at=ends_at.isoformat() + "Z",
            comment=comment,
            created_by="devctl",
        )

        ctx.output.print_success(f"Alert silenced until {ends_at.strftime('%Y-%m-%d %H:%M')}")
        ctx.output.print_info(f"Silence ID: {result.get('silenceID', '-')}")

    except Exception as e:
        raise GrafanaError(f"Failed to silence alert: {e}")


@alerts.command("silences")
@click.option("--active", is_flag=True, help="Show only active silences")
@pass_context
def list_silences(ctx: DevCtlContext, active: bool) -> None:
    """List alert silences."""
    try:
        client = ctx.grafana
        silences = client.list_silences()

        if active:
            now = datetime.utcnow().isoformat()
            silences = [
                s for s in silences
                if s.get("status", {}).get("state") == "active"
            ]

        if not silences:
            ctx.output.print_info("No silences found")
            return

        data = []
        for silence in silences:
            status = silence.get("status", {})
            matchers = silence.get("matchers", [])
            matcher_str = ", ".join(f"{m['name']}={m['value']}" for m in matchers[:2])

            data.append({
                "ID": silence.get("id", "-")[:12],
                "State": status.get("state", "-"),
                "Matchers": matcher_str[:30],
                "Comment": silence.get("comment", "-")[:25],
                "EndsAt": silence.get("endsAt", "-")[:19],
            })

        ctx.output.print_data(
            data,
            headers=["ID", "State", "Matchers", "Comment", "EndsAt"],
            title=f"Silences ({len(data)} found)",
        )

    except Exception as e:
        raise GrafanaError(f"Failed to list silences: {e}")


@alerts.group()
@pass_context
def rules(ctx: DevCtlContext) -> None:
    """Alert rule operations."""
    pass


@rules.command("list")
@click.option("--folder", help="Filter by folder UID")
@pass_context
def list_rules(ctx: DevCtlContext, folder: str | None) -> None:
    """List alert rules."""
    try:
        client = ctx.grafana

        # Use provisioning API
        response = client.list_alert_rules()

        if folder:
            response = [r for r in response if r.get("folderUID") == folder]

        if not response:
            ctx.output.print_info("No alert rules found")
            return

        data = []
        for rule in response:
            data.append({
                "Title": rule.get("title", "-")[:30],
                "UID": rule.get("uid", "-"),
                "Folder": rule.get("folderUID", "-")[:15],
                "Condition": rule.get("condition", "-"),
                "For": rule.get("for", "-"),
            })

        ctx.output.print_data(
            data,
            headers=["Title", "UID", "Folder", "Condition", "For"],
            title=f"Alert Rules ({len(data)} found)",
        )

    except Exception as e:
        raise GrafanaError(f"Failed to list alert rules: {e}")


@rules.command("get")
@click.argument("uid")
@pass_context
def get_rule(ctx: DevCtlContext, uid: str) -> None:
    """Get alert rule details."""
    try:
        client = ctx.grafana
        rule = client.get_alert_rule(uid)

        data = {
            "Title": rule.get("title", "-"),
            "UID": rule.get("uid", "-"),
            "Folder": rule.get("folderUID", "-"),
            "Condition": rule.get("condition", "-"),
            "For": rule.get("for", "-"),
            "NoDataState": rule.get("noDataState", "-"),
            "ExecErrState": rule.get("execErrState", "-"),
        }

        ctx.output.print_data(data, title=f"Alert Rule: {rule.get('title')}")

        # Show annotations
        annotations = rule.get("annotations", {})
        if annotations:
            ctx.output.print_data(annotations, title="Annotations")

        # Show labels
        labels = rule.get("labels", {})
        if labels:
            ctx.output.print_data(labels, title="Labels")

    except Exception as e:
        raise GrafanaError(f"Failed to get alert rule: {e}")


@rules.command("export")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@pass_context
def export_rules(ctx: DevCtlContext, output: str | None) -> None:
    """Export all alert rules to JSON."""
    try:
        client = ctx.grafana
        rules_list = client.list_alert_rules()

        json_content = json.dumps(rules_list, indent=2)

        if output:
            from pathlib import Path
            Path(output).write_text(json_content)
            ctx.output.print_success(f"Alert rules exported to {output}")
        else:
            ctx.output.print_code(json_content, "json")

    except Exception as e:
        raise GrafanaError(f"Failed to export alert rules: {e}")
