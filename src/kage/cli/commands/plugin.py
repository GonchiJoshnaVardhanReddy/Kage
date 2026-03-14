"""Plugin management CLI commands."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kage.cli.ui.themes import KAGE_THEME
from kage.plugins import PluginLoadError, PluginManager

plugin_app = typer.Typer(help="Plugin management commands")
console = Console(theme=KAGE_THEME)


def get_plugin_dirs() -> list[Path]:
    """Get default plugin directories."""
    dirs = []

    # Built-in plugins
    project_root = Path(__file__).parent.parent.parent.parent.parent
    builtin = project_root / "plugins"
    if builtin.exists():
        dirs.append(builtin)

    # User plugins
    user_plugins = Path.home() / ".local" / "share" / "kage" / "plugins"
    if user_plugins.exists():
        dirs.append(user_plugins)

    return dirs


@plugin_app.command("list")
def list_plugins() -> None:
    """List available plugins."""
    manager = PluginManager(get_plugin_dirs())
    discovered = manager.discover_plugins()

    if not discovered:
        console.print("[yellow]No plugins found.[/yellow]")
        console.print("\nPlugin directories searched:")
        for d in manager.plugin_dirs:
            console.print(f"  • {d}")
        return

    table = Table(title="Available Plugins", style="bright_white")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Category", style="yellow")
    table.add_column("Description", style="dim")
    table.add_column("Capabilities", style="magenta")

    for _plugin_dir, schema in discovered:
        cap_count = len(schema.capabilities)
        table.add_row(
            schema.name,
            schema.version,
            schema.category,
            schema.description[:50] + "..." if len(schema.description) > 50 else schema.description,
            str(cap_count),
        )

    console.print(table)


@plugin_app.command("info")
def plugin_info(name: str = typer.Argument(..., help="Plugin name")) -> None:
    """Show detailed plugin information."""
    manager = PluginManager(get_plugin_dirs())
    discovered = manager.discover_plugins()

    for _plugin_dir, schema in discovered:
        if schema.name == name:
            console.print(f"\n[cyan bold]{schema.name}[/cyan bold] v{schema.version}")
            console.print(f"[dim]{schema.description}[/dim]\n")

            if schema.author:
                console.print(f"[yellow]Author:[/yellow] {schema.author}")
            console.print(f"[yellow]Category:[/yellow] {schema.category}")
            console.print(f"[yellow]Entry Point:[/yellow] {schema.entry_point}")

            if schema.required_tools:
                console.print(
                    f"[yellow]Required Tools:[/yellow] {', '.join(schema.required_tools)}"
                )

            if schema.capabilities:
                console.print("\n[cyan]Capabilities:[/cyan]")
                for cap in schema.capabilities:
                    approval = (
                        "[red]⚠ requires approval[/red]"
                        if cap.requires_approval
                        else "[green]✓ no approval needed[/green]"
                    )
                    console.print(f"  • [bold]{cap.name}[/bold] - {cap.description}")
                    console.print(f"    {approval}")

                    if cap.parameters:
                        for param in cap.parameters:
                            req = "[red]*[/red]" if param.get("required", True) else ""
                            default = (
                                f" (default: {param.get('default')})" if "default" in param else ""
                            )
                            console.print(
                                f"      - {param['name']}{req}: {param.get('description', '')}{default}"
                            )

            return

    console.print(f"[red]Plugin not found: {name}[/red]")


@plugin_app.command("load")
def load_plugin(name: str = typer.Argument(..., help="Plugin name to load")) -> None:
    """Load and validate a plugin."""
    manager = PluginManager(get_plugin_dirs())
    discovered = manager.discover_plugins()

    for plugin_dir, schema in discovered:
        if schema.name == name:
            try:
                plugin = manager.load_plugin(plugin_dir)
                console.print(f"[green]✓ Plugin '{name}' loaded successfully[/green]")

                # Check requirements
                available, missing = plugin.check_requirements()
                if not available:
                    console.print(f"[yellow]⚠ Missing tools: {', '.join(missing)}[/yellow]")

                # List capabilities
                caps = plugin.get_capabilities()
                console.print(f"\n[cyan]Registered {len(caps)} capabilities:[/cyan]")
                for cap in caps:
                    console.print(f"  • {cap.name}")

            except PluginLoadError as e:
                console.print(f"[red]✗ Failed to load plugin: {e}[/red]")
            return

    console.print(f"[red]Plugin not found: {name}[/red]")


@plugin_app.command("validate")
def validate_plugin(path: str = typer.Argument(..., help="Path to plugin directory")) -> None:
    """Validate a plugin without loading it."""
    from kage.plugins.sandbox import validate_plugin_code
    from kage.plugins.schema import PluginSchema

    plugin_dir = Path(path)
    if not plugin_dir.exists():
        console.print(f"[red]Directory not found: {path}[/red]")
        raise typer.Exit(1)

    yaml_path = plugin_dir / "plugin.yaml"
    if not yaml_path.exists():
        console.print(f"[red]No plugin.yaml found in {path}[/red]")
        raise typer.Exit(1)

    # Validate schema
    try:
        schema = PluginSchema.from_yaml(yaml_path)
        console.print("[green]✓ plugin.yaml is valid[/green]")
    except Exception as e:
        console.print(f"[red]✗ Invalid plugin.yaml: {e}[/red]")
        raise typer.Exit(1) from e

    # Validate code
    plugin_file = plugin_dir / schema.entry_point
    if not plugin_file.exists():
        console.print(f"[red]✗ Entry point not found: {schema.entry_point}[/red]")
        raise typer.Exit(1)

    with open(plugin_file) as f:
        code = f.read()

    is_safe, issues = validate_plugin_code(code)
    if is_safe:
        console.print("[green]✓ Plugin code passed security checks[/green]")
    else:
        console.print("[red]✗ Plugin code has security issues:[/red]")
        for issue in issues:
            console.print(f"  • {issue}")
        raise typer.Exit(1)

    console.print(f"\n[green]Plugin '{schema.name}' is valid and ready to use[/green]")


@plugin_app.command("create")
def create_plugin(
    name: str = typer.Argument(..., help="Plugin name"),
    output_dir: str = typer.Option(
        ".",
        "--output",
        "-o",
        help="Output directory for the plugin",
    ),
) -> None:
    """Create a new plugin scaffold."""
    from kage.plugins.schema import CapabilitySchema, PluginSchema

    plugin_dir = Path(output_dir) / name
    if plugin_dir.exists():
        console.print(f"[red]Directory already exists: {plugin_dir}[/red]")
        raise typer.Exit(1)

    plugin_dir.mkdir(parents=True)

    # Create plugin.yaml
    schema = PluginSchema(
        name=name,
        version="1.0.0",
        description=f"TODO: Add description for {name} plugin",
        author="Your Name",
        category="general",
        capabilities=[
            CapabilitySchema(
                name=f"{name}_example",
                description="Example capability - replace with your own",
                parameters=[
                    {
                        "name": "target",
                        "description": "Target to operate on",
                        "type": "string",
                        "required": True,
                    }
                ],
            )
        ],
    )
    schema.to_yaml(plugin_dir / "plugin.yaml")

    # Create plugin.py
    plugin_code = f'''"""TODO: Add description for {name} plugin."""

from kage.plugins.base import BasePlugin, CapabilityParameter


class Plugin(BasePlugin):
    """{name.capitalize()} plugin."""

    @property
    def name(self) -> str:
        return "{name}"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "TODO: Add description"

    def setup(self) -> None:
        """Register capabilities."""
        self.register_capability(
            name="{name}_example",
            description="Example capability - replace with your own",
            handler=self._example_handler,
            parameters=[
                CapabilityParameter(
                    name="target",
                    description="Target to operate on",
                    param_type="string",
                    required=True,
                ),
            ],
        )

    def _example_handler(self, target: str) -> dict:
        """Example handler - replace with your implementation."""
        return {{
            "type": "command_suggestion",
            "command": f"echo 'Processing {{target}}'",
            "description": f"Example command for {{target}}",
        }}
'''
    with open(plugin_dir / "plugin.py", "w") as f:
        f.write(plugin_code)

    console.print(f"[green]✓ Created plugin scaffold at {plugin_dir}[/green]")
    console.print("\nNext steps:")
    console.print(f"  1. Edit {plugin_dir / 'plugin.yaml'} to define capabilities")
    console.print(f"  2. Implement handlers in {plugin_dir / 'plugin.py'}")
    console.print(f"  3. Validate with: kage plugin validate {plugin_dir}")
