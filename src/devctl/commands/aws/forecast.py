"""AWS Forecast commands for predictive auto-scaling and capacity planning."""

import csv
import io
import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError


@click.group()
@pass_context
def forecast(ctx: DevCtlContext) -> None:
    """Predictive scaling with AWS Forecast.

    ML-powered capacity planning and auto-scaling predictions for EKS/Karpenter.

    \b
    Workflow:
        1. Export metrics:  devctl aws forecast export-metrics --namespace AWS/ELB
        2. Create dataset:  devctl aws forecast datasets create --name my-traffic
        3. Import data:     devctl aws forecast datasets import DATASET_ARN --s3-uri s3://...
        4. Train model:     devctl aws forecast predictors create --name my-predictor
        5. Generate:        devctl aws forecast create --name my-forecast --predictor ARN
        6. Get schedule:    devctl aws forecast scaling recommend FORECAST_ARN --item-id svc
        7. Apply:           devctl aws forecast scaling apply --cluster my-eks --schedule file

    \b
    Examples:
        devctl aws forecast export-metrics --namespace AWS/ApplicationELB --metric RequestCount
        devctl aws forecast scaling recommend FORECAST_ARN --item-id api-service
    """
    pass


# =============================================================================
# Metrics Export (CloudWatch -> Forecast format)
# =============================================================================

@forecast.command("export-metrics")
@click.option("--namespace", required=True, help="CloudWatch namespace (e.g., AWS/ApplicationELB, AWS/ECS)")
@click.option("--metric", required=True, help="Metric name (e.g., RequestCount, CPUUtilization)")
@click.option("--dimensions", multiple=True, help="Dimensions as Name=Value (can specify multiple)")
@click.option("--item-id", required=True, help="Item ID for Forecast (e.g., service name)")
@click.option("--days", type=int, default=90, help="Days of historical data to export")
@click.option("--period", type=int, default=3600, help="Period in seconds (3600=hourly)")
@click.option("--output", "output_path", required=True, help="Output path: local file or s3://bucket/path")
@click.option("--stat", default="Sum", type=click.Choice(["Sum", "Average", "Maximum", "Minimum"]), help="Statistic")
@pass_context
def export_metrics(
    ctx: DevCtlContext,
    namespace: str,
    metric: str,
    dimensions: tuple[str, ...],
    item_id: str,
    days: int,
    period: int,
    output_path: str,
    stat: str,
) -> None:
    """Export CloudWatch metrics to Forecast-compatible CSV.

    Exports historical metrics and formats them for AWS Forecast import.
    Output can be a local file or S3 URI.

    \b
    Examples:
        # Export ALB request counts
        devctl aws forecast export-metrics \\
            --namespace AWS/ApplicationELB \\
            --metric RequestCount \\
            --dimensions LoadBalancer=app/my-alb/1234567890 \\
            --item-id api-service \\
            --output s3://my-bucket/forecast-data/traffic.csv

        # Export ECS CPU utilization
        devctl aws forecast export-metrics \\
            --namespace AWS/ECS \\
            --metric CPUUtilization \\
            --dimensions ClusterName=prod,ServiceName=api \\
            --item-id api-service \\
            --output ./metrics.csv
    """
    try:
        cloudwatch = ctx.aws.cloudwatch

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)

        # Parse dimensions
        dim_list = []
        for dim in dimensions:
            if "=" in dim:
                name, value = dim.split("=", 1)
                dim_list.append({"Name": name, "Value": value})

        ctx.output.print_info(f"Exporting {namespace}/{metric} for last {days} days...")

        # Fetch metrics
        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric,
            Dimensions=dim_list,
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=[stat],
        )

        datapoints = response.get("Datapoints", [])

        if not datapoints:
            ctx.output.print_warning("No datapoints found for the specified metric")
            return

        # Sort by timestamp
        datapoints.sort(key=lambda x: x["Timestamp"])

        ctx.output.print_info(f"Found {len(datapoints)} datapoints")

        # Format for AWS Forecast
        # Required columns: item_id, timestamp, target_value
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["item_id", "timestamp", "target_value"])

        for dp in datapoints:
            timestamp = dp["Timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            value = dp.get(stat, 0)
            writer.writerow([item_id, timestamp, value])

        csv_content = csv_buffer.getvalue()

        # Write output
        if output_path.startswith("s3://"):
            # Upload to S3
            s3 = ctx.aws.s3
            bucket, key = output_path[5:].split("/", 1)

            if ctx.dry_run:
                ctx.log_dry_run("upload to S3", {"bucket": bucket, "key": key})
                return

            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=csv_content.encode("utf-8"),
                ContentType="text/csv",
            )
            ctx.output.print_success(f"Uploaded to {output_path}")
        else:
            # Write to local file
            if ctx.dry_run:
                ctx.log_dry_run("write file", {"path": output_path})
                return

            with open(output_path, "w") as f:
                f.write(csv_content)
            ctx.output.print_success(f"Written to {output_path}")

        ctx.output.print_info(f"\nData format (first 3 rows):")
        for line in csv_content.split("\n")[:4]:
            ctx.output.print(f"  {line}")

        ctx.output.print_info(f"\nNext step: Import this data into a Forecast dataset:")
        ctx.output.print(f"  devctl aws forecast datasets create --name {item_id}-traffic --frequency H")
        if output_path.startswith("s3://"):
            ctx.output.print(f"  devctl aws forecast datasets import DATASET_ARN --s3-uri {output_path} --role ROLE_ARN")

    except ClientError as e:
        raise AWSError(f"Failed to export metrics: {e}")


# =============================================================================
# Dataset Management
# =============================================================================

