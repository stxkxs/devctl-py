# Getting Started

This guide walks through installing devctl, configuring credentials, and running your first commands.

## Prerequisites

- Python 3.11+
- AWS CLI configured (`aws configure`) or environment credentials
- Grafana Cloud API key (for Grafana commands)
- GitHub personal access token (for GitHub commands)

## Installation

### From source

```bash
git clone https://github.com/stxkxs/devctl.git
cd devctl

# Using pip
pip install -e .

# Using uv (faster)
uv pip install -e .
```

### Verify installation

```bash
devctl --version
devctl --help
```

## Configuration

### 1. Create config directory

```bash
mkdir -p ~/.devctl
```

### 2. Create configuration file

```bash
cp config.example.yaml ~/.devctl/config.yaml
```

Edit `~/.devctl/config.yaml`:

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
    github:
      org: your-org

  production:
    aws:
      profile: prod-account
      region: us-west-2
    grafana:
      url: https://prod.grafana.net
```

### 3. Set up credentials

Create `.env` file or export environment variables:

```bash
# Grafana Cloud
export DEVCTL_GRAFANA_API_KEY=glsa_xxxxxxxxxxxxxxxx

# GitHub
export DEVCTL_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx

# AWS (if not using ~/.aws/credentials)
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
```

## First Commands

### Verify AWS connectivity

```bash
# Check current identity
devctl aws iam whoami

# Expected output:
# ┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
# ┃ Property            ┃ Value                                                  ┃
# ┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
# │ Account             │ 123456789012                                           │
# │ Arn                 │ arn:aws:iam::123456789012:user/myuser                  │
# │ UserId              │ AIDAXXXXXXXXXXXXXXXXX                                  │
# └─────────────────────┴────────────────────────────────────────────────────────┘
```

### List AWS resources

```bash
# S3 buckets
devctl aws s3 ls

# EKS clusters
devctl aws eks list-clusters

# ECR repositories
devctl aws ecr list-repos
```

### Using different profiles

```bash
# Use production profile
devctl -p production aws iam whoami

# Or set environment variable
export DEVCTL_PROFILE=production
devctl aws iam whoami
```

### Output formats

```bash
# Table (default)
devctl aws s3 ls

# JSON (for scripting)
devctl -o json aws s3 ls

# YAML
devctl -o yaml aws s3 ls

# Pipe to jq
devctl -o json aws cost by-service | jq '.[] | select(.cost > 100)'
```

### Dry run mode

Preview what a command would do without executing:

```bash
devctl --dry-run aws ecr cleanup my-repo --keep 5
```

## Common First Tasks

### Check costs

```bash
# Last 30 days summary
devctl aws cost summary --days 30

# Top services by cost
devctl aws cost by-service --top 10
```

### ECR operations

```bash
# Login to ECR
devctl aws ecr login

# List images in a repo
devctl aws ecr list-images my-app

# Clean up old images (keep last 10)
devctl aws ecr cleanup my-app --keep 10 --dry-run
```

### EKS operations

```bash
# List clusters
devctl aws eks list-clusters

# Get kubeconfig for a cluster
devctl aws eks kubeconfig my-cluster

# Describe cluster
devctl aws eks describe my-cluster
```

### Grafana operations

```bash
# List dashboards
devctl grafana dashboards list

# Check datasource health
devctl grafana datasources health

# Create deployment annotation
devctl grafana annotations create "Deployed v1.2.3" --tags deployment
```

## Troubleshooting

### AWS credential errors

```bash
# Check AWS configuration
aws configure list

# Test with AWS CLI directly
aws sts get-caller-identity

# Verify devctl sees credentials
devctl -vvv aws iam whoami
```

### Grafana connection errors

```bash
# Verify API key is set
echo $DEVCTL_GRAFANA_API_KEY

# Test with verbose output
devctl -vvv grafana datasources list
```

### Permission errors

```bash
# Check IAM permissions
devctl aws iam whoami

# For specific service errors, verify IAM policy allows the action
# Example: s3:ListBucket for devctl aws s3 ls
```

## Next Steps

- [Configuration Guide](configuration.md) - Profiles, credentials, advanced config
- [AWS Commands](aws-commands.md) - Full AWS command reference
- [Workflows](workflows.md) - Automate multi-step operations
- [Predictive Scaling](predictive-scaling.md) - ML-powered auto-scaling
