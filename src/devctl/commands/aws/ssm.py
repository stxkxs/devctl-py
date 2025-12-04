"""AWS SSM (Systems Manager) commands."""

import json
import time
from datetime import datetime
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.clients.aws import paginate


@click.group()
@pass_context
def ssm(ctx: DevCtlContext) -> None:
    """SSM operations - Parameter Store, Run Command, Session Manager.

    \b
    Examples:
        devctl aws ssm params list --path /app/
        devctl aws ssm params get /app/database/url
        devctl aws ssm run 'uptime' --targets tag:Environment=production
        devctl aws ssm instances
    """
    pass


# ============================================================================
# Parameter Store Commands
# ============================================================================


@ssm.group()
@pass_context
def params(ctx: DevCtlContext) -> None:
    """Parameter Store operations.

    \b
    Examples:
        devctl aws ssm params list --path /app/
        devctl aws ssm params get /app/database/url
        devctl aws ssm params set /app/api/key --value secret123 --type SecureString
        devctl aws ssm params delete /app/old/param
    """
    pass


@params.command("list")
@click.option("--path", default="/", help="Parameter path prefix")
@click.option("--recursive", is_flag=True, help="Include nested paths")
@click.option("--decrypt", is_flag=True, help="Decrypt SecureString values")
@click.option("--limit", type=int, default=50, help="Maximum parameters to show")
@pass_context
def list_params(
    ctx: DevCtlContext,
    path: str,
    recursive: bool,
    decrypt: bool,
    limit: int,
) -> None:
    """List SSM parameters."""
    try:
        ssm_client = ctx.aws.client("ssm")

        kwargs: dict[str, Any] = {
            "Path": path,
            "Recursive": recursive,
            "WithDecryption": decrypt,
            "MaxResults": min(limit, 10),  # API max is 10 per page
        }

        parameters = paginate(ssm_client, "get_parameters_by_path", "Parameters", **kwargs)

        if not parameters:
            ctx.output.print_info(f"No parameters found under {path}")
            return

        data = []
        for param in parameters[:limit]:
            param_type = param.get("Type", "-")

            # Mask secure values unless decrypt requested
            value = param.get("Value", "-")
            if param_type == "SecureString" and not decrypt:
                value = "********"
            elif len(value) > 40:
                value = value[:37] + "..."

            data.append({
                "Name": param.get("Name", "-"),
                "Type": param_type,
                "Value": value,
                "Version": param.get("Version", "-"),
                "Modified": param.get("LastModifiedDate", datetime.min).strftime("%Y-%m-%d"),
            })

        ctx.output.print_data(
            data,
            headers=["Name", "Type", "Value", "Version", "Modified"],
            title=f"Parameters under {path} ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list parameters: {e}")


@params.command("get")
@click.argument("name")
@click.option("--decrypt", is_flag=True, help="Decrypt SecureString value")
@click.option("--history", is_flag=True, help="Show parameter history")
@pass_context
def get_param(
    ctx: DevCtlContext,
    name: str,
    decrypt: bool,
    history: bool,
) -> None:
    """Get an SSM parameter value."""
    try:
        ssm_client = ctx.aws.client("ssm")

        if history:
            # Get parameter history
            response = ssm_client.get_parameter_history(
                Name=name,
                WithDecryption=decrypt,
                MaxResults=10,
            )

            versions = response.get("Parameters", [])

            if not versions:
                ctx.output.print_info(f"No history found for {name}")
                return

            data = []
            for v in versions:
                value = v.get("Value", "-")
                if v.get("Type") == "SecureString" and not decrypt:
                    value = "********"
                elif len(value) > 30:
                    value = value[:27] + "..."

                data.append({
                    "Version": v.get("Version", "-"),
                    "Value": value,
                    "Type": v.get("Type", "-"),
                    "Modified": v.get("LastModifiedDate", datetime.min).strftime("%Y-%m-%d %H:%M"),
                    "User": v.get("LastModifiedUser", "-").split("/")[-1][:20],
                })

            ctx.output.print_data(
                data,
                headers=["Version", "Value", "Type", "Modified", "User"],
                title=f"History: {name}",
            )

        else:
            # Get current value
            response = ssm_client.get_parameter(
                Name=name,
                WithDecryption=decrypt,
            )

            param = response.get("Parameter", {})

            value = param.get("Value", "")
            param_type = param.get("Type", "-")

            if param_type == "SecureString" and not decrypt:
                ctx.output.print_warning("Value is encrypted. Use --decrypt to show.")
                value = "********"

            info = {
                "Name": param.get("Name", "-"),
                "Type": param_type,
                "Version": param.get("Version", "-"),
                "ARN": param.get("ARN", "-"),
                "Last Modified": param.get("LastModifiedDate", datetime.min).strftime("%Y-%m-%d %H:%M:%S"),
            }

            ctx.output.print_data(info, title="Parameter Details")
            ctx.output.print(f"\nValue:\n{value}")

    except ClientError as e:
        if "ParameterNotFound" in str(e):
            raise AWSError(f"Parameter not found: {name}")
        raise AWSError(f"Failed to get parameter: {e}")