@forecast.group("datasets")
@pass_context
def datasets(ctx: DevCtlContext) -> None:
    """Manage forecast datasets.

    \b
    Examples:
        devctl aws forecast datasets list
        devctl aws forecast datasets create --name traffic-data --domain CUSTOM
    """
    pass


@datasets.command("list")
@pass_context
def datasets_list(ctx: DevCtlContext) -> None:
    """List forecast datasets."""
    try:
        forecast_client = ctx.aws.forecast
        response = forecast_client.list_datasets()
        datasets_data = response.get("Datasets", [])

        if not datasets_data:
            ctx.output.print_info("No datasets found")
            return

        data = []
        for ds in datasets_data:
            data.append({
                "Name": ds.get("DatasetName", "-")[:30],
                "Type": ds.get("DatasetType", "-"),
                "Domain": ds.get("Domain", "-"),
                "Created": ds.get("CreationTime").strftime("%Y-%m-%d") if ds.get("CreationTime") else "-",
            })

        ctx.output.print_data(
            data,
            headers=["Name", "Type", "Domain", "Created"],
            title=f"Forecast Datasets ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list datasets: {e}")


@datasets.command("create")
@click.option("--name", required=True, help="Dataset name")
@click.option("--domain", type=click.Choice([
    "RETAIL", "CUSTOM", "INVENTORY_PLANNING", "EC2_CAPACITY",
    "WORK_FORCE", "WEB_TRAFFIC", "METRICS"
]), default="CUSTOM", help="Dataset domain")
@click.option("--type", "dataset_type", type=click.Choice([
    "TARGET_TIME_SERIES", "RELATED_TIME_SERIES", "ITEM_METADATA"
]), default="TARGET_TIME_SERIES", help="Dataset type")
@click.option("--frequency", default="H", help="Data frequency (H=hourly, D=daily, W=weekly, M=monthly)")
@pass_context
def datasets_create(
    ctx: DevCtlContext,
    name: str,
    domain: str,
    dataset_type: str,
    frequency: str,
) -> None:
    """Create a forecast dataset."""
    if ctx.dry_run:
        ctx.log_dry_run("create dataset", {
            "name": name,
            "domain": domain,
            "type": dataset_type,
        })
        return

    try:
        forecast_client = ctx.aws.forecast

        # Default schema for target time series
        schema = {
            "Attributes": [
                {"AttributeName": "timestamp", "AttributeType": "timestamp"},
                {"AttributeName": "target_value", "AttributeType": "float"},
                {"AttributeName": "item_id", "AttributeType": "string"},
            ]
        }

        response = forecast_client.create_dataset(
            DatasetName=name,
            Domain=domain,
            DatasetType=dataset_type,
            DataFrequency=frequency,
            Schema=schema,
        )

        ctx.output.print_success(f"Dataset created: {name}")
        ctx.output.print_info(f"ARN: {response['DatasetArn']}")

    except ClientError as e:
        raise AWSError(f"Failed to create dataset: {e}")


@datasets.command("import")
@click.argument("dataset_arn")
@click.option("--name", required=True, help="Import job name")
@click.option("--s3-uri", required=True, help="S3 URI for the data (s3://bucket/path/data.csv)")
@click.option("--role", required=True, help="IAM role ARN with S3 access")
@click.option("--format", "data_format", default="CSV", type=click.Choice(["CSV", "PARQUET"]))
@pass_context
def datasets_import(
    ctx: DevCtlContext,
    dataset_arn: str,
    name: str,
    s3_uri: str,
    role: str,
    data_format: str,
) -> None:
    """Import data into a dataset."""
    if ctx.dry_run:
        ctx.log_dry_run("import dataset", {
            "dataset": dataset_arn,
            "s3_uri": s3_uri,
        })
        return

    try:
        forecast_client = ctx.aws.forecast

        response = forecast_client.create_dataset_import_job(
            DatasetImportJobName=name,
            DatasetArn=dataset_arn,
            DataSource={
                "S3Config": {
                    "Path": s3_uri,
                    "RoleArn": role,
                }
            },
            Format=data_format,
        )

        ctx.output.print_success(f"Import job started: {name}")
        ctx.output.print_info(f"ARN: {response['DatasetImportJobArn']}")

    except ClientError as e:
        raise AWSError(f"Failed to create import job: {e}")


# =============================================================================
# Predictor Management
# =============================================================================

@forecast.group("predictors")
@pass_context
def predictors(ctx: DevCtlContext) -> None:
    """Manage ML predictors.

    \b
    Examples:
        devctl aws forecast predictors list
        devctl aws forecast predictors create --name my-predictor --dataset-group GROUP_ARN
    """
    pass


@predictors.command("list")
@pass_context
def predictors_list(ctx: DevCtlContext) -> None:
    """List predictors."""
    try:
        forecast_client = ctx.aws.forecast
        response = forecast_client.list_predictors()
        predictors_data = response.get("Predictors", [])

        if not predictors_data:
            ctx.output.print_info("No predictors found")
            return

        data = []
        for pred in predictors_data:
            data.append({
                "Name": pred.get("PredictorName", "-")[:30],
                "Status": pred.get("Status", "-"),
                "Created": pred.get("CreationTime").strftime("%Y-%m-%d") if pred.get("CreationTime") else "-",
            })

        ctx.output.print_data(
            data,
            headers=["Name", "Status", "Created"],
            title=f"Predictors ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list predictors: {e}")


