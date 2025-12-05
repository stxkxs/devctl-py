"""AWS resource tagging and cost allocation commands."""

from datetime import datetime, timedelta
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.core.output import format_cost


@click.group()
@pass_context
def tagging(ctx: DevCtlContext) -> None:
    """Resource tagging and cost allocation.

    \b
    Examples:
        devctl aws tagging audit --required-tags team,project
        devctl aws tagging report
        devctl aws tagging untagged
    """
    pass


@tagging.command()
@click.option(
    "--required-tags",
    "-r",
    multiple=True,
    help="Required tag keys (can specify multiple)",
)
@click.option(
    "--resource-types",
    "-t",
    multiple=True,
    default=["ec2:instance", "rds:db", "s3:bucket"],
    help="Resource types to audit",
)
@pass_context
def audit(
    ctx: DevCtlContext,
    required_tags: tuple[str, ...],
    resource_types: tuple[str, ...],
) -> None:
    """Audit resources for required tags."""
    if not required_tags:
        required_tags = ("team", "project", "environment")
        ctx.output.print_info(f"Using default required tags: {', '.join(required_tags)}")

    try:
        tagging_client = ctx.aws.client("resourcegroupstaggingapi")

        # Get all resources of specified types
        paginator = tagging_client.get_paginator("get_resources")

        all_resources = []
        for resource_type in resource_types:
            for page in paginator.paginate(ResourceTypeFilters=[resource_type]):
                all_resources.extend(page.get("ResourceTagMappingList", []))

        if not all_resources:
            ctx.output.print_info("No resources found matching the specified types")
            return

        # Check for missing tags
        non_compliant = []
        for resource in all_resources:
            arn = resource["ResourceARN"]
            tags = {t["Key"]: t["Value"] for t in resource.get("Tags", [])}
            missing = [tag for tag in required_tags if tag not in tags]

            if missing:
                # Extract resource type and name from ARN
                parts = arn.split(":")
                resource_type = parts[2] if len(parts) > 2 else "unknown"
                resource_id = arn.split("/")[-1] if "/" in arn else arn.split(":")[-1]

                non_compliant.append({
                    "Resource": resource_id[:30],
                    "Type": resource_type,
                    "MissingTags": ", ".join(missing),
                    "TagCount": len(tags),
                })

        if non_compliant:
            ctx.output.print_data(
                non_compliant,
                headers=["Resource", "Type", "MissingTags", "TagCount"],
                title=f"Non-Compliant Resources ({len(non_compliant)} of {len(all_resources)})",
            )

            compliance_rate = ((len(all_resources) - len(non_compliant)) / len(all_resources)) * 100
            ctx.output.print_warning(f"Tag compliance rate: {compliance_rate:.1f}%")
        else:
            ctx.output.print_success(f"All {len(all_resources)} resources are compliant with required tags")

    except ClientError as e:
        raise AWSError(f"Failed to audit tags: {e}")


@tagging.command()
@pass_context
def report(ctx: DevCtlContext) -> None:
    """Generate tag usage report."""
    try:
        tagging_client = ctx.aws.client("resourcegroupstaggingapi")

        # Get tag keys
        response = tagging_client.get_tag_keys()
        tag_keys = response.get("TagKeys", [])

        if not tag_keys:
            ctx.output.print_info("No tags found in the account")
            return

        # Count resources per tag key
        tag_stats: dict[str, int] = {}
        for key in tag_keys:
            try:
                paginator = tagging_client.get_paginator("get_resources")
                count = 0
                for page in paginator.paginate(TagFilters=[{"Key": key}]):
                    count += len(page.get("ResourceTagMappingList", []))
                tag_stats[key] = count
            except ClientError:
                tag_stats[key] = 0

        # Sort by usage
        sorted_tags = sorted(tag_stats.items(), key=lambda x: -x[1])

        data = []
        for key, count in sorted_tags[:30]:
            data.append({
                "TagKey": key,
                "ResourceCount": count,
                "Status": "Active" if count > 0 else "Unused",
            })

        ctx.output.print_data(
            data,
            headers=["TagKey", "ResourceCount", "Status"],
            title=f"Tag Usage Report ({len(tag_keys)} unique tags)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to generate tag report: {e}")


