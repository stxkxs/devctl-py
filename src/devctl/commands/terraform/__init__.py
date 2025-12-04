"""Terraform command group."""

import json
import os
import re
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import DevCtlError


class TerraformError(DevCtlError):
    """Terraform-specific error."""
    pass


def _check_terraform() -> str:
    """Check if terraform is installed and return path."""
    tf_path = shutil.which("terraform")
    if not tf_path:
        raise TerraformError(
            "Terraform not found. Install from: https://www.terraform.io/downloads"
        )
    return tf_path


def _run_terraform(
    args: list[str],
    cwd: str | None = None,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a terraform command."""
    tf_path = _check_terraform()

    cmd = [tf_path] + args

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    # Disable color if capturing output
    if capture:
        run_env["TF_CLI_ARGS"] = "-no-color"

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            env=run_env,
        )
        return result
    except subprocess.SubprocessError as e:
        raise TerraformError(f"Failed to run terraform: {e}")


def _get_workspace(cwd: str | None = None) -> str:
    """Get current terraform workspace."""
    result = _run_terraform(["workspace", "show"], cwd=cwd)
    if result.returncode == 0:
        return result.stdout.strip()
    return "default"


@click.group()
@pass_context
def terraform(ctx: DevCtlContext) -> None:
    """Terraform operations - plan, apply, state, workspaces.

    \b
    Wraps terraform CLI with enhanced output and workflow integration.

    \b
    Examples:
        devctl terraform plan
        devctl terraform apply --auto-approve
        devctl terraform state list
        devctl terraform workspace list
    """
    pass


@terraform.command()
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--var", "-v", "variables", multiple=True, help="Variables (key=value)")
@click.option("--var-file", type=click.Path(exists=True), help="Variable file")
@click.option("--target", "-t", multiple=True, help="Target specific resources")
@click.option("--out", "plan_file", help="Save plan to file")
@click.option("--destroy", is_flag=True, help="Create a destroy plan")
@click.option("--refresh-only", is_flag=True, help="Only update state, don't plan changes")
@pass_context
def plan(
    ctx: DevCtlContext,
    working_dir: str | None,
    variables: tuple[str, ...],
    var_file: str | None,
    target: tuple[str, ...],
    plan_file: str | None,
    destroy: bool,
    refresh_only: bool,
) -> None:
    """Run terraform plan.

    \b
    Examples:
        devctl terraform plan
        devctl terraform plan --var environment=staging
        devctl terraform plan --target aws_instance.web
        devctl terraform plan --out tfplan
    """
    args = ["plan"]

    for var in variables:
        args.extend(["-var", var])

    if var_file:
        args.extend(["-var-file", var_file])

    for t in target:
        args.extend(["-target", t])

    if plan_file:
        args.extend(["-out", plan_file])

    if destroy:
        args.append("-destroy")

    if refresh_only:
        args.append("-refresh-only")

    workspace = _get_workspace(working_dir)
    ctx.output.print_info(f"Running terraform plan (workspace: {workspace})")

    if ctx.dry_run:
        ctx.output.print_info(f"Would run: terraform {' '.join(args)}")
        return

    result = _run_terraform(args, cwd=working_dir, capture=False)

    if result.returncode != 0:
        raise TerraformError("Terraform plan failed")


@terraform.command()
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--var", "-v", "variables", multiple=True, help="Variables (key=value)")
@click.option("--var-file", type=click.Path(exists=True), help="Variable file")
@click.option("--target", "-t", multiple=True, help="Target specific resources")
@click.option("--auto-approve", is_flag=True, help="Skip interactive approval")
@click.option("--plan-file", type=click.Path(exists=True), help="Apply saved plan file")
@click.option("--parallelism", type=int, default=10, help="Number of parallel operations")
@pass_context
def apply(
    ctx: DevCtlContext,
    working_dir: str | None,
    variables: tuple[str, ...],
    var_file: str | None,
    target: tuple[str, ...],
    auto_approve: bool,
    plan_file: str | None,
    parallelism: int,
) -> None:
    """Run terraform apply.

    \b
    Examples:
        devctl terraform apply --auto-approve
        devctl terraform apply --var environment=production
        devctl terraform apply --plan-file tfplan
    """
    args = ["apply"]

    if plan_file:
        args.append(plan_file)
    else:
        for var in variables:
            args.extend(["-var", var])

        if var_file:
            args.extend(["-var-file", var_file])

        for t in target:
            args.extend(["-target", t])

    if auto_approve:
        args.append("-auto-approve")

    args.extend(["-parallelism", str(parallelism)])

    workspace = _get_workspace(working_dir)
    ctx.output.print_info(f"Running terraform apply (workspace: {workspace})")

    if ctx.dry_run:
        ctx.output.print_info(f"Would run: terraform {' '.join(args)}")
        return

    result = _run_terraform(args, cwd=working_dir, capture=False)

    if result.returncode != 0:
        raise TerraformError("Terraform apply failed")

    ctx.output.print_success("Terraform apply completed")


@terraform.command()
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--var", "-v", "variables", multiple=True, help="Variables (key=value)")
@click.option("--var-file", type=click.Path(exists=True), help="Variable file")
@click.option("--target", "-t", multiple=True, help="Target specific resources")
@click.option("--auto-approve", is_flag=True, help="Skip interactive approval")
@pass_context
def destroy(
    ctx: DevCtlContext,
    working_dir: str | None,
    variables: tuple[str, ...],
    var_file: str | None,
    target: tuple[str, ...],
    auto_approve: bool,
) -> None:
    """Run terraform destroy.

    \b
    Examples:
        devctl terraform destroy --auto-approve
        devctl terraform destroy --target aws_instance.web
    """
    args = ["destroy"]

    for var in variables:
        args.extend(["-var", var])

    if var_file:
        args.extend(["-var-file", var_file])

    for t in target:
        args.extend(["-target", t])

    if auto_approve:
        args.append("-auto-approve")

    workspace = _get_workspace(working_dir)
    ctx.output.print_warning(f"Running terraform destroy (workspace: {workspace})")

    if ctx.dry_run:
        ctx.output.print_info(f"Would run: terraform {' '.join(args)}")
        return

    result = _run_terraform(args, cwd=working_dir, capture=False)

    if result.returncode != 0:
        raise TerraformError("Terraform destroy failed")

    ctx.output.print_success("Terraform destroy completed")


@terraform.command()
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@pass_context
def init(ctx: DevCtlContext, working_dir: str | None) -> None:
    """Run terraform init.

    \b
    Examples:
        devctl terraform init
        devctl terraform init --dir ./infra
    """
    args = ["init"]

    ctx.output.print_info("Initializing terraform...")

    if ctx.dry_run:
        ctx.output.print_info("Would run: terraform init")
        return

    result = _run_terraform(args, cwd=working_dir, capture=False)

    if result.returncode != 0:
        raise TerraformError("Terraform init failed")

    ctx.output.print_success("Terraform initialized")


@terraform.command()
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@pass_context
def validate(ctx: DevCtlContext, working_dir: str | None) -> None:
    """Validate terraform configuration.

    \b
    Examples:
        devctl terraform validate
    """
    args = ["validate", "-json"]

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        ctx.output.print_error("Validation failed")
        try:
            data = json.loads(result.stdout)
            for diag in data.get("diagnostics", []):
                severity = diag.get("severity", "error")
                summary = diag.get("summary", "Unknown error")
                detail = diag.get("detail", "")
                ctx.output.print(f"[{'red' if severity == 'error' else 'yellow'}]{severity}:[/] {summary}")
                if detail:
                    ctx.output.print(f"  {detail}")
        except json.JSONDecodeError:
            ctx.output.print(result.stdout)
        raise TerraformError("Validation failed")

    ctx.output.print_success("Configuration is valid")


@terraform.command()
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@pass_context
def fmt(ctx: DevCtlContext, working_dir: str | None) -> None:
    """Format terraform files.

    \b
    Examples:
        devctl terraform fmt
    """
    args = ["fmt", "-recursive"]

    if ctx.dry_run:
        args.append("-check")

    result = _run_terraform(args, cwd=working_dir)

    if ctx.dry_run:
        if result.returncode != 0:
            ctx.output.print_warning("Files need formatting")
            if result.stdout:
                ctx.output.print(result.stdout)
        else:
            ctx.output.print_success("All files formatted correctly")
    else:
        ctx.output.print_success("Terraform files formatted")
        if result.stdout:
            ctx.output.print(result.stdout)


# ============================================================================
# State Commands
# ============================================================================


@terraform.group()
@pass_context
def state(ctx: DevCtlContext) -> None:
    """State management operations.

    \b
    Examples:
        devctl terraform state list
        devctl terraform state show aws_instance.web
        devctl terraform state mv aws_instance.old aws_instance.new
    """
    pass


@state.command("list")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--filter", "filter_pattern", help="Filter resources by pattern")
@pass_context
def state_list(ctx: DevCtlContext, working_dir: str | None, filter_pattern: str | None) -> None:
    """List resources in state."""
    args = ["state", "list"]

    if filter_pattern:
        args.append(filter_pattern)

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Failed to list state: {result.stderr}")

    resources = [r for r in result.stdout.strip().split("\n") if r]

    if not resources:
        ctx.output.print_info("No resources in state")
        return

    data = []
    for resource in resources:
        # Parse resource type from address
        parts = resource.split(".")
        resource_type = parts[0] if parts else "unknown"

        data.append({
            "Address": resource,
            "Type": resource_type,
        })

    ctx.output.print_data(
        data,
        headers=["Address", "Type"],
        title=f"State Resources ({len(data)} found)",
    )


@state.command("show")
@click.argument("address")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@pass_context
def state_show(ctx: DevCtlContext, address: str, working_dir: str | None) -> None:
    """Show resource details from state."""
    args = ["state", "show", address]

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Resource not found: {address}")

    ctx.output.print(result.stdout)


@state.command("mv")
@click.argument("source")
@click.argument("destination")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@pass_context
def state_mv(ctx: DevCtlContext, source: str, destination: str, working_dir: str | None) -> None:
    """Move resource in state."""
    args = ["state", "mv", source, destination]

    ctx.output.print_info(f"Moving {source} -> {destination}")

    if ctx.dry_run:
        ctx.output.print_info("Would run: terraform state mv")
        return

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Move failed: {result.stderr}")

    ctx.output.print_success(f"Moved {source} to {destination}")


@state.command("rm")
@click.argument("address")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--force", is_flag=True, help="Skip confirmation")
@pass_context
def state_rm(ctx: DevCtlContext, address: str, working_dir: str | None, force: bool) -> None:
    """Remove resource from state (does not destroy)."""
    if not force:
        ctx.output.print_warning(f"About to remove {address} from state (resource will NOT be destroyed)")
        if not click.confirm("Continue?"):
            ctx.output.print_info("Cancelled")
            return

    args = ["state", "rm", address]

    if ctx.dry_run:
        ctx.output.print_info("Would run: terraform state rm")
        return

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Remove failed: {result.stderr}")

    ctx.output.print_success(f"Removed {address} from state")


@state.command("pull")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--out", "output_file", type=click.Path(), help="Output file")
@pass_context
def state_pull(ctx: DevCtlContext, working_dir: str | None, output_file: str | None) -> None:
    """Pull current state."""
    args = ["state", "pull"]

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Pull failed: {result.stderr}")

    if output_file:
        Path(output_file).write_text(result.stdout)
        ctx.output.print_success(f"State saved to {output_file}")
    else:
        ctx.output.print_code(result.stdout, "json")


# ============================================================================
# Workspace Commands
# ============================================================================


@terraform.group()
@pass_context
def workspace(ctx: DevCtlContext) -> None:
    """Workspace management.

    \b
    Examples:
        devctl terraform workspace list
        devctl terraform workspace select staging
        devctl terraform workspace new production
    """
    pass


@workspace.command("list")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@pass_context
def workspace_list(ctx: DevCtlContext, working_dir: str | None) -> None:
    """List workspaces."""
    args = ["workspace", "list"]

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Failed to list workspaces: {result.stderr}")

    workspaces = []
    current = None

    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line.startswith("*"):
            ws = line[1:].strip()
            current = ws
            workspaces.append(ws)
        elif line:
            workspaces.append(line)

    data = []
    for ws in workspaces:
        data.append({
            "Workspace": ws,
            "Current": "[green]Yes[/green]" if ws == current else "No",
        })

    ctx.output.print_data(
        data,
        headers=["Workspace", "Current"],
        title="Terraform Workspaces",
    )


@workspace.command("select")
@click.argument("name")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@pass_context
def workspace_select(ctx: DevCtlContext, name: str, working_dir: str | None) -> None:
    """Select a workspace."""
    args = ["workspace", "select", name]

    if ctx.dry_run:
        ctx.output.print_info(f"Would switch to workspace: {name}")
        return

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Failed to select workspace: {result.stderr}")

    ctx.output.print_success(f"Switched to workspace: {name}")


@workspace.command("new")
@click.argument("name")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@pass_context
def workspace_new(ctx: DevCtlContext, name: str, working_dir: str | None) -> None:
    """Create a new workspace."""
    args = ["workspace", "new", name]

    if ctx.dry_run:
        ctx.output.print_info(f"Would create workspace: {name}")
        return

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Failed to create workspace: {result.stderr}")

    ctx.output.print_success(f"Created and switched to workspace: {name}")


@workspace.command("delete")
@click.argument("name")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--force", is_flag=True, help="Force delete even if state exists")
@pass_context
def workspace_delete(ctx: DevCtlContext, name: str, working_dir: str | None, force: bool) -> None:
    """Delete a workspace."""
    current = _get_workspace(working_dir)
    if name == current:
        raise TerraformError(f"Cannot delete current workspace. Switch to another first.")

    args = ["workspace", "delete"]
    if force:
        args.append("-force")
    args.append(name)

    if ctx.dry_run:
        ctx.output.print_info(f"Would delete workspace: {name}")
        return

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Failed to delete workspace: {result.stderr}")

    ctx.output.print_success(f"Deleted workspace: {name}")


# ============================================================================
# Output Commands
# ============================================================================


@terraform.command()
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.argument("name", required=False)
@pass_context
def output(ctx: DevCtlContext, working_dir: str | None, as_json: bool, name: str | None) -> None:
    """Show terraform outputs.

    \b
    Examples:
        devctl terraform output
        devctl terraform output vpc_id
        devctl terraform output --json
    """
    args = ["output"]

    if as_json:
        args.append("-json")

    if name:
        args.append(name)

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        if "No outputs found" in result.stderr:
            ctx.output.print_info("No outputs defined")
            return
        raise TerraformError(f"Failed to get outputs: {result.stderr}")

    if as_json:
        ctx.output.print_code(result.stdout, "json")
    else:
        ctx.output.print(result.stdout)


# ============================================================================
# Import Command
# ============================================================================


@terraform.command("import")
@click.argument("address")
@click.argument("id")
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--var", "-v", "variables", multiple=True, help="Variables (key=value)")
@pass_context
def import_resource(
    ctx: DevCtlContext,
    address: str,
    id: str,
    working_dir: str | None,
    variables: tuple[str, ...],
) -> None:
    """Import existing infrastructure into terraform.

    ADDRESS is the terraform resource address (e.g., aws_instance.web)
    ID is the infrastructure ID (e.g., i-1234567890abcdef0)

    \b
    Examples:
        devctl terraform import aws_instance.web i-1234567890abcdef0
        devctl terraform import aws_s3_bucket.data my-bucket-name
    """
    args = ["import"]

    for var in variables:
        args.extend(["-var", var])

    args.extend([address, id])

    ctx.output.print_info(f"Importing {id} as {address}")

    if ctx.dry_run:
        ctx.output.print_info("Would run: terraform import")
        return

    result = _run_terraform(args, cwd=working_dir, capture=False)

    if result.returncode != 0:
        raise TerraformError("Import failed")

    ctx.output.print_success(f"Successfully imported {address}")


# ============================================================================
# Providers Command
# ============================================================================


@terraform.command()
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@pass_context
def providers(ctx: DevCtlContext, working_dir: str | None) -> None:
    """Show required providers and versions.

    \b
    Examples:
        devctl terraform providers
    """
    args = ["providers"]

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Failed to get providers: {result.stderr}")

    ctx.output.print(result.stdout)


# ============================================================================
# Graph Command
# ============================================================================


@terraform.command()
@click.option("--dir", "-d", "working_dir", type=click.Path(exists=True), help="Terraform directory")
@click.option("--type", "graph_type", type=click.Choice(["plan", "apply"]), default="plan", help="Graph type")
@click.option("--out", "output_file", type=click.Path(), help="Save to file (dot format)")
@pass_context
def graph(ctx: DevCtlContext, working_dir: str | None, graph_type: str, output_file: str | None) -> None:
    """Generate resource dependency graph.

    \b
    Examples:
        devctl terraform graph
        devctl terraform graph --out graph.dot
    """
    args = ["graph", f"-type={graph_type}"]

    result = _run_terraform(args, cwd=working_dir)

    if result.returncode != 0:
        raise TerraformError(f"Failed to generate graph: {result.stderr}")

    if output_file:
        Path(output_file).write_text(result.stdout)
        ctx.output.print_success(f"Graph saved to {output_file}")
        ctx.output.print_info("Render with: dot -Tpng graph.dot -o graph.png")
    else:
        ctx.output.print_code(result.stdout, "dot")