@params.command("set")
@click.argument("name")
@click.option("--value", required=True, help="Parameter value")
@click.option("--type", "param_type", type=click.Choice(["String", "StringList", "SecureString"]), default="String", help="Parameter type")
@click.option("--description", help="Parameter description")
@click.option("--overwrite", is_flag=True, help="Overwrite existing parameter")
@click.option("--tags", multiple=True, help="Tags (Key=Value)")
@pass_context
def set_param(
    ctx: DevCtlContext,
    name: str,
    value: str,
    param_type: str,
    description: str | None,
    overwrite: bool,
    tags: tuple[str, ...],
) -> None:
    """Set an SSM parameter."""
    try:
        ssm_client = ctx.aws.client("ssm")

        kwargs: dict[str, Any] = {
            "Name": name,
            "Value": value,
            "Type": param_type,
            "Overwrite": overwrite,
        }

        if description:
            kwargs["Description"] = description

        if tags:
            tag_list = []
            for tag in tags:
                if "=" in tag:
                    key, val = tag.split("=", 1)
                    tag_list.append({"Key": key, "Value": val})
            if tag_list:
                kwargs["Tags"] = tag_list

        response = ssm_client.put_parameter(**kwargs)

        version = response.get("Version", "unknown")
        ctx.output.print_success(f"Parameter {name} set successfully (version {version})")

    except ClientError as e:
        if "ParameterAlreadyExists" in str(e):
            raise AWSError(f"Parameter exists. Use --overwrite to update: {name}")
        raise AWSError(f"Failed to set parameter: {e}")


@params.command("delete")
@click.argument("name")
@click.option("--force", is_flag=True, help="Skip confirmation")
@pass_context
def delete_param(
    ctx: DevCtlContext,
    name: str,
    force: bool,
) -> None:
    """Delete an SSM parameter."""
    try:
        if not force:
            ctx.output.print_warning(f"About to delete parameter: {name}")
            if not click.confirm("Continue?"):
                ctx.output.print_info("Cancelled")
                return

        ssm_client = ctx.aws.client("ssm")
        ssm_client.delete_parameter(Name=name)
        ctx.output.print_success(f"Parameter {name} deleted")

    except ClientError as e:
        if "ParameterNotFound" in str(e):
            raise AWSError(f"Parameter not found: {name}")
        raise AWSError(f"Failed to delete parameter: {e}")


@params.command("copy")
@click.argument("source")
@click.argument("destination")
@click.option("--decrypt", is_flag=True, help="Decrypt SecureString before copying")
@click.option("--overwrite", is_flag=True, help="Overwrite if destination exists")
@pass_context
def copy_param(
    ctx: DevCtlContext,
    source: str,
    destination: str,
    decrypt: bool,
    overwrite: bool,
) -> None:
    """Copy an SSM parameter to a new name."""
    try:
        ssm_client = ctx.aws.client("ssm")

        # Get source parameter
        response = ssm_client.get_parameter(Name=source, WithDecryption=decrypt)
        param = response.get("Parameter", {})

        # Put to destination
        ssm_client.put_parameter(
            Name=destination,
            Value=param.get("Value", ""),
            Type=param.get("Type", "String"),
            Overwrite=overwrite,
        )

        ctx.output.print_success(f"Copied {source} to {destination}")

    except ClientError as e:
        raise AWSError(f"Failed to copy parameter: {e}")