@tagging.command()
@click.option(
    "--resource-types",
    "-t",
    multiple=True,
    default=["ec2:instance", "rds:db"],
    help="Resource types to check",
)
@pass_context
def untagged(ctx: DevCtlContext, resource_types: tuple[str, ...]) -> None:
    """Find resources with no tags."""
    try:
        tagging_client = ctx.aws.client("resourcegroupstaggingapi")
        paginator = tagging_client.get_paginator("get_resources")

        untagged_resources = []

        for resource_type in resource_types:
            for page in paginator.paginate(ResourceTypeFilters=[resource_type]):
                for resource in page.get("ResourceTagMappingList", []):
                    tags = resource.get("Tags", [])
                    if not tags:
                        arn = resource["ResourceARN"]
                        parts = arn.split(":")
                        service = parts[2] if len(parts) > 2 else "unknown"
                        resource_id = arn.split("/")[-1] if "/" in arn else arn.split(":")[-1]

                        untagged_resources.append({
                            "Resource": resource_id[:35],
                            "Service": service,
                            "ARN": arn[:60],
                        })

        if untagged_resources:
            ctx.output.print_data(
                untagged_resources,
                headers=["Resource", "Service", "ARN"],
                title=f"Untagged Resources ({len(untagged_resources)} found)",
            )
            ctx.output.print_warning("Consider adding tags for cost allocation and management")
        else:
            ctx.output.print_success("All resources have at least one tag")

    except ClientError as e:
        raise AWSError(f"Failed to find untagged resources: {e}")


# Add to cost.py group - cost by tag command
def get_date_range(days: int) -> tuple[str, str]:
    """Get date range for cost queries."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@click.command("by-tag")
@click.option("--tag-key", "-k", required=True, help="Tag key to group costs by")
@click.option("--days", type=int, default=30, help="Number of days to analyze")
@click.option("--top", type=int, default=10, help="Show top N values")
@pass_context
def by_tag(ctx: DevCtlContext, tag_key: str, days: int, top: int) -> None:
    """Show costs grouped by tag value."""
    try:
        ce = ctx.aws.ce
        start_date, end_date = get_date_range(days)

        response = ce.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "TAG", "Key": tag_key}],
        )

        # Aggregate costs by tag value
        tag_costs: dict[str, float] = {}
        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                tag_value = group["Keys"][0].replace(f"{tag_key}$", "") or "(untagged)"
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                tag_costs[tag_value] = tag_costs.get(tag_value, 0) + amount

        if not tag_costs:
            ctx.output.print_info(f"No cost data found for tag '{tag_key}'")
            return

        # Sort by cost
        sorted_values = sorted(tag_costs.items(), key=lambda x: -x[1])[:top]
        total = sum(c for _, c in sorted_values)

        data = []
        for value, amount in sorted_values:
            pct = (amount / total * 100) if total > 0 else 0
            data.append({
                f"{tag_key}": value[:40],
                "Cost": format_cost(amount, "USD"),
                "Percentage": f"{pct:.1f}%",
            })

        ctx.output.print_data(
            data,
            headers=[tag_key, "Cost", "Percentage"],
            title=f"Costs by {tag_key} ({days} days)",
        )

        ctx.output.print_info(f"Total: {format_cost(total, 'USD')}")

    except ClientError as e:
        raise AWSError(f"Failed to get costs by tag: {e}")


@click.command("by-team")
@click.option("--days", type=int, default=30, help="Number of days to analyze")
@click.option("--tag-key", default="team", help="Tag key for team (default: team)")
@pass_context
def by_team(ctx: DevCtlContext, days: int, tag_key: str) -> None:
    """Show costs grouped by team tag."""
    # Delegate to by_tag
    ctx.invoke(by_tag, tag_key=tag_key, days=days, top=20)


@click.command("by-project")
@click.option("--days", type=int, default=30, help="Number of days to analyze")
@click.option("--tag-key", default="project", help="Tag key for project (default: project)")
@pass_context
def by_project(ctx: DevCtlContext, days: int, tag_key: str) -> None:
    """Show costs grouped by project tag."""
    ctx.invoke(by_tag, tag_key=tag_key, days=days, top=20)
