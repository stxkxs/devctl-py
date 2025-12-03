# AI Context for DevCtl

This document provides context for AI agents continuing development on this project.

## Project Overview

DevCtl is a Python CLI tool for unified DevOps operations across AWS, Grafana Cloud, and GitHub. It's built with Click framework and follows SRE best practices.

## Architecture Decisions

### Why Click over argparse/Typer?
- Battle-tested with excellent composability
- Explicit decorators make command structure clear
- Great support for nested command groups
- Rich ecosystem of plugins

### Why Rich for output?
- Professional terminal UX with tables, progress bars, syntax highlighting
- Easy integration with Click
- Handles terminal width and color support automatically

### Why Pydantic for config?
- Type-safe configuration with validation
- Automatic environment variable binding
- Clear error messages for config issues

### Why httpx over requests?
- Modern async-capable HTTP client
- Better typing support
- More intuitive API for streaming and timeouts

### Why src layout?
- Prevents import issues during development
- Standard for modern Python packages
- Clear separation between source and tests

## Key Components

### Configuration System (`src/devctl/config.py`)
- Hierarchical config: defaults → user config → project config → env vars → CLI flags
- Profiles for multi-environment support
- Pydantic models for type safety
- Special `from_env` value for secrets

### Context Object (`src/devctl/core/context.py`)
- Shared state across commands via Click's context mechanism
- Lazy-loaded clients (AWS, Grafana, GitHub)
- Output formatting and logging configuration
- Dry-run support

### Client Architecture (`src/devctl/clients/`)
- Factory pattern for AWS clients with session management
- HTTP clients for Grafana and GitHub APIs
- Error handling wrappers that convert to custom exceptions

### Command Structure
- Nested groups: `devctl aws s3 ls`, `devctl grafana dashboards list`
- Consistent options across commands (--dry-run, --output, etc.)
- Each command file is self-contained

### Workflow Engine (`src/devctl/workflows/`)
- YAML-defined workflows with Jinja2 templating
- Steps can be devctl commands or shell commands (prefixed with `!`)
- Variables passed via CLI or defined in workflow
- Conditional execution and failure handling
- Built-in templates for predictive scaling pipelines

### Predictive Scaling (`src/devctl/commands/aws/forecast.py`)
- ML-powered auto-scaling using AWS Forecast
- Integration with EKS/Karpenter for node scaling
- Commands: export-metrics, datasets, predictors, scaling
- Generates Karpenter NodePool manifests

## Code Patterns

### Adding a New Command
```python
# src/devctl/commands/aws/newservice.py
import click
from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError

@click.group()
@pass_context
def newservice(ctx: DevCtlContext) -> None:
    """NewService operations."""
    pass

@newservice.command("list")
@click.option("--filter", help="Filter by name")
@pass_context
def list_items(ctx: DevCtlContext, filter: str | None) -> None:
    """List items."""
    if ctx.dry_run:
        ctx.log_dry_run("list items", {"filter": filter})
        return

    try:
        client = ctx.aws.client("newservice")
        items = client.list_items()
        ctx.output.print_data(items, title="Items")
    except Exception as e:
        raise AWSError(f"Failed: {e}")
```

### Adding a New Client
```python
# src/devctl/clients/newclient.py
import httpx
from devctl.core.exceptions import DevCtlError

class NewClient:
    def __init__(self, config: NewConfig):
        self._config = config
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            # Initialize client
            pass
        return self._client

    def list_items(self) -> list[dict]:
        return self.client.get("/api/items").json()
```

## Testing Strategy

We follow the **Testing Trophy** approach (Kent C. Dodds), prioritizing integration tests as the sweet spot for confidence vs. cost.

### Test Distribution

| Level | Files | Count | Purpose |
|-------|-------|-------|---------|
| Static | pyproject.toml | - | ruff (linting), mypy (type checking) |
| Unit | test_output.py | ~19 | Pure functions: formatters, validators |
| **Integration** | test_workflows.py, test_aws_integration.py | ~59 | Workflow engine, AWS commands with moto |
| E2E | test_cli.py | ~11 | CLI wiring verification |

### Key Testing Principles

1. **Integration tests are the priority** - They test how units work together and give the most confidence
2. **Use moto for AWS** - Mock AWS services without hitting real APIs
3. **Test behavior, not implementation** - Focus on what commands do, not how they do it
4. **Keep tests fast** - All 122 tests run in ~1.5 seconds

### Test Files

```
tests/
├── conftest.py              # Shared fixtures
├── test_cli.py              # CLI wiring tests (E2E)
├── test_config.py           # Configuration tests
├── test_output.py           # Output formatting (Unit)
├── test_workflows.py        # Workflow engine (Integration)
└── test_aws_integration.py  # AWS commands with moto (Integration)
```

### Writing Tests

**Unit tests** for pure functions:
```python
def test_format_bytes():
    assert format_bytes(1024) == "1.0 KB"
```

**Integration tests** with moto for AWS:
```python
@mock_aws
def test_s3_ls_with_buckets(self, cli_runner):
    import boto3
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    result = cli_runner.invoke(cli, ["aws", "s3", "ls"])
    assert result.exit_code == 0
    assert "test-bucket" in result.output
```

**Workflow engine tests**:
```python
def test_dry_run_does_not_execute(self, workflow_engine):
    workflow = WorkflowSchema(
        name="test",
        steps=[WorkflowStepSchema(name="dangerous", command="!rm -rf /")],
    )
    result = workflow_engine.run(workflow, dry_run=True)
    assert result["success"] is True
    assert result["steps"][0]["dry_run"] is True
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src/devctl

# Specific file
pytest tests/test_workflows.py

# Verbose output
pytest -v
```

