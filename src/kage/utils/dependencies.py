"""Runtime dependency checker for Kage."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table


@dataclass
class Dependency:
    """A runtime dependency."""

    name: str
    check: Callable[[], bool]
    required: bool = False
    install_hint: str | None = None
    category: str = "general"


def check_python_version() -> bool:
    """Check Python version is 3.10+."""
    return sys.version_info >= (3, 10)


def check_command_exists(cmd: str) -> Callable[[], bool]:
    """Create a checker for a shell command."""
    def checker() -> bool:
        return shutil.which(cmd) is not None
    return checker


def check_docker() -> bool:
    """Check if Docker is available and running."""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def check_module(module_name: str) -> Callable[[], bool]:
    """Create a checker for a Python module."""
    def checker() -> bool:
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False
    return checker


# All dependencies Kage may need
DEPENDENCIES: list[Dependency] = [
    # Core requirements
    Dependency(
        name="Python 3.10+",
        check=check_python_version,
        required=True,
        install_hint="Download from https://python.org",
        category="core",
    ),

    # Security tools (optional but recommended)
    Dependency(
        name="nmap",
        check=check_command_exists("nmap"),
        required=False,
        install_hint="apt install nmap / brew install nmap",
        category="recon",
    ),
    Dependency(
        name="gobuster",
        check=check_command_exists("gobuster"),
        required=False,
        install_hint="apt install gobuster / go install github.com/OJ/gobuster/v3@latest",
        category="enum",
    ),
    Dependency(
        name="nikto",
        check=check_command_exists("nikto"),
        required=False,
        install_hint="apt install nikto",
        category="enum",
    ),
    Dependency(
        name="sqlmap",
        check=check_command_exists("sqlmap"),
        required=False,
        install_hint="apt install sqlmap / pip install sqlmap",
        category="exploit",
    ),
    Dependency(
        name="hydra",
        check=check_command_exists("hydra"),
        required=False,
        install_hint="apt install hydra",
        category="bruteforce",
    ),
    Dependency(
        name="curl",
        check=check_command_exists("curl"),
        required=False,
        install_hint="apt install curl / brew install curl",
        category="network",
    ),
    Dependency(
        name="ffuf",
        check=check_command_exists("ffuf"),
        required=False,
        install_hint="go install github.com/ffuf/ffuf/v2@latest",
        category="enum",
    ),
    Dependency(
        name="nuclei",
        check=check_command_exists("nuclei"),
        required=False,
        install_hint="go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
        category="vuln",
    ),

    # Docker (for MCP servers)
    Dependency(
        name="docker",
        check=check_docker,
        required=False,
        install_hint="Install Docker Desktop or docker-ce",
        category="mcp",
    ),

    # Optional Python packages
    Dependency(
        name="weasyprint (PDF reports)",
        check=check_module("weasyprint"),
        required=False,
        install_hint="pip install weasyprint",
        category="reporting",
    ),
]


class DependencyChecker:
    """Checks and reports on runtime dependencies."""

    def __init__(self, dependencies: list[Dependency] | None = None) -> None:
        self.dependencies = dependencies or DEPENDENCIES
        self._results: dict[str, bool] = {}

    def check_all(self) -> dict[str, bool]:
        """Check all dependencies and return results."""
        self._results = {}
        for dep in self.dependencies:
            try:
                self._results[dep.name] = dep.check()
            except Exception:
                self._results[dep.name] = False
        return self._results

    def check_required(self) -> tuple[bool, list[Dependency]]:
        """Check only required dependencies.

        Returns:
            Tuple of (all_satisfied, list_of_missing)
        """
        if not self._results:
            self.check_all()

        missing = []
        for dep in self.dependencies:
            if dep.required and not self._results.get(dep.name, False):
                missing.append(dep)

        return len(missing) == 0, missing

    def get_available_tools(self) -> list[str]:
        """Get list of available security tools."""
        if not self._results:
            self.check_all()

        return [
            dep.name
            for dep in self.dependencies
            if self._results.get(dep.name, False)
            and dep.category in ("recon", "enum", "exploit", "bruteforce", "vuln")
        ]

    def print_report(self, console: Console, show_all: bool = False) -> None:
        """Print dependency status report."""
        if not self._results:
            self.check_all()

        # Group by category
        categories: dict[str, list[tuple[Dependency, bool]]] = {}
        for dep in self.dependencies:
            status = self._results.get(dep.name, False)
            if show_all or dep.required or status:
                if dep.category not in categories:
                    categories[dep.category] = []
                categories[dep.category].append((dep, status))

        # Print table
        table = Table(title="Kage Dependencies", header_style="bold cyan")
        table.add_column("Tool", style="white")
        table.add_column("Status", justify="center")
        table.add_column("Category", style="dim")
        table.add_column("Install Hint", style="dim")

        category_order = ["core", "recon", "enum", "exploit", "vuln", "bruteforce", "network", "mcp", "reporting"]

        for category in category_order:
            if category not in categories:
                continue

            for dep, status in categories[category]:
                status_str = "[green]✓[/green]" if status else "[red]✗[/red]"
                hint = dep.install_hint or "" if not status else ""
                table.add_row(dep.name, status_str, category, hint)

        console.print(table)

        # Summary
        available = sum(1 for r in self._results.values() if r)
        total = len(self._results)
        console.print()
        console.print(f"[info]{available}/{total} dependencies available[/info]")


def check_startup_dependencies(console: Console) -> bool:
    """Quick check of required dependencies on startup.

    Returns True if all required deps are satisfied.
    """
    checker = DependencyChecker()
    satisfied, missing = checker.check_required()

    if not satisfied:
        console.print("[error]Missing required dependencies:[/error]")
        for dep in missing:
            console.print(f"  [red]✗[/red] {dep.name}")
            if dep.install_hint:
                console.print(f"    [dim]{dep.install_hint}[/dim]")
        console.print()
        return False

    return True
