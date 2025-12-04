# Workflows

YAML-based workflow engine for automating multi-step DevOps operations with [Jinja2](https://jinja.palletsprojects.com/) templating.

## Overview

Workflows chain devctl commands together with:
- Variable interpolation
- Conditional execution
- Failure handling
- Timeout controls

## Quick Start

```yaml
# deploy.yaml
name: deploy-service
description: Build and deploy a service

vars:
  environment: staging
  replicas: 2

steps:
  - name: Build container
    command: aws ecr build
    params:
      repository: "{{ service_name }}"
      tag: "{{ version }}"
      push: true

  - name: Update deployment
    command: "!kubectl set image deployment/{{ service_name }} app={{ image_uri }}"

  - name: Wait for rollout
    command: "!kubectl rollout status deployment/{{ service_name }}"
    timeout: 300

  - name: Create annotation
    command: grafana annotations create
    params:
      text: "Deployed {{ service_name }} {{ version }}"
      tags: "deployment,{{ environment }}"
    on_failure: continue
```

Run it:

```bash
devctl workflow run deploy.yaml \
  --var service_name=api \
  --var version=v1.2.3 \
  --var image_uri=123456789.dkr.ecr.us-east-1.amazonaws.com/api:v1.2.3
```

## Workflow Schema

### Top-Level Structure

```yaml
name: workflow-name              # Required: Unique identifier
description: What this does      # Optional: Human-readable description

vars:                            # Optional: Default variables
  key: value
  key2: "{{ env_var }}"

steps:                           # Required: List of steps
  - name: Step name
    command: command to run
    # ... step options
```

### Step Options

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Required. Step identifier |
| `command` | string | Required. devctl command or shell command (prefixed with `!`) |
| `params` | object | Command parameters |
| `condition` | string | Jinja2 expression for conditional execution |
| `on_failure` | string | `fail` (default), `continue`, or `retry` |
| `timeout` | integer | Timeout in seconds |
| `retries` | integer | Number of retries (when `on_failure: retry`) |

### Commands

#### devctl Commands

Reference any devctl command:

```yaml
- name: List buckets
  command: aws s3 ls

- name: Get cost summary
  command: aws cost summary
  params:
    days: 30
```

#### Shell Commands

Prefix with `!` for shell execution:

```yaml
- name: Run kubectl
  command: "!kubectl apply -f manifest.yaml"

- name: Run script
  command: "!./scripts/deploy.sh {{ environment }}"
```

### Variables

#### Default Variables

```yaml
vars:
  cluster: default-cluster
  namespace: default
  replicas: 2
```

#### Override at Runtime

```bash
devctl workflow run deploy.yaml --var cluster=production --var replicas=5
```

#### Variable Interpolation

Use Jinja2 syntax:

```yaml
steps:
  - name: Deploy
    command: aws ecr build
    params:
      repository: "{{ service_name }}"
      tag: "{{ version | default('latest') }}"
```

#### Built-in Variables

| Variable | Description |
|----------|-------------|
| `results` | Dictionary of previous step results |
| `results['Step Name'].stdout` | stdout from step |
| `results['Step Name'].stderr` | stderr from step |
| `results['Step Name'].exit_code` | Exit code |

Example:

```yaml
- name: Get cluster ARN
  command: aws eks describe
  params:
    cluster: "{{ cluster }}"

- name: Use ARN
  command: "!echo 'Cluster ARN: {{ results[\"Get cluster ARN\"].stdout }}'"
```

### Jinja2 Filters

Available filters:

| Filter | Description | Example |
|--------|-------------|---------|
| `default` | Default value if undefined | `{{ var \| default('fallback') }}` |
| `trim` | Remove whitespace | `{{ output \| trim }}` |
| `lower` | Lowercase | `{{ name \| lower }}` |
| `upper` | Uppercase | `{{ name \| upper }}` |
| `strftime` | Format current time | `{{ '%Y%m%d' \| strftime }}` |

### Conditional Execution

```yaml
- name: Production only step
  condition: "{{ environment == 'production' }}"
  command: aws cloudwatch alarms
  params:
    state: alarm

- name: Optional scaling
  condition: "{{ scale_enabled | default(false) }}"
  command: aws eks nodegroups
  params:
    cluster: "{{ cluster }}"
    scale: "{{ nodegroup }}"
    count: "{{ replicas }}"
```

### Failure Handling

```yaml
# Stop workflow on failure (default)
- name: Critical step
  command: aws ecr login
  on_failure: fail

# Continue even if step fails
- name: Optional annotation
  command: grafana annotations create
  params:
    text: "Deployed {{ service_name }}"
  on_failure: continue

# Retry on failure
- name: Flaky API call
  command: "!curl -f https://api.example.com/webhook"
  on_failure: retry
  retries: 3
  timeout: 30
```

### Timeouts

```yaml
- name: Long running step
  command: aws forecast predictors create
  params:
    name: "{{ predictor_name }}"
    auto-ml: true
  timeout: 3600  # 1 hour
```

## Workflow Commands

### run

Execute a workflow:

```bash
devctl workflow run WORKFLOW [OPTIONS]

Options:
  --var, -v KEY=VALUE    Set variable (can repeat)
```

Examples:

```bash
# Run workflow file
devctl workflow run ./deploy.yaml --var env=prod

# Run configured workflow
devctl workflow run deploy-service --var service_name=api
```

### dry-run

Preview without executing:

```bash
devctl workflow dry-run deploy.yaml --var service_name=api
```

Output:

```
Workflow: deploy-service
Description: Build and deploy a service

Variables:
  service_name: api
  environment: staging (default)
  replicas: 2 (default)

Steps:
  1. Build container
     Command: aws ecr build
     Params: repository=api, tag=latest, push=true

  2. Update deployment
     Command: !kubectl set image deployment/api app=...

  3. Wait for rollout
     Command: !kubectl rollout status deployment/api
     Timeout: 300s

  4. Create annotation
     Command: grafana annotations create
     On Failure: continue
```

### validate

Check workflow syntax:

```bash
devctl workflow validate deploy.yaml
```

### list

List configured workflows:

```bash
# List workflows in config
devctl workflow list

# List built-in templates
devctl workflow list --templates
```

### template

View or copy built-in templates:

```bash
# View template
devctl workflow template predictive-scaling

# Copy to file
devctl workflow template predictive-scaling -o ./my-workflow.yaml
```

### show

Show details of configured workflow:

```bash
devctl workflow show deploy-service
```

## Built-in Templates

| Template | Description |
|----------|-------------|
| `predictive-scaling` | Full ML pipeline for predictive auto-scaling |
| `update-predictive-scaling` | Refresh scaling from existing forecast |
| `predictive-scaling-pipeline` | Continuous daily pipeline |
| `jira-standup` | Generate daily standup report from Jira |
| `jira-sprint-report` | Sprint status and progress report |
| `jira-sprint-cleanup` | Identify issues needing attention before sprint ends |
| `jira-release-notes` | Generate release notes from Jira issues |
| `jira-bug-triage` | Bug triage workflow with prioritization |
| `jira-deployment-ticket` | Create deployment tracking ticket |
| `incident-response` | Full incident lifecycle (PagerDuty, Slack, Confluence) |
| `deploy-with-jira` | Deploy with Jira tracking and notifications |
| `daily-ops-report` | Morning ops report (costs, incidents, alerts) |
| `pr-to-deploy` | GitOps pipeline from PR merge to production |
| `rollback-notify` | Rollback with Jira ticket and notifications |
| `weekly-cost-review` | Cost analysis with optimization recommendations |
| `oncall-handoff` | On-call shift handoff report |
| `access-review-quarterly` | Quarterly IAM access review for compliance |

```bash
# List templates
devctl workflow list --templates

# View template
devctl workflow template predictive-scaling

# Copy and customize
devctl workflow template predictive-scaling -o ./my-scaling.yaml
```

## Configuration File Workflows

Define workflows in `~/.devctl/config.yaml` or `./devctl.yaml`:

```yaml
version: "1"

workflows:
  quick-deploy:
    description: "Quick deployment without health checks"
    vars:
      environment: staging
    steps:
      - name: Build
        command: aws ecr build
        params:
          repository: "{{ service }}"
          push: true
      - name: Annotate
        command: grafana annotations create
        params:
          text: "Deployed {{ service }}"
        on_failure: continue

  cost-check:
    description: "Daily cost review"
    steps:
      - name: Summary
        command: aws cost summary
        params:
          days: 7
      - name: Unused
        command: aws cost unused-resources
      - name: Rightsizing
        command: aws cost rightsizing
```

Run:

```bash
devctl workflow run quick-deploy --var service=api
devctl workflow run cost-check
```

## Examples

### Multi-Environment Deploy

```yaml
name: multi-env-deploy
description: Deploy to staging then production

vars:
  service_name: ""
  version: ""

steps:
  - name: Build container
    command: aws ecr build
    params:
      repository: "{{ service_name }}"
      tag: "{{ version }}"
      push: true

  - name: Deploy to staging
    command: "!kubectl --context staging set image deployment/{{ service_name }} app={{ image }}"

  - name: Run staging tests
    command: "!./scripts/integration-tests.sh staging"
    timeout: 600
    on_failure: fail

  - name: Approve production
    command: "!echo 'Staging passed. Deploying to production...'"

  - name: Deploy to production
    command: "!kubectl --context production set image deployment/{{ service_name }} app={{ image }}"

  - name: Create annotation
    command: grafana annotations create
    params:
      text: "{{ service_name }} {{ version }} deployed to production"
      tags: "deployment,production,{{ service_name }}"
```

### Daily Cost Report

```yaml
name: daily-cost-report
description: Generate and send daily cost report

steps:
  - name: Get cost summary
    command: aws cost summary
    params:
      days: 1

  - name: Check for anomalies
    command: aws cost anomalies
    params:
      days: 1

  - name: Find unused resources
    command: aws cost unused-resources

  - name: Create annotation
    command: grafana annotations create
    params:
      text: "Daily cost report completed"
      tags: "cost,automation"
    on_failure: continue
```

### ECR Cleanup

```yaml
name: ecr-cleanup
description: Clean up old images across repositories

vars:
  keep: 10

steps:
  - name: Cleanup api repo
    command: aws ecr cleanup
    params:
      repository: api
      keep: "{{ keep }}"

  - name: Cleanup worker repo
    command: aws ecr cleanup
    params:
      repository: worker
      keep: "{{ keep }}"

  - name: Cleanup web repo
    command: aws ecr cleanup
    params:
      repository: web
      keep: "{{ keep }}"
```

### Incident Response

```yaml
name: incident-scale-up
description: Emergency scale-up during incident

vars:
  cluster: production
  nodegroup: workers
  target_count: 10

steps:
  - name: Scale up nodes
    command: aws eks nodegroups
    params:
      cluster: "{{ cluster }}"
      scale: "{{ nodegroup }}"
      count: "{{ target_count }}"

  - name: Silence non-critical alerts
    command: grafana alerts silence
    params:
      duration: 1h
      comment: "Scaling in progress - incident response"
    on_failure: continue

  - name: Create incident annotation
    command: grafana annotations create
    params:
      text: "INCIDENT: Scaled {{ nodegroup }} to {{ target_count }} nodes"
      tags: "incident,scaling,{{ cluster }}"
```

## Error Handling

### Step Failures

When a step fails:

1. **`on_failure: fail`** (default) - Workflow stops, exits with error
2. **`on_failure: continue`** - Log warning, continue to next step
3. **`on_failure: retry`** - Retry up to `retries` times

### Debugging

```bash
# Verbose output
devctl -vvv workflow run deploy.yaml --var service=api

# Dry run first
devctl workflow dry-run deploy.yaml --var service=api
```

### Timeouts

Set appropriate timeouts for long-running operations:

```yaml
- name: Train ML model
  command: aws forecast predictors create
  params:
    name: my-predictor
    auto-ml: true
  timeout: 7200  # 2 hours - ML training takes time
```

## Best Practices

1. **Use dry-run first** - Always preview before running
2. **Set explicit timeouts** - Don't rely on defaults for long operations
3. **Use continue for optional steps** - Annotations, notifications shouldn't block
4. **Validate before committing** - Run `devctl workflow validate`
5. **Use templates** - Start from built-in templates when possible
6. **Keep workflows focused** - One workflow per concern

## Related Documentation

- [Jinja2 Template Designer](https://jinja.palletsprojects.com/en/3.1.x/templates/)
- [Predictive Scaling](predictive-scaling.md) - Workflow templates for scaling
- [Configuration](configuration.md) - Configuring workflows in config files
