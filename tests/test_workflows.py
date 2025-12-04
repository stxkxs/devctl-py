"""Tests for workflow engine - the core integration layer."""

import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from devctl.config import DevCtlConfig, ProfileConfig, AWSConfig
from devctl.core.context import DevCtlContext
from devctl.core.output import OutputFormat
from devctl.core.exceptions import WorkflowError
from devctl.workflows.schema import WorkflowSchema, WorkflowStepSchema, validate_workflow
from devctl.workflows.engine import WorkflowEngine


# --- Schema Validation Tests (Unit) ---


class TestWorkflowStepSchema:
    """Tests for WorkflowStepSchema validation."""

    def test_minimal_step(self):
        step = WorkflowStepSchema(name="test", command="aws s3 ls")
        assert step.name == "test"
        assert step.command == "aws s3 ls"
        assert step.params == {}
        assert step.on_failure == "fail"

    def test_step_with_params(self):
        step = WorkflowStepSchema(
            name="list buckets",
            command="aws s3 ls",
            params={"bucket": "my-bucket", "prefix": "logs/"},
        )
        assert step.params["bucket"] == "my-bucket"

    def test_step_with_timeout(self):
        step = WorkflowStepSchema(name="slow", command="aws forecast train", timeout=3600)
        assert step.timeout == 3600

    def test_on_failure_valid_values(self):
        for value in ["fail", "continue", "skip"]:
            step = WorkflowStepSchema(name="test", command="test", on_failure=value)
            assert step.on_failure == value

    def test_on_failure_invalid_value(self):
        with pytest.raises(ValidationError):
            WorkflowStepSchema(name="test", command="test", on_failure="invalid")

    def test_step_with_condition(self):
        step = WorkflowStepSchema(
            name="conditional",
            command="aws deploy",
            condition="{{ environment == 'production' }}",
        )
        assert step.condition == "{{ environment == 'production' }}"


class TestWorkflowSchema:
    """Tests for WorkflowSchema validation."""

    def test_minimal_workflow(self):
        workflow = WorkflowSchema()
        assert workflow.name is None
        assert workflow.steps == []
        assert workflow.vars == {}

    def test_workflow_with_steps(self):
        workflow = WorkflowSchema(
            name="deploy",
            description="Deploy service",
            steps=[
                WorkflowStepSchema(name="build", command="aws ecr build"),
                WorkflowStepSchema(name="deploy", command="aws ecs deploy"),
            ],
        )
        assert len(workflow.steps) == 2
        assert workflow.steps[0].name == "build"

    def test_workflow_with_vars(self):
        workflow = WorkflowSchema(
            name="test",
            vars={"cluster": "production", "replicas": 3},
        )
        assert workflow.vars["cluster"] == "production"
        assert workflow.vars["replicas"] == 3


class TestValidateWorkflow:
    """Tests for validate_workflow function."""

    def test_valid_workflow_dict(self):
        workflow_dict = {
            "name": "test-workflow",
            "description": "A test workflow",
            "vars": {"env": "staging"},
            "steps": [
                {"name": "step1", "command": "aws s3 ls"},
                {"name": "step2", "command": "!echo done"},
            ],
        }
        workflow = validate_workflow(workflow_dict)
        assert workflow.name == "test-workflow"
        assert len(workflow.steps) == 2

    def test_invalid_step_on_failure(self):
        workflow_dict = {
            "name": "bad",
            "steps": [{"name": "step1", "command": "test", "on_failure": "explode"}],
        }
        with pytest.raises(ValidationError):
            validate_workflow(workflow_dict)

    def test_missing_step_name(self):
        workflow_dict = {
            "steps": [{"command": "test"}],  # missing name
        }
        with pytest.raises(ValidationError):
            validate_workflow(workflow_dict)

    def test_missing_step_command(self):
        workflow_dict = {
            "steps": [{"name": "test"}],  # missing command
        }
        with pytest.raises(ValidationError):
            validate_workflow(workflow_dict)


# --- Workflow Engine Tests (Integration) ---


