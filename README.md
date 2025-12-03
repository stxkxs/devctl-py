# DevCtl

A Python CLI for unified DevOps operations across AWS, Grafana Cloud, and GitHub.

## Features

- **Unified Operations**: Single interface for AWS, Grafana, and GitHub
- **Profile Management**: Easy switching between environments (dev, staging, production)
- **Workflow Automation**: YAML-defined workflows with Jinja2 templating
- **Cost Analysis**: Cross-service cost reporting and optimization recommendations
- **Health Checks**: Comprehensive health monitoring for HTTP, TCP, ECS, and EKS
- **Rich Output**: Beautiful terminal output with tables, colors, and progress bars

## Installation

```bash
# Using pip
pip install -e .

# Using uv (recommended)
uv pip install -e .

# Development installation
pip install -e ".[dev]"
```

## Quick Start

```bash
# Configure credentials (copy and edit)
cp config.example.yaml ~/.devctl/config.yaml
cp .env.example .env

# Test AWS connectivity
devctl aws iam whoami

# List S3 buckets
devctl aws s3 ls

# Check Grafana health
devctl grafana datasources health

# List GitHub repos
devctl github repos list
```

## Configuration

DevCtl uses a layered configuration system:

1. **Default values** in code
2. **User config** at `~/.devctl/config.yaml`
3. **Project config** at `./devctl.yaml`
4. **Environment variables** (`DEVCTL_*`)
5. **CLI flags** (highest priority)

### Example Configuration

```yaml
version: "1"

global:
  output_format: table
  color: auto
  confirm_destructive: true

profiles:
  default:
    aws:
      profile: default
      region: us-east-1
    grafana:
      url: https://your-stack.grafana.net
      api_key: from_env
    github:
      token: from_env
      org: your-org

  production:
    aws:
      profile: prod
      region: us-west-2
```

### Environment Variables

```bash
# AWS
export DEVCTL_AWS_PROFILE=default
export DEVCTL_AWS_REGION=us-east-1

# Grafana
export DEVCTL_GRAFANA_URL=https://your-stack.grafana.net
export DEVCTL_GRAFANA_API_KEY=your-api-key

# GitHub
export DEVCTL_GITHUB_TOKEN=ghp_xxxxxxxxxxxx
export DEVCTL_GITHUB_ORG=your-org
```

## Command Reference

### Global Options

```
devctl [OPTIONS] COMMAND

Options:
  -p, --profile NAME    Configuration profile
  -o, --output FORMAT   Output format (table/json/yaml/raw)
  -v, --verbose         Increase verbosity (-v, -vv, -vvv)
  -q, --quiet           Suppress non-essential output
  --dry-run             Show what would happen
  --no-color            Disable colored output
  -c, --config FILE     Config file path
  --version             Show version
  -h, --help            Show help
```

### AWS Commands

```bash
# IAM
devctl aws iam whoami
devctl aws iam list-users
devctl aws iam list-roles --prefix AWSServiceRole
devctl aws iam assume arn:aws:iam::123456789012:role/MyRole
devctl aws iam unused-roles --days 90

# S3
devctl aws s3 ls
devctl aws s3 ls my-bucket --prefix logs/
devctl aws s3 size my-bucket --human
devctl aws s3 sync ./local s3://bucket/prefix
devctl aws s3 cost-analysis --days 30

# ECR
devctl aws ecr list-repos
devctl aws ecr list-images my-repo
devctl aws ecr login
devctl aws ecr cleanup my-repo --keep 10
devctl aws ecr scan my-repo:latest --wait

# EKS
devctl aws eks list-clusters
devctl aws eks describe my-cluster
devctl aws eks kubeconfig my-cluster
devctl aws eks nodegroups my-cluster --scale my-ng --count 3

# Cost Explorer
devctl aws cost summary --days 30
devctl aws cost by-service --top 10
devctl aws cost forecast
devctl aws cost rightsizing
devctl aws cost unused-resources

# Bedrock
devctl aws bedrock list-models
devctl aws bedrock invoke anthropic.claude-v2 --prompt "Hello"
devctl aws bedrock usage --days 7

# CloudWatch
devctl aws cloudwatch metrics AWS/EC2 --metric CPUUtilization
devctl aws cloudwatch logs /aws/lambda/my-function --tail
devctl aws cloudwatch alarms --state alarm
```

