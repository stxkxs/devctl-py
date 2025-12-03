"""Grafana datasource commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import GrafanaError


@click.group()
@pass_context
def datasources(ctx: DevCtlContext) -> None:
    """Datasource operations - list, test, details.

    \b
    Examples:
        devctl grafana datasources list
        devctl grafana datasources test prometheus
        devctl grafana datasources get prometheus
    """
    pass


@datasources.command("list")
@pass_context
def list_datasources(ctx: DevCtlContext) -> None:
    """List all datasources."""
    try:
        client = ctx.grafana
        datasources_list = client.list_datasources()

        if not datasources_list:
            ctx.output.print_info("No datasources configured")
            return

        data = []
        for ds in datasources_list:
            data.append({
                "Name": ds.get("name", "-"),
                "Type": ds.get("type", "-"),
                "UID": ds.get("uid", "-"),
                "URL": ds.get("url", "-")[:40],
                "Default": "Yes" if ds.get("isDefault") else "No",
            })

        ctx.output.print_data(
            data,
            headers=["Name", "Type", "UID", "URL", "Default"],
            title=f"Datasources ({len(data)} configured)",
        )

    except Exception as e:
        raise GrafanaError(f"Failed to list datasources: {e}")


@datasources.command("get")
@click.argument("name_or_uid")
@pass_context
def get_datasource(ctx: DevCtlContext, name_or_uid: str) -> None:
    """Get datasource details."""
    try:
        client = ctx.grafana

        # Try by UID first
        try:
            datasource = client.get_datasource(name_or_uid)
        except GrafanaError:
            # Try by name
            datasources_list = client.list_datasources()
            datasource = next(
                (ds for ds in datasources_list if ds.get("name") == name_or_uid),
                None,
            )
            if not datasource:
                raise GrafanaError(f"Datasource not found: {name_or_uid}")

        data = {
            "Name": datasource.get("name", "-"),
            "Type": datasource.get("type", "-"),
            "UID": datasource.get("uid", "-"),
            "URL": datasource.get("url", "-"),
            "Database": datasource.get("database", "-"),
            "User": datasource.get("user", "-"),
            "Default": "Yes" if datasource.get("isDefault") else "No",
            "ReadOnly": "Yes" if datasource.get("readOnly") else "No",
            "BasicAuth": "Yes" if datasource.get("basicAuth") else "No",
        }

        ctx.output.print_data(data, title=f"Datasource: {datasource.get('name')}")

        # Show JSON data in verbose mode
        if ctx.verbose >= 2:
            import json
            json_data = datasource.get("jsonData", {})
            if json_data:
                ctx.output.print_code(json.dumps(json_data, indent=2), "json")

    except Exception as e:
        raise GrafanaError(f"Failed to get datasource: {e}")


@datasources.command("test")
@click.argument("name_or_uid")
@pass_context
def test_datasource(ctx: DevCtlContext, name_or_uid: str) -> None:
    """Test datasource connection."""
    try:
        client = ctx.grafana

        # Get UID if name provided
        try:
            ds = client.get_datasource(name_or_uid)
            uid = ds.get("uid")
            name = ds.get("name")
        except GrafanaError:
            datasources_list = client.list_datasources()
            ds = next(
                (d for d in datasources_list if d.get("name") == name_or_uid),
                None,
            )
            if not ds:
                raise GrafanaError(f"Datasource not found: {name_or_uid}")
            uid = ds.get("uid")
            name = ds.get("name")

        ctx.output.print_info(f"Testing datasource: {name}")

        # Test connection
        result = client.test_datasource(uid)

        status = result.get("status", "unknown")
        message = result.get("message", "No message")

        if status == "success":
            ctx.output.print_success(f"Connection successful: {message}")
        else:
            ctx.output.print_error(f"Connection failed: {message}")

    except Exception as e:
        raise GrafanaError(f"Failed to test datasource: {e}")


@datasources.command("health")
@pass_context
def datasources_health(ctx: DevCtlContext) -> None:
    """Check health of all datasources."""
    try:
        client = ctx.grafana
        datasources_list = client.list_datasources()

        if not datasources_list:
            ctx.output.print_info("No datasources configured")
            return

        data = []
        for ds in datasources_list:
            name = ds.get("name", "-")
            uid = ds.get("uid")

            try:
                result = client.test_datasource(uid)
                status = result.get("status", "unknown")

                if status == "success":
                    status_display = "[green]OK[/green]"
                else:
                    status_display = f"[red]{status.upper()}[/red]"

                message = result.get("message", "-")[:40]
            except Exception as e:
                status_display = "[red]ERROR[/red]"
                message = str(e)[:40]

            data.append({
                "Name": name,
                "Type": ds.get("type", "-"),
                "Status": status_display,
                "Message": message,
            })

        ctx.output.print_data(
            data,
            headers=["Name", "Type", "Status", "Message"],
            title="Datasource Health Check",
        )

    except Exception as e:
        raise GrafanaError(f"Health check failed: {e}")
