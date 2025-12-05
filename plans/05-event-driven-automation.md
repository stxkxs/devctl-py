# Event-Driven Automation

Daemon mode with webhook server for automated workflow triggers.

## Architecture Overview

```
devctl events daemon [--port 8080]
  ├── Webhook server (Starlette/ASGI)
  │   ├── /webhooks/cloudwatch
  │   ├── /webhooks/grafana
  │   ├── /webhooks/github
  │   └── /webhooks/pagerduty
  ├── Event handlers
  │   └── Parse, validate, normalize events
  ├── Scheduler (APScheduler)
  │   └── Cron-based triggers
  ├── Router
  │   └── Match events to triggers, evaluate conditions
  └── Workflow dispatcher
      └── Execute matched workflows
```

---

## CLI Commands

```bash
# Start event daemon
devctl events daemon [--config events.yaml] [--port 8080]

# List configured triggers
devctl events triggers list

# Test event routing without executing
devctl events test --source github --payload webhook.json

# View event history
devctl events history [--source cloudwatch] [--since 1h] [--status failed]

# View specific event
devctl events show <event-id>

# Replay failed event
devctl events replay <event-id>

# Validate trigger configuration
devctl events validate [triggers.yaml]
```

---

## Configuration Schema

Add to `devctl.yaml`:

```yaml
events:
  enabled: true

  server:
    host: "0.0.0.0"
    port: 8080
    workers: 4

  store:
    type: "sqlite"  # or "postgresql"
    path: "~/.devctl/events.db"
    retention_days: 30

  deduplication:
    enabled: true
    window_seconds: 300

  sources:
    cloudwatch:
      enabled: true
      sns_topic_arn: "arn:aws:sns:us-east-1:123456789:devctl-events"

    grafana:
      enabled: true

    github:
      enabled: true
      webhook_secret: "from_env"  # DEVCTL_GITHUB_WEBHOOK_SECRET

    pagerduty:
      enabled: true

    scheduler:
      enabled: true

  triggers:
    - name: "cpu-alarm-response"
      source: cloudwatch
      event_type: alarm
      conditions:
        alarm_name_pattern: ".*-cpu-high"
        new_state: "ALARM"
      workflow: incident-response.yaml
      variables:
        title: "{{ event.alarm_name }}"
        severity: "p2"
        service: "{{ event.dimensions.get('AutoScalingGroupName', 'unknown') }}"

    - name: "grafana-critical-alert"
      source: grafana
      event_type: alert
      conditions:
        status: "firing"
        labels:
          severity: "critical"
      workflow: incident-response.yaml
      variables:
        title: "{{ event.labels.alertname }}"
        severity: "{{ event.labels.severity }}"

    - name: "github-deploy-on-merge"
      source: github
      event_type: pull_request
      conditions:
        action: "closed"
        merged: true
        base_branch: "main"
      workflow: deploy-with-jira.yaml
      variables:
        repo: "{{ event.repository.name }}"
        version: "{{ event.pull_request.head.sha[:8] }}"

    - name: "daily-cost-report"
      source: scheduler
      schedule: "0 8 * * 1-5"  # 8 AM weekdays
      workflow: daily-ops-report.yaml
      variables:
        report_type: "cost"
```

---

## New Files Structure

### Events Module: `src/devctl/events/`

```
src/devctl/events/
├── __init__.py          # EventDaemon, start_daemon()
├── daemon.py            # Main daemon loop, lifecycle, signal handling
├── server.py            # ASGI webhook server (Starlette)
├── scheduler.py         # Cron-based scheduler (APScheduler)
├── router.py            # Event-to-workflow routing, condition matching
├── store.py             # Event persistence (SQLite/PostgreSQL)
├── models.py            # Event, Trigger, ExecutionRecord dataclasses
└── handlers/
    ├── __init__.py      # Handler registry
    ├── base.py          # BaseEventHandler abstract class
    ├── cloudwatch.py    # CloudWatch alarm parsing
    ├── grafana.py       # Grafana alert parsing
    ├── github.py        # GitHub webhook parsing + signature validation
    └── pagerduty.py     # PagerDuty webhook parsing
```

### CLI Command
- `src/devctl/commands/events.py`

---

## Core Components

### 1. Event Daemon

```python
# src/devctl/events/daemon.py

class EventDaemon:
    def __init__(self, config: EventsConfig):
        self.config = config
        self.server = WebhookServer(config.server)
        self.scheduler = EventScheduler(config.sources.scheduler)
        self.router = EventRouter(config.triggers)
        self.store = EventStore(config.store)
        self._shutdown = asyncio.Event()

    async def start(self):
        """Start daemon components."""
        await asyncio.gather(
            self.server.start(),
            self.scheduler.start(),
            self._event_loop(),
        )

    async def _event_loop(self):
        """Process events from queue."""
        while not self._shutdown.is_set():
            event = await self.server.event_queue.get()

            # Check deduplication
            if self.store.is_duplicate(event):
                continue

            # Find matching triggers
            triggers = self.router.match(event)

            for trigger in triggers:
                # Execute workflow
                await self._execute_trigger(trigger, event)

    async def _execute_trigger(self, trigger: Trigger, event: Event):
        """Execute workflow for trigger."""
        # Render variables with event context
        variables = render_variables(trigger.variables, event)

        # Run workflow
        result = await run_workflow(
            trigger.workflow,
            variables=variables,
            dry_run=self.config.dry_run,
        )

        # Store execution record
        self.store.record_execution(event, trigger, result)
```

