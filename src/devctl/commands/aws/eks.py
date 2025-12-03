"""EKS commands for AWS."""

import base64
import subprocess
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.clients.aws import paginate


@click.group()
@pass_context
def eks(ctx: DevCtlContext) -> None:
    """EKS operations - Kubernetes cluster management.

    \b
    Examples:
        devctl aws eks list-clusters
        devctl aws eks describe my-cluster
        devctl aws eks kubeconfig my-cluster
        devctl aws eks nodegroups my-cluster --list
    """
    pass


@eks.command("list-clusters")
@click.option("--region", help="AWS region (default: configured region)")
@pass_context
def list_clusters(ctx: DevCtlContext, region: str | None) -> None:
    """List EKS clusters."""
    try:
        eks_client = ctx.aws.client("eks", region_name=region) if region else ctx.aws.eks

        clusters = paginate(eks_client, "list_clusters", "clusters")

        if not clusters:
            ctx.output.print_info("No EKS clusters found")
            return

        data = []
        for cluster_name in clusters:
            try:
                cluster = eks_client.describe_cluster(name=cluster_name)["cluster"]
                data.append({
                    "Name": cluster["name"],
                    "Status": cluster["status"],
                    "Version": cluster["version"],
                    "Endpoint": cluster["endpoint"][:50] + "..." if len(cluster.get("endpoint", "")) > 50 else cluster.get("endpoint", "-"),
                    "Created": cluster["createdAt"].strftime("%Y-%m-%d"),
                })
            except ClientError:
                data.append({
                    "Name": cluster_name,
                    "Status": "Unknown",
                    "Version": "-",
                    "Endpoint": "-",
                    "Created": "-",
                })

        ctx.output.print_data(
            data,
            headers=["Name", "Status", "Version", "Endpoint", "Created"],
            title=f"EKS Clusters ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list clusters: {e}")


@eks.command()
@click.argument("cluster")
@pass_context
def describe(ctx: DevCtlContext, cluster: str) -> None:
    """Describe an EKS cluster."""
    try:
        eks_client = ctx.aws.eks
        response = eks_client.describe_cluster(name=cluster)
        cluster_data = response["cluster"]

        # Basic info
        data = {
            "Name": cluster_data["name"],
            "ARN": cluster_data["arn"],
            "Status": cluster_data["status"],
            "Version": cluster_data["version"],
            "Endpoint": cluster_data.get("endpoint", "-"),
            "RoleARN": cluster_data["roleArn"],
            "Created": cluster_data["createdAt"].strftime("%Y-%m-%d %H:%M"),
            "PlatformVersion": cluster_data.get("platformVersion", "-"),
        }

        ctx.output.print_data(data, title=f"Cluster: {cluster}")

        # VPC Config
        vpc_config = cluster_data.get("resourcesVpcConfig", {})
        if vpc_config:
            vpc_data = {
                "VPC ID": vpc_config.get("vpcId", "-"),
                "Subnets": ", ".join(vpc_config.get("subnetIds", [])[:3]),
                "Security Groups": ", ".join(vpc_config.get("securityGroupIds", [])[:3]),
                "Public Access": "Yes" if vpc_config.get("endpointPublicAccess") else "No",
                "Private Access": "Yes" if vpc_config.get("endpointPrivateAccess") else "No",
            }
            ctx.output.print_data(vpc_data, title="VPC Configuration")

        # Logging
        logging_config = cluster_data.get("logging", {})
        enabled_logs = []
        for log_setup in logging_config.get("clusterLogging", []):
            if log_setup.get("enabled"):
                enabled_logs.extend(log_setup.get("types", []))

        if enabled_logs:
            ctx.output.print_info(f"Enabled logs: {', '.join(enabled_logs)}")

    except ClientError as e:
        raise AWSError(f"Failed to describe cluster: {e}")


@eks.command()
@click.argument("cluster")
@click.option("--alias", help="Alias for the context (default: cluster name)")
@click.option("--role-arn", help="IAM role ARN to assume for authentication")
@click.option("--dry-run", is_flag=True, help="Show command without executing")
@pass_context
def kubeconfig(ctx: DevCtlContext, cluster: str, alias: str | None, role_arn: str | None, dry_run: bool) -> None:
    """Update kubeconfig for an EKS cluster.

    Configures kubectl to connect to the specified cluster.
    """
    cmd = ["aws", "eks", "update-kubeconfig", "--name", cluster]

    if alias:
        cmd.extend(["--alias", alias])
    if role_arn:
        cmd.extend(["--role-arn", role_arn])

    profile = ctx.profile.aws.get_profile()
    region = ctx.profile.aws.get_region()
    if profile:
        cmd.extend(["--profile", profile])
    if region:
        cmd.extend(["--region", region])

    if dry_run or ctx.dry_run:
        ctx.output.print_info(f"Would run: {' '.join(cmd)}")
        return

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise AWSError(f"Failed to update kubeconfig: {result.stderr}")

        ctx.output.print_success(f"Kubeconfig updated for cluster {cluster}")
        if result.stdout:
            ctx.output.print(result.stdout)

    except FileNotFoundError:
        raise AWSError("AWS CLI not found. Please install it for kubeconfig operations.")


