"""Tests for output formatting utilities."""

import json

import pytest
import yaml

from devctl.core.output import (
    OutputFormat,
    OutputFormatter,
    format_bytes,
    format_duration,
    format_cost,
)


class TestFormatBytes:
    """Tests for format_bytes utility."""

    def test_bytes(self):
        assert format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        assert format_bytes(1024) == "1.0 KB"
        assert format_bytes(1536) == "1.5 KB"

    def test_megabytes(self):
        assert format_bytes(1024 * 1024) == "1.0 MB"
        assert format_bytes(1024 * 1024 * 2.5) == "2.5 MB"

    def test_gigabytes(self):
        assert format_bytes(1024**3) == "1.0 GB"

    def test_terabytes(self):
        assert format_bytes(1024**4) == "1.0 TB"

    def test_zero(self):
        assert format_bytes(0) == "0.0 B"


class TestFormatDuration:
    """Tests for format_duration utility."""

    def test_seconds(self):
        assert format_duration(30) == "30.0s"
        assert format_duration(59.9) == "59.9s"

    def test_minutes(self):
        assert format_duration(60) == "1.0m"
        assert format_duration(120) == "2.0m"
        assert format_duration(90) == "1.5m"

    def test_hours(self):
        assert format_duration(3600) == "1.0h"
        assert format_duration(7200) == "2.0h"

    def test_days(self):
        assert format_duration(86400) == "1.0d"
        assert format_duration(172800) == "2.0d"


class TestFormatCost:
    """Tests for format_cost utility."""

    def test_usd(self):
        assert format_cost(100.00) == "$100.00"
        assert format_cost(1234.56) == "$1,234.56"

    def test_eur(self):
        assert format_cost(100.00, "EUR") == "€100.00"

    def test_gbp(self):
        assert format_cost(100.00, "GBP") == "£100.00"

    def test_unknown_currency(self):
        assert format_cost(100.00, "JPY") == "JPY100.00"

    def test_zero(self):
        assert format_cost(0) == "$0.00"

    def test_large_number(self):
        assert format_cost(1000000.00) == "$1,000,000.00"


class TestOutputFormatter:
    """Tests for OutputFormatter class."""

    def test_quiet_mode_suppresses_output(self, capsys):
        formatter = OutputFormatter(quiet=True, color=False)
        formatter.print("test message")
        formatter.print_info("info message")
        formatter.print_warning("warning message")
        formatter.print_success("success message")
        captured = capsys.readouterr()
        assert "test message" not in captured.out
        assert "info message" not in captured.out

    def test_error_always_prints(self, capsys):
        formatter = OutputFormatter(quiet=True, color=False)
        formatter.print_error("error message")
        captured = capsys.readouterr()
        assert "error message" in captured.err

    def test_json_output(self, capsys):
        formatter = OutputFormatter(format=OutputFormat.JSON, color=False)
        data = {"name": "test", "value": 123}
        formatter.print_data(data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data

    def test_json_output_list(self, capsys):
        formatter = OutputFormatter(format=OutputFormat.JSON, color=False)
        data = [{"name": "a"}, {"name": "b"}]
        formatter.print_data(data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data

    def test_yaml_output(self, capsys):
        formatter = OutputFormatter(format=OutputFormat.YAML, color=False)
        data = {"name": "test", "value": 123}
        formatter.print_data(data)
        captured = capsys.readouterr()
        parsed = yaml.safe_load(captured.out)
        assert parsed == data

    def test_raw_output_dict(self, capsys):
        formatter = OutputFormatter(format=OutputFormat.RAW, color=False)
        data = {"name": "test", "value": 123}
        formatter.print_data(data)
        captured = capsys.readouterr()
        assert "name: test" in captured.out
        assert "value: 123" in captured.out

    def test_raw_output_list(self, capsys):
        formatter = OutputFormatter(format=OutputFormat.RAW, color=False)
        data = ["item1", "item2", "item3"]
        formatter.print_data(data)
        captured = capsys.readouterr()
        assert "item1" in captured.out
        assert "item2" in captured.out
        assert "item3" in captured.out


class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_values(self):
        assert OutputFormat.TABLE.value == "table"
        assert OutputFormat.JSON.value == "json"
        assert OutputFormat.YAML.value == "yaml"
        assert OutputFormat.RAW.value == "raw"

    def test_string_comparison(self):
        assert OutputFormat.TABLE == "table"
        assert OutputFormat.JSON == "json"
