# devctl

A unified CLI for AWS, Grafana, GitHub, Kubernetes, PagerDuty, ArgoCD, Slack, Confluence, and compliance operations. Built for DevOps engineers who work across these platforms daily.

## Installation

```bash
# Using pip
pip install -e .

# Using uv
uv pip install -e .

# Using Docker
docker build -t devctl .
docker run --rm -v ~/.aws:/home/devctl/.aws:ro devctl aws iam whoami

# Development
pip install -e ".[dev]"
```

## Quick Start

```bash
# Set up configuration
cp config.example.yaml ~/.devctl/config.yaml
cp .env.example .env

# Verify AWS access
devctl aws iam whoami

# List resources
devctl aws s3 ls
devctl aws eks list-clusters
devctl grafana dashboards list
devctl github repos list
```

## Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, configuration, first commands |
| [Configuration](docs/configuration.md) | Profiles, credentials, environment variables |
| [AWS Commands](docs/aws-commands.md) | IAM, S3, ECR, EKS, Cost Explorer, CloudWatch |
| [Kubernetes](docs/kubernetes.md) | Pod management, deployments, events, resources |
| [PagerDuty](docs/pagerduty.md) | Incidents, on-call schedules, services |
| [ArgoCD](docs/argocd.md) | Application sync, diff, rollback, status |
| [Logs](docs/logs.md) | Unified log search across CloudWatch, Loki, EKS |
| [Runbooks](docs/runbooks.md) | Executable runbooks in YAML/Markdown |
| [Deployments](docs/deployments.md) | Blue/Green, Canary, Rolling deployment strategies |
| [Slack](docs/slack.md) | Messages, notifications, channels |
| [Confluence](docs/confluence.md) | Pages, search, runbook publishing |
| [Compliance](docs/compliance.md) | PCI DSS scanning and access reviews |
| [Predictive Scaling](docs/predictive-scaling.md) | ML-powered auto-scaling with AWS Forecast + Karpenter |
| [Bedrock AI](docs/bedrock-ai.md) | Agents, batch inference, model comparison |
| [Jira](docs/jira.md) | Issues, boards, sprints, JQL search |
| [Workflows](docs/workflows.md) | YAML workflow engine with Jinja2 templating |
| [Docker](docs/docker.md) | Container usage, CI/CD integration |

## Command Overview

```
devctl
├── aws
│   ├── iam          # Identity and access management
│   ├── s3           # Object storage operations
│   ├── ecr          # Container registry
│   ├── eks          # Kubernetes clusters
│   ├── cost         # Cost analysis and optimization
│   ├── bedrock      # AI/ML with Bedrock
│   ├── forecast     # Predictive scaling with Forecast
│   └── cloudwatch   # Logs and metrics
├── grafana
│   ├── dashboards   # Dashboard management
│   ├── alerts       # Alert rules and silences
│   ├── datasources  # Data source configuration
│   ├── folders      # Folder organization
│   └── annotations  # Event annotations
├── github
│   ├── repos        # Repository operations
│   ├── actions      # Workflow runs
│   ├── prs          # Pull requests
│   ├── issues       # Issue tracking
│   └── releases     # Release management
├── jira
│   ├── issues       # Issue search, create, update, transition
│   ├── boards       # Agile board management
│   └── sprints      # Sprint operations
├── k8s
│   ├── pods         # Pod operations (list, logs, exec, delete)
│   ├── deployments  # Deployment management and rollouts
│   ├── nodes        # Node information
│   └── events       # Cluster events
├── pagerduty
│   ├── incidents    # Incident management (ack, resolve, escalate)
│   ├── oncall       # On-call schedules
│   ├── schedules    # Schedule management
│   └── services     # Service catalog
├── argocd
│   └── apps         # Application sync, diff, rollback, status
├── logs
│   ├── search       # Unified log search
│   ├── tail         # Real-time log streaming
│   ├── cloudwatch   # CloudWatch Logs / Insights
│   └── eks          # EKS pod logs
├── runbook
│   ├── run          # Execute runbooks
│   ├── list         # List available runbooks
│   ├── validate     # Validate runbook syntax
│   └── history      # Execution history
├── deploy
│   ├── create       # Create deployment (rolling/blue-green/canary)
│   ├── status       # Check deployment status
│   ├── promote      # Promote canary/blue-green
│   ├── rollback     # Rollback deployment
│   ├── abort        # Abort in-progress deployment
│   └── list         # List deployments
├── slack
│   ├── send         # Send messages
│   ├── notify       # Formatted notifications
│   ├── channels     # Channel management
│   ├── users        # User listing
│   └── thread       # Thread replies
├── confluence
│   ├── pages        # Page CRUD operations
│   ├── search       # Content search
│   ├── runbook      # Publish runbooks
│   └── incident     # Incident page creation
├── compliance
│   ├── pci          # PCI DSS scanning and reports
│   └── access-review # IAM access reviews
├── ops
│   ├── health       # Health checks
│   └── cost-report  # Cross-service cost analysis
└── workflow
    ├── run          # Execute workflows
    ├── list         # List workflows/templates
    ├── validate     # Validate YAML
    └── template     # View built-in templates
```

