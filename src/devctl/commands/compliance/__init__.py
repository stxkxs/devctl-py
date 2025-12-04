"""Compliance command group."""

import click
import json
from datetime import datetime
from pathlib import Path

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import ComplianceError


@click.group()
@pass_context
def compliance(ctx: DevCtlContext) -> None:
    """Compliance operations - PCI scans, access reviews.

    \b
    Examples:
        devctl compliance pci scan
        devctl compliance pci report --format html
        devctl compliance access-review
    """
    pass


@compliance.group("pci")
def pci() -> None:
    """PCI DSS compliance operations."""
    pass


@pci.command("scan")
@click.option("--controls", default=None, help="Comma-separated control IDs to check")
@click.option("--regions", default=None, help="Comma-separated AWS regions")
@click.option("--output", "-o", "output_file", default=None, help="Output file")
@pass_context
def pci_scan(
    ctx: DevCtlContext,
    controls: str | None,
    regions: str | None,
    output_file: str | None,
) -> None:
    """Run PCI DSS compliance scan.

    \b
    Examples:
        devctl compliance pci scan
        devctl compliance pci scan --controls PCI-7.1,PCI-8.1
        devctl compliance pci scan --regions us-east-1,us-west-2
    """
    try:
        # Parse controls
        control_list = [c.strip() for c in controls.split(",")] if controls else None

        # Parse regions
        region_list = [r.strip() for r in regions.split(",")] if regions else None

        ctx.output.print_info("Running PCI DSS compliance scan...")

        # Run checks
        results = _run_pci_checks(ctx, control_list, region_list)

        # Summary
        passed = sum(1 for r in results if r["status"] == "PASS")
        failed = sum(1 for r in results if r["status"] == "FAIL")
        warnings = sum(1 for r in results if r["status"] == "WARNING")

        ctx.output.print("")
        ctx.output.print_header("PCI DSS Scan Results")
        ctx.output.print(f"Total checks: {len(results)}")
        ctx.output.print(f"Passed: {passed}")
        ctx.output.print(f"Failed: {failed}")
        ctx.output.print(f"Warnings: {warnings}")

        # Show failures
        if failed > 0:
            ctx.output.print("\nFailed Checks:")
            for r in results:
                if r["status"] == "FAIL":
                    ctx.output.print_error(f"  [{r['control']}] {r['title']}: {r['message']}")

        # Show warnings
        if warnings > 0:
            ctx.output.print("\nWarnings:")
            for r in results:
                if r["status"] == "WARNING":
                    ctx.output.print_warning(f"  [{r['control']}] {r['title']}: {r['message']}")

        # Save to file
        if output_file:
            Path(output_file).write_text(json.dumps(results, indent=2))
            ctx.output.print(f"\nResults saved to: {output_file}")

    except Exception as e:
        ctx.output.print_error(f"Scan failed: {e}")
        raise click.Abort()


@pci.command("report")
@click.option("--format", "output_format", type=click.Choice(["json", "csv", "html"]), default="json", help="Output format")
@click.option("--output", "-o", "output_file", default=None, help="Output file")
@pass_context
def pci_report(ctx: DevCtlContext, output_format: str, output_file: str | None) -> None:
    """Generate PCI compliance report.

    \b
    Examples:
        devctl compliance pci report
        devctl compliance pci report --format html -o report.html
    """
    try:
        ctx.output.print_info("Generating PCI DSS compliance report...")

        # Run full scan
        results = _run_pci_checks(ctx, None, None)

        # Generate report
        if output_format == "json":
            report = json.dumps({
                "generated_at": datetime.utcnow().isoformat(),
                "summary": {
                    "total": len(results),
                    "passed": sum(1 for r in results if r["status"] == "PASS"),
                    "failed": sum(1 for r in results if r["status"] == "FAIL"),
                    "warnings": sum(1 for r in results if r["status"] == "WARNING"),
                },
                "results": results,
            }, indent=2)
        elif output_format == "csv":
            lines = ["control,title,status,message"]
            for r in results:
                lines.append(f"{r['control']},{r['title']},{r['status']},{r['message']}")
            report = "\n".join(lines)
        else:  # html
            report = _generate_html_report(results)

        if output_file:
            Path(output_file).write_text(report)
            ctx.output.print_success(f"Report saved to: {output_file}")
        else:
            ctx.output.print(report)

    except Exception as e:
        ctx.output.print_error(f"Report generation failed: {e}")
        raise click.Abort()


