"""AI-powered Infrastructure as Code review."""

import json
from pathlib import Path
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError


TERRAFORM_REVIEW_PROMPT = """You are a cloud infrastructure security and cost expert. Review the following Terraform code and provide:

1. **Security Issues**: Identify any security vulnerabilities or misconfigurations (severity: Critical/High/Medium/Low)
2. **Cost Optimization**: Identify potential cost savings or inefficiencies
3. **Best Practices**: Suggest improvements for maintainability and reliability
4. **Compliance**: Note any common compliance concerns (SOC2, HIPAA, PCI-DSS)

Format your response with clear sections and bullet points. Be specific about line numbers when possible.

Terraform Code:
```hcl
{code}
```
"""

KUBERNETES_REVIEW_PROMPT = """You are a Kubernetes security and reliability expert. Review the following Kubernetes manifest and provide:

1. **Security Issues**: Identify security vulnerabilities (severity: Critical/High/Medium/Low)
   - Container security (privileged, root user, capabilities)
   - Network policies and exposure
   - Secrets handling
   - Resource limits

2. **Reliability**: Identify reliability concerns
   - Resource requests/limits
   - Health checks (liveness/readiness)
   - Pod disruption budgets
   - Replicas and high availability

3. **Best Practices**: Suggest improvements
   - Labels and annotations
   - Image tagging
   - Configuration management

Format your response with clear sections and bullet points. Be specific about issues found.

Kubernetes Manifest:
```yaml
{code}
```
"""


@click.command("review-iac")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--type", "file_type", type=click.Choice(["terraform", "kubernetes", "auto"]), default="auto", help="File type")
@click.option("--model", default="anthropic.claude-3-haiku-20240307-v1:0", help="Model to use")
@click.option("--output-json", is_flag=True, help="Output as JSON")
@pass_context
def review_iac(
    ctx: DevCtlContext,
    file_path: str,
    file_type: str,
    model: str,
    output_json: bool,
) -> None:
    """Review Infrastructure as Code for security and best practices.

    \b
    Examples:
        devctl ai review-iac ./main.tf
        devctl ai review-iac ./deployment.yaml --type kubernetes
        devctl ai review-iac ./infra/ --output-json
    """
    path = Path(file_path)

    # Collect files to review
    files_to_review: list[tuple[str, str]] = []

    if path.is_file():
        with open(path) as f:
            content = f.read()
        files_to_review.append((str(path), content))
    elif path.is_dir():
        # Collect relevant files
        patterns = ["*.tf", "*.yaml", "*.yml", "*.json"]
        for pattern in patterns:
            for file in path.rglob(pattern):
                if file.is_file() and file.stat().st_size < 100000:  # Skip large files
                    try:
                        with open(file) as f:
                            content = f.read()
                        files_to_review.append((str(file), content))
                    except Exception:
                        pass

    if not files_to_review:
        ctx.output.print_error("No files found to review")
        return

    ctx.output.print_info(f"Reviewing {len(files_to_review)} file(s)...")

    all_results = []

    for file_name, content in files_to_review:
        # Determine file type
        detected_type = file_type
        if file_type == "auto":
            if file_name.endswith(".tf"):
                detected_type = "terraform"
            elif file_name.endswith((".yaml", ".yml")):
                # Check if it looks like Kubernetes
                if "apiVersion:" in content and "kind:" in content:
                    detected_type = "kubernetes"
                else:
                    detected_type = "terraform"  # Fallback
            else:
                detected_type = "terraform"

        # Select prompt
        if detected_type == "kubernetes":
            prompt = KUBERNETES_REVIEW_PROMPT.format(code=content[:15000])
        else:
            prompt = TERRAFORM_REVIEW_PROMPT.format(code=content[:15000])

        try:
            bedrock_runtime = ctx.aws.bedrock_runtime

            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "temperature": 0.3,
                "messages": [{"role": "user", "content": prompt}],
            }

            response = bedrock_runtime.invoke_model(
                modelId=model,
                body=json.dumps(body),
                contentType="application/json",
            )

            response_body = json.loads(response["body"].read())
            review = response_body.get("content", [{}])[0].get("text", "")

            result = {
                "file": file_name,
                "type": detected_type,
                "review": review,
            }
            all_results.append(result)

            if not output_json:
                ctx.output.print_panel(review, title=f"Review: {file_name}")

        except ClientError as e:
            all_results.append({
                "file": file_name,
                "type": detected_type,
                "error": str(e),
            })
            ctx.output.print_error(f"Failed to review {file_name}: {e}")

    if output_json:
        ctx.output.print_data(all_results)
    else:
        # Summary
        ctx.output.print_success(f"Reviewed {len(all_results)} file(s)")
