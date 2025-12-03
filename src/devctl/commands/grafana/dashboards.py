"""Grafana dashboard commands."""

import json
from pathlib import Path
from typing import Any

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import GrafanaError


@click.group()
@pass_context
def dashboards(ctx: DevCtlContext) -> None:
    """Dashboard operations - list, export, import, backup.

    \b
    Examples:
        devctl grafana dashboards list
        devctl grafana dashboards export abc123 --output dashboard.json
        devctl grafana dashboards backup --output ./backups
    """
    pass


@dashboards.command("list")
@click.option("--folder", help="Filter by folder UID")
@pass_context
def list_dashboards(ctx: DevCtlContext, folder: str | None) -> None:
    """List all dashboards."""
    try:
        client = ctx.grafana

        # Get dashboards
        params: dict[str, Any] = {"type": "dash-db"}
        if folder:
            # Get folder ID from UID
            folder_info = client.get_folder(folder)
            params["folderIds"] = folder_info.get("id")

        dashboards_list = client.get("/api/search", params=params)

        if not dashboards_list:
            ctx.output.print_info("No dashboards found")
            return

        data = []
        for db in dashboards_list:
            data.append({
                "Title": db["title"][:40],
                "UID": db["uid"],
                "Folder": db.get("folderTitle", "General")[:20],
                "Tags": ", ".join(db.get("tags", []))[:30],
            })

        ctx.output.print_data(
            data,
            headers=["Title", "UID", "Folder", "Tags"],
            title=f"Dashboards ({len(data)} found)",
        )

    except Exception as e:
        raise GrafanaError(f"Failed to list dashboards: {e}")


@dashboards.command("get")
@click.argument("uid")
@pass_context
def get_dashboard(ctx: DevCtlContext, uid: str) -> None:
    """Get dashboard details by UID."""
    try:
        client = ctx.grafana
        dashboard = client.get_dashboard(uid)

        meta = dashboard.get("meta", {})
        db = dashboard.get("dashboard", {})

        data = {
            "Title": db.get("title", "-"),
            "UID": db.get("uid", "-"),
            "ID": db.get("id", "-"),
            "Version": meta.get("version", "-"),
            "Folder": meta.get("folderTitle", "General"),
            "Created": meta.get("created", "-"),
            "Updated": meta.get("updated", "-"),
            "CreatedBy": meta.get("createdBy", "-"),
            "UpdatedBy": meta.get("updatedBy", "-"),
            "Panels": len(db.get("panels", [])),
            "Tags": ", ".join(db.get("tags", [])),
        }

        ctx.output.print_data(data, title=f"Dashboard: {db.get('title')}")

        # Show panels in verbose mode
        if ctx.verbose >= 1:
            panels = db.get("panels", [])
            if panels:
                panel_data = []
                for p in panels:
                    panel_data.append({
                        "ID": p.get("id", "-"),
                        "Title": p.get("title", "(untitled)")[:30],
                        "Type": p.get("type", "-"),
                    })
                ctx.output.print_data(panel_data, title="Panels")

    except Exception as e:
        raise GrafanaError(f"Failed to get dashboard: {e}")


@dashboards.command("export")
@click.argument("uid")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@pass_context
def export_dashboard(ctx: DevCtlContext, uid: str, output: str | None) -> None:
    """Export dashboard to JSON file."""
    try:
        client = ctx.grafana
        dashboard = client.get_dashboard(uid)

        db = dashboard.get("dashboard", {})

        # Remove server-specific fields for portability
        db.pop("id", None)
        db.pop("version", None)

        json_content = json.dumps(db, indent=2)

        if output:
            Path(output).write_text(json_content)
            ctx.output.print_success(f"Dashboard exported to {output}")
        else:
            ctx.output.print_code(json_content, "json")

    except Exception as e:
        raise GrafanaError(f"Failed to export dashboard: {e}")


@dashboards.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--folder", help="Target folder UID")
@click.option("--overwrite", is_flag=True, help="Overwrite if exists")
@pass_context
def import_dashboard(ctx: DevCtlContext, file: str, folder: str | None, overwrite: bool) -> None:
    """Import dashboard from JSON file."""
    if ctx.dry_run:
        ctx.log_dry_run("import dashboard", {"file": file, "folder": folder})
        return

    try:
        with open(file) as f:
            dashboard = json.load(f)

        client = ctx.grafana
        result = client.create_dashboard(
            dashboard=dashboard,
            folder_uid=folder,
            overwrite=overwrite,
        )

        ctx.output.print_success(f"Dashboard imported: {result.get('uid')}")
        ctx.output.print_info(f"URL: {result.get('url', '-')}")

    except json.JSONDecodeError as e:
        raise GrafanaError(f"Invalid JSON file: {e}")
    except Exception as e:
        raise GrafanaError(f"Failed to import dashboard: {e}")


@dashboards.command()
@click.option("--folder", help="Backup specific folder only")
@click.option("--output", "-o", type=click.Path(), default="./grafana-backup", help="Output directory")
@pass_context
def backup(ctx: DevCtlContext, folder: str | None, output: str) -> None:
    """Backup all dashboards to a directory."""
    if ctx.dry_run:
        ctx.log_dry_run("backup dashboards", {"output": output, "folder": folder})
        return

    try:
        client = ctx.grafana
        output_dir = Path(output)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get all dashboards
        params: dict[str, Any] = {"type": "dash-db"}
        if folder:
            folder_info = client.get_folder(folder)
            params["folderIds"] = folder_info.get("id")

        dashboards_list = client.get("/api/search", params=params)

        ctx.output.print_info(f"Backing up {len(dashboards_list)} dashboards...")

        backed_up = 0
        for db_meta in dashboards_list:
            uid = db_meta["uid"]
            title = db_meta["title"]

            try:
                dashboard = client.get_dashboard(uid)
                db = dashboard.get("dashboard", {})

                # Remove server-specific fields
                db.pop("id", None)
                db.pop("version", None)

                # Create filename from title
                safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)
                filename = output_dir / f"{safe_name}_{uid}.json"

                filename.write_text(json.dumps(db, indent=2))
                backed_up += 1

            except Exception as e:
                ctx.output.print_warning(f"Failed to backup {title}: {e}")

        ctx.output.print_success(f"Backed up {backed_up} dashboards to {output_dir}")

    except Exception as e:
        raise GrafanaError(f"Backup failed: {e}")


@dashboards.command("delete")
@click.argument("uid")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@pass_context
def delete_dashboard(ctx: DevCtlContext, uid: str, yes: bool) -> None:
    """Delete a dashboard by UID."""
    try:
        client = ctx.grafana

        # Get dashboard info first
        dashboard = client.get_dashboard(uid)
        title = dashboard.get("dashboard", {}).get("title", uid)

        if ctx.dry_run:
            ctx.log_dry_run("delete dashboard", {"uid": uid, "title": title})
            return

        if not yes:
            if not ctx.confirm(f"Delete dashboard '{title}'?"):
                ctx.output.print_info("Cancelled")
                return

        client.delete_dashboard(uid)
        ctx.output.print_success(f"Dashboard '{title}' deleted")

    except Exception as e:
        raise GrafanaError(f"Failed to delete dashboard: {e}")
