# Predictive Scaling with AWS Forecast

ML-powered predictive auto-scaling for EKS clusters using [AWS Forecast](https://aws.amazon.com/forecast/) and [Karpenter](https://karpenter.sh/).

## Overview

Traditional auto-scaling reacts to current load. Predictive scaling anticipates future demand based on historical patterns, pre-scaling your cluster before traffic spikes.

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ CloudWatch  │───▶│ AWS Forecast│───▶│   devctl    │───▶│  Karpenter  │
│   Metrics   │    │  (ML Model) │    │  (Schedule) │    │  (NodePool) │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
     │                   │                  │                   │
     │   Historical      │   Predictions    │   Scaling         │   Pre-scaled
     │   Request Data    │   (next 24-48h)  │   Schedule        │   Nodes
     ▼                   ▼                  ▼                   ▼
```

## Prerequisites

| Requirement | Details |
|-------------|---------|
| EKS Cluster | v1.25+ with Karpenter v1.0+ installed |
| S3 Bucket | For storing metrics data |
| IAM Role | For Forecast to access S3 |
| CloudWatch Metrics | 30-90 days of historical data |
| Permissions | `forecast:*`, `s3:*`, `eks:*`, `cloudwatch:GetMetricData` |

### IAM Policy for Forecast

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "forecast:*"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-forecast-bucket",
        "arn:aws:s3:::your-forecast-bucket/*"
      ]
    }
  ]
}
```

### Forecast Service Role

Create a role that Forecast can assume to access S3:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "forecast.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

## Quick Start

### Option 1: Use the Workflow Template

```bash
# Copy the template
devctl workflow template predictive-scaling -o ./my-scaling.yaml

# Edit variables
vim ./my-scaling.yaml

# Run the workflow
devctl workflow run ./my-scaling.yaml \
  --var cluster=my-eks-cluster \
  --var service_name=api-service \
  --var s3_bucket=my-forecast-bucket \
  --var forecast_role=arn:aws:iam::123456789012:role/ForecastRole
```

### Option 2: Step-by-Step Commands

```bash
# 1. Export historical metrics (90 days recommended)
devctl aws forecast export-metrics \
  --namespace AWS/ApplicationELB \
  --metric RequestCount \
  --dimensions "LoadBalancer=app/my-alb/1234567890" \
  --item-id api-service \
  --days 90 \
  --output s3://my-bucket/forecast/api-service/metrics.csv

# 2. Create dataset
devctl aws forecast datasets create \
  --name api-service-traffic \
  --domain CUSTOM \
  --frequency H

# 3. Import data
devctl aws forecast datasets import \
  --name api-service-import \
  --s3-uri s3://my-bucket/forecast/api-service/metrics.csv \
  --role arn:aws:iam::123456789012:role/ForecastRole

# 4. Create predictor (trains ML model)
devctl aws forecast predictors create \
  --name api-service-predictor \
  --dataset-group-arn arn:aws:forecast:us-east-1:123456789012:dataset-group/api-service-group \
  --horizon 24 \
  --auto-ml

# 5. Generate forecast
devctl aws forecast create \
  --name api-service-forecast \
  --predictor arn:aws:forecast:us-east-1:123456789012:predictor/api-service-predictor

# 6. Get scaling recommendations
devctl aws forecast scaling recommend \
  arn:aws:forecast:us-east-1:123456789012:forecast/api-service-forecast \
  --item-id api-service \
  --min-nodes 2 \
  --requests-per-node 1000 \
  --buffer 0.2

# 7. Apply to cluster
devctl aws forecast scaling apply \
  --cluster my-eks-cluster \
  --schedule /tmp/api-service-schedule.json \
  --nodepool-name predictive
```

## Commands Reference

### export-metrics

Export CloudWatch metrics to Forecast-compatible CSV format.

```bash
devctl aws forecast export-metrics [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--namespace` | CloudWatch namespace | `AWS/ApplicationELB` |
| `--metric` | Metric name | `RequestCount` |
| `--dimensions` | Metric dimensions | - |
| `--item-id` | Identifier for this time series | Required |
| `--days` | Days of history to export | `90` |
| `--output` | Output path (local or s3://) | Required |

Output CSV format:

```csv
item_id,timestamp,target_value
api-service,2024-01-01T00:00:00Z,1523
api-service,2024-01-01T01:00:00Z,1845
api-service,2024-01-01T02:00:00Z,987
```

### datasets

Manage Forecast datasets.

```bash
# Create dataset
devctl aws forecast datasets create \
  --name my-dataset \
  --domain CUSTOM \
  --frequency H

# List datasets
devctl aws forecast datasets list

# Import data
devctl aws forecast datasets import \
  --name import-job-name \
  --s3-uri s3://bucket/path/data.csv \
  --role arn:aws:iam::123456789012:role/ForecastRole
```

| Frequency | Description |
|-----------|-------------|
| `Y` | Yearly |
| `M` | Monthly |
| `W` | Weekly |
| `D` | Daily |
| `H` | Hourly |
| `30min` | 30 minutes |
| `15min` | 15 minutes |
| `10min` | 10 minutes |
| `5min` | 5 minutes |
| `1min` | 1 minute |

### predictors

Manage ML predictors.

```bash
# Create with AutoML (recommended)
devctl aws forecast predictors create \
  --name my-predictor \
  --dataset-group-arn arn:aws:forecast:...:dataset-group/my-group \
  --horizon 24 \
  --auto-ml

# Create with specific algorithm
devctl aws forecast predictors create \
  --name my-predictor \
  --dataset-group-arn arn:aws:forecast:...:dataset-group/my-group \
  --horizon 24 \
  --algorithm arn:aws:forecast:::algorithm/Deep_AR_Plus

# List predictors
devctl aws forecast predictors list

# Describe predictor (shows accuracy metrics)
devctl aws forecast predictors describe PREDICTOR_ARN
```

### scaling recommend

Generate Karpenter scaling recommendations from forecast.

```bash
devctl aws forecast scaling recommend FORECAST_ARN [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--item-id` | Time series identifier | Required |
| `--min-nodes` | Minimum nodes to maintain | `2` |
| `--requests-per-node` | Capacity per node | `1000` |
| `--instance-type` | Node instance type | `m5.large` |
| `--buffer` | Buffer percentage | `0.2` (20%) |
| `--output` | Output format | `table` |

Output:

```
Scaling Recommendations for api-service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Time                ┃ Predicted RPS ┃ Raw Nodes ┃ With Buffer   ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ 2024-01-15 00:00    │ 2,500         │ 3         │ 4             │
│ 2024-01-15 01:00    │ 1,800         │ 2         │ 3             │
│ 2024-01-15 02:00    │ 1,200         │ 2         │ 2             │
│ ...                 │               │           │               │
│ 2024-01-15 12:00    │ 8,500         │ 9         │ 11            │
│ 2024-01-15 13:00    │ 9,200         │ 10        │ 12            │
└─────────────────────┴───────────────┴───────────┴───────────────┘

Schedule saved to: /tmp/api-service-schedule.json
```

### scaling apply

Apply scaling schedule to EKS cluster via Karpenter NodePool.

```bash
devctl aws forecast scaling apply [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--cluster` | EKS cluster name | Required |
| `--schedule` | Path to schedule JSON | Required |
| `--nodepool-name` | Karpenter NodePool name | `predictive` |

This creates/updates a Karpenter NodePool with scheduled scaling limits:

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: predictive
spec:
  template:
    spec:
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: predictive
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["m5.large", "m5.xlarge"]
  limits:
    cpu: "100"      # Adjusted based on predictions
    memory: "400Gi"
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
```

### scaling deploy-pipeline

Deploy a continuous pipeline as a Kubernetes CronJob.

```bash
devctl aws forecast scaling deploy-pipeline [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--cluster` | EKS cluster name | Required |
| `--forecast-arn` | Forecast ARN to query | Required |
| `--service-name` | Service identifier | Required |
| `--schedule` | Cron schedule | `0 0 * * *` (daily) |
| `--namespace` | Kubernetes namespace | `devctl-system` |

## Continuous Pipeline

For production use, set up a continuous pipeline that:

1. Exports new metrics daily
2. Queries the latest predictions
3. Updates Karpenter NodePool limits

### Using Workflow Template

```bash
# Deploy using the pipeline workflow template
devctl workflow run predictive-scaling-pipeline.yaml \
  --var cluster=my-cluster \
  --var service_name=api-service \
  --var s3_bucket=my-bucket \
  --var forecast_role=arn:aws:iam::123456789012:role/ForecastRole \
  --var dataset_arn=arn:aws:forecast:...:dataset/my-dataset
```

### Using deploy-pipeline Command

```bash
devctl aws forecast scaling deploy-pipeline \
  --cluster my-cluster \
  --forecast-arn arn:aws:forecast:us-east-1:123456789012:forecast/my-forecast \
  --service-name api-service \
  --schedule "0 2 * * *"  # Run at 2 AM daily
```

This creates:

| Resource | Description |
|----------|-------------|
| `Namespace` | `devctl-system` |
| `ConfigMap` | Pipeline configuration |
| `CronJob` | Runs daily to update predictions |
| `ServiceAccount` | With IRSA annotation for AWS access |
| `ClusterRole` | Permission to update NodePools |
| `ClusterRoleBinding` | Binds role to service account |

## Retraining

ML models need periodic retraining as patterns change.

### Weekly Retraining Schedule

```bash
# Run this weekly via cron or CI/CD
devctl aws forecast predictors create \
  --name api-predictor-$(date +%Y%m%d) \
  --dataset-group-arn arn:aws:forecast:...:dataset-group/my-group \
  --horizon 24 \
  --auto-ml

# Wait for training (can take 30-60 minutes)
# Then create new forecast
devctl aws forecast create \
  --name api-forecast-$(date +%Y%m%d) \
  --predictor arn:aws:forecast:...:predictor/api-predictor-$(date +%Y%m%d)
```

### Cleanup Old Resources

```bash
# List old forecasts
devctl aws forecast list

# Delete forecasts older than 30 days (manual for now)
aws forecast delete-forecast --forecast-arn arn:aws:forecast:...:forecast/old-forecast
```

## Cost Considerations

| Resource | Pricing |
|----------|---------|
| Forecast Dataset Storage | $0.088/GB/month |
| Forecast Training | $0.24/hour |
| Forecast Predictions | $0.60/1000 predictions |
| S3 Storage | ~$0.023/GB/month |

Typical monthly cost for one service: **$10-50/month**

Savings from right-sizing and pre-scaling often exceed this cost significantly.

## Troubleshooting

### No predictions available

```bash
# Check forecast status
devctl aws forecast list

# Verify the forecast completed successfully
aws forecast describe-forecast --forecast-arn arn:aws:forecast:...
```

### Predictor training failed

```bash
# Check predictor status
devctl aws forecast predictors describe PREDICTOR_ARN

# Common issues:
# - Not enough data (need 30+ days)
# - Data format incorrect
# - Timestamps not in UTC
```

### NodePool not scaling

```bash
# Check NodePool status
devctl aws forecast scaling status --cluster my-cluster --nodepool predictive

# Verify Karpenter is running
kubectl get pods -n karpenter

# Check Karpenter logs
kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter
```

## Best Practices

1. **Start with 90 days of data** - More history = better predictions
2. **Use hourly frequency** - Good balance of granularity and noise
3. **Set appropriate buffers** - 20-30% buffer for safety margin
4. **Monitor prediction accuracy** - Compare predictions to actuals
5. **Retrain weekly** - Keep models fresh with recent patterns
6. **Use multiple item_ids** - Separate models for different services/endpoints

## Related Documentation

- [AWS Forecast Developer Guide](https://docs.aws.amazon.com/forecast/latest/dg/what-is-forecast.html)
- [Karpenter Documentation](https://karpenter.sh/docs/)
- [Karpenter NodePool API](https://karpenter.sh/docs/concepts/nodepools/)
- [Workflows](workflows.md) - Automate the pipeline