@pytest.fixture
def mock_context():
    """Create a mock DevCtl context for testing."""
    config = DevCtlConfig(
        profiles={
            "default": ProfileConfig(
                aws=AWSConfig(profile="test", region="us-east-1"),
            )
        }
    )
    return DevCtlContext(
        config=config,
        profile="default",
        output_format=OutputFormat.TABLE,
        verbose=0,
        quiet=True,  # Suppress output in tests
        dry_run=False,
        color=False,
    )


@pytest.fixture
def workflow_engine(mock_context):
    """Create a workflow engine for testing."""
    return WorkflowEngine(mock_context)


class TestWorkflowEngineTemplating:
    """Tests for Jinja2 template rendering in workflow engine."""

    def test_render_simple_variable(self, workflow_engine):
        workflow_engine._variables = {"name": "test-service"}
        result = workflow_engine._render_template("{{ name }}")
        assert result == "test-service"

    def test_render_multiple_variables(self, workflow_engine):
        workflow_engine._variables = {"cluster": "prod", "service": "api"}
        result = workflow_engine._render_template("{{ cluster }}-{{ service }}")
        assert result == "prod-api"

    def test_render_with_default_filter(self, workflow_engine):
        workflow_engine._variables = {}
        result = workflow_engine._render_template("{{ name | default('fallback') }}")
        assert result == "fallback"

    def test_render_params(self, workflow_engine):
        workflow_engine._variables = {"bucket": "my-bucket", "prefix": "logs"}
        params = {"bucket": "{{ bucket }}", "prefix": "{{ prefix }}/"}
        result = workflow_engine._render_params(params)
        assert result["bucket"] == "my-bucket"
        assert result["prefix"] == "logs/"

    def test_render_params_with_list(self, workflow_engine):
        workflow_engine._variables = {"env": "prod"}
        params = {"tags": ["deployment", "{{ env }}"]}
        result = workflow_engine._render_params(params)
        assert result["tags"] == ["deployment", "prod"]


class TestWorkflowEngineConditions:
    """Tests for condition evaluation in workflow engine."""

    def test_true_condition(self, workflow_engine):
        workflow_engine._variables = {"deploy": True}
        result = workflow_engine._evaluate_condition("{{ deploy }}")
        assert result is True

    def test_false_condition(self, workflow_engine):
        workflow_engine._variables = {"deploy": False}
        result = workflow_engine._evaluate_condition("{{ deploy }}")
        assert result is False

    def test_string_comparison(self, workflow_engine):
        workflow_engine._variables = {"environment": "production"}
        result = workflow_engine._evaluate_condition("'{{ environment }}' == 'production'")
        assert result is True

    def test_numeric_comparison(self, workflow_engine):
        workflow_engine._variables = {"replicas": 5}
        result = workflow_engine._evaluate_condition("{{ replicas }} > 3")
        assert result is True


class TestWorkflowEngineDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_does_not_execute(self, workflow_engine):
        workflow = WorkflowSchema(
            name="test",
            steps=[
                WorkflowStepSchema(name="dangerous", command="!rm -rf /"),
            ],
        )
        result = workflow_engine.run(workflow, dry_run=True)
        assert result["success"] is True
        assert result["steps"][0]["dry_run"] is True

    def test_dry_run_still_renders_templates(self, workflow_engine):
        workflow = WorkflowSchema(
            name="test",
            vars={"service": "api"},
            steps=[
                WorkflowStepSchema(
                    name="deploy",
                    command="aws ecs deploy",
                    params={"service": "{{ service }}"},
                ),
            ],
        )
        result = workflow_engine.run(workflow, dry_run=True)
        assert result["success"] is True


class TestWorkflowEngineVariables:
    """Tests for variable handling."""

    def test_default_vars_used(self, workflow_engine):
        workflow = WorkflowSchema(
            name="test",
            vars={"cluster": "default-cluster"},
            steps=[],
        )
        workflow_engine.run(workflow, dry_run=True)
        assert workflow_engine._variables["cluster"] == "default-cluster"

    def test_runtime_vars_override_defaults(self, workflow_engine):
        workflow = WorkflowSchema(
            name="test",
            vars={"cluster": "default-cluster"},
            steps=[],
        )
        workflow_engine.run(workflow, variables={"cluster": "prod-cluster"}, dry_run=True)
        assert workflow_engine._variables["cluster"] == "prod-cluster"


