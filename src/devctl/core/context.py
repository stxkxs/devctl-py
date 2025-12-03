"""Click context object for sharing state across commands."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Callable, TypeVar

import click

from devctl.config import DevCtlConfig, ProfileConfig, load_config, get_default_config
from devctl.core.output import OutputFormat, OutputFormatter
from devctl.core.logging import LogLevel, setup_logging, StructuredLogger

if TYPE_CHECKING:
    from devctl.clients.aws import AWSClientFactory
    from devctl.clients.grafana import GrafanaClient
    from devctl.clients.github import GitHubClient

F = TypeVar("F", bound=Callable[..., Any])


class DevCtlContext:
    """Shared context object for devctl commands.

    This object is passed through Click's context mechanism and provides
    access to configuration, clients, and utilities.
    """

    def __init__(
        self,
        config: DevCtlConfig | None = None,
        profile: str | None = None,
        output_format: OutputFormat | None = None,
        verbose: int = 0,
        quiet: bool = False,
        dry_run: bool = False,
        color: bool = True,
    ):
        # Load or use provided config
        self._config = config or get_default_config()
        self._profile_name = profile or "default"

        # Output settings (CLI overrides config)
        self._output_format = output_format or self._config.global_settings.output_format
        self._verbose = verbose
        self._quiet = quiet
        self._dry_run = dry_run or self._config.global_settings.dry_run
        self._color = color

        # Determine log level from verbosity
        if verbose >= 3:
            log_level = LogLevel.DEBUG
        elif verbose >= 1:
            log_level = LogLevel.INFO
        elif quiet:
            log_level = LogLevel.ERROR
        else:
            log_level = self._config.global_settings.verbosity

        # Setup logging
        setup_logging(log_level, rich_output=color)
        self._logger = StructuredLogger("context")

        # Output formatter
        self._output = OutputFormatter(
            format=self._output_format,
            color=color,
            quiet=quiet,
        )

        # Lazy-loaded clients
        self._aws_factory: AWSClientFactory | None = None
        self._grafana_client: GrafanaClient | None = None
        self._github_client: GitHubClient | None = None

    @property
    def config(self) -> DevCtlConfig:
        """Get the loaded configuration."""
        return self._config

    @property
    def profile(self) -> ProfileConfig:
        """Get the current profile configuration."""
        return self._config.get_profile(self._profile_name)

    @property
    def profile_name(self) -> str:
        """Get the current profile name."""
        return self._profile_name

    @property
    def output(self) -> OutputFormatter:
        """Get the output formatter."""
        return self._output

    @property
    def output_format(self) -> OutputFormat:
        """Get the output format."""
        return self._output_format

    @property
    def dry_run(self) -> bool:
        """Check if dry-run mode is enabled."""
        return self._dry_run

    @property
    def verbose(self) -> int:
        """Get verbosity level."""
        return self._verbose

    @property
    def quiet(self) -> bool:
        """Check if quiet mode is enabled."""
        return self._quiet

    @property
    def color(self) -> bool:
        """Check if color output is enabled."""
        return self._color

    @property
    def logger(self) -> StructuredLogger:
        """Get the context logger."""
        return self._logger

    @property
    def aws(self) -> "AWSClientFactory":
        """Get or create AWS client factory."""
        if self._aws_factory is None:
            from devctl.clients.aws import AWSClientFactory

            self._aws_factory = AWSClientFactory(self.profile.aws)
        return self._aws_factory

    @property
    def grafana(self) -> "GrafanaClient":
        """Get or create Grafana client."""
        if self._grafana_client is None:
            from devctl.clients.grafana import GrafanaClient

            self._grafana_client = GrafanaClient(self.profile.grafana)
        return self._grafana_client

    @property
    def github(self) -> "GitHubClient":
        """Get or create GitHub client."""
        if self._github_client is None:
            from devctl.clients.github import GitHubClient

            self._github_client = GitHubClient(self.profile.github)
        return self._github_client

    def confirm(self, message: str, default: bool = False) -> bool:
        """Ask for user confirmation.

        In dry-run mode, always returns True without prompting.
        """
        if self._dry_run:
            self._output.print(f"[dim][dry-run] Would prompt: {message}[/dim]")
            return True
        return self._output.confirm(message, default)

    def log_dry_run(self, action: str, details: dict[str, Any] | None = None) -> None:
        """Log a dry-run action."""
        if self._dry_run:
            msg = f"[dry-run] {action}"
            if details:
                detail_str = ", ".join(f"{k}={v}" for k, v in details.items())
                msg = f"{msg} ({detail_str})"
            self._output.print(f"[dim]{msg}[/dim]")


# Click decorator for passing context
pass_context = click.make_pass_decorator(DevCtlContext, ensure=True)


def require_confirmation(
    message: str = "Are you sure you want to proceed?",
    default: bool = False,
) -> Callable[[F], F]:
    """Decorator to require confirmation for destructive operations."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        @pass_context
        def wrapper(ctx: DevCtlContext, *args: Any, **kwargs: Any) -> Any:
            # Skip confirmation in dry-run mode or if --yes flag is set
            if ctx.dry_run or kwargs.get("yes", False):
                return func(*args, **kwargs)

            if ctx.config.global_settings.confirm_destructive:
                if not ctx.confirm(message, default):
                    ctx.output.print_info("Operation cancelled")
                    raise click.Abort()

            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator
