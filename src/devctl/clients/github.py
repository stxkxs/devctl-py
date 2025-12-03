"""GitHub API client using httpx."""

from typing import Any

import httpx

from devctl.config import GitHubConfig
from devctl.core.exceptions import GitHubError, AuthenticationError
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class GitHubClient:
    """Client for GitHub REST API."""

    def __init__(self, config: GitHubConfig):
        self._config = config
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            token = self._config.get_token()

            if not token:
                raise AuthenticationError("GitHub token not configured")

            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            self._client = httpx.Client(
                base_url=self._config.base_url.rstrip("/"),
                headers=headers,
                timeout=self._config.timeout,
                follow_redirects=True,
            )

            logger.debug("Created GitHub client", base_url=self._config.base_url)

        return self._client

    @property
    def org(self) -> str | None:
        """Get configured organization."""
        return self._config.get_org()

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
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

            raise GitHubError(message, status_code=status_code)

        except httpx.RequestError as e:
            raise GitHubError(f"Request failed: {e}")

    def _paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        per_page: int = 100,
    ) -> list[Any]:
        """Paginate through API results."""
        params = params or {}
        params["per_page"] = per_page
        page = 1
        results = []

        while True:
            params["page"] = page
            response = self.get(path, params=params)

            if not response:
                break

            if isinstance(response, list):
                results.extend(response)
                if len(response) < per_page:
                    break
            else:
                results.append(response)
                break

            page += 1

        return results

    def get(self, path: str, **kwargs: Any) -> Any:
        """Make a GET request."""
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        """Make a POST request."""
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        """Make a PUT request."""
        return self._request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        """Make a PATCH request."""
        return self._request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        """Make a DELETE request."""
        return self._request("DELETE", path, **kwargs)

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # User operations
    def get_user(self) -> dict[str, Any]:
        """Get authenticated user."""
        return self.get("/user")

    # Repository operations
    def list_repos(
        self,
        org: str | None = None,
        visibility: str | None = None,
        archived: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List repositories."""
        target_org = org or self.org

        if target_org:
            path = f"/orgs/{target_org}/repos"
        else:
            path = "/user/repos"

        params: dict[str, Any] = {}
        if visibility:
            params["visibility"] = visibility
        if archived is not None:
            params["archived"] = str(archived).lower()

        return self._paginate(path, params)

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Get repository details."""
        return self.get(f"/repos/{owner}/{repo}")

    def create_repo(
        self,
        name: str,
        private: bool = True,
        description: str | None = None,
        org: str | None = None,
    ) -> dict[str, Any]:
        """Create a repository."""
        target_org = org or self.org

        payload: dict[str, Any] = {
            "name": name,
            "private": private,
        }
        if description:
            payload["description"] = description

        if target_org:
            return self.post(f"/orgs/{target_org}/repos", json=payload)
        return self.post("/user/repos", json=payload)

    # Actions operations
    def list_workflows(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """List repository workflows."""
        response = self.get(f"/repos/{owner}/{repo}/actions/workflows")
        return response.get("workflows", [])

    def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        workflow_id: int | str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List workflow runs."""
        if workflow_id:
            path = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
        else:
            path = f"/repos/{owner}/{repo}/actions/runs"

        params: dict[str, Any] = {}
        if status:
            params["status"] = status

        response = self.get(path, params=params)
        return response.get("workflow_runs", [])

    def trigger_workflow(
        self,
        owner: str,
        repo: str,
        workflow_id: int | str,
        ref: str = "main",
        inputs: dict[str, Any] | None = None,
    ) -> None:
        """Trigger a workflow dispatch event."""
        payload: dict[str, Any] = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs

        self.post(
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            json=payload,
        )

    def get_workflow_run(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> dict[str, Any]:
        """Get workflow run details."""
        return self.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}")

    def cancel_workflow_run(self, owner: str, repo: str, run_id: int) -> None:
        """Cancel a workflow run."""
        self.post(f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel")

    def get_workflow_run_logs(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> bytes:
        """Download workflow run logs."""
        response = self.client.get(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/logs",
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.content

    # Issues operations
    def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List repository issues."""
        params: dict[str, Any] = {"state": state}
        if labels:
            params["labels"] = ",".join(labels)

        return self._paginate(f"/repos/{owner}/{repo}/issues", params)

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an issue."""
        payload: dict[str, Any] = {"title": title}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels

        return self.post(f"/repos/{owner}/{repo}/issues", json=payload)

    # Pull request operations
    def list_pulls(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        base: str | None = None,
    ) -> list[dict[str, Any]]:
        """List pull requests."""
        params: dict[str, Any] = {"state": state}
        if base:
            params["base"] = base

        return self._paginate(f"/repos/{owner}/{repo}/pulls", params)

    def create_pull(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a pull request."""
        payload: dict[str, Any] = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft,
        }
        if body:
            payload["body"] = body

        return self.post(f"/repos/{owner}/{repo}/pulls", json=payload)

    def merge_pull(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        merge_method: str = "merge",
    ) -> dict[str, Any]:
        """Merge a pull request."""
        payload: dict[str, Any] = {"merge_method": merge_method}
        return self.put(f"/repos/{owner}/{repo}/pulls/{pull_number}/merge", json=payload)

    # Release operations
    def list_releases(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """List releases."""
        return self._paginate(f"/repos/{owner}/{repo}/releases")

    def get_release(self, owner: str, repo: str, tag: str) -> dict[str, Any]:
        """Get release by tag."""
        return self.get(f"/repos/{owner}/{repo}/releases/tags/{tag}")

    def create_release(
        self,
        owner: str,
        repo: str,
        tag_name: str,
        name: str | None = None,
        body: str | None = None,
        draft: bool = False,
        prerelease: bool = False,
    ) -> dict[str, Any]:
        """Create a release."""
        payload: dict[str, Any] = {
            "tag_name": tag_name,
            "draft": draft,
            "prerelease": prerelease,
        }
        if name:
            payload["name"] = name
        if body:
            payload["body"] = body

        return self.post(f"/repos/{owner}/{repo}/releases", json=payload)

    def get_release_assets(
        self,
        owner: str,
        repo: str,
        release_id: int,
    ) -> list[dict[str, Any]]:
        """Get release assets."""
        return self.get(f"/repos/{owner}/{repo}/releases/{release_id}/assets")
