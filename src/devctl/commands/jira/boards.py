"""Jira board commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import JiraError


@click.group()
@pass_context
def boards(ctx: DevCtlContext) -> None:
    """Board operations - list, view, backlog.

    \b
    Examples:
        devctl jira boards list
        devctl jira boards list --project PROJ
        devctl jira boards get 123
        devctl jira boards backlog 123
    """
    pass


@boards.command("list")
@click.option("--project", "-p", help="Filter by project key")
@click.option("--type", "board_type", type=click.Choice(["scrum", "kanban"]), help="Filter by board type")
@click.option("--max", "max_results", default=50, help="Maximum results")
@pass_context
def list_boards(
    ctx: DevCtlContext,
    project: str | None,
    board_type: str | None,
    max_results: int,
) -> None:
    """List agile boards.

    \b
    Examples:
        devctl jira boards list
        devctl jira boards list --project PROJ
        devctl jira boards list --type scrum
    """
    if ctx.dry_run:
        ctx.log_dry_run("list boards", {"project": project, "type": board_type})
        return

    try:
        result = ctx.jira.list_boards(
            project_key=project,
            board_type=board_type,
            max_results=max_results,
        )

        boards_data = []
        for board in result.get("values", []):
            boards_data.append({
                "id": board["id"],
                "name": board["name"],
                "type": board.get("type", ""),
                "project": board.get("location", {}).get("projectKey", ""),
            })

        ctx.output.print_data(
            boards_data,
            title=f"Boards ({result.get('total', len(boards_data))} total)",
            columns=["id", "name", "type", "project"],
        )

    except JiraError as e:
        ctx.output.print_error(f"Failed to list boards: {e}")
        raise click.Abort()


@boards.command("get")
@click.argument("board_id", type=int)
@pass_context
def get_board(ctx: DevCtlContext, board_id: int) -> None:
    """Get board details.

    \b
    Examples:
        devctl jira boards get 123
    """
    if ctx.dry_run:
        ctx.log_dry_run("get board", {"board_id": board_id})
        return

    try:
        board = ctx.jira.get_board(board_id)
        config = ctx.jira.get_board_configuration(board_id)

        board_data = {
            "id": board["id"],
            "name": board["name"],
            "type": board.get("type", ""),
            "project": board.get("location", {}).get("projectKey", ""),
            "project_name": board.get("location", {}).get("displayName", ""),
            "filter_id": config.get("filter", {}).get("id", ""),
        }

        # Add column info
        columns = config.get("columnConfig", {}).get("columns", [])
        board_data["columns"] = ", ".join(c["name"] for c in columns)

        ctx.output.print_data(board_data, title=f"Board: {board['name']}")

    except JiraError as e:
        ctx.output.print_error(f"Failed to get board: {e}")
        raise click.Abort()


@boards.command("backlog")
@click.argument("board_id", type=int)
@click.option("--jql", help="Additional JQL filter")
@click.option("--max", "max_results", default=50, help="Maximum results")
@pass_context
def get_backlog(
    ctx: DevCtlContext,
    board_id: int,
    jql: str | None,
    max_results: int,
) -> None:
    """Get issues in the backlog.

    \b
    Examples:
        devctl jira boards backlog 123
        devctl jira boards backlog 123 --jql "priority = High"
    """
    if ctx.dry_run:
        ctx.log_dry_run("get backlog", {"board_id": board_id})
        return

    try:
        result = ctx.jira.get_backlog_issues(board_id, max_results=max_results, jql=jql)

        issues_data = []
        for issue in result.get("issues", []):
            fields = issue.get("fields", {})
            issues_data.append({
                "key": issue["key"],
                "type": fields.get("issuetype", {}).get("name", ""),
                "priority": fields.get("priority", {}).get("name", "") if fields.get("priority") else "",
                "summary": fields.get("summary", "")[:50],
                "assignee": fields.get("assignee", {}).get("displayName", "Unassigned") if fields.get("assignee") else "Unassigned",
            })

        ctx.output.print_data(
            issues_data,
            title=f"Backlog ({result.get('total', len(issues_data))} issues)",
            columns=["key", "type", "priority", "assignee", "summary"],
        )

    except JiraError as e:
        ctx.output.print_error(f"Failed to get backlog: {e}")
        raise click.Abort()


@boards.command("move-to-backlog")
@click.argument("issue_keys", nargs=-1, required=True)
@pass_context
def move_to_backlog(ctx: DevCtlContext, issue_keys: tuple[str, ...]) -> None:
    """Move issues to backlog.

    \b
    Examples:
        devctl jira boards move-to-backlog PROJ-123
        devctl jira boards move-to-backlog PROJ-123 PROJ-124 PROJ-125
    """
    if ctx.dry_run:
        ctx.log_dry_run("move to backlog", {"issues": issue_keys})
        return

    try:
        ctx.jira.move_issues_to_backlog(list(issue_keys))
        ctx.output.print_success(f"Moved {len(issue_keys)} issue(s) to backlog")

    except JiraError as e:
        ctx.output.print_error(f"Failed to move issues: {e}")
        raise click.Abort()
