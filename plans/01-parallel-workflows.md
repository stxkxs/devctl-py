# Parallel Workflow Execution

Extend workflow engine with parallel step execution.

## Goal

Add parallel step execution to the workflow engine while maintaining backward compatibility with existing sequential workflows.

## Syntax Option 1: Parallel Blocks

```yaml
steps:
  - name: Validate
    command: "!echo 'validating'"

  - parallel:
      name: Deploy all services
      on_failure: fail_all  # or continue, complete_running
      timeout: 600
      steps:
        - name: Deploy API
          command: argocd apps sync
          params: {app: api}
        - name: Deploy Worker
          command: argocd apps sync
          params: {app: worker}
        - name: Deploy Web
          command: argocd apps sync
          params: {app: web}

  - name: Verify
    command: k8s pods list
```

## Syntax Option 2: Dependencies (DAG)

```yaml
steps:
  - name: checkout
    command: "!git checkout main"

  - name: build-backend
    command: "!docker build backend"
    depends_on: [checkout]

  - name: build-frontend
    command: "!docker build frontend"
    depends_on: [checkout]  # Runs parallel with build-backend

  - name: deploy
    depends_on: [build-backend, build-frontend]  # Waits for both
```

## Global Config

```yaml
parallel:
  max_concurrent: 10
  rate_limit: 5.0  # steps/second
  fail_fast: true
```

## Schema Changes

Modify `src/devctl/workflows/schema.py`:

```python
class ParallelConfigSchema(BaseModel):
    max_concurrent: int = 10
    rate_limit: float | None = None
    fail_fast: bool = True

class ParallelBlockSchema(BaseModel):
    name: str | None = None
    steps: list["WorkflowStepSchema"]
    on_failure: Literal["fail_all", "continue", "complete_running"] = "fail_all"
    timeout: int | None = None
    max_concurrent: int | None = None

class WorkflowStepSchema(BaseModel):
    # ... existing fields ...
    parallel: ParallelBlockSchema | None = None  # NEW
    depends_on: list[str] = Field(default_factory=list)  # NEW
```

## New Files to Create

### 1. `src/devctl/workflows/parallel.py` - ParallelExecutor

```python
class ParallelExecutor:
    def __init__(self, engine: "WorkflowEngine", config: ParallelConfigSchema):
        self.engine = engine
        self.semaphore = asyncio.Semaphore(config.max_concurrent)
        self.rate_limiter = RateLimiter(config.rate_limit) if config.rate_limit else None
        self.fail_fast = config.fail_fast

    async def execute_parallel_block(self, block: ParallelBlockSchema, ...) -> ParallelBlockResult:
        """Run steps concurrently."""
        pass

    async def execute_dag(self, graph: DependencyGraph, ...) -> dict[str, StepResult]:
        """Execute based on dependency graph."""
        pass
```

### 2. `src/devctl/workflows/graph.py` - DependencyGraph

```python
class DependencyGraph:
    def __init__(self, steps: list[WorkflowStepSchema]):
        self.steps = {s.name: s for s in steps}
        self.dependencies: dict[str, set[str]] = {}
        self.dependents: dict[str, set[str]] = {}

    def validate(self) -> None:
        """Check for cycles and missing dependencies."""
        pass

    def get_ready_steps(self, completed: set[str]) -> list[str]:
        """Return steps with satisfied deps."""
        pass

    def topological_sort(self) -> list[list[str]]:
        """Return execution layers."""
        pass
```

### 3. `src/devctl/workflows/results.py` - Result dataclasses

```python
@dataclass
class StepResult:
    name: str
    success: bool
    skipped: bool = False
    error: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration: float = 0.0

@dataclass
class ParallelBlockResult:
    name: str | None
    success: bool
    steps: list[StepResult]
    failed_count: int
    succeeded_count: int
```

## Files to Modify

### 1. `src/devctl/workflows/schema.py`
- Add ParallelConfigSchema, ParallelBlockSchema
- Extend WorkflowStepSchema with parallel, depends_on

### 2. `src/devctl/workflows/engine.py`
- Add parallel execution path in `run()`
- Detect parallel workflows and delegate to ParallelExecutor
- Keep sequential path for backward compatibility

### 3. `src/devctl/core/exceptions.py`
- Add ParallelExecutionError, DependencyCycleError

## Error Handling

| Mode | Behavior |
|------|----------|
| `fail_all` | Cancel running steps, fail immediately |
| `continue` | Complete all, aggregate failures |
| `complete_running` | Stop queuing, wait for running |

## Progress Display

Use Rich Live display:

```
Parallel Execution: Deploy all services
+------------------+--------+----------+
| Step             | Status | Duration |
+------------------+--------+----------+
| Deploy API       | [OK]   | 12.3s    |
| Deploy Worker    | [...]  | 8.5s     |
| Deploy Web       | [FAIL] | 5.2s     |
+------------------+--------+----------+
```

## Tests to Add

Create `tests/test_parallel_workflows.py`:
- All steps succeed
- One fails with fail_all
- One fails with continue
- Timeout handling
- Cycle detection
- Max concurrent limit
- Rate limiting

## Implementation Order

1. Schema changes (ParallelBlockSchema, etc.)
2. DependencyGraph with cycle detection
3. ParallelExecutor with basic execution
4. Error handling modes
5. Progress tracking
6. Tests

## Key Integrations

- `src/devctl/core/async_utils.py` - RateLimiter, gather_with_concurrency
- `src/devctl/core/output.py` - Rich progress display
