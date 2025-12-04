# Grafana

Grafana operations for dashboards, alerts, datasources, annotations, and metrics.

## Overview

Grafana commands provide:
- **Dashboards** - List, export, import, backup dashboards
- **Alerts** - Monitor and manage alert rules and silences
- **Datasources** - Configure and test datasources
- **Annotations** - Create deployment and event markers
- **Metrics** - Query and check metrics through datasources

## Configuration

Configure Grafana access in `~/.devctl/config.yaml`:

```yaml
version: "1"
grafana:
  url: https://grafana.example.com
  api_key: ${GRAFANA_API_KEY}  # Or set GRAFANA_API_KEY env var
```

## Dashboards

### List Dashboards

```bash
# List all dashboards
devctl grafana dashboards list

# Filter by folder
devctl grafana dashboards list --folder my-folder
```

### Get Dashboard Details

```bash
devctl grafana dashboards get DASHBOARD_UID
```

### Export Dashboard

```bash
# Export to stdout
devctl grafana dashboards export abc123

# Export to file
devctl grafana dashboards export abc123 --output dashboard.json
```

### Import Dashboard

```bash
# Import from file
devctl grafana dashboards import dashboard.json

# Import to specific folder
devctl grafana dashboards import dashboard.json --folder devctl

# Overwrite existing
devctl grafana dashboards import dashboard.json --overwrite
```

### Backup All Dashboards

```bash
# Backup to directory
devctl grafana dashboards backup --output ./grafana-backup

# Backup specific folder
devctl grafana dashboards backup --folder production --output ./prod-backup
```

### Delete Dashboard

```bash
devctl grafana dashboards delete abc123

# Skip confirmation
devctl grafana dashboards delete abc123 --yes
```

## Dashboard Templates

Built-in dashboard templates for devctl workflows.

### List Templates

```bash
devctl grafana dashboards templates
```

Output:
```
Dashboard Templates (5 available)
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name                 ┃ Title                      ┃ Description               ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ deployment-overview  │ Deployment Overview        │ Track deployments...      │
│ incident-response    │ Incident Response          │ Real-time incident...     │
│ cost-overview        │ AWS Cost Overview          │ Track AWS costs...        │
│ oncall-overview      │ On-Call Overview           │ On-call metrics...        │
│ predictive-scaling   │ Predictive Scaling         │ Monitor predictive...     │
└──────────────────────┴────────────────────────────┴───────────────────────────┘
```

### View Template

```bash
# View template JSON
devctl grafana dashboards template deployment-overview

# Save to file
devctl grafana dashboards template incident-response -o dashboard.json
```

### Deploy Template

```bash
# Deploy single template
devctl grafana dashboards deploy-template deployment-overview

# Deploy to folder
devctl grafana dashboards deploy-template incident-response --folder devctl

# Overwrite existing
devctl grafana dashboards deploy-template cost-overview --overwrite

# Deploy all templates
devctl grafana dashboards deploy-all-templates --folder devctl
```

## Alerts

### List Alerts

```bash
# List all firing alerts
devctl grafana alerts list

# Filter by state
devctl grafana alerts list --state firing
devctl grafana alerts list --state pending
```

### Silence Alerts

```bash
# Silence by matcher
devctl grafana alerts silence --match alertname=HighCPU --duration 1h

# Silence with comment
devctl grafana alerts silence \
  --match severity=warning \
  --duration 2h \
  --comment "Maintenance window"
```

### List Silences

```bash
devctl grafana alerts silences
```

## Datasources

### List Datasources

```bash
devctl grafana datasources list
```

### Get Datasource Details

```bash
devctl grafana datasources get prometheus
```

### Test Datasource

```bash
devctl grafana datasources test prometheus
```

### Health Check All

```bash
devctl grafana datasources health
```

Output:
```
Datasource Health Check
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name            ┃ Type        ┃ Status   ┃ Message                ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ prometheus      │ prometheus  │ OK       │ Data source is working │
│ cloudwatch      │ cloudwatch  │ OK       │ Data source is working │
│ elasticsearch   │ elasticsearch│ ERROR    │ Connection refused    │
└─────────────────┴─────────────┴──────────┴────────────────────────┘
```

## Annotations

### Create Annotation

