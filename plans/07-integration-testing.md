# Integration Testing Framework

> **Status: ⬜ NOT STARTED**
>
> **Dependencies to add**: `pytest-benchmark`, `pact-python`, `pytest-xdist`, `memray`

Comprehensive integration testing with E2E AWS, contract testing, and performance benchmarks.

## Overview

Add four testing capabilities:
1. **End-to-End AWS testing** against real AWS sandbox account
2. **Workflow E2E tests** for complete workflow execution validation
3. **Contract testing** for external service APIs
4. **Performance benchmarks** for critical paths

---

## Architecture

```
tests/
├── unit/                    # Existing unit tests (fast, mocked)
├── integration/             # Moto-based integration (current)
├── e2e/                     # NEW: Real AWS E2E tests
│   ├── conftest.py          # E2E fixtures, AWS sandbox setup
│   ├── test_aws_e2e.py      # AWS command E2E tests
│   ├── test_workflows_e2e.py # Workflow execution E2E
│   └── markers.py           # pytest markers for E2E
├── contracts/               # NEW: Contract tests
│   ├── conftest.py
│   ├── test_aws_contracts.py
│   ├── test_grafana_contracts.py
│   └── pacts/               # Pact contract files
├── benchmarks/              # NEW: Performance tests
│   ├── conftest.py
│   ├── test_cli_performance.py
│   └── test_workflow_performance.py
└── conftest.py              # Shared fixtures
```

---

## 1. End-to-End AWS Testing

### Dependencies

```toml
[project.optional-dependencies]
test-e2e = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-timeout>=2.2.0",
    "pytest-xdist>=3.5.0",    # Parallel test execution
]
```

### Configuration

```yaml
# tests/e2e/config.yaml (or via env vars)
aws:
  region: us-east-1
  account_alias: devctl-sandbox
  resource_prefix: devctl-e2e-  # Prefix for created resources
  cleanup: true                  # Auto-cleanup after tests

safeguards:
  max_cost_per_run: 5.00        # USD limit per test run
  allowed_services: [s3, iam, cloudwatch, ecr]
  blocked_operations: [delete_bucket, terminate_instances]
```

### Markers

```python
# tests/e2e/markers.py
import pytest
import os

# Mark tests requiring real AWS
e2e_aws = pytest.mark.skipif(
    not os.getenv("DEVCTL_E2E_AWS"),
    reason="E2E AWS tests disabled (set DEVCTL_E2E_AWS=1)"
)

# Mark tests by cost tier
e2e_free = pytest.mark.e2e_free      # Free tier only (S3, IAM)
e2e_paid = pytest.mark.e2e_paid      # May incur costs (EKS, Forecast)
```

### Test Structure

```python
# tests/e2e/test_aws_e2e.py
import pytest
import uuid
from tests.e2e.markers import e2e_aws, e2e_free

@e2e_aws
@e2e_free
class TestS3E2E:
    """Real AWS S3 tests."""

    @pytest.fixture(autouse=True)
    def setup_bucket(self, e2e_aws_client):
        """Create test bucket, cleanup after."""
        bucket = f"devctl-e2e-{uuid.uuid4().hex[:8]}"
        e2e_aws_client.s3.create_bucket(Bucket=bucket)
        yield bucket
        e2e_aws_client.s3.delete_bucket(Bucket=bucket)

    def test_s3_ls_real(self, cli_runner, setup_bucket):
        result = cli_runner.invoke(cli, ["aws", "s3", "ls"])
        assert result.exit_code == 0
        assert setup_bucket in result.output

    def test_s3_size_real(self, cli_runner, setup_bucket):
        result = cli_runner.invoke(cli, ["aws", "s3", "size", setup_bucket])
        assert result.exit_code == 0
```

### Fixtures

