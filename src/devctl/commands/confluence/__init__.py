"""Confluence command group."""

import click
from pathlib import Path

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import ConfluenceError


@click.group()
@pass_context
def confluence(ctx: DevCtlContext) -> None:
    """Confluence operations - pages, search, runbook publishing.

    \b
    Examples:
        devctl confluence pages list --space DEV
        devctl confluence search "deployment guide"
        devctl confluence runbook publish ./runbook.md --space OPS
    """
    pass


@confluence.group("pages")
def pages() -> None:
    """Page operations."""
    pass


@pages.command("list")
@click.option("--space", required=True, help="Space key")
@click.option("--title", default=None, help="Filter by title")
@click.option("--limit", default=25, help="Max results")
@pass_context
def list_pages(ctx: DevCtlContext, space: str, title: str | None, limit: int) -> None:
    """List pages in a space.

    \b
    Examples:
        devctl confluence pages list --space DEV
        devctl confluence pages list --space DEV --title "API"
    """
    try:
        result = ctx.confluence.list_pages(space_key=space, title=title, limit=limit)

        pages_list = result.get("results", [])

        if not pages_list:
            ctx.output.print_info("No pages found")
            return

        rows = []
        for page in pages_list:
            rows.append({
                "id": page.get("id", ""),
                "title": page.get("title", ""),
                "version": page.get("version", {}).get("number", ""),
                "status": page.get("status", ""),
            })

        ctx.output.print_table(rows, columns=["id", "title", "version", "status"], title=f"Pages in {space}")

    except ConfluenceError as e:
        ctx.output.print_error(f"Failed to list pages: {e}")
        raise click.Abort()


@pages.command("get")
@click.argument("page_id")
@click.option("--format", "output_format", type=click.Choice(["text", "storage"]), default="text", help="Output format")
@pass_context
def get_page(ctx: DevCtlContext, page_id: str, output_format: str) -> None:
    """Get page content.

    \b
    Examples:
        devctl confluence pages get 12345
        devctl confluence pages get 12345 --format storage
    """
    try:
        expand = "body.view" if output_format == "text" else "body.storage"
        page = ctx.confluence.get_page(page_id, expand=f"version,{expand}")

        ctx.output.print_header(f"Page: {page.get('title', '')}")
        ctx.output.print(f"ID: {page.get('id', '')}")
        ctx.output.print(f"Version: {page.get('version', {}).get('number', '')}")
        ctx.output.print("")

        body = page.get("body", {})
        if output_format == "text":
            content = body.get("view", {}).get("value", "")
        else:
            content = body.get("storage", {}).get("value", "")

        ctx.output.print(content)

    except ConfluenceError as e:
        ctx.output.print_error(f"Failed to get page: {e}")
        raise click.Abort()


@pages.command("create")
@click.option("--space", required=True, help="Space key")
@click.option("--title", required=True, help="Page title")
@click.option("--file", "file_path", type=click.Path(exists=True), default=None, help="Content file")
@click.option("--parent", default=None, help="Parent page ID")
@pass_context
def create_page(
    ctx: DevCtlContext,
    space: str,
    title: str,
    file_path: str | None,
    parent: str | None,
) -> None:
    """Create a page.

    \b
    Examples:
        devctl confluence pages create --space DEV --title "New Guide"
        devctl confluence pages create --space DEV --title "API Docs" --file content.html
    """
    try:
        content = ""
        if file_path:
            content = Path(file_path).read_text()

        if ctx.dry_run:
            ctx.log_dry_run("create page", {"space": space, "title": title})
            return

        page = ctx.confluence.create_page(
            space_key=space,
            title=title,
            body=content or "<p>New page</p>",
            parent_id=parent,
        )

        ctx.output.print_success(f"Created page: {page.get('title', '')}")
        ctx.output.print(f"ID: {page.get('id', '')}")

    except ConfluenceError as e:
        ctx.output.print_error(f"Failed to create page: {e}")
        raise click.Abort()


@pages.command("update")
@click.argument("page_id")
@click.option("--file", "file_path", type=click.Path(exists=True), required=True, help="Content file")
@click.option("--title", default=None, help="New title")
@pass_context
def update_page(ctx: DevCtlContext, page_id: str, file_path: str, title: str | None) -> None:
    """Update a page.

    \b
    Examples:
        devctl confluence pages update 12345 --file content.html
    """
    try:
        # Get current page for version
        current = ctx.confluence.get_page(page_id, expand="version")
        current_version = current.get("version", {}).get("number", 0)
        current_title = current.get("title", "")

        content = Path(file_path).read_text()

        if ctx.dry_run:
            ctx.log_dry_run("update page", {"id": page_id, "title": title or current_title})
            return

        page = ctx.confluence.update_page(
            page_id=page_id,
            title=title or current_title,
            body=content,
            version_number=current_version,
        )

        ctx.output.print_success(f"Updated page: {page.get('title', '')}")
        ctx.output.print(f"Version: {page.get('version', {}).get('number', '')}")

    except ConfluenceError as e:
        ctx.output.print_error(f"Failed to update page: {e}")
        raise click.Abort()


