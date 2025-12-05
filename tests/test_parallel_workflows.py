"""Tests for parallel workflow execution."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

from devctl.workflows.schema import (
    WorkflowSchema,
    WorkflowStepSchema,
    ParallelBlockSchema,
    ParallelConfigSchema,
)
from devctl.workflows.graph import DependencyGraph, DependencyCycleError
from devctl.workflows.results import StepResult, ParallelBlockResult


class TestWorkflowStepSchema:
    """Tests for WorkflowStepSchema with parallel support."""

    def test_basic_step(self):
        """Test basic step with command."""
        step = WorkflowStepSchema(name="test", command="echo hello")
        assert step.name == "test"
        assert step.command == "echo hello"
        assert step.parallel is None
        assert step.depends_on == []

    def test_parallel_block_step(self):
        """Test step with parallel block."""
        step = WorkflowStepSchema(
            name="parallel-test",
            parallel=ParallelBlockSchema(
                name="test block",
                steps=[
                    WorkflowStepSchema(name="step1", command="echo 1"),
                    WorkflowStepSchema(name="step2", command="echo 2"),
                ],
            ),
        )
        assert step.name == "parallel-test"
        assert step.command is None
        assert step.parallel is not None
        assert len(step.parallel.steps) == 2

    def test_depends_on_step(self):
        """Test step with dependencies."""
        step = WorkflowStepSchema(
            name="dependent",
            command="echo dep",
            depends_on=["step1", "step2"],
        )
        assert step.depends_on == ["step1", "step2"]

    def test_step_requires_command_or_parallel(self):
        """Test that step must have either command or parallel."""
        with pytest.raises(ValueError, match="must have either"):
            WorkflowStepSchema(name="invalid")

    def test_step_cannot_have_both_command_and_parallel(self):
        """Test that step cannot have both command and parallel."""
        with pytest.raises(ValueError, match="cannot have both"):
            WorkflowStepSchema(
                name="invalid",
                command="echo hello",
                parallel=ParallelBlockSchema(
                    steps=[WorkflowStepSchema(name="inner", command="echo inner")]
                ),
            )


class TestParallelBlockSchema:
    """Tests for ParallelBlockSchema."""

    def test_basic_parallel_block(self):
        """Test basic parallel block."""
        block = ParallelBlockSchema(
            name="test block",
            steps=[
                WorkflowStepSchema(name="step1", command="echo 1"),
                WorkflowStepSchema(name="step2", command="echo 2"),
            ],
        )
        assert block.name == "test block"
        assert len(block.steps) == 2
        assert block.on_failure == "fail_all"
        assert block.timeout is None

    def test_parallel_block_with_options(self):
        """Test parallel block with all options."""
        block = ParallelBlockSchema(
            name="configured block",
            steps=[WorkflowStepSchema(name="step1", command="echo 1")],
            on_failure="continue",
            timeout=60,
            max_concurrent=5,
        )
        assert block.on_failure == "continue"
        assert block.timeout == 60
        assert block.max_concurrent == 5


class TestParallelConfigSchema:
    """Tests for ParallelConfigSchema."""

    def test_defaults(self):
        """Test default configuration."""
        config = ParallelConfigSchema()
        assert config.max_concurrent == 10
        assert config.rate_limit is None
        assert config.fail_fast is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ParallelConfigSchema(
            max_concurrent=5,
            rate_limit=2.0,
            fail_fast=False,
        )
        assert config.max_concurrent == 5
        assert config.rate_limit == 2.0
        assert config.fail_fast is False


class TestDependencyGraph:
    """Tests for DependencyGraph."""

    def test_simple_dependency(self):
        """Test simple linear dependency chain."""
        steps = [
            WorkflowStepSchema(name="a", command="a"),
            WorkflowStepSchema(name="b", command="b", depends_on=["a"]),
            WorkflowStepSchema(name="c", command="c", depends_on=["b"]),
        ]
        graph = DependencyGraph(steps)
        graph.validate()

        layers = graph.topological_sort()
        assert layers == [["a"], ["b"], ["c"]]

    def test_parallel_dependencies(self):
        """Test diamond dependency pattern."""
        steps = [
            WorkflowStepSchema(name="checkout", command="git checkout"),
            WorkflowStepSchema(name="build-a", command="build a", depends_on=["checkout"]),
            WorkflowStepSchema(name="build-b", command="build b", depends_on=["checkout"]),
            WorkflowStepSchema(name="deploy", command="deploy", depends_on=["build-a", "build-b"]),
        ]
        graph = DependencyGraph(steps)
        graph.validate()

        layers = graph.topological_sort()
        assert layers[0] == ["checkout"]
        assert set(layers[1]) == {"build-a", "build-b"}
        assert layers[2] == ["deploy"]

    def test_cycle_detection(self):
        """Test detection of circular dependencies."""
        steps = [
            WorkflowStepSchema(name="a", command="a", depends_on=["c"]),
            WorkflowStepSchema(name="b", command="b", depends_on=["a"]),
            WorkflowStepSchema(name="c", command="c", depends_on=["b"]),
        ]
        graph = DependencyGraph(steps)

        with pytest.raises(DependencyCycleError) as exc_info:
            graph.validate()

        assert "circular dependency" in str(exc_info.value)

    def test_missing_dependency(self):
        """Test error on missing dependency."""
        steps = [
            WorkflowStepSchema(name="a", command="a", depends_on=["nonexistent"]),
        ]

        with pytest.raises(Exception) as exc_info:
            DependencyGraph(steps)

        assert "unknown step" in str(exc_info.value)

    def test_get_ready_steps(self):
        """Test getting steps ready for execution."""
        steps = [
            WorkflowStepSchema(name="a", command="a"),
            WorkflowStepSchema(name="b", command="b", depends_on=["a"]),
            WorkflowStepSchema(name="c", command="c", depends_on=["a"]),
            WorkflowStepSchema(name="d", command="d", depends_on=["b", "c"]),
        ]
        graph = DependencyGraph(steps)

        # Initially only 'a' is ready
        ready = graph.get_ready_steps(set())
        assert ready == ["a"]

        # After 'a' completes, 'b' and 'c' are ready
        ready = graph.get_ready_steps({"a"})
        assert set(ready) == {"b", "c"}

        # After 'b' completes, still waiting for 'c'
        ready = graph.get_ready_steps({"a", "b"})
        assert ready == ["c"]

        # After both complete, 'd' is ready
        ready = graph.get_ready_steps({"a", "b", "c"})
        assert ready == ["d"]

    def test_root_steps(self):
        """Test getting root steps (no dependencies)."""
        steps = [
            WorkflowStepSchema(name="a", command="a"),
            WorkflowStepSchema(name="b", command="b"),
            WorkflowStepSchema(name="c", command="c", depends_on=["a"]),
        ]
        graph = DependencyGraph(steps)

        roots = graph.get_root_steps()
        assert set(roots) == {"a", "b"}

    def test_has_dependencies(self):
        """Test checking if graph has any dependencies."""
        no_deps = [
            WorkflowStepSchema(name="a", command="a"),
            WorkflowStepSchema(name="b", command="b"),
        ]
        graph1 = DependencyGraph(no_deps)
        assert not graph1.has_dependencies()

        with_deps = [
            WorkflowStepSchema(name="a", command="a"),
            WorkflowStepSchema(name="b", command="b", depends_on=["a"]),
        ]
        graph2 = DependencyGraph(with_deps)
        assert graph2.has_dependencies()


class TestStepResult:
    """Tests for StepResult."""

    def test_successful_result(self):
        """Test successful step result."""
        result = StepResult(
            name="test",
            success=True,
            stdout="output",
            duration=1.5,
        )
        assert result.success is True
        assert result.name == "test"

        d = result.to_dict()
        assert d["success"] is True
        assert d["name"] == "test"

    def test_failed_result(self):
        """Test failed step result."""
        result = StepResult(
            name="test",
            success=False,
            error="something went wrong",
        )
        assert result.success is False
        assert result.error == "something went wrong"

    def test_skipped_result(self):
        """Test skipped step result."""
        result = StepResult(
            name="test",
            success=True,
            skipped=True,
        )
        assert result.skipped is True


class TestParallelBlockResult:
    """Tests for ParallelBlockResult."""

    def test_all_succeeded(self):
        """Test parallel block with all steps succeeded."""
        result = ParallelBlockResult(
            name="test block",
            success=True,
            steps=[
                StepResult(name="a", success=True),
                StepResult(name="b", success=True),
                StepResult(name="c", success=True),
            ],
        )
        assert result.all_succeeded is True
        assert result.succeeded_count == 3
        assert result.failed_count == 0

    def test_some_failed(self):
        """Test parallel block with some steps failed."""
        result = ParallelBlockResult(
            name="test block",
            success=False,
            steps=[
                StepResult(name="a", success=True),
                StepResult(name="b", success=False),
                StepResult(name="c", success=True),
            ],
        )
        assert result.all_succeeded is False
        assert result.any_succeeded is True
        assert result.succeeded_count == 2
        assert result.failed_count == 1

    def test_with_skipped(self):
        """Test parallel block with skipped steps."""
        result = ParallelBlockResult(
            name="test block",
            success=True,
            steps=[
                StepResult(name="a", success=True),
                StepResult(name="b", success=True, skipped=True),
            ],
        )
        assert result.skipped_count == 1
        assert result.succeeded_count == 1


class TestWorkflowSchema:
    """Tests for WorkflowSchema with parallel support."""

    def test_workflow_with_parallel_config(self):
        """Test workflow with parallel configuration."""
        workflow = WorkflowSchema(
            name="test",
            parallel=ParallelConfigSchema(max_concurrent=5),
            steps=[WorkflowStepSchema(name="test", command="echo")],
        )
        assert workflow.parallel.max_concurrent == 5

    def test_workflow_default_parallel_config(self):
        """Test workflow has default parallel configuration."""
        workflow = WorkflowSchema(
            name="test",
            steps=[WorkflowStepSchema(name="test", command="echo")],
        )
        assert workflow.parallel.max_concurrent == 10
        assert workflow.parallel.fail_fast is True
