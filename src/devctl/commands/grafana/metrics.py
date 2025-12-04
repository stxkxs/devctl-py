"""Grafana metrics commands - query metrics through datasources."""

import json
from datetime import datetime, timedelta
from typing import Any

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import GrafanaError
from devctl.core.utils import parse_duration


@click.group()
@pass_context
def metrics(ctx: DevCtlContext) -> None:
    """Metrics operations - query Prometheus/InfluxDB through Grafana.

    \b
    Examples:
        devctl grafana metrics query prometheus 'up{job="api"}'
        devctl grafana metrics get prometheus 'rate(http_requests_total[5m])'
        devctl grafana metrics check prometheus 'avg(cpu_usage)' --threshold 80
    """
    pass


def _get_datasource_uid(client: Any, name_or_uid: str) -> tuple[str, str, str]:
    """Get datasource UID, name, and type from name or UID.

    Returns:
        Tuple of (uid, name, type)
    """
    # Try as UID first
    try:
        ds = client.get_datasource(name_or_uid)
        return ds.get("uid"), ds.get("name"), ds.get("type")
    except GrafanaError:
        pass

    # Try as name
    datasources = client.list_datasources()
    ds = next(
        (d for d in datasources if d.get("name") == name_or_uid),
        None,
    )
    if not ds:
        raise GrafanaError(f"Datasource not found: {name_or_uid}")
    return ds.get("uid"), ds.get("name"), ds.get("type")


def _query_prometheus(
    client: Any,
    datasource_uid: str,
    query: str,
    start_time: datetime,
    end_time: datetime,
    step: int,
) -> dict[str, Any]:
    """Execute a Prometheus range query through Grafana."""
    payload = {
        "queries": [
            {
                "refId": "A",
                "datasource": {"uid": datasource_uid},
                "expr": query,
                "intervalMs": step * 1000,
                "maxDataPoints": 100,
            }
        ],
        "from": str(int(start_time.timestamp() * 1000)),
        "to": str(int(end_time.timestamp() * 1000)),
    }

    return client.post("/api/ds/query", json=payload)


def _query_prometheus_instant(
    client: Any,
    datasource_uid: str,
    query: str,
) -> dict[str, Any]:
    """Execute a Prometheus instant query through Grafana."""
    now = datetime.utcnow()
    payload = {
        "queries": [
            {
                "refId": "A",
                "datasource": {"uid": datasource_uid},
                "expr": query,
                "instant": True,
                "maxDataPoints": 1,
            }
        ],
        "from": str(int((now - timedelta(minutes=5)).timestamp() * 1000)),
        "to": str(int(now.timestamp() * 1000)),
    }

    return client.post("/api/ds/query", json=payload)


@metrics.command("query")
@click.argument("datasource")
@click.argument("query")
@click.option("--since", default="1h", help="Time range (e.g., 30m, 1h, 1d)")
@click.option("--step", default=60, type=int, help="Query step in seconds")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@pass_context
def query_metrics(
    ctx: DevCtlContext,
    datasource: str,
    query: str,
    since: str,
    step: int,
    output_format: str,
) -> None:
    """Query metrics from a Grafana datasource.

    DATASOURCE is the datasource name or UID.
    QUERY is the PromQL or InfluxQL query string.

    \b
    Examples:
        devctl grafana metrics query prometheus 'up{job="api"}'
        devctl grafana metrics query prometheus 'rate(http_requests_total[5m])' --since 6h
        devctl grafana metrics query influxdb 'SELECT mean("value") FROM "cpu" WHERE time > now() - 1h'
    """
    try:
        client = ctx.grafana
        uid, name, ds_type = _get_datasource_uid(client, datasource)

        ctx.output.print_info(f"Querying {name} ({ds_type})...")

        # Parse time range
        duration = parse_duration(since)
        end_time = datetime.utcnow()
        start_time = end_time - duration

        # Execute query
        response = _query_prometheus(client, uid, query, start_time, end_time, step)

        results = response.get("results", {})

        if output_format == "json":
            ctx.output.print_code(json.dumps(results, indent=2, default=str), "json")
            return

        # Process results
        for ref_id, result in results.items():
            frames = result.get("frames", [])

            if not frames:
                ctx.output.print_info("No data returned")
                continue

            for frame in frames:
                schema = frame.get("schema", {})
                fields = schema.get("fields", [])
                data_values = frame.get("data", {}).get("values", [])

                # Get field names
                field_names = [f.get("name", f"field_{i}") for i, f in enumerate(fields)]

                if not data_values or not data_values[0]:
                    continue

                # Get metric name from labels if available
                metric_name = None
                for field in fields:
                    labels = field.get("labels", {})
                    if labels:
                        metric_name = labels.get("__name__", str(labels)[:40])
                        break

                # Build table data
                table_data = []
                time_values = data_values[0] if len(data_values) > 0 else []
                metric_values = data_values[1] if len(data_values) > 1 else []

                for i, (ts, val) in enumerate(zip(time_values[-20:], metric_values[-20:])):
                    # Convert timestamp
                    if isinstance(ts, (int, float)):
                        ts_dt = datetime.fromtimestamp(ts / 1000)
                        ts_str = ts_dt.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        ts_str = str(ts)

                    # Format value
                    if val is None:
                        val_str = "-"
                    elif isinstance(val, float):
                        val_str = f"{val:.4f}"
                    else:
                        val_str = str(val)

                    table_data.append({
                        "Timestamp": ts_str,
                        "Value": val_str,
                    })

                title = f"Results: {metric_name or query[:50]}"
                if len(time_values) > 20:
                    title += f" (showing last 20 of {len(time_values)})"

                ctx.output.print_data(
                    table_data,
                    headers=["Timestamp", "Value"],
                    title=title,
                )

    except Exception as e:
        raise GrafanaError(f"Failed to query metrics: {e}")