class TestWorkflowEngineFailureHandling:
    """Tests for on_failure behavior."""

    def test_continue_on_failure(self, workflow_engine, tmp_path):
        # Create a workflow that fails but continues
        workflow = WorkflowSchema(
            name="test",
            steps=[
                WorkflowStepSchema(
                    name="failing",
                    command="!/bin/sh -c 'exit 1'",
                    on_failure="continue",
                ),
                WorkflowStepSchema(
                    name="succeeding",
                    command="!/bin/sh -c 'exit 0'",
                ),
            ],
        )
        result = workflow_engine.run(workflow)
        # Second step should have run
        assert len(result["steps"]) == 2
        assert result["success"] is True  # Overall success because we continued

    def test_fail_stops_workflow(self, workflow_engine):
        workflow = WorkflowSchema(
            name="test",
            steps=[
                WorkflowStepSchema(
                    name="failing",
                    command="!/bin/sh -c 'exit 1'",
                    on_failure="fail",
                ),
                WorkflowStepSchema(
                    name="never-runs",
                    command="!echo hello",
                ),
            ],
        )
        result = workflow_engine.run(workflow)
        assert result["success"] is False
        assert result["failed_step"] == "failing"
        # Second step should not have run
        assert len(result["steps"]) == 1


class TestWorkflowEngineShellCommands:
    """Tests for shell command execution."""

    def test_shell_command_success(self, workflow_engine):
        workflow = WorkflowSchema(
            name="test",
            steps=[
                WorkflowStepSchema(name="echo", command="!echo hello"),
            ],
        )
        result = workflow_engine.run(workflow)
        assert result["success"] is True
        assert "hello" in result["steps"][0].get("stdout", "")

    def test_shell_command_failure(self, workflow_engine):
        workflow = WorkflowSchema(
            name="test",
            steps=[
                WorkflowStepSchema(name="fail", command="!/bin/sh -c 'exit 42'"),
            ],
        )
        result = workflow_engine.run(workflow)
        assert result["success"] is False
        assert result["steps"][0]["returncode"] == 42


class TestWorkflowEngineLoadWorkflow:
    """Tests for loading workflows from files."""

    def test_load_valid_workflow(self, workflow_engine, tmp_path):
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "name": "test-workflow",
                    "description": "A test",
                    "steps": [{"name": "step1", "command": "!echo test"}],
                }
            )
        )
        workflow = workflow_engine.load_workflow(str(workflow_file))
        assert workflow.name == "test-workflow"
        assert len(workflow.steps) == 1

    def test_load_invalid_yaml(self, workflow_engine, tmp_path):
        workflow_file = tmp_path / "bad.yaml"
        workflow_file.write_text("invalid: yaml: content: [")
        with pytest.raises(WorkflowError) as exc_info:
            workflow_engine.load_workflow(str(workflow_file))
        assert "Invalid YAML" in str(exc_info.value)

    def test_load_nonexistent_file(self, workflow_engine):
        with pytest.raises(WorkflowError):
            workflow_engine.load_workflow("/nonexistent/workflow.yaml")


class TestWorkflowEngineStepConditions:
    """Tests for conditional step execution."""

    def test_condition_true_runs_step(self, workflow_engine):
        workflow = WorkflowSchema(
            name="test",
            vars={"deploy": True},
            steps=[
                WorkflowStepSchema(
                    name="conditional",
                    command="!echo deployed",
                    condition="{{ deploy }}",
                ),
            ],
        )
        result = workflow_engine.run(workflow)
        assert result["success"] is True
        assert not result["steps"][0].get("skipped", False)

    def test_condition_false_skips_step(self, workflow_engine):
        workflow = WorkflowSchema(
            name="test",
            vars={"deploy": False},
            steps=[
                WorkflowStepSchema(
                    name="conditional",
                    command="!echo deployed",
                    condition="{{ deploy }}",
                ),
            ],
        )
        result = workflow_engine.run(workflow)
        assert result["success"] is True
        assert result["steps"][0].get("skipped", False) is True


# --- Workflow Template Tests (Integration) ---


