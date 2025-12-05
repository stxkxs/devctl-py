"""Workflow execution engine."""

import re
import shlex
import subprocess
from typing import Any

import yaml
from jinja2 import Environment, BaseLoader, UndefinedError

from devctl.config import WorkflowConfig, WorkflowStep
from devctl.core.async_utils import run_sync
from devctl.core.context import DevCtlContext
from devctl.core.exceptions import WorkflowError
from devctl.core.logging import get_logger
from devctl.workflows.graph import DependencyGraph
from devctl.workflows.schema import (
    validate_workflow,
    WorkflowSchema,
    WorkflowStepSchema,
    ParallelConfigSchema,
)

logger = get_logger(__name__)


class WorkflowEngine:
    """Engine for executing YAML-defined workflows."""

    def __init__(self, ctx: DevCtlContext):
        self.ctx = ctx
        self.jinja_env = Environment(loader=BaseLoader())
        self._variables: dict[str, Any] = {}
        self._results: dict[str, Any] = {}

    def load_workflow(self, workflow_path: str) -> WorkflowSchema:
        """Load and validate a workflow from a YAML file.

        Args:
            workflow_path: Path to workflow YAML file

        Returns:
            Validated workflow schema
        """
        try:
            with open(workflow_path) as f:
                workflow_dict = yaml.safe_load(f)

            return validate_workflow(workflow_dict)

        except yaml.YAMLError as e:
            raise WorkflowError(f"Invalid YAML: {e}")
        except Exception as e:
            raise WorkflowError(f"Failed to load workflow: {e}")

    def run(
        self,
        workflow: WorkflowSchema,
        variables: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute a workflow.

        Args:
            workflow: Validated workflow schema
            variables: Variables to pass to the workflow
            dry_run: If True, show what would be done without executing

        Returns:
            Dictionary with execution results
        """
        # Initialize variables
        self._variables = {**workflow.vars, **(variables or {})}
        self._results = {}

        results = {
            "success": True,
            "steps": [],
            "failed_step": None,
        }

        self.ctx.output.print_info(f"Running workflow: {workflow.name or 'unnamed'}")
        if workflow.description:
            self.ctx.output.print(f"[dim]{workflow.description}[/dim]")

        # check if this is a parallel workflow (uses depends_on)
        if self._is_dag_workflow(workflow):
            return self._run_dag(workflow, dry_run)

        for i, step in enumerate(workflow.steps):
            # check if this is a parallel block
            if step.parallel is not None:
                step_result = self._execute_parallel_block(
                    step, i + 1, len(workflow.steps), dry_run
                )
            else:
                step_result = self._execute_step(step, i + 1, len(workflow.steps), dry_run)

            results["steps"].append(step_result)

            if not step_result["success"]:
                if step.on_failure == "fail":
                    results["success"] = False
                    results["failed_step"] = step.name
                    self.ctx.output.print_error(f"Workflow failed at step: {step.name}")
                    break
                elif step.on_failure == "continue":
                    self.ctx.output.print_warning(f"Step '{step.name}' failed, continuing...")
                # skip - just continue

        if results["success"]:
            self.ctx.output.print_success("Workflow completed successfully")
        else:
            self.ctx.output.print_error(f"Workflow failed at step: {results['failed_step']}")

        return results

    def _is_dag_workflow(self, workflow: WorkflowSchema) -> bool:
        """Check if workflow uses dependency-based execution."""
        return any(step.depends_on for step in workflow.steps)

    def _run_dag(
        self,
        workflow: WorkflowSchema,
        dry_run: bool,
    ) -> dict[str, Any]:
        """Execute workflow using dependency graph."""
        from devctl.workflows.parallel import ParallelExecutor

        self.ctx.output.print("[dim]Using dependency-based parallel execution[/dim]")

        executor = ParallelExecutor(self, workflow.parallel)
        step_results = run_sync(executor.execute_dag(workflow.steps, dry_run))

        # convert to standard results format
        results = {
            "success": all(r.success or r.skipped for r in step_results.values()),
            "steps": [r.to_dict() for r in step_results.values()],
            "failed_step": None,
        }

        failed = [name for name, r in step_results.items() if not r.success and not r.skipped]
        if failed:
            results["failed_step"] = failed[0]
            self.ctx.output.print_error(f"Workflow failed at step(s): {', '.join(failed)}")
        else:
            self.ctx.output.print_success("Workflow completed successfully")

        return results

    def _execute_parallel_block(
        self,
        step: WorkflowStepSchema,
        step_num: int,
        total_steps: int,
        dry_run: bool,
    ) -> dict[str, Any]:
        """Execute a parallel block step."""
        from devctl.workflows.parallel import ParallelExecutor

        executor = ParallelExecutor(self, ParallelConfigSchema())
        result = run_sync(
            executor.execute_parallel_block(
                step.parallel, step_num, total_steps, dry_run
            )
        )

        return result.to_dict()

    def _execute_step(
        self,
        step: WorkflowStepSchema,
        step_num: int,
        total_steps: int,
        dry_run: bool,
    ) -> dict[str, Any]:
        """Execute a single workflow step.

        Args:
            step: Step to execute
            step_num: Step number
            total_steps: Total number of steps
            dry_run: If True, show what would be done

        Returns:
            Step execution result
        """
        self.ctx.output.print(f"\n[bold]Step {step_num}/{total_steps}: {step.name}[/bold]")

        # Check condition
        if step.condition:
            try:
                condition_result = self._evaluate_condition(step.condition)
                if not condition_result:
                    self.ctx.output.print("[dim]Skipped (condition not met)[/dim]")
                    return {"name": step.name, "success": True, "skipped": True}
            except Exception as e:
                self.ctx.output.print_warning(f"Condition evaluation failed: {e}")

        # Render command and params
        try:
            command = self._render_template(step.command)
            params = self._render_params(step.params)
        except UndefinedError as e:
            return {"name": step.name, "success": False, "error": f"Template error: {e}"}

        if dry_run:
            self.ctx.output.print(f"[dim]Would execute: {command}[/dim]")
            self.ctx.output.print(f"[dim]Params: {params}[/dim]")
            return {"name": step.name, "success": True, "dry_run": True}

        # Execute command
        try:
            result = self._execute_command(command, params, step.timeout)
            self._results[step.name] = result

            if result.get("success"):
                self.ctx.output.print_success(f"Step completed: {step.name}")
            else:
                self.ctx.output.print_error(f"Step failed: {result.get('error', 'Unknown error')}")

            return {"name": step.name, **result}

        except Exception as e:
            logger.exception(f"Step execution failed: {step.name}")
            return {"name": step.name, "success": False, "error": str(e)}

    def _execute_command(
        self,
        command: str,
        params: dict[str, Any],
        timeout: int | None,
    ) -> dict[str, Any]:
        """Execute a workflow command.

        Commands can be:
        - devctl commands: "aws s3 ls", "grafana dashboards list"
        - shell commands (prefixed with !): "!docker build ."

        Args:
            command: Command string
            params: Parameters for the command
            timeout: Execution timeout

        Returns:
            Execution result
        """
        if command.startswith("!"):
            # Shell command
            return self._execute_shell(command[1:], params, timeout)
        else:
            # devctl command
            return self._execute_devctl(command, params, timeout)

    def _execute_shell(
        self,
        command: str,
        params: dict[str, Any],
        timeout: int | None,
    ) -> dict[str, Any]:
        """Execute a shell command."""
        # Build command with params
        cmd_parts = shlex.split(command)

        for key, value in params.items():
            if isinstance(value, bool):
                if value:
                    cmd_parts.append(f"--{key}")
            else:
                cmd_parts.extend([f"--{key}", str(value)])

        self.ctx.output.print(f"[dim]$ {' '.join(cmd_parts)}[/dim]")

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=timeout or 300,
            )

            if result.stdout:
                self.ctx.output.print(result.stdout)
            if result.stderr:
                self.ctx.output.print(f"[dim]{result.stderr}[/dim]")

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _execute_devctl(
        self,
        command: str,
        params: dict[str, Any],
        timeout: int | None,
    ) -> dict[str, Any]:
        """Execute a devctl command.

        This invokes devctl as a subprocess for isolation.
        """
        cmd_parts = ["devctl"] + command.split()

        for key, value in params.items():
            if isinstance(value, bool):
                if value:
                    cmd_parts.append(f"--{key}")
            elif isinstance(value, list):
                for v in value:
                    cmd_parts.extend([f"--{key}", str(v)])
            else:
                cmd_parts.extend([f"--{key}", str(value)])

        self.ctx.output.print(f"[dim]> {' '.join(cmd_parts)}[/dim]")

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=timeout or 300,
            )

            if result.stdout:
                self.ctx.output.print(result.stdout)
            if result.stderr:
                self.ctx.output.print(f"[dim]{result.stderr}[/dim]")

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out"}
        except FileNotFoundError:
            return {"success": False, "error": "devctl not found in PATH"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _render_template(self, template: str) -> str:
        """Render a Jinja2 template string."""
        tmpl = self.jinja_env.from_string(template)
        return tmpl.render(**self._variables, results=self._results)

    def _render_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Render parameters with Jinja2."""
        rendered = {}
        for key, value in params.items():
            if isinstance(value, str):
                rendered[key] = self._render_template(value)
            elif isinstance(value, list):
                rendered[key] = [
                    self._render_template(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                rendered[key] = value
        return rendered

    def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate a condition expression."""
        # Simple condition evaluation
        rendered = self._render_template(condition)
        return bool(eval(rendered, {"__builtins__": {}}, self._variables))


def run_workflow(
    ctx: DevCtlContext,
    workflow_path: str,
    variables: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Convenience function to run a workflow from a file.

    Args:
        ctx: DevCtl context
        workflow_path: Path to workflow YAML file
        variables: Variables to pass to workflow
        dry_run: If True, show what would be done

    Returns:
        Workflow execution results
    """
    engine = WorkflowEngine(ctx)
    workflow = engine.load_workflow(workflow_path)
    return engine.run(workflow, variables, dry_run)
