"""Natural language to devctl command translation."""

import json
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError


SYSTEM_PROMPT = """You are a DevOps CLI assistant that helps users formulate devctl commands.

devctl is a unified CLI for DevOps operations with the following command groups:
- aws: AWS operations (iam, s3, ecr, eks, cost, bedrock, cloudwatch, forecast, ssm, tagging, budget)
- grafana: Grafana dashboards and alerts
- github: GitHub repositories, PRs, issues
- jira: Jira issues and projects
- k8s: Kubernetes operations
- pagerduty: PagerDuty incidents
- argocd: ArgoCD applications
- logs: Log aggregation
- deploy: Deployment orchestration
- slack: Slack notifications
- confluence: Confluence pages
- compliance: Compliance checks
- terraform: Terraform operations
- workflow: Workflow automation

Common commands:
- devctl aws iam whoami - Show current AWS identity
- devctl aws cost summary --days 30 - Show cost summary
- devctl aws cost by-service --top 10 - Show costs by service
- devctl aws cost by-tag --tag-key team - Show costs by tag
- devctl aws budget list - List AWS budgets
- devctl aws tagging audit --required-tags team,project - Audit resource tags
- devctl aws s3 ls BUCKET - List S3 bucket contents
- devctl aws eks list-clusters - List EKS clusters
- devctl grafana dashboards list - List Grafana dashboards
- devctl github repos list - List GitHub repositories
- devctl k8s pods list -n NAMESPACE - List Kubernetes pods
- devctl workflow run FILE.yaml - Run a workflow

Given a natural language request, respond with:
1. The exact devctl command to run
2. A brief explanation of what it does
3. Any relevant options or alternatives

Format your response as JSON:
{
  "command": "devctl aws cost summary --days 30",
  "explanation": "Shows cost summary for the last 30 days",
  "alternatives": ["devctl aws cost by-service --top 10", "devctl aws cost forecast"]
}
"""


@click.command()
@click.argument("question", nargs=-1, required=True)
@click.option("--execute", "-x", is_flag=True, help="Execute the suggested command")
@click.option("--model", default="anthropic.claude-3-haiku-20240307-v1:0", help="Model to use")
@pass_context
def ask(
    ctx: DevCtlContext,
    question: tuple[str, ...],
    execute: bool,
    model: str,
) -> None:
    """Ask a natural language question to get devctl commands.

    \b
    Examples:
        devctl ai ask how do I list S3 buckets
        devctl ai ask "what is my AWS account ID"
        devctl ai ask show me cost breakdown by team --execute
    """
    question_text = " ".join(question)

    try:
        bedrock_runtime = ctx.aws.bedrock_runtime

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "temperature": 0.3,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": question_text}],
        }

        response = bedrock_runtime.invoke_model(
            modelId=model,
            body=json.dumps(body),
            contentType="application/json",
        )

        response_body = json.loads(response["body"].read())
        text = response_body.get("content", [{}])[0].get("text", "")

        # Try to parse as JSON
        try:
            # Find JSON in response
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(text[json_start:json_end])

                command = result.get("command", "")
                explanation = result.get("explanation", "")
                alternatives = result.get("alternatives", [])

                ctx.output.print_panel(
                    f"[bold cyan]{command}[/bold cyan]\n\n{explanation}",
                    title="Suggested Command",
                )

                if alternatives:
                    ctx.output.print_info("Alternatives:")
                    for alt in alternatives:
                        ctx.output.print(f"  - {alt}")

                if execute and command:
                    ctx.output.print("")
                    if ctx.output.confirm(f"Execute: {command}?"):
                        import subprocess
                        import shlex

                        parts = shlex.split(command)
                        result = subprocess.run(parts, capture_output=False)
                        if result.returncode != 0:
                            ctx.output.print_error(f"Command exited with code {result.returncode}")
            else:
                # No JSON found, display raw response
                ctx.output.print_panel(text, title="Response")

        except json.JSONDecodeError:
            ctx.output.print_panel(text, title="Response")

    except ClientError as e:
        raise AWSError(f"Failed to process question: {e}")
