"""GitHub Pull Request commands."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import GitHubError
from devctl.commands.github.repos import parse_repo


@click.group()
@pass_context
def prs(ctx: DevCtlContext) -> None:
    """Pull request operations - list, create, merge.

    \b
    Examples:
        devctl github prs list owner/repo
        devctl github prs create owner/repo "My PR" --head feature-branch
        devctl github prs merge owner/repo 123
    """
    pass


@prs.command("list")
@click.argument("repo")
@click.option("--state", type=click.Choice(["open", "closed", "all"]), default="open", help="PR state filter")
@click.option("--base", help="Filter by base branch")
@click.option("--limit", type=int, default=30, help="Maximum PRs to show")
@pass_context
def list_prs(
    ctx: DevCtlContext,
    repo: str,
    state: str,
    base: str | None,
    limit: int,
) -> None:
    """List pull requests."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github
        pulls = client.list_pulls(owner, repo_name, state=state, base=base)[:limit]

        if not pulls:
            ctx.output.print_info("No pull requests found")
            return

        data = []
        for pr in pulls:
            state_val = pr.get("state", "-")
            merged = pr.get("merged_at") is not None

            if merged:
                state_display = "[magenta]merged[/magenta]"
            elif state_val == "open":
                state_display = "[green]open[/green]"
            else:
                state_display = "[red]closed[/red]"

            data.append({
                "Number": f"#{pr['number']}",
                "Title": pr.get("title", "-")[:40],
                "State": state_display,
                "Author": pr.get("user", {}).get("login", "-")[:15],
                "Branch": pr.get("head", {}).get("ref", "-")[:20],
                "Updated": pr.get("updated_at", "-")[:10],
            })

        ctx.output.print_data(
            data,
            headers=["Number", "Title", "State", "Author", "Branch", "Updated"],
            title=f"Pull Requests ({len(data)} shown)",
        )

    except Exception as e:
        raise GitHubError(f"Failed to list pull requests: {e}")


@prs.command("create")
@click.argument("repo")
@click.argument("title")
@click.option("--head", required=True, help="Head branch (source)")
@click.option("--base", default="main", help="Base branch (target)")
@click.option("--body", "-b", help="PR description")
@click.option("--draft", is_flag=True, help="Create as draft")
@pass_context
def create_pr(
    ctx: DevCtlContext,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str | None,
    draft: bool,
) -> None:
    """Create a pull request."""
    owner, repo_name = parse_repo(repo, ctx)

    if ctx.dry_run:
        ctx.log_dry_run("create pull request", {
            "repo": f"{owner}/{repo_name}",
            "title": title,
            "head": head,
            "base": base,
        })
        return

    try:
        client = ctx.github
        result = client.create_pull(
            owner,
            repo_name,
            title=title,
            head=head,
            base=base,
            body=body,
            draft=draft,
        )

        ctx.output.print_success(f"Pull request created: #{result['number']}")
        ctx.output.print_info(f"URL: {result.get('html_url', '-')}")

    except Exception as e:
        raise GitHubError(f"Failed to create pull request: {e}")


@prs.command("merge")
@click.argument("repo")
@click.argument("number", type=int)
@click.option("--method", type=click.Choice(["merge", "squash", "rebase"]), default="merge", help="Merge method")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@pass_context
def merge_pr(
    ctx: DevCtlContext,
    repo: str,
    number: int,
    method: str,
    yes: bool,
) -> None:
    """Merge a pull request."""
    owner, repo_name = parse_repo(repo, ctx)

    if ctx.dry_run:
        ctx.log_dry_run("merge pull request", {
            "repo": f"{owner}/{repo_name}",
            "number": number,
            "method": method,
        })
        return

    if not yes:
        if not ctx.confirm(f"Merge PR #{number} using {method}?"):
            ctx.output.print_info("Cancelled")
            return

    try:
        client = ctx.github
        result = client.merge_pull(owner, repo_name, number, merge_method=method)

        ctx.output.print_success(f"Pull request #{number} merged")
        ctx.output.print_info(f"SHA: {result.get('sha', '-')}")

    except Exception as e:
        raise GitHubError(f"Failed to merge pull request: {e}")


