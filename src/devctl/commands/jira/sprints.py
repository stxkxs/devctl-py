"""Jira sprint commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import JiraError


@click.group()
@pass_context
def sprints(ctx: DevCtlContext) -> None:
    """Sprint operations - list, view, issues.

    \b
    Examples:
        devctl jira sprints list --board 123
        devctl jira sprints get 456
        devctl jira sprints issues 456
        devctl jira sprints move 456 PROJ-123 PROJ-124
    """
    pass


@sprints.command("list")
@click.option("--board", "-b", "board_id", type=int, required=True, help="Board ID")
@click.option(
    "--state",
    type=click.Choice(["active", "closed", "future"]),
    help="Filter by state",
)
@click.option("--max", "max_results", default=50, help="Maximum results")
@pass_context
def list_sprints(
    ctx: DevCtlContext,
    board_id: int,
    state: str | None,
    max_results: int,
) -> None:
    """List sprints for a board.

    \b
    Examples:
        devctl jira sprints list --board 123
        devctl jira sprints list --board 123 --state active
        devctl jira sprints list --board 123 --state future
    """
    if ctx.dry_run:
        ctx.log_dry_run("list sprints", {"board_id": board_id, "state": state})
        return

    try:
        result = ctx.jira.list_sprints(board_id, state=state, max_results=max_results)

        sprints_data = []
        for sprint in result.get("values", []):
            sprints_data.append({
                "id": sprint["id"],
                "name": sprint["name"],
                "state": sprint.get("state", ""),
                "start": sprint.get("startDate", "")[:10] if sprint.get("startDate") else "",
                "end": sprint.get("endDate", "")[:10] if sprint.get("endDate") else "",
                "goal": sprint.get("goal", "")[:40] if sprint.get("goal") else "",
            })

        ctx.output.print_data(
            sprints_data,
            title=f"Sprints ({len(sprints_data)} total)",
            columns=["id", "name", "state", "start", "end", "goal"],
        )

    except JiraError as e:
        ctx.output.print_error(f"Failed to list sprints: {e}")
        raise click.Abort()


@sprints.command("get")
@click.argument("sprint_id", type=int)
@pass_context
def get_sprint(ctx: DevCtlContext, sprint_id: int) -> None:
    """Get sprint details.

    \b
    Examples:
        devctl jira sprints get 456
    """
    if ctx.dry_run:
        ctx.log_dry_run("get sprint", {"sprint_id": sprint_id})
        return

    try:
        sprint = ctx.jira.get_sprint(sprint_id)

        sprint_data = {
            "id": sprint["id"],
            "name": sprint["name"],
            "state": sprint.get("state", ""),
            "start_date": sprint.get("startDate", ""),
            "end_date": sprint.get("endDate", ""),
            "complete_date": sprint.get("completeDate", ""),
            "goal": sprint.get("goal", ""),
            "board_id": sprint.get("originBoardId", ""),
        }

        ctx.output.print_data(sprint_data, title=f"Sprint: {sprint['name']}")

    except JiraError as e:
        ctx.output.print_error(f"Failed to get sprint: {e}")
        raise click.Abort()


@sprints.command("issues")
@click.argument("sprint_id", type=int)
@click.option("--jql", help="Additional JQL filter")
@click.option("--max", "max_results", default=50, help="Maximum results")
@pass_context
def get_sprint_issues(
    ctx: DevCtlContext,
    sprint_id: int,
    jql: str | None,
    max_results: int,
) -> None:
    """Get issues in a sprint.

    \b
    Examples:
        devctl jira sprints issues 456
        devctl jira sprints issues 456 --jql "status = Done"
    """
    if ctx.dry_run:
        ctx.log_dry_run("get sprint issues", {"sprint_id": sprint_id})
        return

    try:
        result = ctx.jira.get_sprint_issues(sprint_id, max_results=max_results, jql=jql)

        issues_data = []
        for issue in result.get("issues", []):
            fields = issue.get("fields", {})
            issues_data.append({
                "key": issue["key"],
                "type": fields.get("issuetype", {}).get("name", ""),
                "status": fields.get("status", {}).get("name", ""),
                "priority": fields.get("priority", {}).get("name", "") if fields.get("priority") else "",
                "points": fields.get("customfield_10016", ""),  # Story points (varies by instance)
                "assignee": fields.get("assignee", {}).get("displayName", "Unassigned") if fields.get("assignee") else "Unassigned",
                "summary": fields.get("summary", "")[:40],
            })

        ctx.output.print_data(
            issues_data,
            title=f"Sprint Issues ({result.get('total', len(issues_data))} total)",
            columns=["key", "type", "status", "priority", "assignee", "summary"],
        )

    except JiraError as e:
        ctx.output.print_error(f"Failed to get sprint issues: {e}")
        raise click.Abort()


@sprints.command("move")
@click.argument("sprint_id", type=int)
@click.argument("issue_keys", nargs=-1, required=True)
@pass_context
def move_to_sprint(
    ctx: DevCtlContext,
    sprint_id: int,
    issue_keys: tuple[str, ...],
) -> None:
    """Move issues to a sprint.

    \b
    Examples:
        devctl jira sprints move 456 PROJ-123
        devctl jira sprints move 456 PROJ-123 PROJ-124 PROJ-125
    """
    if ctx.dry_run:
        ctx.log_dry_run("move to sprint", {"sprint_id": sprint_id, "issues": issue_keys})
        return

    try:
        ctx.jira.move_issues_to_sprint(sprint_id, list(issue_keys))
        ctx.output.print_success(f"Moved {len(issue_keys)} issue(s) to sprint {sprint_id}")

    except JiraError as e:
        ctx.output.print_error(f"Failed to move issues: {e}")
        raise click.Abort()


@sprints.command("active")
@click.option("--board", "-b", "board_id", type=int, required=True, help="Board ID")
@pass_context
def get_active_sprint(ctx: DevCtlContext, board_id: int) -> None:
    """Get the active sprint for a board.

    \b
    Examples:
        devctl jira sprints active --board 123
    """
    if ctx.dry_run:
        ctx.log_dry_run("get active sprint", {"board_id": board_id})
        return

    try:
        result = ctx.jira.list_sprints(board_id, state="active", max_results=1)

        sprints = result.get("values", [])
        if not sprints:
            ctx.output.print_info("No active sprint found")
            return

        sprint = sprints[0]

        # Get sprint issues for summary
        issues_result = ctx.jira.get_sprint_issues(sprint["id"], max_results=100)
        issues = issues_result.get("issues", [])

        # Calculate status breakdown
        status_counts: dict[str, int] = {}
        for issue in issues:
            status = issue.get("fields", {}).get("status", {}).get("name", "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        sprint_data = {
            "id": sprint["id"],
            "name": sprint["name"],
            "start": sprint.get("startDate", "")[:10] if sprint.get("startDate") else "",
            "end": sprint.get("endDate", "")[:10] if sprint.get("endDate") else "",
            "goal": sprint.get("goal", ""),
            "total_issues": len(issues),
            "status_breakdown": ", ".join(f"{k}: {v}" for k, v in sorted(status_counts.items())),
        }

        ctx.output.print_data(sprint_data, title=f"Active Sprint: {sprint['name']}")

    except JiraError as e:
        ctx.output.print_error(f"Failed to get active sprint: {e}")
        raise click.Abort()
