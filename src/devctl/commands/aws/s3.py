"""S3 commands for AWS."""

import asyncio
from pathlib import Path
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext, require_confirmation
from devctl.core.exceptions import AWSError
from devctl.core.output import format_bytes, create_progress
from devctl.clients.aws import paginate


@click.group()
@pass_context
def s3(ctx: DevCtlContext) -> None:
    """S3 operations - buckets, objects, sync, cost analysis.

    \b
    Examples:
        devctl aws s3 ls
        devctl aws s3 ls my-bucket --prefix logs/
        devctl aws s3 size my-bucket --human
        devctl aws s3 sync ./local s3://bucket/prefix
    """
    pass


@s3.command("ls")
@click.argument("bucket", required=False)
@click.option("--prefix", default="", help="Object prefix filter")
@click.option("--recursive", "-r", is_flag=True, help="List recursively")
@click.option("--max-keys", type=int, default=1000, help="Maximum keys to return")
@pass_context
def ls(
    ctx: DevCtlContext,
    bucket: str | None,
    prefix: str,
    recursive: bool,
    max_keys: int,
) -> None:
    """List S3 buckets or objects.

    Without BUCKET argument, lists all buckets.
    With BUCKET argument, lists objects in that bucket.
    """
    try:
        s3_client = ctx.aws.s3

        if bucket is None:
            # List buckets
            response = s3_client.list_buckets()
            buckets = response.get("Buckets", [])

            data = []
            for b in buckets:
                data.append({
                    "Name": b["Name"],
                    "CreationDate": b["CreationDate"].strftime("%Y-%m-%d %H:%M"),
                })

            ctx.output.print_data(
                data,
                headers=["Name", "CreationDate"],
                title=f"S3 Buckets ({len(data)} found)",
            )
        else:
            # List objects
            kwargs: dict[str, Any] = {
                "Bucket": bucket,
                "MaxKeys": max_keys,
            }
            if prefix:
                kwargs["Prefix"] = prefix
            if not recursive:
                kwargs["Delimiter"] = "/"

            objects = []
            prefixes = []

            paginator = s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(**kwargs):
                objects.extend(page.get("Contents", []))
                prefixes.extend(page.get("CommonPrefixes", []))

                if len(objects) + len(prefixes) >= max_keys:
                    break

            data = []

            # Add prefixes (directories)
            for p in prefixes:
                data.append({
                    "Key": p["Prefix"],
                    "Type": "DIR",
                    "Size": "-",
                    "LastModified": "-",
                })

            # Add objects
            for obj in objects:
                data.append({
                    "Key": obj["Key"],
                    "Type": "FILE",
                    "Size": format_bytes(obj["Size"]),
                    "LastModified": obj["LastModified"].strftime("%Y-%m-%d %H:%M"),
                })

            ctx.output.print_data(
                data,
                headers=["Key", "Type", "Size", "LastModified"],
                title=f"s3://{bucket}/{prefix} ({len(data)} items)",
            )

    except ClientError as e:
        raise AWSError(f"Failed to list: {e}")


@s3.command()
@click.argument("bucket")
@click.option("--human", "-h", is_flag=True, help="Human-readable sizes")
@click.option("--by-storage-class", is_flag=True, help="Group by storage class")
@pass_context
def size(ctx: DevCtlContext, bucket: str, human: bool, by_storage_class: bool) -> None:
    """Calculate total size of a bucket or prefix."""
    try:
        s3_client = ctx.aws.s3

        total_size = 0
        total_objects = 0
        storage_classes: dict[str, int] = {}

        ctx.output.print_info(f"Calculating size of s3://{bucket}...")

        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                total_size += obj["Size"]
                total_objects += 1

                if by_storage_class:
                    sc = obj.get("StorageClass", "STANDARD")
                    storage_classes[sc] = storage_classes.get(sc, 0) + obj["Size"]

        if by_storage_class and storage_classes:
            data = []
            for sc, sc_size in sorted(storage_classes.items(), key=lambda x: -x[1]):
                data.append({
                    "StorageClass": sc,
                    "Size": format_bytes(sc_size) if human else sc_size,
                    "Percentage": f"{(sc_size / total_size * 100):.1f}%",
                })
            ctx.output.print_data(data, title="Size by Storage Class")

        size_display = format_bytes(total_size) if human else f"{total_size} bytes"
        ctx.output.print_success(f"Total: {size_display} ({total_objects:,} objects)")

    except ClientError as e:
        raise AWSError(f"Failed to calculate size: {e}")