@predictors.command("create")
@click.option("--name", required=True, help="Predictor name")
@click.option("--dataset-group", required=True, help="Dataset group ARN")
@click.option("--horizon", type=int, default=24, help="Forecast horizon (number of time points)")
@click.option("--frequency", default="H", help="Forecast frequency")
@click.option("--auto-ml/--no-auto-ml", default=True, help="Use AutoML to select best algorithm")
@pass_context
def predictors_create(
    ctx: DevCtlContext,
    name: str,
    dataset_group: str,
    horizon: int,
    frequency: str,
    auto_ml: bool,
) -> None:
    """Create an AutoML predictor."""
    if ctx.dry_run:
        ctx.log_dry_run("create predictor", {
            "name": name,
            "dataset_group": dataset_group,
            "horizon": horizon,
        })
        return

    try:
        forecast_client = ctx.aws.forecast

        response = forecast_client.create_auto_predictor(
            PredictorName=name,
            ForecastHorizon=horizon,
            ForecastFrequency=frequency,
            DataConfig={
                "DatasetGroupArn": dataset_group,
            },
        )

        ctx.output.print_success(f"Predictor creation started: {name}")
        ctx.output.print_info(f"ARN: {response['PredictorArn']}")
        ctx.output.print_info("Note: Training may take 30-60 minutes depending on data size")

    except ClientError as e:
        raise AWSError(f"Failed to create predictor: {e}")


@predictors.command("describe")
@click.argument("predictor_arn")
@pass_context
def predictors_describe(ctx: DevCtlContext, predictor_arn: str) -> None:
    """Describe a predictor."""
    try:
        forecast_client = ctx.aws.forecast
        response = forecast_client.describe_auto_predictor(PredictorArn=predictor_arn)

        data = {
            "Name": response.get("PredictorName"),
            "ARN": response.get("PredictorArn"),
            "Status": response.get("Status"),
            "Forecast Horizon": response.get("ForecastHorizon"),
            "Forecast Frequency": response.get("ForecastFrequency"),
            "Dataset Group": response.get("DataConfig", {}).get("DatasetGroupArn"),
            "Created": response.get("CreationTime").strftime("%Y-%m-%d %H:%M") if response.get("CreationTime") else "-",
            "Last Modified": response.get("LastModificationTime").strftime("%Y-%m-%d %H:%M") if response.get("LastModificationTime") else "-",
        }

        ctx.output.print_data(data, title="Predictor Details")

        # Show accuracy metrics if available
        try:
            metrics_response = forecast_client.get_accuracy_metrics(PredictorArn=predictor_arn)
            metrics = metrics_response.get("PredictorEvaluationResults", [])
            if metrics:
                ctx.output.print_info("\nAccuracy Metrics:")
                for metric in metrics:
                    test_windows = metric.get("TestWindows", [])
                    for window in test_windows:
                        wape = window.get("Metrics", {}).get("WAPE")
                        rmse = window.get("Metrics", {}).get("RMSE")
                        if wape is not None:
                            ctx.output.print(f"  WAPE: {wape:.4f}")
                        if rmse is not None:
                            ctx.output.print(f"  RMSE: {rmse:.4f}")
        except ClientError:
            pass

    except ClientError as e:
        raise AWSError(f"Failed to describe predictor: {e}")


# =============================================================================
# Forecast Generation & Query
# =============================================================================

@forecast.command("create")
@click.option("--name", required=True, help="Forecast name")
@click.option("--predictor", required=True, help="Predictor ARN")
@click.option("--quantiles", default="0.1,0.5,0.9", help="Forecast quantiles (comma-separated)")
@pass_context
def create_forecast(
    ctx: DevCtlContext,
    name: str,
    predictor: str,
    quantiles: str,
) -> None:
    """Generate a forecast from a trained predictor."""
    if ctx.dry_run:
        ctx.log_dry_run("create forecast", {
            "name": name,
            "predictor": predictor,
        })
        return

    try:
        forecast_client = ctx.aws.forecast

        quantile_list = [q.strip() for q in quantiles.split(",")]

        response = forecast_client.create_forecast(
            ForecastName=name,
            PredictorArn=predictor,
            ForecastTypes=quantile_list,
        )

        ctx.output.print_success(f"Forecast generation started: {name}")
        ctx.output.print_info(f"ARN: {response['ForecastArn']}")

    except ClientError as e:
        raise AWSError(f"Failed to create forecast: {e}")


@forecast.command("list")
@pass_context
def list_forecasts(ctx: DevCtlContext) -> None:
    """List generated forecasts."""
    try:
        forecast_client = ctx.aws.forecast
        response = forecast_client.list_forecasts()
        forecasts = response.get("Forecasts", [])

        if not forecasts:
            ctx.output.print_info("No forecasts found")
            return

        data = []
        for f in forecasts:
            data.append({
                "Name": f.get("ForecastName", "-")[:30],
                "Status": f.get("Status", "-"),
                "Created": f.get("CreationTime").strftime("%Y-%m-%d") if f.get("CreationTime") else "-",
            })

        ctx.output.print_data(
            data,
            headers=["Name", "Status", "Created"],
            title=f"Forecasts ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list forecasts: {e}")


@forecast.command("query")
@click.argument("forecast_arn")
@click.option("--item-id", required=True, help="Item ID to query (e.g., service name)")
@click.option("--start", help="Start time (ISO format, defaults to now)")
@click.option("--end", help="End time (ISO format, defaults to forecast horizon)")
@pass_context
def query_forecast(
    ctx: DevCtlContext,
    forecast_arn: str,
    item_id: str,
    start: str | None,
    end: str | None,
) -> None:
    """Query forecast predictions for an item."""
    try:
        forecastquery = ctx.aws.forecastquery

        filters = {"item_id": item_id}

        if start:
            filters["start_date"] = start
        if end:
            filters["end_date"] = end

        response = forecastquery.query_forecast(
            ForecastArn=forecast_arn,
            Filters=filters,
        )

        predictions = response.get("Forecast", {}).get("Predictions", {})

        if not predictions:
            ctx.output.print_info(f"No predictions found for item: {item_id}")
            return

        # Display predictions for each quantile
        ctx.output.print_info(f"Forecast for: {item_id}\n")

        for quantile, values in predictions.items():
            ctx.output.print_info(f"Quantile {quantile}:")
            data = []
            for point in values[:24]:  # Show first 24 points
                data.append({
                    "Timestamp": point.get("Timestamp", "-"),
                    "Value": f"{point.get('Value', 0):.2f}",
                })

            ctx.output.print_data(data, headers=["Timestamp", "Value"])
            ctx.output.print("")

    except ClientError as e:
        raise AWSError(f"Failed to query forecast: {e}")


