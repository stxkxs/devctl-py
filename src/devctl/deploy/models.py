"""Deployment data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import uuid


class DeploymentStrategy(str, Enum):
    """Deployment strategies."""

    ROLLING = "rolling"
    BLUE_GREEN = "blue-green"
    CANARY = "canary"


class DeploymentStatus(str, Enum):
    """Deployment status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    PROMOTING = "promoting"
    ROLLING_BACK = "rolling_back"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


class DeploymentPhase(str, Enum):
    """Deployment phases."""

    INITIALIZING = "initializing"
    DEPLOYING = "deploying"
    VERIFYING = "verifying"
    PROMOTING = "promoting"
    CLEANING_UP = "cleaning_up"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


@dataclass
class HealthCheck:
    """Health check configuration."""

    enabled: bool = True
    endpoint: str = "/health"
    port: int = 8080
    initial_delay: int = 10  # seconds
    interval: int = 5  # seconds
    timeout: int = 3  # seconds
    success_threshold: int = 3
    failure_threshold: int = 3


@dataclass
class DeploymentMetrics:
    """Deployment metrics snapshot."""

    timestamp: datetime
    success_rate: float = 0.0
    error_rate: float = 0.0
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_p99: float = 0.0
    requests_per_second: float = 0.0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "success_rate": self.success_rate,
            "error_rate": self.error_rate,
            "latency_p50": self.latency_p50,
            "latency_p95": self.latency_p95,
            "latency_p99": self.latency_p99,
            "requests_per_second": self.requests_per_second,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
        }


@dataclass
class DeploymentEvent:
    """Deployment event for audit trail."""

    timestamp: datetime
    event_type: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class Deployment:
    """Deployment instance."""

    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    namespace: str = "default"
    cluster: str = ""

    # Target
    image: str = ""
    replicas: int = 1
    previous_image: str | None = None

    # Strategy
    strategy: DeploymentStrategy = DeploymentStrategy.ROLLING
    strategy_config: dict[str, Any] = field(default_factory=dict)

    # Status
    status: DeploymentStatus = DeploymentStatus.PENDING
    phase: DeploymentPhase = DeploymentPhase.INITIALIZING
    progress: int = 0  # 0-100
    message: str = ""

    # Health
    health_check: HealthCheck = field(default_factory=HealthCheck)

    # Canary-specific
    canary_weight: int = 0  # Traffic percentage to canary

    # Blue-Green specific
    active_color: str = "blue"  # blue or green

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # History
    events: list[DeploymentEvent] = field(default_factory=list)
    metrics_history: list[DeploymentMetrics] = field(default_factory=list)

    # Metadata
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)

    def add_event(self, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
        """Add an event to the deployment history."""
        self.events.append(
            DeploymentEvent(
                timestamp=datetime.utcnow(),
                event_type=event_type,
                message=message,
                details=details or {},
            )
        )

    def add_metrics(self, metrics: DeploymentMetrics) -> None:
        """Add metrics snapshot to history."""
        self.metrics_history.append(metrics)
        # Keep last 100 snapshots
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]

    @property
    def duration_seconds(self) -> float | None:
        """Get deployment duration in seconds."""
        if self.started_at:
            end = self.completed_at or datetime.utcnow()
            return (end - self.started_at).total_seconds()
        return None

    @property
    def is_active(self) -> bool:
        """Check if deployment is active."""
        return self.status in (
            DeploymentStatus.IN_PROGRESS,
            DeploymentStatus.PAUSED,
            DeploymentStatus.PROMOTING,
            DeploymentStatus.ROLLING_BACK,
        )

    @property
    def is_complete(self) -> bool:
        """Check if deployment is complete."""
        return self.status in (
            DeploymentStatus.SUCCEEDED,
            DeploymentStatus.FAILED,
            DeploymentStatus.ABORTED,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "namespace": self.namespace,
            "cluster": self.cluster,
            "image": self.image,
            "replicas": self.replicas,
            "previous_image": self.previous_image,
            "strategy": self.strategy.value,
            "status": self.status.value,
            "phase": self.phase.value,
            "progress": self.progress,
            "message": self.message,
            "canary_weight": self.canary_weight,
            "active_color": self.active_color,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "labels": self.labels,
            "events": [e.to_dict() for e in self.events[-20:]],  # Last 20 events
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Deployment":
        """Create from dictionary."""
        deployment = cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            namespace=data.get("namespace", "default"),
            cluster=data.get("cluster", ""),
            image=data.get("image", ""),
            replicas=data.get("replicas", 1),
            previous_image=data.get("previous_image"),
            strategy=DeploymentStrategy(data.get("strategy", "rolling")),
            strategy_config=data.get("strategy_config", {}),
            status=DeploymentStatus(data.get("status", "pending")),
            phase=DeploymentPhase(data.get("phase", "initializing")),
            progress=data.get("progress", 0),
            message=data.get("message", ""),
            canary_weight=data.get("canary_weight", 0),
            active_color=data.get("active_color", "blue"),
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
        )

        # Parse timestamps
        if data.get("created_at"):
            deployment.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            deployment.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            deployment.completed_at = datetime.fromisoformat(data["completed_at"])

        return deployment