@s3.command()
@click.argument("source")
@click.argument("dest")
@click.option("--delete", is_flag=True, help="Delete files in dest not in source")
@click.option("--exclude", multiple=True, help="Exclude patterns")
@click.option("--include", multiple=True, help="Include patterns")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@pass_context
def sync(
    ctx: DevCtlContext,
    source: str,
    dest: str,
    delete: bool,
    exclude: tuple[str, ...],
    include: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Sync files between local and S3.

    SOURCE and DEST can be local paths or s3://bucket/prefix URIs.

    \b
    Examples:
        devctl aws s3 sync ./data s3://bucket/data
        devctl aws s3 sync s3://bucket/data ./data
        devctl aws s3 sync s3://src-bucket s3://dst-bucket
    """
    import subprocess

    # Build aws s3 sync command
    cmd = ["aws", "s3", "sync", source, dest]

    if delete:
        cmd.append("--delete")
    if dry_run or ctx.dry_run:
        cmd.append("--dryrun")
    for pattern in exclude:
        cmd.extend(["--exclude", pattern])
    for pattern in include:
        cmd.extend(["--include", pattern])

    # Add profile/region if configured
    profile = ctx.profile.aws.get_profile()
    region = ctx.profile.aws.get_region()
    if profile:
        cmd.extend(["--profile", profile])
    if region:
        cmd.extend(["--region", region])

    ctx.output.print_info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:
            raise AWSError(f"Sync failed with exit code {result.returncode}")

        ctx.output.print_success("Sync completed")

    except FileNotFoundError:
        raise AWSError("AWS CLI not found. Please install it for sync operations.")


@s3.command()
@click.argument("source")
@click.argument("dest")
@click.option("--recursive", "-r", is_flag=True, help="Copy recursively")
@pass_context
def cp(ctx: DevCtlContext, source: str, dest: str, recursive: bool) -> None:
    """Copy files to/from S3.

    SOURCE and DEST can be local paths or s3://bucket/prefix URIs.
    """
    import subprocess

    cmd = ["aws", "s3", "cp", source, dest]

    if recursive:
        cmd.append("--recursive")

    if ctx.dry_run:
        cmd.append("--dryrun")

    profile = ctx.profile.aws.get_profile()
    region = ctx.profile.aws.get_region()
    if profile:
        cmd.extend(["--profile", profile])
    if region:
        cmd.extend(["--region", region])

    ctx.output.print_info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:
            raise AWSError(f"Copy failed with exit code {result.returncode}")

        ctx.output.print_success("Copy completed")

    except FileNotFoundError:
        raise AWSError("AWS CLI not found. Please install it for copy operations.")


@s3.command()
@click.argument("target")
@click.option("--recursive", "-r", is_flag=True, help="Delete recursively")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@pass_context
def rm(ctx: DevCtlContext, target: str, recursive: bool, yes: bool) -> None:
    """Delete S3 objects.

    TARGET should be an s3://bucket/key URI.
    """
    if not target.startswith("s3://"):
        raise click.BadParameter("Target must be an S3 URI (s3://bucket/key)")

    if not yes and not ctx.dry_run:
        if not ctx.confirm(f"Delete {target}{'/*' if recursive else ''}?"):
            ctx.output.print_info("Cancelled")
            return

    import subprocess

    cmd = ["aws", "s3", "rm", target]

    if recursive:
        cmd.append("--recursive")

    if ctx.dry_run:
        cmd.append("--dryrun")

    profile = ctx.profile.aws.get_profile()
    region = ctx.profile.aws.get_region()
    if profile:
        cmd.extend(["--profile", profile])
    if region:
        cmd.extend(["--region", region])

    ctx.output.print_info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:
            raise AWSError(f"Delete failed with exit code {result.returncode}")

        ctx.output.print_success("Delete completed")

    except FileNotFoundError:
        raise AWSError("AWS CLI not found. Please install it for delete operations.")


@s3.command("cost-analysis")
@click.option("--bucket", help="Specific bucket to analyze (default: all)")
@click.option("--days", type=int, default=30, help="Days of history to analyze")
@pass_context
def cost_analysis(ctx: DevCtlContext, bucket: str | None, days: int) -> None:
    """Analyze S3 storage costs.

    Provides breakdown of storage costs by bucket and storage class.
    """
    try:
        s3_client = ctx.aws.s3
        cloudwatch = ctx.aws.cloudwatch

        from datetime import datetime, timedelta

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        if bucket:
            buckets = [bucket]
        else:
            response = s3_client.list_buckets()
            buckets = [b["Name"] for b in response.get("Buckets", [])]

        # Storage class pricing (approximate, varies by region)
        pricing = {
            "STANDARD": 0.023,
            "STANDARD_IA": 0.0125,
            "ONEZONE_IA": 0.01,
            "GLACIER": 0.004,
            "DEEP_ARCHIVE": 0.00099,
            "INTELLIGENT_TIERING": 0.023,
        }

        data = []
        total_cost = 0.0

        for bucket_name in buckets:
            try:
                # Get bucket size from CloudWatch metrics
                response = cloudwatch.get_metric_statistics(
                    Namespace="AWS/S3",
                    MetricName="BucketSizeBytes",
                    Dimensions=[
                        {"Name": "BucketName", "Value": bucket_name},
                        {"Name": "StorageType", "Value": "StandardStorage"},
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=["Average"],
                )

                datapoints = response.get("Datapoints", [])
                if datapoints:
                    avg_size = sum(d["Average"] for d in datapoints) / len(datapoints)
                    size_gb = avg_size / (1024**3)
                    monthly_cost = size_gb * pricing.get("STANDARD", 0.023)
                    total_cost += monthly_cost

                    data.append({
                        "Bucket": bucket_name,
                        "SizeGB": f"{size_gb:.2f}",
                        "MonthlyCost": f"${monthly_cost:.2f}",
                    })
            except ClientError:
                continue

        if data:
            ctx.output.print_data(
                data,
                headers=["Bucket", "SizeGB", "MonthlyCost"],
                title=f"S3 Cost Analysis (estimated, {len(data)} buckets)",
            )
            ctx.output.print_info(f"Total estimated monthly cost: ${total_cost:.2f}")
        else:
            ctx.output.print_warning("No storage metrics found. Enable S3 request metrics for cost analysis.")

    except ClientError as e:
        raise AWSError(f"Failed to analyze costs: {e}")


@s3.command()
@click.argument("bucket")
@click.option("--get", "get_policy", is_flag=True, help="Get current lifecycle policy")
@click.option("--set", "set_policy", type=click.Path(exists=True), help="Set lifecycle policy from file")
@pass_context
def lifecycle(ctx: DevCtlContext, bucket: str, get_policy: bool, set_policy: str | None) -> None:
    """Get or set bucket lifecycle policy."""
    try:
        s3_client = ctx.aws.s3

        if set_policy:
            if ctx.dry_run:
                ctx.log_dry_run("set lifecycle policy", {"bucket": bucket, "file": set_policy})
                return

            import json

            with open(set_policy) as f:
                policy = json.load(f)

            s3_client.put_bucket_lifecycle_configuration(
                Bucket=bucket,
                LifecycleConfiguration=policy,
            )
            ctx.output.print_success(f"Lifecycle policy set for {bucket}")

        else:
            try:
                response = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket)
                rules = response.get("Rules", [])

                data = []
                for rule in rules:
                    data.append({
                        "ID": rule.get("ID", "-"),
                        "Status": rule.get("Status", "-"),
                        "Prefix": rule.get("Filter", {}).get("Prefix", "*"),
                        "Transitions": len(rule.get("Transitions", [])),
                        "Expiration": "Yes" if "Expiration" in rule else "No",
                    })

                ctx.output.print_data(
                    data,
                    headers=["ID", "Status", "Prefix", "Transitions", "Expiration"],
                    title=f"Lifecycle Rules for {bucket}",
                )

            except ClientError as e:
                if "NoSuchLifecycleConfiguration" in str(e):
                    ctx.output.print_info(f"No lifecycle policy configured for {bucket}")
                else:
                    raise

    except ClientError as e:
        raise AWSError(f"Lifecycle operation failed: {e}")
