"""Runbook command group."""

import click
from pathlib import Path

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import RunbookError
from devctl.runbooks import RunbookEngine


@click.group()
@pass_context
def runbook(ctx: DevCtlContext) -> None:
    """Runbook automation - run, list, validate.

    \b
    Examples:
        devctl runbook run deploy.md --var env=production
        devctl runbook list
        devctl runbook validate my-runbook.yaml
    """
    pass


@runbook.command("run")
@click.argument("file", type=click.Path(exists=True))
@click.option("--var", "-v", multiple=True, help="Variable (key=value)")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmations")
@click.option("--start", default=None, help="Start from step ID")
@pass_context
def run(
    ctx: DevCtlContext,
    file: str,
    var: tuple[str, ...],
    yes: bool,
    start: str | None,
) -> None:
    """Run a runbook.

    \b
    Examples:
        devctl runbook run deploy.md
        devctl runbook run deploy.yaml --var env=prod --var version=1.2.3
        devctl runbook run rollback.md -y
    """
    try:
        # Parse variables
        variables = {}
        for v in var:
            if "=" in v:
                key, value = v.split("=", 1)
                variables[key] = value

        # Create engine with handlers
        def prompt_handler(message: str, prompt_type: str, choices: list | None) -> bool | str:
            if yes:
                return True if prompt_type == "confirm" else ""
            if prompt_type == "confirm":
                return ctx.confirm(message)
            elif prompt_type == "choice" and choices:
                for i, choice in enumerate(choices):
                    ctx.output.print(f"  {i+1}. {choice}")
                idx = click.prompt("Choice", type=int, default=1)
                return choices[idx - 1] if 0 < idx <= len(choices) else choices[0]
            else:
                return click.prompt(message, default="")

        def output_handler(step_id: str, output: str) -> None:
            if output and not ctx.quiet:
                ctx.output.print(f"[{step_id}] {output}")

        engine = RunbookEngine(
            prompt_handler=prompt_handler,
            output_handler=output_handler,
        )

        # Load and run
        rb = engine.load(file)
        ctx.output.print_header(f"Running: {rb.name}")
        ctx.output.print(f"Description: {rb.description}")
        ctx.output.print(f"Steps: {len(rb.steps)}")

        result = engine.run(
            rb,
            variables=variables,
            dry_run=ctx.dry_run,
            start_step=start,
        )

        # Show result
        ctx.output.print("")
        if result.status.value == "success":
            ctx.output.print_success(f"Runbook completed successfully in {result.duration_seconds:.1f}s")
        else:
            ctx.output.print_error(f"Runbook failed: {result.error}")

        # Summary
        ctx.output.print(f"\nSteps: {result.successful_steps} succeeded, {result.failed_steps} failed, {result.skipped_steps} skipped")

    except RunbookError as e:
        ctx.output.print_error(f"Runbook failed: {e}")
        raise click.Abort()


@runbook.command("list")
@click.option("-d", "--dir", "directory", default=".", help="Runbooks directory")
@click.option("--templates", is_flag=True, help="Show templates only")
@pass_context
def list_runbooks(ctx: DevCtlContext, directory: str, templates: bool) -> None:
    """List available runbooks.

    \b
    Examples:
        devctl runbook list
        devctl runbook list -d ./runbooks
    """
    try:
        engine = RunbookEngine()
        runbooks = engine.list_runbooks(directory)

        if templates:
            runbooks = [r for r in runbooks if "template" in r.get("tags", [])]

        if not runbooks:
            ctx.output.print_info("No runbooks found")
            return

        rows = []
        for rb in runbooks:
            rows.append({
                "name": rb.get("name", ""),
                "version": rb.get("version", ""),
                "steps": rb.get("steps", 0),
                "file": Path(rb.get("file", "")).name,
            })

        ctx.output.print_table(rows, columns=["name", "version", "steps", "file"], title="Runbooks")

    except Exception as e:
        ctx.output.print_error(f"Failed to list runbooks: {e}")
        raise click.Abort()


@runbook.command("validate")
@click.argument("file", type=click.Path(exists=True))
@pass_context
def validate(ctx: DevCtlContext, file: str) -> None:
    """Validate a runbook.

    \b
    Examples:
        devctl runbook validate my-runbook.yaml
    """
    try:
        engine = RunbookEngine()
        rb = engine.load(file)
        issues = engine.validate(rb)

        ctx.output.print_header(f"Validating: {rb.name}")
        ctx.output.print(f"Version: {rb.version}")
        ctx.output.print(f"Steps: {len(rb.steps)}")

        if issues:
            ctx.output.print_error(f"\nFound {len(issues)} issue(s):")
            for issue in issues:
                ctx.output.print(f"  - {issue}")
            raise click.Abort()
        else:
            ctx.output.print_success("\nRunbook is valid")

    except RunbookError as e:
        ctx.output.print_error(f"Validation failed: {e}")
        raise click.Abort()


@runbook.command("history")
@click.option("--limit", default=20, help="Max entries")
@click.option("--runbook", "runbook_name", default=None, help="Filter by runbook")
@pass_context
def history(ctx: DevCtlContext, limit: int, runbook_name: str | None) -> None:
    """Show runbook execution history.

    \b
    Examples:
        devctl runbook history
        devctl runbook history --runbook deploy
    """
    try:
        from devctl.runbooks.audit import RunbookAuditLogger

        audit = RunbookAuditLogger(log_dir=Path.home() / ".devctl" / "runbook_logs")
        entries = audit.get_history(runbook_name=runbook_name, limit=limit)

        if not entries:
            ctx.output.print_info("No history found")
            return

        rows = []
        for entry in entries:
            rows.append({
                "id": entry.get("audit_id", "")[:12],
                "runbook": entry.get("runbook_name", ""),
                "status": entry.get("status", ""),
                "duration": f"{entry.get('duration_seconds', 0):.1f}s",
                "user": entry.get("user", ""),
                "time": entry.get("timestamp", "")[:19],
            })

        ctx.output.print_table(rows, columns=["id", "runbook", "status", "duration", "user", "time"], title="History")

    except Exception as e:
        ctx.output.print_error(f"Failed to get history: {e}")
        raise click.Abort()
