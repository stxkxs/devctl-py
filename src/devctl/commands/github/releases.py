"""GitHub Release commands."""

from pathlib import Path

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import GitHubError
from devctl.core.output import format_bytes
from devctl.commands.github.repos import parse_repo


@click.group()
@pass_context
def releases(ctx: DevCtlContext) -> None:
    """Release operations - list, create, download.

    \b
    Examples:
        devctl github releases list owner/repo
        devctl github releases create owner/repo v1.0.0
        devctl github releases download owner/repo v1.0.0
    """
    pass


@releases.command("list")
@click.argument("repo")
@click.option("--limit", type=int, default=20, help="Maximum releases to show")
@pass_context
def list_releases(ctx: DevCtlContext, repo: str, limit: int) -> None:
    """List repository releases."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github
        releases_list = client.list_releases(owner, repo_name)[:limit]

        if not releases_list:
            ctx.output.print_info("No releases found")
            return

        data = []
        for rel in releases_list:
            tag = rel.get("tag_name", "-")
            name = rel.get("name", "-") or tag

            status = []
            if rel.get("draft"):
                status.append("[yellow]draft[/yellow]")
            if rel.get("prerelease"):
                status.append("[cyan]pre[/cyan]")
            status_str = " ".join(status) if status else "[green]release[/green]"

            assets = rel.get("assets", [])
            asset_count = len(assets)

            data.append({
                "Tag": tag,
                "Name": name[:30],
                "Status": status_str,
                "Assets": asset_count,
                "Published": rel.get("published_at", "-")[:10] if rel.get("published_at") else "-",
                "Author": rel.get("author", {}).get("login", "-")[:15],
            })

        ctx.output.print_data(
            data,
            headers=["Tag", "Name", "Status", "Assets", "Published", "Author"],
            title=f"Releases ({len(data)} shown)",
        )

    except Exception as e:
        raise GitHubError(f"Failed to list releases: {e}")


@releases.command("get")
@click.argument("repo")
@click.argument("tag")
@pass_context
def get_release(ctx: DevCtlContext, repo: str, tag: str) -> None:
    """Get release details by tag."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github
        release = client.get_release(owner, repo_name, tag)

        data = {
            "Tag": release.get("tag_name", "-"),
            "Name": release.get("name", "-"),
            "Draft": "Yes" if release.get("draft") else "No",
            "Prerelease": "Yes" if release.get("prerelease") else "No",
            "Target": release.get("target_commitish", "-"),
            "Published": release.get("published_at", "-")[:19] if release.get("published_at") else "-",
            "Author": release.get("author", {}).get("login", "-"),
        }

        ctx.output.print_data(data, title=f"Release: {tag}")

        # Show release notes
        body = release.get("body")
        if body:
            ctx.output.print_panel(body[:1000], title="Release Notes")

        # Show assets
        assets = release.get("assets", [])
        if assets:
            asset_data = []
            for asset in assets:
                asset_data.append({
                    "Name": asset.get("name", "-"),
                    "Size": format_bytes(asset.get("size", 0)),
                    "Downloads": asset.get("download_count", 0),
                })
            ctx.output.print_data(asset_data, headers=["Name", "Size", "Downloads"], title="Assets")

        ctx.output.print_info(f"URL: {release.get('html_url', '-')}")

    except Exception as e:
        raise GitHubError(f"Failed to get release: {e}")


@releases.command("create")
@click.argument("repo")
@click.argument("tag")
@click.option("--name", "-n", help="Release name (default: tag)")
@click.option("--notes", help="Release notes")
@click.option("--notes-file", type=click.Path(exists=True), help="File containing release notes")
@click.option("--draft", is_flag=True, help="Create as draft")
@click.option("--prerelease", is_flag=True, help="Mark as prerelease")
@click.option("--target", default="main", help="Target branch/commit")
@pass_context
def create_release(
    ctx: DevCtlContext,
    repo: str,
    tag: str,
    name: str | None,
    notes: str | None,
    notes_file: str | None,
    draft: bool,
    prerelease: bool,
    target: str,
) -> None:
    """Create a new release."""
    owner, repo_name = parse_repo(repo, ctx)

    # Get notes from file if specified
    if notes_file:
        notes = Path(notes_file).read_text()

    if ctx.dry_run:
        ctx.log_dry_run("create release", {
            "repo": f"{owner}/{repo_name}",
            "tag": tag,
            "name": name or tag,
            "draft": draft,
        })
        return

    try:
        client = ctx.github
        result = client.create_release(
            owner,
            repo_name,
            tag_name=tag,
            name=name,
            body=notes,
            draft=draft,
            prerelease=prerelease,
        )

        ctx.output.print_success(f"Release created: {result.get('tag_name')}")
        ctx.output.print_info(f"URL: {result.get('html_url', '-')}")

    except Exception as e:
        raise GitHubError(f"Failed to create release: {e}")


@releases.command("download")
@click.argument("repo")
@click.argument("tag")
@click.option("--output", "-o", type=click.Path(), default=".", help="Output directory")
@click.option("--asset", "-a", help="Specific asset to download (default: all)")
@pass_context
def download_release(
    ctx: DevCtlContext,
    repo: str,
    tag: str,
    output: str,
    asset: str | None,
) -> None:
    """Download release assets."""
    owner, repo_name = parse_repo(repo, ctx)

    try:
        client = ctx.github
        release = client.get_release(owner, repo_name, tag)

        assets = release.get("assets", [])

        if not assets:
            ctx.output.print_info("No assets to download")
            return

        if asset:
            assets = [a for a in assets if a.get("name") == asset]
            if not assets:
                raise GitHubError(f"Asset not found: {asset}")

        output_dir = Path(output)
        output_dir.mkdir(parents=True, exist_ok=True)

        if ctx.dry_run:
            for a in assets:
                ctx.log_dry_run("download asset", {
                    "name": a.get("name"),
                    "size": format_bytes(a.get("size", 0)),
                })
            return

        ctx.output.print_info(f"Downloading {len(assets)} asset(s)...")

        import httpx

        for a in assets:
            name = a.get("name", "unknown")
            url = a.get("browser_download_url")

            if not url:
                ctx.output.print_warning(f"No download URL for {name}")
                continue

            ctx.output.print(f"  Downloading {name}...")

            response = httpx.get(url, follow_redirects=True)
            response.raise_for_status()

            output_path = output_dir / name
            output_path.write_bytes(response.content)

        ctx.output.print_success(f"Downloaded {len(assets)} asset(s) to {output_dir}")

    except Exception as e:
        raise GitHubError(f"Failed to download release: {e}")


@releases.command("delete")
@click.argument("repo")
@click.argument("tag")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@pass_context
def delete_release(ctx: DevCtlContext, repo: str, tag: str, yes: bool) -> None:
    """Delete a release by tag."""
    owner, repo_name = parse_repo(repo, ctx)

    if ctx.dry_run:
        ctx.log_dry_run("delete release", {"repo": f"{owner}/{repo_name}", "tag": tag})
        return

    if not yes:
        if not ctx.confirm(f"Delete release {tag}?"):
            ctx.output.print_info("Cancelled")
            return

    try:
        client = ctx.github
        release = client.get_release(owner, repo_name, tag)
        release_id = release.get("id")

        client.delete(f"/repos/{owner}/{repo_name}/releases/{release_id}")
        ctx.output.print_success(f"Release {tag} deleted")

    except Exception as e:
        raise GitHubError(f"Failed to delete release: {e}")
