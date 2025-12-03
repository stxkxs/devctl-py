# AWS Commands

Complete reference for all AWS commands in devctl.

## IAM

Identity and Access Management operations.

```bash
devctl aws iam [COMMAND]
```

| Command | Description |
|---------|-------------|
| `whoami` | Show current AWS identity |
| `list-users` | List IAM users |
| `list-roles` | List IAM roles |
| `list-policies` | List IAM policies |
| `assume ROLE_ARN` | Assume an IAM role |
| `unused-roles` | Find roles not used recently |

### Examples

```bash
# Current identity
devctl aws iam whoami

# List roles with prefix
devctl aws iam list-roles --prefix AWSServiceRole

# Find unused roles (security audit)
devctl aws iam unused-roles --days 90

# Assume role and get credentials
devctl aws iam assume arn:aws:iam::123456789012:role/AdminRole --duration 3600
```

## S3

Object storage operations with async support for bulk operations.

```bash
devctl aws s3 [COMMAND]
```

| Command | Description |
|---------|-------------|
| `ls [BUCKET]` | List buckets or objects |
| `size BUCKET` | Calculate bucket size |
| `sync SOURCE DEST` | Sync files between locations |
| `cp SOURCE DEST` | Copy files |
| `rm TARGET` | Delete files |
| `lifecycle BUCKET` | Manage lifecycle rules |
| `cost-analysis` | Analyze storage costs |

### Examples

```bash
# List all buckets
devctl aws s3 ls

# List objects in bucket with prefix
devctl aws s3 ls my-bucket --prefix logs/2024/

# Get bucket size
devctl aws s3 size my-bucket --human
# Output: 1.2 TB across 50,000 objects

# Sync local to S3
devctl aws s3 sync ./build s3://my-bucket/releases/v1.2.3

# Sync with delete (mirror)
devctl aws s3 sync ./build s3://my-bucket/releases/v1.2.3 --delete --dry-run

# Cost analysis
devctl aws s3 cost-analysis --days 30
```

### Cost Analysis Output

```
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Bucket             ┃ Size     ┃ Storage     ┃ Cost/mo  ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ logs-bucket        │ 500 GB   │ STANDARD    │ $11.50   │
│ backups-bucket     │ 2 TB     │ GLACIER     │ $8.00    │
│ assets-bucket      │ 100 GB   │ STANDARD_IA │ $1.25    │
└────────────────────┴──────────┴─────────────┴──────────┘
```

## ECR

Elastic Container Registry operations.

```bash
devctl aws ecr [COMMAND]
```

| Command | Description |
|---------|-------------|
| `list-repos` | List repositories |
| `list-images REPO` | List images in repository |
| `login` | Authenticate Docker to ECR |
| `build REPO` | Build and optionally push image |
| `scan REPO:TAG` | Run vulnerability scan |
| `cleanup REPO` | Delete old images |
| `lifecycle-policy REPO` | Manage lifecycle policies |

### Examples

```bash
# Login to ECR (configures Docker)
devctl aws ecr login

# List repositories
devctl aws ecr list-repos

# List images with vulnerabilities
devctl aws ecr list-images my-app --show-vulnerabilities

# Build and push
devctl aws ecr build my-app --tag v1.2.3 --push

# Build with custom Dockerfile
devctl aws ecr build my-app --dockerfile ./docker/Dockerfile.prod --push

# Scan for vulnerabilities
devctl aws ecr scan my-app:v1.2.3 --wait

# Cleanup old images (keep last 10)
devctl aws ecr cleanup my-app --keep 10

# Cleanup untagged images only
devctl aws ecr cleanup my-app --untagged-only

# Preview cleanup
devctl aws ecr cleanup my-app --keep 5 --dry-run
```

### Scan Output

```
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Severity            ┃ Count    ┃ Top Findings                           ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ CRITICAL            │ 0        │ -                                      │
│ HIGH                │ 2        │ CVE-2024-1234 (openssl), CVE-2024-5678 │
│ MEDIUM              │ 5        │ CVE-2024-9999 (curl)                   │
│ LOW                 │ 12       │ -                                      │
└─────────────────────┴──────────┴────────────────────────────────────────┘
```

