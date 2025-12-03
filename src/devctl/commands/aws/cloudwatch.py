"""CloudWatch commands for AWS."""

import time
from datetime import datetime, timedelta
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.core.utils import parse_duration
from devctl.clients.aws import paginate


@click.group()
@pass_context
def cloudwatch(ctx: DevCtlContext) -> None:
    """CloudWatch operations - metrics, logs, and alarms.

    \b
    Examples:
        devctl aws cloudwatch metrics AWS/EC2 --metric CPUUtilization
        devctl aws cloudwatch logs /aws/lambda/my-function --tail
        devctl aws cloudwatch alarms --state alarm
    """
    pass


@cloudwatch.command()
@click.argument("namespace")
@click.option("--metric", help="Specific metric name")
@click.option("--since", default="1h", help="Time range (e.g., 30m, 1h, 1d)")
@click.option("--dimensions", multiple=True, help="Dimensions (Name=Value)")
@click.option("--stat", default="Average", help="Statistic (Average, Sum, Maximum, Minimum)")
@pass_context
def metrics(
    ctx: DevCtlContext,
    namespace: str,
    metric: str | None,
    since: str,
    dimensions: tuple[str, ...],
    stat: str,
) -> None:
    """Get CloudWatch metrics.

    NAMESPACE is the CloudWatch namespace (e.g., AWS/EC2, AWS/Lambda).
    """
    try:
        cw = ctx.aws.cloudwatch

        # Parse time range
        duration = parse_duration(since)
        end_time = datetime.utcnow()
        start_time = end_time - duration

        # Parse dimensions
        dim_list = []
        for d in dimensions:
            if "=" in d:
                name, value = d.split("=", 1)
                dim_list.append({"Name": name, "Value": value})

        if metric:
            # Get specific metric data
            kwargs: dict[str, Any] = {
                "Namespace": namespace,
                "MetricName": metric,
                "StartTime": start_time,
                "EndTime": end_time,
                "Period": 300,  # 5 minutes
                "Statistics": [stat],
            }
            if dim_list:
                kwargs["Dimensions"] = dim_list

            response = cw.get_metric_statistics(**kwargs)
            datapoints = response.get("Datapoints", [])

            if not datapoints:
                ctx.output.print_info(f"No data points for {namespace}/{metric}")
                return

            # Sort by timestamp
            datapoints.sort(key=lambda x: x["Timestamp"])

            data = []
            for dp in datapoints[-20:]:  # Last 20 points
                data.append({
                    "Timestamp": dp["Timestamp"].strftime("%Y-%m-%d %H:%M"),
                    stat: f"{dp[stat]:.2f}",
                    "Unit": dp.get("Unit", "-"),
                })

            ctx.output.print_data(
                data,
                headers=["Timestamp", stat, "Unit"],
                title=f"{namespace}/{metric}",
            )

        else:
            # List available metrics
            kwargs = {"Namespace": namespace}
            if dim_list:
                kwargs["Dimensions"] = dim_list

            metrics_list = paginate(cw, "list_metrics", "Metrics", **kwargs)

            # Group by metric name
            metric_names = sorted(set(m["MetricName"] for m in metrics_list))

            data = []
            for name in metric_names[:50]:  # Limit to 50
                sample = next(m for m in metrics_list if m["MetricName"] == name)
                dims = ", ".join(f"{d['Name']}={d['Value']}" for d in sample.get("Dimensions", [])[:2])
                data.append({
                    "MetricName": name,
                    "Dimensions": dims[:40] or "-",
                })

            ctx.output.print_data(
                data,
                headers=["MetricName", "Dimensions"],
                title=f"Metrics in {namespace} ({len(metric_names)} found)",
            )

    except ClientError as e:
        raise AWSError(f"Failed to get metrics: {e}")


