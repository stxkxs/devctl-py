"""ArgoCD API client using httpx."""

from typing import Any

import httpx

from devctl.config import ArgoCDConfig
from devctl.core.exceptions import ArgoCDError, AuthenticationError
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class ArgoCDClient:
    """Client for ArgoCD REST API."""

    def __init__(self, config: ArgoCDConfig):
        self._config = config
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            url = self._config.get_url()
            token = self._config.get_token()

            if not url:
                raise ArgoCDError("ArgoCD URL not configured")
            if not token:
                raise AuthenticationError("ArgoCD token not configured")

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            self._client = httpx.Client(
                base_url=url.rstrip("/"),
                headers=headers,
                timeout=self._config.timeout,
                verify=not self._config.insecure,
            )

            logger.debug("Created ArgoCD client", url=url)

        return self._client

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an API request."""
        try:
            response = self.client.request(method, path, **kwargs)
            response.raise_for_status()

            if response.content:
                return response.json()
            return None

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            try:
                error_data = e.response.json()
                message = error_data.get("message", str(e))
            except Exception:
                message = e.response.text or str(e)
            raise ArgoCDError(message, status_code=status_code)

        except httpx.RequestError as e:
            raise ArgoCDError(f"Request failed: {e}")

    def get(self, path: str, **kwargs: Any) -> Any:
        """Make a GET request."""
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        """Make a POST request."""
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        """Make a PUT request."""
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        """Make a DELETE request."""
        return self._request("DELETE", path, **kwargs)

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "ArgoCDClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # Application operations
    def list_applications(
        self,
        project: str | None = None,
        selector: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all applications."""
        params: dict[str, Any] = {}
        if project:
            params["projects"] = project
        if selector:
            params["selector"] = selector
        response = self.get("/api/v1/applications", params=params)
        return response.get("items", [])

    def get_application(self, name: str) -> dict[str, Any]:
        """Get application by name."""
        return self.get(f"/api/v1/applications/{name}")

    def get_application_manifests(
        self, name: str, revision: str = "HEAD"
    ) -> dict[str, Any]:
        """Get application manifests."""
        return self.get(
            f"/api/v1/applications/{name}/manifests", params={"revision": revision}
        )

    def sync_application(
        self,
        name: str,
        revision: str | None = None,
        prune: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Trigger sync for an application."""
        payload: dict[str, Any] = {
            "prune": prune,
            "dryRun": dry_run,
        }
        if revision:
            payload["revision"] = revision
        return self.post(f"/api/v1/applications/{name}/sync", json=payload)

    def get_application_resource_tree(self, name: str) -> dict[str, Any]:
        """Get application resource tree."""
        return self.get(f"/api/v1/applications/{name}/resource-tree")

    def rollback_application(self, name: str, revision_id: int) -> dict[str, Any]:
        """Rollback application to a previous deployment."""
        return self.post(f"/api/v1/applications/{name}/rollback", json={"id": revision_id})

    def refresh_application(self, name: str, hard: bool = False) -> dict[str, Any]:
        """Refresh application from Git."""
        refresh_type = "hard" if hard else "normal"
        return self.get(f"/api/v1/applications/{name}", params={"refresh": refresh_type})

    def get_application_history(self, name: str) -> list[dict[str, Any]]:
        """Get deployment history."""
        app = self.get_application(name)
        return app.get("status", {}).get("history", [])

    def delete_application(self, name: str, cascade: bool = True) -> None:
        """Delete an application."""
        params = {"cascade": str(cascade).lower()}
        self.delete(f"/api/v1/applications/{name}", params=params)

    def get_application_diff(self, name: str) -> dict[str, Any]:
        """Get diff between live state and desired state."""
        manifests = self.get_application_manifests(name)
        resource_tree = self.get_application_resource_tree(name)

        return {
            "targetRevision": manifests.get("revision", ""),
            "manifests": manifests.get("manifests", []),
            "resources": resource_tree.get("nodes", []),
        }

    # Project operations
    def list_projects(self) -> list[dict[str, Any]]:
        """List all projects."""
        response = self.get("/api/v1/projects")
        return response.get("items", [])

    def get_project(self, name: str) -> dict[str, Any]:
        """Get project by name."""
        return self.get(f"/api/v1/projects/{name}")

    # Repository operations
    def list_repositories(self) -> list[dict[str, Any]]:
        """List all repositories."""
        response = self.get("/api/v1/repositories")
        return response.get("items", [])

    def get_repository(self, repo_url: str) -> dict[str, Any]:
        """Get repository by URL."""
        import urllib.parse

        encoded = urllib.parse.quote(repo_url, safe="")
        return self.get(f"/api/v1/repositories/{encoded}")

    # Cluster operations
    def list_clusters(self) -> list[dict[str, Any]]:
        """List all clusters."""
        response = self.get("/api/v1/clusters")
        return response.get("items", [])

    def get_cluster(self, server: str) -> dict[str, Any]:
        """Get cluster by server URL."""
        import urllib.parse

        encoded = urllib.parse.quote(server, safe="")
        return self.get(f"/api/v1/clusters/{encoded}")

    # Settings
    def get_settings(self) -> dict[str, Any]:
        """Get ArgoCD settings."""
        return self.get("/api/v1/settings")

    def get_version(self) -> dict[str, Any]:
        """Get ArgoCD version info."""
        return self.get("/api/version")
