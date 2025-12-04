"""Rolling deployment strategy executor."""

import time
from datetime import datetime
from typing import Any

from devctl.core.logging import get_logger
from devctl.deploy.models import Deployment, DeploymentMetrics
from devctl.deploy.strategies.base import DeploymentExecutor

logger = get_logger(__name__)


class RollingDeploymentExecutor(DeploymentExecutor):
    """Rolling update deployment executor."""

    @property
    def strategy_name(self) -> str:
        return "rolling"

    def _initialize(self, deployment: Deployment, dry_run: bool) -> None:
        """Initialize rolling deployment."""
        deployment.add_event("init", "Initializing rolling deployment")

        if dry_run:
            deployment.add_event("dry_run", "Would verify deployment exists")
            return

        # Verify the deployment exists
        try:
            current = self._k8s.get_deployment(
                name=deployment.name,
                namespace=deployment.namespace,
            )
            deployment.previous_image = self._get_current_image(current)
            deployment.add_event(
                "init_complete",
                f"Current image: {deployment.previous_image}",
            )
        except Exception:
            # New deployment
            deployment.add_event("init_new", "Creating new deployment")

    def _deploy(self, deployment: Deployment, dry_run: bool) -> None:
        """Execute rolling deployment."""
        deployment.add_event("deploying", f"Updating to image: {deployment.image}")
        deployment.progress = 10

        if dry_run:
            deployment.add_event("dry_run", "Would update deployment image")
            deployment.progress = 50
            return

        # Update the deployment image
        self._k8s.update_deployment_image(
            name=deployment.name,
            namespace=deployment.namespace,
            image=deployment.image,
            container=deployment.strategy_config.get("container"),
        )

        deployment.progress = 30
        deployment.add_event("image_updated", "Deployment image updated")

        # Wait for rollout
        max_surge = deployment.strategy_config.get("max_surge", "25%")
        max_unavailable = deployment.strategy_config.get("max_unavailable", "25%")
        timeout = deployment.strategy_config.get("timeout", 300)

        deployment.add_event(
            "waiting",
            f"Waiting for rollout (max_surge={max_surge}, max_unavailable={max_unavailable})",
        )

        # Poll rollout status
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self._k8s.get_rollout_status(
                name=deployment.name,
                namespace=deployment.namespace,
            )

            # Update progress based on replicas
            ready = status.get("ready_replicas", 0)
            desired = status.get("replicas", deployment.replicas)
            if desired > 0:
                deployment.progress = 30 + int((ready / desired) * 60)

            if status.get("ready", False):
                deployment.add_event("rollout_complete", "Rollout completed")
                return

            time.sleep(5)

        raise Exception(f"Rollout timed out after {timeout}s")

    def _verify(self, deployment: Deployment, dry_run: bool) -> bool:
        """Verify rolling deployment health."""
        if dry_run:
            deployment.add_event("dry_run", "Would verify health checks")
            return True

        if not deployment.health_check.enabled:
            deployment.add_event("skip_health", "Health check disabled")
            return True

        deployment.add_event("verifying", "Verifying deployment health")

        # Wait for health checks
        success_count = 0
        check_count = 0
        max_checks = deployment.health_check.success_threshold + deployment.health_check.failure_threshold

        time.sleep(deployment.health_check.initial_delay)

        while check_count < max_checks:
            healthy = self._check_health(deployment)

            if healthy:
                success_count += 1
                if success_count >= deployment.health_check.success_threshold:
                    deployment.add_event("healthy", "Health checks passed")
                    return True
            else:
                success_count = 0

            check_count += 1
            time.sleep(deployment.health_check.interval)

        deployment.add_event("unhealthy", "Health checks failed")
        return False

    def _promote(self, deployment: Deployment, dry_run: bool) -> None:
        """No-op for rolling deployment (already at 100%)."""
        deployment.add_event("promote", "Rolling deployment already at 100%")

    def _rollback(self, deployment: Deployment, dry_run: bool) -> None:
        """Rollback rolling deployment."""
        if not deployment.previous_image:
            deployment.add_event("rollback_skip", "No previous image to rollback to")
            return

        deployment.add_event("rollback", f"Rolling back to: {deployment.previous_image}")

        if dry_run:
            deployment.add_event("dry_run", "Would rollback deployment")
            return

        # Use K8s rollback
        self._k8s.rollback_deployment(
            name=deployment.name,
            namespace=deployment.namespace,
        )

        deployment.add_event("rolled_back", "Rollback initiated")

    def _cleanup(self, deployment: Deployment, dry_run: bool) -> None:
        """No cleanup needed for rolling deployment."""
        pass

    def _check_health(self, deployment: Deployment) -> bool:
        """Check deployment health via pods."""
        try:
            pods = self._k8s.list_pods(
                namespace=deployment.namespace,
                label_selector=f"app={deployment.name}",
            )

            for pod in pods:
                status = pod.get("status", {})
                phase = status.get("phase", "")

                if phase != "Running":
                    return False

                # Check container readiness
                for container in status.get("containerStatuses", []):
                    if not container.get("ready", False):
                        return False

            return len(pods) > 0

        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def _get_current_image(self, deployment_spec: dict[str, Any]) -> str | None:
        """Extract current image from deployment spec."""
        try:
            containers = deployment_spec.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            if containers:
                return containers[0].get("image")
        except Exception:
            pass
        return None

    def _get_metrics(self, deployment: Deployment) -> DeploymentMetrics:
        """Get deployment metrics from K8s."""
        metrics = DeploymentMetrics(timestamp=datetime.utcnow())

        try:
            # Get pod metrics
            pod_metrics = self._k8s.get_pod_metrics(
                namespace=deployment.namespace,
                label_selector=f"app={deployment.name}",
            )

            if pod_metrics:
                # Aggregate metrics
                total_cpu = 0.0
                total_memory = 0.0

                for pm in pod_metrics:
                    for container in pm.get("containers", []):
                        usage = container.get("usage", {})
                        total_cpu += self._parse_cpu(usage.get("cpu", "0"))
                        total_memory += self._parse_memory(usage.get("memory", "0"))

                metrics.cpu_usage = total_cpu
                metrics.memory_usage = total_memory

        except Exception as e:
            logger.debug(f"Failed to get metrics: {e}")

        return metrics

    def _parse_cpu(self, cpu_str: str) -> float:
        """Parse CPU string to cores."""
        if cpu_str.endswith("n"):
            return float(cpu_str[:-1]) / 1e9
        elif cpu_str.endswith("u"):
            return float(cpu_str[:-1]) / 1e6
        elif cpu_str.endswith("m"):
            return float(cpu_str[:-1]) / 1000
        else:
            return float(cpu_str)

    def _parse_memory(self, mem_str: str) -> float:
        """Parse memory string to bytes."""
        units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3}
        for suffix, multiplier in units.items():
            if mem_str.endswith(suffix):
                return float(mem_str[: -len(suffix)]) * multiplier
        return float(mem_str)
