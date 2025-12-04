"""Grafana Loki log source implementation."""

import re
import time
from datetime import datetime
from typing import Any, Iterator

from devctl.core.exceptions import LogsError
from devctl.core.logs.base import LogEntry, LogLevel, LogQuery, LogSource, LogSourceFactory
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class LokiLogSource(LogSource):
    """Log source for Grafana Loki via Grafana API."""

    def __init__(
        self,
        grafana_client: Any,
        datasource_uid: str | None = None,
    ):
        """Initialize Loki log source.

        Args:
            grafana_client: GrafanaClient instance
            datasource_uid: Loki datasource UID in Grafana
        """
        self._client = grafana_client
        self._datasource_uid = datasource_uid

    @property
    def name(self) -> str:
        return "loki"

    def search(self, query: LogQuery) -> list[LogEntry]:
        """Search Loki logs via Grafana."""
        logql = self._build_logql(query)

        try:
            # Use Grafana's datasource proxy API
            entries = self._query_range(logql, query)
            return entries

        except Exception as e:
            raise LogsError(f"Loki search failed: {e}", source="loki")

    def tail(
        self,
        query: LogQuery,
        follow: bool = False,
    ) -> Iterator[LogEntry]:
        """Tail Loki logs."""
        logql = self._build_logql(query)
        last_timestamp = query.start_time or datetime.utcnow()

        try:
            while True:
                # Query for logs since last timestamp
                tail_query = LogQuery(
                    start_time=last_timestamp,
                    end_time=datetime.utcnow(),
                    limit=query.limit,
                )

                entries = self._query_range(logql, tail_query)

                for entry in entries:
                    yield entry
                    if entry.timestamp > last_timestamp:
                        last_timestamp = entry.timestamp

                if not follow:
                    break

                time.sleep(1)

        except Exception as e:
            raise LogsError(f"Loki tail failed: {e}", source="loki")

    def _build_logql(self, query: LogQuery) -> str:
        """Build LogQL query from LogQuery."""
        # Start with label selectors
        labels: list[str] = []

        if query.labels:
            for key, value in query.labels.items():
                labels.append(f'{key}="{value}"')

        if query.namespace:
            labels.append(f'namespace="{query.namespace}"')
        if query.pod:
            labels.append(f'pod=~"{query.pod}.*"')
        if query.container:
            labels.append(f'container="{query.container}"')

        # Build selector
        if labels:
            selector = "{" + ", ".join(labels) + "}"
        else:
            selector = '{job=~".+"}'  # Match any job

        logql = selector

        # Add filter expression
        if query.query:
            # Check if it's already LogQL or plain text
            if "|" in query.query or "{" in query.query:
                # Assume it's LogQL
                logql = query.query
            else:
                # Plain text search
                logql = f'{selector} |= "{query.query}"'

        if query.filter_pattern:
            logql = f'{logql} |~ "{query.filter_pattern}"'

        # Add level filter
        if query.levels:
            level_pattern = "|".join(l.value for l in query.levels)
            logql = f'{logql} |~ "(?i)({level_pattern})"'

        return logql

    def _query_range(self, logql: str, query: LogQuery) -> list[LogEntry]:
        """Execute range query against Loki."""
        # Convert times to nanoseconds
        start_ns = int(query.start_time.timestamp() * 1e9) if query.start_time else 0
        end_ns = int(query.end_time.timestamp() * 1e9) if query.end_time else int(datetime.utcnow().timestamp() * 1e9)

        # Use Grafana's datasource proxy
        datasource_uid = self._datasource_uid or self._find_loki_datasource()
        if not datasource_uid:
            raise LogsError("No Loki datasource found in Grafana")

        params = {
            "query": logql,
            "start": start_ns,
            "end": end_ns,
            "limit": query.limit,
            "direction": "backward",
        }

        # Query via Grafana proxy
        response = self._client.get(
            f"/api/datasources/proxy/uid/{datasource_uid}/loki/api/v1/query_range",
            params=params,
        )

        return self._parse_response(response)

    def _find_loki_datasource(self) -> str | None:
        """Find a Loki datasource in Grafana."""
        try:
            datasources = self._client.list_datasources()
            for ds in datasources:
                if ds.get("type") == "loki":
                    return ds.get("uid")
        except Exception:
            pass
        return None

    def _parse_response(self, response: dict[str, Any]) -> list[LogEntry]:
        """Parse Loki query response."""
        entries: list[LogEntry] = []

        data = response.get("data", {})
        result_type = data.get("resultType", "")

        if result_type == "streams":
            for stream in data.get("result", []):
                labels = stream.get("stream", {})
                for value in stream.get("values", []):
                    entry = self._parse_stream_value(value, labels)
                    entries.append(entry)

        # Sort by timestamp descending
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries

    def _parse_stream_value(
        self, value: list[str], labels: dict[str, str]
    ) -> LogEntry:
        """Parse a single stream value."""
        # value is [timestamp_ns, log_line]
        timestamp_ns = int(value[0])
        message = value[1]

        timestamp = datetime.fromtimestamp(timestamp_ns / 1e9)
        level = self._detect_level(message)

        # Build source from labels
        source_parts = []
        if "namespace" in labels:
            source_parts.append(labels["namespace"])
        if "pod" in labels:
            source_parts.append(labels["pod"])
        if "container" in labels:
            source_parts.append(labels["container"])

        source = "/".join(source_parts) if source_parts else "loki"

        return LogEntry(
            timestamp=timestamp,
            message=message,
            source=f"loki:{source}",
            level=level,
            labels=labels,
            raw={"timestamp_ns": timestamp_ns, "line": message},
        )

    def _detect_level(self, message: str) -> LogLevel | None:
        """Detect log level from message."""
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

    def get_labels(self) -> list[str]:
        """Get available label names."""
        datasource_uid = self._datasource_uid or self._find_loki_datasource()
        if not datasource_uid:
            return []

        try:
            response = self._client.get(
                f"/api/datasources/proxy/uid/{datasource_uid}/loki/api/v1/labels"
            )
            return response.get("data", [])
        except Exception:
            return []

    def get_label_values(self, label: str) -> list[str]:
        """Get values for a label."""
        datasource_uid = self._datasource_uid or self._find_loki_datasource()
        if not datasource_uid:
            return []

        try:
            response = self._client.get(
                f"/api/datasources/proxy/uid/{datasource_uid}/loki/api/v1/label/{label}/values"
            )
            return response.get("data", [])
        except Exception:
            return []


# Register with factory
LogSourceFactory.register("loki", LokiLogSource)
