"""Import sandbox for Kage plugins."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

from kage.plugins.schema import BLOCKED_IMPORTS, DEFAULT_ALLOWED_IMPORTS


class SandboxViolation(Exception):
    """Raised when a plugin attempts to use blocked functionality."""

    pass


class RestrictedImporter:
    """Custom importer that restricts what plugins can import."""

    def __init__(self, allowed_imports: list[str] | None = None) -> None:
        self.allowed_imports = set(allowed_imports or DEFAULT_ALLOWED_IMPORTS)
        self.blocked_imports = set(BLOCKED_IMPORTS)

    def is_allowed(self, module_name: str) -> bool:
        """Check if a module import is allowed."""
        # Check blocked list first
        for blocked in self.blocked_imports:
            if module_name == blocked or module_name.startswith(f"{blocked}."):
                return False

        # Check allowed list
        for allowed in self.allowed_imports:
            if module_name == allowed or module_name.startswith(f"{allowed}."):
                return True

        return False

    def restricted_import(
        self,
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> ModuleType:
        """Restricted import function for use in plugin execution."""
        if not self.is_allowed(name):
            raise SandboxViolation(
                f"Import of '{name}' is not allowed in plugins. "
                f"Allowed modules: {', '.join(sorted(self.allowed_imports))}"
            )

        return importlib.__import__(name, globals, locals, fromlist, level)


class PluginSandbox:
    """Sandbox environment for executing plugins."""

    def __init__(self, allowed_imports: list[str] | None = None) -> None:
        self.importer = RestrictedImporter(allowed_imports)
        self._original_import: Any = None

    def create_restricted_globals(self) -> dict[str, Any]:
        """Create a restricted globals dict for plugin execution."""
        restricted_builtins = {
            # Safe builtins
            "True": True,
            "False": False,
            "None": None,
            "abs": abs,
            "all": all,
            "any": any,
            "ascii": ascii,
            "bin": bin,
            "bool": bool,
            "bytearray": bytearray,
            "bytes": bytes,
            "chr": chr,
            "dict": dict,
            "divmod": divmod,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "format": format,
            "frozenset": frozenset,
            "hash": hash,
            "hex": hex,
            "int": int,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "iter": iter,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "next": next,
            "oct": oct,
            "ord": ord,
            "pow": pow,
            "print": print,  # Allow print for debugging
            "range": range,
            "repr": repr,
            "reversed": reversed,
            "round": round,
            "set": set,
            "slice": slice,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "type": type,
            "zip": zip,
            # Restricted import
            "__import__": self.importer.restricted_import,
        }

        return {
            "__builtins__": restricted_builtins,
            "__name__": "__plugin__",
            "__doc__": None,
        }

    def execute_code(
        self, code: str, extra_globals: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute code in the sandbox and return the resulting namespace."""
        sandbox_globals = self.create_restricted_globals()
        if extra_globals:
            sandbox_globals.update(extra_globals)

        exec(code, sandbox_globals)
        return sandbox_globals

    def load_module_from_file(self, filepath: str, module_name: str) -> ModuleType:
        """Load a module from file with import restrictions."""
        with open(filepath) as f:
            code = f.read()

        # Create module
        module = ModuleType(module_name)
        module.__file__ = filepath

        # Execute in sandbox
        sandbox_globals = self.create_restricted_globals()
        sandbox_globals["__name__"] = module_name
        sandbox_globals["__file__"] = filepath

        try:
            exec(code, sandbox_globals)
        except SandboxViolation:
            raise
        except Exception as e:
            raise SandboxViolation(f"Error loading plugin: {e}") from e

        # Copy sandbox globals to module
        for key, value in sandbox_globals.items():
            if not key.startswith("__"):
                setattr(module, key, value)

        return module


def validate_plugin_code(code: str) -> tuple[bool, list[str]]:
    """Validate plugin code for security issues.

    Returns:
        Tuple of (is_safe, list of warnings/errors)
    """
    import ast

    issues = []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"Syntax error: {e}"]

    for node in ast.walk(tree):
        # Check for dangerous function calls
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("eval", "exec", "compile", "__import__")
        ):
            issues.append(f"Line {node.lineno}: Use of '{node.func.id}' is restricted")

        # Check for dangerous attribute access
        if (
            isinstance(node, ast.Attribute)
            and node.attr in ("__class__", "__bases__", "__subclasses__", "__globals__")
        ):
            issues.append(f"Line {node.lineno}: Access to '{node.attr}' is restricted")

        # Check for import statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in BLOCKED_IMPORTS:
                    issues.append(f"Line {node.lineno}: Import of '{alias.name}' is blocked")

        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in BLOCKED_IMPORTS
        ):
            issues.append(f"Line {node.lineno}: Import from '{node.module}' is blocked")

    return len(issues) == 0, issues
