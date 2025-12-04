"""Runbook execution engine."""

import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from devctl.core.exceptions import RunbookError
from devctl.core.logging import get_logger
from devctl.runbooks.schema import (
    Runbook,
    RunbookResult,
    RunbookStep,
    StepResult,
    StepStatus,
    StepType,
)
from devctl.runbooks.markdown_parser import MarkdownRunbookParser

logger = get_logger(__name__)


class RunbookEngine:
    """Execute runbooks with variable substitution and step control."""

    def __init__(
        self,
        prompt_handler: Callable[[str, str, list[str] | None], str | bool] | None = None,
        notify_handler: Callable[[str, str], None] | None = None,
        output_handler: Callable[[str, str], None] | None = None,
    ):
        """Initialize runbook engine.

        Args:
            prompt_handler: Function to handle user prompts (message, type, choices) -> response
            notify_handler: Function to handle notifications (channel, message) -> None
            output_handler: Function to handle step output (step_id, output) -> None
        """
        self._prompt_handler = prompt_handler
        self._notify_handler = notify_handler
        self._output_handler = output_handler
        self._markdown_parser = MarkdownRunbookParser()

    def load(self, file_path: str | Path) -> Runbook:
        """Load a runbook from file.

        Args:
            file_path: Path to runbook file (.yaml, .yml, or .md)

        Returns:
            Loaded Runbook
        """
        path = Path(file_path)

        if not path.exists():
            raise RunbookError(f"Runbook file not found: {path}")

        if path.suffix in (".yaml", ".yml"):
            return self._load_yaml(path)
        elif path.suffix == ".md":
            return self._markdown_parser.parse_file(path)
        else:
            raise RunbookError(f"Unsupported runbook format: {path.suffix}")

    def _load_yaml(self, path: Path) -> Runbook:
        """Load YAML runbook."""
        content = path.read_text()
        data = yaml.safe_load(content)

        if not data:
            raise RunbookError(f"Empty runbook file: {path}")

        steps = [self._parse_yaml_step(s, i) for i, s in enumerate(data.get("steps", []))]

        return Runbook(
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            steps=steps,
            variables=data.get("variables", {}),
            parameters=data.get("parameters", []),
            tags=data.get("tags", []),
            stop_on_failure=data.get("stop_on_failure", True),
            dry_run_supported=data.get("dry_run_supported", True),
            source_file=str(path),
        )

    def _parse_yaml_step(self, data: dict[str, Any], index: int) -> RunbookStep:
        """Parse a step from YAML data."""
        step_type = StepType(data.get("type", "command"))

        return RunbookStep(
            id=data.get("id", f"step_{index + 1}"),
            name=data.get("name", f"Step {index + 1}"),
            type=step_type,
            description=data.get("description", ""),
            command=data.get("command"),
            shell=data.get("shell", "/bin/bash"),
            timeout=data.get("timeout", 300),
            retries=data.get("retries", 0),
            retry_delay=data.get("retry_delay", 5),
            when=data.get("when"),
            on_failure=data.get("on_failure", "fail"),
            prompt_message=data.get("prompt_message"),
            prompt_default=data.get("prompt_default"),
            prompt_type=data.get("prompt_type", "confirm"),
            prompt_choices=data.get("prompt_choices"),
            wait_condition=data.get("wait_condition"),
            wait_timeout=data.get("wait_timeout", 300),
            wait_interval=data.get("wait_interval", 10),
            notify_channel=data.get("notify_channel"),
            notify_message=data.get("notify_message"),
            register=data.get("register"),
            environment=data.get("environment", {}),
            tags=data.get("tags", []),
        )

    def run(
        self,
        runbook: Runbook,
        variables: dict[str, Any] | None = None,
        dry_run: bool = False,
        start_step: str | None = None,
    ) -> RunbookResult:
        """Execute a runbook.

        Args:
            runbook: Runbook to execute
            variables: Variables to override
            dry_run: If True, don't execute commands
            start_step: Step ID to start from

        Returns:
            RunbookResult with execution details
        """
        # Merge variables
        run_vars = dict(runbook.variables)
        if variables:
            run_vars.update(variables)

        result = RunbookResult(
            runbook_name=runbook.name,
            status=StepStatus.RUNNING,
            started_at=datetime.utcnow(),
            variables=run_vars,
            dry_run=dry_run,
        )

        logger.info(
            "Starting runbook execution",
            runbook=runbook.name,
            dry_run=dry_run,
            variables=list(run_vars.keys()),
        )

        # Find start step
        start_index = 0
        if start_step:
            for i, step in enumerate(runbook.steps):
                if step.id == start_step:
                    start_index = i
                    break

        try:
            for step in runbook.steps[start_index:]:
                step_result = self._execute_step(step, run_vars, dry_run)
                result.step_results.append(step_result)

                # Update variables if step registered output
                if step.register and step_result.output:
                    run_vars[step.register] = step_result.output.strip()

                # Handle failure
                if step_result.status == StepStatus.FAILED:
                    if step.on_failure == "fail" and runbook.stop_on_failure:
                        result.status = StepStatus.FAILED
                        result.error = f"Step '{step.name}' failed: {step_result.error}"
                        break
                    elif step.on_failure == "skip_remaining":
                        break

            else:
                # All steps completed
                if all(r.status in (StepStatus.SUCCESS, StepStatus.SKIPPED) for r in result.step_results):
                    result.status = StepStatus.SUCCESS
                else:
                    result.status = StepStatus.FAILED

        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = str(e)
            logger.error("Runbook execution failed", error=str(e))

        result.ended_at = datetime.utcnow()
        result.variables = run_vars

        logger.info(
            "Runbook execution completed",
            runbook=runbook.name,
            status=result.status.value,
            duration=result.duration_seconds,
        )

        return result

    def _execute_step(
        self,
        step: RunbookStep,
        variables: dict[str, Any],
        dry_run: bool,
    ) -> StepResult:
        """Execute a single step."""
        result = StepResult(
            step_id=step.id,
            step_name=step.name,
            status=StepStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        logger.info("Executing step", step_id=step.id, step_name=step.name, type=step.type.value)

        try:
            # Check condition
            if step.when:
                if not self._evaluate_condition(step.when, variables):
                    result.status = StepStatus.SKIPPED
                    result.skipped_reason = f"Condition not met: {step.when}"
                    result.ended_at = datetime.utcnow()
                    logger.info("Step skipped", step_id=step.id, reason=result.skipped_reason)
                    return result

            # Execute based on type
            if step.type == StepType.MANUAL:
                result = self._execute_manual_step(step, result, dry_run)

            elif step.type == StepType.PROMPT:
                result = self._execute_prompt_step(step, result, variables, dry_run)

            elif step.type == StepType.NOTIFY:
                result = self._execute_notify_step(step, result, variables, dry_run)

            elif step.type == StepType.WAIT:
                result = self._execute_wait_step(step, result, variables, dry_run)

            elif step.type in (StepType.COMMAND, StepType.SCRIPT):
                result = self._execute_command_step(step, result, variables, dry_run)

            else:
                raise RunbookError(f"Unsupported step type: {step.type}")

        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = str(e)
            logger.error("Step failed", step_id=step.id, error=str(e))

        result.ended_at = datetime.utcnow()

        if self._output_handler and result.output:
            self._output_handler(step.id, result.output)

        return result

    def _execute_command_step(
        self,
        step: RunbookStep,
        result: StepResult,
        variables: dict[str, Any],
        dry_run: bool,
    ) -> StepResult:
        """Execute a command or script step."""
        if not step.command:
            result.status = StepStatus.SUCCESS
            result.output = "(no command)"
            return result

        # Substitute variables
        command = self._substitute_variables(step.command, variables)

        if dry_run:
            result.status = StepStatus.SUCCESS
            result.output = f"[DRY RUN] Would execute:\n{command}"
            return result

        # Prepare environment
        env = os.environ.copy()
        for key, value in step.environment.items():
            env[key] = self._substitute_variables(str(value), variables)

        # Add variables to environment
        for key, value in variables.items():
            env[f"RUNBOOK_{key.upper()}"] = str(value)

        # Execute with retries
        last_error = ""
        for attempt in range(step.retries + 1):
            try:
                proc = subprocess.run(
                    command,
                    shell=True,
                    executable=step.shell,
                    capture_output=True,
                    text=True,
                    timeout=step.timeout,
                    env=env,
                )

                result.return_code = proc.returncode
                result.output = proc.stdout
                result.error = proc.stderr

                if proc.returncode == 0:
                    result.status = StepStatus.SUCCESS
                    return result
                else:
                    last_error = proc.stderr or f"Exit code: {proc.returncode}"

            except subprocess.TimeoutExpired:
                last_error = f"Command timed out after {step.timeout}s"
            except Exception as e:
                last_error = str(e)

            if attempt < step.retries:
                logger.warning(
                    "Step failed, retrying",
                    step_id=step.id,
                    attempt=attempt + 1,
                    max_retries=step.retries,
                )
                time.sleep(step.retry_delay)

        result.status = StepStatus.FAILED
        result.error = last_error
        return result

    def _execute_prompt_step(
        self,
        step: RunbookStep,
        result: StepResult,
        variables: dict[str, Any],
        dry_run: bool,
    ) -> StepResult:
        """Execute a prompt step."""
        message = self._substitute_variables(
            step.prompt_message or step.description or step.name,
            variables,
        )

        if dry_run:
            result.status = StepStatus.SUCCESS
            result.output = f"[DRY RUN] Would prompt: {message}"
            return result

        if not self._prompt_handler:
            # Default: assume yes for confirms, empty for input
            if step.prompt_type == "confirm":
                result.output = "true"
            else:
                result.output = step.prompt_default or ""
            result.status = StepStatus.SUCCESS
            return result

        try:
            response = self._prompt_handler(message, step.prompt_type, step.prompt_choices)

            if step.prompt_type == "confirm":
                if not response:
                    result.status = StepStatus.SKIPPED
                    result.skipped_reason = "User declined"
                else:
                    result.status = StepStatus.SUCCESS
                    result.output = "confirmed"
            else:
                result.status = StepStatus.SUCCESS
                result.output = str(response)

        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = f"Prompt failed: {e}"

        return result

    def _execute_notify_step(
        self,
        step: RunbookStep,
        result: StepResult,
        variables: dict[str, Any],
        dry_run: bool,
    ) -> StepResult:
        """Execute a notification step."""
        channel = step.notify_channel or "default"
        message = self._substitute_variables(
            step.notify_message or step.description,
            variables,
        )

        if dry_run:
            result.status = StepStatus.SUCCESS
            result.output = f"[DRY RUN] Would notify {channel}: {message}"
            return result

        if self._notify_handler:
            try:
                self._notify_handler(channel, message)
                result.status = StepStatus.SUCCESS
                result.output = f"Notified {channel}"
            except Exception as e:
                result.status = StepStatus.FAILED
                result.error = f"Notification failed: {e}"
        else:
            result.status = StepStatus.SUCCESS
            result.output = f"(no notify handler) {channel}: {message}"

        return result

    def _execute_wait_step(
        self,
        step: RunbookStep,
        result: StepResult,
        variables: dict[str, Any],
        dry_run: bool,
    ) -> StepResult:
        """Execute a wait/poll step."""
        condition = step.wait_condition or step.command
        if not condition:
            result.status = StepStatus.SUCCESS
            return result

        condition = self._substitute_variables(condition, variables)

        if dry_run:
            result.status = StepStatus.SUCCESS
            result.output = f"[DRY RUN] Would wait for: {condition}"
            return result

        start_time = time.time()
        elapsed = 0

        while elapsed < step.wait_timeout:
            try:
                proc = subprocess.run(
                    condition,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if proc.returncode == 0:
                    result.status = StepStatus.SUCCESS
                    result.output = f"Condition met after {elapsed:.1f}s"
                    return result

            except subprocess.TimeoutExpired:
                pass

            time.sleep(step.wait_interval)
            elapsed = time.time() - start_time

        result.status = StepStatus.FAILED
        result.error = f"Wait condition not met after {step.wait_timeout}s"
        return result

    def _execute_manual_step(
        self,
        step: RunbookStep,
        result: StepResult,
        dry_run: bool,
    ) -> StepResult:
        """Execute a manual step (just documentation)."""
        result.status = StepStatus.SUCCESS
        result.output = step.description or "(manual step)"
        return result

    def _substitute_variables(self, text: str, variables: dict[str, Any]) -> str:
        """Substitute {{ var }} placeholders with values."""
        def replace(match: re.Match) -> str:
            var_name = match.group(1).strip()
            value = variables.get(var_name, match.group(0))
            return str(value)

        return re.sub(r"\{\{\s*(\w+)\s*\}\}", replace, text)

    def _evaluate_condition(self, condition: str, variables: dict[str, Any]) -> bool:
        """Evaluate a condition expression."""
        # Substitute variables first
        expr = self._substitute_variables(condition, variables)

        # Simple expression evaluator (safe subset)
        # Supports: ==, !=, <, >, <=, >=, and, or, not, in
        try:
            # Replace common operators
            expr = expr.replace(" and ", " and ")
            expr = expr.replace(" or ", " or ")

            # Create safe evaluation context
            safe_vars = {k: v for k, v in variables.items()}
            safe_vars["true"] = True
            safe_vars["false"] = False
            safe_vars["True"] = True
            safe_vars["False"] = False

            # Evaluate
            result = eval(expr, {"__builtins__": {}}, safe_vars)
            return bool(result)

        except Exception as e:
            logger.warning(f"Condition evaluation failed: {condition} - {e}")
            return False

    def validate(self, runbook: Runbook) -> list[str]:
        """Validate a runbook and return list of issues."""
        issues: list[str] = []

        if not runbook.name:
            issues.append("Runbook must have a name")

        if not runbook.steps:
            issues.append("Runbook must have at least one step")

        step_ids = set()
        for step in runbook.steps:
            if step.id in step_ids:
                issues.append(f"Duplicate step ID: {step.id}")
            step_ids.add(step.id)

            if not step.name:
                issues.append(f"Step {step.id} must have a name")

            if step.type in (StepType.COMMAND, StepType.SCRIPT) and not step.command:
                issues.append(f"Step {step.id} ({step.type.value}) must have a command")

            if step.type == StepType.WAIT and not step.wait_condition and not step.command:
                issues.append(f"Wait step {step.id} must have a condition")

        return issues

    def list_runbooks(self, directory: str | Path) -> list[dict[str, Any]]:
        """List available runbooks in a directory."""
        directory = Path(directory)
        runbooks: list[dict[str, Any]] = []

        for pattern in ("*.yaml", "*.yml", "*.md"):
            for path in directory.glob(pattern):
                try:
                    rb = self.load(path)
                    runbooks.append({
                        "name": rb.name,
                        "description": rb.description,
                        "version": rb.version,
                        "author": rb.author,
                        "file": str(path),
                        "steps": len(rb.steps),
                        "tags": rb.tags,
                    })
                except Exception as e:
                    logger.warning(f"Failed to load runbook {path}: {e}")

        return runbooks
