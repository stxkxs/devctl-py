# AI-Powered Features

New `devctl ai` command group leveraging existing Bedrock integration.

## Commands Overview

| Command | Description | Complexity |
|---------|-------------|------------|
| `ai explain-anomaly` | AI explanations for cost/metric anomalies | Low-Medium |
| `ai review-iac` | Security/cost review of Terraform/K8s manifests | Medium |
| `ai ask` | Natural language to devctl commands | Medium |
| `ai generate-runbook` | Auto-generate runbooks from incidents | Medium |
| `ai incident-analyze` | Correlate logs/metrics for root cause | High |

---

## New Files Structure

### Command Group: `src/devctl/commands/ai/`

```
src/devctl/commands/ai/
├── __init__.py      # Register ai command group
├── explain.py       # explain-anomaly command
├── review.py        # review-iac command
├── ask.py           # Natural language command
├── runbook.py       # generate-runbook command
└── incident.py      # incident-analyze command
```

### Core AI Module: `src/devctl/ai/`

```
src/devctl/ai/
├── __init__.py
├── base.py              # Base AI client wrapping Bedrock
├── context_builder.py   # Build context from multiple sources
├── schemas.py           # Pydantic response models
└── prompts/
    ├── __init__.py
    ├── anomaly.py       # Anomaly explanation prompts
    ├── iac_review.py    # IaC review prompts
    ├── command.py       # Natural language prompts
    ├── runbook.py       # Runbook generation prompts
    └── incident.py      # Incident analysis prompts
```

---

## 1. AI Explain Anomaly

**Command**: `devctl ai explain-anomaly [--type cost|metric] [--id ANOMALY_ID]`

### Implementation

```python
# src/devctl/commands/ai/explain.py

@click.command('explain-anomaly')
@click.option('--type', type=click.Choice(['cost', 'metric']), required=True)
@click.option('--id', 'anomaly_id', help='Anomaly ID or metric name')
@click.option('--since', default='24h', help='Time range')
@pass_context
def explain_anomaly(ctx, type: str, anomaly_id: str, since: str):
    """AI-powered explanation for cost or metric anomalies."""

    if type == 'cost':
        # Get anomaly data from Cost Explorer
        anomaly_data = ctx.aws.get_cost_anomaly(anomaly_id)
        context = build_cost_context(anomaly_data)
    else:
        # Get metric data from Grafana/CloudWatch
        metric_data = ctx.grafana.get_metric_history(anomaly_id, since)
        context = build_metric_context(metric_data)

    # Get correlated events (deployments, config changes)
    events = get_correlated_events(anomaly_data['timestamp'], since)

    # Build prompt and invoke Bedrock
    prompt = ANOMALY_PROMPT.format(
        anomaly=context,
        events=events,
    )

    response = ctx.bedrock.invoke(
        model=ctx.config.ai.default_model,
        prompt=prompt,
    )

    display_explanation(response)
```

### Prompt Template

```python
ANOMALY_PROMPT = """
Analyze this anomaly and provide:
1. Likely root cause
2. Related events that may have triggered it
3. Recommended actions

Anomaly Data:
{anomaly}

Recent Events:
{events}
"""
```

---

## 2. AI Review IaC

**Command**: `devctl ai review-iac [FILE] [--type terraform|k8s|helm]`

### Implementation

```python
# src/devctl/commands/ai/review.py

@click.command('review-iac')
@click.argument('file', type=click.Path(exists=True))
@click.option('--type', 'iac_type', type=click.Choice(['terraform', 'k8s', 'helm']))
@click.option('--focus', type=click.Choice(['security', 'cost', 'reliability', 'all']),
              default='all')
@pass_context
def review_iac(ctx, file: str, iac_type: str, focus: str):
    """AI-powered review of Infrastructure as Code."""

    content = Path(file).read_text()

    # Auto-detect type if not specified
    if not iac_type:
        iac_type = detect_iac_type(file)

    # Build review prompt based on focus
    prompt = build_review_prompt(content, iac_type, focus)

    response = ctx.bedrock.invoke(
        model=ctx.config.ai.default_model,
        prompt=prompt,
    )

    display_review(response)
```

### Review Categories

- **Security**: IAM permissions, network exposure, secrets handling
- **Cost**: Instance sizing, storage classes, reserved capacity
- **Reliability**: HA configuration, backup settings, resource limits

---

## 3. AI Ask (Natural Language)

**Command**: `devctl ai ask "show me expensive AWS services this month"`

### Implementation

```python
# src/devctl/commands/ai/ask.py

@click.command('ask')
@click.argument('query')
@click.option('--execute', is_flag=True, help='Execute suggested command')
@pass_context
def ask(ctx, query: str, execute: bool):
    """Natural language to devctl commands."""

    # Build command registry
    commands = get_command_registry()

    prompt = COMMAND_PROMPT.format(
        query=query,
        commands=format_commands(commands),
    )

    response = ctx.bedrock.invoke(
        model=ctx.config.ai.default_model,
        prompt=prompt,
    )

    # Parse response to extract command
    suggested_cmd = parse_command(response)

    console.print(f"Suggested command: [cyan]{suggested_cmd}[/cyan]")
    console.print(f"Explanation: {response.explanation}")

    if execute:
        if is_safe_command(suggested_cmd):
            subprocess.run(f"devctl {suggested_cmd}", shell=True)
        else:
            if click.confirm('This command may modify resources. Continue?'):
                subprocess.run(f"devctl {suggested_cmd}", shell=True)
```

