"""Grafana API client using httpx."""

from typing import Any
from urllib.parse import urljoin

import httpx

from devctl.config import GrafanaConfig
from devctl.core.exceptions import GrafanaError, AuthenticationError
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class GrafanaClient:
    """Client for Grafana HTTP API."""

    def __init__(self, config: GrafanaConfig):
        self._config = config
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            url = self._config.get_url()
            api_key = self._config.get_api_key()

            if not url:
                raise GrafanaError("Grafana URL not configured")
            if not api_key:
                raise AuthenticationError("Grafana API key not configured")

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            self._client = httpx.Client(
                base_url=url.rstrip("/"),
                headers=headers,
                timeout=self._config.timeout,
            )

            logger.debug("Created Grafana client", url=url)

        return self._client

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Make an API request.

        Args:
            method: HTTP method
            path: API path
            **kwargs: Additional request arguments

        Returns:
            Response JSON data
        """
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

            raise GrafanaError(message, status_code=status_code)

        except httpx.RequestError as e:
            raise GrafanaError(f"Request failed: {e}")

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

    def __enter__(self) -> "GrafanaClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # Dashboard operations
    def list_dashboards(self, folder_id: int | None = None) -> list[dict[str, Any]]:
        """List all dashboards."""
        params: dict[str, Any] = {"type": "dash-db"}
        if folder_id is not None:
            params["folderIds"] = folder_id
        return self.get("/api/search", params=params)

    def get_dashboard(self, uid: str) -> dict[str, Any]:
        """Get dashboard by UID."""
        return self.get(f"/api/dashboards/uid/{uid}")

    def create_dashboard(
        self,
        dashboard: dict[str, Any],
        folder_uid: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create or update a dashboard."""
        payload: dict[str, Any] = {
            "dashboard": dashboard,
            "overwrite": overwrite,
        }
        if folder_uid:
            payload["folderUid"] = folder_uid

        return self.post("/api/dashboards/db", json=payload)

    def delete_dashboard(self, uid: str) -> dict[str, Any]:
        """Delete a dashboard by UID."""
        return self.delete(f"/api/dashboards/uid/{uid}")

    # Folder operations
    def list_folders(self) -> list[dict[str, Any]]:
        """List all folders."""
        return self.get("/api/folders")

    def get_folder(self, uid: str) -> dict[str, Any]:
        """Get folder by UID."""
        return self.get(f"/api/folders/{uid}")

    def create_folder(self, title: str, uid: str | None = None) -> dict[str, Any]:
        """Create a folder."""
        payload: dict[str, Any] = {"title": title}
        if uid:
            payload["uid"] = uid
        return self.post("/api/folders", json=payload)

    # Datasource operations
    def list_datasources(self) -> list[dict[str, Any]]:
        """List all datasources."""
        return self.get("/api/datasources")

    def get_datasource(self, uid: str) -> dict[str, Any]:
        """Get datasource by UID."""
        return self.get(f"/api/datasources/uid/{uid}")

    def test_datasource(self, uid: str) -> dict[str, Any]:
        """Test datasource connection."""
        datasource = self.get_datasource(uid)
        return self.post(f"/api/datasources/uid/{uid}/health")

    # Alert operations
    def list_alert_rules(self) -> list[dict[str, Any]]:
        """List all alert rules."""
        return self.get("/api/v1/provisioning/alert-rules")

    def get_alert_rule(self, uid: str) -> dict[str, Any]:
        """Get alert rule by UID."""
        return self.get(f"/api/v1/provisioning/alert-rules/{uid}")

    def list_silences(self) -> list[dict[str, Any]]:
        """List all silences."""
        return self.get("/api/alertmanager/grafana/api/v2/silences")

    def create_silence(
        self,
        matchers: list[dict[str, Any]],
        starts_at: str,
        ends_at: str,
        comment: str,
        created_by: str = "devctl",
    ) -> dict[str, Any]:
        """Create a silence."""
        payload = {
            "matchers": matchers,
            "startsAt": starts_at,
            "endsAt": ends_at,
            "comment": comment,
            "createdBy": created_by,
        }
        return self.post("/api/alertmanager/grafana/api/v2/silences", json=payload)

    # Annotation operations
    def list_annotations(
        self,
        dashboard_uid: str | None = None,
        from_time: int | None = None,
        to_time: int | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List annotations."""
        params: dict[str, Any] = {}
        if dashboard_uid:
            params["dashboardUID"] = dashboard_uid
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        if tags:
            params["tags"] = tags

        return self.get("/api/annotations", params=params)

    def create_annotation(
        self,
        text: str,
        tags: list[str] | None = None,
        dashboard_uid: str | None = None,
        panel_id: int | None = None,
        time: int | None = None,
        time_end: int | None = None,
    ) -> dict[str, Any]:
        """Create an annotation."""
        payload: dict[str, Any] = {"text": text}
        if tags:
            payload["tags"] = tags
        if dashboard_uid:
            payload["dashboardUID"] = dashboard_uid
        if panel_id:
            payload["panelId"] = panel_id
        if time:
            payload["time"] = time
        if time_end:
            payload["timeEnd"] = time_end

        return self.post("/api/annotations", json=payload)

    # Health check
    def health(self) -> dict[str, Any]:
        """Check Grafana health."""
        return self.get("/api/health")