# =============================================================================
# Predictive Auto-Scaling with EKS + Karpenter
# =============================================================================

@forecast.group("scaling")
@pass_context
def scaling(ctx: DevCtlContext) -> None:
    """Predictive auto-scaling for EKS with Karpenter.

    \b
    Examples:
        devctl aws forecast scaling recommend FORECAST_ARN --item my-service
        devctl aws forecast scaling generate-nodepool --schedule schedule.json
        devctl aws forecast scaling apply --cluster my-cluster --nodepool default
    """
    pass


@scaling.command("recommend")
@click.argument("forecast_arn")
@click.option("--item-id", required=True, help="Item ID (service/workload name)")
@click.option("--min-nodes", type=int, default=2, help="Minimum node count")
@click.option("--requests-per-node", type=int, default=1000, help="Requests each node can handle")
@click.option("--buffer", type=float, default=0.2, help="Capacity buffer (0.2 = 20% extra)")
@click.option("--hours", type=int, default=24, help="Hours to forecast")
@click.option("--instance-type", default="m5.large", help="Target instance type for calculations")
@pass_context
def scaling_recommend(
    ctx: DevCtlContext,
    forecast_arn: str,
    item_id: str,
    min_nodes: int,
    requests_per_node: int,
    buffer: float,
    hours: int,
    instance_type: str,
) -> None:
    """Generate Karpenter scaling recommendations from forecast.

    Uses ML predictions to recommend node capacity for each hour.
    Outputs a schedule that can be used to configure Karpenter NodePools.
    """
    try:
        forecastquery = ctx.aws.forecastquery

        response = forecastquery.query_forecast(
            ForecastArn=forecast_arn,
            Filters={"item_id": item_id},
        )

        predictions = response.get("Forecast", {}).get("Predictions", {})

        # Use p90 (90th percentile) for capacity planning
        p90_key = None
        for key in predictions.keys():
            if "0.9" in key or "p90" in key.lower():
                p90_key = key
                break

        if not p90_key:
            p90_key = list(predictions.keys())[0] if predictions else None

        if not p90_key:
            ctx.output.print_error("No prediction data available")
            return

        values = predictions[p90_key][:hours]

        ctx.output.print_info(f"Karpenter Scaling Recommendations for: {item_id}")
        ctx.output.print_info(f"Using quantile: {p90_key} with {buffer*100:.0f}% buffer")
        ctx.output.print_info(f"Instance type: {instance_type}\n")

        schedule_data = []
        for i, point in enumerate(values):
            predicted_load = point.get("Value", 0)
            raw_nodes = predicted_load / requests_per_node
            buffered_nodes = raw_nodes * (1 + buffer)
            recommended = max(min_nodes, int(buffered_nodes) + 1)

            schedule_data.append({
                "Hour": i,
                "Timestamp": point.get("Timestamp", "-")[:16],
                "Predicted Load": f"{predicted_load:,.0f}",
                "Recommended Nodes": recommended,
            })

        ctx.output.print_data(
            schedule_data,
            headers=["Hour", "Timestamp", "Predicted Load", "Recommended Nodes"],
            title="Predictive Scaling Schedule",
        )

        # Generate schedule JSON for Karpenter
        schedule_json = {
            "apiVersion": "devctl.io/v1",
            "kind": "PredictiveScalingSchedule",
            "metadata": {
                "name": f"{item_id}-scaling",
                "generatedAt": datetime.utcnow().isoformat(),
            },
            "spec": {
                "workload": item_id,
                "instanceType": instance_type,
                "parameters": {
                    "minNodes": min_nodes,
                    "requestsPerNode": requests_per_node,
                    "buffer": buffer,
                },
                "schedule": [
                    {
                        "hour": d["Hour"],
                        "timestamp": d["Timestamp"],
                        "minNodes": d["Recommended Nodes"],
                        "maxNodes": d["Recommended Nodes"] + 5,  # Allow burst headroom
                    }
                    for d in schedule_data
                ],
            },
        }

        ctx.output.print_info("\nTo apply with Karpenter:")
        ctx.output.print("  1. Save schedule: devctl aws forecast scaling recommend ... -o json > schedule.json")
        ctx.output.print("  2. Generate NodePool: devctl aws forecast scaling generate-nodepool --schedule schedule.json")
        ctx.output.print("  3. Apply to cluster: kubectl apply -f nodepool.yaml")

        if ctx.output_format.value == "json":
            ctx.output.print_data(schedule_json)

    except ClientError as e:
        raise AWSError(f"Failed to generate recommendations: {e}")


