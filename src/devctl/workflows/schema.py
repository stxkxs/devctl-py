"""Workflow schema validation."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class WorkflowStepSchema(BaseModel):
    """Schema for a workflow step."""

    name: str
    command: str
    params: dict[str, Any] = Field(default_factory=dict)
    on_failure: str = "fail"  # fail, continue, skip
    condition: str | None = None
    timeout: int | None = None
    retries: int = 0

    @field_validator("on_failure")
    @classmethod
    def validate_on_failure(cls, v: str) -> str:
        if v not in ("fail", "continue", "skip"):
            raise ValueError("on_failure must be 'fail', 'continue', or 'skip'")
        return v


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
