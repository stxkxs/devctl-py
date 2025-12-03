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

## Testing Approach

- Unit tests with pytest
- AWS mocking with moto
- HTTP mocking with respx or pytest-httpx
- Fixtures in conftest.py for common setup

## Common Tasks for Future Development

### Adding a New AWS Service
1. Create `src/devctl/commands/aws/newservice.py`
2. Add command group with `@click.group()`
3. Register in `src/devctl/commands/aws/__init__.py`
4. Use `ctx.aws.client("servicename")` for boto3 client

### Adding a New Grafana Endpoint
1. Add method to `GrafanaClient` class
2. Create command in `src/devctl/commands/grafana/`
3. Handle errors consistently

### Adding a New Workflow Step Type
1. Modify `_execute_command` in workflow engine
2. Add new execution method
3. Update workflow schema if needed

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
- ruff>=0.3.0 - Linting/formatting
- mypy>=1.8.0 - Type checking
- moto>=5.0.0 - AWS mocking

## Error Handling

Custom exceptions in `src/devctl/core/exceptions.py`:
- `DevCtlError` - Base exception
- `ConfigError` - Configuration issues
- `AWSError` - AWS API errors
- `GrafanaError` - Grafana API errors
- `GitHubError` - GitHub API errors
- `WorkflowError` - Workflow execution errors

## Next Steps / TODO

1. **Tests**: Add comprehensive test coverage
   - Unit tests for each command
   - Integration tests with mocked services
   - Workflow engine tests

2. **EC2 Commands**: Add EC2 instance management
   - list, start, stop, terminate
   - SSH tunneling

3. **SSM Commands**: Parameter Store operations
   - get, set, list, delete

4. **Lambda Commands**: Function management
   - invoke, logs, deploy

5. **More Workflow Features**:
   - Parallel step execution
   - Step dependencies
   - Output capture between steps

6. **Plugin System**: Allow custom commands via plugins

7. **Shell Completion**: Add bash/zsh completion scripts

## File Structure Summary

```
devctl-py/
├── pyproject.toml          # Package config
├── README.md               # User docs
├── AI_CONTEXT.md           # This file
├── config.example.yaml     # Config template
├── .env.example            # Env var template
├── src/devctl/
│   ├── __init__.py         # Version
│   ├── __main__.py         # Module entry
│   ├── cli.py              # Main CLI
│   ├── config.py           # Config management
│   ├── core/               # Shared utilities
│   ├── clients/            # API clients
│   ├── commands/           # CLI commands
│   │   ├── aws/            # AWS commands
│   │   ├── grafana/        # Grafana commands
│   │   ├── github/         # GitHub commands
│   │   ├── ops/            # DevOps commands
│   │   └── workflow.py     # Workflow commands
│   └── workflows/          # Workflow engine
└── tests/                  # Test files
```