@pci.command("check")
@click.argument("control_id")
@pass_context
def pci_check(ctx: DevCtlContext, control_id: str) -> None:
    """Run a specific PCI control check.

    \b
    Examples:
        devctl compliance pci check PCI-7.1
        devctl compliance pci check PCI-8.2
    """
    try:
        results = _run_pci_checks(ctx, [control_id], None)

        if not results:
            ctx.output.print_error(f"Unknown control: {control_id}")
            return

        result = results[0]

        ctx.output.print_header(f"Control: {result['control']}")
        ctx.output.print(f"Title: {result['title']}")
        ctx.output.print(f"Description: {result['description']}")
        ctx.output.print(f"Status: {result['status']}")
        ctx.output.print(f"Message: {result['message']}")

        if result.get("resources"):
            ctx.output.print("\nAffected Resources:")
            for resource in result["resources"][:10]:
                ctx.output.print(f"  - {resource}")

    except Exception as e:
        ctx.output.print_error(f"Check failed: {e}")
        raise click.Abort()


@pci.command("summary")
@pass_context
def pci_summary(ctx: DevCtlContext) -> None:
    """Show PCI compliance summary.

    \b
    Examples:
        devctl compliance pci summary
    """
    try:
        results = _run_pci_checks(ctx, None, None)

        # Group by control category
        categories = {}
        for r in results:
            cat = r["control"].split("-")[1].split(".")[0] if "-" in r["control"] else "Other"
            cat_name = {
                "1": "Network Security",
                "3": "Data Protection",
                "4": "Encryption",
                "7": "Access Control",
                "8": "Authentication",
                "10": "Logging & Monitoring",
            }.get(cat, f"Category {cat}")

            if cat_name not in categories:
                categories[cat_name] = {"passed": 0, "failed": 0, "warning": 0}

            if r["status"] == "PASS":
                categories[cat_name]["passed"] += 1
            elif r["status"] == "FAIL":
                categories[cat_name]["failed"] += 1
            else:
                categories[cat_name]["warning"] += 1

        rows = []
        for cat, counts in sorted(categories.items()):
            total = counts["passed"] + counts["failed"] + counts["warning"]
            score = int((counts["passed"] / total) * 100) if total > 0 else 0
            rows.append({
                "category": cat,
                "passed": counts["passed"],
                "failed": counts["failed"],
                "warning": counts["warning"],
                "score": f"{score}%",
            })

        ctx.output.print_table(
            rows,
            columns=["category", "passed", "failed", "warning", "score"],
            title="PCI DSS Compliance Summary",
        )

    except Exception as e:
        ctx.output.print_error(f"Summary failed: {e}")
        raise click.Abort()


@compliance.group("access-review")
def access_review() -> None:
    """Access review operations."""
    pass


