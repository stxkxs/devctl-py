"""Command suggestion utilities for 'did you mean?' feature."""

from difflib import get_close_matches
from typing import Sequence

import click


def suggest_commands(
    typo: str,
    commands: Sequence[str],
    n: int = 3,
    cutoff: float = 0.6,
) -> list[str]:
    """Find similar commands for a typo.

    Args:
        typo: The mistyped command
        commands: Available command names
        n: Maximum number of suggestions
        cutoff: Similarity threshold (0-1)

    Returns:
        List of similar command names
    """
    return get_close_matches(typo, commands, n=n, cutoff=cutoff)


def get_all_commands(group: click.Group) -> list[str]:
    """Get all command names from a click group recursively.

    Args:
        group: Click command group

    Returns:
        List of all command names (including nested paths like 'aws.s3.ls')
    """
    commands = []

    for name, cmd in group.commands.items():
        commands.append(name)
        if isinstance(cmd, click.Group):
            # Get nested commands with parent prefix
            nested = get_all_commands(cmd)
            for nested_name in nested:
                commands.append(f"{name} {nested_name}")

    return commands


def format_suggestions(suggestions: list[str]) -> str:
    """Format suggestions for display.

    Args:
        suggestions: List of suggested commands

    Returns:
        Formatted string with suggestions
    """
    if not suggestions:
        return ""

    if len(suggestions) == 1:
        return f"Did you mean: [cyan]{suggestions[0]}[/cyan]?"

    formatted = ", ".join(f"[cyan]{s}[/cyan]" for s in suggestions[:-1])
    return f"Did you mean: {formatted} or [cyan]{suggestions[-1]}[/cyan]?"


class SuggestingGroup(click.Group):
    """Click Group that suggests similar commands on errors."""

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        """Resolve command with suggestions on failure."""
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as e:
            # Check if this is a "No such command" error
            if args and "No such command" in str(e):
                cmd_name = args[0]
                suggestions = suggest_commands(
                    cmd_name,
                    list(self.commands.keys()),
                )
                if suggestions:
                    suggestion_text = format_suggestions(suggestions)
                    raise click.UsageError(
                        f"No such command '{cmd_name}'. {suggestion_text}"
                    )
            raise


def install_suggestions(group: click.Group) -> None:
    """Install suggestion capability on a click group.

    This modifies the group's class to use SuggestingGroup behavior.

    Args:
        group: Click group to enhance
    """
    original_resolve = group.resolve_command

    def resolve_with_suggestions(
        ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return original_resolve(ctx, args)
        except click.UsageError as e:
            if args and "No such command" in str(e):
                cmd_name = args[0]
                suggestions = suggest_commands(
                    cmd_name,
                    list(group.commands.keys()),
                )
                if suggestions:
                    suggestion_text = format_suggestions(suggestions)
                    raise click.UsageError(
                        f"No such command '{cmd_name}'. {suggestion_text}"
                    )
            raise

    group.resolve_command = resolve_with_suggestions  # type: ignore

    # Also install on subgroups
    for cmd in group.commands.values():
        if isinstance(cmd, click.Group):
            install_suggestions(cmd)
