"""Compatibility facade for the modular Smarti agent runtime."""
# Public compatibility facade only.
# Do not add SmartiCore behavior here; put runtime logic in smarti/agent/*.
from .agent.shared import *
from .agent.lifecycle import LifecycleMixin
from .agent.browser_runtime import BrowserRuntimeMixin
from .agent.execution_policy import ExecutionPolicyMixin
from .agent.tool_calls import ToolCallMixin
from .agent.runtime_services import RuntimeServicesMixin
from .agent.background_runtime import BackgroundRuntimeMixin
from .agent.extensions import ExtensionsMixin
from .agent.model_context import ModelContextMixin
from .agent.messaging import MessagingMixin
from .agent.automation import AutomationMixin
from .agent.tool_dispatch import ToolDispatchMixin
from .agent.system_tools import SystemToolsMixin
from .agent.web_content import WebContentMixin
from .agent.email_tools import EmailToolsMixin
from .agent.productivity_tools import ProductivityToolsMixin
from .agent.speech import SpeechMixin


class SmartiCore(
    LifecycleMixin,
    BrowserRuntimeMixin,
    ExecutionPolicyMixin,
    ToolCallMixin,
    RuntimeServicesMixin,
    BackgroundRuntimeMixin,
    ExtensionsMixin,
    ModelContextMixin,
    MessagingMixin,
    AutomationMixin,
    ToolDispatchMixin,
    SystemToolsMixin,
    WebContentMixin,
    EmailToolsMixin,
    ProductivityToolsMixin,
    SpeechMixin,
):
    """Main Smarti agent runtime assembled from focused domain mixins."""
    pass


__all__ = [name for name in globals() if not name.startswith("__")]
