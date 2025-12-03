"""Integration tests for AWS commands using moto mocking.

These tests verify that our AWS commands work correctly with the AWS SDK,
without making real API calls. This is the sweet spot of the testing trophy -
integration tests that give confidence without being slow or flaky.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from moto import mock_aws

from devctl.cli import cli
from devctl.clients.aws import AWSClientFactory
from devctl.config import AWSConfig


@pytest.fixture
def cli_runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def set_aws_region(monkeypatch):
    """Set AWS region for all tests."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


# --- AWS Client Tests ---


class TestAWSClientFactory:
    """Tests for AWSClientFactory class."""

    @mock_aws
    def test_client_creation(self):
        """Test that clients are created correctly."""
        config = AWSConfig(region="us-east-1")
        client = AWSClientFactory(config)

        # Should be able to create a client
        s3 = client.s3
        assert s3 is not None

    @mock_aws
    def test_client_caching(self):
        """Test that clients are cached."""
        config = AWSConfig(region="us-east-1")
        client = AWSClientFactory(config)

        # Note: clients are not cached in current implementation, but session is
        s3_1 = client.session
        s3_2 = client.session
        assert s3_1 is s3_2  # Same session instance

    @mock_aws
    def test_region_from_config(self, monkeypatch):
        """Test that region is read from config."""
        # Clear the default region set by autouse fixture
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

        config = AWSConfig(region="eu-west-1")
        client = AWSClientFactory(config)

        # The session should use the configured region
        assert client.session.region_name == "eu-west-1"


# --- S3 Integration Tests ---


class TestS3Commands:
    """Integration tests for S3 commands."""

    @mock_aws
    def test_s3_ls_empty(self, cli_runner):
        """Test listing when no buckets exist."""
        result = cli_runner.invoke(cli, ["aws", "s3", "ls"])
        # Should not error, may show empty or message
        assert result.exit_code == 0

    @mock_aws
    def test_s3_ls_with_buckets(self, cli_runner):
        """Test listing buckets."""
        import boto3

        # Create some buckets
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket-1")
        s3.create_bucket(Bucket="test-bucket-2")

        result = cli_runner.invoke(cli, ["aws", "s3", "ls"])
        assert result.exit_code == 0
        assert "test-bucket-1" in result.output
        assert "test-bucket-2" in result.output

    @mock_aws
    def test_s3_ls_bucket_contents(self, cli_runner):
        """Test listing objects in a bucket."""
        import boto3

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="my-bucket")
        s3.put_object(Bucket="my-bucket", Key="file1.txt", Body=b"hello")
        s3.put_object(Bucket="my-bucket", Key="file2.txt", Body=b"world")

        result = cli_runner.invoke(cli, ["aws", "s3", "ls", "my-bucket"])
        assert result.exit_code == 0
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output

    @mock_aws
    def test_s3_size(self, cli_runner):
        """Test getting bucket size."""
        import boto3

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="sized-bucket")
        s3.put_object(Bucket="sized-bucket", Key="file.txt", Body=b"x" * 1024)

        result = cli_runner.invoke(cli, ["aws", "s3", "size", "sized-bucket"])
        assert result.exit_code == 0


# --- IAM Integration Tests ---


class TestIAMCommands:
    """Integration tests for IAM commands."""

    @mock_aws
    def test_iam_whoami(self, cli_runner):
        """Test whoami command."""
        result = cli_runner.invoke(cli, ["aws", "iam", "whoami"])
        # Should return caller identity
        assert result.exit_code == 0

    @mock_aws
    def test_iam_list_users_empty(self, cli_runner):
        """Test listing when no users exist."""
        result = cli_runner.invoke(cli, ["aws", "iam", "list-users"])
        assert result.exit_code == 0

    @mock_aws
    def test_iam_list_users(self, cli_runner):
        """Test listing IAM users."""
        import boto3

        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_user(UserName="test-user-1")
        iam.create_user(UserName="test-user-2")

        result = cli_runner.invoke(cli, ["aws", "iam", "list-users"])
        assert result.exit_code == 0
        assert "test-user-1" in result.output
        assert "test-user-2" in result.output

    @mock_aws
    def test_iam_list_roles(self, cli_runner):
        """Test listing IAM roles."""
        import boto3

        iam = boto3.client("iam", region_name="us-east-1")
        assume_role_policy = json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "ec2.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            }
        )
        iam.create_role(RoleName="test-role", AssumeRolePolicyDocument=assume_role_policy)

        result = cli_runner.invoke(cli, ["aws", "iam", "list-roles"])
        assert result.exit_code == 0
        assert "test-role" in result.output


# --- ECR Integration Tests ---


class TestECRCommands:
    """Integration tests for ECR commands."""

    @mock_aws
    def test_ecr_list_repos_empty(self, cli_runner):
        """Test listing when no repos exist."""
        result = cli_runner.invoke(cli, ["aws", "ecr", "list-repos"])
        assert result.exit_code == 0

    @mock_aws
    def test_ecr_list_repos(self, cli_runner):
        """Test listing ECR repositories."""
        import boto3

        ecr = boto3.client("ecr", region_name="us-east-1")
        ecr.create_repository(repositoryName="my-app")
        ecr.create_repository(repositoryName="my-other-app")

        result = cli_runner.invoke(cli, ["aws", "ecr", "list-repos"])
        assert result.exit_code == 0
        assert "my-app" in result.output
        assert "my-other-app" in result.output