@access_review.command("list")
@click.option("--days", default=90, help="Inactive days threshold")
@pass_context
def access_review_list(ctx: DevCtlContext, days: int) -> None:
    """List users for access review.

    \b
    Examples:
        devctl compliance access-review list
        devctl compliance access-review list --days 60
    """
    try:
        ctx.output.print_info(f"Finding users inactive for {days}+ days...")

        # Check IAM users
        iam = ctx.aws.iam()
        users = iam.list_users()["Users"]

        review_needed = []
        now = datetime.utcnow()

        for user in users:
            username = user["UserName"]

            # Check last activity
            try:
                # Get access key last used
                keys = iam.list_access_keys(UserName=username)["AccessKeyMetadata"]
                last_used = None

                for key in keys:
                    key_last_used = iam.get_access_key_last_used(AccessKeyId=key["AccessKeyId"])
                    used_date = key_last_used.get("AccessKeyLastUsed", {}).get("LastUsedDate")
                    if used_date and (not last_used or used_date > last_used):
                        last_used = used_date

                # Check password last used
                pwd_last_used = user.get("PasswordLastUsed")
                if pwd_last_used and (not last_used or pwd_last_used > last_used):
                    last_used = pwd_last_used

                if last_used:
                    inactive_days = (now - last_used.replace(tzinfo=None)).days
                    if inactive_days >= days:
                        review_needed.append({
                            "username": username,
                            "last_activity": last_used.strftime("%Y-%m-%d"),
                            "inactive_days": inactive_days,
                            "has_console": bool(pwd_last_used),
                            "access_keys": len(keys),
                        })
                else:
                    # Never used
                    created = user["CreateDate"]
                    inactive_days = (now - created.replace(tzinfo=None)).days
                    if inactive_days >= days:
                        review_needed.append({
                            "username": username,
                            "last_activity": "Never",
                            "inactive_days": inactive_days,
                            "has_console": False,
                            "access_keys": len(keys),
                        })

            except Exception as e:
                ctx.output.print_warning(f"Could not check {username}: {e}")

        if not review_needed:
            ctx.output.print_success(f"No users inactive for {days}+ days")
            return

        ctx.output.print_table(
            review_needed,
            columns=["username", "last_activity", "inactive_days", "has_console", "access_keys"],
            title=f"Users Inactive {days}+ Days",
        )

    except Exception as e:
        ctx.output.print_error(f"Access review failed: {e}")
        raise click.Abort()


@access_review.command("export")
@click.option("--format", "output_format", type=click.Choice(["json", "csv"]), default="csv", help="Output format")
@click.option("--output", "-o", "output_file", default="access-review.csv", help="Output file")
@click.option("--days", default=90, help="Inactive days threshold")
@pass_context
def access_review_export(ctx: DevCtlContext, output_format: str, output_file: str, days: int) -> None:
    """Export access review data.

    \b
    Examples:
        devctl compliance access-review export
        devctl compliance access-review export --format json -o review.json
    """
    try:
        ctx.output.print_info("Exporting access review data...")

        # Get all IAM users with details
        iam = ctx.aws.iam()
        users = iam.list_users()["Users"]

        export_data = []
        now = datetime.utcnow()

        for user in users:
            username = user["UserName"]

            try:
                # Get groups
                groups = iam.list_groups_for_user(UserName=username)["Groups"]
                group_names = [g["GroupName"] for g in groups]

                # Get policies
                attached_policies = iam.list_attached_user_policies(UserName=username)["AttachedPolicies"]
                policy_names = [p["PolicyName"] for p in attached_policies]

                # Get MFA
                mfa_devices = iam.list_mfa_devices(UserName=username)["MFADevices"]

                export_data.append({
                    "username": username,
                    "created": user["CreateDate"].strftime("%Y-%m-%d"),
                    "password_last_used": user.get("PasswordLastUsed", "").strftime("%Y-%m-%d") if user.get("PasswordLastUsed") else "N/A",
                    "groups": ", ".join(group_names),
                    "policies": ", ".join(policy_names),
                    "mfa_enabled": len(mfa_devices) > 0,
                })

            except Exception:
                pass

        # Export
        if output_format == "json":
            content = json.dumps(export_data, indent=2)
        else:
            lines = ["username,created,password_last_used,groups,policies,mfa_enabled"]
            for d in export_data:
                lines.append(f"{d['username']},{d['created']},{d['password_last_used']},{d['groups']},{d['policies']},{d['mfa_enabled']}")
            content = "\n".join(lines)

        Path(output_file).write_text(content)
        ctx.output.print_success(f"Exported to: {output_file}")

    except Exception as e:
        ctx.output.print_error(f"Export failed: {e}")
        raise click.Abort()


