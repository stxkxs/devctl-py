"""Common utilities for devctl."""

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def parse_duration(duration_str: str) -> timedelta:
    """Parse duration string to timedelta.

    Supports formats like: 30s, 5m, 2h, 1d, 1w
    Also supports combinations: 1h30m, 2d12h

    Args:
        duration_str: Duration string

    Returns:
        timedelta object

    Raises:
        ValueError: If format is invalid
    """
    if not duration_str:
        raise ValueError("Duration string cannot be empty")

    pattern = re.compile(r"(\d+)([smhdw])")
    matches = pattern.findall(duration_str.lower())

    if not matches:
        raise ValueError(f"Invalid duration format: {duration_str}")

    total = timedelta()
    units = {
        "s": "seconds",
        "m": "minutes",
        "h": "hours",
        "d": "days",
        "w": "weeks",
    }

    for value, unit in matches:
        total += timedelta(**{units[unit]: int(value)})

    return total


def parse_time(time_str: str) -> datetime:
    """Parse time string to datetime.

    Supports:
    - Relative: -1h, -30m, -1d (negative durations from now)
    - ISO format: 2024-01-15T10:30:00Z
    - Date only: 2024-01-15

    Args:
        time_str: Time string

    Returns:
        datetime object (UTC)
    """
    if time_str.startswith("-"):
        duration = parse_duration(time_str[1:])
        return datetime.now(timezone.utc) - duration

    # Try ISO format
    try:
        if time_str.endswith("Z"):
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # Try date only
    try:
        return datetime.strptime(time_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(f"Invalid time format: {time_str}")


def get_config_dir() -> Path:
    """Get the devctl config directory."""
    config_dir = Path(os.environ.get("DEVCTL_CONFIG_DIR", "~/.devctl")).expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_cache_dir() -> Path:
    """Get the devctl cache directory."""
    cache_dir = Path(os.environ.get("DEVCTL_CACHE_DIR", "~/.devctl/cache")).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Dictionary to merge on top

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def truncate_string(s: str, max_length: int = 50, suffix: str = "...") -> str:
    """Truncate a string to a maximum length.

    Args:
        s: String to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix


def parse_key_value_pairs(pairs: list[str]) -> dict[str, str]:
    """Parse KEY=VALUE pairs from a list of strings.

    Args:
        pairs: List of KEY=VALUE strings

    Returns:
        Dictionary of parsed pairs
    """
    result = {}
    for pair in pairs:
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def parse_tags(tag_strings: list[str]) -> dict[str, str]:
    """Parse AWS-style tags from strings.

    Supports formats:
    - KEY=VALUE
    - KEY:VALUE (AWS CLI style)

    Args:
        tag_strings: List of tag strings

    Returns:
        Dictionary of tags
    """
    tags = {}
    for tag_str in tag_strings:
        if "=" in tag_str:
            key, value = tag_str.split("=", 1)
        elif ":" in tag_str:
            key, value = tag_str.split(":", 1)
        else:
            key, value = tag_str, ""
        tags[key.strip()] = value.strip()
    return tags


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename.

    Args:
        name: String to sanitize

    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(". ")
    return sanitized or "unnamed"


def chunks(lst: list[Any], n: int) -> list[list[Any]]:
    """Split a list into chunks of size n.

    Args:
        lst: List to split
        n: Chunk size

    Returns:
        List of chunks
    """
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def flatten_dict(
    d: dict[str, Any],
    parent_key: str = "",
    separator: str = ".",
) -> dict[str, Any]:
    """Flatten a nested dictionary.

    Args:
        d: Dictionary to flatten
        parent_key: Prefix for keys
        separator: Key separator

    Returns:
        Flattened dictionary
    """
    items: list[tuple[str, Any]] = []
    for key, value in d.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, separator).items())
        else:
            items.append((new_key, value))
    return dict(items)