@cloudwatch.command()
@click.argument("log_group")
@click.option("--stream", help="Specific log stream")
@click.option("--tail", "-f", is_flag=True, help="Follow logs in real-time")
@click.option("--since", default="1h", help="Time range (e.g., 30m, 1h, 1d)")
@click.option("--filter", "filter_pattern", help="CloudWatch filter pattern")
@click.option("--limit", type=int, default=100, help="Maximum events to return")
@pass_context
def logs(
    ctx: DevCtlContext,
    log_group: str,
    stream: str | None,
    tail: bool,
    since: str,
    filter_pattern: str | None,
    limit: int,
) -> None:
    """View CloudWatch logs.

    LOG_GROUP is the CloudWatch log group name.
    """
    try:
        logs_client = ctx.aws.logs

        # Parse time range
        duration = parse_duration(since)
        start_time = int((datetime.utcnow() - duration).timestamp() * 1000)

        if tail:
            # Tail mode - continuously poll for new logs
            ctx.output.print_info(f"Tailing {log_group}... (Ctrl+C to stop)")
            last_time = start_time

            try:
                while True:
                    kwargs: dict[str, Any] = {
                        "logGroupName": log_group,
                        "startTime": last_time,
                        "limit": 50,
                        "interleaved": True,
                    }
                    if stream:
                        kwargs["logStreamNames"] = [stream]
                    if filter_pattern:
                        kwargs["filterPattern"] = filter_pattern

                    response = logs_client.filter_log_events(**kwargs)
                    events = response.get("events", [])

                    for event in events:
                        ts = datetime.fromtimestamp(event["timestamp"] / 1000)
                        msg = event["message"].rstrip()
                        stream_name = event.get("logStreamName", "")[:20]
                        ctx.output.print(
                            f"[dim]{ts.strftime('%H:%M:%S')}[/dim] [cyan]{stream_name}[/cyan] {msg}"
                        )
                        last_time = max(last_time, event["timestamp"] + 1)

                    time.sleep(2)

            except KeyboardInterrupt:
                ctx.output.print_info("\nStopped tailing")

        else:
            # One-shot query
            kwargs = {
                "logGroupName": log_group,
                "startTime": start_time,
                "limit": limit,
                "interleaved": True,
            }
            if stream:
                kwargs["logStreamNames"] = [stream]
            if filter_pattern:
                kwargs["filterPattern"] = filter_pattern

            response = logs_client.filter_log_events(**kwargs)
            events = response.get("events", [])

            if not events:
                ctx.output.print_info("No log events found")
                return

            for event in events:
                ts = datetime.fromtimestamp(event["timestamp"] / 1000)
                msg = event["message"].rstrip()
                ctx.output.print(f"[dim]{ts.strftime('%Y-%m-%d %H:%M:%S')}[/dim] {msg}")

            ctx.output.print_info(f"\nShowing {len(events)} events")

    except ClientError as e:
        if "ResourceNotFoundException" in str(e):
            raise AWSError(f"Log group not found: {log_group}")
        raise AWSError(f"Failed to get logs: {e}")


@cloudwatch.command()
@click.option("--state", type=click.Choice(["alarm", "ok", "insufficient"]), help="Filter by state")
@click.option("--prefix", help="Filter by alarm name prefix")
@pass_context
def alarms(ctx: DevCtlContext, state: str | None, prefix: str | None) -> None:
    """List CloudWatch alarms."""
    try:
        cw = ctx.aws.cloudwatch

        kwargs: dict[str, Any] = {}
        if state:
            kwargs["StateValue"] = state.upper().replace("INSUFFICIENT", "INSUFFICIENT_DATA")
        if prefix:
            kwargs["AlarmNamePrefix"] = prefix

        alarms_list = paginate(cw, "describe_alarms", "MetricAlarms", **kwargs)

        if not alarms_list:
            ctx.output.print_info("No alarms found")
            return

        data = []
        for alarm in alarms_list:
            state_value = alarm["StateValue"]
            state_color = {
                "ALARM": "[red]ALARM[/red]",
                "OK": "[green]OK[/green]",
                "INSUFFICIENT_DATA": "[yellow]INSUFFICIENT[/yellow]",
            }.get(state_value, state_value)

            data.append({
                "Name": alarm["AlarmName"][:40],
                "State": state_color,
                "Metric": f"{alarm['Namespace']}/{alarm['MetricName']}"[:30],
                "Condition": f"{alarm['ComparisonOperator']} {alarm['Threshold']}",
                "Actions": len(alarm.get("AlarmActions", [])),
            })

        ctx.output.print_data(
            data,
            headers=["Name", "State", "Metric", "Condition", "Actions"],
            title=f"CloudWatch Alarms ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list alarms: {e}")