@prs.command("get")
@click.argument("repo")
@click.argument("number", type=int)
@pass_context
def get_pr(ctx: DevCtlContext, repo: str, number: int) -> None:
    """Get pull request details."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github
        pr = client.get(f"/repos/{owner}/{repo_name}/pulls/{number}")

        merged = pr.get("merged_at") is not None
        state = "merged" if merged else pr.get("state", "-")

        data = {
            "Number": f"#{pr['number']}",
            "Title": pr.get("title", "-"),
            "State": state,
            "Author": pr.get("user", {}).get("login", "-"),
            "Head": pr.get("head", {}).get("ref", "-"),
            "Base": pr.get("base", {}).get("ref", "-"),
            "Created": pr.get("created_at", "-")[:10],
            "Updated": pr.get("updated_at", "-")[:10],
            "Commits": pr.get("commits", 0),
            "Additions": pr.get("additions", 0),
            "Deletions": pr.get("deletions", 0),
            "Changed Files": pr.get("changed_files", 0),
            "Mergeable": "Yes" if pr.get("mergeable") else "No" if pr.get("mergeable") is False else "Unknown",
            "Draft": "Yes" if pr.get("draft") else "No",
        }

        ctx.output.print_data(data, title=f"Pull Request #{number}")

        # Show body
        body = pr.get("body")
        if body and ctx.verbose >= 1:
            ctx.output.print_panel(body[:500], title="Description")

        # Show labels
        labels = pr.get("labels", [])
        if labels:
            label_names = [l.get("name", "-") for l in labels]
            ctx.output.print_info(f"Labels: {', '.join(label_names)}")

        # Show reviewers
        reviewers = pr.get("requested_reviewers", [])
        if reviewers:
            reviewer_names = [r.get("login", "-") for r in reviewers]
            ctx.output.print_info(f"Reviewers: {', '.join(reviewer_names)}")

        ctx.output.print_info(f"URL: {pr.get('html_url', '-')}")

    except Exception as e:
        raise GitHubError(f"Failed to get pull request: {e}")


@prs.command("issues")
@click.argument("repo")
@click.option("--state", type=click.Choice(["open", "closed", "all"]), default="open", help="Issue state")
@click.option("--label", multiple=True, help="Filter by labels")
@click.option("--limit", type=int, default=30, help="Maximum issues to show")
@pass_context
def list_issues(
    ctx: DevCtlContext,
    repo: str,
    state: str,
    label: tuple[str, ...],
    limit: int,
) -> None:
    """List repository issues."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github
        issues = client.list_issues(
            owner,
            repo_name,
            state=state,
            labels=list(label) if label else None,
        )

        # Filter out pull requests (they show up in issues API)
        issues = [i for i in issues if "pull_request" not in i][:limit]

        if not issues:
            ctx.output.print_info("No issues found")
            return

        data = []
        for issue in issues:
            state_val = issue.get("state", "-")
            state_display = "[green]open[/green]" if state_val == "open" else "[red]closed[/red]"

            labels = issue.get("labels", [])
            label_str = ", ".join(l.get("name", "") for l in labels[:2])

            data.append({
                "Number": f"#{issue['number']}",
                "Title": issue.get("title", "-")[:40],
                "State": state_display,
                "Author": issue.get("user", {}).get("login", "-")[:15],
                "Labels": label_str[:20] or "-",
                "Updated": issue.get("updated_at", "-")[:10],
            })

        ctx.output.print_data(
            data,
            headers=["Number", "Title", "State", "Author", "Labels", "Updated"],
            title=f"Issues ({len(data)} shown)",
        )

    except Exception as e:
        raise GitHubError(f"Failed to list issues: {e}")