@confluence.command("search")
@click.argument("query")
@click.option("--space", default=None, help="Filter by space")
@click.option("--limit", default=25, help="Max results")
@pass_context
def search(ctx: DevCtlContext, query: str, space: str | None, limit: int) -> None:
    """Search Confluence.

    \b
    Examples:
        devctl confluence search "deployment guide"
        devctl confluence search "runbook" --space OPS
    """
    try:
        results = ctx.confluence.search_content(query, space_key=space, limit=limit)

        if not results:
            ctx.output.print_info("No results found")
            return

        rows = []
        for result in results:
            content = result.get("content", {})
            rows.append({
                "id": content.get("id", ""),
                "title": content.get("title", ""),
                "space": content.get("space", {}).get("key", ""),
                "type": content.get("type", ""),
            })

        ctx.output.print_table(rows, columns=["id", "title", "space", "type"], title="Search Results")

    except ConfluenceError as e:
        ctx.output.print_error(f"Search failed: {e}")
        raise click.Abort()


@confluence.group("runbook")
def runbook_cmd() -> None:
    """Runbook publishing operations."""
    pass


@runbook_cmd.command("publish")
@click.argument("file", type=click.Path(exists=True))
@click.option("--space", required=True, help="Target space")
@click.option("--parent", default=None, help="Parent page ID")
@click.option("--labels", default=None, help="Comma-separated labels")
@pass_context
def publish_runbook(
    ctx: DevCtlContext,
    file: str,
    space: str,
    parent: str | None,
    labels: str | None,
) -> None:
    """Publish a runbook to Confluence.

    \b
    Examples:
        devctl confluence runbook publish ./runbook.md --space OPS
        devctl confluence runbook publish ./runbook.yaml --space OPS --parent 12345
    """
    try:
        from devctl.runbooks import RunbookEngine

        # Load runbook
        engine = RunbookEngine()
        rb = engine.load(file)

        # Convert to HTML
        content = _runbook_to_html(rb)

        if ctx.dry_run:
            ctx.log_dry_run("publish runbook", {"name": rb.name, "space": space})
            return

        # Parse labels
        label_list = [l.strip() for l in labels.split(",")] if labels else ["runbook"]

        page = ctx.confluence.publish_runbook(
            space_key=space,
            title=rb.name,
            content=content,
            parent_id=parent,
            labels=label_list,
        )

        ctx.output.print_success(f"Published runbook: {page.get('title', '')}")
        ctx.output.print(f"ID: {page.get('id', '')}")

    except Exception as e:
        ctx.output.print_error(f"Failed to publish runbook: {e}")
        raise click.Abort()


@confluence.group("incident")
def incident() -> None:
    """Incident documentation operations."""
    pass


@incident.command("create")
@click.option("--space", required=True, help="Space key")
@click.option("--title", required=True, help="Incident title")
@click.option("--severity", type=click.Choice(["P1", "P2", "P3", "P4", "P5"]), default="P3", help="Severity")
@click.option("--summary", default=None, help="Initial summary")
@click.option("--service", default=None, help="Affected service")
@click.option("--parent", default=None, help="Parent page ID")
@pass_context
def create_incident(
    ctx: DevCtlContext,
    space: str,
    title: str,
    severity: str,
    summary: str | None,
    service: str | None,
    parent: str | None,
) -> None:
    """Create an incident page.

    \b
    Examples:
        devctl confluence incident create --space OPS --title "Database outage" --severity P1
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("create incident", {"title": title, "severity": severity})
            return

        affected_services = [service] if service else []

        page = ctx.confluence.create_incident_page(
            space_key=space,
            title=title,
            severity=severity,
            summary=summary or "",
            affected_services=affected_services,
            parent_id=parent,
        )

        ctx.output.print_success(f"Created incident page: {page.get('title', '')}")
        ctx.output.print(f"ID: {page.get('id', '')}")

    except ConfluenceError as e:
        ctx.output.print_error(f"Failed to create incident: {e}")
        raise click.Abort()


def _runbook_to_html(rb) -> str:
    """Convert runbook to Confluence storage format HTML."""
    html = f"""
<h2>Overview</h2>
<p>{rb.description}</p>
<p><strong>Version:</strong> {rb.version}</p>
<p><strong>Author:</strong> {rb.author}</p>

<h2>Variables</h2>
<table>
<thead><tr><th>Name</th><th>Default</th></tr></thead>
<tbody>
"""

    for name, value in rb.variables.items():
        html += f"<tr><td><code>{name}</code></td><td>{value or 'N/A'}</td></tr>\n"

    html += """</tbody></table>

<h2>Steps</h2>
"""

    for i, step in enumerate(rb.steps, 1):
        html += f"""
<h3>{i}. {step.name}</h3>
<p>{step.description}</p>
"""
        if step.command:
            html += f"""
<ac:structured-macro ac:name="code">
<ac:parameter ac:name="language">bash</ac:parameter>
<ac:plain-text-body><![CDATA[{step.command}]]></ac:plain-text-body>
</ac:structured-macro>
"""
        if step.when:
            html += f"<p><em>Condition:</em> <code>{step.when}</code></p>"

    return html
