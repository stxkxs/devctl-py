# PagerDuty Commands

devctl integrates with PagerDuty for incident management and on-call scheduling.

## Prerequisites

- PagerDuty account with API access
- API key with appropriate permissions

## Configuration

```yaml
profiles:
  default:
    pagerduty:
      api_key: from_env     # Use DEVCTL_PAGERDUTY_API_KEY
      service_id: PXXXXXX   # Default service for incidents
      email: user@company.com  # Your PagerDuty email
      timeout: 30
```

Environment variables:
```bash
export DEVCTL_PAGERDUTY_API_KEY=u+xxxxxxxxxx
export DEVCTL_PAGERDUTY_EMAIL=user@company.com
export DEVCTL_PAGERDUTY_SERVICE_ID=PXXXXXX
```

## Incident Management

### List incidents

```bash
# List open incidents
devctl pagerduty incidents list

# Filter by status
devctl pagerduty incidents list --status triggered
devctl pagerduty incidents list --status acknowledged
devctl pagerduty incidents list --status resolved

# Filter by urgency
devctl pagerduty incidents list --urgency high

# Filter by time
devctl pagerduty incidents list --since 24h

# Filter by service
devctl pagerduty incidents list --service-id PXXXXXX
```

### Create incident

```bash
# Create a new incident
devctl pagerduty incidents create "Database connection timeout"

# With service and urgency
devctl pagerduty incidents create "API latency spike" \
  --service PXXXXXX \
  --urgency high

# With details
devctl pagerduty incidents create "Memory exhaustion" \
  --service PXXXXXX \
  --details "Server running at 98% memory utilization"
```

### Acknowledge incident

```bash
# Acknowledge an incident
devctl pagerduty incidents ack INCIDENT_ID

# Acknowledge multiple
devctl pagerduty incidents ack INCIDENT_ID1 INCIDENT_ID2
```

### Resolve incident

```bash
# Resolve an incident
devctl pagerduty incidents resolve INCIDENT_ID

# With resolution notes
devctl pagerduty incidents resolve INCIDENT_ID \
  --resolution "Scaled up database connections"
```

### Escalate incident

```bash
# Escalate to next level
devctl pagerduty incidents escalate INCIDENT_ID

# Escalate to specific level
devctl pagerduty incidents escalate INCIDENT_ID --level 2
```

### Add notes

```bash
# Add a note to an incident
devctl pagerduty incidents note INCIDENT_ID "Investigating database logs"
```

### Get incident details

```bash
# View incident details
devctl pagerduty incidents get INCIDENT_ID
```

## On-Call Management

### View current on-call

```bash
# Who's on-call now
devctl pagerduty oncall

# For specific schedule
devctl pagerduty oncall --schedule SCHEDULE_ID

# For specific escalation policy
devctl pagerduty oncall --policy POLICY_ID
```

## Schedule Management

### List schedules

```bash
# List all schedules
devctl pagerduty schedules list

# Search by name
devctl pagerduty schedules list --query "primary"
```

### Get schedule details

```bash
# View schedule with upcoming on-call
devctl pagerduty schedules get SCHEDULE_ID

# Include specific time range
devctl pagerduty schedules get SCHEDULE_ID --since 2024-01-01 --until 2024-01-31
```

## Service Management

### List services

```bash
# List all services
devctl pagerduty services list

# Filter by team
devctl pagerduty services list --team-id TEAM_ID

# Search by name
devctl pagerduty services list --query "api"
```

### Get service details

```bash
# View service details
devctl pagerduty services get SERVICE_ID

# Include integrations
devctl pagerduty services get SERVICE_ID --include integrations
```

## Common Patterns

### Incident response workflow

```bash
# 1. Check current incidents
devctl pagerduty incidents list --status triggered

# 2. Acknowledge the incident
devctl pagerduty incidents ack INCIDENT_ID

# 3. Add investigation notes
devctl pagerduty incidents note INCIDENT_ID "Checking application logs"

# 4. After resolving
devctl pagerduty incidents resolve INCIDENT_ID \
  --resolution "Restarted service, monitoring for recurrence"
```

### Check who's on-call before escalating

```bash
# View on-call rotation
devctl pagerduty oncall

# Then escalate if needed
devctl pagerduty incidents escalate INCIDENT_ID
```

### Create incident with Slack notification

```bash
# Create PagerDuty incident
devctl pagerduty incidents create "Production outage" --urgency high

# Notify Slack channel
devctl slack notify --type incident \
  --title "Production outage" \
  --severity critical \
  --channel "#incidents"
```

## Output Formats

```bash
# JSON for scripting
devctl -o json pagerduty incidents list

# Get incident IDs only
devctl -o json pagerduty incidents list | jq '.[].id'

# YAML output
devctl -o yaml pagerduty oncall
```
