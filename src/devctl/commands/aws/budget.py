"""AWS Budget commands."""

from datetime import datetime
from typing import Any

import click
from botocore.exceptions import ClientError

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import AWSError
from devctl.core.output import format_cost


@click.group()
@pass_context
def budget(ctx: DevCtlContext) -> None:
    """Budget management and alerts.

    \b
    Examples:
        devctl aws budget list
        devctl aws budget status
        devctl aws budget create --name monthly-limit --amount 1000
    """
    pass


@budget.command("list")
@pass_context
def list_budgets(ctx: DevCtlContext) -> None:
    """List all budgets."""
    try:
        budgets_client = ctx.aws.client("budgets")
        sts = ctx.aws.client("sts")

        # Get account ID
        account_id = sts.get_caller_identity()["Account"]

        response = budgets_client.describe_budgets(AccountId=account_id)
        budgets = response.get("Budgets", [])

        if not budgets:
            ctx.output.print_info("No budgets configured")
            return

        data = []
        for b in budgets:
            budget_name = b["BudgetName"]
            budget_type = b["BudgetType"]
            time_unit = b["TimeUnit"]

            # Get budget limit
            limit = b.get("BudgetLimit", {})
            limit_amount = float(limit.get("Amount", 0))
            currency = limit.get("Unit", "USD")

            # Get actual spend
            actual = b.get("CalculatedSpend", {}).get("ActualSpend", {})
            actual_amount = float(actual.get("Amount", 0))

            # Calculate percentage
            pct = (actual_amount / limit_amount * 100) if limit_amount > 0 else 0
            status = "OK" if pct < 80 else ("WARNING" if pct < 100 else "EXCEEDED")

            data.append({
                "Name": budget_name[:30],
                "Type": budget_type,
                "Period": time_unit,
                "Limit": format_cost(limit_amount, currency),
                "Actual": format_cost(actual_amount, currency),
                "Used": f"{pct:.1f}%",
                "Status": status,
            })

        ctx.output.print_data(
            data,
            headers=["Name", "Type", "Period", "Limit", "Actual", "Used", "Status"],
            title=f"AWS Budgets ({len(budgets)})",
        )

    except ClientError as e:
        raise AWSError(f"Failed to list budgets: {e}")


@budget.command()
@pass_context
def status(ctx: DevCtlContext) -> None:
    """Show overall budget status with alerts."""
    try:
        budgets_client = ctx.aws.client("budgets")
        sts = ctx.aws.client("sts")

        account_id = sts.get_caller_identity()["Account"]

        response = budgets_client.describe_budgets(AccountId=account_id)
        budgets = response.get("Budgets", [])

        if not budgets:
            ctx.output.print_info("No budgets configured")
            return

        # Summary stats
        total_limit = 0.0
        total_actual = 0.0
        exceeded_budgets = []
        warning_budgets = []

        for b in budgets:
            limit = float(b.get("BudgetLimit", {}).get("Amount", 0))
            actual = float(b.get("CalculatedSpend", {}).get("ActualSpend", {}).get("Amount", 0))

            total_limit += limit
            total_actual += actual

            pct = (actual / limit * 100) if limit > 0 else 0
            if pct >= 100:
                exceeded_budgets.append((b["BudgetName"], pct))
            elif pct >= 80:
                warning_budgets.append((b["BudgetName"], pct))

        overall_pct = (total_actual / total_limit * 100) if total_limit > 0 else 0

        ctx.output.print_panel(
            f"Total Budget: {format_cost(total_limit, 'USD')}\n"
            f"Total Spent: {format_cost(total_actual, 'USD')}\n"
            f"Overall Usage: {overall_pct:.1f}%\n"
            f"Budgets OK: {len(budgets) - len(exceeded_budgets) - len(warning_budgets)}\n"
            f"Budgets Warning: {len(warning_budgets)}\n"
            f"Budgets Exceeded: {len(exceeded_budgets)}",
            title="Budget Status Summary",
        )

        if exceeded_budgets:
            ctx.output.print_error("Exceeded budgets:")
            for name, pct in exceeded_budgets:
                ctx.output.print(f"  - {name}: {pct:.1f}%")

        if warning_budgets:
            ctx.output.print_warning("Warning budgets (>80%):")
            for name, pct in warning_budgets:
                ctx.output.print(f"  - {name}: {pct:.1f}%")

    except ClientError as e:
        raise AWSError(f"Failed to get budget status: {e}")


