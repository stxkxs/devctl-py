"""Slack Web API client using httpx."""

from typing import Any

import httpx

from devctl.config import SlackConfig
from devctl.core.exceptions import SlackError, AuthenticationError
from devctl.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://slack.com/api"


class SlackClient:
    """Client for Slack Web API."""

    def __init__(self, config: SlackConfig):
        self._config = config
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            token = self._config.get_token()

            if not token:
                raise AuthenticationError("Slack token not configured")

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }

            self._client = httpx.Client(
                base_url=BASE_URL,
                headers=headers,
                timeout=self._config.timeout,
            )

            logger.debug("Created Slack client")

        return self._client

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> Any:
        """Make an API request."""
        try:
            response = self.client.request(method, endpoint, **kwargs)
            response.raise_for_status()

            data = response.json()

            # Slack API returns ok=false for errors even with 200 status
            if not data.get("ok", False):
                error_code = data.get("error", "unknown_error")
                raise SlackError(
                    f"Slack API error: {error_code}",
                    error_code=error_code,
                )

            return data

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            try:
                error_data = e.response.json()
                message = error_data.get("error", str(e))
            except Exception:
                message = e.response.text or str(e)
            raise SlackError(f"HTTP {status_code}: {message}", error_code=str(status_code))

        except httpx.RequestError as e:
            raise SlackError(f"Request failed: {e}")

    def get(self, endpoint: str, **kwargs: Any) -> Any:
        """Make a GET request."""
        return self._request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> Any:
        """Make a POST request."""
        return self._request("POST", endpoint, **kwargs)

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "SlackClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # Message operations
    def post_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        username: str | None = None,
        icon_emoji: str | None = None,
        unfurl_links: bool = True,
        unfurl_media: bool = True,
    ) -> dict[str, Any]:
        """Post a message to a channel."""
        payload: dict[str, Any] = {
            "channel": channel,
            "text": text,
            "unfurl_links": unfurl_links,
            "unfurl_media": unfurl_media,
        }

        if thread_ts:
            payload["thread_ts"] = thread_ts
        if blocks:
            payload["blocks"] = blocks
        if attachments:
            payload["attachments"] = attachments

        # Use config defaults if not specified
        payload["username"] = username or self._config.username
        payload["icon_emoji"] = icon_emoji or self._config.icon_emoji

        result = self.post("chat.postMessage", json=payload)
        return result.get("message", {})

    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Update an existing message."""
        payload: dict[str, Any] = {
            "channel": channel,
            "ts": ts,
            "text": text,
        }

        if blocks:
            payload["blocks"] = blocks
        if attachments:
            payload["attachments"] = attachments

        result = self.post("chat.update", json=payload)
        return result

    def delete_message(self, channel: str, ts: str) -> bool:
        """Delete a message."""
        self.post("chat.delete", json={"channel": channel, "ts": ts})
        return True

    def get_permalink(self, channel: str, message_ts: str) -> str:
        """Get permalink for a message."""
        result = self.get(
            "chat.getPermalink",
            params={"channel": channel, "message_ts": message_ts},
        )
        return result.get("permalink", "")

    # Thread operations
    def get_thread_replies(
        self,
        channel: str,
        thread_ts: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Get replies in a thread."""
        params: dict[str, Any] = {
            "channel": channel,
            "ts": thread_ts,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor

        result = self.get("conversations.replies", params=params)
        return {
            "messages": result.get("messages", []),
            "has_more": result.get("has_more", False),
            "cursor": result.get("response_metadata", {}).get("next_cursor"),
        }

    def reply_to_thread(
        self,
        channel: str,
        thread_ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        broadcast: bool = False,
    ) -> dict[str, Any]:
        """Reply to a thread."""
        payload: dict[str, Any] = {
            "channel": channel,
            "thread_ts": thread_ts,
            "text": text,
            "reply_broadcast": broadcast,
        }

        if blocks:
            payload["blocks"] = blocks

        result = self.post("chat.postMessage", json=payload)
        return result.get("message", {})

    # Channel operations
    def list_channels(
        self,
        types: str = "public_channel,private_channel",
        exclude_archived: bool = True,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List channels."""
        params: dict[str, Any] = {
            "types": types,
            "exclude_archived": exclude_archived,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor

        result = self.get("conversations.list", params=params)
        return {
            "channels": result.get("channels", []),
            "cursor": result.get("response_metadata", {}).get("next_cursor"),
        }

    def get_channel_info(self, channel: str) -> dict[str, Any]:
        """Get channel info."""
        result = self.get("conversations.info", params={"channel": channel})
        return result.get("channel", {})

    def create_channel(
        self,
        name: str,
        is_private: bool = False,
    ) -> dict[str, Any]:
        """Create a channel."""
        result = self.post(
            "conversations.create",
            json={"name": name, "is_private": is_private},
        )
        return result.get("channel", {})

    def archive_channel(self, channel: str) -> bool:
        """Archive a channel."""
        self.post("conversations.archive", json={"channel": channel})
        return True

    def unarchive_channel(self, channel: str) -> bool:
        """Unarchive a channel."""
        self.post("conversations.unarchive", json={"channel": channel})
        return True

    def join_channel(self, channel: str) -> dict[str, Any]:
        """Join a channel."""
        result = self.post("conversations.join", json={"channel": channel})
        return result.get("channel", {})

    def invite_to_channel(self, channel: str, users: list[str]) -> dict[str, Any]:
        """Invite users to a channel."""
        result = self.post(
            "conversations.invite",
            json={"channel": channel, "users": ",".join(users)},
        )
        return result.get("channel", {})

    def set_channel_topic(self, channel: str, topic: str) -> dict[str, Any]:
        """Set channel topic."""
        result = self.post(
            "conversations.setTopic",
            json={"channel": channel, "topic": topic},
        )
        return result.get("channel", {})

    def set_channel_purpose(self, channel: str, purpose: str) -> dict[str, Any]:
        """Set channel purpose."""
        result = self.post(
            "conversations.setPurpose",
            json={"channel": channel, "purpose": purpose},
        )
        return result.get("channel", {})

    # User operations
    def list_users(
        self,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List users."""
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        result = self.get("users.list", params=params)
        return {
            "members": result.get("members", []),
            "cursor": result.get("response_metadata", {}).get("next_cursor"),
        }

    def get_user_info(self, user: str) -> dict[str, Any]:
        """Get user info."""
        result = self.get("users.info", params={"user": user})
        return result.get("user", {})

    def lookup_user_by_email(self, email: str) -> dict[str, Any]:
        """Look up user by email."""
        result = self.get("users.lookupByEmail", params={"email": email})
        return result.get("user", {})

    def get_user_presence(self, user: str) -> dict[str, Any]:
        """Get user presence status."""
        return self.get("users.getPresence", params={"user": user})

    # Auth/identity
    def auth_test(self) -> dict[str, Any]:
        """Test authentication and get bot info."""
        return self.get("auth.test")

    def get_bot_info(self, bot: str | None = None) -> dict[str, Any]:
        """Get bot info."""
        params = {}
        if bot:
            params["bot"] = bot
        result = self.get("bots.info", params=params)
        return result.get("bot", {})

    # Reactions
    def add_reaction(self, channel: str, timestamp: str, name: str) -> bool:
        """Add a reaction to a message."""
        self.post(
            "reactions.add",
            json={"channel": channel, "timestamp": timestamp, "name": name},
        )
        return True

    def remove_reaction(self, channel: str, timestamp: str, name: str) -> bool:
        """Remove a reaction from a message."""
        self.post(
            "reactions.remove",
            json={"channel": channel, "timestamp": timestamp, "name": name},
        )
        return True

    # Convenience methods for notifications
    def send_notification(
        self,
        notification_type: str,
        channel: str | None = None,
        **data: Any,
    ) -> dict[str, Any]:
        """Send a formatted notification.

        Args:
            notification_type: Type of notification (deployment, incident, build)
            channel: Target channel (uses default if not specified)
            **data: Additional data for the notification

        Returns:
            Posted message data
        """
        target_channel = channel or self._config.default_channel

        if notification_type == "deployment":
            return self._send_deployment_notification(target_channel, **data)
        elif notification_type == "incident":
            return self._send_incident_notification(target_channel, **data)
        elif notification_type == "build":
            return self._send_build_notification(target_channel, **data)
        else:
            # Generic notification
            text = data.get("text", f"Notification: {notification_type}")
            return self.post_message(target_channel, text)

    def _send_deployment_notification(
        self,
        channel: str,
        service: str = "unknown",
        version: str = "unknown",
        environment: str = "unknown",
        status: str = "started",
        url: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a deployment notification."""
        status_emoji = {
            "started": ":rocket:",
            "succeeded": ":white_check_mark:",
            "failed": ":x:",
            "rolled_back": ":rewind:",
        }.get(status, ":information_source:")

        text = f"{status_emoji} Deployment {status}: {service} v{version} to {environment}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Deployment {status.title()}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Service:*\n{service}"},
                    {"type": "mrkdwn", "text": f"*Version:*\n{version}"},
                    {"type": "mrkdwn", "text": f"*Environment:*\n{environment}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{status_emoji} {status}"},
                ],
            },
        ]

        if url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Details"},
                        "url": url,
                    }
                ],
            })

        return self.post_message(channel, text, blocks=blocks)

    def _send_incident_notification(
        self,
        channel: str,
        title: str = "Unknown Incident",
        severity: str = "unknown",
        status: str = "triggered",
        service: str | None = None,
        url: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send an incident notification."""
        severity_emoji = {
            "critical": ":rotating_light:",
            "high": ":fire:",
            "medium": ":warning:",
            "low": ":information_source:",
        }.get(severity.lower(), ":exclamation:")

        status_emoji = {
            "triggered": ":rotating_light:",
            "acknowledged": ":eyes:",
            "resolved": ":white_check_mark:",
        }.get(status.lower(), ":grey_question:")

        text = f"{severity_emoji} Incident {status}: {title}"

        fields = [
            {"type": "mrkdwn", "text": f"*Severity:*\n{severity_emoji} {severity}"},
            {"type": "mrkdwn", "text": f"*Status:*\n{status_emoji} {status}"},
        ]

        if service:
            fields.append({"type": "mrkdwn", "text": f"*Service:*\n{service}"})

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title},
            },
            {
                "type": "section",
                "fields": fields,
            },
        ]

        if url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Incident"},
                        "url": url,
                    }
                ],
            })

        return self.post_message(channel, text, blocks=blocks)

    def _send_build_notification(
        self,
        channel: str,
        repository: str = "unknown",
        branch: str = "unknown",
        status: str = "started",
        commit: str | None = None,
        url: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a build notification."""
        status_emoji = {
            "started": ":hourglass_flowing_sand:",
            "succeeded": ":white_check_mark:",
            "failed": ":x:",
        }.get(status.lower(), ":information_source:")

        text = f"{status_emoji} Build {status}: {repository} ({branch})"

        fields = [
            {"type": "mrkdwn", "text": f"*Repository:*\n{repository}"},
            {"type": "mrkdwn", "text": f"*Branch:*\n{branch}"},
            {"type": "mrkdwn", "text": f"*Status:*\n{status_emoji} {status}"},
        ]

        if commit:
            fields.append({"type": "mrkdwn", "text": f"*Commit:*\n`{commit[:8]}`"})

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Build {status.title()}"},
            },
            {
                "type": "section",
                "fields": fields,
            },
        ]

        if url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Build"},
                        "url": url,
                    }
                ],
            })

        return self.post_message(channel, text, blocks=blocks)
