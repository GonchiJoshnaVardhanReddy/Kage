"""Unit tests for the plugin capability system."""

import pytest

from kage.core.models import Session
from kage.plugins.base import (
    BasePlugin,
    Capability,
    CapabilityParameter,
    PluginContext,
    capability,
)

# --- Concrete test plugin ---------------------------------------------------


class DummyPlugin(BasePlugin):
    """A concrete plugin for testing."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def description(self) -> str:
        return "A dummy plugin for tests"

    @capability(
        name="safe_action",
        description="A safe action",
        parameters=[CapabilityParameter(name="target", description="target host")],
        dangerous=False,
    )
    def safe_action(self, target: str) -> str:
        return f"safe:{target}"

    @capability(
        name="dangerous_action",
        description="A dangerous action",
        dangerous=True,
        requires_approval=True,
    )
    def dangerous_action(self) -> str:
        return "boom"

    @capability(
        name="dangerous_no_approval",
        description="Dangerous but does not require approval",
        dangerous=True,
        requires_approval=False,
    )
    def dangerous_no_approval(self) -> str:
        return "ok"

    def setup(self) -> None:
        self._auto_register_capabilities()


# --- Tests -------------------------------------------------------------------


@pytest.fixture
def plugin():
    """Create a DummyPlugin with context set."""
    p = DummyPlugin()
    ctx = PluginContext(session=Session(), log_fn=None)
    p.set_context(ctx)
    return p


class TestCapabilityDecorator:
    """@capability decorator registers metadata on the function."""

    def test_decorator_stores_meta(self, plugin):
        """Decorated method has _capability_meta attribute."""
        assert hasattr(plugin.safe_action, "_capability_meta")
        meta = plugin.safe_action._capability_meta
        assert meta["name"] == "safe_action"
        assert meta["dangerous"] is False

    def test_decorator_dangerous_flag(self, plugin):
        """Dangerous flag is correctly stored."""
        meta = plugin.dangerous_action._capability_meta
        assert meta["dangerous"] is True
        assert meta["requires_approval"] is True


class TestAutoRegisterCapabilities:
    """_auto_register_capabilities discovers decorated methods."""

    def test_auto_register_finds_all(self, plugin):
        """All decorated methods are registered."""
        plugin.setup()
        caps = plugin.get_capabilities()
        cap_names = {c.name for c in caps}
        assert "safe_action" in cap_names
        assert "dangerous_action" in cap_names
        assert "dangerous_no_approval" in cap_names

    def test_auto_register_sets_handler(self, plugin):
        """Registered capability has a callable handler."""
        plugin.setup()
        cap = plugin.get_capability("safe_action")
        assert cap is not None
        assert callable(cap.handler)

    def test_manual_register(self, plugin):
        """register_capability() works independently of decorator."""
        plugin.register_capability(
            name="manual_cap",
            description="Manually registered",
            handler=lambda: "manual",
        )
        cap = plugin.get_capability("manual_cap")
        assert cap is not None
        assert cap.name == "manual_cap"


class TestInvoke:
    """Invoke enforces dangerous-capability rules."""

    async def test_invoke_safe_capability(self, plugin):
        """Safe capability can be invoked normally."""
        plugin.setup()
        result = await plugin.invoke("safe_action", target="10.0.0.1")
        assert result == "safe:10.0.0.1"

    async def test_invoke_dangerous_requires_approval_raises(self, plugin):
        """Dangerous + requires_approval raises PermissionError."""
        plugin.setup()
        with pytest.raises(PermissionError, match="dangerous"):
            await plugin.invoke("dangerous_action")

    async def test_invoke_dangerous_no_approval_succeeds(self, plugin):
        """Dangerous with requires_approval=False can be invoked."""
        plugin.setup()
        result = await plugin.invoke("dangerous_no_approval")
        assert result == "ok"

    async def test_invoke_unknown_capability_raises(self, plugin):
        """Invoking an unregistered capability raises ValueError."""
        plugin.setup()
        with pytest.raises(ValueError, match="Unknown capability"):
            await plugin.invoke("nonexistent")

    async def test_invoke_missing_required_param_raises(self, plugin):
        """Missing required parameter raises ValueError."""
        plugin.setup()
        with pytest.raises(ValueError, match="Missing required parameter"):
            await plugin.invoke("safe_action")


class TestCapabilityToolSchema:
    """Capability.to_tool_schema produces valid OpenAI-style schema."""

    def test_schema_structure(self):
        """Schema has expected top-level keys."""
        cap = Capability(
            name="test",
            description="desc",
            handler=lambda: None,
            parameters=[
                CapabilityParameter(name="host", description="hostname", param_type="string"),
                CapabilityParameter(
                    name="port", description="port", param_type="int", required=False, default=80
                ),
            ],
        )
        schema = cap.to_tool_schema()
        assert schema["type"] == "function"
        func = schema["function"]
        assert func["name"] == "test"
        assert "host" in func["parameters"]["properties"]
        assert "host" in func["parameters"]["required"]
        assert "port" not in func["parameters"]["required"]