```bash
# Simple annotation
devctl grafana annotations create --text "Deployed api v1.2.3"

# With tags
devctl grafana annotations create \
  --text "Deployed api v1.2.3" \
  --tags deployment,api,production

# On specific dashboard
devctl grafana annotations create \
  --text "Config change" \
  --dashboard-uid abc123
```

### List Annotations

```bash
# Recent annotations
devctl grafana annotations list

# Filter by tags
devctl grafana annotations list --tags deployment

# Time range
devctl grafana annotations list --since 24h
```

## Metrics

Query metrics through Grafana datasources.

### Query Metrics

```bash
# Run PromQL query
devctl grafana metrics query prometheus 'up{job="api"}'

# With time range
devctl grafana metrics query prometheus 'rate(http_requests_total[5m])' --since 6h

# Custom step
devctl grafana metrics query prometheus 'cpu_usage' --step 300

# JSON output
devctl grafana metrics query prometheus 'memory_usage' --format json
```

### Get Current Value

```bash
# Instant query
devctl grafana metrics get prometheus 'up{job="api"}'

# Aggregated value
devctl grafana metrics get prometheus 'avg(rate(http_requests_total[5m]))'
```

### Check Threshold

Check if metrics cross thresholds - useful for CI/CD pipelines and canary deployments.

```bash
# Check if value > threshold
devctl grafana metrics check prometheus 'avg(cpu_usage)' --threshold 80

# Check if value < threshold
devctl grafana metrics check prometheus 'up{job="api"}' --threshold 1 --comparison lt

# Exit with code 1 if threshold breached
devctl grafana metrics check prometheus 'sum(rate(error_total[5m]))' \
  --threshold 10 \
  --comparison gt \
  --exit-code
```

**Comparison operators:**
| Operator | Description |
|----------|-------------|
| `gt` | Greater than (default) |
| `lt` | Less than |
| `ge` | Greater than or equal |
| `le` | Less than or equal |
| `eq` | Equal |

### List Available Metrics

```bash
# List metrics from datasource
devctl grafana metrics list prometheus

# Filter by pattern
devctl grafana metrics list prometheus --filter http
```

### List Metric Labels

```bash
# Show labels for a metric
devctl grafana metrics labels prometheus http_requests_total
```

Output:
```
Labels for http_requests_total
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Label       ┃ Cardinality  ┃ Values                          ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ job         │ 3            │ api, web, worker                │
│ method      │ 4            │ GET, POST, PUT, DELETE          │
│ status      │ 5            │ 200, 201, 400, 404, 500         │
│ endpoint    │ 12           │ /api/users, /api/orders ... (+7)│
└─────────────┴──────────────┴─────────────────────────────────┘
```

## Workflow Integration

### Deployment Annotations

```yaml
name: deploy-with-annotation
steps:
  - name: Deploy
    command: "!kubectl apply -f deployment.yaml"

  - name: Annotate deployment
    command: grafana annotations create
    params:
      text: "Deployed {{ service }} {{ version }}"
      tags: "deployment,{{ environment }},{{ service }}"
```

### Canary Deployment with Metrics Check

```yaml
name: canary-deploy
steps:
  - name: Deploy canary
    command: "!kubectl apply -f canary.yaml"

  - name: Wait for traffic
    command: "!sleep 300"

  - name: Check error rate
    command: grafana metrics check
    params:
      datasource: prometheus
      query: "sum(rate(http_requests_total{status=~'5..'}[5m])) / sum(rate(http_requests_total[5m])) * 100"
      threshold: 5
      comparison: lt
      exit-code: true
    on_failure: fail

  - name: Promote canary
    command: "!kubectl apply -f production.yaml"
```

## Best Practices

1. **Use annotations** - Mark deployments, incidents, and config changes
2. **Deploy dashboard templates** - Use built-in dashboards for consistency
3. **Check metrics in CI/CD** - Use `metrics check` for deployment gates
4. **Backup dashboards** - Regular backups before major changes
5. **Test datasources** - Verify connectivity before debugging issues

## Related Documentation

- [Workflows](workflows.md) - Automate Grafana operations
- [Predictive Scaling](predictive-scaling.md) - Scaling dashboards
- [Configuration](configuration.md) - Grafana setup
