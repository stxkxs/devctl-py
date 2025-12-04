"""PagerDuty service commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import PagerDutyError


@click.group()
def services() -> None:
    """Service operations."""
    pass


@services.command("list")
@click.option("-q", "--query", default=None, help="Search query")
@click.option("--team", default=None, help="Filter by team ID")
@pass_context
def list_services(
    ctx: DevCtlContext,
    query: str | None,
    team: str | None,
) -> None:
    """List services.

    \b
    Examples:
        devctl pagerduty services list
        devctl pagerduty services list -q "api"
    """
    try:
        services_list = ctx.pagerduty.list_services(
            query=query,
            team_ids=[team] if team else None,
        )

        if not services_list:
            ctx.output.print_info("No services found")
            return

        rows = []
        for svc in services_list:
            rows.append({
                "id": svc.get("id", ""),
                "name": svc.get("name", ""),
                "status": svc.get("status", ""),
                "escalation_policy": svc.get("escalation_policy", {}).get("summary", ""),
            })

        ctx.output.print_table(
            rows,
            columns=["id", "name", "status", "escalation_policy"],
            title="Services",
        )

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to list services: {e}")
        raise click.Abort()


@services.command("show")
@click.argument("service_id")
@pass_context
def show_service(ctx: DevCtlContext, service_id: str) -> None:
    """Show service details.

    \b
    Examples:
        devctl pagerduty services show P123ABC
    """
    try:
        service = ctx.pagerduty.get_service(service_id)

        ctx.output.print_header(f"Service: {service.get('name', '')}")
        ctx.output.print(f"ID: {service.get('id', '')}")
        ctx.output.print(f"Status: {service.get('status', '')}")
        ctx.output.print(f"Description: {service.get('description', '')}")

        # Escalation policy
        policy = service.get("escalation_policy", {})
        if policy:
            ctx.output.print(f"\nEscalation Policy: {policy.get('summary', '')}")
            ctx.output.print(f"  ID: {policy.get('id', '')}")

        # Integrations
        integrations = service.get("integrations", [])
        if integrations:
            ctx.output.print("\nIntegrations:")
            for intg in integrations:
                ctx.output.print(f"  - {intg.get('summary', '')} ({intg.get('type', '')})")

    except PagerDutyError as e:
        ctx.output.print_error(f"Failed to get service: {e}")
        raise click.Abort()