## EKS

Elastic Kubernetes Service operations.

```bash
devctl aws eks [COMMAND]
```

| Command | Description |
|---------|-------------|
| `list-clusters` | List EKS clusters |
| `describe CLUSTER` | Show cluster details |
| `kubeconfig CLUSTER` | Update kubeconfig |
| `nodegroups CLUSTER` | List or scale node groups |
| `addons CLUSTER` | Manage cluster addons |
| `logs CLUSTER` | View control plane logs |
| `cost CLUSTER` | Analyze cluster costs |

### Examples

```bash
# List clusters
devctl aws eks list-clusters

# Get cluster details
devctl aws eks describe my-cluster

# Update kubeconfig
devctl aws eks kubeconfig my-cluster

# Update kubeconfig with alias
devctl aws eks kubeconfig my-cluster --alias prod-cluster

# List node groups
devctl aws eks nodegroups my-cluster --list

# Scale node group
devctl aws eks nodegroups my-cluster --scale my-nodegroup --count 5

# List addons
devctl aws eks addons my-cluster --list

# Install addon
devctl aws eks addons my-cluster --install vpc-cni

# Cluster cost breakdown
devctl aws eks cost my-cluster --breakdown
```

### Cost Breakdown Output

```
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Component           ┃ Instance Type ┃ Count       ┃ Cost/month  ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ Control Plane       │ -             │ 1           │ $72.00      │
│ workers-general     │ m5.large      │ 3           │ $210.24     │
│ workers-compute     │ c5.xlarge     │ 2           │ $248.20     │
│ Fargate             │ -             │ 5 pods      │ $45.00      │
├─────────────────────┼───────────────┼─────────────┼─────────────┤
│ Total               │               │             │ $575.44     │
└─────────────────────┴───────────────┴─────────────┴─────────────┘
```

## Cost Explorer

Cost analysis and optimization recommendations.

```bash
devctl aws cost [COMMAND]
```

| Command | Description |
|---------|-------------|
| `summary` | Overall cost summary |
| `by-service` | Costs broken down by service |
| `forecast` | Cost forecast |
| `anomalies` | Detect cost anomalies |
| `rightsizing` | EC2 rightsizing recommendations |
| `savings-plans` | Savings plan recommendations |
| `unused-resources` | Find unused resources |

### Examples

```bash
# Cost summary
devctl aws cost summary --days 30

# Top 10 services by cost
devctl aws cost by-service --top 10

# Cost forecast
devctl aws cost forecast --days 30

# Find anomalies
devctl aws cost anomalies --days 7

# Rightsizing recommendations
devctl aws cost rightsizing

# Find unused resources
devctl aws cost unused-resources
```

### Summary Output

```
AWS Cost Summary (Last 30 Days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total:           $12,456.78
Daily Average:   $415.23
vs Last Period:  +5.2%

Top Services:
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Service              ┃ Cost       ┃ % Total  ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━┩
│ Amazon EC2           │ $5,234.56  │ 42.0%    │
│ Amazon RDS           │ $2,345.67  │ 18.8%    │
│ Amazon S3            │ $1,234.56  │ 9.9%     │
│ AWS Lambda           │ $987.65    │ 7.9%     │
│ Amazon CloudFront    │ $654.32    │ 5.3%     │
└──────────────────────┴────────────┴──────────┘
```

### Unused Resources Output

```
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ Resource Type       ┃ Resource ID                    ┃ Est. Savings/mo ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ EC2 Instance        │ i-0123456789abcdef0 (stopped)  │ $50.00          │
│ EBS Volume          │ vol-0123456789abcdef0          │ $25.00          │
│ Elastic IP          │ 52.1.2.3 (unattached)          │ $3.60           │
│ Load Balancer       │ my-unused-alb                  │ $16.20          │
│ NAT Gateway         │ nat-0123456789abcdef0 (idle)   │ $32.40          │
├─────────────────────┼────────────────────────────────┼─────────────────┤
│ Total Potential     │                                │ $127.20         │
└─────────────────────┴────────────────────────────────┴─────────────────┘
```