# ============================================================================
# Run Command
# ============================================================================


@ssm.command("run")
@click.argument("command")
@click.option("--targets", "-t", multiple=True, required=True, help="Target instances (tag:Key=Value or i-xxx)")
@click.option("--timeout", type=int, default=600, help="Command timeout in seconds")
@click.option("--comment", help="Command comment")
@click.option("--wait/--no-wait", default=True, help="Wait for command completion")
@pass_context
def run_command(
    ctx: DevCtlContext,
    command: str,
    targets: tuple[str, ...],
    timeout: int,
    comment: str | None,
    wait: bool,
) -> None:
    """Run a shell command on EC2 instances via SSM.

    \b
    Target formats:
        tag:Environment=production    - Instances with specific tag
        i-1234567890abcdef0          - Specific instance ID

    \b
    Examples:
        devctl aws ssm run 'uptime' --targets tag:Environment=production
        devctl aws ssm run 'df -h' --targets i-1234567890abcdef0
        devctl aws ssm run 'systemctl restart nginx' --targets tag:Role=web
    """
    try:
        ssm_client = ctx.aws.client("ssm")

        # Parse targets
        target_list = []
        for target in targets:
            if target.startswith("tag:"):
                # Tag-based targeting
                tag_part = target[4:]  # Remove "tag:"
                if "=" in tag_part:
                    key, value = tag_part.split("=", 1)
                    target_list.append({
                        "Key": f"tag:{key}",
                        "Values": [value],
                    })
            elif target.startswith("i-"):
                # Instance ID
                target_list.append({
                    "Key": "InstanceIds",
                    "Values": [target],
                })
            else:
                ctx.output.print_warning(f"Unknown target format: {target}")

        if not target_list:
            raise AWSError("No valid targets specified")

        kwargs: dict[str, Any] = {
            "DocumentName": "AWS-RunShellScript",
            "Targets": target_list,
            "Parameters": {"commands": [command]},
            "TimeoutSeconds": timeout,
        }

        if comment:
            kwargs["Comment"] = comment

        ctx.output.print_info(f"Sending command to targets...")

        response = ssm_client.send_command(**kwargs)
        command_id = response["Command"]["CommandId"]

        ctx.output.print_info(f"Command ID: {command_id}")

        if not wait:
            ctx.output.print_info("Command sent. Use 'devctl aws ssm status' to check results.")
            return

        # Wait for completion
        ctx.output.print_info("Waiting for command to complete...")

        max_wait = timeout + 60  # Extra buffer
        start_time = time.time()

        while True:
            if time.time() - start_time > max_wait:
                raise AWSError("Timeout waiting for command completion")

            result = ssm_client.list_command_invocations(
                CommandId=command_id,
                Details=True,
            )

            invocations = result.get("CommandInvocations", [])

            if not invocations:
                time.sleep(5)
                continue

            # Check if all invocations are complete
            all_done = all(
                inv["Status"] in ["Success", "Failed", "Cancelled", "TimedOut"]
                for inv in invocations
            )

            if all_done:
                break

            time.sleep(5)

        # Display results
        for inv in invocations:
            instance_id = inv.get("InstanceId", "unknown")
            status = inv.get("Status", "unknown")
            status_color = {
                "Success": "[green]Success[/green]",
                "Failed": "[red]Failed[/red]",
                "TimedOut": "[yellow]TimedOut[/yellow]",
            }.get(status, status)

            ctx.output.print(f"\n[bold]{instance_id}[/bold]: {status_color}")

            # Get command output
            plugins = inv.get("CommandPlugins", [])
            for plugin in plugins:
                output = plugin.get("Output", "")
                if output:
                    ctx.output.print(output)

                stderr = plugin.get("StandardErrorContent", "")
                if stderr:
                    ctx.output.print(f"[red]STDERR:[/red]\n{stderr}")

    except ClientError as e:
        raise AWSError(f"Failed to run command: {e}")


