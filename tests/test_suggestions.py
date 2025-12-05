"""Tests for command suggestion feature."""

import pytest
import click

from devctl.core.suggestions import (
    suggest_commands,
    format_suggestions,
    get_all_commands,
    install_suggestions,
)


class TestSuggestCommands:
    """Tests for suggest_commands function."""

    def test_exact_match(self):
        """Test that exact matches are returned."""
        commands = ["aws", "grafana", "github", "jira"]
        result = suggest_commands("aws", commands)
        assert "aws" in result

    def test_close_match(self):
        """Test suggestions for typos."""
        commands = ["aws", "grafana", "github", "jira"]
        result = suggest_commands("awx", commands)
        assert "aws" in result

    def test_similar_commands(self):
        """Test suggestions for similar commands."""
        commands = ["deploy", "delete", "describe", "download"]
        result = suggest_commands("delpoy", commands)
        assert "deploy" in result

    def test_no_match(self):
        """Test no suggestions for very different input."""
        commands = ["aws", "grafana", "github"]
        result = suggest_commands("xyz123", commands)
        assert result == []

    def test_multiple_suggestions(self):
        """Test multiple suggestions returned."""
        commands = ["list", "lint", "link", "login"]
        result = suggest_commands("lit", commands)
        assert len(result) >= 1
        assert "list" in result or "lint" in result

    def test_max_suggestions(self):
        """Test maximum number of suggestions."""
        commands = ["test1", "test2", "test3", "test4", "test5"]
        result = suggest_commands("test", commands, n=2)
        assert len(result) <= 2

    def test_cutoff_threshold(self):
        """Test similarity cutoff."""
        commands = ["aws", "grafana"]
        # With high cutoff, no matches for different string
        result = suggest_commands("gra", commands, cutoff=0.9)
        assert "grafana" not in result

        # With lower cutoff, matches
        result = suggest_commands("grafan", commands, cutoff=0.6)
        assert "grafana" in result


class TestFormatSuggestions:
    """Tests for format_suggestions function."""

    def test_single_suggestion(self):
        """Test formatting single suggestion."""
        result = format_suggestions(["aws"])
        assert "Did you mean:" in result
        assert "aws" in result
        assert "?" in result

    def test_multiple_suggestions(self):
        """Test formatting multiple suggestions."""
        result = format_suggestions(["aws", "grafana", "github"])
        assert "Did you mean:" in result
        assert "aws" in result
        assert "grafana" in result
        assert "github" in result
        assert " or " in result

    def test_empty_suggestions(self):
        """Test formatting empty suggestions."""
        result = format_suggestions([])
        assert result == ""


class TestGetAllCommands:
    """Tests for get_all_commands function."""

    def test_simple_group(self):
        """Test getting commands from simple group."""
        @click.group()
        def cli():
            pass

        @cli.command()
        def cmd1():
            pass

        @cli.command()
        def cmd2():
            pass

        commands = get_all_commands(cli)
        assert "cmd1" in commands
        assert "cmd2" in commands

    def test_nested_groups(self):
        """Test getting commands from nested groups."""
        @click.group()
        def cli():
            pass

        @cli.group()
        def sub():
            pass

        @sub.command()
        def nested():
            pass

        commands = get_all_commands(cli)
        assert "sub" in commands
        assert "sub nested" in commands


class TestInstallSuggestions:
    """Tests for install_suggestions function."""

    def test_suggests_on_typo(self):
        """Test that suggestions are shown on command typo."""
        @click.group()
        def cli():
            pass

        @cli.command()
        def deploy():
            pass

        @cli.command()
        def delete():
            pass

        install_suggestions(cli)

        # Simulate resolving a mistyped command
        ctx = click.Context(cli)
        with pytest.raises(click.UsageError) as exc_info:
            cli.resolve_command(ctx, ["delpoy"])

        error_msg = str(exc_info.value)
        assert "No such command" in error_msg
        assert "Did you mean:" in error_msg
        assert "deploy" in error_msg

    def test_no_suggestion_for_valid_command(self):
        """Test that valid commands work normally."""
        @click.group()
        def cli():
            pass

        @cli.command()
        def deploy():
            pass

        install_suggestions(cli)

        ctx = click.Context(cli)
        name, cmd, args = cli.resolve_command(ctx, ["deploy"])
        assert name == "deploy"
        assert cmd is not None

    def test_nested_suggestions(self):
        """Test suggestions work on nested groups."""
        @click.group()
        def cli():
            pass

        @cli.group()
        def aws():
            pass

        @aws.command()
        def s3():
            pass

        @aws.command()
        def ec2():
            pass

        install_suggestions(cli)

        # Test suggestion on nested group
        ctx = click.Context(aws)
        with pytest.raises(click.UsageError) as exc_info:
            aws.resolve_command(ctx, ["s33"])

        error_msg = str(exc_info.value)
        assert "Did you mean:" in error_msg
        assert "s3" in error_msg
