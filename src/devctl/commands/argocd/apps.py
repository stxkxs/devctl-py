"""ArgoCD application commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import ArgoCDError


@click.group()
def apps() -> None:
    """Application operations - list, sync, diff, rollback, status, history."""
    pass


@apps.command("list")
@click.option("-p", "--project", default=None, help="Filter by project")
@click.option("-l", "--selector", default=None, help="Label selector")
@pass_context
def list_apps(
    ctx: DevCtlContext,
    project: str | None,
    selector: str | None,
) -> None:
    """List applications.

    \b
    Examples:
        devctl argocd apps list
        devctl argocd apps list -p default
        devctl argocd apps list -l team=backend
    """
    try:
        apps_list = ctx.argocd.list_applications(project=project, selector=selector)

        if not apps_list:
            ctx.output.print_info("No applications found")
            return

        rows = []
        for app in apps_list:
            metadata = app.get("metadata", {})
            spec = app.get("spec", {})
            status = app.get("status", {})

            sync_status = status.get("sync", {}).get("status", "Unknown")
            health_status = status.get("health", {}).get("status", "Unknown")

            rows.append({
                "name": metadata.get("name", ""),
                "project": spec.get("project", ""),
                "sync": sync_status,
                "health": health_status,
                "namespace": spec.get("destination", {}).get("namespace", ""),
                "cluster": _get_cluster_name(spec.get("destination", {}).get("server", "")),
            })

        ctx.output.print_table(
            rows,
            columns=["name", "project", "sync", "health", "namespace", "cluster"],
            title="Applications",
        )

    except ArgoCDError as e:
        ctx.output.print_error(f"Failed to list applications: {e}")
        raise click.Abort()


@apps.command("status")
@click.argument("name")
@pass_context
def status(ctx: DevCtlContext, name: str) -> None:
    """Show application status.

    \b
    Examples:
        devctl argocd apps status my-app
    """
    try:
        app = ctx.argocd.get_application(name)

        metadata = app.get("metadata", {})
        spec = app.get("spec", {})
        status = app.get("status", {})

        sync = status.get("sync", {})
        health = status.get("health", {})
        source = spec.get("source", {})

        ctx.output.print_header(f"Application: {metadata.get('name')}")
        ctx.output.print(f"Project: {spec.get('project', '')}")
        ctx.output.print(f"Namespace: {spec.get('destination', {}).get('namespace', '')}")
        ctx.output.print(f"Cluster: {spec.get('destination', {}).get('server', '')}")

        ctx.output.print(f"\nSync Status: {sync.get('status', 'Unknown')}")
        ctx.output.print(f"Health: {health.get('status', 'Unknown')}")
        if health.get("message"):
            ctx.output.print(f"  Message: {health.get('message')}")

        ctx.output.print(f"\nSource:")
        ctx.output.print(f"  Repo: {source.get('repoURL', '')}")
        ctx.output.print(f"  Path: {source.get('path', '')}")
        ctx.output.print(f"  Target Revision: {source.get('targetRevision', 'HEAD')}")
        ctx.output.print(f"  Current Revision: {sync.get('revision', '')[:8]}")

        # Resources summary
        resources = status.get("resources", [])
        if resources:
            synced = sum(1 for r in resources if r.get("status") == "Synced")
            healthy = sum(1 for r in resources if r.get("health", {}).get("status") == "Healthy")
            ctx.output.print(f"\nResources: {len(resources)} total, {synced} synced, {healthy} healthy")

    except ArgoCDError as e:
        ctx.output.print_error(f"Failed to get application: {e}")
        raise click.Abort()


@apps.command("sync")
@click.argument("name")
@click.option("--revision", default=None, help="Revision to sync to")
@click.option("--prune", is_flag=True, help="Prune deleted resources")
@click.option("--dry-run", "sync_dry_run", is_flag=True, help="Dry run sync")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@pass_context
def sync(
    ctx: DevCtlContext,
    name: str,
    revision: str | None,
    prune: bool,
    sync_dry_run: bool,
    yes: bool,
) -> None:
    """Sync an application.

    \b
    Examples:
        devctl argocd apps sync my-app
        devctl argocd apps sync my-app --revision HEAD
        devctl argocd apps sync my-app --prune
    """
    try:
        if ctx.dry_run or sync_dry_run:
            ctx.log_dry_run("sync", {"app": name, "revision": revision, "prune": prune})
            if sync_dry_run:
                # Actually do a dry-run sync to see what would change
                result = ctx.argocd.sync_application(
                    name=name,
                    revision=revision,
                    prune=prune,
                    dry_run=True,
                )
                ctx.output.print_info("Dry run results:")
                ctx.output.print_json(result)
            return

        if not yes and not ctx.confirm(f"Sync application {name}?"):
            ctx.output.print_info("Cancelled")
            return

        result = ctx.argocd.sync_application(
            name=name,
            revision=revision,
            prune=prune,
            dry_run=False,
        )

        ctx.output.print_success(f"Sync initiated for {name}")

        # Show sync operation status
        operation = result.get("status", {}).get("operationState", {})
        phase = operation.get("phase", "")
        message = operation.get("message", "")

        ctx.output.print(f"Phase: {phase}")
        if message:
            ctx.output.print(f"Message: {message}")

    except ArgoCDError as e:
        ctx.output.print_error(f"Failed to sync application: {e}")
        raise click.Abort()


@apps.command("diff")
@click.argument("name")
@pass_context
def diff(ctx: DevCtlContext, name: str) -> None:
    """Show diff between live and desired state.

    \b
    Examples:
        devctl argocd apps diff my-app
    """
    try:
        diff_result = ctx.argocd.get_application_diff(name)

        ctx.output.print_header(f"Diff: {name}")
        ctx.output.print(f"Target Revision: {diff_result.get('targetRevision', 'HEAD')}")

        manifests = diff_result.get("manifests", [])
        resources = diff_result.get("resources", [])

        ctx.output.print(f"\nManifests: {len(manifests)}")
        ctx.output.print(f"Resources: {len(resources)}")

        # Show resources
        for resource in resources:
            health = resource.get("health", {})
            status = resource.get("status", "Unknown")
            kind = resource.get("kind", "")
            name = resource.get("name", "")

            health_status = health.get("status", "")
            icon = "+" if status == "Synced" else "~"

            ctx.output.print(f"  {icon} {kind}/{name} [{status}] {health_status}")

    except ArgoCDError as e:
        ctx.output.print_error(f"Failed to get diff: {e}")
        raise click.Abort()


@apps.command("history")
@click.argument("name")
@pass_context
def history(ctx: DevCtlContext, name: str) -> None:
    """Show deployment history.

    \b
    Examples:
        devctl argocd apps history my-app
    """
    try:
        history_list = ctx.argocd.get_application_history(name)

        if not history_list:
            ctx.output.print_info("No deployment history found")
            return

        rows = []
        for entry in history_list:
            rows.append({
                "id": entry.get("id", ""),
                "revision": entry.get("revision", "")[:8],
                "deployed_at": entry.get("deployedAt", ""),
                "source": entry.get("source", {}).get("path", ""),
            })

        ctx.output.print_table(
            rows,
            columns=["id", "revision", "deployed_at", "source"],
            title=f"History: {name}",
        )

    except ArgoCDError as e:
        ctx.output.print_error(f"Failed to get history: {e}")
        raise click.Abort()


@apps.command("rollback")
@click.argument("name")
@click.option("--revision-id", type=int, required=True, help="Revision ID from history")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@pass_context
def rollback(
    ctx: DevCtlContext,
    name: str,
    revision_id: int,
    yes: bool,
) -> None:
    """Rollback to a previous revision.

    \b
    Examples:
        devctl argocd apps rollback my-app --revision-id 5
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("rollback", {"app": name, "revision_id": revision_id})
            return

        if not yes and not ctx.confirm(f"Rollback {name} to revision {revision_id}?"):
            ctx.output.print_info("Cancelled")
            return

        result = ctx.argocd.rollback_application(name, revision_id)
        ctx.output.print_success(f"Rollback initiated for {name}")

    except ArgoCDError as e:
        ctx.output.print_error(f"Failed to rollback application: {e}")
        raise click.Abort()


@apps.command("refresh")
@click.argument("name")
@click.option("--hard", is_flag=True, help="Force hard refresh")
@pass_context
def refresh(ctx: DevCtlContext, name: str, hard: bool) -> None:
    """Refresh application from Git.

    \b
    Examples:
        devctl argocd apps refresh my-app
        devctl argocd apps refresh my-app --hard
    """
    try:
        result = ctx.argocd.refresh_application(name, hard=hard)
        ctx.output.print_success(f"Refreshed {name}" + (" (hard)" if hard else ""))

    except ArgoCDError as e:
        ctx.output.print_error(f"Failed to refresh application: {e}")
        raise click.Abort()


def _get_cluster_name(server: str) -> str:
    """Extract cluster name from server URL."""
    if server == "https://kubernetes.default.svc":
        return "in-cluster"
    return server.split("//")[-1].split(".")[0] if server else ""