### Command Registry

```python
def get_command_registry() -> dict:
    """Build registry of all devctl commands with descriptions."""
    return {
        'aws cost summary': 'Show AWS cost summary for a period',
        'aws cost by-service': 'Break down costs by AWS service',
        'k8s pods list': 'List Kubernetes pods',
        # ... all commands
    }
```

---

## 4. AI Generate Runbook

**Command**: `devctl ai generate-runbook [--from-incident INCIDENT_ID] [--type TYPE]`

### Implementation

```python
# src/devctl/commands/ai/runbook.py

@click.command('generate-runbook')
@click.option('--from-incident', 'incident_id', help='Generate from incident')
@click.option('--type', 'runbook_type', help='Runbook type (e.g., database-failover)')
@click.option('--output', type=click.Path(), help='Output file')
@pass_context
def generate_runbook(ctx, incident_id: str, runbook_type: str, output: str):
    """Auto-generate runbooks from incidents or descriptions."""

    if incident_id:
        # Get incident details from PagerDuty
        incident = ctx.pagerduty.get_incident(incident_id)
        # Get resolution actions from incident notes
        notes = ctx.pagerduty.get_incident_notes(incident_id)
        context = build_incident_context(incident, notes)
    else:
        context = f"Runbook type: {runbook_type}"

    prompt = RUNBOOK_PROMPT.format(
        context=context,
        schema=RUNBOOK_SCHEMA,
    )

    response = ctx.bedrock.invoke(
        model=ctx.config.ai.default_model,
        prompt=prompt,
    )

    # Parse and validate runbook YAML
    runbook = parse_runbook(response)
    validate_runbook(runbook)

    if output:
        Path(output).write_text(yaml.dump(runbook))
    else:
        console.print(yaml.dump(runbook))
```

---

## 5. AI Incident Analyze

**Command**: `devctl ai incident-analyze [INCIDENT_ID] [--since DURATION]`

### Implementation

```python
# src/devctl/commands/ai/incident.py

@click.command('incident-analyze')
@click.argument('incident_id')
@click.option('--since', default='1h', help='Look back period')
@pass_context
def incident_analyze(ctx, incident_id: str, since: str):
    """Correlate logs, metrics, and events for root cause analysis."""

    # Gather data from multiple sources
    with console.status("Gathering incident data..."):
        # PagerDuty incident details
        incident = ctx.pagerduty.get_incident(incident_id)

        # CloudWatch logs around incident time
        logs = ctx.cloudwatch.get_logs_insights(
            log_groups=['/aws/ecs/*', '/aws/lambda/*'],
            query='fields @message | filter @message like /error|exception/i',
            start_time=incident['created_at'] - timedelta(hours=1),
            end_time=incident['created_at'] + timedelta(hours=1),
        )

        # Grafana metrics
        metrics = ctx.grafana.get_metrics_around(
            incident['created_at'],
            since=since,
        )

        # Kubernetes events (if applicable)
        k8s_events = ctx.k8s.get_events(since=since)

        # Deployment annotations
        deployments = ctx.grafana.get_annotations(
            tags=['deployment'],
            since=since,
        )

    # Build comprehensive context
    context = build_incident_context(
        incident=incident,
        logs=logs,
        metrics=metrics,
        k8s_events=k8s_events,
        deployments=deployments,
    )

    prompt = INCIDENT_ANALYSIS_PROMPT.format(context=context)

    response = ctx.bedrock.invoke(
        model=ctx.config.ai.default_model,
        prompt=prompt,
        max_tokens=4096,
    )

    display_analysis(response)
```

### Analysis Output Structure

```python
@dataclass
class IncidentAnalysis:
    summary: str
    probable_root_cause: str
    confidence: float
    contributing_factors: list[str]
    timeline: list[TimelineEvent]
    recommendations: list[str]
    similar_incidents: list[str]
```

---

## Configuration

Add to `~/.devctl/config.yaml`:

```yaml
ai:
  default_model: anthropic.claude-3-sonnet-20240229
  max_tokens: 4096
  temperature: 0.3
  safety_mode: true  # Require confirmation for actions
  context_window_days: 7  # Default lookback for incident analysis
```

### Config Schema

```python
class AIConfig(BaseModel):
    default_model: str = "anthropic.claude-3-sonnet-20240229"
    max_tokens: int = 4096
    temperature: float = 0.3
    safety_mode: bool = True
    context_window_days: int = 7
```

---

## Files to Modify

- `src/devctl/cli.py` - Register ai command group
- `src/devctl/config.py` - Add AIConfig

---

## Implementation Order

1. **explain-anomaly** (Low-Medium) - Builds on existing anomaly detection
2. **review-iac** (Medium) - Structured code analysis, clear output
3. **ask** (Medium) - Natural language interface, command registry
4. **generate-runbook** (Medium) - Leverage existing runbook schema
5. **incident-analyze** (High) - Multi-source correlation

---

## Key Integrations

- `src/devctl/commands/aws/bedrock.py` - Model invocation patterns
- `src/devctl/commands/aws/cost.py` - Anomaly data
- `src/devctl/commands/pagerduty/incidents.py` - Incident data
- `src/devctl/commands/grafana/metrics.py` - Metric queries
- `src/devctl/runbooks/schema.py` - Runbook format
