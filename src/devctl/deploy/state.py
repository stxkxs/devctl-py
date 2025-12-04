"""Deployment state management."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from devctl.core.exceptions import DeploymentError
from devctl.core.logging import get_logger
from devctl.deploy.models import Deployment, DeploymentStatus

logger = get_logger(__name__)


class DeploymentState:
    """Manage deployment state persistence."""

    def __init__(self, state_dir: str | Path | None = None):
        """Initialize deployment state manager.

        Args:
            state_dir: Directory to store deployment state
        """
        if state_dir:
            self._state_dir = Path(state_dir)
            self._state_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Use default location
            self._state_dir = Path.home() / ".devctl" / "deployments"
            self._state_dir.mkdir(parents=True, exist_ok=True)

    def save(self, deployment: Deployment) -> None:
        """Save deployment state.

        Args:
            deployment: Deployment to save
        """
        state_file = self._state_dir / f"{deployment.id}.json"

        try:
            with open(state_file, "w") as f:
                json.dump(deployment.to_dict(), f, indent=2)

            logger.debug("Saved deployment state", id=deployment.id)

        except Exception as e:
            raise DeploymentError(
                f"Failed to save deployment state: {e}",
                deployment_id=deployment.id,
            )

    def load(self, deployment_id: str) -> Deployment:
        """Load deployment state.

        Args:
            deployment_id: Deployment ID

        Returns:
            Loaded Deployment
        """
        state_file = self._state_dir / f"{deployment_id}.json"

        if not state_file.exists():
            raise DeploymentError(
                f"Deployment not found: {deployment_id}",
                deployment_id=deployment_id,
            )

        try:
            with open(state_file) as f:
                data = json.load(f)

            return Deployment.from_dict(data)

        except Exception as e:
            raise DeploymentError(
                f"Failed to load deployment state: {e}",
                deployment_id=deployment_id,
            )

    def delete(self, deployment_id: str) -> None:
        """Delete deployment state.

        Args:
            deployment_id: Deployment ID
        """
        state_file = self._state_dir / f"{deployment_id}.json"

        if state_file.exists():
            state_file.unlink()
            logger.debug("Deleted deployment state", id=deployment_id)

    def list(
        self,
        status: DeploymentStatus | None = None,
        namespace: str | None = None,
        limit: int = 50,
    ) -> list[Deployment]:
        """List deployments.

        Args:
            status: Filter by status
            namespace: Filter by namespace
            limit: Maximum deployments to return

        Returns:
            List of Deployments
        """
        deployments: list[Deployment] = []

        for state_file in self._state_dir.glob("*.json"):
            try:
                with open(state_file) as f:
                    data = json.load(f)

                deployment = Deployment.from_dict(data)

                # Apply filters
                if status and deployment.status != status:
                    continue
                if namespace and deployment.namespace != namespace:
                    continue

                deployments.append(deployment)

            except Exception as e:
                logger.warning(f"Failed to load deployment {state_file}: {e}")

        # Sort by created_at descending
        deployments.sort(key=lambda d: d.created_at, reverse=True)

        return deployments[:limit]

    def list_active(self) -> list[Deployment]:
        """List active deployments.

        Returns:
            List of active Deployments
        """
        return [d for d in self.list(limit=100) if d.is_active]

    def get_by_name(self, name: str, namespace: str = "default") -> Deployment | None:
        """Get deployment by name and namespace.

        Args:
            name: Deployment name
            namespace: Namespace

        Returns:
            Deployment or None
        """
        for deployment in self.list(namespace=namespace, limit=100):
            if deployment.name == name:
                return deployment
        return None

    def cleanup_old(self, days: int = 30) -> int:
        """Clean up old completed deployments.

        Args:
            days: Remove deployments older than this many days

        Returns:
            Number of deployments removed
        """
        cutoff = datetime.utcnow().timestamp() - (days * 86400)
        removed = 0

        for state_file in self._state_dir.glob("*.json"):
            try:
                with open(state_file) as f:
                    data = json.load(f)

                deployment = Deployment.from_dict(data)

                # Only clean up completed deployments
                if not deployment.is_complete:
                    continue

                # Check age
                if deployment.created_at.timestamp() < cutoff:
                    state_file.unlink()
                    removed += 1

            except Exception:
                pass

        if removed > 0:
            logger.info(f"Cleaned up {removed} old deployments")

        return removed
