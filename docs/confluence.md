# Confluence Commands

devctl integrates with Confluence for documentation, runbook publishing, and incident pages.

## Prerequisites

- Confluence Cloud account
- API token with appropriate permissions

## Configuration

```yaml
profiles:
  default:
    confluence:
      url: https://company.atlassian.net/wiki
      email: user@company.com
      api_token: from_env       # Use DEVCTL_CONFLUENCE_API_TOKEN
      default_space: DEV
```

Environment variables:
```bash
export DEVCTL_CONFLUENCE_URL=https://company.atlassian.net/wiki
export DEVCTL_CONFLUENCE_EMAIL=user@company.com
export DEVCTL_CONFLUENCE_API_TOKEN=xxxxxxxxxxxxxxxxxxxx
```

## Page Operations

### List pages

```bash
# List pages in a space
devctl confluence pages list --space DEV

# Filter by title
devctl confluence pages list --space DEV --title "API"

# Limit results
devctl confluence pages list --space DEV --limit 50
```

### Get page content

```bash
# Get page as rendered text
devctl confluence pages get 12345

# Get as storage format (raw HTML)
devctl confluence pages get 12345 --format storage
```

### Create page

```bash
# Create a basic page
devctl confluence pages create \
  --space DEV \
  --title "New Documentation"

# Create with content from file
devctl confluence pages create \
  --space DEV \
  --title "API Reference" \
  --file content.html

# Create as child of another page
devctl confluence pages create \
  --space DEV \
  --title "Sub Page" \
  --parent 12345
```

### Update page

```bash
# Update page content from file
devctl confluence pages update 12345 --file updated-content.html

# Update with new title
devctl confluence pages update 12345 --file content.html --title "New Title"
```

## Search

```bash
# Search across Confluence
devctl confluence search "deployment guide"

# Search within a space
devctl confluence search "runbook" --space OPS

# Limit results
devctl confluence search "API" --limit 20
```

## Runbook Publishing

Publish runbooks from YAML or Markdown to Confluence:

```bash
# Publish a runbook
devctl confluence runbook publish ./runbooks/restart-service.yaml \
  --space OPS

# With parent page
devctl confluence runbook publish ./runbooks/database-failover.yaml \
  --space OPS \
  --parent 12345

# With custom labels
devctl confluence runbook publish ./runbooks/incident-response.md \
  --space OPS \
  --labels "runbook,incident,database"
```

The runbook is converted to Confluence storage format with:
- Formatted steps with code blocks
- Variable documentation table
- Author and version metadata
- Runbook label for easy searching

## Incident Documentation

Create incident pages with a standard template:

```bash
# Create incident page
devctl confluence incident create \
  --space OPS \
  --title "Database outage 2024-01-15" \
  --severity P1

# With initial summary
devctl confluence incident create \
  --space OPS \
  --title "API latency spike" \
  --severity P2 \
  --summary "Increased response times observed starting 10:30 UTC" \
  --service api-gateway

# Under incident parent page
devctl confluence incident create \
  --space OPS \
  --title "Memory exhaustion" \
  --severity P3 \
  --parent 12345
```

The incident page template includes:
- Severity indicator
- Affected services
- Timeline section
- Investigation notes
- Root cause analysis section
- Action items

## Common Patterns

### Automated runbook documentation

Keep Confluence in sync with runbook files:

```bash
#!/bin/bash
# Publish all runbooks in a directory
for rb in ./runbooks/*.yaml; do
  devctl confluence runbook publish "$rb" --space OPS --parent $RUNBOOKS_PAGE_ID
done
```

### Incident workflow

```bash
# 1. Create incident page
PAGE_ID=$(devctl -o json confluence incident create \
  --space OPS \
  --title "$(date +%Y-%m-%d) Database Connection Timeout" \
  --severity P1 | jq -r '.id')

# 2. Share in Slack
devctl slack send "#incidents" "Incident page created: https://company.atlassian.net/wiki/pages/$PAGE_ID"

# 3. After resolution, update page with post-mortem
devctl confluence pages update $PAGE_ID --file postmortem.html
```

### Documentation pipeline

```yaml
# CI/CD: Publish docs on merge to main
- name: Publish to Confluence
  run: |
    devctl confluence pages update $PAGE_ID --file docs/api-reference.html
```

## Storage Format

Confluence uses a specific HTML storage format. For complex formatting:

```html
<!-- Code block -->
<ac:structured-macro ac:name="code">
  <ac:parameter ac:name="language">bash</ac:parameter>
  <ac:plain-text-body><![CDATA[kubectl get pods]]></ac:plain-text-body>
</ac:structured-macro>

<!-- Info panel -->
<ac:structured-macro ac:name="info">
  <ac:rich-text-body>
    <p>Important note here</p>
  </ac:rich-text-body>
</ac:structured-macro>

<!-- Warning panel -->
<ac:structured-macro ac:name="warning">
  <ac:rich-text-body>
    <p>Warning message</p>
  </ac:rich-text-body>
</ac:structured-macro>
```

## Output Formats

```bash
# JSON for scripting
devctl -o json confluence pages list --space DEV

# Get page IDs
devctl -o json confluence search "runbook" | jq '.[].content.id'
```

## Dry Run Mode

```bash
devctl --dry-run confluence pages create --space DEV --title "Test"
devctl --dry-run confluence runbook publish ./runbook.yaml --space OPS
```
