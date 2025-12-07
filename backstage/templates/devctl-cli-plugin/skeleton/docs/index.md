# devctl ${{ values.name }} Plugin

${{ values.description }}

## Overview

This plugin extends devctl with ${{ values.name }} integration capabilities.

## Quick Start

```bash
# Install the plugin
pip install devctl-plugin-${{ values.name }}

# Verify installation
devctl ${{ values.name }} --help
```

## Available Commands

| Command | Description |
|---------|-------------|
{%- for cmd in values.subcommands %}
| `devctl ${{ values.name }} {{ cmd }}` | {{ cmd | capitalize }} ${{ values.name }} resources |
{%- endfor %}
