"""Progress indicator utilities for long-running operations."""

from contextlib import contextmanager
from typing import Any, Generator, Iterator, TypeVar

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TaskID,
)
from rich.live import Live
from rich.status import Status
from rich.table import Table

console = Console()

T = TypeVar("T")


class ProgressManager:
    """Manages progress indicators for CLI operations.

    Supports multiple concurrent progress bars, spinners, and status indicators.
    """

    def __init__(self, console: Console | None = None):
        """Initialize progress manager.

        Args:
            console: Rich console to use for output
        """
        self._console = console or Console()
        self._progress: Progress | None = None
        self._tasks: dict[str, TaskID] = {}

    @contextmanager
    def progress(
        self,
        description: str = "Processing",
        total: int | None = None,
        transient: bool = True,
    ) -> Generator[Progress, None, None]:
        """Create a progress bar context.

        Args:
            description: Description of the operation
            total: Total number of items (None for indeterminate)
            transient: Whether to remove progress bar when done

        Yields:
            Rich Progress object
        """
        columns = [
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
        ]

        if total is not None:
            columns.extend([
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            ])
        else:
            columns.append(TimeElapsedColumn())

        with Progress(
            *columns,
            console=self._console,
            transient=transient,
        ) as progress:
            task = progress.add_task(description, total=total)
            self._progress = progress
            self._tasks["main"] = task
            try:
                yield progress
            finally:
                self._progress = None
                self._tasks.clear()

    @contextmanager
    def status(
        self,
        message: str,
        spinner: str = "dots",
    ) -> Generator[Status, None, None]:
        """Create a status spinner context.

        Args:
            message: Status message to display
            spinner: Spinner style to use

        Yields:
            Rich Status object for updating the message
        """
        with self._console.status(message, spinner=spinner) as status:
            yield status

    @contextmanager
    def multi_progress(
        self,
        tasks: list[dict[str, Any]],
        transient: bool = True,
    ) -> Generator[Progress, None, None]:
        """Create multiple progress bars.

        Args:
            tasks: List of task definitions with 'name', 'total' keys
            transient: Whether to remove progress bars when done

        Yields:
            Rich Progress object with all tasks added
        """
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self._console,
            transient=transient,
        ) as progress:
            self._progress = progress
            for task_def in tasks:
                name = task_def.get("name", "Task")
                total = task_def.get("total")
                task_id = progress.add_task(name, total=total)
                self._tasks[name] = task_id
            try:
                yield progress
            finally:
                self._progress = None
                self._tasks.clear()

    def update(
        self,
        task_name: str = "main",
        advance: int = 1,
        description: str | None = None,
    ) -> None:
        """Update a progress task.

        Args:
            task_name: Name of task to update
            advance: Amount to advance progress by
            description: New description (optional)
        """
        if self._progress and task_name in self._tasks:
            task_id = self._tasks[task_name]
            kwargs: dict[str, Any] = {"advance": advance}
            if description:
                kwargs["description"] = description
            self._progress.update(task_id, **kwargs)

    def track_iterator(
        self,
        items: Iterator[T],
        description: str = "Processing",
        total: int | None = None,
    ) -> Generator[T, None, None]:
        """Track progress through an iterator.

        Args:
            items: Items to iterate over
            description: Progress description
            total: Total number of items

        Yields:
            Items from the iterator
        """
        with self.progress(description, total=total) as progress:
            task = self._tasks.get("main")
            for item in items:
                yield item
                if task is not None:
                    progress.advance(task)


@contextmanager
def spinner(
    message: str,
    success_message: str | None = None,
    error_message: str | None = None,
) -> Generator[None, None, None]:
    """Simple spinner context manager.

    Args:
        message: Message to display while spinning
        success_message: Message to display on success
        error_message: Message to display on error

    Yields:
        Nothing - just displays spinner during operation
    """
    status = console.status(message, spinner="dots")
    status.start()
    try:
        yield
        status.stop()
        if success_message:
            console.print(f"[green]✓[/green] {success_message}")
    except Exception:
        status.stop()
        if error_message:
            console.print(f"[red]✗[/red] {error_message}")
        raise


@contextmanager
def progress_bar(
    description: str = "Processing",
    total: int | None = None,
    transient: bool = True,
) -> Generator[Progress, None, None]:
    """Simple progress bar context manager.

    Args:
        description: Description of operation
        total: Total items (None for indeterminate)
        transient: Remove bar when done

    Yields:
        Rich Progress object
    """
    manager = ProgressManager()
    with manager.progress(description, total, transient) as progress:
        yield progress


def track(
    items: Iterator[T],
    description: str = "Processing",
    total: int | None = None,
) -> Generator[T, None, None]:
    """Track progress through an iterator.

    Simple wrapper around ProgressManager.track_iterator.

    Args:
        items: Items to iterate over
        description: Progress description
        total: Total number of items

    Yields:
        Items from the iterator
    """
    manager = ProgressManager()
    yield from manager.track_iterator(items, description, total)


class StepProgress:
    """Track progress through named steps.

    Useful for multi-step operations where each step
    has a name and can succeed or fail independently.
    """

    def __init__(self, steps: list[str], title: str = "Progress"):
        """Initialize step progress tracker.

        Args:
            steps: List of step names
            title: Title for the progress display
        """
        self._steps = steps
        self._title = title
        self._current = 0
        self._results: dict[str, str] = {}
        self._console = Console()

    def start(self, step_name: str) -> None:
        """Mark a step as started.

        Args:
            step_name: Name of the step
        """
        self._results[step_name] = "running"
        self._display()

    def complete(self, step_name: str, success: bool = True) -> None:
        """Mark a step as complete.

        Args:
            step_name: Name of the step
            success: Whether step succeeded
        """
        self._results[step_name] = "success" if success else "failed"
        self._current += 1
        self._display()

    def skip(self, step_name: str) -> None:
        """Mark a step as skipped.

        Args:
            step_name: Name of the step
        """
        self._results[step_name] = "skipped"
        self._current += 1
        self._display()

    def _display(self) -> None:
        """Display current progress state."""
        table = Table(title=self._title, show_header=False)
        table.add_column("Status", width=8)
        table.add_column("Step")

        for step in self._steps:
            status = self._results.get(step, "pending")
            if status == "success":
                icon = "[green]✓[/green]"
            elif status == "failed":
                icon = "[red]✗[/red]"
            elif status == "skipped":
                icon = "[dim]○[/dim]"
            elif status == "running":
                icon = "[yellow]●[/yellow]"
            else:
                icon = "[dim]○[/dim]"

            table.add_row(icon, step)

        self._console.print(table)

    @contextmanager
    def step(self, name: str) -> Generator[None, None, None]:
        """Context manager for a step.

        Args:
            name: Name of the step

        Yields:
            Nothing - marks step success/failure automatically
        """
        self.start(name)
        try:
            yield
            self.complete(name, success=True)
        except Exception:
            self.complete(name, success=False)
            raise