@eks.command()
@click.argument("cluster")
@click.option("--list", "list_nodegroups", is_flag=True, help="List node groups")
@click.option("--scale", help="Node group name to scale")
@click.option("--count", type=int, help="Desired node count (use with --scale)")
@click.option("--min", "min_size", type=int, help="Minimum nodes (use with --scale)")
@click.option("--max", "max_size", type=int, help="Maximum nodes (use with --scale)")
@pass_context
def nodegroups(
    ctx: DevCtlContext,
    cluster: str,
    list_nodegroups: bool,
    scale: str | None,
    count: int | None,
    min_size: int | None,
    max_size: int | None,
) -> None:
    """List or scale EKS node groups."""
    try:
        eks_client = ctx.aws.eks

        if scale:
            # Scale operation
            if count is None:
                raise click.BadParameter("--count is required when using --scale")

            if ctx.dry_run:
                ctx.log_dry_run("scale nodegroup", {
                    "cluster": cluster,
                    "nodegroup": scale,
                    "desired": count,
                })
                return

            scaling_config: dict[str, Any] = {"desiredSize": count}
            if min_size is not None:
                scaling_config["minSize"] = min_size
            if max_size is not None:
                scaling_config["maxSize"] = max_size

            eks_client.update_nodegroup_config(
                clusterName=cluster,
                nodegroupName=scale,
                scalingConfig=scaling_config,
            )

            ctx.output.print_success(f"Scaling {scale} to {count} nodes")

        else:
            # List node groups
            nodegroup_names = paginate(
                eks_client,
                "list_nodegroups",
                "nodegroups",
                clusterName=cluster,
            )

            if not nodegroup_names:
                ctx.output.print_info(f"No node groups found in cluster {cluster}")
                return

            data = []
            for ng_name in nodegroup_names:
                ng = eks_client.describe_nodegroup(
                    clusterName=cluster,
                    nodegroupName=ng_name,
                )["nodegroup"]

                scaling = ng.get("scalingConfig", {})
                data.append({
                    "Name": ng["nodegroupName"],
                    "Status": ng["status"],
                    "InstanceTypes": ", ".join(ng.get("instanceTypes", ["-"])),
                    "Desired": scaling.get("desiredSize", "-"),
                    "Min": scaling.get("minSize", "-"),
                    "Max": scaling.get("maxSize", "-"),
                    "AMI": ng.get("amiType", "-"),
                })

            ctx.output.print_data(
                data,
                headers=["Name", "Status", "InstanceTypes", "Desired", "Min", "Max", "AMI"],
                title=f"Node Groups in {cluster}",
            )

    except ClientError as e:
        raise AWSError(f"Node group operation failed: {e}")


@eks.command()
@click.argument("cluster")
@click.option("--list", "list_addons", is_flag=True, help="List installed addons")
@click.option("--install", help="Addon name to install")
@click.option("--update", help="Addon name to update")
@click.option("--version", "addon_version", help="Addon version (use with --install or --update)")
@pass_context
def addons(
    ctx: DevCtlContext,
    cluster: str,
    list_addons: bool,
    install: str | None,
    update: str | None,
    addon_version: str | None,
) -> None:
    """List, install, or update EKS addons."""
    try:
        eks_client = ctx.aws.eks

        if install:
            if ctx.dry_run:
                ctx.log_dry_run("install addon", {
                    "cluster": cluster,
                    "addon": install,
                    "version": addon_version,
                })
                return

            kwargs: dict[str, Any] = {
                "clusterName": cluster,
                "addonName": install,
            }
            if addon_version:
                kwargs["addonVersion"] = addon_version

            eks_client.create_addon(**kwargs)
            ctx.output.print_success(f"Installing addon {install}")

        elif update:
            if ctx.dry_run:
                ctx.log_dry_run("update addon", {
                    "cluster": cluster,
                    "addon": update,
                    "version": addon_version,
                })
                return

            kwargs = {
                "clusterName": cluster,
                "addonName": update,
            }
            if addon_version:
                kwargs["addonVersion"] = addon_version

            eks_client.update_addon(**kwargs)
            ctx.output.print_success(f"Updating addon {update}")

        else:
            # List addons
            addon_names = paginate(
                eks_client,
                "list_addons",
                "addons",
                clusterName=cluster,
            )

            if not addon_names:
                ctx.output.print_info(f"No addons installed in cluster {cluster}")
                return

            data = []
            for addon_name in addon_names:
                addon = eks_client.describe_addon(
                    clusterName=cluster,
                    addonName=addon_name,
                )["addon"]

                data.append({
                    "Name": addon["addonName"],
                    "Version": addon["addonVersion"],
                    "Status": addon["status"],
                    "ServiceAccount": addon.get("serviceAccountRoleArn", "-")[:40] + "..." if addon.get("serviceAccountRoleArn") else "-",
                })

            ctx.output.print_data(
                data,
                headers=["Name", "Version", "Status", "ServiceAccount"],
                title=f"Addons in {cluster}",
            )

    except ClientError as e:
        raise AWSError(f"Addon operation failed: {e}")