### 2. Webhook Server

```python
# src/devctl/events/server.py

from starlette.applications import Starlette
from starlette.routing import Route

class WebhookServer:
    def __init__(self, config: ServerConfig):
        self.config = config
        self.event_queue = asyncio.Queue()
        self.handlers = {
            'cloudwatch': CloudWatchHandler(),
            'grafana': GrafanaHandler(),
            'github': GitHubHandler(config.github_secret),
            'pagerduty': PagerDutyHandler(),
        }
        self.app = self._create_app()

    def _create_app(self) -> Starlette:
        return Starlette(routes=[
            Route('/webhooks/{source}', self.handle_webhook, methods=['POST']),
            Route('/health', self.health_check),
        ])

    async def handle_webhook(self, request):
        source = request.path_params['source']
        handler = self.handlers.get(source)

        if not handler:
            return JSONResponse({'error': 'Unknown source'}, 404)

        try:
            event = await handler.parse(request)
            await self.event_queue.put(event)
            return JSONResponse({'status': 'accepted'})
        except ValidationError as e:
            return JSONResponse({'error': str(e)}, 400)
```

### 3. Event Handlers

```python
# src/devctl/events/handlers/github.py

import hmac
import hashlib

class GitHubHandler(BaseEventHandler):
    def __init__(self, webhook_secret: str):
        self.secret = webhook_secret

    async def parse(self, request) -> Event:
        # Validate signature
        signature = request.headers.get('X-Hub-Signature-256')
        body = await request.body()

        if not self._verify_signature(body, signature):
            raise ValidationError("Invalid signature")

        # Parse event
        event_type = request.headers.get('X-GitHub-Event')
        payload = json.loads(body)

        return Event(
            source='github',
            event_type=event_type,
            timestamp=datetime.utcnow(),
            raw_payload=payload,
            normalized={
                'action': payload.get('action'),
                'repository': payload.get('repository', {}).get('full_name'),
                'sender': payload.get('sender', {}).get('login'),
                # ... other normalized fields
            }
        )

    def _verify_signature(self, body: bytes, signature: str) -> bool:
        expected = 'sha256=' + hmac.new(
            self.secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
```

### 4. Event Router

```python
# src/devctl/events/router.py

import re
from jinja2 import Environment

class EventRouter:
    def __init__(self, triggers: list[TriggerConfig]):
        self.triggers = triggers
        self.jinja = Environment()

    def match(self, event: Event) -> list[TriggerConfig]:
        """Find triggers matching the event."""
        matches = []

        for trigger in self.triggers:
            if self._matches(trigger, event):
                matches.append(trigger)

        return matches

    def _matches(self, trigger: TriggerConfig, event: Event) -> bool:
        # Check source
        if trigger.source != event.source:
            return False

        # Check event type
        if trigger.event_type and trigger.event_type != event.event_type:
            return False

        # Evaluate conditions
        return self._evaluate_conditions(trigger.conditions, event)

    def _evaluate_conditions(self, conditions: dict, event: Event) -> bool:
        for key, expected in conditions.items():
            if key.endswith('_pattern'):
                # Regex pattern match
                field = key.replace('_pattern', '')
                actual = get_nested(event.normalized, field)
                if not re.match(expected, str(actual)):
                    return False
            elif key == 'expression':
                # Jinja2 expression
                result = self.jinja.from_string(expected).render(event=event)
                if result.lower() not in ('true', '1', 'yes'):
                    return False
            else:
                # Exact match
                actual = get_nested(event.normalized, key)
                if actual != expected:
                    return False

        return True
```

### 5. Event Store

```python
# src/devctl/events/store.py

import sqlite3
from dataclasses import asdict

class EventStore:
    def __init__(self, config: StoreConfig):
        self.db_path = Path(config.path).expanduser()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload JSON,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    trigger_name TEXT,
                    workflow_name TEXT,
                    workflow_result JSON,
                    error_message TEXT
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_events_status
                ON events(status)
            ''')

    def is_duplicate(self, event: Event) -> bool:
        """Check if event was recently processed."""
        # Hash key fields for dedup
        pass

    def record_execution(self, event: Event, trigger: TriggerConfig, result):
        """Record workflow execution."""
        pass
```

---

## Files to Modify

- `src/devctl/cli.py` - Register events command group
- `src/devctl/config.py` - Add EventsConfig, TriggerConfig, SourcesConfig

---

## New Dependencies

```toml
[project.optional-dependencies]
events = [
    "starlette>=0.32.0",
    "uvicorn[standard]>=0.27.0",
    "apscheduler>=3.10.0",
    "aiosqlite>=0.19.0",  # For async SQLite
]
```

---

## Implementation Order

1. **Core infrastructure** - Daemon, server skeleton, CLI command
2. **Event handlers** - CloudWatch, Grafana (simpler webhooks)
3. **Trigger configuration** - Router, condition matching
4. **Scheduler** - Cron-based triggers
5. **Event store** - Persistence, history, replay
6. **GitHub/PagerDuty handlers** - Signature validation

---

## Key Integrations

- `src/devctl/workflows/engine.py` - Workflow execution
- `src/devctl/core/async_utils.py` - RateLimiter, gather_with_concurrency
- `src/devctl/config.py` - Configuration loading
