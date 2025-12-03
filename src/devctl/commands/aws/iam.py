"""IAM commands for AWS."""

import json
from datetime import datetime, timezone
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.clients.aws import paginate


@click.group()
@pass_context
def iam(ctx: DevCtlContext) -> None:
    """IAM operations - users, roles, policies, identity.

    \b
    Examples:
        devctl aws iam whoami
        devctl aws iam list-users
        devctl aws iam list-roles --prefix AWSServiceRole
        devctl aws iam assume arn:aws:iam::123456789012:role/MyRole
    """
    pass


@iam.command()
@pass_context
def whoami(ctx: DevCtlContext) -> None:
    """Show current IAM identity."""
    try:
        sts = ctx.aws.client("sts")
        identity = sts.get_caller_identity()

        data = {
            "Account": identity["Account"],
            "UserId": identity["UserId"],
            "Arn": identity["Arn"],
        }

        # Try to get more details if it's a user
        if ":user/" in identity["Arn"]:
            try:
                iam_client = ctx.aws.iam
                user_name = identity["Arn"].split("/")[-1]
                user = iam_client.get_user(UserName=user_name)["User"]
                data["UserName"] = user["UserName"]
                data["CreateDate"] = user["CreateDate"].isoformat()
            except ClientError:
                pass

        ctx.output.print_data(data, title="Current Identity")

    except ClientError as e:
        raise AWSError(f"Failed to get identity: {e}")


@iam.command("list-users")
@click.option("--path", default="/", help="IAM path prefix filter")
@click.option("--max-items", type=int, help="Maximum number of users to return")
@pass_context
def list_users(ctx: DevCtlContext, path: str, max_items: int | None) -> None:
    """List IAM users."""
    try:
        iam_client = ctx.aws.iam
        kwargs: dict[str, Any] = {"PathPrefix": path}
        if max_items:
            kwargs["MaxItems"] = max_items

        users = paginate(iam_client, "list_users", "Users", **kwargs)

        data = []
        for user in users:
            data.append({
                "UserName": user["UserName"],
                "UserId": user["UserId"],
                "Path": user["Path"],
                "CreateDate": user["CreateDate"].strftime("%Y-%m-%d"),
                "PasswordLastUsed": (
                    user.get("PasswordLastUsed", "").strftime("%Y-%m-%d")
                    if user.get("PasswordLastUsed")
                    else "Never"
                ),
            })

        ctx.output.print_data(
            data,
            headers=["UserName", "UserId", "Path", "CreateDate", "PasswordLastUsed"],
            title=f"IAM Users ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list users: {e}")


@iam.command("list-roles")
@click.option("--path", default="/", help="IAM path prefix filter")
@click.option("--prefix", help="Filter roles by name prefix")
@click.option("--max-items", type=int, help="Maximum number of roles to return")
@pass_context
def list_roles(ctx: DevCtlContext, path: str, prefix: str | None, max_items: int | None) -> None:
    """List IAM roles."""
    try:
        iam_client = ctx.aws.iam
        kwargs: dict[str, Any] = {"PathPrefix": path}
        if max_items:
            kwargs["MaxItems"] = max_items

        roles = paginate(iam_client, "list_roles", "Roles", **kwargs)

        # Filter by prefix if specified
        if prefix:
            roles = [r for r in roles if r["RoleName"].startswith(prefix)]

        data = []
        for role in roles:
            data.append({
                "RoleName": role["RoleName"],
                "RoleId": role["RoleId"],
                "Path": role["Path"],
                "CreateDate": role["CreateDate"].strftime("%Y-%m-%d"),
                "Description": role.get("Description", "")[:50],
            })

        ctx.output.print_data(
            data,
            headers=["RoleName", "RoleId", "Path", "CreateDate", "Description"],
            title=f"IAM Roles ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list roles: {e}")


@iam.command("list-policies")
@click.option(
    "--scope",
    type=click.Choice(["Local", "AWS", "All"]),
    default="Local",
    help="Policy scope filter",
)
@click.option("--only-attached", is_flag=True, help="Only show attached policies")
@click.option("--max-items", type=int, help="Maximum number of policies to return")
@pass_context
def list_policies(
    ctx: DevCtlContext,
    scope: str,
    only_attached: bool,
    max_items: int | None,
) -> None:
    """List IAM policies."""
    try:
        iam_client = ctx.aws.iam
        kwargs: dict[str, Any] = {"Scope": scope}
        if only_attached:
            kwargs["OnlyAttached"] = True
        if max_items:
            kwargs["MaxItems"] = max_items

        policies = paginate(iam_client, "list_policies", "Policies", **kwargs)

        data = []
        for policy in policies:
            data.append({
                "PolicyName": policy["PolicyName"],
                "Arn": policy["Arn"],
                "AttachmentCount": policy.get("AttachmentCount", 0),
                "CreateDate": policy["CreateDate"].strftime("%Y-%m-%d"),
                "UpdateDate": policy.get("UpdateDate", policy["CreateDate"]).strftime("%Y-%m-%d"),
            })

        ctx.output.print_data(
            data,
            headers=["PolicyName", "Arn", "AttachmentCount", "CreateDate", "UpdateDate"],
            title=f"IAM Policies ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list policies: {e}")


