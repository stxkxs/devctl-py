"""Confluence Cloud REST API client using httpx."""

import base64
from typing import Any

import httpx

from devctl.config import ConfluenceConfig
from devctl.core.exceptions import ConfluenceError, AuthenticationError
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class ConfluenceClient:
    """Client for Confluence Cloud REST API v2."""

    def __init__(self, config: ConfluenceConfig):
        self._config = config
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            url = self._config.get_url()
            email = self._config.get_email()
            api_token = self._config.get_api_token()

            if not url:
                raise ConfluenceError("Confluence URL not configured")
            if not email or not api_token:
                raise AuthenticationError(
                    "Confluence email and API token not configured"
                )

            # Basic auth with email:api_token
            auth_str = f"{email}:{api_token}"
            auth_bytes = base64.b64encode(auth_str.encode()).decode()

            headers = {
                "Authorization": f"Basic {auth_bytes}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            # Ensure URL ends with /wiki for Confluence Cloud
            base_url = url.rstrip("/")
            if not base_url.endswith("/wiki"):
                base_url = f"{base_url}/wiki"

            self._client = httpx.Client(
                base_url=base_url,
                headers=headers,
                timeout=self._config.timeout,
            )

            logger.debug("Created Confluence client", url=url)

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
                # Handle Confluence error format
                if "data" in error_data and "errors" in error_data["data"]:
                    errors = error_data["data"]["errors"]
                    if errors:
                        message = "; ".join(
                            err.get("message", {}).get("translation", str(err))
                            for err in errors
                        )
            except Exception:
                message = e.response.text or str(e)

            raise ConfluenceError(message, status_code=status_code)

        except httpx.RequestError as e:
            raise ConfluenceError(f"Request failed: {e}")

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

    def __enter__(self) -> "ConfluenceClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # Space operations
    def list_spaces(
        self,
        limit: int = 25,
        start: int = 0,
        space_type: str | None = None,
    ) -> dict[str, Any]:
        """List spaces."""
        params: dict[str, Any] = {"limit": limit, "start": start}
        if space_type:
            params["type"] = space_type

        return self.get("/rest/api/space", params=params)

    def get_space(self, space_key: str) -> dict[str, Any]:
        """Get space by key."""
        return self.get(f"/rest/api/space/{space_key}")

    # Page operations (using v1 API for broader compatibility)
    def list_pages(
        self,
        space_key: str | None = None,
        title: str | None = None,
        limit: int = 25,
        start: int = 0,
        expand: str = "version,body.storage",
    ) -> dict[str, Any]:
        """List pages in a space."""
        params: dict[str, Any] = {
            "limit": limit,
            "start": start,
            "expand": expand,
            "type": "page",
        }
        if space_key:
            params["spaceKey"] = space_key
        if title:
            params["title"] = title

        return self.get("/rest/api/content", params=params)

    def get_page(
        self,
        page_id: str,
        expand: str = "version,body.storage,space,ancestors",
    ) -> dict[str, Any]:
        """Get page by ID."""
        return self.get(f"/rest/api/content/{page_id}", params={"expand": expand})

    def get_page_by_title(
        self,
        space_key: str,
        title: str,
        expand: str = "version,body.storage",
    ) -> dict[str, Any] | None:
        """Get page by title in a space."""
        result = self.list_pages(space_key=space_key, title=title, limit=1, expand=expand)
        pages = result.get("results", [])
        return pages[0] if pages else None

    def create_page(
        self,
        space_key: str,
        title: str,
        body: str,
        parent_id: str | None = None,
        body_format: str = "storage",
    ) -> dict[str, Any]:
        """Create a new page.

        Args:
            space_key: Space key to create page in
            title: Page title
            body: Page content
            parent_id: Optional parent page ID
            body_format: Content format ('storage' for XHTML, 'wiki' for wiki markup)
        """
        payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {
                body_format: {"value": body, "representation": body_format}
            },
        }

        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]

        return self.post("/rest/api/content", json=payload)

    def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        version_number: int,
        body_format: str = "storage",
    ) -> dict[str, Any]:
        """Update an existing page.

        Args:
            page_id: Page ID to update
            title: New page title
            body: New page content
            version_number: Current version number (will be incremented)
            body_format: Content format
        """
        payload = {
            "type": "page",
            "title": title,
            "body": {
                body_format: {"value": body, "representation": body_format}
            },
            "version": {"number": version_number + 1},
        }

        return self.put(f"/rest/api/content/{page_id}", json=payload)

    def delete_page(self, page_id: str) -> None:
        """Delete a page."""
        self.delete(f"/rest/api/content/{page_id}")

    def get_page_children(
        self,
        page_id: str,
        limit: int = 25,
        start: int = 0,
        expand: str = "version",
    ) -> dict[str, Any]:
        """Get child pages."""
        return self.get(
            f"/rest/api/content/{page_id}/child/page",
            params={"limit": limit, "start": start, "expand": expand},
        )

    def get_page_ancestors(self, page_id: str) -> list[dict[str, Any]]:
        """Get page ancestors (parent hierarchy)."""
        page = self.get_page(page_id, expand="ancestors")
        return page.get("ancestors", [])

    # Content operations
    def get_page_history(
        self,
        page_id: str,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Get page version history."""
        return self.get(
            f"/rest/api/content/{page_id}/history",
            params={"expand": "previousVersion,nextVersion"},
        )

    def get_page_version(
        self,
        page_id: str,
        version_number: int,
        expand: str = "body.storage",
    ) -> dict[str, Any]:
        """Get specific page version."""
        return self.get(
            f"/rest/api/content/{page_id}/version/{version_number}",
            params={"expand": expand},
        )

    # Search
    def search(
        self,
        cql: str,
        limit: int = 25,
        start: int = 0,
        expand: str = "content.version",
    ) -> dict[str, Any]:
        """Search using CQL (Confluence Query Language).

        Args:
            cql: CQL query string (e.g., 'text ~ "kubernetes" AND space = "DEV"')
            limit: Max results
            start: Offset for pagination
            expand: Fields to expand
        """
        return self.get(
            "/rest/api/content/search",
            params={"cql": cql, "limit": limit, "start": start, "expand": expand},
        )

    def search_content(
        self,
        query: str,
        space_key: str | None = None,
        content_type: str = "page",
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Search for content with a simple query.

        Args:
            query: Search text
            space_key: Optional space to limit search
            content_type: Content type (page, blogpost, etc.)
            limit: Max results
        """
        cql_parts = [f'text ~ "{query}"', f'type = "{content_type}"']
        if space_key:
            cql_parts.append(f'space = "{space_key}"')

        cql = " AND ".join(cql_parts)
        result = self.search(cql, limit=limit)
        return result.get("results", [])

    # Labels
    def get_page_labels(self, page_id: str) -> list[dict[str, Any]]:
        """Get labels for a page."""
        result = self.get(f"/rest/api/content/{page_id}/label")
        return result.get("results", [])

    def add_page_label(self, page_id: str, label: str) -> dict[str, Any]:
        """Add a label to a page."""
        return self.post(
            f"/rest/api/content/{page_id}/label",
            json=[{"prefix": "global", "name": label}],
        )

    def remove_page_label(self, page_id: str, label: str) -> None:
        """Remove a label from a page."""
        self.delete(f"/rest/api/content/{page_id}/label/{label}")

    # Comments
    def get_page_comments(
        self,
        page_id: str,
        limit: int = 25,
        start: int = 0,
        expand: str = "body.view",
    ) -> dict[str, Any]:
        """Get comments on a page."""
        return self.get(
            f"/rest/api/content/{page_id}/child/comment",
            params={"limit": limit, "start": start, "expand": expand},
        )

    def add_page_comment(
        self,
        page_id: str,
        body: str,
        body_format: str = "storage",
    ) -> dict[str, Any]:
        """Add a comment to a page."""
        payload = {
            "type": "comment",
            "container": {"id": page_id, "type": "page"},
            "body": {
                body_format: {"value": body, "representation": body_format}
            },
        }
        return self.post("/rest/api/content", json=payload)

    # Attachments
    def get_page_attachments(
        self,
        page_id: str,
        limit: int = 25,
        start: int = 0,
    ) -> dict[str, Any]:
        """Get attachments on a page."""
        return self.get(
            f"/rest/api/content/{page_id}/child/attachment",
            params={"limit": limit, "start": start},
        )

    # User operations
    def get_current_user(self) -> dict[str, Any]:
        """Get current user info."""
        return self.get("/rest/api/user/current")

    # Convenience methods for runbooks and incidents
    def publish_runbook(
        self,
        space_key: str,
        title: str,
        content: str,
        parent_id: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Publish a runbook page.

        Args:
            space_key: Space to publish to
            title: Runbook title
            content: Runbook content (HTML/storage format)
            parent_id: Optional parent page for organization
            labels: Optional labels to add
        """
        # Check if page exists
        existing = self.get_page_by_title(space_key, title)

        if existing:
            # Update existing page
            page = self.update_page(
                page_id=existing["id"],
                title=title,
                body=content,
                version_number=existing["version"]["number"],
            )
        else:
            # Create new page
            page = self.create_page(
                space_key=space_key,
                title=title,
                body=content,
                parent_id=parent_id,
            )

        # Add labels
        if labels:
            for label in labels:
                try:
                    self.add_page_label(page["id"], label)
                except ConfluenceError:
                    # Ignore label errors (may already exist)
                    pass

        return page

    def create_incident_page(
        self,
        space_key: str,
        title: str,
        severity: str = "P3",
        summary: str = "",
        timeline: list[dict[str, str]] | None = None,
        affected_services: list[str] | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an incident documentation page.

        Args:
            space_key: Space to create page in
            title: Incident title
            severity: Severity level (P1-P5)
            summary: Incident summary
            timeline: List of timeline entries [{time, event}]
            affected_services: List of affected service names
            parent_id: Optional parent page ID
        """
        # Build incident page content
        content = self._build_incident_page_content(
            title=title,
            severity=severity,
            summary=summary,
            timeline=timeline or [],
            affected_services=affected_services or [],
        )

        page = self.create_page(
            space_key=space_key,
            title=title,
            body=content,
            parent_id=parent_id,
        )

        # Add incident label
        try:
            self.add_page_label(page["id"], "incident")
            self.add_page_label(page["id"], f"severity-{severity.lower()}")
        except ConfluenceError:
            pass

        return page

    def _build_incident_page_content(
        self,
        title: str,
        severity: str,
        summary: str,
        timeline: list[dict[str, str]],
        affected_services: list[str],
    ) -> str:
        """Build incident page content in Confluence storage format."""
        severity_color = {
            "P1": "#ff0000",
            "P2": "#ff6600",
            "P3": "#ffcc00",
            "P4": "#0066ff",
            "P5": "#00cc00",
        }.get(severity.upper(), "#666666")

        services_list = "".join(f"<li>{svc}</li>" for svc in affected_services)
        timeline_rows = "".join(
            f"<tr><td>{entry.get('time', 'N/A')}</td><td>{entry.get('event', '')}</td></tr>"
            for entry in timeline
        )

        content = f"""
<ac:structured-macro ac:name="info">
  <ac:rich-text-body>
    <p><strong>Severity:</strong> <span style="color: {severity_color};">{severity}</span></p>
    <p><strong>Status:</strong> Investigating</p>
  </ac:rich-text-body>
</ac:structured-macro>

<h2>Summary</h2>
<p>{summary or 'To be added...'}</p>

<h2>Affected Services</h2>
<ul>
{services_list or '<li>To be determined</li>'}
</ul>

<h2>Timeline</h2>
<table>
  <thead>
    <tr>
      <th>Time</th>
      <th>Event</th>
    </tr>
  </thead>
  <tbody>
{timeline_rows or '<tr><td colspan="2">No entries yet</td></tr>'}
  </tbody>
</table>

<h2>Root Cause</h2>
<p>Under investigation...</p>

<h2>Resolution</h2>
<p>Pending...</p>

<h2>Action Items</h2>
<ac:task-list>
  <ac:task>
    <ac:task-id>1</ac:task-id>
    <ac:task-status>incomplete</ac:task-status>
    <ac:task-body>Determine root cause</ac:task-body>
  </ac:task>
  <ac:task>
    <ac:task-id>2</ac:task-id>
    <ac:task-status>incomplete</ac:task-status>
    <ac:task-body>Document lessons learned</ac:task-body>
  </ac:task>
</ac:task-list>
"""
        return content.strip()
