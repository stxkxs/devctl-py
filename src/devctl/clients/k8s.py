"""Kubernetes client using the official kubernetes Python client."""

from datetime import datetime, timezone
from typing import Any, Generator

from devctl.config import K8sConfig
from devctl.core.exceptions import K8sError, AuthenticationError
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class K8sClient:
    """Client for Kubernetes API operations."""

    def __init__(self, config: K8sConfig):
        self._config = config
        self._api_client: Any = None
        self._core_v1: Any = None
        self._apps_v1: Any = None
        self._custom_objects: Any = None
        self._loaded = False

    def _load_config(self) -> None:
        """Load kubernetes configuration."""
        if self._loaded:
            return

        try:
            from kubernetes import client, config

            kubeconfig = self._config.get_kubeconfig()
            context = self._config.get_context()

            try:
                if kubeconfig:
                    config.load_kube_config(config_file=kubeconfig, context=context)
                else:
                    # Try in-cluster config first, then default kubeconfig
                    try:
                        config.load_incluster_config()
                    except config.ConfigException:
                        config.load_kube_config(context=context)

                self._loaded = True
                logger.debug("Loaded k8s config", context=context)
            except Exception as e:
                raise AuthenticationError(f"Failed to load k8s config: {e}")
        except ImportError:
            raise K8sError(
                "kubernetes package not installed. Run: pip install kubernetes"
            )

    @property
    def core_v1(self) -> Any:
        """Get CoreV1Api client (pods, services, nodes, events)."""
        if self._core_v1 is None:
            self._load_config()
            from kubernetes import client

            self._core_v1 = client.CoreV1Api()
        return self._core_v1

    @property
    def apps_v1(self) -> Any:
        """Get AppsV1Api client (deployments, replicasets, daemonsets)."""
        if self._apps_v1 is None:
            self._load_config()
            from kubernetes import client

            self._apps_v1 = client.AppsV1Api()
        return self._apps_v1

    @property
    def custom_objects(self) -> Any:
        """Get CustomObjectsApi client (for metrics)."""
        if self._custom_objects is None:
            self._load_config()
            from kubernetes import client

            self._custom_objects = client.CustomObjectsApi()
        return self._custom_objects

    @property
    def namespace(self) -> str:
        """Get default namespace."""
        return self._config.get_namespace()

    # Pod operations
    def list_pods(
        self,
        namespace: str | None = None,
        label_selector: str | None = None,
        field_selector: str | None = None,
        all_namespaces: bool = False,
    ) -> list[dict[str, Any]]:
        """List pods in a namespace."""
        from kubernetes.client.rest import ApiException

        kwargs: dict[str, Any] = {}
        if label_selector:
            kwargs["label_selector"] = label_selector
        if field_selector:
            kwargs["field_selector"] = field_selector

        try:
            if all_namespaces:
                pods = self.core_v1.list_pod_for_all_namespaces(**kwargs)
            else:
                ns = namespace or self.namespace
                pods = self.core_v1.list_namespaced_pod(ns, **kwargs)
            return [self._pod_to_dict(pod) for pod in pods.items]
        except ApiException as e:
            raise K8sError(f"Failed to list pods: {e.reason}", status_code=e.status)

    def get_pod(self, name: str, namespace: str | None = None) -> dict[str, Any]:
        """Get pod details."""
        from kubernetes.client.rest import ApiException

        ns = namespace or self.namespace
        try:
            pod = self.core_v1.read_namespaced_pod(name, ns)
            return self._pod_to_dict(pod, detailed=True)
        except ApiException as e:
            raise K8sError(f"Failed to get pod: {e.reason}", status_code=e.status)

    def get_pod_logs(
        self,
        name: str,
        namespace: str | None = None,
        container: str | None = None,
        tail_lines: int | None = None,
        since_seconds: int | None = None,
        follow: bool = False,
        previous: bool = False,
    ) -> str | Generator[str, None, None]:
        """Get pod logs."""
        from kubernetes.client.rest import ApiException

        ns = namespace or self.namespace
        kwargs: dict[str, Any] = {}
        if container:
            kwargs["container"] = container
        if tail_lines:
            kwargs["tail_lines"] = tail_lines
        if since_seconds:
            kwargs["since_seconds"] = since_seconds
        if previous:
            kwargs["previous"] = previous

        try:
            if follow:
                kwargs["follow"] = True
                kwargs["_preload_content"] = False
                response = self.core_v1.read_namespaced_pod_log(name, ns, **kwargs)
                return self._stream_logs(response)
            else:
                return self.core_v1.read_namespaced_pod_log(name, ns, **kwargs)
        except ApiException as e:
            raise K8sError(f"Failed to get pod logs: {e.reason}", status_code=e.status)

    def _stream_logs(self, response: Any) -> Generator[str, None, None]:
        """Stream log lines from response."""
        for line in response:
            yield line.decode("utf-8").rstrip()

    def exec_pod(
        self,
        name: str,
        command: list[str],
        namespace: str | None = None,
        container: str | None = None,
        stdin: bool = False,
        tty: bool = False,
    ) -> str:
        """Execute command in a pod."""
        from kubernetes.client.rest import ApiException
        from kubernetes.stream import stream

        ns = namespace or self.namespace
        kwargs: dict[str, Any] = {
            "command": command,
            "stderr": True,
            "stdout": True,
            "stdin": stdin,
            "tty": tty,
        }
        if container:
            kwargs["container"] = container

        try:
            result = stream(
                self.core_v1.connect_get_namespaced_pod_exec, name, ns, **kwargs
            )
            return result
        except ApiException as e:
            raise K8sError(f"Failed to exec in pod: {e.reason}", status_code=e.status)

    def delete_pod(
        self,
        name: str,
        namespace: str | None = None,
        grace_period: int | None = None,
    ) -> None:
        """Delete a pod."""
        from kubernetes import client
        from kubernetes.client.rest import ApiException

        ns = namespace or self.namespace
        body = client.V1DeleteOptions()
        if grace_period is not None:
            body.grace_period_seconds = grace_period

        try:
            self.core_v1.delete_namespaced_pod(name, ns, body=body)
        except ApiException as e:
            raise K8sError(f"Failed to delete pod: {e.reason}", status_code=e.status)

    # Deployment operations
    def list_deployments(
        self,
        namespace: str | None = None,
        label_selector: str | None = None,
        all_namespaces: bool = False,
    ) -> list[dict[str, Any]]:
        """List deployments."""
        from kubernetes.client.rest import ApiException

        kwargs: dict[str, Any] = {}
        if label_selector:
            kwargs["label_selector"] = label_selector

        try:
            if all_namespaces:
                deployments = self.apps_v1.list_deployment_for_all_namespaces(**kwargs)
            else:
                ns = namespace or self.namespace
                deployments = self.apps_v1.list_namespaced_deployment(ns, **kwargs)
            return [self._deployment_to_dict(d) for d in deployments.items]
        except ApiException as e:
            raise K8sError(
                f"Failed to list deployments: {e.reason}", status_code=e.status
            )

    def get_deployment(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        """Get deployment details."""
        from kubernetes.client.rest import ApiException

        ns = namespace or self.namespace
        try:
            deployment = self.apps_v1.read_namespaced_deployment(name, ns)
            return self._deployment_to_dict(deployment, detailed=True)
        except ApiException as e:
            raise K8sError(
                f"Failed to get deployment: {e.reason}", status_code=e.status
            )

    def scale_deployment(
        self,
        name: str,
        replicas: int,
        namespace: str | None = None,
    ) -> None:
        """Scale a deployment."""
        from kubernetes.client.rest import ApiException

        ns = namespace or self.namespace
        body = {"spec": {"replicas": replicas}}

        try:
            self.apps_v1.patch_namespaced_deployment_scale(name, ns, body)
        except ApiException as e:
            raise K8sError(
                f"Failed to scale deployment: {e.reason}", status_code=e.status
            )

    def restart_deployment(self, name: str, namespace: str | None = None) -> None:
        """Restart a deployment (rolling restart)."""
        from kubernetes.client.rest import ApiException

        ns = namespace or self.namespace
        now = datetime.now(timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {"kubectl.kubernetes.io/restartedAt": now}
                    }
                }
            }
        }

        try:
            self.apps_v1.patch_namespaced_deployment(name, ns, body)
        except ApiException as e:
            raise K8sError(
                f"Failed to restart deployment: {e.reason}", status_code=e.status
            )

    # Rollout operations
    def get_rollout_status(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        """Get deployment rollout status."""
        deployment = self.get_deployment(name, namespace)
        conditions = deployment.get("conditions", [])

        progressing = next(
            (c for c in conditions if c["type"] == "Progressing"), None
        )
        available = next((c for c in conditions if c["type"] == "Available"), None)

        return {
            "name": deployment["name"],
            "replicas": deployment["replicas"],
            "ready": deployment["ready_replicas"],
            "updated": deployment["updated_replicas"],
            "available": deployment["available_replicas"],
            "progressing": (
                progressing.get("status") == "True" if progressing else False
            ),
            "progressing_reason": progressing.get("reason") if progressing else None,
            "available_status": (
                available.get("status") == "True" if available else False
            ),
        }

    def get_rollout_history(
        self,
        name: str,
        namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get deployment revision history."""
        from kubernetes.client.rest import ApiException

        ns = namespace or self.namespace
        try:
            rs_list = self.apps_v1.list_namespaced_replica_set(
                ns, label_selector=f"app={name}"
            )

            history = []
            for rs in rs_list.items:
                annotations = rs.metadata.annotations or {}
                revision = annotations.get("deployment.kubernetes.io/revision", "?")
                containers = (
                    rs.spec.template.spec.containers
                    if rs.spec.template.spec.containers
                    else []
                )
                image = containers[0].image if containers else "-"

                history.append(
                    {
                        "revision": revision,
                        "name": rs.metadata.name,
                        "replicas": rs.spec.replicas or 0,
                        "created": rs.metadata.creation_timestamp.strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                        "image": image,
                    }
                )

            return sorted(
                history,
                key=lambda x: int(x["revision"]) if x["revision"].isdigit() else 0,
                reverse=True,
            )
        except ApiException as e:
            raise K8sError(
                f"Failed to get rollout history: {e.reason}", status_code=e.status
            )

    # Node operations
    def list_nodes(self, label_selector: str | None = None) -> list[dict[str, Any]]:
        """List cluster nodes."""
        from kubernetes.client.rest import ApiException

        kwargs: dict[str, Any] = {}
        if label_selector:
            kwargs["label_selector"] = label_selector

        try:
            nodes = self.core_v1.list_node(**kwargs)
            return [self._node_to_dict(n) for n in nodes.items]
        except ApiException as e:
            raise K8sError(f"Failed to list nodes: {e.reason}", status_code=e.status)

    # Events
    def list_events(
        self,
        namespace: str | None = None,
        field_selector: str | None = None,
        limit: int = 50,
        all_namespaces: bool = False,
    ) -> list[dict[str, Any]]:
        """List cluster events."""
        from kubernetes.client.rest import ApiException

        kwargs: dict[str, Any] = {"limit": limit}
        if field_selector:
            kwargs["field_selector"] = field_selector

        try:
            if all_namespaces or namespace is None:
                events = self.core_v1.list_event_for_all_namespaces(**kwargs)
            else:
                events = self.core_v1.list_namespaced_event(namespace, **kwargs)
            return [self._event_to_dict(e) for e in events.items]
        except ApiException as e:
            raise K8sError(f"Failed to list events: {e.reason}", status_code=e.status)

    def watch_events(
        self,
        namespace: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Watch cluster events in real-time."""
        from kubernetes import watch
        from kubernetes.client.rest import ApiException

        w = watch.Watch()
        try:
            if namespace:
                stream_func = w.stream(
                    self.core_v1.list_namespaced_event, namespace
                )
            else:
                stream_func = w.stream(self.core_v1.list_event_for_all_namespaces)

            for event in stream_func:
                yield {
                    "type": event["type"],
                    **self._event_to_dict(event["object"]),
                }
        except ApiException as e:
            raise K8sError(f"Failed to watch events: {e.reason}", status_code=e.status)

    # Resource metrics (requires metrics-server)
    def get_pod_metrics(
        self, namespace: str | None = None
    ) -> list[dict[str, Any]]:
        """Get pod resource usage metrics."""
        from kubernetes.client.rest import ApiException

        ns = namespace or self.namespace
        try:
            metrics = self.custom_objects.list_namespaced_custom_object(
                "metrics.k8s.io", "v1beta1", ns, "pods"
            )
            return [self._pod_metrics_to_dict(m) for m in metrics.get("items", [])]
        except ApiException as e:
            if e.status == 404:
                raise K8sError(
                    "Metrics server not available. Install metrics-server."
                )
            raise K8sError(f"Failed to get metrics: {e.reason}", status_code=e.status)

    def get_node_metrics(self) -> list[dict[str, Any]]:
        """Get node resource usage metrics."""
        from kubernetes.client.rest import ApiException

        try:
            metrics = self.custom_objects.list_cluster_custom_object(
                "metrics.k8s.io", "v1beta1", "nodes"
            )
            return [self._node_metrics_to_dict(m) for m in metrics.get("items", [])]
        except ApiException as e:
            if e.status == 404:
                raise K8sError(
                    "Metrics server not available. Install metrics-server."
                )
            raise K8sError(f"Failed to get metrics: {e.reason}", status_code=e.status)

    # Helper methods to convert k8s objects to dicts
    def _pod_to_dict(self, pod: Any, detailed: bool = False) -> dict[str, Any]:
        """Convert Pod object to dictionary."""
        status = pod.status
        phase = status.phase

        container_statuses = status.container_statuses or []
        ready_containers = sum(1 for cs in container_statuses if cs.ready)
        total_containers = len(container_statuses)
        restarts = sum(cs.restart_count for cs in container_statuses)

        result = {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status": phase,
            "ready": f"{ready_containers}/{total_containers}",
            "restarts": restarts,
            "age": self._format_age(pod.metadata.creation_timestamp),
            "node": pod.spec.node_name or "-",
            "ip": status.pod_ip or "-",
        }

        if detailed:
            result["labels"] = pod.metadata.labels or {}
            result["containers"] = [
                {
                    "name": c.name,
                    "image": c.image,
                    "ports": [p.container_port for p in (c.ports or [])],
                }
                for c in pod.spec.containers
            ]
            result["conditions"] = [
                {"type": c.type, "status": c.status, "reason": c.reason}
                for c in (status.conditions or [])
            ]

        return result

    def _deployment_to_dict(
        self, deployment: Any, detailed: bool = False
    ) -> dict[str, Any]:
        """Convert Deployment object to dictionary."""
        status = deployment.status
        spec = deployment.spec

        result = {
            "name": deployment.metadata.name,
            "namespace": deployment.metadata.namespace,
            "replicas": spec.replicas or 0,
            "ready_replicas": status.ready_replicas or 0,
            "updated_replicas": status.updated_replicas or 0,
            "available_replicas": status.available_replicas or 0,
            "age": self._format_age(deployment.metadata.creation_timestamp),
        }

        if detailed:
            result["labels"] = deployment.metadata.labels or {}
            result["selector"] = (
                spec.selector.match_labels if spec.selector else {}
            )
            result["strategy"] = spec.strategy.type if spec.strategy else "RollingUpdate"
            result["conditions"] = [
                {
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                }
                for c in (status.conditions or [])
            ]
            if spec.template.spec.containers:
                result["image"] = spec.template.spec.containers[0].image

        return result

    def _node_to_dict(self, node: Any) -> dict[str, Any]:
        """Convert Node object to dictionary."""
        status = node.status
        conditions = {c.type: c.status for c in status.conditions}

        allocatable = status.allocatable or {}
        capacity = status.capacity or {}

        labels = node.metadata.labels or {}
        roles = [
            k.replace("node-role.kubernetes.io/", "")
            for k in labels
            if k.startswith("node-role.kubernetes.io/")
        ]

        return {
            "name": node.metadata.name,
            "status": "Ready" if conditions.get("Ready") == "True" else "NotReady",
            "roles": ",".join(roles) if roles else "worker",
            "version": status.node_info.kubelet_version if status.node_info else "-",
            "cpu_capacity": capacity.get("cpu", "-"),
            "memory_capacity": capacity.get("memory", "-"),
            "pods_capacity": capacity.get("pods", "-"),
            "age": self._format_age(node.metadata.creation_timestamp),
        }

    def _event_to_dict(self, event: Any) -> dict[str, Any]:
        """Convert Event object to dictionary."""
        involved = event.involved_object
        return {
            "namespace": event.metadata.namespace,
            "name": involved.name if involved else "-",
            "kind": involved.kind if involved else "-",
            "type": event.type,
            "reason": event.reason,
            "message": (event.message[:80] if event.message else "-"),
            "count": event.count or 1,
            "first_seen": self._format_age(event.first_timestamp),
            "last_seen": self._format_age(event.last_timestamp),
        }

    def _pod_metrics_to_dict(self, metrics: dict) -> dict[str, Any]:
        """Convert pod metrics to dictionary."""
        containers = metrics.get("containers", [])
        total_cpu = sum(
            self._parse_cpu(c.get("usage", {}).get("cpu", "0")) for c in containers
        )
        total_memory = sum(
            self._parse_memory(c.get("usage", {}).get("memory", "0"))
            for c in containers
        )

        return {
            "name": metrics["metadata"]["name"],
            "namespace": metrics["metadata"]["namespace"],
            "cpu": f"{total_cpu}m",
            "memory": f"{total_memory}Mi",
        }

    def _node_metrics_to_dict(self, metrics: dict) -> dict[str, Any]:
        """Convert node metrics to dictionary."""
        usage = metrics.get("usage", {})
        return {
            "name": metrics["metadata"]["name"],
            "cpu": usage.get("cpu", "-"),
            "memory": usage.get("memory", "-"),
        }

    def _format_age(self, timestamp: Any) -> str:
        """Format timestamp to age string."""
        if not timestamp:
            return "-"
        now = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        delta = now - timestamp

        if delta.days > 0:
            return f"{delta.days}d"
        elif delta.seconds >= 3600:
            return f"{delta.seconds // 3600}h"
        elif delta.seconds >= 60:
            return f"{delta.seconds // 60}m"
        else:
            return f"{delta.seconds}s"

    def _parse_cpu(self, cpu_str: str) -> int:
        """Parse CPU string to millicores."""
        if cpu_str.endswith("n"):
            return int(cpu_str[:-1]) // 1000000
        elif cpu_str.endswith("m"):
            return int(cpu_str[:-1])
        else:
            return int(float(cpu_str) * 1000)

    def _parse_memory(self, mem_str: str) -> int:
        """Parse memory string to MiB."""
        units = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "Ti": 1024 * 1024}
        for suffix, multiplier in units.items():
            if mem_str.endswith(suffix):
                return int(float(mem_str[: -len(suffix)]) * multiplier)
        return int(mem_str) // (1024 * 1024)

    def close(self) -> None:
        """Close the client."""
        pass

    def __enter__(self) -> "K8sClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
