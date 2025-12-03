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


# =============================================================================
# Bedrock Agents
# =============================================================================

@bedrock.group()
@pass_context
def agents(ctx: DevCtlContext) -> None:
    """Bedrock Agents - autonomous AI assistants with tools.

    \b
    Examples:
        devctl aws bedrock agents list
        devctl aws bedrock agents invoke AGENT_ID --prompt "Query"
        devctl aws bedrock agents kb list
    """
    pass


@agents.command("list")
@pass_context
def agents_list(ctx: DevCtlContext) -> None:
    """List Bedrock agents."""
    try:
        agent_client = ctx.aws.bedrock_agent
        response = agent_client.list_agents()
        agents_data = response.get("agentSummaries", [])

        if not agents_data:
            ctx.output.print_info("No agents found")
            return

        data = []
        for agent in agents_data:
            data.append({
                "Name": agent.get("agentName", "-")[:25],
                "ID": agent.get("agentId", "-")[:20],
                "Status": agent.get("agentStatus", "-"),
                "Foundation Model": agent.get("foundationModel", "-").split("/")[-1][:20] if agent.get("foundationModel") else "-",
                "Updated": agent.get("updatedAt").strftime("%Y-%m-%d") if agent.get("updatedAt") else "-",
            })

        ctx.output.print_data(
            data,
            headers=["Name", "ID", "Status", "Foundation Model", "Updated"],
            title=f"Bedrock Agents ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list agents: {e}")


@agents.command("describe")
@click.argument("agent_id")
@pass_context
def agents_describe(ctx: DevCtlContext, agent_id: str) -> None:
    """Describe a Bedrock agent."""
    try:
        agent_client = ctx.aws.bedrock_agent
        response = agent_client.get_agent(agentId=agent_id)
        agent = response.get("agent", {})

        data = {
            "Agent ID": agent.get("agentId"),
            "Name": agent.get("agentName"),
            "Status": agent.get("agentStatus"),
            "Foundation Model": agent.get("foundationModel"),
            "Instruction": agent.get("instruction", "")[:200] + "..." if len(agent.get("instruction", "")) > 200 else agent.get("instruction", "-"),
            "Idle Timeout": f"{agent.get('idleSessionTTLInSeconds', 0)}s",
            "Created": agent.get("createdAt").strftime("%Y-%m-%d %H:%M") if agent.get("createdAt") else "-",
            "Updated": agent.get("updatedAt").strftime("%Y-%m-%d %H:%M") if agent.get("updatedAt") else "-",
        }

        ctx.output.print_data(data, title=f"Agent: {agent.get('agentName')}")

        # List action groups
        try:
            ag_response = agent_client.list_agent_action_groups(
                agentId=agent_id,
                agentVersion="DRAFT"
            )
            action_groups = ag_response.get("actionGroupSummaries", [])
            if action_groups:
                ctx.output.print_info(f"\nAction Groups ({len(action_groups)}):")
                for ag in action_groups:
                    ctx.output.console.print(f"  - {ag.get('actionGroupName')} ({ag.get('actionGroupState')})")
        except ClientError:
            pass

    except ClientError as e:
        raise AWSError(f"Failed to describe agent: {e}")


@agents.command("invoke")
@click.argument("agent_id")
@click.argument("agent_alias_id", default="TSTALIASID")
@click.option("--prompt", "-p", required=True, help="Input prompt for the agent")
@click.option("--session-id", help="Session ID for multi-turn conversation")
@pass_context
def agents_invoke(
    ctx: DevCtlContext,
    agent_id: str,
    agent_alias_id: str,
    prompt: str,
    session_id: str | None,
) -> None:
    """Invoke a Bedrock agent.

    AGENT_ALIAS_ID defaults to TSTALIASID (test alias).
    """
    if ctx.dry_run:
        ctx.log_dry_run("invoke agent", {
            "agent_id": agent_id,
            "alias_id": agent_alias_id,
            "prompt_length": len(prompt),
        })
        return

    try:
        import uuid
        agent_runtime = ctx.aws.bedrock_agent_runtime

        session = session_id or str(uuid.uuid4())

        response = agent_runtime.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=session,
            inputText=prompt,
        )

        # Process streaming response
        full_response = ""
        for event in response.get("completion", []):
            if "chunk" in event:
                chunk_data = event["chunk"]
                if "bytes" in chunk_data:
                    text = chunk_data["bytes"].decode("utf-8")
                    full_response += text

        ctx.output.print_panel(full_response, title=f"Agent Response (session: {session[:8]}...)")

    except ClientError as e:
        raise AWSError(f"Failed to invoke agent: {e}")


