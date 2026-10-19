"""Official local subscription transports; Smarti Core exclusively owns tools."""
from .base import SubscriptionError, SubscriptionProvider, model_efforts

CLAUDE = "anthropic_claude_code_signin"
ANTIGRAVITY = "google_antigravity_signin"
PROVIDERS = (CLAUDE, ANTIGRAVITY)


def get_provider(core, name):
    from .claude import ClaudeProvider
    from .antigravity import AntigravityProvider
    if name not in PROVIDERS:
        raise ValueError("unknown_subscription_provider")
    frozen = getattr(core, "_subscription_provider", None)
    if frozen is not None and frozen.provider == name:
        return frozen
    strategy = core.settings.get("claude_code_auth_strategy", "claude_login") if name == CLAUDE else "google_login"
    if strategy not in {"claude_login", "setup_token_env", "google_login"}:
        raise SubscriptionError("שיטת ההתחברות אינה נתמכת.", reason="wrong_auth_mode")
    providers = getattr(core, "_subscription_providers", None)
    if providers is None:
        core._subscription_providers = providers = {}
    key = (name, strategy)
    if key not in providers:
        from ..common import USER_DATA_DIR
        providers[key] = (ClaudeProvider if name == CLAUDE else AntigravityProvider)(USER_DATA_DIR, strategy)
    if core.settings.get("subscription_provider_connections", {}).get(name) is False:
        providers[key].disconnected = True
    return providers[key]
