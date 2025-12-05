"""Tests for progress indicator utilities."""

import pytest
from unittest.mock import MagicMock, patch
from io import StringIO

from rich.console import Console

from devctl.core.progress import (
    ProgressManager,
    spinner,
    progress_bar,
    track,
    StepProgress,
)


class TestProgressManager:
    """Tests for ProgressManager class."""

    def test_init(self):
        """Test basic initialization."""
        manager = ProgressManager()
        assert manager._progress is None
        assert manager._tasks == {}

    def test_init_with_console(self):
        """Test initialization with custom console."""
        console = Console(file=StringIO())
        manager = ProgressManager(console=console)
        assert manager._console is console

    def test_progress_context(self):
        """Test progress context manager."""
        console = Console(file=StringIO(), force_terminal=True)
        manager = ProgressManager(console=console)

        with manager.progress("Testing", total=100) as progress:
            assert manager._progress is not None
            assert "main" in manager._tasks
            progress.advance(manager._tasks["main"], 50)

        assert manager._progress is None
        assert manager._tasks == {}

    def test_status_context(self):
        """Test status spinner context."""
        console = Console(file=StringIO(), force_terminal=True)
        manager = ProgressManager(console=console)

        with manager.status("Loading...") as status:
            status.update("Still loading...")

    def test_multi_progress(self):
        """Test multiple progress bars."""
        console = Console(file=StringIO(), force_terminal=True)
        manager = ProgressManager(console=console)

        tasks = [
            {"name": "Task A", "total": 100},
            {"name": "Task B", "total": 50},
        ]

        with manager.multi_progress(tasks) as progress:
            assert "Task A" in manager._tasks
            assert "Task B" in manager._tasks

    def test_update(self):
        """Test progress update method."""
        console = Console(file=StringIO(), force_terminal=True)
        manager = ProgressManager(console=console)

        with manager.progress("Testing", total=100):
            manager.update("main", advance=10)
            manager.update("main", advance=20, description="Updated")

    def test_track_iterator(self):
        """Test tracking iterator progress."""
        console = Console(file=StringIO(), force_terminal=True)
        manager = ProgressManager(console=console)

        items = list(range(5))
        result = list(manager.track_iterator(iter(items), "Processing", total=5))

        assert result == items


class TestSpinner:
    """Tests for spinner context manager."""

    def test_spinner_success(self):
        """Test spinner with successful operation."""
        output = StringIO()
        with patch("devctl.core.progress.console", Console(file=output, force_terminal=True)):
            with spinner("Loading...", success_message="Done!"):
                pass

    def test_spinner_error(self):
        """Test spinner with failed operation."""
        output = StringIO()
        with patch("devctl.core.progress.console", Console(file=output, force_terminal=True)):
            with pytest.raises(ValueError):
                with spinner("Loading...", error_message="Failed!"):
                    raise ValueError("test error")


class TestProgressBar:
    """Tests for progress_bar context manager."""

    def test_progress_bar(self):
        """Test basic progress bar."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        with patch("devctl.core.progress.ProgressManager") as mock_manager:
            mock_progress = MagicMock()
            mock_manager.return_value.progress.return_value.__enter__ = lambda s: mock_progress
            mock_manager.return_value.progress.return_value.__exit__ = lambda s, *args: None

            with progress_bar("Testing", total=100) as progress:
                pass


class TestTrack:
    """Tests for track function."""

    def test_track_list(self):
        """Test tracking a list."""
        items = [1, 2, 3, 4, 5]

        with patch("devctl.core.progress.ProgressManager") as mock_manager:
            mock_instance = MagicMock()
            mock_manager.return_value = mock_instance
            mock_instance.track_iterator.return_value = iter(items)

            result = list(track(iter(items), "Processing", total=5))

            mock_instance.track_iterator.assert_called_once()


class TestStepProgress:
    """Tests for StepProgress class."""

    def test_init(self):
        """Test step progress initialization."""
        steps = ["Step 1", "Step 2", "Step 3"]
        progress = StepProgress(steps, title="Test Progress")

        assert progress._steps == steps
        assert progress._title == "Test Progress"
        assert progress._current == 0

    def test_start_step(self):
        """Test starting a step."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        steps = ["Step 1", "Step 2"]
        progress = StepProgress(steps)
        progress._console = console

        progress.start("Step 1")
        assert progress._results["Step 1"] == "running"

    def test_complete_step_success(self):
        """Test completing a step successfully."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        steps = ["Step 1", "Step 2"]
        progress = StepProgress(steps)
        progress._console = console

        progress.complete("Step 1", success=True)
        assert progress._results["Step 1"] == "success"
        assert progress._current == 1

    def test_complete_step_failure(self):
        """Test completing a step with failure."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        steps = ["Step 1", "Step 2"]
        progress = StepProgress(steps)
        progress._console = console

        progress.complete("Step 1", success=False)
        assert progress._results["Step 1"] == "failed"

    def test_skip_step(self):
        """Test skipping a step."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        steps = ["Step 1", "Step 2"]
        progress = StepProgress(steps)
        progress._console = console

        progress.skip("Step 1")
        assert progress._results["Step 1"] == "skipped"

    def test_step_context_success(self):
        """Test step context manager with success."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        steps = ["Step 1"]
        progress = StepProgress(steps)
        progress._console = console

        with progress.step("Step 1"):
            pass

        assert progress._results["Step 1"] == "success"

    def test_step_context_failure(self):
        """Test step context manager with failure."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        steps = ["Step 1"]
        progress = StepProgress(steps)
        progress._console = console

        with pytest.raises(ValueError):
            with progress.step("Step 1"):
                raise ValueError("test error")

        assert progress._results["Step 1"] == "failed"
