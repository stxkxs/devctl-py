"""Structured logging configuration for devctl."""

import logging
import sys
from enum import Enum
from typing import Any

from rich.console import Console
from rich.logging import RichHandler


class LogLevel(str, Enum):
    """Log level enumeration."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def setup_logging(
    level: LogLevel = LogLevel.INFO,
    rich_output: bool = True,
) -> logging.Logger:
    """Configure logging for devctl.

    Args:
        level: The logging level
        rich_output: Whether to use Rich for formatted output

    Returns:
        Configured logger instance
    """
    log_level = getattr(logging, level.value.upper())

    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    if rich_output:
        handler = RichHandler(
            console=Console(stderr=True),
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Set level for devctl logger
    logger = logging.getLogger("devctl")
    logger.setLevel(log_level)

    # Quiet noisy libraries
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module.

    Args:
        name: The module name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(f"devctl.{name}")


class StructuredLogger:
    """Logger that supports structured logging with context."""

    def __init__(self, name: str):
        self._logger = get_logger(name)
        self._context: dict[str, Any] = {}

    def bind(self, **kwargs: Any) -> "StructuredLogger":
        """Create a new logger with additional context."""
        new_logger = StructuredLogger(self._logger.name.replace("devctl.", ""))
        new_logger._context = {**self._context, **kwargs}
        return new_logger

    def _format_message(self, message: str, **kwargs: Any) -> str:
        """Format message with context."""
        context = {**self._context, **kwargs}
        if context:
            context_str = " ".join(f"{k}={v}" for k, v in context.items())
            return f"{message} [{context_str}]"
        return message

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._logger.debug(self._format_message(message, **kwargs))

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        self._logger.info(self._format_message(message, **kwargs))

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._logger.warning(self._format_message(message, **kwargs))

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        self._logger.error(self._format_message(message, **kwargs))

    def exception(self, message: str, **kwargs: Any) -> None:
        """Log exception with traceback."""
        self._logger.exception(self._format_message(message, **kwargs))