def _run_pci_checks(ctx: DevCtlContext, controls: list | None, regions: list | None) -> list:
    """Run PCI DSS checks."""
    results = []

    # Define checks
    all_checks = [
        ("PCI-7.1", "Least Privilege Access", "Check for overly permissive IAM policies", _check_iam_permissions),
        ("PCI-8.1", "Root Account Usage", "Check for root account access", _check_root_account),
        ("PCI-8.2", "Access Key Rotation", "Check access key age", _check_key_rotation),
        ("PCI-8.3", "MFA Enforcement", "Check MFA for console users", _check_mfa),
        ("PCI-1.3", "Network Segmentation", "Check security group rules", _check_security_groups),
        ("PCI-3.4", "Encryption at Rest", "Check encryption status", _check_encryption_at_rest),
        ("PCI-10.1", "CloudTrail", "Check CloudTrail configuration", _check_cloudtrail),
        ("PCI-10.2", "VPC Flow Logs", "Check VPC flow logs", _check_flow_logs),
    ]

    # Filter checks
    if controls:
        all_checks = [c for c in all_checks if c[0] in controls]

    for control_id, title, description, check_func in all_checks:
        try:
            status, message, resources = check_func(ctx)
            results.append({
                "control": control_id,
                "title": title,
                "description": description,
                "status": status,
                "message": message,
                "resources": resources,
            })
        except Exception as e:
            results.append({
                "control": control_id,
                "title": title,
                "description": description,
                "status": "ERROR",
                "message": str(e),
                "resources": [],
            })

    return results


def _check_iam_permissions(ctx: DevCtlContext) -> tuple[str, str, list]:
    """Check for overly permissive IAM policies."""
    iam = ctx.aws.iam()
    issues = []

    # Check for policies with * actions
    paginator = iam.get_paginator("list_policies")
    for page in paginator.paginate(Scope="Local"):
        for policy in page["Policies"]:
            try:
                version = iam.get_policy_version(
                    PolicyArn=policy["Arn"],
                    VersionId=policy["DefaultVersionId"]
                )
                doc = version["PolicyVersion"]["Document"]
                statements = doc.get("Statement", [])

                for stmt in statements:
                    if stmt.get("Effect") == "Allow":
                        actions = stmt.get("Action", [])
                        if isinstance(actions, str):
                            actions = [actions]
                        if "*" in actions or "iam:*" in actions:
                            issues.append(policy["PolicyName"])
            except Exception:
                pass

    if issues:
        return "FAIL", f"{len(issues)} policies with overly permissive actions", issues
    return "PASS", "No overly permissive policies found", []


def _check_root_account(ctx: DevCtlContext) -> tuple[str, str, list]:
    """Check root account usage."""
    iam = ctx.aws.iam()

    try:
        summary = iam.get_account_summary()["SummaryMap"]
        root_keys = summary.get("AccountAccessKeysPresent", 0)

        if root_keys > 0:
            return "FAIL", "Root account has access keys", ["Root Access Keys"]

        return "PASS", "No root access keys found", []
    except Exception as e:
        return "WARNING", f"Could not check: {e}", []


def _check_key_rotation(ctx: DevCtlContext) -> tuple[str, str, list]:
    """Check access key age."""
    iam = ctx.aws.iam()
    old_keys = []
    now = datetime.utcnow()

    users = iam.list_users()["Users"]
    for user in users:
        keys = iam.list_access_keys(UserName=user["UserName"])["AccessKeyMetadata"]
        for key in keys:
            if key["Status"] == "Active":
                age = (now - key["CreateDate"].replace(tzinfo=None)).days
                if age > 90:
                    old_keys.append(f"{user['UserName']}:{key['AccessKeyId']} ({age} days)")

    if old_keys:
        return "FAIL", f"{len(old_keys)} access keys older than 90 days", old_keys
    return "PASS", "All access keys within rotation policy", []


def _check_mfa(ctx: DevCtlContext) -> tuple[str, str, list]:
    """Check MFA for console users."""
    iam = ctx.aws.iam()
    no_mfa = []

    users = iam.list_users()["Users"]
    for user in users:
        # Check if user has console access
        if user.get("PasswordLastUsed"):
            mfa_devices = iam.list_mfa_devices(UserName=user["UserName"])["MFADevices"]
            if not mfa_devices:
                no_mfa.append(user["UserName"])

    if no_mfa:
        return "FAIL", f"{len(no_mfa)} console users without MFA", no_mfa
    return "PASS", "All console users have MFA enabled", []


