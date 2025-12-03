"""GitHub repository commands."""

import subprocess

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import GitHubError


def parse_repo(repo: str, ctx: DevCtlContext) -> tuple[str, str]:
    """Parse owner/repo string, using configured org as default owner."""
    if "/" in repo:
        parts = repo.split("/")
        return parts[0], parts[1]
    else:
        org = ctx.github.org
        if not org:
            raise click.BadParameter(
                "Repository must be in owner/repo format or configure a default org"
            )
        return org, repo


@click.group()
@pass_context
def repos(ctx: DevCtlContext) -> None:
    """Repository operations - list, clone, create.

    \b
    Examples:
        devctl github repos list
        devctl github repos clone owner/repo
        devctl github repos create new-repo --private
    """
    pass


@repos.command("list")
@click.option("--org", help="Organization (default: configured org)")
@click.option("--visibility", type=click.Choice(["public", "private", "all"]), default="all", help="Visibility filter")
@click.option("--archived", is_flag=True, help="Include archived repos")
@click.option("--limit", type=int, default=50, help="Maximum repos to show")
@pass_context
def list_repos(
    ctx: DevCtlContext,
    org: str | None,
    visibility: str,
    archived: bool,
    limit: int,
) -> None:
    """List repositories."""
    try:
        client = ctx.github

        repos_list = client.list_repos(
            org=org,
            visibility=visibility if visibility != "all" else None,
            archived=True if archived else None,
        )

        # Filter archived if not requested
        if not archived:
            repos_list = [r for r in repos_list if not r.get("archived")]

        repos_list = repos_list[:limit]

        if not repos_list:
            ctx.output.print_info("No repositories found")
            return

        data = []
        for repo in repos_list:
            visibility_icon = "[red]Private[/red]" if repo.get("private") else "[green]Public[/green]"
            archived_str = " [dim](archived)[/dim]" if repo.get("archived") else ""

            data.append({
                "Name": repo["full_name"],
                "Visibility": visibility_icon,
                "Stars": repo.get("stargazers_count", 0),
                "Language": repo.get("language", "-") or "-",
                "Updated": repo.get("updated_at", "-")[:10],
            })

        ctx.output.print_data(
            data,
            headers=["Name", "Visibility", "Stars", "Language", "Updated"],
            title=f"Repositories ({len(data)} shown)",
        )

    except Exception as e:
        raise GitHubError(f"Failed to list repositories: {e}")


@repos.command("clone")
@click.argument("repo")
@click.option("--shallow", is_flag=True, help="Shallow clone (--depth 1)")
@click.option("--directory", "-d", help="Target directory")
@pass_context
def clone_repo(ctx: DevCtlContext, repo: str, shallow: bool, directory: str | None) -> None:
    """Clone a repository.

    REPO should be in owner/repo format.
    """
    owner, repo_name = parse_repo(repo, ctx)
    full_name = f"{owner}/{repo_name}"

    if ctx.dry_run:
        ctx.log_dry_run("clone repository", {"repo": full_name, "shallow": shallow})
        return

    try:
        # Build git clone command
        clone_url = f"https://github.com/{full_name}.git"
        cmd = ["git", "clone"]

        if shallow:
            cmd.extend(["--depth", "1"])

        cmd.append(clone_url)

        if directory:
            cmd.append(directory)

        ctx.output.print_info(f"Cloning {full_name}...")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise GitHubError(f"Clone failed: {result.stderr}")

        ctx.output.print_success(f"Cloned {full_name}")

    except FileNotFoundError:
        raise GitHubError("Git not found. Please install git.")
    except Exception as e:
        raise GitHubError(f"Failed to clone repository: {e}")


@repos.command("create")
@click.argument("name")
@click.option("--private", "is_private", is_flag=True, help="Create as private repo")
@click.option("--description", "-d", help="Repository description")
@click.option("--org", help="Organization (default: user account)")
@pass_context
def create_repo(
    ctx: DevCtlContext,
    name: str,
    is_private: bool,
    description: str | None,
    org: str | None,
) -> None:
    """Create a new repository."""
    if ctx.dry_run:
        ctx.log_dry_run("create repository", {
            "name": name,
            "private": is_private,
            "org": org or "user",
        })
        return

    try:
        client = ctx.github

        result = client.create_repo(
            name=name,
            private=is_private,
            description=description,
            org=org,
        )

        ctx.output.print_success(f"Repository created: {result['full_name']}")
        ctx.output.print_info(f"URL: {result.get('html_url', '-')}")

    except Exception as e:
        raise GitHubError(f"Failed to create repository: {e}")


@repos.command("get")
@click.argument("repo")
@pass_context
def get_repo(ctx: DevCtlContext, repo: str) -> None:
    """Get repository details."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github
        repo_data = client.get_repo(owner, repo_name)

        data = {
            "Name": repo_data["full_name"],
            "Description": repo_data.get("description", "-") or "-",
            "URL": repo_data.get("html_url", "-"),
            "Visibility": "Private" if repo_data.get("private") else "Public",
            "Default Branch": repo_data.get("default_branch", "-"),
            "Stars": repo_data.get("stargazers_count", 0),
            "Forks": repo_data.get("forks_count", 0),
            "Open Issues": repo_data.get("open_issues_count", 0),
            "Language": repo_data.get("language", "-") or "-",
            "Created": repo_data.get("created_at", "-")[:10],
            "Updated": repo_data.get("updated_at", "-")[:10],
            "Archived": "Yes" if repo_data.get("archived") else "No",
        }

        ctx.output.print_data(data, title=f"Repository: {repo_data['full_name']}")

        # Show topics
        topics = repo_data.get("topics", [])
        if topics:
            ctx.output.print_info(f"Topics: {', '.join(topics)}")

    except Exception as e:
        raise GitHubError(f"Failed to get repository: {e}")
