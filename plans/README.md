# DevCtl Extension Plans

This directory contains implementation plans for extending devctl-py.

## Status Overview

| Plan | Status | Description |
|------|--------|-------------|
| [01-parallel-workflows](01-parallel-workflows.md) | ✅ Complete | Parallel step execution with DAG support |
| [02-developer-experience](02-developer-experience.md) | 🟡 Partial | Command suggestions, progress indicators done |
| [03-cost-intelligence](03-cost-intelligence.md) | 🟡 Partial | Tagging, budget commands done |
| [04-ai-features](04-ai-features.md) | 🟡 Partial | ask, explain-anomaly, review-iac done |
| [05-event-driven-automation](05-event-driven-automation.md) | ⬜ Not Started | Webhook daemon, scheduled triggers |
| [06-web-dashboard](06-web-dashboard.md) | ⬜ Not Started | FastAPI web UI |

## Implemented Features (December 2024)

### Phase 1: Core Features

**Parallel Workflows** (`src/devctl/workflows/`)
- `parallel.py` - ParallelExecutor for concurrent execution
- `graph.py` - DependencyGraph with cycle detection
- `results.py` - StepResult, ParallelBlockResult
- Schema updates for `parallel` blocks and `depends_on`

**Developer Experience** (`src/devctl/core/`)
- `suggestions.py` - "Did you mean?" command suggestions
- `progress.py` - ProgressManager, StepProgress, spinners

### Phase 2: Cost Intelligence

**Tagging** (`src/devctl/commands/aws/tagging.py`)
- `devctl aws tagging audit` - Audit required tags
- `devctl aws tagging report` - Tag usage report
- `devctl aws tagging untagged` - Find untagged resources

**Budget** (`src/devctl/commands/aws/budget.py`)
- `devctl aws budget list` - List budgets
- `devctl aws budget status` - Budget health summary
- `devctl aws budget create` - Create with alerts
- `devctl aws budget forecast` - Budget forecasts

**Cost by Tag** (added to `devctl aws cost`)
- `devctl aws cost by-tag` - Costs by any tag
- `devctl aws cost by-team` - Costs by team
- `devctl aws cost by-project` - Costs by project

### Phase 3: AI Features

**AI Commands** (`src/devctl/commands/ai/`)
- `devctl ai ask` - Natural language to commands
- `devctl ai explain-anomaly` - AI cost analysis
- `devctl ai review-iac` - Terraform/K8s security review

## Remaining Work

### Developer Experience (02)
- Shell completions (bash/zsh/fish)
- Configuration wizard (`devctl setup`)
- Interactive mode / REPL
- Command history & favorites

### Cost Intelligence (03)
- Cross-service optimization (`devctl aws optimize`)
- Cost attribution reports
- FinOps workflows

### AI Features (04)
- `ai generate-runbook` - Auto-generate runbooks
- `ai incident-analyze` - Multi-source correlation

### Event-Driven Automation (05)
**New dependencies needed**: `starlette`, `uvicorn`, `apscheduler`

Files to create:
- `src/devctl/events/daemon.py`
- `src/devctl/events/server.py`
- `src/devctl/events/scheduler.py`
- `src/devctl/events/router.py`
- `src/devctl/events/handlers/`
- `src/devctl/commands/events.py`

### Web Dashboard (06)
**New dependencies needed**: `fastapi`, `uvicorn[standard]`, `python-multipart`, `sse-starlette`

Files to create:
- `src/devctl/web/app.py`
- `src/devctl/web/routes/`
- `src/devctl/web/templates/`
- `src/devctl/commands/serve.py`

## Quick Start for New Session

To continue implementation:

```bash
# Check current test status
pytest --tb=short -q

# View specific plan
cat plans/05-event-driven-automation.md

# Check what's implemented
devctl --help
devctl aws --help
devctl ai --help
```

## Test Coverage

- `tests/test_parallel_workflows.py` - 24 tests
- `tests/test_suggestions.py` - 15 tests
- `tests/test_progress.py` - 18 tests

All tests pass (260 total).