def _check_security_groups(ctx: DevCtlContext) -> tuple[str, str, list]:
    """Check for overly permissive security groups."""
    ec2 = ctx.aws.ec2()
    issues = []

    sgs = ec2.describe_security_groups()["SecurityGroups"]
    for sg in sgs:
        for rule in sg.get("IpPermissions", []):
            for ip_range in rule.get("IpRanges", []):
                if ip_range.get("CidrIp") == "0.0.0.0/0":
                    port = rule.get("FromPort", "all")
                    if port in [22, 3389, 3306, 5432, 1433]:
                        issues.append(f"{sg['GroupId']}:{port}")

    if issues:
        return "FAIL", f"{len(issues)} security groups with 0.0.0.0/0 on sensitive ports", issues
    return "PASS", "No overly permissive security groups", []


def _check_encryption_at_rest(ctx: DevCtlContext) -> tuple[str, str, list]:
    """Check encryption at rest."""
    s3 = ctx.aws.s3()
    issues = []

    buckets = s3.list_buckets()["Buckets"]
    for bucket in buckets:
        try:
            enc = s3.get_bucket_encryption(Bucket=bucket["Name"])
        except Exception:
            issues.append(f"s3:{bucket['Name']}")

    if issues:
        return "WARNING", f"{len(issues)} S3 buckets without default encryption", issues
    return "PASS", "All S3 buckets have encryption", []


def _check_cloudtrail(ctx: DevCtlContext) -> tuple[str, str, list]:
    """Check CloudTrail configuration."""
    cloudtrail = ctx.aws.cloudtrail()

    trails = cloudtrail.describe_trails()["trailList"]

    if not trails:
        return "FAIL", "No CloudTrail trails found", []

    multi_region = [t for t in trails if t.get("IsMultiRegionTrail")]
    if not multi_region:
        return "WARNING", "No multi-region trail found", []

    return "PASS", "CloudTrail configured with multi-region trail", []


def _check_flow_logs(ctx: DevCtlContext) -> tuple[str, str, list]:
    """Check VPC flow logs."""
    ec2 = ctx.aws.ec2()
    issues = []

    vpcs = ec2.describe_vpcs()["Vpcs"]
    flow_logs = ec2.describe_flow_logs()["FlowLogs"]
    vpc_with_logs = {fl["ResourceId"] for fl in flow_logs}

    for vpc in vpcs:
        if vpc["VpcId"] not in vpc_with_logs:
            issues.append(vpc["VpcId"])

    if issues:
        return "FAIL", f"{len(issues)} VPCs without flow logs", issues
    return "PASS", "All VPCs have flow logs enabled", []


def _generate_html_report(results: list) -> str:
    """Generate HTML compliance report."""
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    warnings = sum(1 for r in results if r["status"] == "WARNING")

    rows = ""
    for r in results:
        color = {"PASS": "green", "FAIL": "red", "WARNING": "orange"}.get(r["status"], "gray")
        rows += f"""
        <tr>
            <td>{r['control']}</td>
            <td>{r['title']}</td>
            <td style="color: {color}; font-weight: bold;">{r['status']}</td>
            <td>{r['message']}</td>
        </tr>
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>PCI DSS Compliance Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .summary {{ margin: 20px 0; padding: 10px; background: #f5f5f5; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>PCI DSS Compliance Report</h1>
    <p>Generated: {datetime.utcnow().isoformat()}</p>

    <div class="summary">
        <strong>Summary:</strong>
        Total: {len(results)} |
        <span style="color: green;">Passed: {passed}</span> |
        <span style="color: red;">Failed: {failed}</span> |
        <span style="color: orange;">Warnings: {warnings}</span>
    </div>

    <table>
        <thead>
            <tr>
                <th>Control</th>
                <th>Title</th>
                <th>Status</th>
                <th>Details</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
</body>
</html>
"""
