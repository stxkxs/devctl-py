"""Runbook data models and schemas."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StepType(str, Enum):
    """Types of runbook steps."""

    COMMAND = "command"  # Shell command
    SCRIPT = "script"  # Multi-line script
    PROMPT = "prompt"  # User confirmation/input
    CONDITIONAL = "conditional"  # If/else logic
    PARALLEL = "parallel"  # Parallel step execution
    WAIT = "wait"  # Wait for condition
    NOTIFY = "notify"  # Send notification
    MANUAL = "manual"  # Manual step (documentation only)


class StepStatus(str, Enum):
    """Step execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RunbookStep:
    """A single step in a runbook."""

    id: str
    name: str
    type: StepType
    description: str = ""

    # Execution details
    command: str | None = None  # For command/script types
    shell: str = "/bin/bash"  # Shell to use
    timeout: int = 300  # Timeout in seconds
    retries: int = 0  # Number of retries on failure
    retry_delay: int = 5  # Seconds between retries

    # Conditional execution
    when: str | None = None  # Condition expression
    on_failure: str = "fail"  # fail, continue, skip_remaining

    # For prompt type
    prompt_message: str | None = None
    prompt_default: str | None = None
    prompt_type: str = "confirm"  # confirm, input, choice
    prompt_choices: list[str] | None = None

    # For parallel type
    parallel_steps: list["RunbookStep"] | None = None
    max_parallel: int = 5

    # For wait type
    wait_condition: str | None = None
    wait_timeout: int = 300
    wait_interval: int = 10

    # For notify type
    notify_channel: str | None = None
    notify_message: str | None = None

    # Variables
    register: str | None = None  # Store output in variable
    environment: dict[str, str] = field(default_factory=dict)

    # Metadata
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "command": self.command,
            "timeout": self.timeout,
            "when": self.when,
            "on_failure": self.on_failure,
            "tags": self.tags,
        }


@dataclass
class StepResult:
    """Result of executing a step."""

    step_id: str
    step_name: str
    status: StepStatus
    started_at: datetime
    ended_at: datetime | None = None
    output: str = ""
    error: str = ""
    return_code: int | None = None
    skipped_reason: str | None = None

    @property
    def duration_seconds(self) -> float:
        """Get step duration in seconds."""
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "step_name": self.step_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "output": self.output,
            "error": self.error,
            "return_code": self.return_code,
        }


@dataclass
class Runbook:
    """A runbook definition."""

    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    steps: list[RunbookStep] = field(default_factory=list)

    # Variables and parameters
    variables: dict[str, Any] = field(default_factory=dict)
    parameters: list[dict[str, Any]] = field(default_factory=list)

    # Execution settings
    stop_on_failure: bool = True
    dry_run_supported: bool = True

    # Metadata
    tags: list[str] = field(default_factory=list)
    source_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "steps": [s.to_dict() for s in self.steps],
            "variables": self.variables,
            "parameters": self.parameters,
            "tags": self.tags,
        }

    def get_step(self, step_id: str) -> RunbookStep | None:
        """Get step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


@dataclass
class RunbookResult:
    """Result of running a runbook."""

    runbook_name: str
    status: StepStatus
    started_at: datetime
    ended_at: datetime | None = None
    step_results: list[StepResult] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    error: str | None = None

    @property
    def duration_seconds(self) -> float:
        """Get total duration in seconds."""
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return 0.0

    @property
    def successful_steps(self) -> int:
        """Count successful steps."""
        return sum(1 for r in self.step_results if r.status == StepStatus.SUCCESS)

    @property
    def failed_steps(self) -> int:
        """Count failed steps."""
        return sum(1 for r in self.step_results if r.status == StepStatus.FAILED)

    @property
    def skipped_steps(self) -> int:
        """Count skipped steps."""
        return sum(1 for r in self.step_results if r.status == StepStatus.SKIPPED)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "runbook_name": self.runbook_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "dry_run": self.dry_run,
            "summary": {
                "total": len(self.step_results),
                "successful": self.successful_steps,
                "failed": self.failed_steps,
                "skipped": self.skipped_steps,
            },
            "step_results": [r.to_dict() for r in self.step_results],
            "variables": self.variables,
            "error": self.error,
        }