@scaling.command("generate-nodepool")
@click.option("--schedule", "schedule_file", type=click.Path(exists=True), required=True, help="Schedule JSON from recommend command")
@click.option("--nodepool-name", default="predictive", help="Karpenter NodePool name")
@click.option("--output", "output_file", type=click.Path(), help="Output file (default: stdout)")
@click.option("--node-class", default="default", help="EC2NodeClass name to reference")
@pass_context
def generate_nodepool(
    ctx: DevCtlContext,
    schedule_file: str,
    nodepool_name: str,
    output_file: str | None,
    node_class: str,
) -> None:
    """Generate Karpenter NodePool YAML from scaling schedule.

    Creates a NodePool with limits based on predicted peak capacity.
    For time-based scaling, generates a CronJob that patches NodePool limits.
    """
    with open(schedule_file) as f:
        schedule = json.load(f)

    spec = schedule.get("spec", {})
    schedule_items = spec.get("schedule", [])
    instance_type = spec.get("instanceType", "m5.large")
    workload = spec.get("workload", "default")

    if not schedule_items:
        ctx.output.print_error("No schedule items found")
        return

    # Calculate peak capacity for NodePool limits
    peak_nodes = max(item["maxNodes"] for item in schedule_items)
    min_nodes = min(item["minNodes"] for item in schedule_items)

    # Generate Karpenter v1 NodePool
    nodepool_yaml = f"""# Generated by devctl aws forecast scaling
# Workload: {workload}
# Generated: {datetime.utcnow().isoformat()}
---
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: {nodepool_name}
  labels:
    devctl.io/predictive-scaling: "true"
    devctl.io/workload: "{workload}"
spec:
  template:
    metadata:
      labels:
        nodepool: {nodepool_name}
        workload: {workload}
    spec:
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: {node_class}
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand", "spot"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["{instance_type}", "{instance_type.replace('.large', '.xlarge')}", "{instance_type.replace('.large', '.2xlarge')}"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
      expireAfter: 720h  # 30 days
  limits:
    cpu: {peak_nodes * 4}  # Assuming 4 vCPU per node
    memory: "{peak_nodes * 16}Gi"  # Assuming 16GB per node
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 30s
---
# Predictive scaling ConfigMap with hourly targets
apiVersion: v1
kind: ConfigMap
metadata:
  name: {nodepool_name}-schedule
  labels:
    devctl.io/predictive-scaling: "true"
data:
  schedule.json: |
    {json.dumps(schedule_items, indent=2)}
---
# CronJob to update NodePool limits based on predictions
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {nodepool_name}-scaler
  labels:
    devctl.io/predictive-scaling: "true"
spec:
  schedule: "0 * * * *"  # Every hour
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: karpenter-scaler
          containers:
          - name: scaler
            image: bitnami/kubectl:latest
            command:
            - /bin/sh
            - -c
            - |
              HOUR=$(date +%H)
              SCHEDULE=$(cat /config/schedule.json)
              TARGET=$(echo "$SCHEDULE" | jq ".[$HOUR].minNodes // {min_nodes}")
              MAX=$(echo "$SCHEDULE" | jq ".[$HOUR].maxNodes // {peak_nodes}")

              echo "Hour $HOUR: Setting capacity to $TARGET-$MAX nodes"

              # Patch NodePool with predicted limits
              kubectl patch nodepool {nodepool_name} --type=merge -p "{{
                \\"spec\\": {{
                  \\"limits\\": {{
                    \\"cpu\\": \\"$(($TARGET * 4))\\",
                    \\"memory\\": \\"$(($TARGET * 16))Gi\\"
                  }}
                }}
              }}"
            volumeMounts:
            - name: schedule
              mountPath: /config
          volumes:
          - name: schedule
            configMap:
              name: {nodepool_name}-schedule
          restartPolicy: OnFailure
---
# ServiceAccount and RBAC for the scaler
apiVersion: v1
kind: ServiceAccount
metadata:
  name: karpenter-scaler
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: karpenter-scaler
rules:
- apiGroups: ["karpenter.sh"]
  resources: ["nodepools"]
  verbs: ["get", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: karpenter-scaler
subjects:
- kind: ServiceAccount
  name: karpenter-scaler
  namespace: default
roleRef:
  kind: ClusterRole
  name: karpenter-scaler
  apiGroup: rbac.authorization.k8s.io
"""

    if output_file:
        with open(output_file, "w") as f:
            f.write(nodepool_yaml)
        ctx.output.print_success(f"NodePool manifest written to: {output_file}")
    else:
        ctx.output.print(nodepool_yaml)

    ctx.output.print_info(f"\nGenerated NodePool '{nodepool_name}':")
    ctx.output.print_info(f"  - Peak capacity: {peak_nodes} nodes")
    ctx.output.print_info(f"  - Min capacity: {min_nodes} nodes")
    ctx.output.print_info(f"  - Instance types: {instance_type} family")
    ctx.output.print_info(f"  - Includes CronJob for hourly limit updates")


