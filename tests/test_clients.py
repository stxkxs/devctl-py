"""Tests for new API clients."""

from unittest.mock import MagicMock, patch
import pytest

from devctl.config import (
    PagerDutyConfig,
    ArgoCDConfig,
    SlackConfig,
    ConfluenceConfig,
)


class TestPagerDutyClient:
    """Tests for PagerDuty client."""

    @pytest.fixture
    def pd_config(self):
        return PagerDutyConfig(
            api_key="test-api-key",
            email="test@example.com",
            service_id="PTEST123",
        )

    def test_client_initialization(self, pd_config):
        """Test client can be initialized."""
        from devctl.clients.pagerduty import PagerDutyClient

        client = PagerDutyClient(pd_config)
        assert client._config == pd_config
        assert client._client is None  # Lazy initialization

    @patch("devctl.clients.pagerduty.PagerDutyClient._request")
    def test_list_incidents(self, mock_request, pd_config):
        """Test listing incidents."""
        from devctl.clients.pagerduty import PagerDutyClient

        mock_request.return_value = {
            "incidents": [
                {"id": "INC001", "title": "Test incident", "status": "triggered"}
            ]
        }

        client = PagerDutyClient(pd_config)
        result = client.list_incidents()

        assert len(result) == 1
        assert result[0]["id"] == "INC001"
        mock_request.assert_called_once()

    @patch("devctl.clients.pagerduty.PagerDutyClient._request")
    def test_create_incident(self, mock_request, pd_config):
        """Test creating an incident."""
        from devctl.clients.pagerduty import PagerDutyClient

        mock_request.return_value = {
            "incident": {"id": "INC002", "title": "New incident"}
        }

        client = PagerDutyClient(pd_config)
        result = client.create_incident("New incident", "PTEST123", "high")

        assert result["id"] == "INC002"
        mock_request.assert_called_once()


class TestArgoCDClient:
    """Tests for ArgoCD client."""

    @pytest.fixture
    def argocd_config(self):
        return ArgoCDConfig(
            url="https://argocd.test.com",
            token="test-token",
        )

    def test_client_initialization(self, argocd_config):
        """Test client can be initialized."""
        from devctl.clients.argocd import ArgoCDClient

        client = ArgoCDClient(argocd_config)
        assert client._config == argocd_config
        assert client._client is None  # Lazy initialization

    @patch("devctl.clients.argocd.ArgoCDClient._request")
    def test_list_applications(self, mock_request, argocd_config):
        """Test listing applications."""
        from devctl.clients.argocd import ArgoCDClient

        mock_request.return_value = {
            "items": [
                {"metadata": {"name": "my-app"}, "status": {"sync": {"status": "Synced"}}}
            ]
        }

        client = ArgoCDClient(argocd_config)
        result = client.list_applications()

        # list_applications returns response.get("items", [])
        assert len(result) == 1
        assert result[0]["metadata"]["name"] == "my-app"
        mock_request.assert_called_once()

    @patch("devctl.clients.argocd.ArgoCDClient._request")
    def test_sync_application(self, mock_request, argocd_config):
        """Test syncing an application."""
        from devctl.clients.argocd import ArgoCDClient

        mock_request.return_value = {"metadata": {"name": "my-app"}}

        client = ArgoCDClient(argocd_config)
        result = client.sync_application("my-app")

        assert result["metadata"]["name"] == "my-app"
        mock_request.assert_called_once()


class TestSlackClient:
    """Tests for Slack client."""

    @pytest.fixture
    def slack_config(self):
        return SlackConfig(
            token="xoxb-test-token",
            default_channel="#test",
        )

    def test_client_initialization(self, slack_config):
        """Test client can be initialized."""
        from devctl.clients.slack import SlackClient

        client = SlackClient(slack_config)
        assert client._config == slack_config
        assert client._client is None  # Lazy initialization

    @patch("devctl.clients.slack.SlackClient._request")
    def test_post_message(self, mock_request, slack_config):
        """Test posting a message."""
        from devctl.clients.slack import SlackClient

        mock_request.return_value = {
            "ok": True,
            "message": {
                "ts": "1234567890.123456",
                "text": "Hello, world!",
            },
        }

        client = SlackClient(slack_config)
        result = client.post_message("#test", "Hello, world!")

        # post_message returns result.get("message", {})
        assert "ts" in result
        mock_request.assert_called_once()

    @patch("devctl.clients.slack.SlackClient._request")
    def test_list_channels(self, mock_request, slack_config):
        """Test listing channels."""
        from devctl.clients.slack import SlackClient

        mock_request.return_value = {
            "ok": True,
            "channels": [{"id": "C12345", "name": "test"}],
            "response_metadata": {"next_cursor": ""},
        }

        client = SlackClient(slack_config)
        result = client.list_channels()

        # list_channels returns {"channels": [...], "cursor": ...}
        assert "channels" in result
        assert len(result["channels"]) == 1
        mock_request.assert_called_once()


class TestConfluenceClient:
    """Tests for Confluence client."""

    @pytest.fixture
    def confluence_config(self):
        return ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            email="test@example.com",
            api_token="test-token",
        )

    def test_client_initialization(self, confluence_config):
        """Test client can be initialized."""
        from devctl.clients.confluence import ConfluenceClient

        client = ConfluenceClient(confluence_config)
        assert client._config == confluence_config
        assert client._client is None  # Lazy initialization

    @patch("devctl.clients.confluence.ConfluenceClient._request")
    def test_list_pages(self, mock_request, confluence_config):
        """Test listing pages."""
        from devctl.clients.confluence import ConfluenceClient

        mock_request.return_value = {
            "results": [
                {"id": "123", "title": "Test Page", "status": "current"}
            ]
        }

        client = ConfluenceClient(confluence_config)
        result = client.list_pages("TEST")

        assert "results" in result
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Test Page"
        mock_request.assert_called_once()

    @patch("devctl.clients.confluence.ConfluenceClient._request")
    def test_create_page(self, mock_request, confluence_config):
        """Test creating a page."""
        from devctl.clients.confluence import ConfluenceClient

        mock_request.return_value = {
            "id": "456",
            "title": "New Page",
            "status": "current",
        }

        client = ConfluenceClient(confluence_config)
        result = client.create_page("TEST", "New Page", "<p>Content</p>")

        assert result["id"] == "456"
        assert result["title"] == "New Page"
        mock_request.assert_called_once()
