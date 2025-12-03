"""Jira Cloud API client using httpx."""

import base64
from typing import Any

import httpx

from devctl.config import JiraConfig
from devctl.core.exceptions import JiraError, AuthenticationError
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class JiraClient:
    """Client for Jira Cloud REST API."""

    def __init__(self, config: JiraConfig):
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
                raise JiraError("Jira URL not configured")
            if not email:
                raise AuthenticationError("Jira email not configured")
            if not api_token:
                raise AuthenticationError("Jira API token not configured")

            # Jira Cloud uses Basic Auth with email:api_token
            credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()

            headers = {
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            self._client = httpx.Client(
                base_url=url.rstrip("/"),
                headers=headers,
                timeout=self._config.timeout,
            )

            logger.debug("Created Jira client", url=url)

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
                messages = error_data.get("errorMessages", [])
                errors = error_data.get("errors", {})
                message = "; ".join(messages) if messages else str(errors) or str(e)
            except Exception:
                message = e.response.text or str(e)

            raise JiraError(message, status_code=status_code)

        except httpx.RequestError as e:
            raise JiraError(f"Request failed: {e}")

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

    def __enter__(self) -> "JiraClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # Issue operations
    def get_issue(self, issue_key: str, fields: list[str] | None = None) -> dict[str, Any]:
        """Get issue by key."""
        params: dict[str, Any] = {}
        if fields:
            params["fields"] = ",".join(fields)
        return self.get(f"/rest/api/3/issue/{issue_key}", params=params)

    def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search issues using JQL."""
        payload: dict[str, Any] = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
        }
        if fields:
            payload["fields"] = fields
        return self.post("/rest/api/3/search", json=payload)

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: str | None = None,
        assignee: str | None = None,
        labels: list[str] | None = None,
        priority: str | None = None,
        parent_key: str | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new issue."""
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        if description:
            # Atlassian Document Format (ADF) for description
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }

        if assignee:
            fields["assignee"] = {"accountId": assignee}

        if labels:
            fields["labels"] = labels

        if priority:
            fields["priority"] = {"name": priority}

        if parent_key:
            fields["parent"] = {"key": parent_key}

        if custom_fields:
            fields.update(custom_fields)

        return self.post("/rest/api/3/issue", json={"fields": fields})

    def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any] | None = None,
        update: dict[str, Any] | None = None,
    ) -> None:
        """Update an issue."""
        payload: dict[str, Any] = {}
        if fields:
            payload["fields"] = fields
        if update:
            payload["update"] = update
        self.put(f"/rest/api/3/issue/{issue_key}", json=payload)

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        """Transition an issue to a new status."""
        payload = {"transition": {"id": transition_id}}
        self.post(f"/rest/api/3/issue/{issue_key}/transitions", json=payload)

    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """Get available transitions for an issue."""
        result = self.get(f"/rest/api/3/issue/{issue_key}/transitions")
        return result.get("transitions", [])

    def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }
        return self.post(f"/rest/api/3/issue/{issue_key}/comment", json=payload)

    def assign_issue(self, issue_key: str, account_id: str | None) -> None:
        """Assign an issue to a user. Pass None to unassign."""
        payload = {"accountId": account_id}
        self.put(f"/rest/api/3/issue/{issue_key}/assignee", json=payload)

    def add_labels(self, issue_key: str, labels: list[str]) -> None:
        """Add labels to an issue."""
        update = {"labels": [{"add": label} for label in labels]}
        self.update_issue(issue_key, update=update)

    def remove_labels(self, issue_key: str, labels: list[str]) -> None:
        """Remove labels from an issue."""
        update = {"labels": [{"remove": label} for label in labels]}
        self.update_issue(issue_key, update=update)

    def link_issues(
        self,
        inward_issue: str,
        outward_issue: str,
        link_type: str = "Relates",
    ) -> None:
        """Create a link between two issues."""
        payload = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_issue},
            "outwardIssue": {"key": outward_issue},
        }
        self.post("/rest/api/3/issueLink", json=payload)

    # Project operations
    def list_projects(self) -> list[dict[str, Any]]:
        """List all projects."""
        return self.get("/rest/api/3/project")

    def get_project(self, project_key: str) -> dict[str, Any]:
        """Get project by key."""
        return self.get(f"/rest/api/3/project/{project_key}")

    # Board operations (Agile API)
    def list_boards(
        self,
        project_key: str | None = None,
        board_type: str | None = None,
        start_at: int = 0,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """List agile boards."""
        params: dict[str, Any] = {
            "startAt": start_at,
            "maxResults": max_results,
        }
        if project_key:
            params["projectKeyOrId"] = project_key
        if board_type:
            params["type"] = board_type
        return self.get("/rest/agile/1.0/board", params=params)

    def get_board(self, board_id: int) -> dict[str, Any]:
        """Get board by ID."""
        return self.get(f"/rest/agile/1.0/board/{board_id}")

    def get_board_configuration(self, board_id: int) -> dict[str, Any]:
        """Get board configuration."""
        return self.get(f"/rest/agile/1.0/board/{board_id}/configuration")

    # Sprint operations
    def list_sprints(
        self,
        board_id: int,
        state: str | None = None,
        start_at: int = 0,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """List sprints for a board."""
        params: dict[str, Any] = {
            "startAt": start_at,
            "maxResults": max_results,
        }
        if state:
            params["state"] = state  # active, closed, future
        return self.get(f"/rest/agile/1.0/board/{board_id}/sprint", params=params)

    def get_sprint(self, sprint_id: int) -> dict[str, Any]:
        """Get sprint by ID."""
        return self.get(f"/rest/agile/1.0/sprint/{sprint_id}")

    def get_sprint_issues(
        self,
        sprint_id: int,
        start_at: int = 0,
        max_results: int = 50,
        jql: str | None = None,
    ) -> dict[str, Any]:
        """Get issues in a sprint."""
        params: dict[str, Any] = {
            "startAt": start_at,
            "maxResults": max_results,
        }
        if jql:
            params["jql"] = jql
        return self.get(f"/rest/agile/1.0/sprint/{sprint_id}/issue", params=params)

    def move_issues_to_sprint(self, sprint_id: int, issue_keys: list[str]) -> None:
        """Move issues to a sprint."""
        payload = {"issues": issue_keys}
        self.post(f"/rest/agile/1.0/sprint/{sprint_id}/issue", json=payload)

    # Backlog operations
    def get_backlog_issues(
        self,
        board_id: int,
        start_at: int = 0,
        max_results: int = 50,
        jql: str | None = None,
    ) -> dict[str, Any]:
        """Get issues in the backlog."""
        params: dict[str, Any] = {
            "startAt": start_at,
            "maxResults": max_results,
        }
        if jql:
            params["jql"] = jql
        return self.get(f"/rest/agile/1.0/board/{board_id}/backlog", params=params)

    def move_issues_to_backlog(self, issue_keys: list[str]) -> None:
        """Move issues to backlog."""
        payload = {"issues": issue_keys}
        self.post("/rest/agile/1.0/backlog/issue", json=payload)

    # User operations
    def get_myself(self) -> dict[str, Any]:
        """Get current user."""
        return self.get("/rest/api/3/myself")

    def search_users(
        self,
        query: str,
        start_at: int = 0,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Search for users."""
        params = {
            "query": query,
            "startAt": start_at,
            "maxResults": max_results,
        }
        return self.get("/rest/api/3/user/search", params=params)

    def get_assignable_users(
        self,
        project_key: str,
        query: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Get users assignable to issues in a project."""
        params: dict[str, Any] = {
            "project": project_key,
            "maxResults": max_results,
        }
        if query:
            params["query"] = query
        return self.get("/rest/api/3/user/assignable/search", params=params)

    # Status operations
    def list_statuses(self) -> list[dict[str, Any]]:
        """List all statuses."""
        return self.get("/rest/api/3/status")

    def list_statuses_for_project(self, project_key: str) -> list[dict[str, Any]]:
        """List statuses for a project."""
        return self.get(f"/rest/api/3/project/{project_key}/statuses")

    # Priority operations
    def list_priorities(self) -> list[dict[str, Any]]:
        """List all priorities."""
        return self.get("/rest/api/3/priority")

    # Issue type operations
    def list_issue_types(self) -> list[dict[str, Any]]:
        """List all issue types."""
        return self.get("/rest/api/3/issuetype")

    def list_issue_types_for_project(self, project_key: str) -> list[dict[str, Any]]:
        """List issue types for a project."""
        result = self.get_project(project_key)
        return result.get("issueTypes", [])

    # Worklog operations
    def add_worklog(
        self,
        issue_key: str,
        time_spent: str,
        comment: str | None = None,
        started: str | None = None,
    ) -> dict[str, Any]:
        """Add worklog to an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            time_spent: Time spent (e.g., "3h 30m", "1d")
            comment: Optional comment
            started: Optional start time (ISO 8601)
        """
        payload: dict[str, Any] = {"timeSpent": time_spent}
        if comment:
            payload["comment"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment}],
                    }
                ],
            }
        if started:
            payload["started"] = started
        return self.post(f"/rest/api/3/issue/{issue_key}/worklog", json=payload)

    # Server info
    def server_info(self) -> dict[str, Any]:
        """Get server info (for testing connectivity)."""
        return self.get("/rest/api/3/serverInfo")
