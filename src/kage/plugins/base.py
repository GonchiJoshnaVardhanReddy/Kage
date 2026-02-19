"""Base plugin class for Kage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from kage.core.models import Session


@dataclass
class CapabilityParameter:
    """Parameter definition for a capability."""

    name: str
    description: str
    param_type: str = "string"  # string, int, float, bool, list
    required: bool = True
    default: Any = None


@dataclass
class Capability:
    """A capability provided by a plugin."""

    name: str
    description: str
    handler: Callable[..., Any]
    parameters: list[CapabilityParameter] = field(default_factory=list)
    returns: str = "string"
    dangerous: bool = False
    requires_approval: bool = True
    category: str = "general"

    def to_tool_schema(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible tool schema."""
        properties = {}
        required = []

        for param in self.parameters:
            prop: dict[str, Any] = {"description": param.description}

            # Map param types
            type_map = {
                "string": "string",
                "int": "integer",
                "float": "number",
                "bool": "boolean",
                "list": "array",
            }
            prop["type"] = type_map.get(param.param_type, "string")

            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class PluginContext:
    """Context provided to plugins during execution."""

    def __init__(
        self,
        session: "Session",
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.session = session
        self._log_fn = log_fn

    @property
    def targets(self) -> list[str]:
        """Get current scope targets."""
        return [t.value for t in self.session.scope.targets]

    @property
    def safe_mode(self) -> bool:
        """Check if safe mode is enabled."""
        return self.session.safe_mode

    def log(self, message: str) -> None:
        """Log a message."""
        if self._log_fn:
            self._log_fn(message)


class BasePlugin(ABC):
    """Abstract base class for Kage plugins."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._context: PluginContext | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Plugin description."""
        ...

    @property
    def author(self) -> str | None:
        """Plugin author."""
        return None

    @property
    def category(self) -> str:
        """Plugin category (recon, enum, exploit, etc.)."""
        return "general"

    @property
    def required_tools(self) -> list[str]:
        """List of external tools required by this plugin."""
        return []

    def set_context(self, context: PluginContext) -> None:
        """Set the plugin context."""
        self._context = context

    @property
    def context(self) -> PluginContext:
        """Get the plugin context."""
        if self._context is None:
            raise RuntimeError("Plugin context not set")
        return self._context

    def register_capability(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        parameters: list[CapabilityParameter] | None = None,
        dangerous: bool = False,
        requires_approval: bool = True,
        category: str | None = None,
    ) -> None:
        """Register a capability."""
        self._capabilities[name] = Capability(
            name=name,
            description=description,
            handler=handler,
            parameters=parameters or [],
            dangerous=dangerous,
            requires_approval=requires_approval,
            category=category or self.category,
        )

    def get_capabilities(self) -> list[Capability]:
        """Get all registered capabilities."""
        return list(self._capabilities.values())

    def get_capability(self, name: str) -> Capability | None:
        """Get a specific capability by name."""
        return self._capabilities.get(name)

    async def invoke(self, capability_name: str, **kwargs: Any) -> Any:
        """Invoke a capability by name."""
        capability = self._capabilities.get(capability_name)
        if not capability:
            raise ValueError(f"Unknown capability: {capability_name}")

        # Validate parameters
        for param in capability.parameters:
            if param.required and param.name not in kwargs:
                if param.default is not None:
                    kwargs[param.name] = param.default
                else:
                    raise ValueError(f"Missing required parameter: {param.name}")

        # Call handler
        result = capability.handler(**kwargs)

        # Handle async handlers
        if hasattr(result, "__await__"):
            result = await result

        return result

    @abstractmethod
    def setup(self) -> None:
        """Set up the plugin and register capabilities."""
        ...

    def cleanup(self) -> None:
        """Clean up plugin resources."""
        pass

    def check_requirements(self) -> tuple[bool, list[str]]:
        """Check if required tools are available.
        
        Returns:
            Tuple of (all_available, list of missing tools)
        """
        import shutil

        missing = []
        for tool in self.required_tools:
            if not shutil.which(tool):
                missing.append(tool)

        return len(missing) == 0, missing
