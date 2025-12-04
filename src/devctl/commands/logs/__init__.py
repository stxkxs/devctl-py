"""Logs command group."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import LogsError
from devctl.core.logs import LogQuery


@click.group()
@pass_context
def logs(ctx: DevCtlContext) -> None:
    """Unified log operations - search, tail across sources.

    \b
    Examples:
        devctl logs search "error" --source cloudwatch -g /aws/lambda/my-func
        devctl logs tail cloudwatch /aws/ecs/my-service -f
        devctl logs eks my-pod -n production
    """
    pass


@logs.command("search")
@click.argument("query")
@click.option("--source", type=click.Choice(["cloudwatch", "loki", "eks", "all"]), default="cloudwatch", help="Log source")
@click.option("-g", "--log-group", default=None, help="CloudWatch log group")
@click.option("-n", "--namespace", default=None, help="K8s namespace")
@click.option("--pod", default=None, help="Pod name")
@click.option("--since", default="1h", help="Time range (e.g., 1h, 30m, 7d)")
@click.option("--limit", default=100, help="Max results")
@pass_context
def search(
    ctx: DevCtlContext,
    query: str,
    source: str,
    log_group: str | None,
    namespace: str | None,
    pod: str | None,
    since: str,
    limit: int,
) -> None:
    """Search logs across sources.

    \b
    Examples:
        devctl logs search "error" --source cloudwatch -g /aws/lambda/my-func
        devctl logs search "exception" --source loki --namespace production
    """
    try:
        log_query = LogQuery(
            query=query,
            time_range=since,
            log_group=log_group,
            namespace=namespace,
            pod=pod,
            limit=limit,
        )

        # Create log source
        if source == "cloudwatch":
            from devctl.core.logs.cloudwatch import CloudWatchLogSource

            logs_client = ctx.aws.logs()
            log_source = CloudWatchLogSource(
                logs_client=logs_client,
                log_group_prefix=ctx.config.get_profile(ctx.profile_name).logs.cloudwatch_log_group_prefix,
            )
        elif source == "loki":
            from devctl.core.logs.loki import LokiLogSource

            log_source = LokiLogSource(
                grafana_client=ctx.grafana,
                datasource_uid=ctx.config.get_profile(ctx.profile_name).logs.loki_datasource_uid,
            )
        elif source == "eks":
            from devctl.core.logs.eks import EKSLogSource

            log_source = EKSLogSource(
                k8s_client=ctx.k8s,
                default_namespace=namespace or "default",
            )
        else:
            ctx.output.print_error(f"Unknown source: {source}")
            raise click.Abort()

        with log_source:
            entries = log_source.search(log_query)

        if not entries:
            ctx.output.print_info("No logs found")
            return

        for entry in entries:
            ctx.output.print(entry.format())

    except LogsError as e:
        ctx.output.print_error(f"Search failed: {e}")
        raise click.Abort()


@logs.command("tail")
@click.argument("source", type=click.Choice(["cloudwatch", "loki", "eks"]))
@click.argument("target")
@click.option("-f", "--follow", is_flag=True, help="Follow log output")
@click.option("-n", "--namespace", default=None, help="K8s namespace")
@click.option("--filter", "filter_pattern", default=None, help="Filter pattern")
@click.option("--tail", "tail_lines", default=100, help="Lines to show")
@pass_context
def tail(
    ctx: DevCtlContext,
    source: str,
    target: str,
    follow: bool,
    namespace: str | None,
    filter_pattern: str | None,
    tail_lines: int,
) -> None:
    """Tail logs from a source.

    \b
    Examples:
        devctl logs tail cloudwatch /aws/ecs/my-service -f
        devctl logs tail eks my-pod -n production -f
    """
    try:
        log_query = LogQuery(
            log_group=target if source == "cloudwatch" else None,
            pod=target if source in ("eks", "loki") else None,
            namespace=namespace,
            filter_pattern=filter_pattern,
            limit=tail_lines,
            time_range="1h",
        )

        # Create log source
        if source == "cloudwatch":
            from devctl.core.logs.cloudwatch import CloudWatchLogSource

            log_source = CloudWatchLogSource(logs_client=ctx.aws.logs())
        elif source == "eks":
            from devctl.core.logs.eks import EKSLogSource

            log_source = EKSLogSource(k8s_client=ctx.k8s)
        else:
            from devctl.core.logs.loki import LokiLogSource

            log_source = LokiLogSource(grafana_client=ctx.grafana)

        with log_source:
            for entry in log_source.tail(log_query, follow=follow):
                ctx.output.print(entry.format())

    except KeyboardInterrupt:
        ctx.output.print_info("\nStopped")
    except LogsError as e:
        ctx.output.print_error(f"Tail failed: {e}")
        raise click.Abort()


@logs.command("cloudwatch")
@click.argument("log_group")
@click.option("--since", default="1h", help="Time range")
@click.option("--filter", "filter_pattern", default=None, help="Filter pattern")
@click.option("--insights", default=None, help="CloudWatch Insights query")
@click.option("--limit", default=100, help="Max results")
@pass_context
def cloudwatch(
    ctx: DevCtlContext,
    log_group: str,
    since: str,
    filter_pattern: str | None,
    insights: str | None,
    limit: int,
) -> None:
    """Query CloudWatch logs.

    \b
    Examples:
        devctl logs cloudwatch /aws/lambda/my-func --since 1h
        devctl logs cloudwatch /aws/ecs/service --insights "fields @timestamp, @message | filter @message like /error/"
    """
    try:
        from devctl.core.logs.cloudwatch import CloudWatchLogSource

        log_source = CloudWatchLogSource(logs_client=ctx.aws.logs())

        query = LogQuery(
            log_group=log_group,
            time_range=since,
            filter_pattern=filter_pattern,
            query=insights,
            limit=limit,
        )

        with log_source:
            entries = log_source.search(query)

        if not entries:
            ctx.output.print_info("No logs found")
            return

        for entry in entries:
            ctx.output.print(entry.format())

    except LogsError as e:
        ctx.output.print_error(f"Query failed: {e}")
        raise click.Abort()


@logs.command("eks")
@click.argument("pod")
@click.option("-n", "--namespace", default="default", help="Namespace")
@click.option("-c", "--container", default=None, help="Container")
@click.option("-f", "--follow", is_flag=True, help="Follow logs")
@click.option("--tail", "tail_lines", default=100, help="Lines to show")
@click.option("--since", default=None, help="Since duration")
@pass_context
def eks(
    ctx: DevCtlContext,
    pod: str,
    namespace: str,
    container: str | None,
    follow: bool,
    tail_lines: int,
    since: str | None,
) -> None:
    """Get EKS/Kubernetes pod logs.

    \b
    Examples:
        devctl logs eks my-pod -n production
        devctl logs eks my-pod -f
    """
    try:
        from devctl.core.logs.eks import EKSLogSource

        log_source = EKSLogSource(
            k8s_client=ctx.k8s,
            default_namespace=namespace,
        )

        query = LogQuery(
            pod=pod,
            namespace=namespace,
            container=container,
            time_range=since or "1h",
            limit=tail_lines,
        )

        with log_source:
            for entry in log_source.tail(query, follow=follow):
                ctx.output.print(entry.format(show_source=False))

    except KeyboardInterrupt:
        ctx.output.print_info("\nStopped")
    except LogsError as e:
        ctx.output.print_error(f"Failed to get logs: {e}")
        raise click.Abort()
