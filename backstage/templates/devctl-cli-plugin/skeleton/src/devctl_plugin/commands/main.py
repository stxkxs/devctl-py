"""${{ values.name }} CLI commands for devctl."""

import click
from rich.console import Console
from rich.table import Table

console = Console()

{%- if values.hasApi %}


class ${{ values.name | capitalize }}Client:
    """Client for ${{ values.name }} API interactions."""

    def __init__(self, {% if values.hasAuth %}api_key: str, {% endif %}base_url: str = None):
        {%- if values.hasAuth %}
        self.api_key = api_key
        {%- endif %}
        self.base_url = base_url or "https://api.${{ values.name }}.com"

    # Add API methods here
{%- endif %}


@click.group(name="${{ values.name }}")
def cli():
    """${{ values.description }}"""
    pass

{%- for cmd in values.subcommands %}


@cli.command()
@click.option("-o", "--output", type=click.Choice(["table", "json", "yaml"]), default="table")
def {{ cmd }}(output: str):
    """{{ cmd | capitalize }} ${{ values.name }} resources."""
    # Implementation here
    console.print(f"[green]{{ cmd }} command executed[/green]")
{%- endfor %}


# Register with devctl
def register(parent_group):
    """Register this plugin with the main devctl CLI."""
    parent_group.add_command(cli)
