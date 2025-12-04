# Unified Logs Commands

devctl provides unified log access across multiple sources: CloudWatch, Grafana Loki, and EKS pod logs.

## Configuration

```yaml
profiles:
  default:
    logs:
      default_source: cloudwatch  # cloudwatch, loki, eks
      default_time_range: 1h
      max_results: 1000
```

## Log Sources

| Source | Description |
|--------|-------------|
| `cloudwatch` | AWS CloudWatch Logs |
| `loki` | Grafana Loki |
| `eks` | EKS pod logs (via Kubernetes API) |
| `all` | Search all configured sources |

## Search Across Sources

```bash
# Search all sources
devctl logs search "error" --source all

# Search specific source
devctl logs search "error" --source cloudwatch

# With time range
devctl logs search "exception" --since 2h

# Limit results
devctl logs search "timeout" --limit 100
```

## CloudWatch Logs

### Basic log retrieval

```bash
# Get logs from a log group
devctl logs cloudwatch /aws/lambda/my-function

# With time range
devctl logs cloudwatch /aws/lambda/my-function --since 1h

# Tail logs (follow)
devctl logs cloudwatch /aws/lambda/my-function --tail

# Filter pattern
devctl logs cloudwatch /aws/ecs/my-cluster --filter "ERROR"

# Limit lines
devctl logs cloudwatch /aws/lambda/my-function --limit 500
```

### CloudWatch Insights queries

```bash
# Run an Insights query
devctl logs cloudwatch /aws/ecs/my-cluster \
  --insights "fields @timestamp, @message | filter @message like /ERROR/ | limit 50"

# Complex query
devctl logs cloudwatch /aws/lambda/my-function \
  --insights "fields @timestamp, @message, @requestId
    | filter @message like /Exception/
    | stats count() by bin(5m)
    | sort @timestamp desc"
```

### List log groups

```bash
# List all log groups
devctl logs cloudwatch --list-groups

# Filter by prefix
devctl logs cloudwatch --list-groups --prefix /aws/lambda/
```

## EKS Pod Logs

```bash
# Get logs from a pod
devctl logs eks my-pod

# With namespace
devctl logs eks my-pod -n production

# Follow logs
devctl logs eks my-pod -f

# Tail last N lines
devctl logs eks my-pod --tail 100

# From specific container
devctl logs eks my-pod -c sidecar

# Since duration
devctl logs eks my-pod --since 30m
```

## Log Tailing

Real-time log streaming:

```bash
# Tail CloudWatch logs
devctl logs tail cloudwatch /aws/lambda/my-function

# Tail EKS pod logs
devctl logs tail eks my-pod -n production

# With filter pattern
devctl logs tail cloudwatch /aws/ecs/cluster --filter "ERROR"
```

## Common Patterns

### Debug Lambda function

```bash
# Get recent errors
devctl logs cloudwatch /aws/lambda/my-function \
  --since 1h \
  --filter "ERROR"

# Check cold starts
devctl logs cloudwatch /aws/lambda/my-function \
  --insights "fields @timestamp, @message
    | filter @message like /INIT_START/
    | stats count() by bin(1h)"
```

### ECS container debugging

```bash
# Get container logs
devctl logs cloudwatch /aws/ecs/my-cluster/my-service \
  --since 30m

# Find memory issues
devctl logs cloudwatch /aws/ecs/my-cluster \
  --insights "fields @timestamp, @message
    | filter @message like /OutOfMemory/
    | limit 100"
```

### Kubernetes pod investigation

```bash
# Get recent logs
devctl logs eks my-pod -n production --tail 200

# Follow for real-time debugging
devctl logs eks my-pod -n production -f

# Check previous container (after restart)
devctl k8s pods logs my-pod --previous
```

### Cross-source error search

```bash
# Search for errors across all sources
devctl logs search "error|exception|failed" --source all --since 1h

# Export to JSON for analysis
devctl -o json logs search "timeout" --source cloudwatch > errors.json
```

## Output Formats

```bash
# Default (raw log lines)
devctl logs cloudwatch /aws/lambda/my-function

# JSON (structured)
devctl -o json logs cloudwatch /aws/lambda/my-function

# With timestamps
devctl logs eks my-pod --timestamps
```

## Environment Variables

```bash
# Default log source
export DEVCTL_LOGS_SOURCE=cloudwatch

# Default time range
export DEVCTL_LOGS_SINCE=1h

# Grafana Loki URL (for loki source)
export DEVCTL_GRAFANA_URL=https://logs.company.grafana.net
```