@agents.group("kb")
@pass_context
def knowledge_bases(ctx: DevCtlContext) -> None:
    """Knowledge base operations.

    \b
    Examples:
        devctl aws bedrock agents kb list
        devctl aws bedrock agents kb query KB_ID --query "Search term"
    """
    pass


@knowledge_bases.command("list")
@pass_context
def kb_list(ctx: DevCtlContext) -> None:
    """List knowledge bases."""
    try:
        agent_client = ctx.aws.bedrock_agent
        response = agent_client.list_knowledge_bases()
        kb_list = response.get("knowledgeBaseSummaries", [])

        if not kb_list:
            ctx.output.print_info("No knowledge bases found")
            return

        data = []
        for kb in kb_list:
            data.append({
                "Name": kb.get("name", "-")[:25],
                "ID": kb.get("knowledgeBaseId", "-")[:20],
                "Status": kb.get("status", "-"),
                "Updated": kb.get("updatedAt").strftime("%Y-%m-%d") if kb.get("updatedAt") else "-",
            })

        ctx.output.print_data(
            data,
            headers=["Name", "ID", "Status", "Updated"],
            title=f"Knowledge Bases ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list knowledge bases: {e}")


@knowledge_bases.command("query")
@click.argument("knowledge_base_id")
@click.option("--query", "-q", required=True, help="Search query")
@click.option("--model-id", default="anthropic.claude-3-haiku-20240307-v1:0", help="Model for retrieval and generation")
@click.option("--results", type=int, default=5, help="Number of results to retrieve")
@pass_context
def kb_query(
    ctx: DevCtlContext,
    knowledge_base_id: str,
    query: str,
    model_id: str,
    results: int,
) -> None:
    """Query a knowledge base with RAG."""
    if ctx.dry_run:
        ctx.log_dry_run("query knowledge base", {
            "kb_id": knowledge_base_id,
            "query": query[:50],
        })
        return

    try:
        agent_runtime = ctx.aws.bedrock_agent_runtime

        response = agent_runtime.retrieve_and_generate(
            input={"text": query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": knowledge_base_id,
                    "modelArn": f"arn:aws:bedrock:{ctx.aws.region}::foundation-model/{model_id}",
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults": results,
                        }
                    }
                }
            }
        )

        output = response.get("output", {}).get("text", "No response generated")
        ctx.output.print_panel(output, title="Knowledge Base Response")

        # Show citations
        citations = response.get("citations", [])
        if citations:
            ctx.output.print_info(f"\nSources ({len(citations)} citations):")
            for i, citation in enumerate(citations, 1):
                refs = citation.get("retrievedReferences", [])
                for ref in refs:
                    location = ref.get("location", {})
                    s3_loc = location.get("s3Location", {})
                    if s3_loc:
                        ctx.output.console.print(f"  {i}. s3://{s3_loc.get('uri', 'unknown')}")

    except ClientError as e:
        raise AWSError(f"Failed to query knowledge base: {e}")


# =============================================================================
# Batch Inference
# =============================================================================

@bedrock.group("batch")
@pass_context
def batch(ctx: DevCtlContext) -> None:
    """Batch inference operations.

    \b
    Examples:
        devctl aws bedrock batch list
        devctl aws bedrock batch submit --model MODEL --input s3://bucket/input
        devctl aws bedrock batch status JOB_ID
    """
    pass


@batch.command("list")
@click.option("--status", type=click.Choice(["Submitted", "InProgress", "Completed", "Failed", "Stopping", "Stopped"]))
@pass_context
def batch_list(ctx: DevCtlContext, status: str | None) -> None:
    """List batch inference jobs."""
    try:
        bedrock_client = ctx.aws.bedrock

        kwargs: dict[str, Any] = {}
        if status:
            kwargs["statusEquals"] = status

        response = bedrock_client.list_model_invocation_jobs(**kwargs)
        jobs = response.get("invocationJobSummaries", [])

        if not jobs:
            ctx.output.print_info("No batch jobs found")
            return

        data = []
        for job in jobs:
            data.append({
                "Job ID": job.get("jobArn", "").split("/")[-1][:20],
                "Name": job.get("jobName", "-")[:20],
                "Status": job.get("status", "-"),
                "Model": job.get("modelId", "-").split("/")[-1][:15],
                "Submitted": job.get("submitTime").strftime("%Y-%m-%d %H:%M") if job.get("submitTime") else "-",
            })

        ctx.output.print_data(
            data,
            headers=["Job ID", "Name", "Status", "Model", "Submitted"],
            title=f"Batch Inference Jobs ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list batch jobs: {e}")


