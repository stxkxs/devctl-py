"""Blue-Green deployment strategy executor."""

import time
from datetime import datetime
from typing import Any

from devctl.core.logging import get_logger
from devctl.deploy.models import Deployment, DeploymentMetrics
from devctl.deploy.strategies.base import DeploymentExecutor

logger = get_logger(__name__)


class BlueGreenDeploymentExecutor(DeploymentExecutor):
    """Blue-Green deployment executor."""

    @property
    def strategy_name(self) -> str:
        return "blue-green"

    def _get_colors(self, deployment: Deployment) -> tuple[str, str]:
        """Get active and inactive colors."""
        active = deployment.active_color
        inactive = "green" if active == "blue" else "blue"
        return active, inactive

    def _initialize(self, deployment: Deployment, dry_run: bool) -> None:
        """Initialize blue-green deployment."""
        active, inactive = self._get_colors(deployment)
        deployment.add_event("init", f"Initializing blue-green deployment (active={active})")

        if dry_run:
            deployment.add_event("dry_run", f"Would create {inactive} deployment")
            return

        # Check if inactive deployment exists
        inactive_name = f"{deployment.name}-{inactive}"

        try:
            existing = self._k8s.get_deployment(
                name=inactive_name,
                namespace=deployment.namespace,
            )
            deployment.add_event("init_existing", f"Found existing {inactive} deployment")
        except Exception:
            deployment.add_event("init_new", f"Will create new {inactive} deployment")

    def _deploy(self, deployment: Deployment, dry_run: bool) -> None:
        """Deploy to inactive color."""
        active, inactive = self._get_colors(deployment)
        inactive_name = f"{deployment.name}-{inactive}"

        deployment.add_event("deploying", f"Deploying to {inactive}: {deployment.image}")
        deployment.progress = 10

        if dry_run:
            deployment.add_event("dry_run", f"Would deploy to {inactive_name}")
            deployment.progress = 50
            return

        # Create or update inactive deployment
        try:
            # Try to update existing
            self._k8s.update_deployment_image(
                name=inactive_name,
                namespace=deployment.namespace,
                image=deployment.image,
            )
            deployment.add_event("updated", f"Updated {inactive} deployment")
        except Exception:
            # Create new deployment
            self._create_color_deployment(deployment, inactive)
            deployment.add_event("created", f"Created {inactive} deployment")

        deployment.progress = 30

        # Scale up inactive deployment
        self._k8s.scale_deployment(
            name=inactive_name,
            namespace=deployment.namespace,
            replicas=deployment.replicas,
        )

        deployment.progress = 40
        deployment.add_event("scaled", f"Scaled {inactive} to {deployment.replicas} replicas")

        # Wait for rollout
        timeout = deployment.strategy_config.get("timeout", 300)
        if not self._wait_for_rollout_named(inactive_name, deployment.namespace, timeout):
            raise Exception(f"{inactive} deployment rollout timed out")

        deployment.progress = 60
        deployment.add_event("ready", f"{inactive} deployment is ready")

    def _verify(self, deployment: Deployment, dry_run: bool) -> bool:
        """Verify inactive deployment health."""
        if dry_run:
            deployment.add_event("dry_run", "Would verify health")
            return True

        if not deployment.health_check.enabled:
            deployment.add_event("skip_health", "Health check disabled")
            return True

        active, inactive = self._get_colors(deployment)
        inactive_name = f"{deployment.name}-{inactive}"

        deployment.add_event("verifying", f"Verifying {inactive} deployment health")

        # Check pod health
        success_count = 0
        check_count = 0
        max_checks = deployment.health_check.success_threshold + deployment.health_check.failure_threshold

        time.sleep(deployment.health_check.initial_delay)

        while check_count < max_checks:
            healthy = self._check_deployment_health(inactive_name, deployment.namespace)

            if healthy:
                success_count += 1
                if success_count >= deployment.health_check.success_threshold:
                    deployment.add_event("healthy", f"{inactive} is healthy")
                    deployment.progress = 80
                    return True
            else:
                success_count = 0

            check_count += 1
            time.sleep(deployment.health_check.interval)

        deployment.add_event("unhealthy", f"{inactive} health checks failed")
        return False

    def _promote(self, deployment: Deployment, dry_run: bool) -> None:
        """Switch traffic to new color."""
        active, inactive = self._get_colors(deployment)

        deployment.add_event("promoting", f"Switching traffic from {active} to {inactive}")

        if dry_run:
            deployment.add_event("dry_run", "Would update service selector")
            return

        # Update service to point to new color
        service_name = deployment.strategy_config.get("service", deployment.name)

        self._k8s.patch_service(
            name=service_name,
            namespace=deployment.namespace,
            patch={
                "spec": {
                    "selector": {
                        "app": deployment.name,
                        "color": inactive,
                    }
                }
            },
        )

        # Update active color
        deployment.active_color = inactive
        deployment.add_event("switched", f"Traffic now routing to {inactive}")

    def _rollback(self, deployment: Deployment, dry_run: bool) -> None:
        """Rollback by switching back to previous color."""
        active, inactive = self._get_colors(deployment)

        # Inactive is what we just deployed, so switch back to active
        deployment.add_event("rollback", f"Switching traffic back to {active}")

        if dry_run:
            deployment.add_event("dry_run", "Would update service selector")
            return

        service_name = deployment.strategy_config.get("service", deployment.name)

        self._k8s.patch_service(
            name=service_name,
            namespace=deployment.namespace,
            patch={
                "spec": {
                    "selector": {
                        "app": deployment.name,
                        "color": active,
                    }
                }
            },
        )

        deployment.add_event("rolled_back", f"Traffic restored to {active}")

    def _cleanup(self, deployment: Deployment, dry_run: bool) -> None:
        """Scale down old color deployment."""
        # After promotion, the old active color should be scaled down
        # active_color is now the NEW active (was inactive before promote)
        old_color = "blue" if deployment.active_color == "green" else "green"
        old_name = f"{deployment.name}-{old_color}"

        deployment.add_event("cleanup", f"Scaling down {old_color} deployment")

        if dry_run:
            deployment.add_event("dry_run", f"Would scale down {old_name}")
            return

        # Scale down but don't delete (for quick rollback)
        self._k8s.scale_deployment(
            name=old_name,
            namespace=deployment.namespace,
            replicas=0,
        )

        deployment.add_event("cleanup_complete", f"Scaled down {old_color} to 0 replicas")

    def _create_color_deployment(self, deployment: Deployment, color: str) -> None:
        """Create a new color deployment."""
        deployment_name = f"{deployment.name}-{color}"

        # Get template from active deployment or create new
        active_name = f"{deployment.name}-{deployment.active_color}"

        try:
            template = self._k8s.get_deployment(
                name=active_name,
                namespace=deployment.namespace,
            )

            # Modify for new color
            template["metadata"]["name"] = deployment_name
            template["metadata"]["labels"]["color"] = color
            template["spec"]["selector"]["matchLabels"]["color"] = color
            template["spec"]["template"]["metadata"]["labels"]["color"] = color
            template["spec"]["template"]["spec"]["containers"][0]["image"] = deployment.image
            template["spec"]["replicas"] = 0  # Start scaled down

            self._k8s.create_deployment(
                namespace=deployment.namespace,
                body=template,
            )

        except Exception as e:
            logger.warning(f"Could not clone from active deployment: {e}")
            raise Exception(f"Failed to create {color} deployment: {e}")

    def _wait_for_rollout_named(self, name: str, namespace: str, timeout: int) -> bool:
        """Wait for a specific deployment rollout."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                status = self._k8s.get_rollout_status(name=name, namespace=namespace)
                if status.get("ready", False):
                    return True
            except Exception:
                pass

            time.sleep(5)

        return False

    def _check_deployment_health(self, name: str, namespace: str) -> bool:
        """Check if a deployment's pods are healthy."""
        try:
            pods = self._k8s.list_pods(
                namespace=namespace,
                label_selector=f"app={name.rsplit('-', 1)[0]},color={name.rsplit('-', 1)[1]}",
            )

            if not pods:
                return False

            for pod in pods:
                status = pod.get("status", {})
                if status.get("phase") != "Running":
                    return False

                for container in status.get("containerStatuses", []):
                    if not container.get("ready", False):
                        return False

            return True

        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False
