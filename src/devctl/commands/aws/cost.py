"""Cost Explorer commands for AWS."""

from datetime import datetime, timedelta
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.core.output import format_cost


@click.group()
@pass_context
def cost(ctx: DevCtlContext) -> None:
    """Cost Explorer operations - billing analysis and optimization.

    \b
    Examples:
        devctl aws cost summary
        devctl aws cost by-service --top 10
        devctl aws cost forecast
        devctl aws cost rightsizing
    """
    pass


def get_date_range(days: int) -> tuple[str, str]:
    """Get date range for cost queries."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@cost.command()
@click.option("--days", type=int, default=30, help="Number of days to analyze")
@click.option("--granularity", type=click.Choice(["daily", "monthly"]), default="monthly", help="Cost granularity")
@pass_context
def summary(ctx: DevCtlContext, days: int, granularity: str) -> None:
    """Show cost summary for the account."""
    try:
        ce = ctx.aws.ce
        start_date, end_date = get_date_range(days)

        response = ce.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity=granularity.upper(),
            Metrics=["UnblendedCost", "UsageQuantity"],
        )

        results = response.get("ResultsByTime", [])

        if not results:
            ctx.output.print_info("No cost data available for the specified period")
            return

        total_cost = 0.0
        data = []

        for result in results:
            period_start = result["TimePeriod"]["Start"]
            amount = float(result["Total"]["UnblendedCost"]["Amount"])
            currency = result["Total"]["UnblendedCost"]["Unit"]
            total_cost += amount

            data.append({
                "Period": period_start,
                "Cost": format_cost(amount, currency),
            })

        ctx.output.print_data(
            data,
            headers=["Period", "Cost"],
            title=f"Cost Summary ({days} days)",
        )

        ctx.output.print_success(f"Total: {format_cost(total_cost, 'USD')}")

    except ClientError as e:
        raise AWSError(f"Failed to get cost summary: {e}")


@cost.command("by-service")
@click.option("--days", type=int, default=30, help="Number of days to analyze")
@click.option("--top", type=int, default=10, help="Show top N services")
@pass_context
def by_service(ctx: DevCtlContext, days: int, top: int) -> None:
    """Show costs grouped by service."""
    try:
        ce = ctx.aws.ce
        start_date, end_date = get_date_range(days)

        response = ce.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        # Aggregate costs by service
        service_costs: dict[str, float] = {}
        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                service_costs[service] = service_costs.get(service, 0) + amount

        # Sort by cost
        sorted_services = sorted(service_costs.items(), key=lambda x: -x[1])[:top]
        total = sum(c for _, c in sorted_services)

        data = []
        for service, amount in sorted_services:
            pct = (amount / total * 100) if total > 0 else 0
            data.append({
                "Service": service[:50],
                "Cost": format_cost(amount, "USD"),
                "Percentage": f"{pct:.1f}%",
            })

        ctx.output.print_data(
            data,
            headers=["Service", "Cost", "Percentage"],
            title=f"Top {top} Services by Cost ({days} days)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to get service costs: {e}")


@cost.command()
@click.option("--days", type=int, default=30, help="Forecast horizon in days")
@pass_context
def forecast(ctx: DevCtlContext, days: int) -> None:
    """Forecast future costs."""
    try:
        ce = ctx.aws.ce

        start = datetime.utcnow().date()
        end = start + timedelta(days=days)

        response = ce.get_cost_forecast(
            TimePeriod={
                "Start": start.strftime("%Y-%m-%d"),
                "End": end.strftime("%Y-%m-%d"),
            },
            Metric="UNBLENDED_COST",
            Granularity="MONTHLY",
        )

        total = response.get("Total", {})
        forecast_amount = float(total.get("Amount", 0))

        forecasts = response.get("ForecastResultsByTime", [])

        data = []
        for f in forecasts:
            period = f["TimePeriod"]["Start"]
            mean = float(f.get("MeanValue", 0))
            lower = float(f.get("PredictionIntervalLowerBound", mean * 0.9))
            upper = float(f.get("PredictionIntervalUpperBound", mean * 1.1))

            data.append({
                "Period": period,
                "Forecast": format_cost(mean, "USD"),
                "Lower": format_cost(lower, "USD"),
                "Upper": format_cost(upper, "USD"),
            })

        ctx.output.print_data(
            data,
            headers=["Period", "Forecast", "Lower", "Upper"],
            title=f"Cost Forecast (next {days} days)",
        )

        ctx.output.print_info(f"Total forecast: {format_cost(forecast_amount, 'USD')}")

    except ClientError as e:
        if "not have enough data" in str(e):
            ctx.output.print_warning("Not enough historical data for forecasting")
        else:
            raise AWSError(f"Failed to forecast costs: {e}")


@cost.command()
@click.option("--days", type=int, default=7, help="Days to check for anomalies")
@pass_context
def anomalies(ctx: DevCtlContext, days: int) -> None:
    """Detect cost anomalies."""
    try:
        ce = ctx.aws.ce

        end = datetime.utcnow()
        start = end - timedelta(days=days)

        response = ce.get_anomalies(
            DateInterval={
                "StartDate": start.strftime("%Y-%m-%d"),
                "EndDate": end.strftime("%Y-%m-%d"),
            },
        )

        anomalies_list = response.get("Anomalies", [])

        if not anomalies_list:
            ctx.output.print_success("No cost anomalies detected")
            return

        data = []
        for anomaly in anomalies_list:
            impact = anomaly.get("Impact", {})
            data.append({
                "ID": anomaly["AnomalyId"][:12],
                "Start": anomaly.get("AnomalyStartDate", "-"),
                "End": anomaly.get("AnomalyEndDate", "ongoing"),
                "Impact": format_cost(float(impact.get("TotalImpact", 0)), "USD"),
                "Percentage": f"{float(impact.get('TotalImpactPercentage', 0)):.1f}%",
                "Service": anomaly.get("RootCauses", [{}])[0].get("Service", "-")[:30],
            })

        ctx.output.print_data(
            data,
            headers=["ID", "Start", "End", "Impact", "Percentage", "Service"],
            title=f"Cost Anomalies ({len(data)} found)",
        )

    except ClientError as e:
        raise AWSError(f"Failed to get anomalies: {e}")


@cost.command()
@pass_context
def rightsizing(ctx: DevCtlContext) -> None:
    """Get EC2 rightsizing recommendations."""
    try:
        ce = ctx.aws.ce

        response = ce.get_rightsizing_recommendation(
            Service="AmazonEC2",
        )

        recommendations = response.get("RightsizingRecommendations", [])

        if not recommendations:
            ctx.output.print_success("No rightsizing recommendations found")
            return

        data = []
        total_savings = 0.0

        for rec in recommendations[:20]:  # Limit to top 20
            current = rec.get("CurrentInstance", {})
            resource_details = current.get("ResourceDetails", {}).get("EC2ResourceDetails", {})

            modify = rec.get("ModifyRecommendationDetail", {})
            target = modify.get("TargetInstances", [{}])[0] if modify else {}
            target_details = target.get("ResourceDetails", {}).get("EC2ResourceDetails", {})

            savings = float(target.get("EstimatedMonthlySavings", "0") or "0")
            total_savings += savings

            data.append({
                "Instance": current.get("ResourceId", "-")[:20],
                "Current": resource_details.get("InstanceType", "-"),
                "Recommended": target_details.get("InstanceType", "-"),
                "MonthlySavings": format_cost(savings, "USD"),
                "Action": rec.get("RightsizingType", "-"),
            })

        ctx.output.print_data(
            data,
            headers=["Instance", "Current", "Recommended", "MonthlySavings", "Action"],
            title=f"Rightsizing Recommendations ({len(data)} shown)",
        )

        ctx.output.print_success(f"Total potential monthly savings: {format_cost(total_savings, 'USD')}")

    except ClientError as e:
        raise AWSError(f"Failed to get rightsizing recommendations: {e}")


@cost.command("savings-plans")
@pass_context
def savings_plans(ctx: DevCtlContext) -> None:
    """Get Savings Plans recommendations."""
    try:
        ce = ctx.aws.ce

        response = ce.get_savings_plans_purchase_recommendation(
            SavingsPlansType="COMPUTE_SP",
            TermInYears="ONE_YEAR",
            PaymentOption="NO_UPFRONT",
            LookbackPeriodInDays="SIXTY_DAYS",
        )

        metadata = response.get("Metadata", {})
        recommendations = response.get("SavingsPlansPurchaseRecommendation", {})
        details = recommendations.get("SavingsPlansPurchaseRecommendationDetails", [])

        if not details:
            ctx.output.print_info("No Savings Plans recommendations available")
            return

        summary = recommendations.get("SavingsPlansPurchaseRecommendationSummary", {})

        ctx.output.print_panel(
            f"Recommended hourly commitment: {format_cost(float(summary.get('HourlyCommitmentToPurchase', 0)), 'USD')}\n"
            f"Estimated monthly savings: {format_cost(float(summary.get('EstimatedMonthlySavingsAmount', 0)), 'USD')}\n"
            f"Estimated savings percentage: {summary.get('EstimatedSavingsPercentage', 0)}%",
            title="Savings Plans Summary",
        )

        data = []
        for detail in details[:10]:
            data.append({
                "Type": detail.get("SavingsPlansDetails", {}).get("OfferingId", "-")[:30],
                "Commitment": format_cost(float(detail.get("HourlyCommitmentToPurchase", 0)), "USD") + "/hr",
                "EstSavings": format_cost(float(detail.get("EstimatedMonthlySavingsAmount", 0)), "USD") + "/mo",
                "Coverage": f"{float(detail.get('EstimatedAverageUtilization', 0)):.1f}%",
            })

        if data:
            ctx.output.print_data(
                data,
                headers=["Type", "Commitment", "EstSavings", "Coverage"],
                title="Recommended Plans",
            )

    except ClientError as e:
        raise AWSError(f"Failed to get Savings Plans recommendations: {e}")


@cost.command("unused-resources")
@pass_context
def unused_resources(ctx: DevCtlContext) -> None:
    """Find potentially unused AWS resources."""
    ctx.output.print_info("Checking for unused resources...")

    findings = []

    # Check for unattached EBS volumes
    try:
        ec2 = ctx.aws.client("ec2")
        volumes = ec2.describe_volumes(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )["Volumes"]

        for vol in volumes:
            size_gb = vol["Size"]
            monthly_cost = size_gb * 0.10  # Approximate gp2 pricing
            findings.append({
                "Type": "EBS Volume",
                "Resource": vol["VolumeId"],
                "Details": f"{size_gb} GB unattached",
                "EstMonthlyCost": format_cost(monthly_cost, "USD"),
            })
    except ClientError:
        pass

    # Check for unused Elastic IPs
    try:
        ec2 = ctx.aws.client("ec2")
        addresses = ec2.describe_addresses()["Addresses"]

        for addr in addresses:
            if "InstanceId" not in addr and "NetworkInterfaceId" not in addr:
                findings.append({
                    "Type": "Elastic IP",
                    "Resource": addr.get("PublicIp", "-"),
                    "Details": "Not associated",
                    "EstMonthlyCost": format_cost(3.60, "USD"),  # $0.005/hr
                })
    except ClientError:
        pass

    # Check for idle load balancers
    try:
        elbv2 = ctx.aws.client("elbv2")
        lbs = elbv2.describe_load_balancers()["LoadBalancers"]

        for lb in lbs:
            target_groups = elbv2.describe_target_groups(
                LoadBalancerArn=lb["LoadBalancerArn"]
            ).get("TargetGroups", [])

            has_targets = False
            for tg in target_groups:
                health = elbv2.describe_target_health(
                    TargetGroupArn=tg["TargetGroupArn"]
                ).get("TargetHealthDescriptions", [])
                if health:
                    has_targets = True
                    break

            if not has_targets:
                findings.append({
                    "Type": "Load Balancer",
                    "Resource": lb["LoadBalancerName"],
                    "Details": "No healthy targets",
                    "EstMonthlyCost": format_cost(16.20, "USD"),  # ALB base cost
                })
    except ClientError:
        pass

    if findings:
        ctx.output.print_data(
            findings,
            headers=["Type", "Resource", "Details", "EstMonthlyCost"],
            title=f"Potentially Unused Resources ({len(findings)} found)",
        )

        total = sum(float(f["EstMonthlyCost"].replace("$", "").replace(",", "")) for f in findings)
        ctx.output.print_info(f"Total potential monthly savings: {format_cost(total, 'USD')}")
    else:
        ctx.output.print_success("No unused resources found")
