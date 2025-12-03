"""Custom exceptions for devctl."""

from typing import Any


class DevCtlError(Exception):
    """Base exception for all devctl errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - {self.details}"
        return self.message


class ConfigError(DevCtlError):
    """Configuration-related errors."""

    pass


class ValidationError(DevCtlError):
    """Input validation errors."""

    pass


class AWSError(DevCtlError):
    """AWS API errors."""

    def __init__(
        self,
        message: str,
        service: str | None = None,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.service = service
        self.operation = operation


class GrafanaError(DevCtlError):
    """Grafana API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.status_code = status_code


class GitHubError(DevCtlError):
    """GitHub API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.status_code = status_code


class WorkflowError(DevCtlError):
    """Workflow execution errors."""

    def __init__(
        self,
        message: str,
        step: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.step = step


class AuthenticationError(DevCtlError):
    """Authentication/authorization errors."""

    pass


class TimeoutError(DevCtlError):
    """Operation timeout errors."""

    def __init__(
        self,
        message: str,
        timeout_seconds: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.timeout_seconds = timeout_seconds
