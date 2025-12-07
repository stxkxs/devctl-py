"""Tests for ${{ values.name }} plugin."""

import pytest
from click.testing import CliRunner

from devctl_plugin.commands.main import cli


@pytest.fixture
def runner():
    return CliRunner()


class Test${{ values.name | capitalize }}Commands:
    """Test suite for ${{ values.name }} commands."""

{%- for cmd in values.subcommands %}

    def test_{{ cmd }}_command(self, runner):
        """Test {{ cmd }} command executes successfully."""
        result = runner.invoke(cli, ["{{ cmd }}"])
        assert result.exit_code == 0
{%- endfor %}