## CloudWatch

Logs, metrics, and alarms.

```bash
devctl aws cloudwatch [COMMAND]
```

| Command | Description |
|---------|-------------|
| `logs GROUP` | View log events |
| `metrics NAMESPACE` | Query metrics |
| `alarms` | List CloudWatch alarms |

### Examples

```bash
# Tail logs
devctl aws cloudwatch logs /aws/lambda/my-function --tail

# Filter logs
devctl aws cloudwatch logs /aws/ecs/my-service --filter "ERROR"

# Get specific time range
devctl aws cloudwatch logs /aws/lambda/my-function --since 1h

# Query metrics
devctl aws cloudwatch metrics AWS/EC2 --metric CPUUtilization --since 24h

# List alarms in alarm state
devctl aws cloudwatch alarms --state alarm

# List all alarms
devctl aws cloudwatch alarms
```

## Forecast

Predictive scaling with AWS Forecast. See [Predictive Scaling Guide](predictive-scaling.md) for complete documentation.

```bash
devctl aws forecast [COMMAND]
```

| Command | Description |
|---------|-------------|
| `export-metrics` | Export CloudWatch metrics to CSV |
| `datasets` | Manage Forecast datasets |
| `predictors` | Manage ML predictors |
| `create` | Generate a forecast |
| `query` | Query forecast predictions |
| `scaling` | Predictive scaling for EKS/Karpenter |

### Quick Example

```bash
# Export metrics for training
devctl aws forecast export-metrics \
  --namespace AWS/ApplicationELB \
  --metric RequestCount \
  --days 90 \
  --output s3://bucket/metrics.csv

# Generate scaling recommendations
devctl aws forecast scaling recommend FORECAST_ARN \
  --item-id my-service \
  --requests-per-node 1000
```

## Bedrock

AI/ML operations with Amazon Bedrock. See [Bedrock AI Guide](bedrock-ai.md) for complete documentation.

```bash
devctl aws bedrock [COMMAND]
```

| Command | Description |
|---------|-------------|
| `list-models` | List available foundation models |
| `invoke MODEL` | Invoke a model |
| `usage` | Show usage statistics |
| `agents` | Manage Bedrock agents |
| `batch` | Batch inference jobs |
| `compare` | Compare model responses |

### Quick Example

```bash
# List models
devctl aws bedrock list-models --provider anthropic

# Invoke model
devctl aws bedrock invoke anthropic.claude-3-sonnet --prompt "Explain Kubernetes"

# Compare models
devctl aws bedrock compare \
  --models anthropic.claude-3-sonnet,anthropic.claude-3-haiku \
  --prompt "What is GitOps?"
```

## Common Patterns

### JSON Output for Scripting

```bash
# Get instance IDs
devctl -o json aws eks nodegroups my-cluster --list | jq -r '.[].nodegroupName'

# Get bucket names
devctl -o json aws s3 ls | jq -r '.[].Name'

# Filter by cost
devctl -o json aws cost by-service | jq '.[] | select(.cost > 100)'
```

### Dry Run for Safety

```bash
# Preview S3 sync
devctl --dry-run aws s3 sync ./local s3://bucket/prefix --delete

# Preview ECR cleanup
devctl --dry-run aws ecr cleanup my-repo --keep 5

# Preview role assumption
devctl --dry-run aws iam assume arn:aws:iam::123456789012:role/Role
```

### Cross-Region Operations

```bash
# Override region for single command
AWS_REGION=eu-west-1 devctl aws eks list-clusters

# Or use profile with different region
devctl -p eu-profile aws eks list-clusters
```

## Related Documentation

- [Predictive Scaling](predictive-scaling.md) - ML-powered auto-scaling
- [Bedrock AI](bedrock-ai.md) - AI/ML operations
- [Workflows](workflows.md) - Automate AWS operations