@budget.command()
@click.option("--name", "-n", required=True, help="Budget name")
@click.option("--amount", "-a", required=True, type=float, help="Budget limit amount in USD")
@click.option(
    "--period",
    "-p",
    type=click.Choice(["monthly", "quarterly", "annually"]),
    default="monthly",
    help="Budget period",
)
@click.option("--alert-threshold", "-t", type=int, default=80, help="Alert threshold percentage")
@click.option("--email", "-e", multiple=True, help="Email addresses for alerts")
@pass_context
def create(
    ctx: DevCtlContext,
    name: str,
    amount: float,
    period: str,
    alert_threshold: int,
    email: tuple[str, ...],
) -> None:
    """Create a new budget."""
    if ctx.dry_run:
        ctx.output.print_info(f"Would create budget '{name}' with limit {format_cost(amount, 'USD')}")
        return

    try:
        budgets_client = ctx.aws.client("budgets")
        sts = ctx.aws.client("sts")

        account_id = sts.get_caller_identity()["Account"]

        # Map period to AWS time unit
        time_unit_map = {
            "monthly": "MONTHLY",
            "quarterly": "QUARTERLY",
            "annually": "ANNUALLY",
        }

        budget_config: dict[str, Any] = {
            "BudgetName": name,
            "BudgetType": "COST",
            "BudgetLimit": {
                "Amount": str(amount),
                "Unit": "USD",
            },
            "TimeUnit": time_unit_map[period],
            "CostTypes": {
                "IncludeTax": True,
                "IncludeSubscription": True,
                "UseBlended": False,
                "IncludeRefund": False,
                "IncludeCredit": False,
                "IncludeUpfront": True,
                "IncludeRecurring": True,
                "IncludeOtherSubscription": True,
                "IncludeSupport": True,
                "IncludeDiscount": True,
                "UseAmortized": False,
            },
        }

        # Create notifications if email provided
        notifications_with_subscribers = []
        if email:
            notifications_with_subscribers.append({
                "Notification": {
                    "NotificationType": "ACTUAL",
                    "ComparisonOperator": "GREATER_THAN",
                    "Threshold": float(alert_threshold),
                    "ThresholdType": "PERCENTAGE",
                },
                "Subscribers": [
                    {"SubscriptionType": "EMAIL", "Address": e} for e in email
                ],
            })

            # Also add forecasted alert
            notifications_with_subscribers.append({
                "Notification": {
                    "NotificationType": "FORECASTED",
                    "ComparisonOperator": "GREATER_THAN",
                    "Threshold": 100.0,
                    "ThresholdType": "PERCENTAGE",
                },
                "Subscribers": [
                    {"SubscriptionType": "EMAIL", "Address": e} for e in email
                ],
            })

        budgets_client.create_budget(
            AccountId=account_id,
            Budget=budget_config,
            NotificationsWithSubscribers=notifications_with_subscribers if notifications_with_subscribers else [],
        )

        ctx.output.print_success(f"Created budget '{name}' with limit {format_cost(amount, 'USD')}")
        if email:
            ctx.output.print_info(f"Alert notifications configured for: {', '.join(email)}")

    except ClientError as e:
        if "DuplicateRecordException" in str(e):
            raise AWSError(f"Budget '{name}' already exists")
        raise AWSError(f"Failed to create budget: {e}")


@budget.command()
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@pass_context
def delete(ctx: DevCtlContext, name: str, force: bool) -> None:
    """Delete a budget."""
    if not force and not ctx.output.confirm(f"Delete budget '{name}'?"):
        ctx.output.print("Cancelled")
        return

    if ctx.dry_run:
        ctx.output.print_info(f"Would delete budget '{name}'")
        return

    try:
        budgets_client = ctx.aws.client("budgets")
        sts = ctx.aws.client("sts")

        account_id = sts.get_caller_identity()["Account"]

        budgets_client.delete_budget(
            AccountId=account_id,
            BudgetName=name,
        )

        ctx.output.print_success(f"Deleted budget '{name}'")

    except ClientError as e:
        if "NotFoundException" in str(e):
            raise AWSError(f"Budget '{name}' not found")
        raise AWSError(f"Failed to delete budget: {e}")


@budget.command()
@click.option("--months", "-m", type=int, default=3, help="Number of months to forecast")
@pass_context
def forecast(ctx: DevCtlContext, months: int) -> None:
    """Show budget forecast based on current spending."""
    try:
        budgets_client = ctx.aws.client("budgets")
        sts = ctx.aws.client("sts")

        account_id = sts.get_caller_identity()["Account"]

        response = budgets_client.describe_budgets(AccountId=account_id)
        budgets = response.get("Budgets", [])

        if not budgets:
            ctx.output.print_info("No budgets configured")
            return

        data = []
        for b in budgets:
            if b["BudgetType"] != "COST":
                continue

            budget_name = b["BudgetName"]
            limit = float(b.get("BudgetLimit", {}).get("Amount", 0))

            # Get forecasted spend
            forecasted = b.get("CalculatedSpend", {}).get("ForecastedSpend", {})
            forecast_amount = float(forecasted.get("Amount", 0))

            # Calculate projected overage
            projected_pct = (forecast_amount / limit * 100) if limit > 0 else 0
            overage = max(0, forecast_amount - limit)

            status = "ON_TRACK" if projected_pct <= 100 else "PROJECTED_OVERAGE"

            data.append({
                "Budget": budget_name[:25],
                "Limit": format_cost(limit, "USD"),
                "Forecast": format_cost(forecast_amount, "USD"),
                "Projected": f"{projected_pct:.1f}%",
                "Overage": format_cost(overage, "USD") if overage > 0 else "-",
                "Status": status,
            })

        ctx.output.print_data(
            data,
            headers=["Budget", "Limit", "Forecast", "Projected", "Overage", "Status"],
            title="Budget Forecast",
        )

    except ClientError as e:
        raise AWSError(f"Failed to get budget forecast: {e}")
