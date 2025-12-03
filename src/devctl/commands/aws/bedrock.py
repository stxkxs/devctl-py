"""Bedrock commands for AWS AI/ML operations."""

import json
from datetime import datetime, timedelta
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.core.output import format_cost


@click.group()
@pass_context
def bedrock(ctx: DevCtlContext) -> None:
    """Bedrock operations - AI/ML model management.

    \b
    Examples:
        devctl aws bedrock list-models
        devctl aws bedrock invoke anthropic.claude-v2 --prompt "Hello"
        devctl aws bedrock usage --days 7
    """
    pass


@bedrock.command("list-models")
@click.option("--provider", help="Filter by provider (e.g., anthropic, amazon, meta)")
@click.option("--inference", is_flag=True, help="Only show models available for inference")
@pass_context
def list_models(ctx: DevCtlContext, provider: str | None, inference: bool) -> None:
    """List available foundation models."""
    try:
        bedrock_client = ctx.aws.bedrock

        kwargs: dict[str, Any] = {}
        if provider:
            kwargs["byProvider"] = provider
        if inference:
            kwargs["byInferenceType"] = "ON_DEMAND"

        response = bedrock_client.list_foundation_models(**kwargs)
        models = response.get("modelSummaries", [])

        data = []
        for model in models:
            data.append({
                "ModelId": model["modelId"],
                "Provider": model["providerName"],
                "Name": model["modelName"][:30],
                "Input": ", ".join(model.get("inputModalities", []))[:15],
                "Output": ", ".join(model.get("outputModalities", []))[:15],
                "Streaming": "Yes" if model.get("responseStreamingSupported") else "No",
            })

        ctx.output.print_data(
            data,
            headers=["ModelId", "Provider", "Name", "Input", "Output", "Streaming"],
            title=f"Foundation Models ({len(data)} available)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list models: {e}")


@bedrock.command()
@click.argument("model_id")
@click.option("--prompt", "-p", required=True, help="Prompt text")
@click.option("--max-tokens", type=int, default=500, help="Maximum tokens to generate")
@click.option("--temperature", type=float, default=0.7, help="Temperature (0-1)")
@click.option("--stream", is_flag=True, help="Stream the response")
@pass_context
def invoke(
    ctx: DevCtlContext,
    model_id: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    stream: bool,
) -> None:
    """Invoke a foundation model.

    MODEL_ID is the model identifier (e.g., anthropic.claude-v2).
    """
    if ctx.dry_run:
        ctx.log_dry_run("invoke model", {
            "model_id": model_id,
            "prompt_length": len(prompt),
            "max_tokens": max_tokens,
        })
        return

    try:
        bedrock_runtime = ctx.aws.bedrock_runtime

        # Build request body based on model provider
        if "anthropic" in model_id.lower():
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
        elif "amazon" in model_id.lower():
            body = {
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": max_tokens,
                    "temperature": temperature,
                },
            }
        elif "meta" in model_id.lower():
            body = {
                "prompt": prompt,
                "max_gen_len": max_tokens,
                "temperature": temperature,
            }
        else:
            # Generic format
            body = {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

        if stream:
            response = bedrock_runtime.invoke_model_with_response_stream(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
            )

            ctx.output.print_info(f"Response from {model_id}:")
            for event in response.get("body"):
                chunk = json.loads(event["chunk"]["bytes"])
                if "anthropic" in model_id.lower():
                    if chunk.get("type") == "content_block_delta":
                        print(chunk.get("delta", {}).get("text", ""), end="", flush=True)
                else:
                    print(chunk.get("completion", chunk.get("generation", "")), end="", flush=True)
            print()  # Newline at end

        else:
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
            )

            response_body = json.loads(response["body"].read())

            # Extract response based on model
            if "anthropic" in model_id.lower():
                text = response_body.get("content", [{}])[0].get("text", "")
                usage = response_body.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
            elif "amazon" in model_id.lower():
                results = response_body.get("results", [{}])
                text = results[0].get("outputText", "") if results else ""
                input_tokens = response_body.get("inputTextTokenCount", 0)
                output_tokens = sum(r.get("tokenCount", 0) for r in results)
            else:
                text = response_body.get("completion", response_body.get("generation", str(response_body)))
                input_tokens = 0
                output_tokens = 0

            ctx.output.print_panel(text, title=f"Response from {model_id}")

            if input_tokens or output_tokens:
                ctx.output.print_info(f"Tokens: {input_tokens} input, {output_tokens} output")

    except ClientError as e:
        raise AWSError(f"Failed to invoke model: {e}")


