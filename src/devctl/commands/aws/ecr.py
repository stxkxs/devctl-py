"""ECR commands for AWS."""

import base64
import subprocess
from datetime import datetime, timezone
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.core.output import format_bytes
from devctl.clients.aws import paginate


@click.group()
@pass_context
def ecr(ctx: DevCtlContext) -> None:
    """ECR operations - container registry management.

    \b
    Examples:
        devctl aws ecr list-repos
        devctl aws ecr list-images my-repo
        devctl aws ecr login
        devctl aws ecr cleanup my-repo --keep 10
    """
    pass


@ecr.command("list-repos")
@click.option("--filter", "name_filter", help="Filter repositories by name pattern")
@pass_context
def list_repos(ctx: DevCtlContext, name_filter: str | None) -> None:
    """List ECR repositories."""
    try:
        ecr_client = ctx.aws.ecr
        repos = paginate(ecr_client, "describe_repositories", "repositories")

        if name_filter:
            repos = [r for r in repos if name_filter.lower() in r["repositoryName"].lower()]

        data = []
        for repo in repos:
            data.append({
                "Name": repo["repositoryName"],
                "URI": repo["repositoryUri"],
                "Created": repo["createdAt"].strftime("%Y-%m-%d"),
                "ScanOnPush": "Yes" if repo.get("imageScanningConfiguration", {}).get("scanOnPush") else "No",
            })

        ctx.output.print_data(
            data,
            headers=["Name", "URI", "Created", "ScanOnPush"],
            title=f"ECR Repositories ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list repositories: {e}")


