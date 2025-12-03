"""Cross-service cost reporting."""

from datetime import datetime, timedelta
from typing import Any

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import DevCtlError
from devctl.core.output import format_cost


@click.command("cost-report")
@click.option("--days", type=int, default=30, help="Number of days to analyze")
@click.option("--format", "output_format", type=click.Choice(["summary", "detailed", "csv"]), default="summary", help="Report format")
@click.option("--output", "-o", type=click.Path(), help="Output file (for CSV)")
@pass_context
def cost_report(ctx: DevCtlContext, days: int, output_format: str, output: str | None) -> None:
    """Generate cross-service cost report.

    Aggregates costs from AWS, and estimates for Grafana/GitHub.
    """
    ctx.output.print_info(f"Generating cost report for the last {days} days...")

    report_data: dict[str, Any] = {
        "period": {
            "start": (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "end": datetime.utcnow().strftime("%Y-%m-%d"),
            "days": days,
        },
        "services": [],
        "total": 0.0,
    }

    # AWS Costs
    try:
        aws_costs = _get_aws_costs(ctx, days)
        report_data["services"].append({
            "name": "AWS",
            "cost": aws_costs["total"],
            "breakdown": aws_costs["by_service"],
        })
        report_data["total"] += aws_costs["total"]
    except Exception as e:
        ctx.output.print_warning(f"Could not get AWS costs: {e}")
        report_data["services"].append({
            "name": "AWS",
            "cost": 0,
            "error": str(e),
        })

    # Grafana Costs (estimated based on usage)
    try:
        grafana_costs = _estimate_grafana_costs(ctx)
        report_data["services"].append({
            "name": "Grafana Cloud",
            "cost": grafana_costs["estimated"],
            "note": "Estimated based on dashboards and datasources",
        })
        report_data["total"] += grafana_costs["estimated"]
    except Exception as e:
        ctx.output.print_warning(f"Could not estimate Grafana costs: {e}")

    # GitHub Costs (estimated based on usage)
    try:
        github_costs = _estimate_github_costs(ctx)
        report_data["services"].append({
            "name": "GitHub",
            "cost": github_costs["estimated"],
            "note": "Estimated based on repos and actions",
        })
        report_data["total"] += github_costs["estimated"]
    except Exception as e:
        ctx.output.print_warning(f"Could not estimate GitHub costs: {e}")

    # Output report
    if output_format == "csv":
        _output_csv(report_data, output)
        ctx.output.print_success(f"Report saved to {output or 'cost_report.csv'}")
    elif output_format == "detailed":
        _output_detailed(ctx, report_data)
    else:
        _output_summary(ctx, report_data)


def _get_aws_costs(ctx: DevCtlContext, days: int) -> dict[str, Any]:
    """Get AWS costs from Cost Explorer."""
    from botocore.exceptions import ClientError

    try:
        ce = ctx.aws.ce

        end = datetime.utcnow().date()
        start = end - timedelta(days=days)

        response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": start.strftime("%Y-%m-%d"),
                "End": end.strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        by_service: dict[str, float] = {}
        total = 0.0

        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                by_service[service] = by_service.get(service, 0) + amount
                total += amount

        return {"total": total, "by_service": by_service}

    except ClientError as e:
        raise DevCtlError(f"AWS Cost Explorer error: {e}")


def _estimate_grafana_costs(ctx: DevCtlContext) -> dict[str, Any]:
    """Estimate Grafana costs based on usage."""
    try:
        client = ctx.grafana

        # Count resources
        dashboards = len(client.list_dashboards())
        datasources = len(client.list_datasources())

        # Rough estimation (Grafana Cloud pricing varies)
        # Free tier: 3 users, 10k metrics, 50GB logs
        # Pro: ~$49/user/month + usage

        estimated_base = 0  # Assuming free tier for base
        estimated_usage = (dashboards * 0.10) + (datasources * 1.00)  # Very rough estimate

        return {
            "estimated": estimated_usage,
            "dashboards": dashboards,
            "datasources": datasources,
        }
    except Exception:
        return {"estimated": 0}


def _estimate_github_costs(ctx: DevCtlContext) -> dict[str, Any]:
    """Estimate GitHub costs based on usage."""
    try:
        client = ctx.github

        # Get user/org info
        user = client.get_user()

        # Count repos
        repos = client.list_repos()
        private_repos = len([r for r in repos if r.get("private")])

        # GitHub pricing:
        # Free: unlimited public, limited private
        # Team: $4/user/month
        # Enterprise: $21/user/month

        # Rough estimate based on private repos and actions
        estimated = private_repos * 0.50  # Very rough estimate

        return {
            "estimated": estimated,
            "total_repos": len(repos),
            "private_repos": private_repos,
        }
    except Exception:
        return {"estimated": 0}


def _output_summary(ctx: DevCtlContext, report: dict[str, Any]) -> None:
    """Output summary report."""
    period = report["period"]
    ctx.output.print_panel(
        f"Period: {period['start']} to {period['end']} ({period['days']} days)",
        title="Cost Report",
    )

    data = []
    for service in report["services"]:
        data.append({
            "Service": service["name"],
            "Cost": format_cost(service["cost"], "USD"),
            "Note": service.get("note", service.get("error", "-"))[:40],
        })

    ctx.output.print_data(data, headers=["Service", "Cost", "Note"])
    ctx.output.print_success(f"Total: {format_cost(report['total'], 'USD')}")


def _output_detailed(ctx: DevCtlContext, report: dict[str, Any]) -> None:
    """Output detailed report."""
    period = report["period"]
    ctx.output.print_panel(
        f"Period: {period['start']} to {period['end']} ({period['days']} days)",
        title="Detailed Cost Report",
    )

    for service in report["services"]:
        ctx.output.print_info(f"\n{service['name']}: {format_cost(service['cost'], 'USD')}")

        if "breakdown" in service:
            breakdown = service["breakdown"]
            sorted_items = sorted(breakdown.items(), key=lambda x: -x[1])[:10]

            data = []
            for name, cost in sorted_items:
                data.append({
                    "Item": name[:40],
                    "Cost": format_cost(cost, "USD"),
                })

            if data:
                ctx.output.print_data(data, headers=["Item", "Cost"])

        if service.get("note"):
            ctx.output.print(f"  [dim]{service['note']}[/dim]")

    ctx.output.print_success(f"\nTotal: {format_cost(report['total'], 'USD')}")


def _output_csv(report: dict[str, Any], output_path: str | None) -> None:
    """Output CSV report."""
    import csv
    from pathlib import Path

    output_file = Path(output_path or "cost_report.csv")

    rows = []
    for service in report["services"]:
        if "breakdown" in service:
            for item, cost in service["breakdown"].items():
                rows.append({
                    "service": service["name"],
                    "item": item,
                    "cost": cost,
                })
        else:
            rows.append({
                "service": service["name"],
                "item": "Total",
                "cost": service["cost"],
            })

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["service", "item", "cost"])
        writer.writeheader()
        writer.writerows(rows)