```python
# tests/e2e/conftest.py
import os
import pytest
import boto3

@pytest.fixture(scope="session")
def e2e_aws_session():
    """Create AWS session for E2E tests."""
    if not os.getenv("DEVCTL_E2E_AWS"):
        pytest.skip("E2E tests disabled")

    profile = os.getenv("DEVCTL_E2E_AWS_PROFILE", "devctl-sandbox")
    return boto3.Session(profile_name=profile)

@pytest.fixture(scope="session")
def e2e_aws_client(e2e_aws_session):
    """Factory for AWS clients."""
    class AWSClients:
        def __init__(self, session):
            self._session = session
            self._clients = {}

        def __getattr__(self, name):
            if name not in self._clients:
                self._clients[name] = self._session.client(name)
            return self._clients[name]

    return AWSClients(e2e_aws_session)

@pytest.fixture(scope="session", autouse=True)
def e2e_cleanup(e2e_aws_client):
    """Cleanup any orphaned resources after test session."""
    yield
    # Cleanup logic: delete resources with devctl-e2e- prefix
```

---

## 2. Workflow E2E Tests

### Test Scenarios

```python
# tests/e2e/test_workflows_e2e.py
import tempfile
from tests.e2e.markers import e2e_aws

@e2e_aws
class TestWorkflowE2E:
    """End-to-end workflow execution tests."""

    def test_multi_step_workflow_real(self, cli_runner, e2e_aws_client):
        """Test complete workflow with real AWS calls."""
        workflow = """
        name: e2e-test-workflow
        vars:
          bucket: devctl-e2e-test
        steps:
          - name: Create bucket
            command: "!aws s3 mb s3://{{ bucket }}"
          - name: List buckets
            command: aws s3 ls
          - name: Cleanup
            command: "!aws s3 rb s3://{{ bucket }}"
        """
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w") as f:
            f.write(workflow)
            f.flush()
            result = cli_runner.invoke(cli, ["workflow", "run", f.name])

        assert result.exit_code == 0
        assert "Create bucket" in result.output
        assert "List buckets" in result.output

    def test_parallel_workflow_real(self, cli_runner):
        """Test parallel execution with timing validation."""
        # Parallel steps should complete faster than sequential
        pass

    def test_workflow_failure_handling(self, cli_runner):
        """Test on_failure modes with real failures."""
        pass

    def test_workflow_variable_interpolation(self, cli_runner):
        """Test Jinja2 variable passing through steps."""
        pass

    def test_workflow_timeout_handling(self, cli_runner):
        """Test step timeout with real slow operations."""
        pass
```

### Workflow Validation Framework

```python
# src/devctl/testing/workflow_validator.py

from devctl.workflows.schema import WorkflowSchema
from devctl.workflows.engine import WorkflowEngine
from devctl.workflows.results import StepResult

class WorkflowValidator:
    """Validate workflow execution results."""

    def __init__(self, workflow_path: str):
        self.workflow = self._load_workflow(workflow_path)
        self.results: list[StepResult] = []

    def _load_workflow(self, path: str) -> WorkflowSchema:
        import yaml
        with open(path) as f:
            return WorkflowSchema.model_validate(yaml.safe_load(f))

    def execute(self, variables: dict = None) -> "WorkflowValidator":
        """Execute workflow and capture results."""
        engine = WorkflowEngine(context)
        self.results = engine.run(self.workflow, variables or {})
        return self

    def assert_all_succeeded(self) -> "WorkflowValidator":
        """Assert all steps succeeded."""
        failed = [r for r in self.results if not r.success]
        if failed:
            raise AssertionError(f"Steps failed: {[f.name for f in failed]}")
        return self

    def assert_step_output_contains(self, step: str, text: str) -> "WorkflowValidator":
        """Assert step output contains text."""
        result = self.get_step_result(step)
        assert text in (result.stdout or ""), f"'{text}' not in {step} output"
        return self

    def assert_step_completed_before(self, step1: str, step2: str) -> "WorkflowValidator":
        """Assert step1 completed before step2 started."""
        r1, r2 = self.get_step_result(step1), self.get_step_result(step2)
        assert r1.completed_at < r2.started_at
        return self

    def get_step_result(self, name: str) -> StepResult:
        """Get result for a specific step."""
        for result in self.results:
            if result.name == name:
                return result
        raise ValueError(f"No result for step: {name}")
```

---

## 3. Contract Testing

### Framework: Pact

```toml
[project.optional-dependencies]
test-contracts = [
    "pact-python>=2.0.0",
]
```

### AWS Contract Tests