@eks.command()
@click.argument("cluster")
@click.option("--type", "log_type", type=click.Choice(["api", "audit", "authenticator", "controllerManager", "scheduler"]), default="api", help="Log type")
@pass_context
def logs(ctx: DevCtlContext, cluster: str, log_type: str) -> None:
    """View EKS control plane logs.

    Note: Logs must be enabled for the cluster first.
    """
    try:
        logs_client = ctx.aws.logs

        log_group = f"/aws/eks/{cluster}/cluster"

        # List log streams
        streams = logs_client.describe_log_streams(
            logGroupName=log_group,
            logStreamNamePrefix=log_type,
            orderBy="LastEventTime",
            descending=True,
            limit=5,
        )["logStreams"]

        if not streams:
            ctx.output.print_warning(f"No {log_type} logs found. Ensure logging is enabled for the cluster.")
            return

        # Get recent logs from most recent stream
        stream = streams[0]
        events = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=stream["logStreamName"],
            limit=50,
            startFromHead=False,
        )["events"]

        for event in events:
            timestamp = event["timestamp"]
            from datetime import datetime
            dt = datetime.fromtimestamp(timestamp / 1000)
            ctx.output.print(f"[dim]{dt.strftime('%H:%M:%S')}[/dim] {event['message']}")

    except ClientError as e:
        if "ResourceNotFoundException" in str(e):
            ctx.output.print_warning(f"Log group not found. Ensure logging is enabled for cluster {cluster}.")
        else:
            raise AWSError(f"Failed to get logs: {e}")


@eks.command("upgrade-check")
@click.argument("cluster")
@pass_context
def upgrade_check(ctx: DevCtlContext, cluster: str) -> None:
    """Check cluster upgrade compatibility."""
    try:
        eks_client = ctx.aws.eks

        cluster_data = eks_client.describe_cluster(name=cluster)["cluster"]
        current_version = cluster_data["version"]

        ctx.output.print_info(f"Current version: {current_version}")

        # Get available versions
        # Note: This is a simplified check - actual upgrade paths may vary
        version_parts = current_version.split(".")
        major, minor = int(version_parts[0]), int(version_parts[1])
        next_version = f"{major}.{minor + 1}"

        ctx.output.print_info(f"Next available version: {next_version}")

        # Check node group versions
        nodegroup_names = paginate(
            eks_client,
            "list_nodegroups",
            "nodegroups",
            clusterName=cluster,
        )

        issues = []
        for ng_name in nodegroup_names:
            ng = eks_client.describe_nodegroup(
                clusterName=cluster,
                nodegroupName=ng_name,
            )["nodegroup"]

            ng_version = ng.get("version", current_version)
            if ng_version != current_version:
                issues.append(f"Node group {ng_name} is on version {ng_version}")

        # Check addons
        addon_names = paginate(
            eks_client,
            "list_addons",
            "addons",
            clusterName=cluster,
        )

        for addon_name in addon_names:
            addon = eks_client.describe_addon(
                clusterName=cluster,
                addonName=addon_name,
            )["addon"]

            if addon["status"] not in ["ACTIVE", "READY"]:
                issues.append(f"Addon {addon_name} is in {addon['status']} state")

        if issues:
            ctx.output.print_warning("Issues found:")
            for issue in issues:
                ctx.output.print(f"  - {issue}")
        else:
            ctx.output.print_success("No compatibility issues found")

    except ClientError as e:
        raise AWSError(f"Upgrade check failed: {e}")
