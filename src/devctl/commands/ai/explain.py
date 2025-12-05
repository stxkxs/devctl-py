"""AI-powered anomaly explanation."""

import json
from datetime import datetime, timedelta
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.core.output import format_cost


ANOMALY_PROMPT = """You are a cloud cost analyst. Analyze the following AWS cost anomaly and provide:

1. **Root Cause Analysis**: What likely caused this cost spike
2. **Impact Assessment**: Business and operational impact
3. **Recommended Actions**: Specific steps to address this
4. **Prevention**: How to prevent similar anomalies in the future

Be concise and actionable. Focus on practical DevOps recommendations.

Anomaly Data:
{anomaly_data}
"""


@click.command("explain-anomaly")
@click.option("--anomaly-id", "-a", help="Specific anomaly ID to explain")
@click.option("--days", type=int, default=7, help="Days to check for anomalies")
@click.option("--model", default="anthropic.claude-3-haiku-20240307-v1:0", help="Model to use")
@pass_context
def explain_anomaly(
    ctx: DevCtlContext,
    anomaly_id: str | None,
    days: int,
    model: str,
) -> None:
    """Get AI explanation for cost anomalies.

    \b
    Examples:
        devctl ai explain-anomaly
        devctl ai explain-anomaly --anomaly-id ABC123
        devctl ai explain-anomaly --days 30
    """
    try:
        ce = ctx.aws.ce

        if anomaly_id:
            # Get specific anomaly
            response = ce.get_anomalies(
                AnomalyId=anomaly_id,
            )
        else:
            # Get recent anomalies
            end = datetime.utcnow()
            start = end - timedelta(days=days)

            response = ce.get_anomalies(
                DateInterval={
                    "StartDate": start.strftime("%Y-%m-%d"),
                    "EndDate": end.strftime("%Y-%m-%d"),
                },
            )

        anomalies = response.get("Anomalies", [])

        if not anomalies:
            ctx.output.print_success("No cost anomalies found")
            return

        # Take the most significant anomaly if no specific ID
        if not anomaly_id:
            anomalies.sort(
                key=lambda x: float(x.get("Impact", {}).get("TotalImpact", 0)),
                reverse=True,
            )

        anomaly = anomalies[0]

        # Build context for AI
        impact = anomaly.get("Impact", {})
        root_causes = anomaly.get("RootCauses", [])

        anomaly_data = {
            "anomaly_id": anomaly.get("AnomalyId"),
            "start_date": anomaly.get("AnomalyStartDate"),
            "end_date": anomaly.get("AnomalyEndDate", "ongoing"),
            "total_impact_usd": float(impact.get("TotalImpact", 0)),
            "impact_percentage": float(impact.get("TotalImpactPercentage", 0)),
            "root_causes": [
                {
                    "service": rc.get("Service"),
                    "region": rc.get("Region"),
                    "linked_account": rc.get("LinkedAccount"),
                    "usage_type": rc.get("UsageType"),
                }
                for rc in root_causes
            ],
        }

        # Display anomaly info
        ctx.output.print_panel(
            f"ID: {anomaly_data['anomaly_id']}\n"
            f"Period: {anomaly_data['start_date']} to {anomaly_data['end_date']}\n"
            f"Impact: {format_cost(anomaly_data['total_impact_usd'], 'USD')} ({anomaly_data['impact_percentage']:.1f}%)\n"
            f"Primary Service: {root_causes[0].get('Service', 'Unknown') if root_causes else 'Unknown'}",
            title="Anomaly Details",
        )

        ctx.output.print_info("Generating AI analysis...")

        # Get AI explanation
        bedrock_runtime = ctx.aws.bedrock_runtime

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1500,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": ANOMALY_PROMPT.format(
                        anomaly_data=json.dumps(anomaly_data, indent=2)
                    ),
                }
            ],
        }

        response = bedrock_runtime.invoke_model(
            modelId=model,
            body=json.dumps(body),
            contentType="application/json",
        )

        response_body = json.loads(response["body"].read())
        explanation = response_body.get("content", [{}])[0].get("text", "")

        ctx.output.print_panel(explanation, title="AI Analysis")

    except ClientError as e:
        raise AWSError(f"Failed to explain anomaly: {e}")