## Global Options

```bash
devctl [OPTIONS] COMMAND

  -p, --profile NAME    Configuration profile (default, production, etc.)
  -o, --output FORMAT   Output format: table, json, yaml, raw
  -v, --verbose         Increase verbosity (-v, -vv, -vvv)
  -q, --quiet           Suppress non-essential output
  --dry-run             Show what would happen without executing
  --no-color            Disable colored output
  -c, --config FILE     Custom config file path
  --version             Show version
  -h, --help            Show help
```

## Common Workflows

### Deploy with health check and annotation

```bash
# Build and push container
devctl aws ecr build my-app --tag v1.2.3 --push

# Update EKS deployment
kubectl set image deployment/my-app app=123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.2.3

# Wait for rollout
kubectl rollout status deployment/my-app

# Create Grafana annotation
devctl grafana annotations create "Deployed my-app v1.2.3" --tags deployment,my-app
```

### Cost investigation

```bash
# Get cost summary
devctl aws cost summary --days 30

# Find top spending services
devctl aws cost by-service --top 10

# Check for unused resources
devctl aws cost unused-resources

# Get rightsizing recommendations
devctl aws cost rightsizing
```

### Kubernetes operations

```bash
# List pods in namespace
devctl k8s pods list -n production

# Stream logs from a pod
devctl k8s pods logs my-app-pod -f --tail 100

# Execute command in pod
devctl k8s pods exec my-app-pod -- /bin/sh

# Check deployment status
devctl k8s deployments describe my-app -n production

# Rollback a deployment
devctl k8s deployments rollout undo my-app
```

### Incident response

```bash
# Create PagerDuty incident
devctl pagerduty incidents create "Database latency spike" --service db-service --urgency high

# Acknowledge incident
devctl pagerduty incidents ack INCIDENT_ID

# Check who's on-call
devctl pagerduty oncall

# Create incident channel in Slack
devctl slack channels create incident-2024-01-15

# Notify team
devctl slack notify --type incident --title "Database latency spike" --severity critical
```

### Deployment with canary

```bash
# Create canary deployment
devctl deploy create --name my-app --image myrepo/app:v2.0.0 --strategy canary

# Check deployment status
devctl deploy status DEPLOYMENT_ID

# Promote canary to full rollout
devctl deploy promote DEPLOYMENT_ID

# Or rollback if issues
devctl deploy rollback DEPLOYMENT_ID
```

### ArgoCD sync

```bash
# List applications
devctl argocd apps list

# Check app status
devctl argocd apps status my-app

# Preview changes
devctl argocd apps diff my-app

# Sync application
devctl argocd apps sync my-app --prune
```

### Runbook execution

```bash
# List available runbooks
devctl runbook list

# Validate runbook syntax
devctl runbook validate ./runbooks/restart-service.yaml

# Execute runbook with variables
devctl runbook run ./runbooks/restart-service.yaml --var service=api --var env=production
```