@batch.command("submit")
@click.option("--name", required=True, help="Job name")
@click.option("--model", required=True, help="Model ID to use")
@click.option("--input", "input_uri", required=True, help="S3 URI for input data (s3://bucket/path)")
@click.option("--output", "output_uri", required=True, help="S3 URI for output data")
@click.option("--role", required=True, help="IAM role ARN for the job")
@pass_context
def batch_submit(
    ctx: DevCtlContext,
    name: str,
    model: str,
    input_uri: str,
    output_uri: str,
    role: str,
) -> None:
    """Submit a batch inference job."""
    if ctx.dry_run:
        ctx.log_dry_run("submit batch job", {
            "name": name,
            "model": model,
            "input": input_uri,
            "output": output_uri,
        })
        return

    try:
        bedrock_client = ctx.aws.bedrock

        response = bedrock_client.create_model_invocation_job(
            jobName=name,
            modelId=model,
            roleArn=role,
            inputDataConfig={
                "s3InputDataConfig": {
                    "s3Uri": input_uri,
                }
            },
            outputDataConfig={
                "s3OutputDataConfig": {
                    "s3Uri": output_uri,
                }
            },
        )

        job_arn = response.get("jobArn", "")
        ctx.output.print_success(f"Batch job submitted: {job_arn.split('/')[-1]}")
        ctx.output.print_info(f"Full ARN: {job_arn}")

    except ClientError as e:
        raise AWSError(f"Failed to submit batch job: {e}")


@batch.command("status")
@click.argument("job_id")
@pass_context
def batch_status(ctx: DevCtlContext, job_id: str) -> None:
    """Get status of a batch inference job."""
    try:
        bedrock_client = ctx.aws.bedrock

        # Build full ARN if not provided
        if not job_id.startswith("arn:"):
            job_id = f"arn:aws:bedrock:{ctx.aws.region}:{ctx.aws.account_id}:model-invocation-job/{job_id}"

        response = bedrock_client.get_model_invocation_job(jobIdentifier=job_id)

        data = {
            "Job ID": response.get("jobArn", "").split("/")[-1],
            "Name": response.get("jobName"),
            "Status": response.get("status"),
            "Model": response.get("modelId"),
            "Input": response.get("inputDataConfig", {}).get("s3InputDataConfig", {}).get("s3Uri"),
            "Output": response.get("outputDataConfig", {}).get("s3OutputDataConfig", {}).get("s3Uri"),
            "Submitted": response.get("submitTime").strftime("%Y-%m-%d %H:%M:%S") if response.get("submitTime") else "-",
            "End Time": response.get("endTime").strftime("%Y-%m-%d %H:%M:%S") if response.get("endTime") else "-",
        }

        # Add metrics if available
        if response.get("status") == "Completed":
            metrics = response.get("metrics", {})
            if metrics:
                data["Processed Records"] = metrics.get("inputRecordCount", "-")
                data["Output Records"] = metrics.get("outputRecordCount", "-")

        ctx.output.print_data(data, title="Batch Job Status")

        # Show failure message if failed
        if response.get("status") == "Failed":
            message = response.get("message", "Unknown error")
            ctx.output.print_error(f"Failure reason: {message}")

    except ClientError as e:
        raise AWSError(f"Failed to get job status: {e}")


@batch.command("stop")
@click.argument("job_id")
@pass_context
def batch_stop(ctx: DevCtlContext, job_id: str) -> None:
    """Stop a running batch inference job."""
    if ctx.dry_run:
        ctx.log_dry_run("stop batch job", {"job_id": job_id})
        return

    try:
        bedrock_client = ctx.aws.bedrock

        if not job_id.startswith("arn:"):
            job_id = f"arn:aws:bedrock:{ctx.aws.region}:{ctx.aws.account_id}:model-invocation-job/{job_id}"

        bedrock_client.stop_model_invocation_job(jobIdentifier=job_id)
        ctx.output.print_success(f"Stop requested for job: {job_id.split('/')[-1]}")

    except ClientError as e:
        raise AWSError(f"Failed to stop batch job: {e}")


