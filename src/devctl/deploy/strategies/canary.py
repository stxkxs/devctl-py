"""Canary deployment strategy executor."""

import time
from datetime import datetime
from typing import Any

from devctl.core.exceptions import DeploymentError
from devctl.core.logging import get_logger
from devctl.deploy.models import Deployment, DeploymentMetrics
from devctl.deploy.strategies.base import DeploymentExecutor

logger = get_logger(__name__)


class CanaryDeploymentExecutor(DeploymentExecutor):
    """Canary deployment executor with gradual traffic shifting."""

    @property
    def strategy_name(self) -> str:
        return "canary"

    def _initialize(self, deployment: Deployment, dry_run: bool) -> None:
        """Initialize canary deployment."""
        deployment.add_event("init", "Initializing canary deployment")

        if dry_run:
            deployment.add_event("dry_run", "Would create canary deployment")
            return

        # Get current deployment for rollback
        try:
            current = self._k8s.get_deployment(
                name=deployment.name,
                namespace=deployment.namespace,
            )
            deployment.previous_image = self._get_current_image(current)
            deployment.add_event("init_complete", f"Baseline: {deployment.previous_image}")
        except Exception:
            raise DeploymentError("Baseline deployment not found for canary")

    def _deploy(self, deployment: Deployment, dry_run: bool) -> None:
        """Deploy canary version."""
        canary_name = f"{deployment.name}-canary"
        deployment.add_event("deploying", f"Creating canary: {deployment.image}")
        deployment.progress = 10

        if dry_run:
            deployment.add_event("dry_run", "Would create canary deployment")
            deployment.progress = 30
            return

        # Calculate canary replicas
        initial_weight = deployment.strategy_config.get("initial_weight", 10)
        canary_replicas = max(1, int(deployment.replicas * initial_weight / 100))

        # Create canary deployment
        self._create_canary_deployment(deployment, canary_replicas)
        deployment.progress = 20
        deployment.add_event("created", f"Created canary with {canary_replicas} replicas")

        # Wait for canary to be ready
        timeout = deployment.strategy_config.get("timeout", 300)
        if not self._wait_for_rollout_named(canary_name, deployment.namespace, timeout):
            raise Exception("Canary deployment rollout timed out")

        deployment.progress = 30
        deployment.canary_weight = initial_weight
        deployment.add_event("ready", f"Canary ready with {initial_weight}% traffic")

        # Configure traffic splitting
        self._set_traffic_split(deployment, initial_weight, dry_run)

    def _verify(self, deployment: Deployment, dry_run: bool) -> bool:
        """Verify canary health and metrics."""
        if dry_run:
            deployment.add_event("dry_run", "Would verify canary health")
            return True

        deployment.add_event("verifying", "Verifying canary deployment")

        # Get verification configuration
        steps = deployment.strategy_config.get("steps", [
            {"weight": 10, "pause": 60},
            {"weight": 30, "pause": 60},
            {"weight": 50, "pause": 60},
        ])

        error_threshold = deployment.strategy_config.get("error_rate_threshold", 0.05)
        latency_threshold = deployment.strategy_config.get("latency_threshold", 500)

        for i, step in enumerate(steps):
            weight = step.get("weight", 10)
            pause = step.get("pause", 60)

            deployment.add_event("step", f"Canary step {i+1}: {weight}% traffic")

            # Update traffic weight
            self._set_traffic_split(deployment, weight, False)
            deployment.canary_weight = weight
            deployment.progress = 30 + int((i + 1) / len(steps) * 40)

            # Wait and observe
            time.sleep(pause)

            # Check metrics
            metrics = self._get_metrics(deployment)
            deployment.add_metrics(metrics)

            # Validate metrics
            if metrics.error_rate > error_threshold:
                deployment.add_event(
                    "metrics_fail",
                    f"Error rate {metrics.error_rate:.2%} exceeds threshold {error_threshold:.2%}",
                )
                return False

            if metrics.latency_p95 > latency_threshold:
                deployment.add_event(
                    "metrics_fail",
                    f"P95 latency {metrics.latency_p95}ms exceeds threshold {latency_threshold}ms",
                )
                return False

            deployment.add_event(
                "metrics_ok",
                f"Metrics healthy: error_rate={metrics.error_rate:.2%}, p95={metrics.latency_p95}ms",
            )

        deployment.add_event("verified", "Canary verification passed")
        return True

    def _promote(self, deployment: Deployment, dry_run: bool) -> None:
        """Promote canary to 100% traffic."""
        deployment.add_event("promoting", "Promoting canary to 100%")

        if dry_run:
            deployment.add_event("dry_run", "Would promote canary")
            return

        # Update main deployment to canary image
        self._k8s.update_deployment_image(
            name=deployment.name,
            namespace=deployment.namespace,
            image=deployment.image,
        )

        # Wait for main deployment rollout
        timeout = deployment.strategy_config.get("timeout", 300)
        if not self._wait_for_rollout(deployment, timeout, False):
            raise Exception("Main deployment rollout timed out")

        # Route all traffic to main
        self._set_traffic_split(deployment, 0, dry_run)
        deployment.canary_weight = 0

        deployment.add_event("promoted", "Canary promoted to production")

    def _rollback(self, deployment: Deployment, dry_run: bool) -> None:
        """Rollback canary deployment."""
        deployment.add_event("rollback", "Rolling back canary")

        if dry_run:
            deployment.add_event("dry_run", "Would delete canary")
            return

        # Route all traffic to stable
        self._set_traffic_split(deployment, 0, dry_run)
        deployment.canary_weight = 0

        # Delete canary deployment
        canary_name = f"{deployment.name}-canary"
        try:
            self._k8s.delete_deployment(
                name=canary_name,
                namespace=deployment.namespace,
            )
            deployment.add_event("deleted", "Canary deployment deleted")
        except Exception as e:
            logger.warning(f"Failed to delete canary: {e}")

        deployment.add_event("rolled_back", "Traffic restored to stable")

    def _cleanup(self, deployment: Deployment, dry_run: bool) -> None:
        """Delete canary deployment after promotion."""
        canary_name = f"{deployment.name}-canary"
        deployment.add_event("cleanup", "Deleting canary deployment")

        if dry_run:
            deployment.add_event("dry_run", f"Would delete {canary_name}")
            return

        try:
            self._k8s.delete_deployment(
                name=canary_name,
                namespace=deployment.namespace,
            )
            deployment.add_event("cleanup_complete", "Canary deployment deleted")
        except Exception as e:
            logger.warning(f"Failed to delete canary: {e}")

    def _create_canary_deployment(self, deployment: Deployment, replicas: int) -> None:
        """Create canary deployment from stable."""
        canary_name = f"{deployment.name}-canary"

        # Clone stable deployment
        stable = self._k8s.get_deployment(
            name=deployment.name,
            namespace=deployment.namespace,
        )

        # Modify for canary
        canary_spec = stable.copy()
        canary_spec["metadata"]["name"] = canary_name
        canary_spec["metadata"]["labels"]["canary"] = "true"
        canary_spec["spec"]["replicas"] = replicas
        canary_spec["spec"]["selector"]["matchLabels"]["canary"] = "true"
        canary_spec["spec"]["template"]["metadata"]["labels"]["canary"] = "true"
        canary_spec["spec"]["template"]["spec"]["containers"][0]["image"] = deployment.image

        # Remove resourceVersion for create
        if "resourceVersion" in canary_spec.get("metadata", {}):
            del canary_spec["metadata"]["resourceVersion"]

        try:
            # Try to create
            self._k8s.create_deployment(
                namespace=deployment.namespace,
                body=canary_spec,
            )
        except Exception:
            # Update if exists
            self._k8s.update_deployment_image(
                name=canary_name,
                namespace=deployment.namespace,
                image=deployment.image,
            )
            self._k8s.scale_deployment(
                name=canary_name,
                namespace=deployment.namespace,
                replicas=replicas,
            )

    def _set_traffic_split(self, deployment: Deployment, canary_weight: int, dry_run: bool) -> None:
        """Configure traffic split between stable and canary.

        This is a simplified implementation. In production, you would use:
        - Istio VirtualService
        - Linkerd TrafficSplit
        - AWS App Mesh
        - nginx ingress annotations
        """
        if dry_run:
            return

        # Check for Istio
        if deployment.strategy_config.get("service_mesh") == "istio":
            self._set_istio_traffic_split(deployment, canary_weight)
        else:
            # Use replica-based traffic split (approximate)
            self._set_replica_based_split(deployment, canary_weight)

    def _set_replica_based_split(self, deployment: Deployment, canary_weight: int) -> None:
        """Approximate traffic split using replica counts."""
        stable_weight = 100 - canary_weight
        total_replicas = deployment.replicas

        if canary_weight == 0:
            canary_replicas = 0
            stable_replicas = total_replicas
        elif canary_weight == 100:
            canary_replicas = total_replicas
            stable_replicas = 0
        else:
            canary_replicas = max(1, int(total_replicas * canary_weight / 100))
            stable_replicas = max(1, total_replicas - canary_replicas)

        # Scale deployments
        canary_name = f"{deployment.name}-canary"

        self._k8s.scale_deployment(
            name=deployment.name,
            namespace=deployment.namespace,
            replicas=stable_replicas,
        )

        if canary_weight > 0:
            self._k8s.scale_deployment(
                name=canary_name,
                namespace=deployment.namespace,
                replicas=canary_replicas,
            )

    def _set_istio_traffic_split(self, deployment: Deployment, canary_weight: int) -> None:
        """Set traffic split using Istio VirtualService."""
        # This would use the Kubernetes API to update an Istio VirtualService
        # Simplified example - in production use proper Istio client
        stable_weight = 100 - canary_weight

        virtual_service = {
            "apiVersion": "networking.istio.io/v1beta1",
            "kind": "VirtualService",
            "metadata": {
                "name": deployment.name,
                "namespace": deployment.namespace,
            },
            "spec": {
                "hosts": [deployment.name],
                "http": [
                    {
                        "route": [
                            {
                                "destination": {
                                    "host": deployment.name,
                                    "subset": "stable",
                                },
                                "weight": stable_weight,
                            },
                            {
                                "destination": {
                                    "host": deployment.name,
                                    "subset": "canary",
                                },
                                "weight": canary_weight,
                            },
                        ]
                    }
                ],
            },
        }

        # Apply VirtualService
        # self._k8s.apply_custom_resource(virtual_service)
        logger.info(f"Would apply Istio VirtualService with canary={canary_weight}%")

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
        """Get deployment metrics for canary analysis."""
        metrics = DeploymentMetrics(timestamp=datetime.utcnow())

        # In production, you would query:
        # - Prometheus for latency/error metrics
        # - Grafana datasources
        # - Cloud monitoring (CloudWatch, etc.)

        try:
            # Get pod metrics as proxy
            canary_name = f"{deployment.name}-canary"
            pod_metrics = self._k8s.get_pod_metrics(
                namespace=deployment.namespace,
                label_selector=f"app={deployment.name},canary=true",
            )

            if pod_metrics:
                # Basic resource metrics
                for pm in pod_metrics:
                    for container in pm.get("containers", []):
                        usage = container.get("usage", {})
                        metrics.cpu_usage = self._parse_cpu(usage.get("cpu", "0"))
                        metrics.memory_usage = self._parse_memory(usage.get("memory", "0"))

            # TODO: Query actual error rates and latencies from observability stack

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
