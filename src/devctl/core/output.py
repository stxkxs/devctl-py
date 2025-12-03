"""Output formatting utilities using Rich."""

import json
import sys
from enum import Enum
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from tabulate import tabulate

console = Console()
error_console = Console(stderr=True)


class OutputFormat(str, Enum):
    """Supported output formats."""

    TABLE = "table"
    JSON = "json"
    YAML = "yaml"
    RAW = "raw"


class OutputFormatter:
    """Handles output formatting for CLI commands."""

    def __init__(
        self,
        format: OutputFormat = OutputFormat.TABLE,
        color: bool = True,
        quiet: bool = False,
    ):
        self.format = format
        self.color = color
        self.quiet = quiet
        self._console = Console(force_terminal=color, no_color=not color)

    def print(self, message: str, style: str | None = None) -> None:
        """Print a message to stdout."""
        if self.quiet:
            return
        self._console.print(message, style=style)

    def print_error(self, message: str) -> None:
        """Print an error message to stderr."""
        error_console.print(f"[red]Error:[/red] {message}")

    def print_warning(self, message: str) -> None:
        """Print a warning message."""
        if self.quiet:
            return
        self._console.print(f"[yellow]Warning:[/yellow] {message}")

    def print_success(self, message: str) -> None:
        """Print a success message."""
        if self.quiet:
            return
        self._console.print(f"[green]✓[/green] {message}")

    def print_info(self, message: str) -> None:
        """Print an info message."""
        if self.quiet:
            return
        self._console.print(f"[blue]ℹ[/blue] {message}")

    def print_data(
        self,
        data: list[dict[str, Any]] | dict[str, Any],
        headers: list[str] | None = None,
        title: str | None = None,
    ) -> None:
        """Print data in the configured format."""
        if self.format == OutputFormat.JSON:
            self._print_json(data)
        elif self.format == OutputFormat.YAML:
            self._print_yaml(data)
        elif self.format == OutputFormat.RAW:
            self._print_raw(data)
        else:
            self._print_table(data, headers, title)

    def _print_json(self, data: Any) -> None:
        """Print data as JSON."""
        if self.color:
            json_str = json.dumps(data, indent=2, default=str)
            syntax = Syntax(json_str, "json", theme="monokai")
            self._console.print(syntax)
        else:
            print(json.dumps(data, indent=2, default=str))

    def _print_yaml(self, data: Any) -> None:
        """Print data as YAML."""
        yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True)
        if self.color:
            syntax = Syntax(yaml_str, "yaml", theme="monokai")
            self._console.print(syntax)
        else:
            print(yaml_str)

    def _print_raw(self, data: Any) -> None:
        """Print raw data."""
        if isinstance(data, list):
            for item in data:
                print(item)
        elif isinstance(data, dict):
            for key, value in data.items():
                print(f"{key}: {value}")
        else:
            print(data)

    def _print_table(
        self,
        data: list[dict[str, Any]] | dict[str, Any],
        headers: list[str] | None = None,
        title: str | None = None,
    ) -> None:
        """Print data as a formatted table."""
        if isinstance(data, dict):
            # Single record - display as key-value pairs
            table = Table(title=title, show_header=True, header_style="bold cyan")
            table.add_column("Field", style="dim")
            table.add_column("Value")
            for key, value in data.items():
                table.add_row(str(key), str(value))
            self._console.print(table)
        elif isinstance(data, list) and len(data) > 0:
            # List of records
            if headers is None:
                headers = list(data[0].keys()) if data else []

            table = Table(title=title, show_header=True, header_style="bold cyan")
            for header in headers:
                table.add_column(header)

            for row in data:
                table.add_row(*[str(row.get(h, "")) for h in headers])

            self._console.print(table)
        else:
            self._console.print("[dim]No data to display[/dim]")

    def print_panel(self, content: str, title: str | None = None, style: str = "blue") -> None:
        """Print content in a panel."""
        if self.quiet:
            return
        panel = Panel(content, title=title, border_style=style)
        self._console.print(panel)

    def print_code(self, code: str, language: str = "python") -> None:
        """Print syntax-highlighted code."""
        syntax = Syntax(code, language, theme="monokai", line_numbers=True)
        self._console.print(syntax)

    def confirm(self, message: str, default: bool = False) -> bool:
        """Ask for confirmation."""
        if self.quiet:
            return default

        suffix = " [Y/n]" if default else " [y/N]"
        self._console.print(f"{message}{suffix}", end=" ")

        try:
            response = input().strip().lower()
            if not response:
                return default
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False


def create_progress() -> Progress:
    """Create a Rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def format_bytes(size: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(size) < 1024.0:
            return f"{size:3.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} EB"


def format_duration(seconds: float) -> str:
    """Format seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}h"
    else:
        days = seconds / 86400
        return f"{days:.1f}d"


def format_cost(amount: float, currency: str = "USD") -> str:
    """Format cost with currency symbol."""
    symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
    symbol = symbols.get(currency, currency)
    return f"{symbol}{amount:,.2f}"
