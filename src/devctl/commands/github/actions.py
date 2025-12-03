"""GitHub Actions commands."""

import time
from typing import Any

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import GitHubError
from devctl.commands.github.repos import parse_repo


@click.group()
@pass_context
def actions(ctx: DevCtlContext) -> None:
    """GitHub Actions operations - workflows, runs, logs.

    \b
    Examples:
        devctl github actions list owner/repo
        devctl github actions run owner/repo deploy.yml
        devctl github actions logs owner/repo 12345
    """
    pass


@actions.command("list")
@click.argument("repo")
@pass_context
def list_workflows(ctx: DevCtlContext, repo: str) -> None:
    """List repository workflows."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github
        workflows = client.list_workflows(owner, repo_name)

        if not workflows:
            ctx.output.print_info("No workflows found")
            return

        data = []
        for wf in workflows:
            state = wf.get("state", "-")
            state_color = "[green]active[/green]" if state == "active" else f"[dim]{state}[/dim]"

            data.append({
                "ID": wf.get("id", "-"),
                "Name": wf.get("name", "-")[:30],
                "State": state_color,
                "Path": wf.get("path", "-")[:30],
            })

        ctx.output.print_data(
            data,
            headers=["ID", "Name", "State", "Path"],
            title=f"Workflows in {owner}/{repo_name}",
        )

    except Exception as e:
        raise GitHubError(f"Failed to list workflows: {e}")


@actions.command("runs")
@click.argument("repo")
@click.option("--workflow", "-w", help="Filter by workflow ID or filename")
@click.option("--status", type=click.Choice(["queued", "in_progress", "completed"]), help="Filter by status")
@click.option("--limit", type=int, default=20, help="Maximum runs to show")
@pass_context
def list_runs(
    ctx: DevCtlContext,
    repo: str,
    workflow: str | None,
    status: str | None,
    limit: int,
) -> None:
    """List workflow runs."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github
        runs = client.list_workflow_runs(
            owner,
            repo_name,
            workflow_id=workflow,
            status=status,
        )[:limit]

        if not runs:
            ctx.output.print_info("No workflow runs found")
            return

        data = []
        for run in runs:
            status_val = run.get("status", "-")
            conclusion = run.get("conclusion", "-")

            if conclusion == "success":
                status_display = "[green]success[/green]"
            elif conclusion == "failure":
                status_display = "[red]failure[/red]"
            elif status_val == "in_progress":
                status_display = "[yellow]running[/yellow]"
            else:
                status_display = status_val

            data.append({
                "ID": run.get("id", "-"),
                "Workflow": run.get("name", "-")[:25],
                "Status": status_display,
                "Branch": run.get("head_branch", "-")[:15],
                "Event": run.get("event", "-"),
                "Created": run.get("created_at", "-")[:16],
            })

        ctx.output.print_data(
            data,
            headers=["ID", "Workflow", "Status", "Branch", "Event", "Created"],
            title=f"Workflow Runs ({len(data)} shown)",
        )

    except Exception as e:
        raise GitHubError(f"Failed to list runs: {e}")


@actions.command("run")
@click.argument("repo")
@click.argument("workflow")
@click.option("--ref", default="main", help="Git ref (branch/tag)")
@click.option("--input", "inputs", multiple=True, help="Input parameters (KEY=VALUE)")
@pass_context
def trigger_workflow(
    ctx: DevCtlContext,
    repo: str,
    workflow: str,
    ref: str,
    inputs: tuple[str, ...],
) -> None:
    """Trigger a workflow dispatch.

    WORKFLOW is the workflow filename (e.g., deploy.yml) or ID.
    """
    owner, repo_name = parse_repo(repo, ctx)

    # Parse inputs
    input_dict: dict[str, Any] = {}
    for inp in inputs:
        if "=" in inp:
            key, value = inp.split("=", 1)
            input_dict[key] = value

    if ctx.dry_run:
        ctx.log_dry_run("trigger workflow", {
            "repo": f"{owner}/{repo_name}",
            "workflow": workflow,
            "ref": ref,
            "inputs": input_dict,
        })
        return

    try:
        client = ctx.github
        client.trigger_workflow(owner, repo_name, workflow, ref, input_dict or None)

        ctx.output.print_success(f"Workflow {workflow} triggered on {ref}")

    except Exception as e:
        raise GitHubError(f"Failed to trigger workflow: {e}")


@actions.command("logs")
@click.argument("repo")
@click.argument("run_id", type=int)
@pass_context
def get_logs(ctx: DevCtlContext, repo: str, run_id: int) -> None:
    """Download workflow run logs."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github

        ctx.output.print_info(f"Downloading logs for run {run_id}...")

        logs = client.get_workflow_run_logs(owner, repo_name, run_id)

        # Logs are returned as a zip file
        import zipfile
        import io

        with zipfile.ZipFile(io.BytesIO(logs)) as zf:
            for name in zf.namelist():
                ctx.output.print_panel(name, title="Log File")
                content = zf.read(name).decode("utf-8", errors="replace")
                # Show last 100 lines
                lines = content.strip().split("\n")
                for line in lines[-100:]:
                    ctx.output.print(line)

    except Exception as e:
        raise GitHubError(f"Failed to get logs: {e}")


@actions.command("cancel")
@click.argument("repo")
@click.argument("run_id", type=int)
@pass_context
def cancel_run(ctx: DevCtlContext, repo: str, run_id: int) -> None:
    """Cancel a workflow run."""
    owner, repo_name = parse_repo(repo, ctx)

    if ctx.dry_run:
        ctx.log_dry_run("cancel workflow run", {"repo": f"{owner}/{repo_name}", "run_id": run_id})
        return

    try:
        client = ctx.github
        client.cancel_workflow_run(owner, repo_name, run_id)

        ctx.output.print_success(f"Cancelled workflow run {run_id}")

    except Exception as e:
        raise GitHubError(f"Failed to cancel run: {e}")


@actions.command("status")
@click.argument("repo")
@click.option("--wait", "-w", is_flag=True, help="Wait for running workflows to complete")
@click.option("--timeout", type=int, default=600, help="Wait timeout in seconds")
@pass_context
def workflow_status(ctx: DevCtlContext, repo: str, wait: bool, timeout: int) -> None:
    """Show workflow status for a repository."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github

        if wait:
            ctx.output.print_info("Waiting for workflows to complete...")
            start_time = time.time()

            while True:
                runs = client.list_workflow_runs(owner, repo_name, status="in_progress")

                if not runs:
                    ctx.output.print_success("All workflows completed")
                    break

                if time.time() - start_time > timeout:
                    ctx.output.print_warning(f"Timeout after {timeout}s - {len(runs)} workflows still running")
                    break

                ctx.output.print(f"[dim]Waiting... {len(runs)} workflows running[/dim]")
                time.sleep(10)

        # Show current status
        runs = client.list_workflow_runs(owner, repo_name)[:10]

        if not runs:
            ctx.output.print_info("No recent workflow runs")
            return

        # Group by status
        by_status: dict[str, list] = {}
        for run in runs:
            status = run.get("conclusion") or run.get("status", "unknown")
            by_status.setdefault(status, []).append(run)

        ctx.output.print_info(f"Recent workflow status for {owner}/{repo_name}:")
        for status, status_runs in by_status.items():
            count = len(status_runs)
            icon = {"success": "[green]✓[/green]", "failure": "[red]✗[/red]", "in_progress": "[yellow]⟳[/yellow]"}.get(status, "[dim]?[/dim]")
            ctx.output.print(f"  {icon} {status}: {count}")

    except Exception as e:
        raise GitHubError(f"Failed to get status: {e}")
