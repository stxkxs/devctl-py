"""Grafana dashboard templates for devctl workflows."""

import json
from pathlib import Path
from typing import Any


TEMPLATES_DIR = Path(__file__).parent / "templates"


def list_templates() -> list[str]:
    """List available dashboard templates."""
    templates = []
    for f in TEMPLATES_DIR.glob("*.json"):
        templates.append(f.stem)
    return sorted(templates)


def get_template(name: str) -> dict[str, Any]:
    """Get a dashboard template by name."""
    template_path = TEMPLATES_DIR / f"{name}.json"
    if not template_path.exists():
        raise ValueError(f"Dashboard template not found: {name}")

    with open(template_path) as f:
        return json.load(f)


def get_template_info(name: str) -> dict[str, str]:
    """Get template metadata."""
    template = get_template(name)
    return {
        "name": name,
        "title": template.get("title", name),
        "description": template.get("description", ""),
        "tags": ", ".join(template.get("tags", [])),
    }