```python
# tests/contracts/test_aws_contracts.py
"""
Contract tests verify that devctl's expectations of AWS APIs match reality.
These use recorded interactions, not live AWS calls.
"""
import pytest
from pact import Verifier

class TestAWSContracts:
    """Verify AWS API contracts."""

    def test_s3_list_buckets_contract(self):
        """Verify S3 ListBuckets response structure."""
        # Expected: {"Buckets": [{"Name": str, "CreationDate": datetime}]}
        pass

    def test_cost_explorer_contract(self):
        """Verify Cost Explorer GetCostAndUsage response."""
        pass

    def test_cloudwatch_alarms_contract(self):
        """Verify CloudWatch DescribeAlarms response."""
        pass
```

### External Service Contracts

```python
# tests/contracts/test_grafana_contracts.py
from pact import Consumer, Provider

class TestGrafanaContracts:
    """Contract tests for Grafana API."""

    @pytest.fixture
    def pact(self):
        return Consumer("devctl").has_pact_with(
            Provider("grafana"),
            pact_dir="tests/contracts/pacts"
        )

    def test_list_dashboards_contract(self, pact):
        pact.given("dashboards exist").upon_receiving(
            "a request to list dashboards"
        ).with_request(
            method="GET",
            path="/api/search",
            query={"type": "dash-db"}
        ).will_respond_with(
            status=200,
            body=[{"id": 1, "uid": "abc", "title": "Dashboard"}]
        )

        with pact:
            # Call devctl code that hits this endpoint
            pass

# Similar for: GitHub, PagerDuty, Jira, ArgoCD, Slack, Confluence
```

### Contract Registry

```yaml
# tests/contracts/registry.yaml
contracts:
  aws:
    s3:
      - list_buckets
      - get_bucket_location
      - list_objects_v2
    iam:
      - list_users
      - list_roles
    cost_explorer:
      - get_cost_and_usage
      - get_cost_forecast

  grafana:
    - search_dashboards
    - get_dashboard
    - create_annotation
    - list_datasources

  github:
    - list_pull_requests
    - get_pull_request
    - list_workflows

  pagerduty:
    - list_incidents
    - get_incident
    - list_services
```

---

## 4. Performance Benchmarks

### Dependencies

```toml
[project.optional-dependencies]
test-benchmarks = [
    "pytest-benchmark>=4.0.0",
    "memray>=1.0.0",           # Memory profiling
]
```

### CLI Performance

```python
# tests/benchmarks/test_cli_performance.py
import pytest
from click.testing import CliRunner
from devctl.cli import cli

class TestCLIPerformance:
    """Benchmark CLI startup and command execution."""

    @pytest.fixture
    def cli_runner(self):
        return CliRunner()

    def test_cli_startup_time(self, benchmark, cli_runner):
        """CLI should start in <100ms."""
        result = benchmark(cli_runner.invoke, cli, ["--version"])
        assert result.exit_code == 0
        # Benchmark plugin tracks timing automatically

    def test_help_generation(self, benchmark, cli_runner):
        """Help text generation should be fast."""
        benchmark(cli_runner.invoke, cli, ["--help"])

    def test_command_discovery(self, benchmark, cli_runner):
        """Command group loading should be fast."""
        benchmark(cli_runner.invoke, cli, ["aws", "--help"])
```

### Workflow Performance

```python
# tests/benchmarks/test_workflow_performance.py
import yaml
import pytest
from devctl.workflows.schema import WorkflowSchema

class TestWorkflowPerformance:
    """Benchmark workflow engine performance."""

    def test_workflow_parsing(self, benchmark):
        """Workflow YAML parsing should be fast."""
        workflow_yaml = """
        name: benchmark-test
        steps:
        """ + "\n".join([f"  - name: step{i}\n    command: '!echo {i}'" for i in range(100)])

        data = yaml.safe_load(workflow_yaml)
        benchmark(WorkflowSchema.model_validate, data)

    def test_parallel_executor_overhead(self, benchmark):
        """Parallel execution should have minimal overhead."""
        # Compare sequential vs parallel for independent steps
        pass

    def test_dependency_graph_resolution(self, benchmark):
        """DAG resolution should be O(V+E)."""
        # Benchmark with various graph sizes
        pass

    def test_jinja_template_rendering(self, benchmark):
        """Template rendering should be fast."""
        pass
```

### Memory Benchmarks

