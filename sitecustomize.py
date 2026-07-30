"""Load Smarti's selected TLS behavior as early as possible."""

try:
    from smarti.ssl_compat import configure_ssl_from_environment

    configure_ssl_from_environment()
except Exception:
    # Startup must remain available even if an optional trust backend is absent.
    pass