@ecr.command("list-images")
@click.argument("repository")
@click.option(
    "--tag-status",
    type=click.Choice(["tagged", "untagged", "all"]),
    default="all",
    help="Filter by tag status",
)
@click.option("--max-results", type=int, default=100, help="Maximum images to return")
@pass_context
def list_images(
    ctx: DevCtlContext,
    repository: str,
    tag_status: str,
    max_results: int,
) -> None:
    """List images in an ECR repository."""
    try:
        ecr_client = ctx.aws.ecr

        kwargs: dict[str, Any] = {"repositoryName": repository, "maxResults": max_results}
        if tag_status == "tagged":
            kwargs["filter"] = {"tagStatus": "TAGGED"}
        elif tag_status == "untagged":
            kwargs["filter"] = {"tagStatus": "UNTAGGED"}

        images = paginate(ecr_client, "describe_images", "imageDetails", **kwargs)

        # Sort by push date, newest first
        images.sort(key=lambda x: x.get("imagePushedAt", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

        data = []
        for img in images[:max_results]:
            tags = img.get("imageTags", [])
            tag_display = ", ".join(tags[:3])
            if len(tags) > 3:
                tag_display += f" (+{len(tags) - 3})"

            scan_status = img.get("imageScanStatus", {}).get("status", "-")
            findings = img.get("imageScanFindingsSummary", {}).get("findingSeverityCounts", {})
            vuln_summary = ""
            if findings:
                vuln_summary = ", ".join(f"{k}:{v}" for k, v in findings.items())

            data.append({
                "Tags": tag_display or "(untagged)",
                "Digest": img["imageDigest"][:19] + "...",
                "Size": format_bytes(img.get("imageSizeInBytes", 0)),
                "Pushed": img.get("imagePushedAt", "").strftime("%Y-%m-%d %H:%M") if img.get("imagePushedAt") else "-",
                "ScanStatus": scan_status,
                "Vulnerabilities": vuln_summary or "-",
            })

        ctx.output.print_data(
            data,
            headers=["Tags", "Digest", "Size", "Pushed", "ScanStatus", "Vulnerabilities"],
            title=f"Images in {repository} ({len(data)} shown)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list images: {e}")


@ecr.command()
@click.option("--region", help="AWS region for login")
@pass_context
def login(ctx: DevCtlContext, region: str | None) -> None:
    """Authenticate Docker to ECR.

    Gets an authorization token and configures Docker to use it.
    """
    if ctx.dry_run:
        ctx.log_dry_run("ECR login", {"region": region or ctx.aws.region})
        return

    try:
        ecr_client = ctx.aws.ecr

        response = ecr_client.get_authorization_token()
        auth_data = response["authorizationData"][0]

        token = base64.b64decode(auth_data["authorizationToken"]).decode()
        username, password = token.split(":")
        endpoint = auth_data["proxyEndpoint"]

        # Run docker login
        cmd = ["docker", "login", "--username", username, "--password-stdin", endpoint]

        result = subprocess.run(
            cmd,
            input=password.encode(),
            capture_output=True,
        )

        if result.returncode != 0:
            raise AWSError(f"Docker login failed: {result.stderr.decode()}")

        ctx.output.print_success(f"Successfully logged in to {endpoint}")

    except ClientError as e:
        raise AWSError(f"Failed to get ECR token: {e}")
    except FileNotFoundError:
        raise AWSError("Docker not found. Please install Docker for ECR operations.")


@ecr.command()
@click.argument("repository")
@click.option("--tag", "-t", default="latest", help="Image tag")
@click.option("--dockerfile", "-f", default="Dockerfile", help="Dockerfile path")
@click.option("--push", is_flag=True, help="Push image after building")
@click.option("--build-arg", multiple=True, help="Build arguments (KEY=VALUE)")
@pass_context
def build(
    ctx: DevCtlContext,
    repository: str,
    tag: str,
    dockerfile: str,
    push: bool,
    build_arg: tuple[str, ...],
) -> None:
    """Build and optionally push a Docker image to ECR."""
    try:
        ecr_client = ctx.aws.ecr

        # Get repository URI
        repos = ecr_client.describe_repositories(repositoryNames=[repository])
        repo_uri = repos["repositories"][0]["repositoryUri"]
        image_uri = f"{repo_uri}:{tag}"

        if ctx.dry_run:
            ctx.log_dry_run("build image", {"uri": image_uri, "dockerfile": dockerfile})
            if push:
                ctx.log_dry_run("push image", {"uri": image_uri})
            return

        # Build image
        cmd = ["docker", "build", "-t", image_uri, "-f", dockerfile]
        for arg in build_arg:
            cmd.extend(["--build-arg", arg])
        cmd.append(".")

        ctx.output.print_info(f"Building {image_uri}...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise AWSError(f"Build failed: {result.stderr}")

        ctx.output.print_success(f"Built {image_uri}")

        if push:
            # Push image
            ctx.output.print_info(f"Pushing {image_uri}...")
            result = subprocess.run(["docker", "push", image_uri], capture_output=True, text=True)

            if result.returncode != 0:
                raise AWSError(f"Push failed: {result.stderr}")

            ctx.output.print_success(f"Pushed {image_uri}")

    except ClientError as e:
        raise AWSError(f"ECR operation failed: {e}")
    except FileNotFoundError:
        raise AWSError("Docker not found. Please install Docker for build operations.")


@ecr.command()
@click.argument("repository_tag")
@click.option("--wait", is_flag=True, help="Wait for scan to complete")
@pass_context
def scan(ctx: DevCtlContext, repository_tag: str, wait: bool) -> None:
    """Start or check vulnerability scan for an image.

    REPOSITORY_TAG should be in format: repository:tag
    """
    try:
        if ":" in repository_tag:
            repository, tag = repository_tag.split(":", 1)
        else:
            repository = repository_tag
            tag = "latest"

        ecr_client = ctx.aws.ecr

        if ctx.dry_run:
            ctx.log_dry_run("scan image", {"repository": repository, "tag": tag})
            return

        # Start scan
        ecr_client.start_image_scan(
            repositoryName=repository,
            imageId={"imageTag": tag},
        )
        ctx.output.print_info(f"Scan started for {repository}:{tag}")

        if wait:
            import time

            ctx.output.print_info("Waiting for scan to complete...")

            for _ in range(60):  # Max 10 minutes
                response = ecr_client.describe_image_scan_findings(
                    repositoryName=repository,
                    imageId={"imageTag": tag},
                )

                status = response["imageScanStatus"]["status"]
                if status == "COMPLETE":
                    findings = response.get("imageScanFindings", {})
                    summary = findings.get("findingSeverityCounts", {})

                    if summary:
                        data = [{"Severity": k, "Count": v} for k, v in summary.items()]
                        ctx.output.print_data(data, title="Scan Results")
                    else:
                        ctx.output.print_success("No vulnerabilities found")
                    return
                elif status == "FAILED":
                    raise AWSError(f"Scan failed: {response['imageScanStatus'].get('description')}")

                time.sleep(10)

            ctx.output.print_warning("Scan still in progress after timeout")

    except ClientError as e:
        raise AWSError(f"Scan operation failed: {e}")


@ecr.command()
@click.argument("repository")
@click.option("--keep", type=int, default=10, help="Number of recent images to keep")
@click.option("--untagged-only", is_flag=True, help="Only remove untagged images")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@pass_context
def cleanup(
    ctx: DevCtlContext,
    repository: str,
    keep: int,
    untagged_only: bool,
    yes: bool,
) -> None:
    """Clean up old images from a repository.

    Removes images older than the most recent N images (specified by --keep).
    """
    try:
        ecr_client = ctx.aws.ecr

        # Get all images
        kwargs: dict[str, Any] = {"repositoryName": repository}
        if untagged_only:
            kwargs["filter"] = {"tagStatus": "UNTAGGED"}

        images = paginate(ecr_client, "describe_images", "imageDetails", **kwargs)

        # Sort by push date, newest first
        images.sort(key=lambda x: x.get("imagePushedAt", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

        # Identify images to delete
        to_delete = images[keep:] if not untagged_only else images

        if not to_delete:
            ctx.output.print_success("No images to clean up")
            return

        ctx.output.print_info(f"Found {len(to_delete)} images to delete")

        if ctx.dry_run:
            for img in to_delete[:10]:
                tags = img.get("imageTags", ["(untagged)"])
                ctx.output.print(f"  Would delete: {', '.join(tags)}")
            if len(to_delete) > 10:
                ctx.output.print(f"  ... and {len(to_delete) - 10} more")
            return

        if not yes:
            if not ctx.confirm(f"Delete {len(to_delete)} images from {repository}?"):
                ctx.output.print_info("Cancelled")
                return

        # Delete in batches of 100
        deleted = 0
        for i in range(0, len(to_delete), 100):
            batch = to_delete[i : i + 100]
            image_ids = [{"imageDigest": img["imageDigest"]} for img in batch]

            response = ecr_client.batch_delete_image(
                repositoryName=repository,
                imageIds=image_ids,
            )

            deleted += len(response.get("imageIds", []))
            failures = response.get("failures", [])
            if failures:
                ctx.output.print_warning(f"{len(failures)} images failed to delete")

        ctx.output.print_success(f"Deleted {deleted} images from {repository}")

    except ClientError as e:
        raise AWSError(f"Cleanup failed: {e}")


@ecr.command("lifecycle-policy")
@click.argument("repository")
@click.option("--get", "get_policy", is_flag=True, help="Get current lifecycle policy")
@click.option("--set", "set_policy", type=click.Path(exists=True), help="Set lifecycle policy from file")
@pass_context
def lifecycle_policy(ctx: DevCtlContext, repository: str, get_policy: bool, set_policy: str | None) -> None:
    """Get or set ECR lifecycle policy."""
    try:
        ecr_client = ctx.aws.ecr

        if set_policy:
            if ctx.dry_run:
                ctx.log_dry_run("set lifecycle policy", {"repository": repository, "file": set_policy})
                return

            with open(set_policy) as f:
                policy_text = f.read()

            ecr_client.put_lifecycle_policy(
                repositoryName=repository,
                lifecyclePolicyText=policy_text,
            )
            ctx.output.print_success(f"Lifecycle policy set for {repository}")

        else:
            try:
                response = ecr_client.get_lifecycle_policy(repositoryName=repository)
                import json

                policy = json.loads(response["lifecyclePolicyText"])
                rules = policy.get("rules", [])

                data = []
                for rule in rules:
                    data.append({
                        "Priority": rule.get("rulePriority", "-"),
                        "Description": rule.get("description", "-"),
                        "Selection": rule.get("selection", {}).get("tagStatus", "-"),
                        "Action": rule.get("action", {}).get("type", "-"),
                    })

                ctx.output.print_data(
                    data,
                    headers=["Priority", "Description", "Selection", "Action"],
                    title=f"Lifecycle Policy for {repository}",
                )

                if ctx.verbose >= 2:
                    ctx.output.print_code(json.dumps(policy, indent=2), "json")

            except ClientError as e:
                if "LifecyclePolicyNotFoundException" in str(e):
                    ctx.output.print_info(f"No lifecycle policy configured for {repository}")
                else:
                    raise

    except ClientError as e:
        raise AWSError(f"Lifecycle policy operation failed: {e}")
