# Slack Commands

devctl integrates with Slack for messaging, notifications, and channel management.

## Prerequisites

- Slack workspace with bot installed
- Bot token with appropriate scopes

## Configuration

```yaml
profiles:
  default:
    slack:
      token: from_env           # Use DEVCTL_SLACK_TOKEN
      default_channel: "#devops"
      username: "DevCtl Bot"
```

Environment variables:
```bash
export DEVCTL_SLACK_TOKEN=xoxb-xxxxxxxxxxxx-xxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx
export DEVCTL_SLACK_DEFAULT_CHANNEL="#devops"
```

### Required Bot Scopes

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages |
| `channels:read` | List public channels |
| `channels:manage` | Create/archive channels |
| `groups:read` | List private channels |
| `users:read` | List users |

## Sending Messages

### Basic message

```bash
# Send to a channel
devctl slack send "#devops" "Deployment completed successfully"

# Send to a user
devctl slack send "@john" "Your deployment is ready for review"
```

### Thread replies

```bash
# Reply to a thread
devctl slack send "#devops" "Following up on this" --thread 1234567890.123456

# Or use the thread command
devctl slack thread "#devops" 1234567890.123456 "This is a thread reply"
```

## Formatted Notifications

### Deployment notification

```bash
devctl slack notify --type deployment \
  --service my-app \
  --version v1.2.3 \
  --environment production \
  --status succeeded \
  --url https://argocd.company.com/applications/my-app
```

### Incident notification

```bash
devctl slack notify --type incident \
  --title "Database connection timeout" \
  --severity critical \
  --status triggered \
  --url https://pagerduty.com/incidents/ABC123
```

### Build notification

```bash
devctl slack notify --type build \
  --service my-app \
  --status succeeded \
  --url https://github.com/org/repo/actions/runs/12345
```

### Notification options

```bash
# Send to specific channel (overrides default)
devctl slack notify --type deployment --channel "#releases" ...

# All notification types support these common options:
#   --channel    Target channel
#   --status     started, succeeded, failed
#   --url        Link to details
```

## Channel Operations

### List channels

```bash
# List public channels
devctl slack channels list

# Include archived channels
devctl slack channels list --include-archived

# Limit results
devctl slack channels list --limit 50
```

### Create channel

```bash
# Create public channel
devctl slack channels create incident-2024-01-15

# Create private channel
devctl slack channels create team-private --private
```

### Archive channel

```bash
# Archive a channel
devctl slack channels archive old-project

# Skip confirmation
devctl slack channels archive old-project -y
```

## User Operations

```bash
# List users
devctl slack users list

# Limit results
devctl slack users list --limit 100
```

## Common Patterns

### Incident response workflow

```bash
# 1. Create incident channel
devctl slack channels create incident-$(date +%Y-%m-%d)-database

# 2. Notify team
devctl slack notify --type incident \
  --title "Database connection timeout" \
  --severity critical \
  --channel "#incident-2024-01-15-database"

# 3. Post updates
devctl slack send "#incident-2024-01-15-database" "Investigating database logs..."

# 4. Resolve and archive
devctl slack send "#incident-2024-01-15-database" "Incident resolved. Root cause: connection pool exhaustion"
devctl slack channels archive incident-2024-01-15-database
```

### Deployment notifications

```bash
#!/bin/bash

# Notify start
devctl slack notify --type deployment \
  --service $SERVICE \
  --version $VERSION \
  --environment production \
  --status started

# ... perform deployment ...

# Notify completion
devctl slack notify --type deployment \
  --service $SERVICE \
  --version $VERSION \
  --environment production \
  --status succeeded \
  --url "https://argocd.company.com/applications/$SERVICE"
```

### CI/CD integration

```yaml
# GitHub Actions example
- name: Notify Slack on success
  if: success()
  run: |
    devctl slack notify --type build \
      --service ${{ github.repository }} \
      --status succeeded \
      --url ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}

- name: Notify Slack on failure
  if: failure()
  run: |
    devctl slack notify --type build \
      --service ${{ github.repository }} \
      --status failed \
      --url ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
```

## Dry Run Mode

Preview what would be sent:

```bash
devctl --dry-run slack send "#devops" "Test message"
devctl --dry-run slack notify --type deployment --service my-app --status succeeded
```

## Output Formats

```bash
# JSON output for scripting
devctl -o json slack channels list

# Get channel IDs
devctl -o json slack channels list | jq '.[].id'
```
