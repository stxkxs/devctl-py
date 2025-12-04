"""CloudWatch Logs source implementation."""

import re
import time
from datetime import datetime
from typing import Any, Iterator

from devctl.core.exceptions import LogsError
from devctl.core.logs.base import LogEntry, LogLevel, LogQuery, LogSource, LogSourceFactory
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class CloudWatchLogSource(LogSource):
    """Log source for AWS CloudWatch Logs."""

    def __init__(
        self,
        logs_client: Any,
        log_group_prefix: str | None = None,
    ):
        """Initialize CloudWatch log source.

        Args:
            logs_client: boto3 CloudWatch Logs client
            log_group_prefix: Optional prefix for log group names
        """
        self._client = logs_client
        self._log_group_prefix = log_group_prefix

    @property
    def name(self) -> str:
        return "cloudwatch"

    def search(self, query: LogQuery) -> list[LogEntry]:
        """Search CloudWatch logs."""
        if not query.log_group:
            raise LogsError("log_group is required for CloudWatch search")

        log_group = self._resolve_log_group(query.log_group)
        entries: list[LogEntry] = []

        try:
            # Use CloudWatch Logs Insights for complex queries
            if query.query:
                entries = self._insights_query(log_group, query)
            else:
                entries = self._filter_logs(log_group, query)

        except Exception as e:
            raise LogsError(f"CloudWatch search failed: {e}", source="cloudwatch")

        return entries

    def tail(
        self,
        query: LogQuery,
        follow: bool = False,
    ) -> Iterator[LogEntry]:
        """Tail CloudWatch logs."""
        if not query.log_group:
            raise LogsError("log_group is required for CloudWatch tail")

        log_group = self._resolve_log_group(query.log_group)
        seen_event_ids: set[str] = set()
        last_timestamp = int(query.start_time.timestamp() * 1000) if query.start_time else 0

        try:
            while True:
                params: dict[str, Any] = {
                    "logGroupName": log_group,
                    "startTime": last_timestamp,
                    "interleaved": True,
                }

                if query.log_stream:
                    params["logStreamNames"] = [query.log_stream]
                if query.filter_pattern:
                    params["filterPattern"] = query.filter_pattern
                if query.limit:
                    params["limit"] = min(query.limit, 10000)

                response = self._client.filter_log_events(**params)

                for event in response.get("events", []):
                    event_id = event["eventId"]
                    if event_id not in seen_event_ids:
                        seen_event_ids.add(event_id)
                        entry = self._parse_log_event(event, log_group)
                        yield entry
                        last_timestamp = max(last_timestamp, event["timestamp"])

                if not follow:
                    # Process all pages then exit
                    next_token = response.get("nextToken")
                    if not next_token:
                        break
                    params["nextToken"] = next_token
                else:
                    # Wait before polling for new logs
                    time.sleep(1)
                    # Move forward slightly to avoid duplicates
                    last_timestamp += 1
                    # Limit seen events set size
                    if len(seen_event_ids) > 10000:
                        seen_event_ids = set(list(seen_event_ids)[-5000:])

        except Exception as e:
            raise LogsError(f"CloudWatch tail failed: {e}", source="cloudwatch")

    def _resolve_log_group(self, log_group: str) -> str:
        """Resolve log group name with optional prefix."""
        if self._log_group_prefix and not log_group.startswith("/"):
            return f"{self._log_group_prefix}/{log_group}"
        return log_group

    def _filter_logs(self, log_group: str, query: LogQuery) -> list[LogEntry]:
        """Filter logs using FilterLogEvents API."""
        entries: list[LogEntry] = []

        params: dict[str, Any] = {
            "logGroupName": log_group,
            "limit": min(query.limit, 10000),
        }

        if query.start_time:
            params["startTime"] = int(query.start_time.timestamp() * 1000)
        if query.end_time:
            params["endTime"] = int(query.end_time.timestamp() * 1000)
        if query.log_stream:
            params["logStreamNames"] = [query.log_stream]
        if query.filter_pattern:
            params["filterPattern"] = query.filter_pattern

        paginator = self._client.get_paginator("filter_log_events")

        for page in paginator.paginate(**params):
            for event in page.get("events", []):
                entry = self._parse_log_event(event, log_group)
                entries.append(entry)
                if len(entries) >= query.limit:
                    return entries

        return entries

    def _insights_query(self, log_group: str, query: LogQuery) -> list[LogEntry]:
        """Run CloudWatch Logs Insights query."""
        # Build Insights query
        insights_query = query.query or "fields @timestamp, @message"

        # Add time range if not in query
        if "@timestamp" not in insights_query.lower():
            insights_query = f"fields @timestamp, @message | {insights_query}"

        # Add limit
        insights_query = f"{insights_query} | limit {query.limit}"

        start_time = query.start_time or datetime.utcnow()
        end_time = query.end_time or datetime.utcnow()

        # Start query
        response = self._client.start_query(
            logGroupName=log_group,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=insights_query,
        )

        query_id = response["queryId"]

        # Poll for results
        while True:
            result = self._client.get_query_results(queryId=query_id)
            status = result["status"]

            if status == "Complete":
                break
            elif status in ("Failed", "Cancelled"):
                raise LogsError(f"Insights query {status.lower()}")

            time.sleep(0.5)

        # Parse results
        entries: list[LogEntry] = []
        for result_row in result.get("results", []):
            entry = self._parse_insights_result(result_row, log_group)
            if entry:
                entries.append(entry)

        return entries

    def _parse_log_event(self, event: dict[str, Any], log_group: str) -> LogEntry:
        """Parse CloudWatch log event to LogEntry."""
        timestamp = datetime.fromtimestamp(event["timestamp"] / 1000)
        message = event.get("message", "")

        # Try to detect log level
        level = self._detect_level(message)

        return LogEntry(
            timestamp=timestamp,
            message=message,
            source=f"cloudwatch:{log_group}",
            level=level,
            labels={
                "log_group": log_group,
                "log_stream": event.get("logStreamName", ""),
            },
            raw=event,
        )

    def _parse_insights_result(
        self, result: list[dict[str, str]], log_group: str
    ) -> LogEntry | None:
        """Parse Insights query result row to LogEntry."""
        data = {item["field"]: item["value"] for item in result}

        timestamp_str = data.get("@timestamp")
        message = data.get("@message", "")

        if not timestamp_str:
            return None

        try:
            # Parse ISO format timestamp
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            timestamp = datetime.utcnow()

        level = self._detect_level(message)

        return LogEntry(
            timestamp=timestamp,
            message=message,
            source=f"cloudwatch:{log_group}",
            level=level,
            labels={"log_group": log_group},
            raw=data,
        )

    def _detect_level(self, message: str) -> LogLevel | None:
        """Detect log level from message content."""
        message_lower = message.lower()

        level_patterns = [
            (LogLevel.CRITICAL, r"\b(critical|fatal|panic)\b"),
            (LogLevel.ERROR, r"\b(error|err|exception|fail)\b"),
            (LogLevel.WARNING, r"\b(warn|warning)\b"),
            (LogLevel.INFO, r"\b(info)\b"),
            (LogLevel.DEBUG, r"\b(debug|trace)\b"),
        ]

        for level, pattern in level_patterns:
            if re.search(pattern, message_lower):
                return level

        return None

    def list_log_groups(self, prefix: str | None = None) -> list[dict[str, Any]]:
        """List available log groups."""
        params: dict[str, Any] = {}
        if prefix:
            params["logGroupNamePrefix"] = prefix
        elif self._log_group_prefix:
            params["logGroupNamePrefix"] = self._log_group_prefix

        groups: list[dict[str, Any]] = []
        paginator = self._client.get_paginator("describe_log_groups")

        for page in paginator.paginate(**params):
            for group in page.get("logGroups", []):
                groups.append({
                    "name": group["logGroupName"],
                    "stored_bytes": group.get("storedBytes", 0),
                    "retention_days": group.get("retentionInDays"),
                    "created": datetime.fromtimestamp(
                        group.get("creationTime", 0) / 1000
                    ),
                })

        return groups

    def list_log_streams(
        self, log_group: str, prefix: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List log streams in a log group."""
        log_group = self._resolve_log_group(log_group)
        params: dict[str, Any] = {
            "logGroupName": log_group,
            "orderBy": "LastEventTime",
            "descending": True,
            "limit": limit,
        }
        if prefix:
            params["logStreamNamePrefix"] = prefix

        response = self._client.describe_log_streams(**params)

        streams: list[dict[str, Any]] = []
        for stream in response.get("logStreams", []):
            streams.append({
                "name": stream["logStreamName"],
                "first_event": datetime.fromtimestamp(
                    stream.get("firstEventTimestamp", 0) / 1000
                ) if stream.get("firstEventTimestamp") else None,
                "last_event": datetime.fromtimestamp(
                    stream.get("lastEventTimestamp", 0) / 1000
                ) if stream.get("lastEventTimestamp") else None,
                "stored_bytes": stream.get("storedBytes", 0),
            })

        return streams


# Register with factory
LogSourceFactory.register("cloudwatch", CloudWatchLogSource)