@ssm.command("status")
@click.argument("command_id")
@pass_context
def command_status(ctx: DevCtlContext, command_id: str) -> None:
    """Get status of an SSM Run Command."""
    try:
        ssm_client = ctx.aws.client("ssm")

        result = ssm_client.list_command_invocations(
            CommandId=command_id,
            Details=True,
        )

        invocations = result.get("CommandInvocations", [])

        if not invocations:
            ctx.output.print_info("No invocations found for this command")
            return

        data = []
        for inv in invocations:
            status = inv.get("Status", "unknown")
            status_display = {
                "Success": "[green]Success[/green]",
                "Failed": "[red]Failed[/red]",
                "InProgress": "[yellow]InProgress[/yellow]",
                "Pending": "[dim]Pending[/dim]",
                "TimedOut": "[red]TimedOut[/red]",
            }.get(status, status)

            data.append({
                "Instance": inv.get("InstanceId", "-"),
                "Status": status_display,
                "Started": inv.get("RequestedDateTime", datetime.min).strftime("%H:%M:%S"),
                "Document": inv.get("DocumentName", "-"),
            })

        ctx.output.print_data(
            data,
            headers=["Instance", "Status", "Started", "Document"],
            title=f"Command {command_id}",
        )

    except ClientError as e:
        raise AWSError(f"Failed to get command status: {e}")


# ============================================================================
# Managed Instances
# ============================================================================


@ssm.command("instances")
@click.option("--filter", "filter_key", type=click.Choice(["online", "offline", "all"]), default="all", help="Filter by status")
@pass_context
def list_instances(ctx: DevCtlContext, filter_key: str) -> None:
    """List SSM managed instances."""
    try:
        ssm_client = ctx.aws.client("ssm")

        kwargs: dict[str, Any] = {}

        if filter_key == "online":
            kwargs["Filters"] = [{"Key": "PingStatus", "Values": ["Online"]}]
        elif filter_key == "offline":
            kwargs["Filters"] = [{"Key": "PingStatus", "Values": ["ConnectionLost"]}]

        instances = paginate(ssm_client, "describe_instance_information", "InstanceInformationList", **kwargs)

        if not instances:
            ctx.output.print_info("No managed instances found")
            return

        data = []
        for inst in instances:
            ping_status = inst.get("PingStatus", "unknown")
            status_display = {
                "Online": "[green]Online[/green]",
                "ConnectionLost": "[red]Offline[/red]",
                "Inactive": "[yellow]Inactive[/yellow]",
            }.get(ping_status, ping_status)

            data.append({
                "Instance ID": inst.get("InstanceId", "-"),
                "Name": inst.get("ComputerName", "-")[:20],
                "Status": status_display,
                "Platform": inst.get("PlatformName", "-")[:15],
                "Agent": inst.get("AgentVersion", "-"),
                "Last Ping": inst.get("LastPingDateTime", datetime.min).strftime("%Y-%m-%d %H:%M"),
            })

        ctx.output.print_data(
            data,
            headers=["Instance ID", "Name", "Status", "Platform", "Agent", "Last Ping"],
            title=f"SSM Managed Instances ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list instances: {e}")


@ssm.command("session")
@click.argument("instance_id")
@pass_context
def start_session(ctx: DevCtlContext, instance_id: str) -> None:
    """Start an interactive SSM session (requires AWS CLI).

    This command launches the AWS CLI session manager plugin.
    """
    import subprocess
    import shutil

    # Check if session-manager-plugin is installed
    if not shutil.which("session-manager-plugin"):
        ctx.output.print_error(
            "session-manager-plugin not found. Install it from:\n"
            "https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html"
        )
        return

    ctx.output.print_info(f"Starting session to {instance_id}...")

    # Use AWS CLI to start session
    cmd = ["aws", "ssm", "start-session", "--target", instance_id]

    # Add profile if configured
    profile = ctx.aws._config.get_profile()
    if profile:
        cmd.extend(["--profile", profile])

    # Add region if configured
    region = ctx.aws._config.get_region()
    if region:
        cmd.extend(["--region", region])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise AWSError(f"Failed to start session: {e}")
    except FileNotFoundError:
        raise AWSError("AWS CLI not found. Please install and configure the AWS CLI.")
