"""Base deployment executor."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from devctl.core.exceptions import DeploymentError
from devctl.core.logging import get_logger
from devctl.deploy.models import (
    Deployment,
    DeploymentPhase,
    DeploymentStatus,
    DeploymentMetrics,
)

logger = get_logger(__name__)


class DeploymentExecutor(ABC):
    """Abstract base class for deployment executors."""

    def __init__(
        self,
        k8s_client: Any,
        notify_callback: Any = None,
    ):
        """Initialize executor.

        Args:
            k8s_client: Kubernetes client
            notify_callback: Callback for notifications
        """
        self._k8s = k8s_client
        self._notify = notify_callback

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Get strategy name."""
        pass

    def execute(self, deployment: Deployment, dry_run: bool = False) -> Deployment:
        """Execute the deployment.

        Args:
            deployment: Deployment to execute
            dry_run: If True, don't make actual changes

        Returns:
            Updated Deployment
        """
        deployment.started_at = datetime.utcnow()
        deployment.status = DeploymentStatus.IN_PROGRESS
        deployment.add_event("started", f"Deployment started using {self.strategy_name} strategy")

        try:
            # Initialize
            deployment.phase = DeploymentPhase.INITIALIZING
            self._initialize(deployment, dry_run)

            # Deploy
            deployment.phase = DeploymentPhase.DEPLOYING
            self._deploy(deployment, dry_run)

            # Verify
            deployment.phase = DeploymentPhase.VERIFYING
            if not self._verify(deployment, dry_run):
                raise DeploymentError("Health check verification failed")

            # Complete
            deployment.phase = DeploymentPhase.COMPLETED
            deployment.status = DeploymentStatus.SUCCEEDED
            deployment.progress = 100
            deployment.add_event("completed", "Deployment completed successfully")

        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.message = str(e)
            deployment.add_event("failed", f"Deployment failed: {e}")
            logger.error("Deployment failed", id=deployment.id, error=str(e))

        deployment.completed_at = datetime.utcnow()
        return deployment

    def promote(self, deployment: Deployment, dry_run: bool = False) -> Deployment:
        """Promote deployment (for canary/blue-green).

        Args:
            deployment: Deployment to promote
            dry_run: If True, don't make actual changes

        Returns:
            Updated Deployment
        """
        deployment.status = DeploymentStatus.PROMOTING
        deployment.phase = DeploymentPhase.PROMOTING
        deployment.add_event("promoting", "Promoting deployment")

        try:
            self._promote(deployment, dry_run)

            deployment.phase = DeploymentPhase.CLEANING_UP
            self._cleanup(deployment, dry_run)

            deployment.phase = DeploymentPhase.COMPLETED
            deployment.status = DeploymentStatus.SUCCEEDED
            deployment.progress = 100
            deployment.add_event("promoted", "Deployment promoted successfully")

        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.message = str(e)
            deployment.add_event("promote_failed", f"Promotion failed: {e}")

        deployment.completed_at = datetime.utcnow()
        return deployment

    def rollback(self, deployment: Deployment, dry_run: bool = False) -> Deployment:
        """Rollback deployment.

        Args:
            deployment: Deployment to rollback
            dry_run: If True, don't make actual changes

        Returns:
            Updated Deployment
        """
        deployment.status = DeploymentStatus.ROLLING_BACK
        deployment.phase = DeploymentPhase.ROLLED_BACK
        deployment.add_event("rolling_back", "Rolling back deployment")

        try:
            self._rollback(deployment, dry_run)

            deployment.status = DeploymentStatus.ABORTED
            deployment.add_event("rolled_back", "Deployment rolled back successfully")

        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.message = f"Rollback failed: {e}"
            deployment.add_event("rollback_failed", f"Rollback failed: {e}")

        deployment.completed_at = datetime.utcnow()
        return deployment

    def abort(self, deployment: Deployment, dry_run: bool = False) -> Deployment:
        """Abort deployment.

        Args:
            deployment: Deployment to abort
            dry_run: If True, don't make actual changes

        Returns:
            Updated Deployment
        """
        deployment.add_event("aborting", "Aborting deployment")

        try:
            self._abort(deployment, dry_run)
            deployment.status = DeploymentStatus.ABORTED
            deployment.add_event("aborted", "Deployment aborted")

        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.message = f"Abort failed: {e}"
            deployment.add_event("abort_failed", f"Abort failed: {e}")

        deployment.completed_at = datetime.utcnow()
        return deployment

    def get_metrics(self, deployment: Deployment) -> DeploymentMetrics:
        """Get current deployment metrics.

        Args:
            deployment: Deployment to get metrics for

        Returns:
            Current metrics
        """
        return self._get_metrics(deployment)

    @abstractmethod
    def _initialize(self, deployment: Deployment, dry_run: bool) -> None:
        """Initialize deployment resources."""
        pass

    @abstractmethod
    def _deploy(self, deployment: Deployment, dry_run: bool) -> None:
        """Execute deployment."""
        pass

    @abstractmethod
    def _verify(self, deployment: Deployment, dry_run: bool) -> bool:
        """Verify deployment health."""
        pass

    @abstractmethod
    def _promote(self, deployment: Deployment, dry_run: bool) -> None:
        """Promote deployment to full traffic."""
        pass

    @abstractmethod
    def _rollback(self, deployment: Deployment, dry_run: bool) -> None:
        """Rollback deployment."""
        pass

    @abstractmethod
    def _cleanup(self, deployment: Deployment, dry_run: bool) -> None:
        """Clean up old resources."""
        pass

    def _abort(self, deployment: Deployment, dry_run: bool) -> None:
        """Abort deployment. Default implementation calls rollback."""
        self._rollback(deployment, dry_run)

    def _get_metrics(self, deployment: Deployment) -> DeploymentMetrics:
        """Get deployment metrics. Override for real metrics."""
        return DeploymentMetrics(timestamp=datetime.utcnow())

    def _wait_for_rollout(
        self,
        deployment: Deployment,
        timeout: int = 300,
        dry_run: bool = False,
    ) -> bool:
        """Wait for rollout to complete.

        Args:
            deployment: Deployment to wait for
            timeout: Timeout in seconds
            dry_run: If True, skip waiting

        Returns:
            True if rollout succeeded
        """
        if dry_run:
            return True

        try:
            # Use K8s client to wait for rollout
            status = self._k8s.get_rollout_status(
                name=deployment.name,
                namespace=deployment.namespace,
                timeout=timeout,
            )
            return status.get("ready", False)

        except Exception as e:
            logger.warning(f"Rollout wait failed: {e}")
            return False

    def _notify_status(self, deployment: Deployment, message: str) -> None:
        """Send status notification."""
        if self._notify:
            try:
                self._notify(deployment, message)
            except Exception as e:
                logger.warning(f"Notification failed: {e}")
