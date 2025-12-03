"""Jira issue commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import JiraError


@click.group()
@pass_context
def issues(ctx: DevCtlContext) -> None:
    """Issue operations - search, create, update, transition.

    \b
    Examples:
        devctl jira issues search "project = PROJ AND status = Open"
        devctl jira issues get PROJ-123
        devctl jira issues create PROJ "Fix bug" --type Bug
        devctl jira issues transition PROJ-123 "In Progress"
    """
    pass


@issues.command("search")
@click.argument("jql")
@click.option("--max", "max_results", default=50, help="Maximum results to return")
@click.option("--fields", help="Comma-separated fields to return")
@pass_context
def search_issues(
    ctx: DevCtlContext,
    jql: str,
    max_results: int,
    fields: str | None,
) -> None:
    """Search issues using JQL.

    \b
    Examples:
        devctl jira issues search "project = PROJ"
        devctl jira issues search "assignee = currentUser() AND status != Done"
        devctl jira issues search "sprint in openSprints()" --max 100
    """
    if ctx.dry_run:
        ctx.log_dry_run("search issues", {"jql": jql, "max_results": max_results})
        return

    try:
        field_list = fields.split(",") if fields else None
        result = ctx.jira.search_issues(jql, max_results=max_results, fields=field_list)

        issues_data = []
        for issue in result.get("issues", []):
            fields_data = issue.get("fields", {})
            issues_data.append({
                "key": issue["key"],
                "type": fields_data.get("issuetype", {}).get("name", ""),
                "status": fields_data.get("status", {}).get("name", ""),
                "priority": fields_data.get("priority", {}).get("name", "") if fields_data.get("priority") else "",
                "summary": fields_data.get("summary", "")[:60],
                "assignee": fields_data.get("assignee", {}).get("displayName", "Unassigned") if fields_data.get("assignee") else "Unassigned",
            })

        ctx.output.print_data(
            issues_data,
            title=f"Issues ({result.get('total', 0)} total)",
            columns=["key", "type", "status", "priority", "assignee", "summary"],
        )

    except JiraError as e:
        ctx.output.print_error(f"Failed to search issues: {e}")
        raise click.Abort()


@issues.command("get")
@click.argument("issue_key")
@pass_context
def get_issue(ctx: DevCtlContext, issue_key: str) -> None:
    """Get issue details.

    \b
    Examples:
        devctl jira issues get PROJ-123
    """
    if ctx.dry_run:
        ctx.log_dry_run("get issue", {"issue_key": issue_key})
        return

    try:
        issue = ctx.jira.get_issue(issue_key)
        fields = issue.get("fields", {})

        # Extract description text from ADF format
        description = ""
        if fields.get("description"):
            desc_content = fields["description"].get("content", [])
            for block in desc_content:
                if block.get("type") == "paragraph":
                    for content in block.get("content", []):
                        if content.get("type") == "text":
                            description += content.get("text", "")
                    description += "\n"

        issue_data = {
            "key": issue["key"],
            "summary": fields.get("summary", ""),
            "type": fields.get("issuetype", {}).get("name", ""),
            "status": fields.get("status", {}).get("name", ""),
            "priority": fields.get("priority", {}).get("name", "") if fields.get("priority") else "",
            "assignee": fields.get("assignee", {}).get("displayName", "Unassigned") if fields.get("assignee") else "Unassigned",
            "reporter": fields.get("reporter", {}).get("displayName", "") if fields.get("reporter") else "",
            "project": fields.get("project", {}).get("key", ""),
            "labels": ", ".join(fields.get("labels", [])),
            "created": fields.get("created", "")[:10],
            "updated": fields.get("updated", "")[:10],
            "description": description.strip()[:200] + "..." if len(description.strip()) > 200 else description.strip(),
        }

        ctx.output.print_data(issue_data, title=f"Issue: {issue_key}")

    except JiraError as e:
        ctx.output.print_error(f"Failed to get issue: {e}")
        raise click.Abort()


@issues.command("create")
@click.argument("project_key")
@click.argument("summary")
@click.option("--type", "issue_type", default="Task", help="Issue type (Task, Bug, Story, etc.)")
@click.option("--description", "-d", help="Issue description")
@click.option("--priority", "-p", help="Priority (Highest, High, Medium, Low, Lowest)")
@click.option("--label", "-l", "labels", multiple=True, help="Labels (can be repeated)")
@click.option("--parent", help="Parent issue key (for subtasks)")
@pass_context
def create_issue(
    ctx: DevCtlContext,
    project_key: str,
    summary: str,
    issue_type: str,
    description: str | None,
    priority: str | None,
    labels: tuple[str, ...],
    parent: str | None,
) -> None:
    """Create a new issue.

    \b
    Examples:
        devctl jira issues create PROJ "Fix login bug" --type Bug
        devctl jira issues create PROJ "New feature" --type Story -d "Description here"
        devctl jira issues create PROJ "Subtask" --type Sub-task --parent PROJ-123
    """
    if ctx.dry_run:
        ctx.log_dry_run("create issue", {
            "project": project_key,
            "summary": summary,
            "type": issue_type,
        })
        return

    try:
        result = ctx.jira.create_issue(
            project_key=project_key,
            summary=summary,
            issue_type=issue_type,
            description=description,
            priority=priority,
            labels=list(labels) if labels else None,
            parent_key=parent,
        )

        ctx.output.print_success(f"Created issue: {result['key']}")
        ctx.output.print_data({
            "key": result["key"],
            "url": f"{ctx.jira._config.get_url()}/browse/{result['key']}",
        })

    except JiraError as e:
        ctx.output.print_error(f"Failed to create issue: {e}")
        raise click.Abort()


@issues.command("update")
@click.argument("issue_key")
@click.option("--summary", "-s", help="New summary")
@click.option("--description", "-d", help="New description")
@click.option("--priority", "-p", help="New priority")
@click.option("--add-label", "add_labels", multiple=True, help="Labels to add")
@click.option("--remove-label", "remove_labels", multiple=True, help="Labels to remove")
@pass_context
def update_issue(
    ctx: DevCtlContext,
    issue_key: str,
    summary: str | None,
    description: str | None,
    priority: str | None,
    add_labels: tuple[str, ...],
    remove_labels: tuple[str, ...],
) -> None:
    """Update an issue.

    \b
    Examples:
        devctl jira issues update PROJ-123 --summary "New title"
        devctl jira issues update PROJ-123 --priority High
        devctl jira issues update PROJ-123 --add-label urgent --add-label backend
    """
    if ctx.dry_run:
        ctx.log_dry_run("update issue", {"issue_key": issue_key})
        return

    try:
        fields: dict = {}
        update: dict = {}

        if summary:
            fields["summary"] = summary

        if description:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }

        if priority:
            fields["priority"] = {"name": priority}

        if add_labels:
            update["labels"] = [{"add": label} for label in add_labels]

        if remove_labels:
            if "labels" not in update:
                update["labels"] = []
            update["labels"].extend([{"remove": label} for label in remove_labels])

        if fields or update:
            ctx.jira.update_issue(issue_key, fields=fields if fields else None, update=update if update else None)
            ctx.output.print_success(f"Updated issue: {issue_key}")
        else:
            ctx.output.print_warning("No updates specified")

    except JiraError as e:
        ctx.output.print_error(f"Failed to update issue: {e}")
        raise click.Abort()


@issues.command("transition")
@click.argument("issue_key")
@click.argument("status", required=False)
@click.option("--list", "list_transitions", is_flag=True, help="List available transitions")
@pass_context
def transition_issue(
    ctx: DevCtlContext,
    issue_key: str,
    status: str | None,
    list_transitions: bool,
) -> None:
    """Transition an issue to a new status.

    \b
    Examples:
        devctl jira issues transition PROJ-123 --list
        devctl jira issues transition PROJ-123 "In Progress"
        devctl jira issues transition PROJ-123 "Done"
    """
    if ctx.dry_run:
        ctx.log_dry_run("transition issue", {"issue_key": issue_key, "status": status})
        return

    try:
        transitions = ctx.jira.get_transitions(issue_key)

        if list_transitions or not status:
            data = [{"id": t["id"], "name": t["name"]} for t in transitions]
            ctx.output.print_data(data, title=f"Available transitions for {issue_key}")
            return

        # Find matching transition
        transition_id = None
        for t in transitions:
            if t["name"].lower() == status.lower():
                transition_id = t["id"]
                break

        if not transition_id:
            available = ", ".join(t["name"] for t in transitions)
            ctx.output.print_error(f"Transition '{status}' not found. Available: {available}")
            raise click.Abort()

        ctx.jira.transition_issue(issue_key, transition_id)
        ctx.output.print_success(f"Transitioned {issue_key} to '{status}'")

    except JiraError as e:
        ctx.output.print_error(f"Failed to transition issue: {e}")
        raise click.Abort()


@issues.command("comment")
@click.argument("issue_key")
@click.argument("body")
@pass_context
def add_comment(ctx: DevCtlContext, issue_key: str, body: str) -> None:
    """Add a comment to an issue.

    \b
    Examples:
        devctl jira issues comment PROJ-123 "Working on this now"
    """
    if ctx.dry_run:
        ctx.log_dry_run("add comment", {"issue_key": issue_key})
        return

    try:
        ctx.jira.add_comment(issue_key, body)
        ctx.output.print_success(f"Added comment to {issue_key}")

    except JiraError as e:
        ctx.output.print_error(f"Failed to add comment: {e}")
        raise click.Abort()


@issues.command("assign")
@click.argument("issue_key")
@click.argument("assignee", required=False)
@click.option("--me", is_flag=True, help="Assign to current user")
@click.option("--unassign", is_flag=True, help="Unassign the issue")
@pass_context
def assign_issue(
    ctx: DevCtlContext,
    issue_key: str,
    assignee: str | None,
    me: bool,
    unassign: bool,
) -> None:
    """Assign an issue to a user.

    \b
    Examples:
        devctl jira issues assign PROJ-123 --me
        devctl jira issues assign PROJ-123 --unassign
        devctl jira issues assign PROJ-123 john@company.com
    """
    if ctx.dry_run:
        ctx.log_dry_run("assign issue", {"issue_key": issue_key})
        return

    try:
        account_id = None

        if unassign:
            pass  # account_id stays None
        elif me:
            myself = ctx.jira.get_myself()
            account_id = myself["accountId"]
        elif assignee:
            # Search for user
            users = ctx.jira.search_users(assignee, max_results=1)
            if not users:
                ctx.output.print_error(f"User not found: {assignee}")
                raise click.Abort()
            account_id = users[0]["accountId"]
        else:
            ctx.output.print_error("Specify --me, --unassign, or a user email")
            raise click.Abort()

        ctx.jira.assign_issue(issue_key, account_id)

        if unassign:
            ctx.output.print_success(f"Unassigned {issue_key}")
        else:
            ctx.output.print_success(f"Assigned {issue_key}")

    except JiraError as e:
        ctx.output.print_error(f"Failed to assign issue: {e}")
        raise click.Abort()


@issues.command("log-work")
@click.argument("issue_key")
@click.argument("time_spent")
@click.option("--comment", "-c", help="Work description")
@pass_context
def log_work(
    ctx: DevCtlContext,
    issue_key: str,
    time_spent: str,
    comment: str | None,
) -> None:
    """Log work on an issue.

    \b
    Examples:
        devctl jira issues log-work PROJ-123 "2h 30m"
        devctl jira issues log-work PROJ-123 "1d" --comment "Completed review"
    """
    if ctx.dry_run:
        ctx.log_dry_run("log work", {"issue_key": issue_key, "time_spent": time_spent})
        return

    try:
        ctx.jira.add_worklog(issue_key, time_spent, comment=comment)
        ctx.output.print_success(f"Logged {time_spent} on {issue_key}")

    except JiraError as e:
        ctx.output.print_error(f"Failed to log work: {e}")
        raise click.Abort()


@issues.command("link")
@click.argument("issue_key")
@click.argument("target_key")
@click.option("--type", "link_type", default="Relates", help="Link type (Relates, Blocks, Duplicates, etc.)")
@pass_context
def link_issues(
    ctx: DevCtlContext,
    issue_key: str,
    target_key: str,
    link_type: str,
) -> None:
    """Link two issues.

    \b
    Examples:
        devctl jira issues link PROJ-123 PROJ-456
        devctl jira issues link PROJ-123 PROJ-456 --type Blocks
    """
    if ctx.dry_run:
        ctx.log_dry_run("link issues", {"from": issue_key, "to": target_key, "type": link_type})
        return

    try:
        ctx.jira.link_issues(issue_key, target_key, link_type)
        ctx.output.print_success(f"Linked {issue_key} -> {target_key} ({link_type})")

    except JiraError as e:
        ctx.output.print_error(f"Failed to link issues: {e}")
        raise click.Abort()


@issues.command("my-issues")
@click.option("--status", help="Filter by status")
@click.option("--project", "-p", help="Filter by project")
@click.option("--max", "max_results", default=25, help="Maximum results")
@pass_context
def my_issues(
    ctx: DevCtlContext,
    status: str | None,
    project: str | None,
    max_results: int,
) -> None:
    """List issues assigned to me.

    \b
    Examples:
        devctl jira issues my-issues
        devctl jira issues my-issues --status "In Progress"
        devctl jira issues my-issues --project PROJ
    """
    if ctx.dry_run:
        ctx.log_dry_run("list my issues")
        return

    try:
        jql_parts = ["assignee = currentUser()"]

        if status:
            jql_parts.append(f'status = "{status}"')
        if project:
            jql_parts.append(f"project = {project}")

        jql = " AND ".join(jql_parts)
        result = ctx.jira.search_issues(jql, max_results=max_results)

        issues_data = []
        for issue in result.get("issues", []):
            fields = issue.get("fields", {})
            issues_data.append({
                "key": issue["key"],
                "type": fields.get("issuetype", {}).get("name", ""),
                "status": fields.get("status", {}).get("name", ""),
                "priority": fields.get("priority", {}).get("name", "") if fields.get("priority") else "",
                "summary": fields.get("summary", "")[:50],
            })

        ctx.output.print_data(
            issues_data,
            title=f"My Issues ({result.get('total', 0)} total)",
            columns=["key", "type", "status", "priority", "summary"],
        )

    except JiraError as e:
        ctx.output.print_error(f"Failed to list issues: {e}")
        raise click.Abort()