```python
# tests/benchmarks/test_memory.py
import pytest

@pytest.mark.memory
class TestMemoryUsage:
    """Memory usage benchmarks."""

    def test_large_workflow_memory(self):
        """Workflow with 1000 steps should use <100MB."""
        pass

    def test_parallel_execution_memory(self):
        """Parallel execution should not leak memory."""
        pass
```

---

## 5. CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yaml
name: Tests

on: [push, pull_request]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -m "not e2e and not benchmark" --cov

  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e ".[dev]"
      - run: pytest tests/integration/ --cov

  e2e:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    environment: aws-sandbox
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_E2E_ROLE }}
          aws-region: us-east-1
      - run: pip install -e ".[dev,test-e2e]"
      - run: pytest tests/e2e/ -m "e2e_free" --timeout=300
        env:
          DEVCTL_E2E_AWS: "1"

  benchmarks:
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[dev,test-benchmarks]"
      - run: pytest tests/benchmarks/ --benchmark-json=benchmark.json
      - uses: benchmark-action/github-action-benchmark@v1
        with:
          tool: pytest
          output-file-path: benchmark.json
```

---

## New Files to Create

| File | Description |
|------|-------------|
| `tests/e2e/__init__.py` | E2E test package |
| `tests/e2e/conftest.py` | E2E fixtures, AWS session management |
| `tests/e2e/markers.py` | pytest markers for E2E tests |
| `tests/e2e/config.py` | E2E configuration loading |
| `tests/e2e/test_aws_e2e.py` | AWS command E2E tests |
| `tests/e2e/test_workflows_e2e.py` | Workflow execution E2E tests |
| `tests/contracts/__init__.py` | Contract test package |
| `tests/contracts/conftest.py` | Pact fixtures |
| `tests/contracts/test_aws_contracts.py` | AWS API contracts |
| `tests/contracts/test_grafana_contracts.py` | Grafana API contracts |
| `tests/contracts/test_github_contracts.py` | GitHub API contracts |
| `tests/benchmarks/__init__.py` | Benchmark package |
| `tests/benchmarks/conftest.py` | Benchmark fixtures |
| `tests/benchmarks/test_cli_performance.py` | CLI benchmarks |
| `tests/benchmarks/test_workflow_performance.py` | Workflow benchmarks |
| `src/devctl/testing/__init__.py` | Testing utilities package |
| `src/devctl/testing/workflow_validator.py` | Workflow validation helpers |
| `.github/workflows/test.yaml` | Updated CI workflow |

---

## Files to Modify

| File | Changes |
|------|---------|
| `pyproject.toml` | Add test-e2e, test-contracts, test-benchmarks extras |
| `tests/conftest.py` | Add shared E2E fixtures, benchmark config |
| `pyproject.toml` [tool.pytest] | Add marker definitions |

---

## Implementation Order

1. **Foundation** - pytest markers, conftest updates, pyproject.toml deps
2. **E2E Infrastructure** - AWS session fixtures, cleanup, safeguards
3. **E2E AWS Tests** - S3, IAM, CloudWatch (free tier)
4. **Workflow E2E** - Multi-step, parallel, failure handling
5. **Performance Benchmarks** - CLI startup, workflow parsing
6. **Contract Tests** - AWS contracts, then external services
7. **CI/CD** - GitHub Actions workflow updates

---

## Key Decisions

1. **E2E AWS requires explicit opt-in** via `DEVCTL_E2E_AWS=1`
2. **Resources use prefix** `devctl-e2e-` for easy identification/cleanup
3. **Cost safeguards** prevent accidental expensive operations
4. **Contracts are recorded** not live-tested (faster, more reliable)
5. **Benchmarks run on every push** to detect regressions

---

## Running Tests

```bash
# Unit tests only (fast, mocked)
pytest tests/ -m "not e2e and not benchmark"

# Integration tests (moto-based)
pytest tests/test_aws_integration.py

# E2E tests (real AWS - requires credentials)
DEVCTL_E2E_AWS=1 pytest tests/e2e/ -m "e2e_free"

# Benchmarks
pytest tests/benchmarks/ --benchmark-only

# All free-tier E2E tests with timeout
DEVCTL_E2E_AWS=1 pytest tests/e2e/ -m "e2e_free" --timeout=300

# Contract tests
pytest tests/contracts/
```