class TestBuiltinWorkflowTemplates:
    """Tests for built-in workflow templates."""

    def get_templates_path(self):
        """Get path to workflow templates."""
        import devctl.workflows
        return Path(devctl.workflows.__file__).parent / "templates"

    def test_templates_directory_exists(self):
        templates_path = self.get_templates_path()
        assert templates_path.exists()
        assert templates_path.is_dir()

    def test_predictive_scaling_template_valid(self):
        template_path = self.get_templates_path() / "predictive-scaling.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "predictive-scaling"
            assert len(workflow.steps) > 0

    def test_update_predictive_scaling_template_valid(self):
        template_path = self.get_templates_path() / "update-predictive-scaling.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "update-predictive-scaling"

    def test_pipeline_template_valid(self):
        template_path = self.get_templates_path() / "predictive-scaling-pipeline.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "predictive-scaling-pipeline"

    def test_jira_standup_template_valid(self):
        template_path = self.get_templates_path() / "jira-standup.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "jira-standup"
            assert len(workflow.steps) == 4

    def test_jira_sprint_report_template_valid(self):
        template_path = self.get_templates_path() / "jira-sprint-report.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "jira-sprint-report"
            assert "board_id" in workflow.vars

    def test_jira_release_notes_template_valid(self):
        template_path = self.get_templates_path() / "jira-release-notes.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "jira-release-notes"
            assert "project" in workflow.vars

    def test_jira_bug_triage_template_valid(self):
        template_path = self.get_templates_path() / "jira-bug-triage.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "jira-bug-triage"
            assert len(workflow.steps) == 6

    def test_jira_sprint_cleanup_template_valid(self):
        template_path = self.get_templates_path() / "jira-sprint-cleanup.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "jira-sprint-cleanup"

    def test_jira_deployment_ticket_template_valid(self):
        template_path = self.get_templates_path() / "jira-deployment-ticket.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "jira-deployment-ticket"
            assert "environment" in workflow.vars

    def test_incident_response_template_valid(self):
        template_path = self.get_templates_path() / "incident-response.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "incident-response"
            assert "title" in workflow.vars
            assert "severity" in workflow.vars
            assert "service" in workflow.vars
            assert len(workflow.steps) >= 5

    def test_deploy_with_jira_template_valid(self):
        template_path = self.get_templates_path() / "deploy-with-jira.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "deploy-with-jira"
            assert "app_name" in workflow.vars
            assert "jira_ticket" in workflow.vars
            assert len(workflow.steps) >= 8

    def test_daily_ops_report_template_valid(self):
        template_path = self.get_templates_path() / "daily-ops-report.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "daily-ops-report"
            assert "slack_channel" in workflow.vars
            assert len(workflow.steps) >= 6

    def test_pr_to_deploy_template_valid(self):
        template_path = self.get_templates_path() / "pr-to-deploy.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "pr-to-deploy"
            assert "pr_number" in workflow.vars
            assert "repo" in workflow.vars
            assert "argocd_app" in workflow.vars
            assert len(workflow.steps) >= 10

    def test_rollback_notify_template_valid(self):
        template_path = self.get_templates_path() / "rollback-notify.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "rollback-notify"
            assert "app_name" in workflow.vars
            assert "reason" in workflow.vars
            assert len(workflow.steps) >= 6

    def test_weekly_cost_review_template_valid(self):
        template_path = self.get_templates_path() / "weekly-cost-review.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "weekly-cost-review"
            assert "slack_channel" in workflow.vars
            assert "savings_threshold" in workflow.vars
            assert len(workflow.steps) >= 10

    def test_oncall_handoff_template_valid(self):
        template_path = self.get_templates_path() / "oncall-handoff.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "oncall-handoff"
            assert "shift_hours" in workflow.vars
            assert "slack_channel" in workflow.vars
            assert len(workflow.steps) >= 8

    def test_access_review_quarterly_template_valid(self):
        template_path = self.get_templates_path() / "access-review-quarterly.yaml"
        if template_path.exists():
            with open(template_path) as f:
                workflow_dict = yaml.safe_load(f)
            workflow = validate_workflow(workflow_dict)
            assert workflow.name == "access-review-quarterly"
            assert "inactive_days" in workflow.vars
            assert "jira_project" in workflow.vars
            assert "confluence_space" in workflow.vars
            assert len(workflow.steps) >= 10
