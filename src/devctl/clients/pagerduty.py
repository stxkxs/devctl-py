"""PagerDuty API client using httpx."""

from datetime import datetime
from typing import Any

import httpx

from devctl.config import PagerDutyConfig
from devctl.core.exceptions import PagerDutyError, AuthenticationError
from devctl.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.pagerduty.com"


class PagerDutyClient:
    """Client for PagerDuty REST API v2."""

    def __init__(self, config: PagerDutyConfig):
        self._config = config
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            api_key = self._config.get_api_key()

            if not api_key:
                raise AuthenticationError("PagerDuty API key not configured")

            headers = {
                "Authorization": f"Token token={api_key}",
                "Content-Type": "application/json",
                "Accept": "application/vnd.pagerduty+json;version=2",
            }

            self._client = httpx.Client(
                base_url=BASE_URL,
                headers=headers,
                timeout=self._config.timeout,
            )

            logger.debug("Created PagerDuty client")

        return self._client

    def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Make an API request."""
        try:
            req_headers = dict(self.client.headers)
            if headers:
                req_headers.update(headers)

            response = self.client.request(method, path, headers=req_headers, **kwargs)
            response.raise_for_status()

            if response.content:
                return response.json()
            return None

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            try:
                error_data = e.response.json()
                error = error_data.get("error", {})
                message = error.get("message", str(e))
                errors = error.get("errors", [])
                if errors:
                    message = f"{message}: {', '.join(errors)}"
            except Exception:
                message = e.response.text or str(e)

            raise PagerDutyError(message, status_code=status_code)

        except httpx.RequestError as e:
            raise PagerDutyError(f"Request failed: {e}")

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

    def __enter__(self) -> "PagerDutyClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # Incident operations
    def list_incidents(
        self,
        statuses: list[str] | None = None,
        urgencies: list[str] | None = None,
        service_ids: list[str] | None = None,
        user_ids: list[str] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """List incidents with optional filters."""
        params: dict[str, Any] = {"limit": limit}

        if statuses:
            params["statuses[]"] = statuses
        if urgencies:
            params["urgencies[]"] = urgencies
        if service_ids:
            params["service_ids[]"] = service_ids
        if user_ids:
            params["user_ids[]"] = user_ids
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()

        result = self.get("/incidents", params=params)
        return result.get("incidents", [])

    def get_incident(self, incident_id: str) -> dict[str, Any]:
        """Get incident details."""
        result = self.get(f"/incidents/{incident_id}")
        return result.get("incident", {})

    def create_incident(
        self,
        title: str,
        service_id: str,
        urgency: str = "high",
        body: str | None = None,
        escalation_policy_id: str | None = None,
        incident_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a new incident."""
        email = self._config.get_email()
        if not email:
            raise PagerDutyError(
                "Email required for creating incidents. Set PAGERDUTY_EMAIL."
            )

        incident_data: dict[str, Any] = {
            "type": "incident",
            "title": title,
            "service": {"id": service_id, "type": "service_reference"},
            "urgency": urgency,
        }

        if body:
            incident_data["body"] = {"type": "incident_body", "details": body}
        if escalation_policy_id:
            incident_data["escalation_policy"] = {
                "id": escalation_policy_id,
                "type": "escalation_policy_reference",
            }
        if incident_key:
            incident_data["incident_key"] = incident_key

        headers = {"From": email}
        result = self.post(
            "/incidents", headers=headers, json={"incident": incident_data}
        )
        return result.get("incident", {})

    def update_incident(
        self,
        incident_id: str,
        status: str | None = None,
        resolution: str | None = None,
        title: str | None = None,
        escalation_level: int | None = None,
        assignee_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an incident."""
        email = self._config.get_email()
        if not email:
            raise PagerDutyError(
                "Email required for updating incidents. Set PAGERDUTY_EMAIL."
            )

        incident_data: dict[str, Any] = {
            "id": incident_id,
            "type": "incident",
        }

        if status:
            incident_data["status"] = status
        if resolution:
            incident_data["resolution"] = resolution
        if title:
            incident_data["title"] = title
        if escalation_level is not None:
            incident_data["escalation_level"] = escalation_level
        if assignee_ids:
            incident_data["assignments"] = [
                {"assignee": {"id": uid, "type": "user_reference"}} for uid in assignee_ids
            ]

        headers = {"From": email}
        result = self.put(
            f"/incidents/{incident_id}",
            headers=headers,
            json={"incident": incident_data},
        )
        return result.get("incident", {})

    def acknowledge_incident(self, incident_id: str) -> dict[str, Any]:
        """Acknowledge an incident."""
        return self.update_incident(incident_id, status="acknowledged")

    def resolve_incident(
        self, incident_id: str, resolution: str | None = None
    ) -> dict[str, Any]:
        """Resolve an incident."""
        return self.update_incident(incident_id, status="resolved", resolution=resolution)

    def escalate_incident(
        self, incident_id: str, escalation_level: int = 2
    ) -> dict[str, Any]:
        """Escalate an incident."""
        return self.update_incident(incident_id, escalation_level=escalation_level)

    def add_note(self, incident_id: str, content: str) -> dict[str, Any]:
        """Add a note to an incident."""
        email = self._config.get_email()
        if not email:
            raise PagerDutyError("Email required. Set PAGERDUTY_EMAIL.")

        headers = {"From": email}
        result = self.post(
            f"/incidents/{incident_id}/notes",
            headers=headers,
            json={"note": {"content": content}},
        )
        return result.get("note", {})

    # On-call operations
    def get_oncalls(
        self,
        schedule_ids: list[str] | None = None,
        user_ids: list[str] | None = None,
        escalation_policy_ids: list[str] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get current on-call users."""
        params: dict[str, Any] = {}

        if schedule_ids:
            params["schedule_ids[]"] = schedule_ids
        if user_ids:
            params["user_ids[]"] = user_ids
        if escalation_policy_ids:
            params["escalation_policy_ids[]"] = escalation_policy_ids
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()

        result = self.get("/oncalls", params=params)
        return result.get("oncalls", [])

    # Schedule operations
    def list_schedules(self, query: str | None = None) -> list[dict[str, Any]]:
        """List schedules."""
        params: dict[str, Any] = {}
        if query:
            params["query"] = query

        result = self.get("/schedules", params=params)
        return result.get("schedules", [])

    def get_schedule(
        self,
        schedule_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        """Get schedule details with on-call entries."""
        params: dict[str, Any] = {}
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()

        result = self.get(f"/schedules/{schedule_id}", params=params)
        return result.get("schedule", {})

    # Service operations
    def list_services(
        self,
        query: str | None = None,
        team_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List services."""
        params: dict[str, Any] = {}
        if query:
            params["query"] = query
        if team_ids:
            params["team_ids[]"] = team_ids

        result = self.get("/services", params=params)
        return result.get("services", [])

    def get_service(self, service_id: str) -> dict[str, Any]:
        """Get service details."""
        result = self.get(f"/services/{service_id}")
        return result.get("service", {})

    # User operations
    def get_current_user(self) -> dict[str, Any]:
        """Get current user info."""
        result = self.get("/users/me")
        return result.get("user", {})

    def list_users(self, query: str | None = None) -> list[dict[str, Any]]:
        """List users."""
        params: dict[str, Any] = {}
        if query:
            params["query"] = query

        result = self.get("/users", params=params)
        return result.get("users", [])

    # Escalation policy operations
    def list_escalation_policies(
        self, query: str | None = None
    ) -> list[dict[str, Any]]:
        """List escalation policies."""
        params: dict[str, Any] = {}
        if query:
            params["query"] = query

        result = self.get("/escalation_policies", params=params)
        return result.get("escalation_policies", [])

    def get_escalation_policy(self, policy_id: str) -> dict[str, Any]:
        """Get escalation policy details."""
        result = self.get(f"/escalation_policies/{policy_id}")
        return result.get("escalation_policy", {})
