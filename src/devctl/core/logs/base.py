"""Base classes for log source abstractions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Iterator

from devctl.core.exceptions import LogsError


class LogLevel(str, Enum):
    """Log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class LogEntry:
    """Represents a single log entry."""

    timestamp: datetime
    message: str
    source: str
    level: LogLevel | None = None
    labels: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "source": self.source,
            "level": self.level.value if self.level else None,
            "labels": self.labels,
        }

    def format(self, show_source: bool = True) -> str:
        """Format log entry for display."""
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        level_str = f"[{self.level.value.upper()}]" if self.level else ""
        source_str = f"[{self.source}]" if show_source else ""
        parts = [ts, level_str, source_str, self.message]
        return " ".join(p for p in parts if p)


@dataclass
class LogQuery:
    """Query parameters for log searches."""

    # Time range
    start_time: datetime | None = None
    end_time: datetime | None = None
    time_range: str | None = None  # e.g., "1h", "30m", "7d"

    # Filtering
    query: str | None = None  # Free-text search
    filter_pattern: str | None = None  # Regex pattern
    levels: list[LogLevel] | None = None
    labels: dict[str, str] | None = None

    # Source-specific
    log_group: str | None = None  # CloudWatch
    log_stream: str | None = None  # CloudWatch
    namespace: str | None = None  # K8s/Loki
    pod: str | None = None  # K8s/Loki
    container: str | None = None  # K8s

    # Pagination
    limit: int = 100
    offset: int = 0

    def __post_init__(self) -> None:
        """Parse time_range if provided."""
        if self.time_range and not self.start_time:
            self.start_time = self._parse_time_range(self.time_range)
        if not self.end_time:
            self.end_time = datetime.utcnow()

    def _parse_time_range(self, time_range: str) -> datetime:
        """Parse time range string to datetime."""
        now = datetime.utcnow()
        value = int(time_range[:-1])
        unit = time_range[-1].lower()

        if unit == "m":
            return now - timedelta(minutes=value)
        elif unit == "h":
            return now - timedelta(hours=value)
        elif unit == "d":
            return now - timedelta(days=value)
        elif unit == "w":
            return now - timedelta(weeks=value)
        else:
            raise LogsError(f"Invalid time range unit: {unit}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "query": self.query,
            "filter_pattern": self.filter_pattern,
            "levels": [l.value for l in self.levels] if self.levels else None,
            "labels": self.labels,
            "log_group": self.log_group,
            "namespace": self.namespace,
            "pod": self.pod,
            "limit": self.limit,
        }


class LogSource(ABC):
    """Abstract base class for log sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Get log source name."""
        pass

    @abstractmethod
    def search(self, query: LogQuery) -> list[LogEntry]:
        """Search logs matching query.

        Args:
            query: Log query parameters

        Returns:
            List of matching log entries
        """
        pass

    @abstractmethod
    def tail(
        self,
        query: LogQuery,
        follow: bool = False,
    ) -> Iterator[LogEntry]:
        """Tail logs, optionally following.

        Args:
            query: Log query parameters
            follow: If True, continue streaming new logs

        Yields:
            Log entries as they arrive
        """
        pass

    def close(self) -> None:
        """Clean up resources."""
        pass

    def __enter__(self) -> "LogSource":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class LogSourceFactory:
    """Factory for creating log sources."""

    _sources: dict[str, type[LogSource]] = {}

    @classmethod
    def register(cls, name: str, source_class: type[LogSource]) -> None:
        """Register a log source type."""
        cls._sources[name] = source_class

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> LogSource:
        """Create a log source instance.

        Args:
            name: Source name (cloudwatch, loki, eks)
            **kwargs: Source-specific configuration

        Returns:
            LogSource instance
        """
        if name not in cls._sources:
            raise LogsError(
                f"Unknown log source: {name}. Available: {list(cls._sources.keys())}"
            )
        return cls._sources[name](**kwargs)

    @classmethod
    def available_sources(cls) -> list[str]:
        """Get list of available source names."""
        return list(cls._sources.keys())
