# Web Dashboard

Lightweight web UI complementing the CLI.

## Stack

- **Backend**: FastAPI (matches existing pydantic/httpx usage)
- **Frontend**: HTMX + Jinja2 (no build step, server-side rendering)
- **Styling**: TailwindCSS CDN (no build required)

## CLI Command

```bash
# Start web dashboard
devctl serve [--host 0.0.0.0] [--port 8080]

# With options
devctl serve --host 0.0.0.0 --port 8080 --no-auth

# Generate API key
devctl serve --generate-key

# Development mode with auto-reload
devctl serve --reload
```

---

## Views

### 1. Dashboard (Home)
- Overview with key metrics
- Recent workflow executions
- Active alerts
- Quick actions

### 2. Workflows
- List available workflows
- Execute workflows with variable forms
- Real-time execution progress (SSE)
- Execution history

### 3. Command History
- Recent commands with output
- Search and filter
- Re-execute commands
- Export history

### 4. Health Overview
- Datasource status (Grafana)
- AWS connectivity
- Kubernetes cluster status
- PagerDuty/Slack/GitHub connectivity

### 5. Cost Dashboard
- MTD spend widget
- Top services chart
- Cost anomalies
- Unused resources

---

## API Structure

```
/api/v1/
  /health                       GET  - Overall health status
  /config                       GET  - Current configuration (sanitized)

  /workflows/
    /                           GET  - List available workflows
    /templates                  GET  - List built-in templates
    /{name}                     GET  - Get workflow details
    /{name}/run                 POST - Execute workflow
    /executions                 GET  - List past executions
    /executions/{id}            GET  - Get execution details
    /executions/{id}/stream     GET  - SSE stream for live updates

  /commands/
    /execute                    POST - Execute devctl command
    /history                    GET  - Get command history
    /groups                     GET  - List command groups

  /health/
    /services                   GET  - All service health
    /datasources                GET  - Grafana datasource health
    /aws                        GET  - AWS connectivity
    /k8s                        GET  - Kubernetes connectivity

  /cost/
    /summary                    GET  - Cost summary (cached)
    /by-service                 GET  - Cost by service
    /forecast                   GET  - Cost forecast
    /anomalies                  GET  - Cost anomalies
    /unused                     GET  - Unused resources
```

---

## New Files Structure

### Web Module: `src/devctl/web/`

```
src/devctl/web/
├── __init__.py
├── app.py                      # FastAPI application factory
├── config.py                   # WebConfig
├── dependencies.py             # FastAPI dependencies
├── middleware/
│   ├── __init__.py
│   └── auth.py                 # Authentication middleware
├── routes/
│   ├── __init__.py
│   ├── dashboard.py            # Dashboard views
│   ├── workflows.py            # Workflow views
│   ├── history.py              # History views
│   ├── health.py               # Health views
│   ├── cost.py                 # Cost views
│   └── api/
│       ├── __init__.py
│       ├── workflows.py        # Workflow REST API
│       ├── commands.py         # Command execution API
│       ├── health.py           # Health check API
│       └── cost.py             # Cost data API
├── services/
│   ├── __init__.py
│   ├── workflow_service.py     # Workflow business logic
│   ├── history_service.py      # Command history
│   └── health_service.py       # Aggregated health checks
├── templates/
│   ├── base.html               # Base template with navigation
│   ├── dashboard.html          # Main dashboard
│   ├── workflows/
│   │   ├── list.html
│   │   ├── detail.html
│   │   └── run.html
│   ├── history/
│   │   └── list.html
│   ├── health/
│   │   └── overview.html
│   └── cost/
│       └── dashboard.html
└── static/
    └── styles.css              # Custom CSS overrides
```

### CLI Command
- `src/devctl/commands/serve.py`

---

## Core Implementation

### 1. FastAPI Application

```python
# src/devctl/web/app.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

def create_app(config: WebConfig) -> FastAPI:
    app = FastAPI(
        title="DevCtl Dashboard",
        version="1.0.0",
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Setup templates
    templates = Jinja2Templates(directory="templates")

    # Add middleware
    if config.auth_method != "none":
        app.add_middleware(AuthMiddleware, config=config)

    # Include routers
    app.include_router(dashboard_router)
    app.include_router(workflow_router, prefix="/workflows")
    app.include_router(api_router, prefix="/api/v1")

    return app
```

### 2. Authentication Middleware

```python
# src/devctl/web/middleware/auth.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: WebConfig):
        super().__init__(app)
        self.config = config
        self.api_key = config.get_api_key()

    async def dispatch(self, request, call_next):
        # Skip auth for health check
        if request.url.path == "/health":
            return await call_next(request)

        if self.config.auth_method == "api_key":
            key = request.headers.get("X-API-Key") or \
                  request.query_params.get("api_key")
            if key != self.api_key:
                return JSONResponse(
                    {"error": "Unauthorized"},
                    status_code=401
                )

        elif self.config.auth_method == "basic":
            # Validate basic auth
            pass

        return await call_next(request)
```

### 3. Workflow Execution with SSE

