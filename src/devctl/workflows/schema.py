"""Workflow schema validation."""

from __future__ import annotations

from typing import Any, Literal, TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator, model_validator


class ParallelConfigSchema(BaseModel):
    """Global parallel execution configuration."""

    max_concurrent: int = 10
    rate_limit: float | None = None  # steps per second
    fail_fast: bool = True


class WorkflowStepSchema(BaseModel):
    """Schema for a workflow step."""

    name: str
    command: str | None = None  # optional if parallel block
    params: dict[str, Any] = Field(default_factory=dict)
    on_failure: str = "fail"  # fail, continue, skip
    condition: str | None = None
    timeout: int | None = None
    retries: int = 0

    # parallel execution fields
    parallel: ParallelBlockSchema | None = None
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("on_failure")
    @classmethod
    def validate_on_failure(cls, v: str) -> str:
        if v not in ("fail", "continue", "skip"):
            raise ValueError("on_failure must be 'fail', 'continue', or 'skip'")
        return v

    @model_validator(mode="after")
    def validate_command_or_parallel(self) -> "WorkflowStepSchema":
        """Ensure step has either command or parallel block."""
        if self.command is None and self.parallel is None:
            raise ValueError("step must have either 'command' or 'parallel'")
        if self.command is not None and self.parallel is not None:
            raise ValueError("step cannot have both 'command' and 'parallel'")
        return self


class ParallelBlockSchema(BaseModel):
    """Schema for a parallel step group."""

    name: str | None = None
    steps: list[WorkflowStepSchema] = Field(default_factory=list)
    on_failure: Literal["fail_all", "continue", "complete_running"] = "fail_all"
    timeout: int | None = None
    max_concurrent: int | None = None  # override global setting


# rebuild models to resolve forward references
WorkflowStepSchema.model_rebuild()


class WorkflowSchema(BaseModel):
    """Schema for a workflow definition."""

    name: str | None = None
    description: str = ""
    version: str = "1"
    steps: list[WorkflowStepSchema] = Field(default_factory=list)
    vars: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    on_success: list[str] = Field(default_factory=list)
    on_failure: list[str] = Field(default_factory=list)

    # parallel execution configuration
    parallel: ParallelConfigSchema = Field(default_factory=ParallelConfigSchema)


def validate_workflow(workflow_dict: dict[str, Any]) -> WorkflowSchema:
    """Validate a workflow dictionary against the schema.

    Args:
        workflow_dict: Dictionary representation of workflow

    Returns:
        Validated WorkflowSchema object

    Raises:
        ValidationError: If validation fails
    """
    return WorkflowSchema(**workflow_dict)