@iam.command()
@click.argument("role_arn")
@click.option("--duration", type=int, default=3600, help="Session duration in seconds")
@click.option("--session-name", default="devctl-session", help="Session name")
@pass_context
def assume(ctx: DevCtlContext, role_arn: str, duration: int, session_name: str) -> None:
    """Assume an IAM role and output credentials.

    ROLE_ARN is the ARN of the role to assume.

    \b
    Example:
        devctl aws iam assume arn:aws:iam::123456789012:role/MyRole
        eval $(devctl aws iam assume arn:aws:iam::123456789012:role/MyRole -o raw)
    """
    if ctx.dry_run:
        ctx.log_dry_run("assume role", {"role_arn": role_arn, "duration": duration})
        return

    try:
        sts = ctx.aws.client("sts")
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=duration,
        )

        credentials = response["Credentials"]

        if ctx.output_format.value == "raw":
            # Output export commands for shell eval
            print(f"export AWS_ACCESS_KEY_ID={credentials['AccessKeyId']}")
            print(f"export AWS_SECRET_ACCESS_KEY={credentials['SecretAccessKey']}")
            print(f"export AWS_SESSION_TOKEN={credentials['SessionToken']}")
        else:
            data = {
                "AccessKeyId": credentials["AccessKeyId"],
                "SecretAccessKey": credentials["SecretAccessKey"][:20] + "...",
                "SessionToken": credentials["SessionToken"][:20] + "...",
                "Expiration": credentials["Expiration"].isoformat(),
                "AssumedRoleArn": response["AssumedRoleUser"]["Arn"],
            }
            ctx.output.print_data(data, title="Assumed Role Credentials")

    except ClientError as e:
        raise AWSError(f"Failed to assume role: {e}")


@iam.command("analyze-policy")
@click.argument("policy_arn")
@pass_context
def analyze_policy(ctx: DevCtlContext, policy_arn: str) -> None:
    """Analyze an IAM policy and show its permissions.

    POLICY_ARN is the ARN of the policy to analyze.
    """
    try:
        iam_client = ctx.aws.iam

        # Get policy details
        policy = iam_client.get_policy(PolicyArn=policy_arn)["Policy"]

        # Get policy version document
        version = iam_client.get_policy_version(
            PolicyArn=policy_arn,
            VersionId=policy["DefaultVersionId"],
        )["PolicyVersion"]

        document = version["Document"]
        if isinstance(document, str):
            document = json.loads(document)

        ctx.output.print_panel(
            f"Policy: {policy['PolicyName']}\nARN: {policy_arn}\nVersion: {policy['DefaultVersionId']}",
            title="Policy Info",
        )

        # Analyze statements
        statements = document.get("Statement", [])
        if not isinstance(statements, list):
            statements = [statements]

        data = []
        for i, stmt in enumerate(statements):
            effect = stmt.get("Effect", "Allow")
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            resources = stmt.get("Resource", [])
            if isinstance(resources, str):
                resources = [resources]

            data.append({
                "Statement": stmt.get("Sid", f"Statement{i+1}"),
                "Effect": effect,
                "Actions": ", ".join(actions[:3]) + ("..." if len(actions) > 3 else ""),
                "Resources": ", ".join(resources[:2]) + ("..." if len(resources) > 2 else ""),
            })

        ctx.output.print_data(
            data,
            headers=["Statement", "Effect", "Actions", "Resources"],
            title="Policy Statements",
        )

        # Show full document in verbose mode
        if ctx.verbose >= 2:
            ctx.output.print_code(json.dumps(document, indent=2), "json")

    except ClientError as e:
        raise AWSError(f"Failed to analyze policy: {e}")


@iam.command("unused-roles")
@click.option("--days", type=int, default=90, help="Days of inactivity threshold")
@pass_context
def unused_roles(ctx: DevCtlContext, days: int) -> None:
    """Find IAM roles that haven't been used recently.

    Helps identify roles that can be removed for security and cost purposes.
    """
    try:
        iam_client = ctx.aws.iam
        roles = paginate(iam_client, "list_roles", "Roles")

        now = datetime.now(timezone.utc)
        threshold = now.replace(tzinfo=None) - __import__("datetime").timedelta(days=days)

        unused = []
        for role in roles:
            # Skip service-linked roles
            if role.get("Path", "").startswith("/aws-service-role/"):
                continue

            # Get role last used info
            try:
                role_detail = iam_client.get_role(RoleName=role["RoleName"])["Role"]
                last_used = role_detail.get("RoleLastUsed", {})
                last_used_date = last_used.get("LastUsedDate")

                if last_used_date is None:
                    status = "Never used"
                    unused.append({
                        "RoleName": role["RoleName"],
                        "CreateDate": role["CreateDate"].strftime("%Y-%m-%d"),
                        "LastUsed": status,
                        "Region": "-",
                    })
                elif last_used_date.replace(tzinfo=None) < threshold:
                    unused.append({
                        "RoleName": role["RoleName"],
                        "CreateDate": role["CreateDate"].strftime("%Y-%m-%d"),
                        "LastUsed": last_used_date.strftime("%Y-%m-%d"),
                        "Region": last_used.get("Region", "-"),
                    })
            except ClientError:
                continue

        if unused:
            ctx.output.print_data(
                unused,
                headers=["RoleName", "CreateDate", "LastUsed", "Region"],
                title=f"Unused Roles (>{days} days inactive): {len(unused)} found",
            )
        else:
            ctx.output.print_success(f"No unused roles found (threshold: {days} days)")

    except ClientError as e:
        raise AWSError(f"Failed to check unused roles: {e}")
