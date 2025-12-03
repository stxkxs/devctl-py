"""AWS client factory using boto3."""

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from devctl.config import AWSConfig
from devctl.core.exceptions import AWSError, AuthenticationError
from devctl.core.logging import get_logger

logger = get_logger(__name__)


class AWSClientFactory:
    """Factory for creating boto3 clients with consistent configuration."""

    def __init__(self, config: AWSConfig):
        self._config = config
        self._session: boto3.Session | None = None

    @property
    def session(self) -> boto3.Session:
        """Get or create boto3 session."""
        if self._session is None:
            profile = self._config.get_profile()
            region = self._config.get_region()

            session_kwargs: dict[str, Any] = {}
            if profile:
                session_kwargs["profile_name"] = profile
            if region:
                session_kwargs["region_name"] = region

            # Use explicit credentials if provided
            if self._config.access_key_id and self._config.secret_access_key:
                session_kwargs["aws_access_key_id"] = self._config.access_key_id
                session_kwargs["aws_secret_access_key"] = self._config.secret_access_key
                if self._config.session_token:
                    session_kwargs["aws_session_token"] = self._config.session_token

            try:
                self._session = boto3.Session(**session_kwargs)
                logger.debug(
                    "Created AWS session",
                    profile=profile,
                    region=region,
                )
            except BotoCoreError as e:
                raise AuthenticationError(f"Failed to create AWS session: {e}")

        return self._session

    @property
    def region(self) -> str:
        """Get the configured region."""
        return self.session.region_name or "us-east-1"

    @property
    def account_id(self) -> str:
        """Get the AWS account ID."""
        sts = self.client("sts")
        identity = sts.get_caller_identity()
        return identity["Account"]

    def client(self, service_name: str, **kwargs: Any) -> Any:
        """Create a boto3 client for a service.

        Args:
            service_name: AWS service name (e.g., 's3', 'ec2', 'iam')
            **kwargs: Additional client configuration

        Returns:
            boto3 client instance
        """
        config = BotoConfig(
            retries={"max_attempts": 3, "mode": "adaptive"},
            connect_timeout=10,
            read_timeout=30,
        )

        client_kwargs: dict[str, Any] = {"config": config, **kwargs}

        if self._config.endpoint_url:
            client_kwargs["endpoint_url"] = self._config.endpoint_url

        try:
            return self.session.client(service_name, **client_kwargs)
        except BotoCoreError as e:
            raise AWSError(
                f"Failed to create {service_name} client: {e}",
                service=service_name,
            )

    def resource(self, service_name: str, **kwargs: Any) -> Any:
        """Create a boto3 resource for a service.

        Args:
            service_name: AWS service name
            **kwargs: Additional resource configuration

        Returns:
            boto3 resource instance
        """
        resource_kwargs: dict[str, Any] = {**kwargs}

        if self._config.endpoint_url:
            resource_kwargs["endpoint_url"] = self._config.endpoint_url

        try:
            return self.session.resource(service_name, **resource_kwargs)
        except BotoCoreError as e:
            raise AWSError(
                f"Failed to create {service_name} resource: {e}",
                service=service_name,
            )

    # Convenience methods for common clients
    @property
    def iam(self) -> Any:
        """Get IAM client."""
        return self.client("iam")

    @property
    def s3(self) -> Any:
        """Get S3 client."""
        return self.client("s3")

    @property
    def ecr(self) -> Any:
        """Get ECR client."""
        return self.client("ecr")

    @property
    def eks(self) -> Any:
        """Get EKS client."""
        return self.client("eks")

    @property
    def sts(self) -> Any:
        """Get STS client."""
        return self.client("sts")

    @property
    def ce(self) -> Any:
        """Get Cost Explorer client."""
        return self.client("ce")

    @property
    def bedrock(self) -> Any:
        """Get Bedrock client."""
        return self.client("bedrock")

    @property
    def bedrock_runtime(self) -> Any:
        """Get Bedrock Runtime client."""
        return self.client("bedrock-runtime")

    @property
    def cloudwatch(self) -> Any:
        """Get CloudWatch client."""
        return self.client("cloudwatch")

    @property
    def logs(self) -> Any:
        """Get CloudWatch Logs client."""
        return self.client("logs")

    @property
    def sagemaker(self) -> Any:
        """Get SageMaker client."""
        return self.client("sagemaker")

    @property
    def bedrock_agent(self) -> Any:
        """Get Bedrock Agent client."""
        return self.client("bedrock-agent")

    @property
    def bedrock_agent_runtime(self) -> Any:
        """Get Bedrock Agent Runtime client."""
        return self.client("bedrock-agent-runtime")

    @property
    def forecast(self) -> Any:
        """Get AWS Forecast client."""
        return self.client("forecast")

    @property
    def forecastquery(self) -> Any:
        """Get AWS Forecast Query client."""
        return self.client("forecastquery")

    @property
    def autoscaling(self) -> Any:
        """Get Auto Scaling client."""
        return self.client("autoscaling")


def handle_aws_error(func: Any) -> Any:
    """Decorator to handle AWS errors consistently."""
    from functools import wraps

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            raise AWSError(
                f"{error_code}: {error_message}",
                service=e.operation_name if hasattr(e, "operation_name") else None,
                details={"response": e.response},
            )
        except BotoCoreError as e:
            raise AWSError(str(e))

    return wrapper


def paginate(client: Any, method: str, key: str, **kwargs: Any) -> list[Any]:
    """Helper to paginate through AWS API results.

    Args:
        client: boto3 client
        method: Method name to call
        key: Key in response containing items
        **kwargs: Arguments to pass to the method

    Returns:
        List of all items across all pages
    """
    paginator = client.get_paginator(method)
    items = []

    for page in paginator.paginate(**kwargs):
        items.extend(page.get(key, []))

    return items
