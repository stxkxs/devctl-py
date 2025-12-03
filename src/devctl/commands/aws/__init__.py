"""AWS command group."""

import click

from devctl.core.context import pass_context, DevCtlContext


@click.group()
@pass_context
def aws(ctx: DevCtlContext) -> None:
    """AWS operations - IAM, S3, ECR, EKS, Cost, Bedrock, CloudWatch.

    \b
    Examples:
        devctl aws iam whoami
        devctl aws s3 ls my-bucket
        devctl aws ecr list-repos
        devctl aws eks list-clusters
        devctl aws cost summary
    """
    pass


# Import and register subcommands
from devctl.commands.aws import iam, s3, ecr, eks, cost, bedrock, cloudwatch

aws.add_command(iam.iam)
aws.add_command(s3.s3)
aws.add_command(ecr.ecr)
aws.add_command(eks.eks)
aws.add_command(cost.cost)
aws.add_command(bedrock.bedrock)
aws.add_command(cloudwatch.cloudwatch)