### Grafana Commands

```bash
# Dashboards
devctl grafana dashboards list
devctl grafana dashboards get abc123
devctl grafana dashboards export abc123 --output dashboard.json
devctl grafana dashboards import dashboard.json --folder MyFolder
devctl grafana dashboards backup --output ./backups

# Alerts
devctl grafana alerts list --state firing
devctl grafana alerts silence rule-uid --duration 1h
devctl grafana alerts rules list

# Datasources
devctl grafana datasources list
devctl grafana datasources test prometheus
devctl grafana datasources health

# Annotations
devctl grafana annotations create "Deployment v1.2.3" --tags deployment
devctl grafana annotations list --from -24h
```

### GitHub Commands

```bash
# Repositories
devctl github repos list
devctl github repos clone owner/repo
devctl github repos create new-repo --private

# Actions
devctl github actions list owner/repo
devctl github actions runs owner/repo --status completed
devctl github actions run owner/repo deploy.yml --ref main
devctl github actions logs owner/repo 12345

# Pull Requests
devctl github prs list owner/repo
devctl github prs create owner/repo "My PR" --head feature --base main
devctl github prs merge owner/repo 123 --method squash

# Releases
devctl github releases list owner/repo
devctl github releases create owner/repo v1.0.0 --notes "Initial release"
devctl github releases download owner/repo v1.0.0
```

### Ops Commands

```bash
# Health Checks
devctl ops health check my-service --type http
devctl ops health wait my-service --timeout 300
devctl ops health url https://api.example.com/health

# Cost Reports
devctl ops cost-report --days 30
devctl ops cost-report --format detailed
```

### Workflows

```bash
# Run a workflow
devctl workflow run deploy-service --var service_name=api --var env=prod

# Dry-run a workflow
devctl workflow dry-run deploy-service --var service_name=api

# List configured workflows
devctl workflow list

# Validate a workflow file
devctl workflow validate ./my-workflow.yaml
```

## Workflow Definition

Workflows are defined in YAML with Jinja2 templating:

```yaml
name: deploy-service
description: Deploy a service with health checks

vars:
  cluster: default-cluster
  timeout: 300

steps:
  - name: Build container
    command: aws ecr build
    params:
      repository: "{{ service_name }}"
      push: true

  - name: Deploy to ECS
    command: aws ecs deploy
    params:
      cluster: "{{ cluster }}"
      service: "{{ service_name }}"

  - name: Wait for healthy
    command: ops health wait
    params:
      target: "{{ service_name }}"
      type: ecs
    on_failure: continue

  - name: Create annotation
    command: grafana annotations create
    params:
      text: "Deployed {{ service_name }}"
      tags:
        - deployment
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/

# Run type checker
mypy src/

# Format code
ruff format src/
```

## Architecture

```
src/devctl/
├── cli.py              # Main CLI entry point
├── config.py           # Configuration management
├── core/
│   ├── context.py      # Shared context object
│   ├── output.py       # Output formatting
│   ├── exceptions.py   # Exception hierarchy
│   └── async_utils.py  # Async helpers
├── clients/
│   ├── aws.py          # AWS client factory
│   ├── grafana.py      # Grafana API client
│   └── github.py       # GitHub API client
├── commands/
│   ├── aws/            # AWS command groups
│   ├── grafana/        # Grafana commands
│   ├── github/         # GitHub commands
│   └── ops/            # DevOps commands
└── workflows/
    ├── engine.py       # Workflow executor
    └── schema.py       # Workflow validation
```

## License

MIT License
