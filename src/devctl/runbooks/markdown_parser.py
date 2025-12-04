"""Parse runbooks from Markdown format."""

import re
from pathlib import Path
from typing import Any

import yaml

from devctl.core.exceptions import RunbookError
from devctl.runbooks.schema import Runbook, RunbookStep, StepType


class MarkdownRunbookParser:
    """Parse runbooks from Markdown files.

    Expected format:
    ```markdown
    # Runbook: My Runbook Name

    Description of the runbook.

    ## Variables

    - `var1`: Description (default: value)
    - `var2`: Description

    ## Steps

    ### 1. Step Name

    Description of the step.

    ```bash
    echo "Hello World"
    ```

    ### 2. Another Step [prompt]

    Confirm before proceeding?

    ### 3. Conditional Step [when: var1 == 'true']

    ```bash
    echo "Conditional command"
    ```
    ```
    """

    # Regex patterns
    TITLE_PATTERN = re.compile(r"^#\s+(?:Runbook:\s*)?(.+)$", re.MULTILINE)
    SECTION_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    STEP_PATTERN = re.compile(
        r"^###\s+(\d+)\.\s+(.+?)(?:\s*\[(.+?)\])?$", re.MULTILINE
    )
    CODE_BLOCK_PATTERN = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
    VARIABLE_PATTERN = re.compile(
        r"^-\s+`(\w+)`:\s*(.+?)(?:\s*\(default:\s*(.+?)\))?$", re.MULTILINE
    )
    FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---", re.DOTALL)

    def parse_file(self, file_path: str | Path) -> Runbook:
        """Parse a Markdown runbook file."""
        path = Path(file_path)
        if not path.exists():
            raise RunbookError(f"Runbook file not found: {path}")

        content = path.read_text()
        runbook = self.parse(content)
        runbook.source_file = str(path)
        return runbook

    def parse(self, content: str) -> Runbook:
        """Parse Markdown content to Runbook."""
        # Extract frontmatter if present
        frontmatter: dict[str, Any] = {}
        fm_match = self.FRONTMATTER_PATTERN.match(content)
        if fm_match:
            try:
                frontmatter = yaml.safe_load(fm_match.group(1)) or {}
            except yaml.YAMLError:
                pass
            content = content[fm_match.end() :].strip()

        # Extract title
        title_match = self.TITLE_PATTERN.search(content)
        if not title_match:
            raise RunbookError("Runbook must have a title (# Runbook: Name)")

        name = title_match.group(1).strip()

        # Extract description (text between title and first section)
        title_end = title_match.end()
        first_section = self.SECTION_PATTERN.search(content, title_end)
        if first_section:
            description = content[title_end : first_section.start()].strip()
        else:
            description = ""

        # Parse sections
        variables: dict[str, Any] = frontmatter.get("variables", {})
        parameters: list[dict[str, Any]] = frontmatter.get("parameters", [])
        steps: list[RunbookStep] = []
        tags: list[str] = frontmatter.get("tags", [])

        sections = self._split_sections(content)

        for section_name, section_content in sections.items():
            section_lower = section_name.lower()

            if section_lower == "variables":
                parsed_vars = self._parse_variables(section_content)
                variables.update(parsed_vars)

            elif section_lower == "parameters":
                parameters.extend(self._parse_parameters(section_content))

            elif section_lower == "steps":
                steps = self._parse_steps(section_content)

        return Runbook(
            name=name,
            description=description,
            version=frontmatter.get("version", "1.0.0"),
            author=frontmatter.get("author", ""),
            steps=steps,
            variables=variables,
            parameters=parameters,
            tags=tags,
            stop_on_failure=frontmatter.get("stop_on_failure", True),
            dry_run_supported=frontmatter.get("dry_run_supported", True),
        )

    def _split_sections(self, content: str) -> dict[str, str]:
        """Split content into sections by ## headers."""
        sections: dict[str, str] = {}
        matches = list(self.SECTION_PATTERN.finditer(content))

        for i, match in enumerate(matches):
            name = match.group(1).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            sections[name] = content[start:end].strip()

        return sections

    def _parse_variables(self, content: str) -> dict[str, Any]:
        """Parse variables section."""
        variables: dict[str, Any] = {}

        for match in self.VARIABLE_PATTERN.finditer(content):
            var_name = match.group(1)
            default = match.group(3)
            if default:
                # Try to parse as YAML value
                try:
                    variables[var_name] = yaml.safe_load(default)
                except yaml.YAMLError:
                    variables[var_name] = default
            else:
                variables[var_name] = None

        return variables

    def _parse_parameters(self, content: str) -> list[dict[str, Any]]:
        """Parse parameters section."""
        parameters: list[dict[str, Any]] = []

        for match in self.VARIABLE_PATTERN.finditer(content):
            param = {
                "name": match.group(1),
                "description": match.group(2).strip(),
            }
            if match.group(3):
                param["default"] = match.group(3)
            parameters.append(param)

        return parameters

    def _parse_steps(self, content: str) -> list[RunbookStep]:
        """Parse steps section."""
        steps: list[RunbookStep] = []
        step_matches = list(self.STEP_PATTERN.finditer(content))

        for i, match in enumerate(step_matches):
            step_num = match.group(1)
            step_name = match.group(2).strip()
            step_options = match.group(3)

            # Get step content
            start = match.end()
            end = step_matches[i + 1].start() if i + 1 < len(step_matches) else len(content)
            step_content = content[start:end].strip()

            step = self._parse_step(step_num, step_name, step_options, step_content)
            steps.append(step)

        return steps

    def _parse_step(
        self,
        step_num: str,
        step_name: str,
        options_str: str | None,
        content: str,
    ) -> RunbookStep:
        """Parse a single step."""
        # Parse options from [option1, option2: value]
        options = self._parse_step_options(options_str)

        # Determine step type
        step_type = StepType.COMMAND  # Default
        if "prompt" in options:
            step_type = StepType.PROMPT
        elif "manual" in options:
            step_type = StepType.MANUAL
        elif "wait" in options:
            step_type = StepType.WAIT
        elif "notify" in options:
            step_type = StepType.NOTIFY
        elif "parallel" in options:
            step_type = StepType.PARALLEL

        # Extract code blocks
        code_blocks = self.CODE_BLOCK_PATTERN.findall(content)
        command = None
        shell = "/bin/bash"

        if code_blocks:
            lang, code = code_blocks[0]
            command = code.strip()
            if lang:
                shell = f"/bin/{lang}" if lang in ("bash", "sh", "zsh") else lang

            # Multi-line scripts use script type
            if "\n" in command:
                step_type = StepType.SCRIPT

        # Get description (text before code blocks)
        description = self.CODE_BLOCK_PATTERN.split(content)[0].strip()

        # Build step
        step = RunbookStep(
            id=f"step_{step_num}",
            name=step_name,
            type=step_type,
            description=description,
            command=command,
            shell=shell,
            when=options.get("when"),
            on_failure=options.get("on_failure", "fail"),
            timeout=int(options.get("timeout", 300)),
            retries=int(options.get("retries", 0)),
            register=options.get("register"),
        )

        # Prompt-specific options
        if step_type == StepType.PROMPT:
            step.prompt_message = description or f"Confirm: {step_name}?"
            step.prompt_type = options.get("prompt_type", "confirm")

        # Wait-specific options
        if step_type == StepType.WAIT:
            step.wait_condition = command or options.get("condition")
            step.wait_timeout = int(options.get("wait_timeout", 300))
            step.wait_interval = int(options.get("wait_interval", 10))

        # Notify-specific options
        if step_type == StepType.NOTIFY:
            step.notify_channel = options.get("channel")
            step.notify_message = description or step_name

        return step

    def _parse_step_options(self, options_str: str | None) -> dict[str, Any]:
        """Parse step options from [option1, key: value] format."""
        options: dict[str, Any] = {}

        if not options_str:
            return options

        # Split by comma, but respect nested structures
        parts = options_str.split(",")

        for part in parts:
            part = part.strip()
            if ":" in part:
                key, value = part.split(":", 1)
                options[key.strip()] = value.strip()
            else:
                options[part] = True

        return options