### Unified log search

```bash
# Search across all log sources
devctl logs search "error" --source all --since 1h

# Tail CloudWatch logs
devctl logs cloudwatch /aws/lambda/my-function --tail

# Search with Insights query
devctl logs cloudwatch /aws/ecs/my-cluster --insights "fields @timestamp, @message | filter @message like /ERROR/"
```

### PCI compliance scan

```bash
# Run full PCI scan
devctl compliance pci scan

# Generate HTML report
devctl compliance pci report --format html --output pci-report.html

# Run access review
devctl compliance access-review --days 90
```

### Predictive scaling setup

```bash
# Export historical metrics
devctl aws forecast export-metrics \
  --namespace AWS/ApplicationELB \
  --metric RequestCount \
  --days 90 \
  --output s3://my-bucket/forecast/metrics.csv

# Create and train predictor
devctl aws forecast datasets create --name api-traffic
devctl aws forecast predictors create --name api-predictor --dataset-group-arn ARN

# Generate scaling schedule
devctl aws forecast scaling recommend FORECAST_ARN \
  --item-id api-service \
  --min-nodes 2 \
  --requests-per-node 1000

# Apply to EKS with Karpenter
devctl aws forecast scaling apply \
  --cluster my-eks \
  --schedule /tmp/schedule.json
```

## Configuration

DevCtl uses layered configuration (lowest to highest priority):

1. Default values
2. `~/.devctl/config.yaml` (user defaults)
3. `./devctl.yaml` (project config)
4. Environment variables (`DEVCTL_*`)
5. CLI flags

See [Configuration Guide](docs/configuration.md) for details.

### Minimal config.yaml

```yaml
version: "1"

profiles:
  default:
    aws:
      profile: default
      region: us-east-1
    grafana:
      url: https://your-stack.grafana.net
    github:
      org: your-org
```

### Environment variables

```bash
# Core services
export DEVCTL_AWS_PROFILE=default
export DEVCTL_AWS_REGION=us-east-1
export DEVCTL_GRAFANA_API_KEY=glsa_xxxx
export DEVCTL_GITHUB_TOKEN=ghp_xxxx
export DEVCTL_JIRA_API_TOKEN=xxxx

# New integrations
export DEVCTL_PAGERDUTY_API_KEY=xxxx
export DEVCTL_ARGOCD_TOKEN=xxxx
export DEVCTL_SLACK_TOKEN=xoxb-xxxx
export DEVCTL_CONFLUENCE_API_TOKEN=xxxx
```

## Built-in Workflow Templates

```bash
# List available templates
devctl workflow list --templates

# View a template
devctl workflow template predictive-scaling

# Copy and customize
devctl workflow template predictive-scaling -o ./my-scaling.yaml
```

Available templates:
- `predictive-scaling` - Full ML pipeline setup for predictive auto-scaling
- `update-predictive-scaling` - Refresh scaling schedule from existing model
- `predictive-scaling-pipeline` - Continuous daily pipeline for metrics/predictions

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/

# Type check
mypy src/

# Format
ruff format src/
```

## Dependencies

| Package | Purpose |
|---------|---------|
| [click](https://click.palletsprojects.com/) | CLI framework |
| [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) | AWS SDK |
| [httpx](https://www.python-httpx.org/) | HTTP client for Grafana/GitHub/PagerDuty/ArgoCD/Slack/Confluence APIs |
| [rich](https://rich.readthedocs.io/) | Terminal formatting |
| [pydantic](https://docs.pydantic.dev/) | Configuration validation |
| [jinja2](https://jinja.palletsprojects.com/) | Workflow and runbook templating |
| [pyyaml](https://pyyaml.org/) | YAML parsing |
| [kubernetes](https://github.com/kubernetes-client/python) | Kubernetes API client |
| [markdown](https://python-markdown.github.io/) | Runbook markdown parsing |

## License

MIT
