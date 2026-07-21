"""Domain mixins that compose the SmartiCore runtime."""
from .lifecycle import LifecycleMixin
from .browser_runtime import BrowserRuntimeMixin
from .execution_policy import ExecutionPolicyMixin
from .context_compaction import ContextCompactionMixin
from .tool_calls import ToolCallMixin
from .runtime_services import RuntimeServicesMixin
from .background_runtime import BackgroundRuntimeMixin
from .extensions import ExtensionsMixin
from .model_context import ModelContextMixin
from .messaging import MessagingMixin
from .automation import AutomationMixin
from .tool_dispatch import ToolDispatchMixin
from .system_tools import SystemToolsMixin
from .web_content import WebContentMixin
from .email_tools import EmailToolsMixin
from .productivity_tools import ProductivityToolsMixin
from .speech import SpeechMixin

__all__ = [
    "LifecycleMixin",
    "BrowserRuntimeMixin",
    "ExecutionPolicyMixin",
    "ContextCompactionMixin",
    "ToolCallMixin",
    "RuntimeServicesMixin",
    "BackgroundRuntimeMixin",
    "ExtensionsMixin",
    "ModelContextMixin",
    "MessagingMixin",
    "AutomationMixin",
    "ToolDispatchMixin",
    "SystemToolsMixin",
    "WebContentMixin",
    "EmailToolsMixin",
    "ProductivityToolsMixin",
    "SpeechMixin",
]
