"""Dependency graph for workflow steps."""

from collections import defaultdict
from typing import TYPE_CHECKING

from devctl.core.exceptions import WorkflowError

if TYPE_CHECKING:
    from devctl.workflows.schema import WorkflowStepSchema


class DependencyCycleError(WorkflowError):
    """Raised when a circular dependency is detected."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        cycle_str = " -> ".join(cycle)
        super().__init__(f"circular dependency detected: {cycle_str}")


class DependencyGraph:
    """Build and manage step dependency graph (DAG)."""

    def __init__(self, steps: list["WorkflowStepSchema"]):
        """Initialize the dependency graph.

        Args:
            steps: list of workflow steps with depends_on fields
        """
        self.steps = {s.name: s for s in steps}
        self.dependencies: dict[str, set[str]] = defaultdict(set)
        self.dependents: dict[str, set[str]] = defaultdict(set)
        self._build_graph(steps)

    def _build_graph(self, steps: list["WorkflowStepSchema"]) -> None:
        """Build adjacency lists for dependencies."""
        for step in steps:
            step_name = step.name
            deps = getattr(step, "depends_on", []) or []

            for dep in deps:
                if dep not in self.steps:
                    raise WorkflowError(
                        f"step '{step_name}' depends on unknown step '{dep}'"
                    )
                self.dependencies[step_name].add(dep)
                self.dependents[dep].add(step_name)

    def validate(self) -> None:
        """Check for cycles and validate the graph.

        Raises:
            DependencyCycleError: if a cycle is detected
        """
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for dep in self.dependencies.get(node, set()):
                if dep not in visited:
                    if has_cycle(dep):
                        return True
                elif dep in rec_stack:
                    # found cycle - build cycle path
                    cycle_start = path.index(dep)
                    cycle = path[cycle_start:] + [dep]
                    raise DependencyCycleError(cycle)

            path.pop()
            rec_stack.remove(node)
            return False

        for step_name in self.steps:
            if step_name not in visited:
                has_cycle(step_name)

    def get_ready_steps(self, completed: set[str]) -> list[str]:
        """Get steps ready to execute (all dependencies satisfied).

        Args:
            completed: set of completed step names

        Returns:
            list of step names ready to execute
        """
        ready = []
        for step_name in self.steps:
            if step_name in completed:
                continue

            deps = self.dependencies.get(step_name, set())
            if deps.issubset(completed):
                ready.append(step_name)

        return ready

    def get_root_steps(self) -> list[str]:
        """Get steps with no dependencies (entry points).

        Returns:
            list of step names with no dependencies
        """
        return [
            name for name in self.steps if not self.dependencies.get(name)
        ]

    def topological_sort(self) -> list[list[str]]:
        """Return execution layers (parallelizable groups).

        Steps in the same layer can run in parallel.
        Each layer depends on all previous layers.

        Returns:
            list of layers, each layer is a list of step names
        """
        self.validate()

        layers: list[list[str]] = []
        completed: set[str] = set()

        while len(completed) < len(self.steps):
            ready = self.get_ready_steps(completed)
            if not ready:
                # this shouldn't happen if validation passed
                remaining = set(self.steps.keys()) - completed
                raise WorkflowError(f"unable to resolve dependencies for: {remaining}")

            layers.append(ready)
            completed.update(ready)

        return layers

    def has_dependencies(self) -> bool:
        """Check if any step has dependencies.

        Returns:
            True if any step has depends_on set
        """
        return any(self.dependencies.values())