# =============================================================================
# Model Comparison
# =============================================================================

@bedrock.command("compare")
@click.option("--models", "-m", required=True, multiple=True, help="Model IDs to compare (use multiple times)")
@click.option("--prompt", "-p", required=True, help="Prompt to send to all models")
@click.option("--max-tokens", type=int, default=500, help="Maximum tokens per response")
@click.option("--temperature", type=float, default=0.7, help="Temperature")
@pass_context
def compare_models(
    ctx: DevCtlContext,
    models: tuple[str, ...],
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> None:
    """Compare responses from multiple models.

    \b
    Examples:
        devctl aws bedrock compare -m anthropic.claude-3-haiku-20240307-v1:0 \\
            -m anthropic.claude-3-sonnet-20240229-v1:0 -p "Explain kubernetes"
    """
    if len(models) < 2:
        ctx.output.print_error("Please specify at least 2 models to compare")
        return

    if ctx.dry_run:
        ctx.log_dry_run("compare models", {
            "models": list(models),
            "prompt_length": len(prompt),
        })
        return

    bedrock_runtime = ctx.aws.bedrock_runtime
    results = []

    ctx.output.print_info(f"Comparing {len(models)} models...")
    ctx.output.print_info(f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n")

    for model_id in models:
        try:
            start_time = datetime.now()

            # Build request based on provider
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
            elif "mistral" in model_id.lower():
                body = {
                    "prompt": f"<s>[INST] {prompt} [/INST]",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            elif "cohere" in model_id.lower():
                body = {
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            else:
                body = {
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }

            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            response_body = json.loads(response["body"].read())

            # Extract text based on model
            if "anthropic" in model_id.lower():
                text = response_body.get("content", [{}])[0].get("text", "")
                input_tokens = response_body.get("usage", {}).get("input_tokens", 0)
                output_tokens = response_body.get("usage", {}).get("output_tokens", 0)
            elif "amazon" in model_id.lower():
                res = response_body.get("results", [{}])
                text = res[0].get("outputText", "") if res else ""
                input_tokens = response_body.get("inputTextTokenCount", 0)
                output_tokens = sum(r.get("tokenCount", 0) for r in res)
            elif "meta" in model_id.lower():
                text = response_body.get("generation", "")
                input_tokens = response_body.get("prompt_token_count", 0)
                output_tokens = response_body.get("generation_token_count", 0)
            elif "mistral" in model_id.lower():
                outputs = response_body.get("outputs", [{}])
                text = outputs[0].get("text", "") if outputs else ""
                input_tokens = 0
                output_tokens = 0
            elif "cohere" in model_id.lower():
                generations = response_body.get("generations", [{}])
                text = generations[0].get("text", "") if generations else ""
                input_tokens = 0
                output_tokens = 0
            else:
                text = str(response_body)
                input_tokens = 0
                output_tokens = 0

            results.append({
                "model": model_id,
                "text": text,
                "latency": elapsed,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "error": None,
            })

        except ClientError as e:
            results.append({
                "model": model_id,
                "text": "",
                "latency": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "error": str(e),
            })

    # Display results
    for result in results:
        model_name = result["model"].split("/")[-1]

        if result["error"]:
            ctx.output.print_panel(
                f"[red]Error: {result['error']}[/red]",
                title=f"❌ {model_name}",
            )
        else:
            footer = f"⏱️ {result['latency']:.2f}s"
            if result["input_tokens"] or result["output_tokens"]:
                footer += f" | 📊 {result['input_tokens']} in / {result['output_tokens']} out"

            ctx.output.print_panel(
                result["text"],
                title=f"✅ {model_name}",
                subtitle=footer,
            )

    # Summary table
    ctx.output.print_info("\n📊 Comparison Summary:")
    summary_data = []
    for r in results:
        summary_data.append({
            "Model": r["model"].split("/")[-1][:30],
            "Latency": f"{r['latency']:.2f}s" if not r["error"] else "error",
            "Input Tokens": r["input_tokens"] or "-",
            "Output Tokens": r["output_tokens"] or "-",
            "Response Length": len(r["text"]) if r["text"] else 0,
        })

    ctx.output.print_data(
        summary_data,
        headers=["Model", "Latency", "Input Tokens", "Output Tokens", "Response Length"],
    )