@metrics.command("get")
@click.argument("datasource")
@click.argument("query")
@click.option("--format", "output_format", type=click.Choice(["value", "json"]), default="value", help="Output format")
@pass_context
def get_metric(
    ctx: DevCtlContext,
    datasource: str,
    query: str,
    output_format: str,
) -> None:
    """Get the current value of a metric (instant query).

    DATASOURCE is the datasource name or UID.
    QUERY is the PromQL query string.

    \b
    Examples:
        devctl grafana metrics get prometheus 'up{job="api"}'
        devctl grafana metrics get prometheus 'avg(rate(http_requests_total[5m]))'
    """
    try:
        client = ctx.grafana
        uid, name, ds_type = _get_datasource_uid(client, datasource)

        # Execute instant query
        response = _query_prometheus_instant(client, uid, query)

        if output_format == "json":
            ctx.output.print_code(json.dumps(response, indent=2, default=str), "json")
            return

        results = response.get("results", {})

        for ref_id, result in results.items():
            frames = result.get("frames", [])

            if not frames:
                ctx.output.print_info("No data returned")
                continue

            for frame in frames:
                schema = frame.get("schema", {})
                fields = schema.get("fields", [])
                data_values = frame.get("data", {}).get("values", [])

                # Get metric labels
                labels = {}
                for field in fields:
                    field_labels = field.get("labels", {})
                    if field_labels:
                        labels.update(field_labels)

                # Get the latest value
                if len(data_values) >= 2 and data_values[1]:
                    value = data_values[1][-1] if data_values[1] else None

                    if value is not None:
                        if isinstance(value, float):
                            value_str = f"{value:.4f}"
                        else:
                            value_str = str(value)

                        # Format output
                        label_str = ", ".join(f"{k}={v}" for k, v in labels.items() if not k.startswith("__"))
                        if label_str:
                            ctx.output.print(f"{label_str}: {value_str}")
                        else:
                            ctx.output.print(value_str)
                    else:
                        ctx.output.print_info("No value available")

    except Exception as e:
        raise GrafanaError(f"Failed to get metric: {e}")


@metrics.command("check")
@click.argument("datasource")
@click.argument("query")
@click.option("--threshold", "-t", type=float, required=True, help="Threshold value")
@click.option("--comparison", "-c", type=click.Choice(["gt", "lt", "ge", "le", "eq"]), default="gt", help="Comparison operator")
@click.option("--exit-code", is_flag=True, help="Exit with code 1 if threshold breached")
@pass_context
def check_metric(
    ctx: DevCtlContext,
    datasource: str,
    query: str,
    threshold: float,
    comparison: str,
    exit_code: bool,
) -> None:
    """Check if a metric crosses a threshold.

    Useful for CI/CD pipelines, canary deployments, and health checks.

    DATASOURCE is the datasource name or UID.
    QUERY is the PromQL query string.

    \b
    Comparison operators:
        gt  - greater than (default)
        lt  - less than
        ge  - greater than or equal
        le  - less than or equal
        eq  - equal

    \b
    Examples:
        devctl grafana metrics check prometheus 'avg(cpu_usage)' --threshold 80
        devctl grafana metrics check prometheus 'sum(rate(error_total[5m]))' -t 10 -c gt --exit-code
        devctl grafana metrics check prometheus 'up{job="api"}' -t 1 -c lt --exit-code
    """
    try:
        client = ctx.grafana
        uid, name, ds_type = _get_datasource_uid(client, datasource)

        # Execute instant query
        response = _query_prometheus_instant(client, uid, query)

        results = response.get("results", {})

        value = None
        for ref_id, result in results.items():
            frames = result.get("frames", [])
            for frame in frames:
                data_values = frame.get("data", {}).get("values", [])
                if len(data_values) >= 2 and data_values[1]:
                    value = data_values[1][-1] if data_values[1] else None
                    break
            if value is not None:
                break

        if value is None:
            ctx.output.print_error("No value returned from query")
            if exit_code:
                raise SystemExit(1)
            return

        # Perform comparison
        comparison_ops = {
            "gt": (lambda v, t: v > t, ">"),
            "lt": (lambda v, t: v < t, "<"),
            "ge": (lambda v, t: v >= t, ">="),
            "le": (lambda v, t: v <= t, "<="),
            "eq": (lambda v, t: v == t, "=="),
        }

        op_func, op_symbol = comparison_ops[comparison]
        breached = op_func(value, threshold)

        value_str = f"{value:.4f}" if isinstance(value, float) else str(value)
        threshold_str = f"{threshold:.4f}" if isinstance(threshold, float) else str(threshold)

        if breached:
            ctx.output.print_error(
                f"THRESHOLD BREACHED: {value_str} {op_symbol} {threshold_str}"
            )
            if exit_code:
                raise SystemExit(1)
        else:
            ctx.output.print_success(
                f"OK: {value_str} (threshold: {op_symbol} {threshold_str})"
            )

    except SystemExit:
        raise
    except Exception as e:
        raise GrafanaError(f"Failed to check metric: {e}")


