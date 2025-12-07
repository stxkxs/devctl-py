# devctl-plugin-${{ values.name }}

${{ values.description }}

## Installation

```bash
pip install devctl-plugin-${{ values.name }}
```

Or for development:

```bash
pip install -e ".[dev]"
```

## Usage

Once installed, the plugin automatically registers with devctl:

```bash
# Available commands
devctl ${{ values.name }} --help
{%- for cmd in values.subcommands %}

# {{ cmd | capitalize }} resources
devctl ${{ values.name }} {{ cmd }}
{%- endfor %}
```

## Configuration

{%- if values.hasAuth %}

Add the following to your `~/.devctl/config.yaml`:

```yaml
profiles:
  default:
    ${{ values.name }}:
      api_key: ${DEVCTL_${{ values.name | upper }}_API_KEY}
      # base_url: https://api.${{ values.name }}.com  # optional
```

Or use environment variables:

```bash
export DEVCTL_${{ values.name | upper }}_API_KEY=your-api-key
```
{%- else %}

No authentication required. The plugin works out of the box.
{%- endif %}

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/

# Type check
mypy src/
```

## License

MIT