```python
# src/devctl/web/routes/api/workflows.py

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.post("/{name}/run")
async def run_workflow(name: str, variables: dict = {}):
    """Execute workflow and return execution ID."""
    execution_id = str(uuid.uuid4())

    # Start workflow in background
    asyncio.create_task(
        execute_workflow(execution_id, name, variables)
    )

    return {"execution_id": execution_id}

@router.get("/executions/{id}/stream")
async def stream_execution(id: str):
    """SSE stream for workflow execution progress."""

    async def event_generator():
        async for event in get_execution_events(id):
            yield {
                "event": event.type,
                "data": json.dumps(event.data)
            }

    return EventSourceResponse(event_generator())
```

### 4. HTMX Templates

```html
<!-- templates/workflows/run.html -->
{% extends "base.html" %}

{% block content %}
<div class="container mx-auto p-4">
    <h1 class="text-2xl font-bold mb-4">Run Workflow: {{ workflow.name }}</h1>

    <form hx-post="/api/v1/workflows/{{ workflow.name }}/run"
          hx-trigger="submit"
          hx-target="#execution-result">

        {% for var_name, var_default in workflow.vars.items() %}
        <div class="mb-4">
            <label class="block text-sm font-medium">{{ var_name }}</label>
            <input type="text"
                   name="{{ var_name }}"
                   value="{{ var_default }}"
                   class="mt-1 block w-full rounded border-gray-300">
        </div>
        {% endfor %}

        <button type="submit"
                class="bg-blue-500 text-white px-4 py-2 rounded">
            Run Workflow
        </button>
    </form>

    <div id="execution-result" class="mt-8">
        <!-- Results injected here via HTMX -->
    </div>
</div>
{% endblock %}
```

### 5. Serve Command

```python
# src/devctl/commands/serve.py

import click
import uvicorn
import secrets

@click.command()
@click.option('--host', default='127.0.0.1')
@click.option('--port', default=8080, type=int)
@click.option('--no-auth', is_flag=True)
@click.option('--reload', is_flag=True)
@click.option('--generate-key', is_flag=True)
def serve(host: str, port: int, no_auth: bool, reload: bool, generate_key: bool):
    """Start web dashboard."""

    if generate_key:
        key = secrets.token_urlsafe(32)
        click.echo(f"Generated API key: {key}")
        click.echo("Add to config or set DEVCTL_WEB_API_KEY environment variable")
        return

    from devctl.web.app import create_app
    from devctl.config import load_config

    config = load_config()
    if no_auth:
        config.web.auth_method = "none"

    app = create_app(config.web)

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
    )
```

---

## Configuration

Add to `~/.devctl/config.yaml`:

```yaml
web:
  host: "127.0.0.1"
  port: 8080
  auth_method: api_key  # api_key, basic, none
  api_key: "from_env"   # DEVCTL_WEB_API_KEY
  basic_users:
    admin: "hashed_password"
  cors_origins: []
  session_secret: "from_env"  # DEVCTL_SESSION_SECRET
```

### Config Schema

```python
class WebConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080
    auth_method: str = "api_key"
    api_key: str | None = None
    basic_users: dict[str, str] = Field(default_factory=dict)
    cors_origins: list[str] = Field(default_factory=list)
    session_secret: str | None = None

    def get_api_key(self) -> str | None:
        if self.api_key == "from_env" or self.api_key is None:
            return os.environ.get("DEVCTL_WEB_API_KEY")
        return self.api_key
```

---

## New Dependencies

```toml
[project.optional-dependencies]
web = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "jinja2>=3.1.0",           # Already a dependency
    "python-multipart>=0.0.6",  # For form handling
    "sse-starlette>=1.6.0",     # For SSE support
]
```

---

## Docker Support

```dockerfile
# Dockerfile addition
FROM runtime AS web

# Install web dependencies
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] python-multipart sse-starlette

# Expose web port
EXPOSE 8080

# Override entrypoint for web mode
ENTRYPOINT ["/usr/bin/tini", "--", "devctl", "serve"]
CMD ["--host", "0.0.0.0", "--port", "8080"]
```

### Docker Compose

```yaml
version: "3.8"
services:
  devctl-web:
    build:
      context: .
      target: web
    ports:
      - "8080:8080"
    volumes:
      - ~/.aws:/home/devctl/.aws:ro
      - ~/.kube:/home/devctl/.kube:ro
      - ~/.devctl:/home/devctl/.devctl
    environment:
      - DEVCTL_WEB_API_KEY=${DEVCTL_WEB_API_KEY}
      - GRAFANA_API_KEY=${GRAFANA_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
```

---

## Files to Modify

- `src/devctl/cli.py` - Register serve command
- `src/devctl/config.py` - Add WebConfig

---

## Implementation Order

1. **FastAPI app with serve command** - Basic skeleton
2. **Authentication middleware** - API key auth
3. **Health overview page** - Datasource status
4. **Workflow list/execute** - Core functionality
5. **Command history** - Tracking and replay
6. **Cost dashboard** - Widgets and charts
7. **Docker support** - Containerization

---

## Design Principles

1. **CLI-First**: Dashboard visualizes CLI data, never bypasses CLI
2. **Lightweight**: Minimal dependencies, no build step, fast startup
3. **Secure by Default**: Auth required, localhost binding
4. **Progressive Enhancement**: Works without JavaScript (HTMX)
5. **Familiar Patterns**: Follow existing devctl conventions

---

## Key Integrations

- `src/devctl/core/context.py` - DevCtlContext for request context
- `src/devctl/workflows/engine.py` - WorkflowEngine for execution
- `src/devctl/commands/ops/health.py` - Health check patterns
- `src/devctl/commands/aws/cost.py` - Cost data