@bedrock.command("list-jobs")
@click.option("--status", type=click.Choice(["InProgress", "Completed", "Failed", "Stopping", "Stopped"]), help="Filter by status")
@click.option("--max-results", type=int, default=20, help="Maximum results to return")
@pass_context
def list_jobs(ctx: DevCtlContext, status: str | None, max_results: int) -> None:
    """List model customization jobs."""
    try:
        bedrock_client = ctx.aws.bedrock

        kwargs: dict[str, Any] = {"maxResults": max_results}
        if status:
            kwargs["statusEquals"] = status

        response = bedrock_client.list_model_customization_jobs(**kwargs)
        jobs = response.get("modelCustomizationJobSummaries", [])

        if not jobs:
            ctx.output.print_info("No customization jobs found")
            return

        data = []
        for job in jobs:
            data.append({
                "JobName": job["jobName"][:30],
                "Status": job["status"],
                "BaseModel": job["baseModelIdentifier"].split("/")[-1][:20],
                "Created": job.get("creationTime", "").strftime("%Y-%m-%d") if job.get("creationTime") else "-",
            })

        ctx.output.print_data(
            data,
            headers=["JobName", "Status", "BaseModel", "Created"],
            title=f"Model Customization Jobs ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list jobs: {e}")


@bedrock.command()
@click.option("--days", type=int, default=7, help="Days of history to analyze")
@pass_context
def usage(ctx: DevCtlContext, days: int) -> None:
    """Show Bedrock usage and estimated costs.

    Note: Requires CloudWatch metrics access.
    """
    try:
        cloudwatch = ctx.aws.cloudwatch

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        # Get invocation metrics
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/Bedrock",
            MetricName="Invocations",
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,  # Daily
            Statistics=["Sum"],
        )

        datapoints = response.get("Datapoints", [])

        if not datapoints:
            ctx.output.print_info("No Bedrock usage data found for the specified period")
            ctx.output.print_info("Note: CloudWatch metrics may take some time to populate")
            return

        # Sort by timestamp
        datapoints.sort(key=lambda x: x["Timestamp"])

        total_invocations = sum(d["Sum"] for d in datapoints)

        data = []
        for dp in datapoints:
            data.append({
                "Date": dp["Timestamp"].strftime("%Y-%m-%d"),
                "Invocations": int(dp["Sum"]),
            })

        ctx.output.print_data(
            data,
            headers=["Date", "Invocations"],
            title=f"Bedrock Usage ({days} days)",
        )

        ctx.output.print_info(f"Total invocations: {int(total_invocations):,}")

        # Try to get token metrics
        try:
            input_response = cloudwatch.get_metric_statistics(
                Namespace="AWS/Bedrock",
                MetricName="InputTokenCount",
                StartTime=start_time,
                EndTime=end_time,
                Period=86400 * days,
                Statistics=["Sum"],
            )

            output_response = cloudwatch.get_metric_statistics(
                Namespace="AWS/Bedrock",
                MetricName="OutputTokenCount",
                StartTime=start_time,
                EndTime=end_time,
                Period=86400 * days,
                Statistics=["Sum"],
            )

            input_tokens = sum(d["Sum"] for d in input_response.get("Datapoints", []))
            output_tokens = sum(d["Sum"] for d in output_response.get("Datapoints", []))

            if input_tokens or output_tokens:
                ctx.output.print_info(f"Total tokens: {int(input_tokens):,} input, {int(output_tokens):,} output")

                # Rough cost estimate (Claude pricing)
                input_cost = (input_tokens / 1000) * 0.008
                output_cost = (output_tokens / 1000) * 0.024
                total_cost = input_cost + output_cost

                ctx.output.print_info(f"Estimated cost: {format_cost(total_cost, 'USD')} (based on Claude pricing)")

        except ClientError:
            pass

    except ClientError as e:
        raise AWSError(f"Failed to get usage data: {e}")


@bedrock.command()
@click.option("--list", "list_guardrails", is_flag=True, help="List existing guardrails")
@click.option("--create", type=click.Path(exists=True), help="Create guardrail from JSON file")
@pass_context
def guardrails(ctx: DevCtlContext, list_guardrails: bool, create: str | None) -> None:
    """Manage Bedrock guardrails."""
    try:
        bedrock_client = ctx.aws.bedrock

        if create:
            if ctx.dry_run:
                ctx.log_dry_run("create guardrail", {"file": create})
                return

            with open(create) as f:
                config = json.load(f)

            response = bedrock_client.create_guardrail(**config)
            ctx.output.print_success(f"Created guardrail: {response['guardrailId']}")

        else:
            # List guardrails
            response = bedrock_client.list_guardrails()
            guardrails_list = response.get("guardrails", [])

            if not guardrails_list:
                ctx.output.print_info("No guardrails configured")
                return

            data = []
            for g in guardrails_list:
                data.append({
                    "Name": g["name"],
                    "ID": g["id"][:20],
                    "Status": g["status"],
                    "Version": g.get("version", "-"),
                    "Created": g.get("createdAt", "").strftime("%Y-%m-%d") if g.get("createdAt") else "-",
                })

            ctx.output.print_data(
                data,
                headers=["Name", "ID", "Status", "Version", "Created"],
                title=f"Bedrock Guardrails ({len(data)} found)",
            )

    except ClientError as e:
        raise AWSError(f"Guardrail operation failed: {e}")