## Documentation

```
docs/
├── getting-started.md       # Installation, first commands
├── configuration.md         # Profiles, credentials, env vars
├── aws-commands.md          # Full AWS command reference
├── predictive-scaling.md    # Forecast + Karpenter guide
├── workflows.md             # Workflow engine docs
└── bedrock-ai.md            # Bedrock agents, batch, compare
```

## Common Tasks for Future Development

### Adding a New AWS Service
1. Create `src/devctl/commands/aws/newservice.py`
2. Add command group with `@click.group()`
3. Register in `src/devctl/commands/aws/__init__.py`
4. Use `ctx.aws.client("servicename")` for boto3 client
5. Add integration tests with moto in `tests/test_aws_integration.py`

### Adding a New Grafana Endpoint
1. Add method to `GrafanaClient` class
2. Create command in `src/devctl/commands/grafana/`
3. Handle errors consistently

### Adding a New Workflow Step Type
1. Modify `_execute_command` in workflow engine
2. Add new execution method
3. Update workflow schema if needed
4. Add tests in `test_workflows.py`

### Adding a New Workflow Template
1. Create YAML file in `src/devctl/workflows/templates/`
2. Include name, description, vars, steps
3. Add validation test in `TestBuiltinWorkflowTemplates`

## Configuration Reference

### Environment Variables
- `DEVCTL_AWS_PROFILE`, `AWS_PROFILE`
- `DEVCTL_AWS_REGION`, `AWS_REGION`, `AWS_DEFAULT_REGION`
- `DEVCTL_GRAFANA_API_KEY`, `GRAFANA_API_KEY`
- `DEVCTL_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`

### Config File Locations
1. `~/.devctl/config.yaml` - User defaults
2. `./devctl.yaml` - Project config
3. CLI `--config` flag - Explicit path

## Dependencies

Core:
- click>=8.1.0 - CLI framework
- boto3>=1.34.0 - AWS SDK
- pyyaml>=6.0 - YAML parsing
- rich>=13.0.0 - Terminal output
- httpx>=0.27.0 - HTTP client
- pydantic>=2.0.0 - Config validation
- jinja2>=3.1.0 - Template rendering

Dev:
- pytest>=8.0.0 - Testing
- pytest-cov>=4.0.0 - Coverage
- ruff>=0.3.0 - Linting/formatting
- mypy>=1.8.0 - Type checking
- moto[all]>=5.0.0 - AWS mocking

## Error Handling

Custom exceptions in `src/devctl/core/exceptions.py`:
- `DevCtlError` - Base exception
- `ConfigError` - Configuration issues
- `AWSError` - AWS API errors
- `GrafanaError` - Grafana API errors
- `GitHubError` - GitHub API errors
- `WorkflowError` - Workflow execution errors

## Next Steps / TODO

1. **EC2 Commands**: Add EC2 instance management
   - list, start, stop, terminate
   - SSH tunneling

2. **SSM Commands**: Parameter Store operations
   - get, set, list, delete

3. **Lambda Commands**: Function management
   - invoke, logs, deploy

4. **More Workflow Features**:
   - Parallel step execution
   - Step dependencies
   - Output capture between steps

5. **Plugin System**: Allow custom commands via plugins

6. **Shell Completion**: Add bash/zsh completion scripts

## Docker

The CLI can run in a container with all dependencies (AWS CLI v2, kubectl, helm).

### Build and Run
```bash
docker build -t devctl .
docker run --rm -v ~/.aws:/home/devctl/.aws:ro devctl aws iam whoami
```

### Container Features
- Multi-stage build (builder → runtime → development)
- Non-root user (devctl, UID 1000)
- Includes: AWS CLI v2, kubectl, helm, git, jq
- Entrypoint handles credential validation
- Read-only filesystem with tmpfs for /tmp

### Key Files
- `Dockerfile` - Multi-stage build with runtime and dev targets
- `docker/entrypoint.sh` - Credential validation, shell mode
- `docker-compose.yml` - Easy local usage
- `.dockerignore` - Build context optimization

## File Structure Summary

```
devctl-py/
├── pyproject.toml          # Package config
├── README.md               # User docs
├── AI_CONTEXT.md           # This file
├── Dockerfile              # Container build
├── docker-compose.yml      # Compose config
├── docker/
│   └── entrypoint.sh       # Container entrypoint
├── config.example.yaml     # Config template
├── .env.example            # Env var template
├── docs/                   # Documentation
│   ├── getting-started.md
│   ├── configuration.md
│   ├── aws-commands.md
│   ├── predictive-scaling.md
│   ├── workflows.md
│   ├── bedrock-ai.md
│   └── docker.md
├── src/devctl/
│   ├── __init__.py         # Version
│   ├── __main__.py         # Module entry
│   ├── cli.py              # Main CLI
│   ├── config.py           # Config management
│   ├── core/               # Shared utilities
│   ├── clients/            # API clients
│   ├── commands/           # CLI commands
│   │   ├── aws/            # AWS commands
│   │   │   ├── forecast.py # Predictive scaling
│   │   │   ├── bedrock.py  # AI/ML operations
│   │   │   └── ...
│   │   ├── grafana/        # Grafana commands
│   │   ├── github/         # GitHub commands
│   │   ├── ops/            # DevOps commands
│   │   └── workflow.py     # Workflow commands
│   └── workflows/          # Workflow engine
│       ├── engine.py       # Execution engine
│       ├── schema.py       # Validation
│       └── templates/      # Built-in templates
└── tests/                  # Test files
    ├── conftest.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_output.py
    ├── test_workflows.py
    └── test_aws_integration.py
```
