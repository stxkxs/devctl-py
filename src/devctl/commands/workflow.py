"""Workflow commands."""

from pathlib import Path
from typing import Any

import click
import yaml

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import WorkflowError
from devctl.core.utils import parse_key_value_pairs
from devctl.workflows import WorkflowEngine, validate_workflow


@click.group()
@pass_context
def workflow(ctx: DevCtlContext) -> None:
    """Workflow operations - run, list, validate YAML workflows.

    \b
    Examples:
        devctl workflow run deploy --var env=production
        devctl workflow list
        devctl workflow validate ./workflow.yaml
    """
    pass


@workflow.command()
@click.argument("name_or_file")
@click.option("--var", "-v", multiple=True, help="Variables (KEY=VALUE)")
@pass_context
def run(ctx: DevCtlContext, name_or_file: str, var: tuple[str, ...]) -> None:
    """Run a workflow.

    NAME_OR_FILE can be a workflow name from config or a path to a YAML file.
    """
    # Parse variables
    variables = parse_key_value_pairs(list(var))

    # Check if it's a file path
    if Path(name_or_file).exists():
        workflow_path = name_or_file
    else:
        # Look for workflow in config
        workflows = ctx.config.workflows
        if name_or_file not in workflows:
            raise WorkflowError(f"Workflow not found: {name_or_file}")

        # Create temporary file from config workflow
        workflow_config = workflows[name_or_file]
        workflow_dict = {
            "name": name_or_file,
            "description": workflow_config.description,
            "steps": [
                {
                    "name": step.name,
                    "command": step.command,
                    "params": step.params,
                    "on_failure": step.on_failure,
                    "condition": step.condition,
                    "timeout": step.timeout,
                }
                for step in workflow_config.steps
            ],
            "vars": workflow_config.vars,
        }

        # Save to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(workflow_dict, f)
            workflow_path = f.name

    try:
        engine = WorkflowEngine(ctx)
        workflow_schema = engine.load_workflow(workflow_path)
        result = engine.run(workflow_schema, variables, dry_run=ctx.dry_run)

        if not result["success"]:
            raise SystemExit(1)

    except Exception as e:
        raise WorkflowError(f"Workflow execution failed: {e}")


@workflow.command("dry-run")
@click.argument("name_or_file")
@click.option("--var", "-v", multiple=True, help="Variables (KEY=VALUE)")
@pass_context
def dry_run(ctx: DevCtlContext, name_or_file: str, var: tuple[str, ...]) -> None:
    """Dry-run a workflow without executing commands."""
    variables = parse_key_value_pairs(list(var))

    if Path(name_or_file).exists():
        workflow_path = name_or_file
    else:
        workflows = ctx.config.workflows
        if name_or_file not in workflows:
            raise WorkflowError(f"Workflow not found: {name_or_file}")

        workflow_config = workflows[name_or_file]
        workflow_dict = {
            "name": name_or_file,
            "description": workflow_config.description,
            "steps": [
                {
                    "name": step.name,
                    "command": step.command,
                    "params": step.params,
                }
                for step in workflow_config.steps
            ],
            "vars": workflow_config.vars,
        }

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(workflow_dict, f)
            workflow_path = f.name

    engine = WorkflowEngine(ctx)
    workflow_schema = engine.load_workflow(workflow_path)
    engine.run(workflow_schema, variables, dry_run=True)


@workflow.command("list")
@pass_context
def list_workflows(ctx: DevCtlContext) -> None:
    """List configured workflows."""
    workflows = ctx.config.workflows

    if not workflows:
        ctx.output.print_info("No workflows configured")
        ctx.output.print_info("Add workflows to your devctl.yaml config file")
        return

    data = []
    for name, wf in workflows.items():
        data.append({
            "Name": name,
            "Description": wf.description[:40] or "-",
            "Steps": len(wf.steps),
            "Vars": len(wf.vars),
        })

    ctx.output.print_data(
        data,
        headers=["Name", "Description", "Steps", "Vars"],
        title=f"Configured Workflows ({len(data)} found)",
    )


@workflow.command()
@click.argument("file", type=click.Path(exists=True))
@pass_context
def validate(ctx: DevCtlContext, file: str) -> None:
    """Validate a workflow YAML file."""
    try:
        with open(file) as f:
            workflow_dict = yaml.safe_load(f)

        schema = validate_workflow(workflow_dict)

        ctx.output.print_success(f"Workflow is valid: {file}")

        # Show summary
        data = {
            "Name": schema.name or "(unnamed)",
            "Description": schema.description[:50] or "-",
            "Steps": len(schema.steps),
            "Variables": len(schema.vars),
        }
        ctx.output.print_data(data, title="Workflow Summary")

        # Show steps
        if schema.steps:
            step_data = []
            for i, step in enumerate(schema.steps):
                step_data.append({
                    "Step": i + 1,
                    "Name": step.name,
                    "Command": step.command[:30],
                    "OnFailure": step.on_failure,
                })
            ctx.output.print_data(step_data, headers=["Step", "Name", "Command", "OnFailure"], title="Steps")

    except yaml.YAMLError as e:
        ctx.output.print_error(f"Invalid YAML: {e}")
        raise SystemExit(1)
    except Exception as e:
        ctx.output.print_error(f"Validation failed: {e}")
        raise SystemExit(1)


@workflow.command()
@click.argument("name")
@pass_context
def show(ctx: DevCtlContext, name: str) -> None:
    """Show details of a configured workflow."""
    workflows = ctx.config.workflows

    if name not in workflows:
        raise WorkflowError(f"Workflow not found: {name}")

    wf = workflows[name]

    data = {
        "Name": name,
        "Description": wf.description or "-",
        "Variables": ", ".join(wf.vars.keys()) or "None",
    }
    ctx.output.print_data(data, title=f"Workflow: {name}")

    if wf.steps:
        ctx.output.print_info("\nSteps:")
        for i, step in enumerate(wf.steps):
            ctx.output.print(f"\n  [bold]{i + 1}. {step.name}[/bold]")
            ctx.output.print(f"     Command: {step.command}")
            if step.params:
                ctx.output.print(f"     Params: {step.params}")
            if step.condition:
                ctx.output.print(f"     Condition: {step.condition}")
            ctx.output.print(f"     On Failure: {step.on_failure}")
