"""Workflow execution result types."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class StepResult:
    """Result from a single workflow step execution."""

    name: str
    success: bool
    skipped: bool = False
    dry_run: bool = False
    error: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    returncode: int | None = None
    duration: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for compatibility."""
        return {
            "name": self.name,
            "success": self.success,
            "skipped": self.skipped,
            "dry_run": self.dry_run,
            "error": self.error,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "duration": self.duration,
        }


@dataclass
class ParallelBlockResult:
    """Aggregated result from a parallel block execution."""

    name: str | None
    success: bool
    steps: list[StepResult] = field(default_factory=list)
    total_duration: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def failed_count(self) -> int:
        """Count of failed steps."""
        return sum(1 for s in self.steps if not s.success and not s.skipped)

    @property
    def succeeded_count(self) -> int:
        """Count of succeeded steps."""
        return sum(1 for s in self.steps if s.success and not s.skipped)

    @property
    def skipped_count(self) -> int:
        """Count of skipped steps."""
        return sum(1 for s in self.steps if s.skipped)

    @property
    def all_succeeded(self) -> bool:
        """Check if all steps succeeded."""
        return self.failed_count == 0

    @property
    def any_succeeded(self) -> bool:
        """Check if any step succeeded."""
        return self.succeeded_count > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for compatibility."""
        return {
            "name": self.name,
            "success": self.success,
            "steps": [s.to_dict() for s in self.steps],
            "failed_count": self.failed_count,
            "succeeded_count": self.succeeded_count,
            "skipped_count": self.skipped_count,
            "total_duration": self.total_duration,
        }
