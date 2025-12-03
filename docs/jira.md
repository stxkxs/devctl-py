# Jira

Jira Cloud operations for issue tracking, agile boards, and sprint management.

## Prerequisites

- Jira Cloud instance (not Jira Server/Data Center)
- API token from [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
- Your Atlassian account email

## Configuration

### Environment Variables

```bash
export JIRA_URL=https://your-domain.atlassian.net
export JIRA_EMAIL=your-email@company.com
export JIRA_API_TOKEN=your-api-token
```

Or with `DEVCTL_` prefix:

```bash
export DEVCTL_JIRA_URL=https://your-domain.atlassian.net
export DEVCTL_JIRA_EMAIL=your-email@company.com
export DEVCTL_JIRA_API_TOKEN=your-api-token
```

### Config File

```yaml
# ~/.devctl/config.yaml
profiles:
  default:
    jira:
      url: https://your-domain.atlassian.net
      email: your-email@company.com
      api_token: from_env  # Uses JIRA_API_TOKEN or DEVCTL_JIRA_API_TOKEN
```

## Commands Overview

```
devctl jira
├── issues          # Issue operations
│   ├── search      # Search with JQL
│   ├── get         # Get issue details
│   ├── create      # Create new issue
│   ├── update      # Update issue fields
│   ├── transition  # Change issue status
│   ├── comment     # Add comment
│   ├── assign      # Assign issue
│   ├── log-work    # Log time
│   ├── link        # Link issues
│   └── my-issues   # List my assigned issues
├── boards          # Board operations
│   ├── list        # List boards
│   ├── get         # Get board details
│   ├── backlog     # View backlog
│   └── move-to-backlog  # Move issues to backlog
└── sprints         # Sprint operations
    ├── list        # List sprints
    ├── get         # Get sprint details
    ├── issues      # View sprint issues
    ├── move        # Move issues to sprint
    └── active      # Get active sprint info
```

## Issue Commands

### Search Issues

```bash
# Basic JQL search
devctl jira issues search "project = PROJ"

# Complex queries
devctl jira issues search "assignee = currentUser() AND status != Done"
devctl jira issues search "sprint in openSprints() AND type = Bug"
devctl jira issues search "created >= -7d AND priority = High"

# Limit results
devctl jira issues search "project = PROJ" --max 100

# Select specific fields
devctl jira issues search "project = PROJ" --fields summary,status,assignee
```

### Get Issue Details

```bash
devctl jira issues get PROJ-123
```

### Create Issues

```bash
# Basic task
devctl jira issues create PROJ "Implement login feature"

# Bug with priority
devctl jira issues create PROJ "Fix null pointer exception" --type Bug --priority High

# Story with description
devctl jira issues create PROJ "User authentication" --type Story \
  -d "As a user, I want to log in securely"

# With labels
devctl jira issues create PROJ "Database optimization" \
  --type Task --label backend --label performance

# Subtask
devctl jira issues create PROJ "Write unit tests" \
  --type Sub-task --parent PROJ-123
```

### Update Issues

```bash
# Update summary
devctl jira issues update PROJ-123 --summary "New title"

# Change priority
devctl jira issues update PROJ-123 --priority Critical

# Add labels
devctl jira issues update PROJ-123 --add-label urgent --add-label production

# Remove labels
devctl jira issues update PROJ-123 --remove-label backlog
```

### Transition Issues

```bash
# List available transitions
devctl jira issues transition PROJ-123 --list

# Move to In Progress
devctl jira issues transition PROJ-123 "In Progress"

# Mark as Done
devctl jira issues transition PROJ-123 "Done"
```

### Comments

```bash
devctl jira issues comment PROJ-123 "Starting work on this"
devctl jira issues comment PROJ-123 "Blocked by external dependency"
```

### Assignment

```bash
# Assign to yourself
devctl jira issues assign PROJ-123 --me

# Assign to someone else
devctl jira issues assign PROJ-123 john@company.com

# Unassign
devctl jira issues assign PROJ-123 --unassign
```

### Time Tracking

```bash
# Log work
devctl jira issues log-work PROJ-123 "2h 30m"
devctl jira issues log-work PROJ-123 "1d" --comment "Completed implementation"
```

### Link Issues

```bash
# Default "Relates" link
devctl jira issues link PROJ-123 PROJ-456

# Specific link type
devctl jira issues link PROJ-123 PROJ-456 --type Blocks
devctl jira issues link PROJ-123 PROJ-456 --type Duplicates
```

### My Issues

```bash
# All my issues
devctl jira issues my-issues

# Filter by status
devctl jira issues my-issues --status "In Progress"

# Filter by project
devctl jira issues my-issues --project PROJ
```

## Board Commands

### List Boards

```bash
# All boards
devctl jira boards list

# Filter by project
devctl jira boards list --project PROJ

# Filter by type
devctl jira boards list --type scrum
devctl jira boards list --type kanban
```

### Get Board Details

```bash
devctl jira boards get 123
```

### View Backlog

```bash
# All backlog items
devctl jira boards backlog 123

# With JQL filter
devctl jira boards backlog 123 --jql "priority = High"
```

### Move to Backlog

```bash
devctl jira boards move-to-backlog PROJ-123
devctl jira boards move-to-backlog PROJ-123 PROJ-124 PROJ-125
```

## Sprint Commands

### List Sprints

```bash
# All sprints for a board
devctl jira sprints list --board 123

# Filter by state
devctl jira sprints list --board 123 --state active
devctl jira sprints list --board 123 --state future
devctl jira sprints list --board 123 --state closed
```

### Get Sprint Details

```bash
devctl jira sprints get 456
```

### View Sprint Issues

```bash
# All issues in sprint
devctl jira sprints issues 456

# Filter with JQL
devctl jira sprints issues 456 --jql "status = Done"
devctl jira sprints issues 456 --jql "assignee = currentUser()"
```

### Move Issues to Sprint

```bash
devctl jira sprints move 456 PROJ-123
devctl jira sprints move 456 PROJ-123 PROJ-124 PROJ-125
```

### Active Sprint Summary

```bash
# Get active sprint with status breakdown
devctl jira sprints active --board 123
```

## Common JQL Queries

| Query | Description |
|-------|-------------|
| `project = PROJ` | All issues in project |
| `assignee = currentUser()` | Assigned to me |
| `assignee is EMPTY` | Unassigned issues |
| `status = "In Progress"` | In progress issues |
| `status != Done` | Not completed |
| `sprint in openSprints()` | In active sprints |
| `sprint is EMPTY` | Not in any sprint |
| `created >= -7d` | Created in last 7 days |
| `updated >= startOfDay()` | Updated today |
| `priority in (High, Highest)` | High priority |
| `type = Bug` | Bugs only |
| `labels = urgent` | Has urgent label |
| `reporter = currentUser()` | Reported by me |
| `resolution is EMPTY` | Unresolved |

### Combining Queries

```bash
# My open bugs
devctl jira issues search "assignee = currentUser() AND type = Bug AND status != Done"

# High priority in current sprint
devctl jira issues search "sprint in openSprints() AND priority in (High, Highest)"

# Recently updated in my project
devctl jira issues search "project = PROJ AND updated >= -24h ORDER BY updated DESC"
```

## Output Formats

```bash
# Table (default)
devctl jira issues my-issues

# JSON (for scripting)
devctl -o json jira issues search "project = PROJ"

# YAML
devctl -o yaml jira issues get PROJ-123
```

## Dry Run Mode

Preview operations without making changes:

```bash
devctl --dry-run jira issues create PROJ "Test issue"
devctl --dry-run jira issues transition PROJ-123 "Done"
```

## Workflow Templates

Built-in workflow templates for common Jira operations:

```bash
# List available templates
devctl workflow list --templates

# View a template
devctl workflow template jira-standup
```

### Daily Standup

Generate a standup report showing yesterday's completed work, today's in-progress items, and blockers:

```bash
devctl workflow run jira-standup.yaml

# For a specific project
devctl workflow run jira-standup.yaml --var project=PROJ
```

### Sprint Report

Generate sprint status with issue breakdown:

```bash
devctl workflow run jira-sprint-report.yaml --var board_id=123
```

### Release Notes

Generate release notes from completed issues:

```bash
# By version
devctl workflow run jira-release-notes.yaml \
  --var project=PROJ \
  --var version="1.2.0"

# By sprint
devctl workflow run jira-release-notes.yaml \
  --var project=PROJ \
  --var sprint="Sprint 42"
```

### Bug Triage

List bugs needing triage (unassigned, unprioritized, stale):

```bash
devctl workflow run jira-bug-triage.yaml --var project=PROJ

# Custom stale threshold
devctl workflow run jira-bug-triage.yaml \
  --var project=PROJ \
  --var stale_days=7
```

### Sprint Cleanup

Identify issues needing attention before sprint ends:

```bash
devctl workflow run jira-sprint-cleanup.yaml --var board_id=123
```

### Deployment Ticket

Create a deployment tracking ticket with linked issues:

```bash
devctl workflow run jira-deployment-ticket.yaml \
  --var project=PROJ \
  --var version="1.2.0" \
  --var environment=production \
  --var issues="PROJ-123,PROJ-124"
```

## Scripting Examples

### Create Multiple Issues

```bash
#!/bin/bash
for task in "Task 1" "Task 2" "Task 3"; do
  devctl jira issues create PROJ "$task" --type Task
done
```

### Bulk Transition

```bash
#!/bin/bash
# Move all my in-progress issues to review
issues=$(devctl -o json jira issues search "assignee = currentUser() AND status = 'In Progress'" | jq -r '.[] | .key')
for issue in $issues; do
  devctl jira issues transition "$issue" "In Review"
done
```

### Daily Standup Report

```bash
#!/bin/bash
echo "=== My Work ==="
devctl jira issues my-issues --status "In Progress"

echo ""
echo "=== Completed Yesterday ==="
devctl jira issues search "assignee = currentUser() AND status changed to Done AFTER startOfDay(-1)"
```

## Troubleshooting

### Authentication Errors

```bash
# Verify credentials
echo $JIRA_URL
echo $JIRA_EMAIL
echo $JIRA_API_TOKEN | head -c 10  # Show first 10 chars only

# Test connection
curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_URL/rest/api/3/myself" | jq .displayName
```

### Permission Errors

- Ensure your account has access to the project
- Check if the issue type is allowed in the project
- Verify you have permission to transition issues

### JQL Syntax Errors

- Use double quotes for values with spaces: `status = "In Progress"`
- Field names are case-insensitive
- Use `ORDER BY` at the end of query

## API Reference

- [Jira Cloud REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [Jira Agile REST API](https://developer.atlassian.com/cloud/jira/software/rest/)
- [JQL Reference](https://support.atlassian.com/jira-software-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
