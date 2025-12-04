"""EKS/Kubernetes pod logs source implementation."""

import re
import time
from datetime import datetime, timedelta
from typing import Any, Iterator

from devctl.core.exceptions import LogsError
from devctl.core.logs.base import LogEntry, LogLevel, LogQuery, LogSource, LogSourceFactory
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class EKSLogSource(LogSource):
    """Log source for EKS/Kubernetes pod logs."""

    def __init__(
        self,
        k8s_client: Any,
        default_namespace: str = "default",
    ):
        """Initialize EKS log source.

        Args:
            k8s_client: K8sClient instance
            default_namespace: Default namespace for queries
        """
        self._client = k8s_client
        self._default_namespace = default_namespace

    @property
    def name(self) -> str:
        return "eks"

    def search(self, query: LogQuery) -> list[LogEntry]:
        """Search Kubernetes pod logs."""
        if not query.pod:
            raise LogsError("pod is required for EKS log search")

        namespace = query.namespace or self._default_namespace

        try:
            # Calculate since_seconds from time range
            since_seconds = None
            if query.start_time:
                delta = datetime.utcnow() - query.start_time
                since_seconds = int(delta.total_seconds())

            # Get pod logs
            logs = self._client.get_pod_logs(
                name=query.pod,
                namespace=namespace,
                container=query.container,
                tail_lines=query.limit,
                since_seconds=since_seconds,
                timestamps=True,
            )

            entries = self._parse_logs(logs, namespace, query.pod, query.container)

            # Apply filters
            if query.filter_pattern:
                pattern = re.compile(query.filter_pattern, re.IGNORECASE)
                entries = [e for e in entries if pattern.search(e.message)]

            if query.levels:
                entries = [e for e in entries if e.level in query.levels]

            if query.query:
                query_lower = query.query.lower()
                entries = [e for e in entries if query_lower in e.message.lower()]

            return entries[:query.limit]

        except Exception as e:
            raise LogsError(f"EKS log search failed: {e}", source="eks")

    def tail(
        self,
        query: LogQuery,
        follow: bool = False,
    ) -> Iterator[LogEntry]:
        """Tail Kubernetes pod logs."""
        if not query.pod:
            raise LogsError("pod is required for EKS log tail")

        namespace = query.namespace or self._default_namespace

        try:
            if follow:
                # Use streaming logs
                yield from self._stream_logs(
                    namespace=namespace,
                    pod=query.pod,
                    container=query.container,
                    tail_lines=query.limit,
                    filter_pattern=query.filter_pattern,
                )
            else:
                # Just get current logs
                entries = self.search(query)
                for entry in entries:
                    yield entry

        except Exception as e:
            raise LogsError(f"EKS log tail failed: {e}", source="eks")

    def _stream_logs(
        self,
        namespace: str,
        pod: str,
        container: str | None = None,
        tail_lines: int = 100,
        filter_pattern: str | None = None,
    ) -> Iterator[LogEntry]:
        """Stream logs from a pod."""
        pattern = re.compile(filter_pattern, re.IGNORECASE) if filter_pattern else None

        # Get streaming response
        stream = self._client.stream_pod_logs(
            name=pod,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
            timestamps=True,
        )

        for line in stream:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")

            line = line.rstrip("\n")
            if not line:
                continue

            entry = self._parse_log_line(line, namespace, pod, container)

            if pattern and not pattern.search(entry.message):
                continue

            yield entry

    def _parse_logs(
        self,
        logs: str,
        namespace: str,
        pod: str,
        container: str | None = None,
    ) -> list[LogEntry]:
        """Parse log output into LogEntry objects."""
        entries: list[LogEntry] = []

        for line in logs.split("\n"):
            line = line.strip()
            if not line:
                continue

            entry = self._parse_log_line(line, namespace, pod, container)
            entries.append(entry)

        return entries

    def _parse_log_line(
        self,
        line: str,
        namespace: str,
        pod: str,
        container: str | None = None,
    ) -> LogEntry:
        """Parse a single log line."""
        # Format with timestamps: "2024-01-15T10:30:45.123456789Z message"
        timestamp = datetime.utcnow()
        message = line

        # Try to parse RFC3339Nano timestamp
        if len(line) > 30 and line[4] == "-" and line[10] == "T":
            try:
                ts_str = line[:30]  # RFC3339Nano is 30 chars
                # Handle nanosecond precision
                ts_str = ts_str.replace("Z", "+00:00")
                if "." in ts_str:
                    # Truncate to microseconds
                    parts = ts_str.split(".")
                    frac = parts[1][:6]
                    tz = ""
                    if "+" in parts[1]:
                        tz = "+" + parts[1].split("+")[1]
                    elif "-" in parts[1][1:]:
                        tz = "-" + parts[1].split("-")[-1]
                    ts_str = f"{parts[0]}.{frac}{tz}"

                timestamp = datetime.fromisoformat(ts_str)
                message = line[31:].strip() if len(line) > 31 else ""
            except (ValueError, IndexError):
                pass

        level = self._detect_level(message)

        # Build source identifier
        source_parts = [namespace, pod]
        if container:
            source_parts.append(container)
        source = "/".join(source_parts)

        labels = {
            "namespace": namespace,
            "pod": pod,
        }
        if container:
            labels["container"] = container

        return LogEntry(
            timestamp=timestamp,
            message=message,
            source=f"eks:{source}",
            level=level,
            labels=labels,
            raw={"line": line},
        )

    def _detect_level(self, message: str) -> LogLevel | None:
        """Detect log level from message."""
        message_lower = message.lower()

        # Common log format patterns
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

    def list_pods(
        self,
        namespace: str | None = None,
        label_selector: str | None = None,
    ) -> list[dict[str, Any]]:
        """List pods available for log access."""
        ns = namespace or self._default_namespace
        pods = self._client.list_pods(namespace=ns, label_selector=label_selector)

        return [
            {
                "name": pod["metadata"]["name"],
                "namespace": pod["metadata"]["namespace"],
                "status": pod["status"]["phase"],
                "containers": [
                    c["name"] for c in pod["spec"].get("containers", [])
                ],
            }
            for pod in pods
        ]

    def get_pod_containers(self, pod: str, namespace: str | None = None) -> list[str]:
        """Get container names for a pod."""
        ns = namespace or self._default_namespace
        pod_info = self._client.get_pod(pod, namespace=ns)
        return [c["name"] for c in pod_info["spec"].get("containers", [])]


# Register with factory
LogSourceFactory.register("eks", EKSLogSource)
