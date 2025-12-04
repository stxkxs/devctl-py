# Runbook Commands

devctl provides an executable runbook engine that supports both YAML and Markdown formats.

## Overview

Runbooks are documented procedures that can be executed step-by-step, with:
- Variable substitution using Jinja2 templating
- Conditional steps
- Interactive prompts
- Command execution
- Audit logging

## Configuration

```yaml
profiles:
  default:
    runbooks:
      path: ./runbooks           # Default runbook directory
      audit_log: ~/.devctl/runbook-audit.log
      templates_path: ./templates
```

## Runbook Formats

### YAML Format

```yaml
name: Restart Service
version: "1.0"
description: Safely restart a service with health checks
author: Platform Team

variables:
  service: null        # Required
  namespace: default
  wait_time: 30

steps:
  - name: Check current status
    type: command
    command: kubectl get pods -n {{ namespace }} -l app={{ service }}

  - name: Confirm restart
    type: prompt
    message: "Proceed with restarting {{ service }}?"

  - name: Scale down
    type: command
    command: kubectl scale deployment/{{ service }} -n {{ namespace }} --replicas=0

  - name: Wait for termination
    type: wait
    duration: "{{ wait_time }}"

  - name: Scale up
    type: command
    command: kubectl scale deployment/{{ service }} -n {{ namespace }} --replicas=3

  - name: Verify health
    type: command
    command: kubectl rollout status deployment/{{ service }} -n {{ namespace }}
```

### Markdown Format

```markdown
# Restart Service

**Version:** 1.0
**Author:** Platform Team

## Description

Safely restart a service with health checks.

## Variables

| Name | Default | Description |
|------|---------|-------------|
| service | (required) | Service name |
| namespace | default | Kubernetes namespace |

## Steps

### 1. Check current status

\`\`\`bash
kubectl get pods -n {{ namespace }} -l app={{ service }}
\`\`\`

### 2. Confirm restart

> **Prompt:** Proceed with restarting {{ service }}?

### 3. Scale down

\`\`\`bash
kubectl scale deployment/{{ service }} -n {{ namespace }} --replicas=0
\`\`\`

### 4. Wait for termination

> **Wait:** 30 seconds

### 5. Scale up

\`\`\`bash
kubectl scale deployment/{{ service }} -n {{ namespace }} --replicas=3
\`\`\`

### 6. Verify health

\`\`\`bash
kubectl rollout status deployment/{{ service }} -n {{ namespace }}
\`\`\`
```

## Commands

### Run a runbook

```bash
# Basic execution
devctl runbook run ./runbooks/restart-service.yaml

# With variables
devctl runbook run ./runbooks/restart-service.yaml \
  --var service=api \
  --var namespace=production

# Skip confirmations
devctl runbook run ./runbooks/restart-service.yaml -y

# Dry run (show what would execute)
devctl runbook run ./runbooks/restart-service.yaml --dry-run

# Start from specific step
devctl runbook run ./runbooks/restart-service.yaml --start-step 3
```

### List runbooks

```bash
# List available runbooks
devctl runbook list

# List built-in templates
devctl runbook list --templates

# Search by name
devctl runbook list --query "restart"
```

### Validate runbook

```bash
# Validate syntax
devctl runbook validate ./runbooks/restart-service.yaml

# Validate with variables
devctl runbook validate ./runbooks/restart-service.yaml \
  --var service=api
```

### View execution history

```bash
# Show recent executions
devctl runbook history

# Limit results
devctl runbook history --limit 20

# Filter by runbook
devctl runbook history --runbook restart-service
```

## Step Types

| Type | Description |
|------|-------------|
| `command` | Execute a shell command |
| `script` | Execute a multi-line script |
| `prompt` | Ask for confirmation |
| `wait` | Pause for specified duration |
| `manual` | Display instructions for manual steps |
| `notify` | Send a notification (Slack, etc.) |
| `conditional` | Execute based on condition |

### Command Step

```yaml
- name: Check pods
  type: command
  command: kubectl get pods -n {{ namespace }}
  continue_on_error: false  # Stop if command fails
```

### Script Step

```yaml
- name: Complex operation
  type: script
  script: |
    #!/bin/bash
    set -e
    echo "Starting operation..."
    kubectl get pods
    kubectl get services
```

### Prompt Step

```yaml
- name: Confirm action
  type: prompt
  message: "Are you sure you want to proceed?"
  default: "no"  # yes/no
```

### Wait Step

```yaml
- name: Wait for propagation
  type: wait
  duration: 60  # seconds
  message: "Waiting for DNS propagation..."
```

### Manual Step

```yaml
- name: Manual verification
  type: manual
  instructions: |
    1. Open the application in browser
    2. Verify the login page loads
    3. Check the API health endpoint
  prompt: "Have you completed the verification?"
```

### Notify Step

```yaml
- name: Notify team
  type: notify
  channel: "#ops"
  message: "Deployment of {{ service }} started"
```

### Conditional Step

```yaml
- name: Scale for production
  type: command
  command: kubectl scale deployment/{{ service }} --replicas=5
  when: "{{ env == 'production' }}"
```

## Variable Substitution

Variables use Jinja2 syntax:

```yaml
variables:
  service: my-app
  replicas: 3
  env: production

steps:
  - name: Deploy
    type: command
    command: |
      kubectl set image deployment/{{ service }} \
        app={{ registry }}/{{ service }}:{{ version }}
```

### Built-in Variables

| Variable | Description |
|----------|-------------|
| `_timestamp` | Current ISO timestamp |
| `_date` | Current date (YYYY-MM-DD) |
| `_user` | Current username |
| `_hostname` | Current hostname |

## Audit Logging

All runbook executions are logged:

```
2024-01-15T10:30:00Z | restart-service | user@host | STARTED | service=api
2024-01-15T10:30:05Z | restart-service | user@host | STEP_COMPLETED | step=1
2024-01-15T10:30:10Z | restart-service | user@host | STEP_COMPLETED | step=2
2024-01-15T10:32:00Z | restart-service | user@host | COMPLETED | duration=120s
```

## Publishing to Confluence

Runbooks can be published to Confluence for documentation:

```bash
devctl confluence runbook publish ./runbooks/restart-service.yaml \
  --space OPS \
  --parent 12345
```

## Common Patterns

### Database failover runbook

```yaml
name: Database Failover
version: "1.0"
description: Failover primary database to replica

variables:
  primary: db-primary
  replica: db-replica

steps:
  - name: Check replication lag
    type: command
    command: psql -h {{ replica }} -c "SELECT pg_last_wal_receive_lsn() - pg_last_wal_replay_lsn();"

  - name: Confirm failover
    type: prompt
    message: "Proceed with failover from {{ primary }} to {{ replica }}?"

  - name: Stop writes to primary
    type: command
    command: psql -h {{ primary }} -c "ALTER SYSTEM SET default_transaction_read_only = on; SELECT pg_reload_conf();"

  - name: Wait for replication
    type: wait
    duration: 10
    message: "Waiting for replica to catch up..."

  - name: Promote replica
    type: command
    command: psql -h {{ replica }} -c "SELECT pg_promote();"

  - name: Update DNS
    type: manual
    instructions: |
      Update Route53 record for database.company.com to point to {{ replica }}
    prompt: "Have you updated DNS?"

  - name: Notify team
    type: notify
    channel: "#database"
    message: "Database failover completed: {{ replica }} is now primary"
```