@metrics.command("list")
@click.argument("datasource")
@click.option("--filter", "filter_pattern", help="Filter metrics by name pattern")
@click.option("--limit", type=int, default=50, help="Maximum metrics to show")
@pass_context
def list_metrics(
    ctx: DevCtlContext,
    datasource: str,
    filter_pattern: str | None,
    limit: int,
) -> None:
    """List available metrics from a Prometheus datasource.

    DATASOURCE is the datasource name or UID.

    \b
    Examples:
        devctl grafana metrics list prometheus
        devctl grafana metrics list prometheus --filter http
        devctl grafana metrics list prometheus --limit 100
    """
    try:
        client = ctx.grafana
        uid, name, ds_type = _get_datasource_uid(client, datasource)

        if "prometheus" not in ds_type.lower():
            ctx.output.print_warning(f"Datasource is {ds_type}, not Prometheus. Results may vary.")

        ctx.output.print_info(f"Fetching metrics from {name}...")

        # Query Prometheus label values for __name__
        # Use the Grafana datasource proxy
        params = {}
        if filter_pattern:
            params["match[]"] = f'{{{filter_pattern}=~".+"}}'

        # Try to get metric names via Prometheus API through Grafana proxy
        try:
            response = client.get(f"/api/datasources/proxy/uid/{uid}/api/v1/label/__name__/values")
            metric_names = response.get("data", [])
        except GrafanaError:
            # Fallback: query for metadata
            ctx.output.print_warning("Could not fetch metric list. Try querying specific metrics.")
            return

        if filter_pattern:
            metric_names = [m for m in metric_names if filter_pattern.lower() in m.lower()]

        metric_names = sorted(metric_names)[:limit]

        if not metric_names:
            ctx.output.print_info("No metrics found")
            return

        data = [{"Metric": name} for name in metric_names]

        ctx.output.print_data(
            data,
            headers=["Metric"],
            title=f"Available Metrics ({len(data)} shown)",
        )

    except Exception as e:
        raise GrafanaError(f"Failed to list metrics: {e}")


@metrics.command("labels")
@click.argument("datasource")
@click.argument("metric")
@pass_context
def list_labels(
    ctx: DevCtlContext,
    datasource: str,
    metric: str,
) -> None:
    """List labels for a specific metric.

    DATASOURCE is the datasource name or UID.
    METRIC is the metric name.

    \b
    Examples:
        devctl grafana metrics labels prometheus http_requests_total
        devctl grafana metrics labels prometheus up
    """
    try:
        client = ctx.grafana
        uid, name, ds_type = _get_datasource_uid(client, datasource)

        # Query for label names using series endpoint
        try:
            response = client.get(
                f"/api/datasources/proxy/uid/{uid}/api/v1/series",
                params={"match[]": metric}
            )
            series = response.get("data", [])
        except GrafanaError:
            ctx.output.print_warning("Could not fetch series data")
            return

        if not series:
            ctx.output.print_info(f"No series found for metric: {metric}")
            return

        # Collect all unique labels and their values
        labels: dict[str, set[str]] = {}
        for s in series:
            for key, value in s.items():
                if key != "__name__":
                    if key not in labels:
                        labels[key] = set()
                    labels[key].add(value)

        if not labels:
            ctx.output.print_info("No labels found")
            return

        data = []
        for label, values in sorted(labels.items()):
            values_list = sorted(values)
            values_str = ", ".join(values_list[:5])
            if len(values_list) > 5:
                values_str += f" ... (+{len(values_list) - 5} more)"

            data.append({
                "Label": label,
                "Cardinality": len(values),
                "Values": values_str,
            })

        ctx.output.print_data(
            data,
            headers=["Label", "Cardinality", "Values"],
            title=f"Labels for {metric}",
        )

    except Exception as e:
        raise GrafanaError(f"Failed to list labels: {e}")
