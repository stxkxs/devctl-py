# Developer Experience Improvements

> **Status: ✅ PARTIALLY IMPLEMENTED** (December 2024)
> - ✅ Command Suggestions ("Did you mean?")
> - ✅ Progress Indicators
> - ⬜ Shell Completions
> - ⬜ Configuration Wizard
> - ⬜ Interactive Mode (REPL)
> - ⬜ Command History & Favorites

Six features to improve CLI usability and developer productivity.

## 2.1 Command Suggestions ("Did you mean?")

**Goal**: Fuzzy matching for typos with suggestions.

### Files to Modify
- `src/devctl/cli.py` - Hook into error handling (lines 238-249)

### New File
- `src/devctl/core/suggestions.py`

### Implementation

```python
from difflib import get_close_matches

def get_all_commands(group, prefix="") -> list[str]:
    """Recursively get all command paths."""
    commands = []
    for name, cmd in group.commands.items():
        full_name = f"{prefix} {name}".strip()
        commands.append(full_name)
        if hasattr(cmd, 'commands'):
            commands.extend(get_all_commands(cmd, full_name))
    return commands

def suggest_commands(typo: str, commands: list[str]) -> list[str]:
    return get_close_matches(typo, commands, n=3, cutoff=0.6)
```

In `cli.py`, wrap the main function:
```python
try:
    cli()
except click.UsageError as e:
    if "No such command" in str(e):
        suggestions = suggest_commands(...)
        if suggestions:
            click.echo(f"Did you mean: {', '.join(suggestions)}?")
    raise
```

**Complexity**: Low

---

## 2.2 Progress Indicators

**Goal**: Better feedback for long operations.

### Files to Modify
- `src/devctl/core/output.py` - Extend create_progress()

### New File
- `src/devctl/core/progress.py`

### Implementation

```python
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from contextlib import contextmanager

class ProgressManager:
    def __init__(self, console):
        self.console = console
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        )

    @contextmanager
    def task(self, description: str):
        with self.progress:
            task_id = self.progress.add_task(description)
            try:
                yield
                self.progress.update(task_id, completed=True)
            except Exception:
                self.progress.update(task_id, description=f"[red]{description} - Failed")
                raise
```

Retrofit AWS paginated operations, S3 sync, etc.

**Complexity**: Low-Medium

---

## 2.3 Shell Completions

**Goal**: Tab completion for bash/zsh/fish.

### New File
- `src/devctl/commands/completion.py`

### Commands
```bash
devctl completion bash  # Generate bash completion
devctl completion zsh   # Generate zsh completion
devctl completion fish  # Generate fish completion
```

### Implementation

```python
import click
from click.shell_completion import get_completion_class

@click.group()
def completion():
    """Generate shell completions."""
    pass

@completion.command()
@click.argument('shell', type=click.Choice(['bash', 'zsh', 'fish']))
def install(shell: str):
    """Generate completion script for SHELL."""
    comp_cls = get_completion_class(shell)
    comp = comp_cls(cli, {}, 'devctl', '_DEVCTL_COMPLETE')
    click.echo(comp.source())
```

Add dynamic completions:
```python
def complete_s3_buckets(ctx, param, incomplete):
    # Return bucket names matching incomplete
    pass
```

**Complexity**: Medium

---

## 2.4 Configuration Wizard

**Goal**: Interactive setup for new users.

### New File
- `src/devctl/commands/setup.py`

### Command
```bash
devctl setup  # Interactive configuration wizard
```

### Implementation

```python
import questionary
from devctl.config import DevCtlConfig

@click.command()
def setup():
    """Interactive configuration wizard."""

    # AWS setup
    if questionary.confirm("Configure AWS?").ask():
        profile = questionary.text("AWS profile name:", default="default").ask()
        region = questionary.select(
            "Default region:",
            choices=["us-east-1", "us-west-2", "eu-west-1", ...]
        ).ask()

    # GitHub setup
    if questionary.confirm("Configure GitHub?").ask():
        token = questionary.password("GitHub token:").ask()
        # Validate token

    # Grafana setup
    if questionary.confirm("Configure Grafana?").ask():
        url = questionary.text("Grafana URL:").ask()
        api_key = questionary.password("API key:").ask()
        # Test connection

    # Generate config
    config = DevCtlConfig(...)
    config.save()
```

### New Dependency
- `questionary` or `InquirerPy`

**Complexity**: Medium

---

## 2.5 Interactive Mode (REPL)

**Goal**: REPL interface for exploring commands.

### New Files
- `src/devctl/interactive/__init__.py`
- `src/devctl/interactive/shell.py`

### Command
```bash
devctl interactive  # or devctl -i
```

### Implementation

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory

class DevctlCompleter(Completer):
    def get_completions(self, document, complete_event):
        # Complete based on Click command tree
        pass

class InteractiveShell:
    def __init__(self, ctx):
        self.ctx = ctx
        self.session = PromptSession(
            history=FileHistory('~/.devctl/history'),
            completer=DevctlCompleter(),
        )

    def run(self):
        while True:
            try:
                text = self.session.prompt('devctl> ')
                if text.strip():
                    self.execute(text)
            except (KeyboardInterrupt, EOFError):
                break

    def execute(self, text):
        args = shlex.split(text)
        # Invoke through Click command tree
        ctx.invoke(cli, args)
```

### New Dependency
- `prompt_toolkit`

**Complexity**: Medium-High

---

## 2.6 Command History & Favorites

**Goal**: Track and reuse commands.

### New Files
- `src/devctl/core/history.py`
- `src/devctl/commands/history.py`

### Commands
```bash
devctl history [--search PATTERN]
devctl favorites add "aws cost summary"
devctl favorites list
devctl favorites run 1
```

### Implementation

```python
import sqlite3
from pathlib import Path

class CommandHistory:
    def __init__(self):
        self.db_path = Path.home() / '.devctl' / 'history.db'
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY,
                    command TEXT,
                    args TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    exit_code INTEGER
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    command TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

    def log(self, command: str, args: list, exit_code: int):
        # Mask sensitive args
        pass

    def search(self, pattern: str) -> list:
        pass
```

Hook into CLI entry point to log commands.

**Complexity**: Medium

---

## Implementation Order

1. **Command Suggestions** - Quick win, immediate UX improvement
2. **Progress Indicators** - Visible improvement for long operations
3. **Shell Completions** - High value for power users
4. **Configuration Wizard** - Important for onboarding
5. **History & Favorites** - Nice to have
6. **Interactive Mode** - Highest complexity, optional

## New Dependencies

```toml
[project.optional-dependencies]
interactive = [
    "prompt_toolkit>=3.0.0",
    "questionary>=2.0.0",
]
```

Optional:
- `thefuzz` for better fuzzy matching in suggestions