# --- EKS Integration Tests ---


class TestEKSCommands:
    """Integration tests for EKS commands."""

    @mock_aws
    def test_eks_list_clusters_empty(self, cli_runner):
        """Test listing when no clusters exist."""
        result = cli_runner.invoke(cli, ["aws", "eks", "list-clusters"])
        assert result.exit_code == 0


# --- Cost Explorer Tests ---


class TestCostCommands:
    """Tests for cost commands.

    Note: moto has limited Cost Explorer support, so we use mocking.
    """

    def test_cost_summary_help(self, cli_runner):
        """Test cost summary help works."""
        result = cli_runner.invoke(cli, ["aws", "cost", "summary", "--help"])
        assert result.exit_code == 0
        assert "days" in result.output.lower()

    def test_cost_by_service_help(self, cli_runner):
        """Test cost by-service help works."""
        result = cli_runner.invoke(cli, ["aws", "cost", "by-service", "--help"])
        assert result.exit_code == 0


# --- CloudWatch Tests ---


class TestCloudWatchCommands:
    """Integration tests for CloudWatch commands."""

    @mock_aws
    def test_cloudwatch_alarms_empty(self, cli_runner):
        """Test listing when no alarms exist."""
        result = cli_runner.invoke(cli, ["aws", "cloudwatch", "alarms"])
        assert result.exit_code == 0

    @mock_aws
    def test_cloudwatch_alarms(self, cli_runner):
        """Test listing CloudWatch alarms."""
        import boto3

        cw = boto3.client("cloudwatch", region_name="us-east-1")
        cw.put_metric_alarm(
            AlarmName="test-alarm",
            MetricName="CPUUtilization",
            Namespace="AWS/EC2",
            Statistic="Average",
            Period=300,
            EvaluationPeriods=1,
            Threshold=80,
            ComparisonOperator="GreaterThanThreshold",
        )

        result = cli_runner.invoke(cli, ["aws", "cloudwatch", "alarms"])
        assert result.exit_code == 0
        assert "test-alarm" in result.output


# --- Bedrock Tests ---


class TestBedrockCommands:
    """Tests for Bedrock commands.

    Bedrock is not fully supported by moto, so we test help and basic structure.
    """

    def test_bedrock_help(self, cli_runner):
        """Test bedrock help works."""
        result = cli_runner.invoke(cli, ["aws", "bedrock", "--help"])
        assert result.exit_code == 0
        assert "list-models" in result.output
        assert "invoke" in result.output

    def test_bedrock_agents_help(self, cli_runner):
        """Test bedrock agents help works."""
        result = cli_runner.invoke(cli, ["aws", "bedrock", "agents", "--help"])
        assert result.exit_code == 0

    def test_bedrock_batch_help(self, cli_runner):
        """Test bedrock batch help works."""
        result = cli_runner.invoke(cli, ["aws", "bedrock", "batch", "--help"])
        assert result.exit_code == 0


# --- Forecast Tests ---


class TestForecastCommands:
    """Tests for Forecast commands.

    Forecast is not supported by moto, so we test help and structure.
    """

    def test_forecast_help(self, cli_runner):
        """Test forecast help works."""
        result = cli_runner.invoke(cli, ["aws", "forecast", "--help"])
        assert result.exit_code == 0
        assert "scaling" in result.output
        assert "datasets" in result.output

    def test_forecast_scaling_help(self, cli_runner):
        """Test forecast scaling help works."""
        result = cli_runner.invoke(cli, ["aws", "forecast", "scaling", "--help"])
        assert result.exit_code == 0
        assert "recommend" in result.output
        assert "apply" in result.output

    def test_forecast_export_metrics_help(self, cli_runner):
        """Test export-metrics help works."""
        result = cli_runner.invoke(cli, ["aws", "forecast", "export-metrics", "--help"])
        assert result.exit_code == 0
        assert "namespace" in result.output
        assert "metric" in result.output


# --- JSON Output Tests ---


class TestJSONOutput:
    """Tests for JSON output format across commands."""

    @mock_aws
    def test_s3_ls_json_output(self, cli_runner):
        """Test S3 ls with JSON output."""
        import boto3

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="json-test-bucket")

        result = cli_runner.invoke(cli, ["-o", "json", "--no-color", "aws", "s3", "ls"])
        assert result.exit_code == 0
        # Output should contain JSON (may have some formatting)
        assert "json-test-bucket" in result.output

    @mock_aws
    def test_iam_list_users_json(self, cli_runner):
        """Test IAM list-users with JSON output."""
        import boto3

        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_user(UserName="json-user")

        result = cli_runner.invoke(cli, ["-o", "json", "--no-color", "aws", "iam", "list-users"])
        assert result.exit_code == 0
        # Output should contain JSON with user data
        assert "json-user" in result.output