@cloudwatch.command("log-groups")
@click.option("--prefix", help="Filter by log group prefix")
@click.option("--limit", type=int, default=50, help="Maximum groups to return")
@pass_context
def log_groups(ctx: DevCtlContext, prefix: str | None, limit: int) -> None:
    """List CloudWatch log groups."""
    try:
        logs_client = ctx.aws.logs

        kwargs: dict[str, Any] = {"limit": limit}
        if prefix:
            kwargs["logGroupNamePrefix"] = prefix

        groups = paginate(logs_client, "describe_log_groups", "logGroups", **kwargs)

        data = []
        for group in groups[:limit]:
            size_bytes = group.get("storedBytes", 0)
            size_mb = size_bytes / (1024 * 1024)

            retention = group.get("retentionInDays")
            retention_str = f"{retention} days" if retention else "Never expire"

            data.append({
                "LogGroup": group["logGroupName"],
                "StoredMB": f"{size_mb:.1f}",
                "Retention": retention_str,
                "Created": datetime.fromtimestamp(
                    group["creationTime"] / 1000
                ).strftime("%Y-%m-%d"),
            })

        ctx.output.print_data(
            data,
            headers=["LogGroup", "StoredMB", "Retention", "Created"],
            title=f"Log Groups ({len(data)} shown)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list log groups: {e}")


@cloudwatch.command("insights")
@click.argument("log_group")
@click.argument("query")
@click.option("--since", default="1h", help="Time range")
@click.option("--limit", type=int, default=100, help="Maximum results")
@pass_context
def insights(ctx: DevCtlContext, log_group: str, query: str, since: str, limit: int) -> None:
    """Run CloudWatch Logs Insights query.

    QUERY is the Logs Insights query string.

    \b
    Example queries:
        "fields @timestamp, @message | sort @timestamp desc | limit 20"
        "filter @message like /ERROR/ | stats count(*) by bin(1h)"
    """
    try:
        logs_client = ctx.aws.logs

        duration = parse_duration(since)
        end_time = datetime.utcnow()
        start_time = end_time - duration

        # Start query
        response = logs_client.start_query(
            logGroupName=log_group,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query,
            limit=limit,
        )

        query_id = response["queryId"]
        ctx.output.print_info(f"Query started: {query_id}")

        # Poll for results
        while True:
            result = logs_client.get_query_results(queryId=query_id)
            status = result["status"]

            if status == "Complete":
                break
            elif status in ("Failed", "Cancelled"):
                raise AWSError(f"Query {status.lower()}")

            time.sleep(1)

        results = result.get("results", [])

        if not results:
            ctx.output.print_info("No results found")
            return

        # Convert results to list of dicts
        data = []
        for row in results:
            record = {}
            for field in row:
                record[field["field"]] = field["value"]
            data.append(record)

        # Get headers from first row
        headers = list(data[0].keys()) if data else []

        ctx.output.print_data(data, headers=headers, title=f"Query Results ({len(data)} rows)")

        stats = result.get("statistics", {})
        if stats:
            ctx.output.print_info(
                f"Scanned: {stats.get('bytesScanned', 0) / 1024:.1f} KB, "
                f"Records: {stats.get('recordsScanned', 0)}, "
                f"Matched: {stats.get('recordsMatched', 0)}"
            )

    except ClientError as e:
        raise AWSError(f"Insights query failed: {e}")
