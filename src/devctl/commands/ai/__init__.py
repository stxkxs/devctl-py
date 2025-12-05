"""AI-powered commands using AWS Bedrock."""

import click

from devctl.core.context import pass_context, DevCtlContext


@click.group()
@pass_context
def ai(ctx: DevCtlContext) -> None:
    """AI-powered operations using AWS Bedrock.

    \b
    Examples:
        devctl ai ask "how do I list S3 buckets?"
        devctl ai explain-anomaly --anomaly-id ABC123
        devctl ai review-iac ./terraform/main.tf
    """
    pass


# Import and register subcommands
from devctl.commands.ai import ask, explain, review

ai.add_command(ask.ask)
ai.add_command(explain.explain_anomaly)
ai.add_command(review.review_iac)
