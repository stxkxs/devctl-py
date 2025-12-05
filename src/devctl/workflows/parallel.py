"""Parallel workflow execution."""

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from rich.live import Live
from rich.table import Table

from devctl.core.async_utils import RateLimiter
from devctl.core.exceptions import WorkflowError
from devctl.workflows.graph import DependencyGraph
from devctl.workflows.results import ParallelBlockResult, StepResult

if TYPE_CHECKING:
    from devctl.workflows.engine import WorkflowEngine
    from devctl.workflows.schema import ParallelBlockSchema, ParallelConfigSchema, WorkflowStepSchema


class ParallelExecutionError(WorkflowError):
    """Raised when parallel execution fails."""

    def __init__(
        self,
        message: str,
        failed_steps: list[str] | None = None,
        results: list[StepResult] | None = None,
    ):
        super().__init__(message)
        self.failed_steps = failed_steps or []
        self.results = results or []


class ParallelExecutor:
    """Coordinates parallel step execution."""

    def __init__(
        self,
        engine: "WorkflowEngine",
        config: "ParallelConfigSchema",
    ):
        self.engine = engine
        self.config = config
        self.semaphore = asyncio.Semaphore(config.max_concurrent)
        self.rate_limiter = (
            RateLimiter(config.rate_limit) if config.rate_limit else None
        )
        self._cancel_event = asyncio.Event()
        self._results: dict[str, StepResult] = {}
        self._lock = asyncio.Lock()

    async def execute_parallel_block(
        self,
        block: "ParallelBlockSchema",
        step_num: int,
        total_steps: int,
        dry_run: bool,
    ) -> ParallelBlockResult:
        """Execute a parallel block of steps.

        Args:
            block: parallel block configuration
            step_num: current step number in workflow
            total_steps: total steps in workflow
            dry_run: if True, show what would be done

        Returns:
            ParallelBlockResult with aggregated results
        """
        started_at = datetime.now()
        start_time = time.monotonic()

        block_name = block.name or f"parallel block {step_num}"
        self.engine.ctx.output.print(f"\n[bold]Step {step_num}/{total_steps}: {block_name}[/bold]")
        self.engine.ctx.output.print(f"[dim]Running {len(block.steps)} steps in parallel...[/dim]")

        # use block-level concurrency override if specified
        max_concurrent = block.max_concurrent or self.config.max_concurrent
        semaphore = asyncio.Semaphore(max_concurrent)

        # create tasks for all steps
        tasks: list[asyncio.Task[StepResult]] = []
        for i, step in enumerate(block.steps):
            task = asyncio.create_task(
                self._execute_step_with_limits(
                    step, i + 1, len(block.steps), dry_run, semaphore
                )
            )
            tasks.append(task)

        # execute with timeout if specified
        results: list[StepResult] = []
        try:
            if block.timeout:
                done, pending = await asyncio.wait(
                    tasks,
                    timeout=block.timeout,
                    return_when=asyncio.ALL_COMPLETED,
                )

                # cancel pending tasks
                for task in pending:
                    task.cancel()

                # collect results from done tasks
                for task in done:
                    try:
                        results.append(task.result())
                    except Exception as e:
                        # task failed
                        results.append(StepResult(
                            name="unknown",
                            success=False,
                            error=str(e),
                        ))

                # add timeout results for pending
                for task in pending:
                    results.append(StepResult(
                        name="unknown",
                        success=False,
                        error="step timed out",
                    ))
            else:
                # no timeout - gather all results
                results = await asyncio.gather(*tasks, return_exceptions=False)

        except Exception as e:
            # handle unexpected errors
            self.engine.ctx.output.print_error(f"parallel execution failed: {e}")
            return ParallelBlockResult(
                name=block_name,
                success=False,
                steps=results,
                total_duration=time.monotonic() - start_time,
                started_at=started_at,
                completed_at=datetime.now(),
            )

        # handle failure modes
        failed_steps = [r for r in results if not r.success and not r.skipped]
        success = len(failed_steps) == 0

        if failed_steps and block.on_failure == "fail_all":
            success = False
        elif block.on_failure == "continue":
            # continue mode - success if any step succeeded
            success = any(r.success for r in results)

        # display summary
        completed_at = datetime.now()
        total_duration = time.monotonic() - start_time

        self._display_summary(block_name, results, total_duration)

        return ParallelBlockResult(
            name=block_name,
            success=success,
            steps=results,
            total_duration=total_duration,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def execute_dag(
        self,
        steps: list["WorkflowStepSchema"],
        dry_run: bool,
    ) -> dict[str, StepResult]:
        """Execute steps based on dependency graph.

        Args:
            steps: workflow steps with depends_on fields
            dry_run: if True, show what would be done

        Returns:
            dict mapping step names to results
        """
        graph = DependencyGraph(steps)
        graph.validate()

        layers = graph.topological_sort()
        results: dict[str, StepResult] = {}

        total_steps = len(steps)
        step_counter = 0

        for layer_num, layer in enumerate(layers):
            self.engine.ctx.output.print(
                f"\n[dim]Layer {layer_num + 1}/{len(layers)}: "
                f"running {len(layer)} steps in parallel[/dim]"
            )

            # create tasks for this layer
            tasks: list[asyncio.Task[StepResult]] = []
            for step_name in layer:
                step = graph.steps[step_name]
                step_counter += 1
                task = asyncio.create_task(
                    self._execute_step_with_limits(
                        step, step_counter, total_steps, dry_run, self.semaphore
                    )
                )
                tasks.append(task)

            # wait for all tasks in this layer
            layer_results = await asyncio.gather(*tasks)

            for result in layer_results:
                results[result.name] = result
                self._results[result.name] = result

                # check for failures in fail_fast mode
                if not result.success and not result.skipped and self.config.fail_fast:
                    self.engine.ctx.output.print_error(
                        f"step '{result.name}' failed, stopping execution"
                    )
                    return results

        return results

    async def _execute_step_with_limits(
        self,
        step: "WorkflowStepSchema",
        step_num: int,
        total: int,
        dry_run: bool,
        semaphore: asyncio.Semaphore,
    ) -> StepResult:
        """Execute a step with semaphore and rate limiting.

        Args:
            step: step to execute
            step_num: step number
            total: total steps
            dry_run: if True, show what would be done
            semaphore: concurrency limiter

        Returns:
            StepResult
        """
        async with semaphore:
            if self.rate_limiter:
                await self.rate_limiter.acquire()

            if self._cancel_event.is_set():
                return StepResult(
                    name=step.name,
                    success=False,
                    error="execution cancelled",
                )

            # execute step synchronously (workflow engine is sync)
            start_time = time.monotonic()
            started_at = datetime.now()

            try:
                # run in thread pool since _execute_step is sync
                loop = asyncio.get_event_loop()
                result_dict = await loop.run_in_executor(
                    None,
                    lambda: self.engine._execute_step(step, step_num, total, dry_run),
                )

                duration = time.monotonic() - start_time

                return StepResult(
                    name=step.name,
                    success=result_dict.get("success", False),
                    skipped=result_dict.get("skipped", False),
                    dry_run=result_dict.get("dry_run", False),
                    error=result_dict.get("error"),
                    stdout=result_dict.get("stdout"),
                    stderr=result_dict.get("stderr"),
                    returncode=result_dict.get("returncode"),
                    duration=duration,
                    started_at=started_at,
                    completed_at=datetime.now(),
                )

            except Exception as e:
                return StepResult(
                    name=step.name,
                    success=False,
                    error=str(e),
                    duration=time.monotonic() - start_time,
                    started_at=started_at,
                    completed_at=datetime.now(),
                )

    def _display_summary(
        self,
        block_name: str,
        results: list[StepResult],
        duration: float,
    ) -> None:
        """Display parallel execution summary."""
        table = Table(title=f"Parallel: {block_name}")
        table.add_column("Step", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")

        for result in results:
            if result.skipped:
                status = "[dim]SKIP[/dim]"
            elif result.success:
                status = "[green]OK[/green]"
            else:
                status = "[red]FAIL[/red]"

            table.add_row(
                result.name,
                status,
                f"{result.duration:.1f}s",
            )

        self.engine.ctx.output.console.print(table)

        succeeded = sum(1 for r in results if r.success and not r.skipped)
        failed = sum(1 for r in results if not r.success and not r.skipped)
        skipped = sum(1 for r in results if r.skipped)

        summary = f"[dim]{succeeded} succeeded, {failed} failed, {skipped} skipped in {duration:.1f}s[/dim]"
        self.engine.ctx.output.print(summary)

    def cancel(self) -> None:
        """Cancel ongoing parallel execution."""
        self._cancel_event.set()