@scaling.command("apply")
@click.option("--cluster", required=True, help="EKS cluster name")
@click.option("--schedule", "schedule_file", type=click.Path(exists=True), required=True, help="Schedule JSON from recommend command")
@click.option("--nodepool-name", default="predictive", help="Karpenter NodePool name")
@click.option("--node-class", default="default", help="EC2NodeClass name to reference")
@click.option("--namespace", default="default", help="Namespace for CronJob and ConfigMap")
@pass_context
def scaling_apply(
    ctx: DevCtlContext,
    cluster: str,
    schedule_file: str,
    nodepool_name: str,
    node_class: str,
    namespace: str,
) -> None:
    """Apply predictive scaling to an EKS cluster with Karpenter.

    Generates NodePool, ConfigMap, and CronJob manifests, then applies them
    to the cluster using kubectl.

    \b
    Examples:
        devctl aws forecast scaling apply \\
            --cluster my-eks-cluster \\
            --schedule schedule.json \\
            --nodepool-name api-scaling
    """
    # First, update kubeconfig for the cluster
    ctx.output.print_info(f"Configuring kubectl for cluster: {cluster}")

    try:
        result = subprocess.run(
            ["aws", "eks", "update-kubeconfig", "--name", cluster, "--region", ctx.aws.region],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            ctx.output.print_error(f"Failed to update kubeconfig: {result.stderr}")
            return
    except FileNotFoundError:
        ctx.output.print_error("AWS CLI not found. Please install the AWS CLI.")
        return

    # Load schedule
    with open(schedule_file) as f:
        schedule = json.load(f)

    spec = schedule.get("spec", {})
    schedule_items = spec.get("schedule", [])
    instance_type = spec.get("instanceType", "m5.large")
    workload = spec.get("workload", "default")

    if not schedule_items:
        ctx.output.print_error("No schedule items found in file")
        return

    peak_nodes = max(item["maxNodes"] for item in schedule_items)
    min_nodes = min(item["minNodes"] for item in schedule_items)

    if ctx.dry_run:
        ctx.output.print_info(f"Would apply predictive scaling to cluster: {cluster}")
        ctx.output.print_info(f"  NodePool: {nodepool_name}")
        ctx.output.print_info(f"  Capacity range: {min_nodes}-{peak_nodes} nodes")
        ctx.output.print_info(f"  Instance type: {instance_type}")
        return

    # Generate manifest (reuse generate_nodepool logic but apply directly)
    nodepool_yaml = f"""# Generated by devctl aws forecast scaling
# Workload: {workload}
# Generated: {datetime.now(timezone.utc).isoformat()}
---
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: {nodepool_name}
  labels:
    devctl.io/predictive-scaling: "true"
    devctl.io/workload: "{workload}"
spec:
  template:
    metadata:
      labels:
        nodepool: {nodepool_name}
        workload: {workload}
    spec:
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: {node_class}
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand", "spot"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["{instance_type}", "{instance_type.replace('.large', '.xlarge')}", "{instance_type.replace('.large', '.2xlarge')}"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
      expireAfter: 720h
  limits:
    cpu: {peak_nodes * 4}
    memory: "{peak_nodes * 16}Gi"
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 30s
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {nodepool_name}-schedule
  namespace: {namespace}
  labels:
    devctl.io/predictive-scaling: "true"
data:
  schedule.json: |
    {json.dumps(schedule_items, indent=2)}
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {nodepool_name}-scaler
  namespace: {namespace}
  labels:
    devctl.io/predictive-scaling: "true"
spec:
  schedule: "0 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: karpenter-scaler
          containers:
          - name: scaler
            image: bitnami/kubectl:latest
            command:
            - /bin/sh
            - -c
            - |
              HOUR=$(date +%H)
              SCHEDULE=$(cat /config/schedule.json)
              TARGET=$(echo "$SCHEDULE" | jq ".[$HOUR].minNodes // {min_nodes}")
              MAX=$(echo "$SCHEDULE" | jq ".[$HOUR].maxNodes // {peak_nodes}")
              echo "Hour $HOUR: Setting capacity to $TARGET-$MAX nodes"
              kubectl patch nodepool {nodepool_name} --type=merge -p "{{
                \\"spec\\": {{
                  \\"limits\\": {{
                    \\"cpu\\": \\"$(($TARGET * 4))\\",
                    \\"memory\\": \\"$(($TARGET * 16))Gi\\"
                  }}
                }}
              }}"
            volumeMounts:
            - name: schedule
              mountPath: /config
          volumes:
          - name: schedule
            configMap:
              name: {nodepool_name}-schedule
          restartPolicy: OnFailure
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: karpenter-scaler
  namespace: {namespace}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: karpenter-scaler
rules:
- apiGroups: ["karpenter.sh"]
  resources: ["nodepools"]
  verbs: ["get", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: karpenter-scaler
subjects:
- kind: ServiceAccount
  name: karpenter-scaler
  namespace: {namespace}
roleRef:
  kind: ClusterRole
  name: karpenter-scaler
  apiGroup: rbac.authorization.k8s.io
"""

    # Write to temp file and apply
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(nodepool_yaml)
        temp_path = f.name

    try:
        ctx.output.print_info("Applying manifests to cluster...")

        result = subprocess.run(
            ["kubectl", "apply", "-f", temp_path],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            ctx.output.print_error(f"kubectl apply failed: {result.stderr}")
            return

        # Show what was applied
        for line in result.stdout.strip().split("\n"):
            if line:
                ctx.output.print(f"  {line}")

        ctx.output.print_success(f"\nPredictive scaling applied to cluster: {cluster}")
        ctx.output.print_info(f"  NodePool: {nodepool_name}")
        ctx.output.print_info(f"  Capacity: {min_nodes}-{peak_nodes} nodes")
        ctx.output.print_info(f"  CronJob: {nodepool_name}-scaler (hourly updates)")

        ctx.output.print_info("\nVerify with:")
        ctx.output.print(f"  kubectl get nodepool {nodepool_name}")
        ctx.output.print(f"  kubectl get cronjob {nodepool_name}-scaler -n {namespace}")

    finally:
        import os
        os.unlink(temp_path)


@scaling.command("status")
@click.option("--cluster", required=True, help="EKS cluster name")
@click.option("--nodepool", help="Karpenter NodePool name (optional)")
@pass_context
def scaling_status(ctx: DevCtlContext, cluster: str, nodepool: str | None) -> None:
    """Show Karpenter NodePool status and scaling info."""
    try:
        eks = ctx.aws.eks

        # Get cluster info
        cluster_info = eks.describe_cluster(name=cluster)
        cluster_data = cluster_info.get("cluster", {})

        ctx.output.print_info(f"EKS Cluster: {cluster}")
        ctx.output.print_info(f"Status: {cluster_data.get('status')}")
        ctx.output.print_info(f"Version: {cluster_data.get('version')}")
        ctx.output.print_info(f"Endpoint: {cluster_data.get('endpoint', '-')[:50]}...")

        # Show how to get Karpenter status via kubectl
        ctx.output.print_info("\nTo check Karpenter NodePools:")
        ctx.output.print("  kubectl get nodepools")
        ctx.output.print("  kubectl get nodeclaims")
        ctx.output.print("  kubectl get nodes -l karpenter.sh/nodepool")

        if nodepool:
            ctx.output.print_info(f"\nTo check specific NodePool '{nodepool}':")
            ctx.output.print(f"  kubectl describe nodepool {nodepool}")
            ctx.output.print(f"  kubectl get nodeclaims -l karpenter.sh/nodepool={nodepool}")

        # Show predictive scaling CronJob status
        ctx.output.print_info("\nTo check predictive scaling status:")
        ctx.output.print("  kubectl get cronjobs -l devctl.io/predictive-scaling=true")
        ctx.output.print("  kubectl get jobs -l devctl.io/predictive-scaling=true")

    except ClientError as e:
        raise AWSError(f"Failed to get cluster status: {e}")


@scaling.command("nodepools")
@click.option("--cluster", required=True, help="EKS cluster name")
@pass_context
def list_nodepools(ctx: DevCtlContext, cluster: str) -> None:
    """List Karpenter NodePools in a cluster.

    Note: Requires kubectl configured for the cluster.
    """
    import subprocess

    # First update kubeconfig
    try:
        eks = ctx.aws.eks
        cluster_info = eks.describe_cluster(name=cluster)

        ctx.output.print_info(f"Fetching NodePools from cluster: {cluster}\n")

        # Run kubectl to get nodepools
        result = subprocess.run(
            ["kubectl", "get", "nodepools", "-o", "json"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            if "the server doesn't have a resource type" in result.stderr:
                ctx.output.print_warning("Karpenter NodePools not found. Is Karpenter installed?")
                ctx.output.print_info("\nTo install Karpenter:")
                ctx.output.print("  helm install karpenter oci://public.ecr.aws/karpenter/karpenter \\")
                ctx.output.print("    --namespace karpenter --create-namespace")
                return
            ctx.output.print_error(f"kubectl error: {result.stderr}")
            return

        nodepools = json.loads(result.stdout)
        items = nodepools.get("items", [])

        if not items:
            ctx.output.print_info("No NodePools found")
            return

        data = []
        for np in items:
            metadata = np.get("metadata", {})
            spec = np.get("spec", {})
            status = np.get("status", {})
            limits = spec.get("limits", {})

            data.append({
                "Name": metadata.get("name", "-"),
                "CPU Limit": limits.get("cpu", "-"),
                "Memory Limit": limits.get("memory", "-"),
                "Nodes Ready": status.get("resources", {}).get("nodes", "-"),
                "Consolidation": spec.get("disruption", {}).get("consolidationPolicy", "-"),
            })

        ctx.output.print_data(
            data,
            headers=["Name", "CPU Limit", "Memory Limit", "Nodes Ready", "Consolidation"],
            title=f"Karpenter NodePools ({len(data)} found)",
        )

    except FileNotFoundError:
        ctx.output.print_error("kubectl not found. Please install kubectl and configure cluster access.")
    except ClientError as e:
        raise AWSError(f"Failed to access cluster: {e}")


@scaling.command("deploy-pipeline")
@click.option("--cluster", required=True, help="EKS cluster name")
@click.option("--service-name", required=True, help="Service/workload name")
@click.option("--s3-bucket", required=True, help="S3 bucket for forecast data")
@click.option("--schedule", default="rate(1 day)", help="EventBridge schedule expression")
@click.option("--namespace", default="devctl", help="Kubernetes namespace for the pipeline")
@pass_context
def deploy_pipeline(
    ctx: DevCtlContext,
    cluster: str,
    service_name: str,
    s3_bucket: str,
    schedule: str,
    namespace: str,
) -> None:
    """Deploy continuous predictive scaling pipeline to EKS.

    Creates a Kubernetes CronJob that runs daily to:
    1. Export recent CloudWatch metrics
    2. Update Forecast dataset
    3. Refresh scaling predictions
    4. Update NodePool limits

    \b
    Examples:
        devctl aws forecast scaling deploy-pipeline \\
            --cluster my-eks \\
            --service-name api-service \\
            --s3-bucket my-forecast-bucket
    """
    if ctx.dry_run:
        ctx.output.print_info("Would deploy predictive scaling pipeline:")
        ctx.output.print_info(f"  Cluster: {cluster}")
        ctx.output.print_info(f"  Service: {service_name}")
        ctx.output.print_info(f"  Schedule: {schedule}")
        return

    # Generate the pipeline CronJob manifest
    pipeline_yaml = f"""# Predictive Scaling Pipeline
# Generated by devctl aws forecast scaling deploy-pipeline
# Service: {service_name}
# Schedule: Daily at 2 AM UTC
---
apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    devctl.io/predictive-scaling: "true"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {service_name}-pipeline-config
  namespace: {namespace}
data:
  CLUSTER_NAME: "{cluster}"
  SERVICE_NAME: "{service_name}"
  S3_BUCKET: "{s3_bucket}"
  CLOUDWATCH_NAMESPACE: "AWS/ApplicationELB"
  CLOUDWATCH_METRIC: "RequestCount"
  MIN_NODES: "2"
  REQUESTS_PER_NODE: "1000"
  NODEPOOL_NAME: "{service_name}-predictive"
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {service_name}-forecast-pipeline
  namespace: {namespace}
  labels:
    devctl.io/predictive-scaling: "true"
    devctl.io/service: "{service_name}"
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM UTC
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: {service_name}-pipeline
          restartPolicy: OnFailure
          containers:
          - name: pipeline
            image: amazon/aws-cli:latest
            envFrom:
            - configMapRef:
                name: {service_name}-pipeline-config
            command:
            - /bin/bash
            - -c
            - |
              set -e

              echo "=== Predictive Scaling Pipeline ==="
              echo "Service: $SERVICE_NAME"
              echo "Time: $(date -u)"

              # Step 1: Export recent CloudWatch metrics
              echo "Step 1: Exporting CloudWatch metrics..."
              END_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
              START_TIME=$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ)

              aws cloudwatch get-metric-statistics \\
                --namespace "$CLOUDWATCH_NAMESPACE" \\
                --metric-name "$CLOUDWATCH_METRIC" \\
                --start-time "$START_TIME" \\
                --end-time "$END_TIME" \\
                --period 3600 \\
                --statistics Sum \\
                --output json > /tmp/metrics.json

              # Convert to Forecast CSV format
              echo "item_id,timestamp,target_value" > /tmp/metrics.csv
              jq -r --arg item "$SERVICE_NAME" '.Datapoints | sort_by(.Timestamp) | .[] | [$item, .Timestamp, .Sum] | @csv' /tmp/metrics.json >> /tmp/metrics.csv

              # Upload to S3
              DATE=$(date +%Y%m%d)
              aws s3 cp /tmp/metrics.csv "s3://$S3_BUCKET/forecast/$SERVICE_NAME/incremental/metrics-$DATE.csv"
              echo "Metrics uploaded to S3"

              # Step 2: Query latest forecast and update schedule
              echo "Step 2: Updating scaling schedule..."

              # Get latest forecast ARN
              FORECAST_ARN=$(aws forecast list-forecasts \\
                --query "Forecasts[?contains(ForecastName, '$SERVICE_NAME')] | sort_by(@, &CreationTime) | [-1].ForecastArn" \\
                --output text)

              if [ "$FORECAST_ARN" != "None" ] && [ -n "$FORECAST_ARN" ]; then
                echo "Using forecast: $FORECAST_ARN"

                # Query predictions
                aws forecastquery query-forecast \\
                  --forecast-arn "$FORECAST_ARN" \\
                  --filters "item_id=$SERVICE_NAME" \\
                  --output json > /tmp/predictions.json

                # Generate scaling schedule
                echo "Generating scaling recommendations..."
                jq -r '.Forecast.Predictions.p90 // .Forecast.Predictions | keys[0] as $k | .[$k]' /tmp/predictions.json > /tmp/schedule.json

                # Step 3: Update NodePool limits via kubectl
                echo "Step 3: Updating Karpenter NodePool..."

                # Calculate peak from predictions
                PEAK=$(jq '[.[].Value] | max | . * 1.2 / env.REQUESTS_PER_NODE | ceil | if . < env.MIN_NODES then env.MIN_NODES else . end' /tmp/schedule.json)

                kubectl patch nodepool "$NODEPOOL_NAME" --type=merge -p "{{
                  \\"spec\\": {{
                    \\"limits\\": {{
                      \\"cpu\\": \\"$(($PEAK * 4))\\",
                      \\"memory\\": \\"$(($PEAK * 16))Gi\\"
                    }}
                  }}
                }}" || echo "NodePool patch failed (may not exist yet)"

                echo "Pipeline completed successfully"
              else
                echo "No forecast found for $SERVICE_NAME - run initial setup first"
                exit 1
              fi
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {service_name}-pipeline
  namespace: {namespace}
  annotations:
    # Add IRSA annotation for your AWS account
    # eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/ForecastPipelineRole
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {service_name}-pipeline
rules:
- apiGroups: ["karpenter.sh"]
  resources: ["nodepools"]
  verbs: ["get", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {service_name}-pipeline
subjects:
- kind: ServiceAccount
  name: {service_name}-pipeline
  namespace: {namespace}
roleRef:
  kind: ClusterRole
  name: {service_name}-pipeline
  apiGroup: rbac.authorization.k8s.io
"""

    # Update kubeconfig
    ctx.output.print_info(f"Configuring kubectl for cluster: {cluster}")
    try:
        result = subprocess.run(
            ["aws", "eks", "update-kubeconfig", "--name", cluster, "--region", ctx.aws.region],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            ctx.output.print_error(f"Failed to update kubeconfig: {result.stderr}")
            return
    except FileNotFoundError:
        ctx.output.print_error("AWS CLI not found")
        return

    # Write and apply
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(pipeline_yaml)
        temp_path = f.name

    try:
        ctx.output.print_info("Deploying pipeline to cluster...")

        result = subprocess.run(
            ["kubectl", "apply", "-f", temp_path],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            ctx.output.print_error(f"kubectl apply failed: {result.stderr}")
            return

        for line in result.stdout.strip().split("\n"):
            if line:
                ctx.output.print(f"  {line}")

        ctx.output.print_success(f"\nPipeline deployed!")
        ctx.output.print_info(f"  CronJob: {service_name}-forecast-pipeline")
        ctx.output.print_info(f"  Schedule: Daily at 2 AM UTC")
        ctx.output.print_info(f"  Namespace: {namespace}")

        ctx.output.print_warning("\nIMPORTANT: Configure IRSA for AWS access:")
        ctx.output.print(f"  1. Create IAM role with Forecast, CloudWatch, S3 permissions")
        ctx.output.print(f"  2. Add annotation to ServiceAccount:")
        ctx.output.print(f"     kubectl annotate sa {service_name}-pipeline -n {namespace} \\")
        ctx.output.print(f"       eks.amazonaws.com/role-arn=arn:aws:iam::ACCOUNT:role/ForecastPipelineRole")

        ctx.output.print_info("\nVerify with:")
        ctx.output.print(f"  kubectl get cronjob {service_name}-forecast-pipeline -n {namespace}")
        ctx.output.print(f"  kubectl create job --from=cronjob/{service_name}-forecast-pipeline test-run -n {namespace}")

    finally:
        import os
        os.unlink(temp_path)
