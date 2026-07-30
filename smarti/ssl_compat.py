"""TLS trust for Windows, filtered networks, and child runtimes.

The preferred modes keep server identity verification enabled through either
the native Windows certificate store or an explicitly imported public filter
CA.  A clearly labelled compatibility mode intentionally restores Smarti's
historical process-wide verification bypass when the verified modes cannot
work on a filtered network.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import ssl
import tempfile
from urllib.parse import urlparse


SSL_MODE_SYSTEM = "system"
SSL_MODE_CUSTOM_CA = "custom_ca"
SSL_MODE_LEGACY_INSECURE = "legacy_insecure"
SSL_TRUST_MODES = frozenset({
    SSL_MODE_SYSTEM,
    SSL_MODE_CUSTOM_CA,
    SSL_MODE_LEGACY_INSECURE,
})
SSL_TRUST_MIGRATION_VERSION = 1

_SERVER_AUTH_OID = "1.3.6.1.5.5.7.3.1"
_PEM_CERT_RE = re.compile(
    rb"-----BEGIN CERTIFICATE-----\s+.+?\s+-----END CERTIFICATE-----",
    re.DOTALL,
)
_BUNDLE_CACHE = {}
_SYSTEM_PEM_CACHE = None
_TRUSTSTORE_INJECTED = False
_COMPAT_HOOKS_INSTALLED = False
_ORIGINAL_DEFAULT_HTTPS_CONTEXT = getattr(
    ssl,
    "_create_default_https_context",
    ssl.create_default_context,
)
_ORIGINAL_CREATE_DEFAULT_CONTEXT = ssl.create_default_context

INSECURE_SSL_ENV_KEYS = frozenset({
    "PYTHONHTTPSVERIFY",
    "NODE_TLS_REJECT_UNAUTHORIZED",
    "GIT_SSL_NO_VERIFY",
    "PIP_TRUSTED_HOST",
    "UV_INSECURE_HOST",
    "npm_config_strict_ssl",
    "NPM_CONFIG_STRICT_SSL",
    "YARN_ENABLE_STRICT_SSL",
    "PNPM_CONFIG_STRICT_SSL",
    "CURL_SSL_NO_REVOKE",
})

MANAGED_CA_ENV_KEYS = frozenset({
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "npm_config_cafile",
    "NPM_CONFIG_CAFILE",
    "YARN_CA_FILE",
    "PNPM_CONFIG_CAFILE",
    "GIT_SSL_CAINFO",
    "PIP_CERT",
    "CURL_CA_BUNDLE",
})


class SSLTrustConfigurationError(RuntimeError):
    """Raised when an explicitly selected trust configuration is unusable."""


@dataclass(frozen=True)
class ResolvedSSLTrust:
    mode: str
    ca_bundle_path: str
    custom_ca_path: str
    legacy_allowed_hosts: tuple[str, ...]
    legacy_session_enabled: bool
    verified: bool = True


def normalize_ssl_trust_mode(value):
    mode = str(value or SSL_MODE_SYSTEM).strip().lower()
    return mode if mode in SSL_TRUST_MODES else SSL_MODE_SYSTEM


def normalize_legacy_hosts(value):
    if isinstance(value, str):
        items = re.split(r"[\s,;]+", value)
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = []
    normalized = []
    seen = set()
    for item in items:
        raw = str(item or "").strip().lower().rstrip(".")
        if not raw:
            continue
        if "://" in raw:
            raw = (urlparse(raw).hostname or "").lower().rstrip(".")
        else:
            raw = raw.split("/", 1)[0]
            if raw.startswith("[") and "]" in raw:
                raw = raw[1:raw.index("]")]
            elif raw.count(":") == 1:
                raw = raw.split(":", 1)[0]
        wildcard = raw.startswith("*.")
        candidate = raw[2:] if wildcard else raw
        if (
            not candidate
            or len(candidate) > 253
            or candidate in {"*", "."}
            or not re.fullmatch(r"[a-z0-9._:-]+", candidate)
        ):
            continue
        host = f"*.{candidate}" if wildcard else candidate
        if host not in seen:
            seen.add(host)
            normalized.append(host)
    return normalized


def _url_hostname(url_or_host):
    raw = str(url_or_host or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return str(parsed.hostname or "").lower().rstrip(".")


def host_matches_legacy(host, allowed_hosts):
    hostname = _url_hostname(host)
    if not hostname:
        return False
    for pattern in normalize_legacy_hosts(allowed_hosts):
        if pattern.startswith("*."):
            suffix = pattern[1:]
            if hostname.endswith(suffix) and hostname != pattern[2:]:
                return True
        elif hostname == pattern:
            return True
    return False


def legacy_insecure_for_url(settings, url_or_host=""):
    """Return whether the explicit global compatibility mode is active.

    ``url_or_host`` is retained for call-site compatibility.  The user-facing
    mode deliberately mirrors Smarti's former global SSL-off behavior, so it
    is not host- or session-scoped.
    """
    settings = settings if isinstance(settings, dict) else {}
    return normalize_ssl_trust_mode(
        settings.get("ssl_trust_mode")
    ) == SSL_MODE_LEGACY_INSECURE


def _certificate_blocks(pem_bytes):
    blocks = []
    seen = set()
    for match in _PEM_CERT_RE.findall(pem_bytes or b""):
        block = b"\n".join(line.strip() for line in match.splitlines() if line.strip()) + b"\n"
        digest = hashlib.sha256(block).digest()
        if digest not in seen:
            seen.add(digest)
            blocks.append(block)
    return blocks


def _pem_from_certificate_file(path):
    path = os.path.abspath(os.path.expandvars(os.path.expanduser(str(path or ""))))
    if not path or not os.path.isfile(path):
        raise SSLTrustConfigurationError("קובץ תעודת הסינון לא נמצא.")
    try:
        raw = Path(path).read_bytes()
    except Exception as exc:
        raise SSLTrustConfigurationError(f"לא ניתן לקרוא את קובץ התעודה: {exc}") from exc
    if not raw:
        raise SSLTrustConfigurationError("קובץ תעודת הסינון ריק.")
    if b"PRIVATE KEY" in raw.upper():
        raise SSLTrustConfigurationError("יש לבחור תעודת CA ציבורית בלבד, ללא מפתח פרטי.")
    blocks = _certificate_blocks(raw)
    if not blocks:
        try:
            pem = ssl.DER_cert_to_PEM_cert(raw).encode("ascii")
            blocks = _certificate_blocks(pem)
        except Exception as exc:
            raise SSLTrustConfigurationError(
                "הקובץ אינו מכיל תעודת X.509 תקינה בפורמט PEM או DER."
            ) from exc
    blocks = _validate_ca_certificates(blocks)
    pem = b"".join(blocks)
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=pem.decode("ascii"))
    except Exception as exc:
        raise SSLTrustConfigurationError(f"תעודת ה-CA אינה ניתנת לטעינה: {exc}") from exc
    return pem


def _validate_ca_certificates(blocks):
    """Return usable CA blocks while rejecting unsafe certificate content.

    Provider bundles can legitimately retain expired historical roots beside
    their current root. Those obsolete roots are omitted when at least one
    valid CA remains; a leaf/non-CA certificate or a bundle with no currently
    valid CA is still rejected.
    """
    try:
        from cryptography import x509
    except Exception as exc:
        raise SSLTrustConfigurationError(
            "לא ניתן לאמת שקובץ התעודה הוא CA תקין. רכיב cryptography אינו זמין."
        ) from exc

    now = datetime.now(timezone.utc)
    valid_blocks = []
    validity_errors = []
    for index, block in enumerate(blocks, start=1):
        try:
            certificate = x509.load_pem_x509_certificate(block)
            constraints = certificate.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value
        except x509.ExtensionNotFound as exc:
            raise SSLTrustConfigurationError(
                f"תעודה {index} אינה מצהירה שהיא תעודת CA."
            ) from exc
        except Exception as exc:
            raise SSLTrustConfigurationError(
                f"תעודה {index} אינה תעודת X.509 תקינה: {exc}"
            ) from exc
        if not constraints.ca:
            raise SSLTrustConfigurationError(
                f"תעודה {index} היא תעודת שרת או משתמש, ולא תעודת CA."
            )
        try:
            key_usage = certificate.extensions.get_extension_for_class(
                x509.KeyUsage
            ).value
            if not key_usage.key_cert_sign:
                raise SSLTrustConfigurationError(
                    f"תעודה {index} אינה מורשית לחתום על תעודות אחרות."
                )
        except x509.ExtensionNotFound:
            pass

        not_before = getattr(certificate, "not_valid_before_utc", None)
        if not_before is None:
            not_before = certificate.not_valid_before.replace(tzinfo=timezone.utc)
        not_after = getattr(certificate, "not_valid_after_utc", None)
        if not_after is None:
            not_after = certificate.not_valid_after.replace(tzinfo=timezone.utc)
        if now < not_before:
            validity_errors.append(f"תעודה {index} עדיין אינה בתוקף.")
            continue
        if now > not_after:
            validity_errors.append(f"תעודה {index} פגה ואינה בטוחה לשימוש.")
            continue
        valid_blocks.append(block)

    if not valid_blocks:
        raise SSLTrustConfigurationError(
            validity_errors[0]
            if validity_errors
            else "הקובץ אינו מכיל תעודת CA ציבורית ותקפה."
        )
    return valid_blocks


def validate_custom_ca(path):
    try:
        pem = _pem_from_certificate_file(path)
        return True, f"נטענו {len(_certificate_blocks(pem))} תעודות CA תקינות."
    except Exception as exc:
        return False, str(exc)


def describe_custom_ca(path):
    """Return lightweight display metadata for an already imported PEM CA."""
    expanded = os.path.abspath(os.path.expandvars(os.path.expanduser(str(path or ""))))
    result = {
        "path": expanded,
        "filename": os.path.basename(expanded) if expanded else "",
        "name": "",
        "issuer": "",
        "expires": "",
        "fingerprint": "",
    }
    if not expanded or not os.path.isfile(expanded):
        return result
    try:
        decoded = ssl._ssl._test_decode_cert(expanded)

        def flattened_name(field):
            values = {}
            for group in decoded.get(field, ()):
                for key, value in group:
                    values[str(key)] = str(value)
            return (
                values.get("commonName")
                or values.get("organizationName")
                or values.get("organizationalUnitName")
                or ""
            )

        result["name"] = flattened_name("subject")
        result["issuer"] = flattened_name("issuer")
        result["expires"] = str(decoded.get("notAfter") or "")
        pem = Path(expanded).read_bytes()
        blocks = _certificate_blocks(pem)
        if blocks:
            der = ssl.PEM_cert_to_DER_cert(blocks[0].decode("ascii"))
            result["fingerprint"] = hashlib.sha256(der).hexdigest().upper()
    except Exception:
        pass
    return result


def import_custom_ca(source_path, data_dir):
    """Validate and copy a public filter CA into Smarti's managed data folder."""
    pem = _pem_from_certificate_file(source_path)
    ssl_dir = os.path.join(os.path.abspath(str(data_dir)), "ssl")
    os.makedirs(ssl_dir, exist_ok=True)
    target = os.path.join(ssl_dir, "custom-filter-ca.pem")
    _atomic_write(target, pem)
    return target


def _windows_store_pem():
    if os.name != "nt" or not hasattr(ssl, "enum_certificates"):
        return b""
    blocks = []
    for store_name in ("ROOT", "CA"):
        try:
            certificates = ssl.enum_certificates(store_name)
        except Exception:
            continue
        for cert_bytes, encoding, trust in certificates:
            if trust is not True and isinstance(trust, set) and _SERVER_AUTH_OID not in trust:
                continue
            try:
                if encoding == "x509_asn":
                    pem = ssl.DER_cert_to_PEM_cert(cert_bytes).encode("ascii")
                elif encoding == "pkcs_7_asn":
                    continue
                else:
                    continue
                blocks.extend(_certificate_blocks(pem))
            except Exception:
                continue
    return b"".join(_dedupe_blocks(blocks))


def _fallback_bundle_pem():
    try:
        import certifi

        return Path(certifi.where()).read_bytes()
    except Exception:
        paths = ssl.get_default_verify_paths()
        for candidate in (paths.cafile, paths.openssl_cafile):
            if candidate and os.path.isfile(candidate):
                try:
                    return Path(candidate).read_bytes()
                except Exception:
                    pass
    return b""


def _system_bundle_pem():
    global _SYSTEM_PEM_CACHE
    if _SYSTEM_PEM_CACHE is None:
        windows_pem = _windows_store_pem()
        fallback_pem = _fallback_bundle_pem()
        _SYSTEM_PEM_CACHE = b"".join(
            _dedupe_blocks(_certificate_blocks(windows_pem) + _certificate_blocks(fallback_pem))
        )
    return _SYSTEM_PEM_CACHE


def _dedupe_blocks(blocks):
    result = []
    seen = set()
    for block in blocks:
        digest = hashlib.sha256(block).digest()
        if digest not in seen:
            seen.add(digest)
            result.append(block)
    return result


def _atomic_write(path, data):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".smarti-ca-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def _settings_data_dir(settings, data_dir=None):
    if data_dir:
        return os.path.abspath(str(data_dir))
    if isinstance(settings, dict) and settings.get("_ssl_data_dir"):
        return os.path.abspath(str(settings["_ssl_data_dir"]))
    env_dir = os.environ.get("SMARTI_DATA_DIR", "").strip()
    if env_dir:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(env_dir)))
    return os.path.join(os.path.expanduser("~"), ".smarti")


def resolve_ca_bundle(settings=None, data_dir=None, force=False):
    settings = settings if isinstance(settings, dict) else {}
    mode = normalize_ssl_trust_mode(settings.get("ssl_trust_mode"))
    custom_path = str(settings.get("ssl_custom_ca_path") or "").strip()
    if mode == SSL_MODE_CUSTOM_CA and not custom_path:
        raise SSLTrustConfigurationError("מצב תעודת סינון נבחר, אך לא נבחר קובץ CA.")
    custom_stamp = ()
    if mode == SSL_MODE_CUSTOM_CA:
        expanded = os.path.abspath(os.path.expandvars(os.path.expanduser(custom_path)))
        try:
            stat = os.stat(expanded)
            custom_stamp = (expanded, stat.st_mtime_ns, stat.st_size)
        except OSError:
            custom_stamp = (expanded, None, None)
    target_dir = _settings_data_dir(settings, data_dir)
    cache_key = (target_dir, mode, custom_stamp)
    cached = _BUNDLE_CACHE.get(cache_key)
    if not force and cached and os.path.isfile(cached):
        return cached

    blocks = _certificate_blocks(_system_bundle_pem())
    if mode == SSL_MODE_CUSTOM_CA:
        blocks.extend(_certificate_blocks(_pem_from_certificate_file(custom_path)))
    bundle = b"".join(_dedupe_blocks(blocks))
    if not bundle:
        if mode == SSL_MODE_CUSTOM_CA:
            raise SSLTrustConfigurationError("לא ניתן לבנות מאגר CA מאומת.")
        return ""
    target = os.path.join(target_dir, "ssl", "smarti-trusted-ca-bundle.pem")
    _atomic_write(target, bundle)
    _BUNDLE_CACHE[cache_key] = target
    return target


def resolve_ssl_trust(settings=None, data_dir=None):
    settings = settings if isinstance(settings, dict) else {}
    mode = normalize_ssl_trust_mode(settings.get("ssl_trust_mode"))
    if mode == SSL_MODE_LEGACY_INSECURE:
        return ResolvedSSLTrust(
            mode=mode,
            ca_bundle_path="",
            custom_ca_path=str(settings.get("ssl_custom_ca_path") or "").strip(),
            legacy_allowed_hosts=(),
            legacy_session_enabled=True,
            verified=False,
        )
    return ResolvedSSLTrust(
        mode=mode,
        ca_bundle_path=resolve_ca_bundle(settings, data_dir=data_dir),
        custom_ca_path=str(settings.get("ssl_custom_ca_path") or "").strip(),
        legacy_allowed_hosts=tuple(normalize_legacy_hosts(
            settings.get("ssl_legacy_insecure_allowed_hosts", [])
        )),
        legacy_session_enabled=bool(
            settings.get("_ssl_legacy_insecure_session_enabled", False)
        ),
        verified=True,
    )


def _system_ssl_context():
    if os.name == "nt":
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            pass
    return ssl.create_default_context()


def create_ssl_context(settings=None, *, url="", data_dir=None, allow_legacy=True):
    settings = settings if isinstance(settings, dict) else {}
    if allow_legacy and legacy_insecure_for_url(settings, url):
        return ssl._create_unverified_context()
    mode = normalize_ssl_trust_mode(settings.get("ssl_trust_mode"))
    if mode == SSL_MODE_CUSTOM_CA:
        bundle = resolve_ca_bundle(settings, data_dir=data_dir)
        context = _system_ssl_context()
        context.load_verify_locations(cafile=bundle)
        return context
    return _system_ssl_context()


def ssl_request_kwargs(settings=None, *, url="", data_dir=None, allow_legacy=True):
    settings = settings if isinstance(settings, dict) else {}
    if allow_legacy and legacy_insecure_for_url(settings, url):
        return {"verify": False}
    mode = normalize_ssl_trust_mode(settings.get("ssl_trust_mode"))
    if mode == SSL_MODE_CUSTOM_CA:
        bundle = resolve_ca_bundle(settings, data_dir=data_dir)
        return {"verify": bundle}
    # ``True`` is important here: after truststore.inject_into_ssl(), Requests
    # delegates validation to Windows. Passing an exported PEM bundle instead
    # forces OpenSSL validation and can break valid intercepted chains used by
    # filtering providers such as NetFree, Rimon, and similar services.
    return {"verify": True}


def apply_ssl_trust_environment(settings=None, env=None, data_dir=None):
    """Mutate and return an environment matching the selected trust mode."""
    settings = settings if isinstance(settings, dict) else {}
    target = os.environ if env is None else env
    for key in INSECURE_SSL_ENV_KEYS:
        target.pop(key, None)
    mode = normalize_ssl_trust_mode(settings.get("ssl_trust_mode"))
    target["SMARTI_SSL_TRUST_MODE"] = mode
    target["SMARTI_SSL_LEGACY_ALLOWED_HOSTS"] = "[]"

    if mode == SSL_MODE_LEGACY_INSECURE:
        for key in MANAGED_CA_ENV_KEYS:
            target.pop(key, None)
        target.pop("SMARTI_SSL_CA_BUNDLE", None)
        target["SMARTI_ALLOW_INSECURE_SSL"] = "1"
        target["PYTHONHTTPSVERIFY"] = "0"
        target["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
        target["GIT_SSL_NO_VERIFY"] = "true"
        target["PIP_TRUSTED_HOST"] = "pypi.org files.pythonhosted.org pypi.python.org"
        target["UV_INSECURE_HOST"] = "https://pypi.org https://files.pythonhosted.org"
        target["npm_config_strict_ssl"] = "false"
        target["NPM_CONFIG_STRICT_SSL"] = "false"
        target["YARN_ENABLE_STRICT_SSL"] = "false"
        target["PNPM_CONFIG_STRICT_SSL"] = "false"
        target["CURL_SSL_NO_REVOKE"] = "1"
        target.pop("UV_SYSTEM_CERTS", None)
        target.pop("UV_NATIVE_TLS", None)
        return target

    target["SMARTI_ALLOW_INSECURE_SSL"] = "0"
    bundle = resolve_ca_bundle(settings, data_dir=data_dir)
    if bundle:
        for key in MANAGED_CA_ENV_KEYS:
            target[key] = bundle
        target["SMARTI_SSL_CA_BUNDLE"] = bundle
    else:
        for key in MANAGED_CA_ENV_KEYS:
            target.pop(key, None)
        target.pop("SMARTI_SSL_CA_BUNDLE", None)
    target["UV_SYSTEM_CERTS"] = "true"
    target["UV_NATIVE_TLS"] = "true"
    target["npm_config_strict_ssl"] = "true"
    target["NPM_CONFIG_STRICT_SSL"] = "true"
    target["YARN_ENABLE_STRICT_SSL"] = "true"
    target["PNPM_CONFIG_STRICT_SSL"] = "true"
    return target


def _compat_enabled():
    return os.environ.get("SMARTI_ALLOW_INSECURE_SSL") == "1"


def _dynamic_default_https_context(*args, **kwargs):
    if _compat_enabled():
        return ssl._create_unverified_context(*args, **kwargs)
    return _ORIGINAL_DEFAULT_HTTPS_CONTEXT(*args, **kwargs)


def _dynamic_create_default_context(*args, **kwargs):
    if _compat_enabled():
        return ssl._create_unverified_context(*args, **kwargs)
    return _ORIGINAL_CREATE_DEFAULT_CONTEXT(*args, **kwargs)


def _install_dynamic_compat_hooks():
    """Install reversible hooks whose behavior follows the current env flag."""
    global _COMPAT_HOOKS_INSTALLED
    if _COMPAT_HOOKS_INSTALLED:
        return

    ssl._create_default_https_context = _dynamic_default_https_context
    ssl.create_default_context = _dynamic_create_default_context

    try:
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        if not getattr(requests.Session, "_smarti_ssl_compat_patched", False):
            requests_original_request = requests.Session.request
            requests_original_merge = requests.Session.merge_environment_settings

            def request(session, method, url, **kwargs):
                if _compat_enabled():
                    kwargs["verify"] = False
                return requests_original_request(session, method, url, **kwargs)

            def merge_environment_settings(session, url, proxies, stream, verify, cert):
                merged = requests_original_merge(session, url, proxies, stream, verify, cert)
                if _compat_enabled():
                    merged["verify"] = False
                return merged

            requests.Session.request = request
            requests.Session.merge_environment_settings = merge_environment_settings
            requests.Session._smarti_ssl_compat_patched = True
    except Exception:
        pass

    try:
        import httpx

        if not getattr(httpx, "_smarti_ssl_compat_patched", False):
            httpx_original_request = httpx.request
            httpx_original_client_init = httpx.Client.__init__
            httpx_original_async_client_init = httpx.AsyncClient.__init__

            def httpx_request(method, url, **kwargs):
                if _compat_enabled():
                    kwargs["verify"] = False
                return httpx_original_request(method, url, **kwargs)

            def client_init(client, *args, **kwargs):
                if _compat_enabled():
                    kwargs["verify"] = False
                return httpx_original_client_init(client, *args, **kwargs)

            def async_client_init(client, *args, **kwargs):
                if _compat_enabled():
                    kwargs["verify"] = False
                return httpx_original_async_client_init(client, *args, **kwargs)

            httpx.request = httpx_request
            httpx.Client.__init__ = client_init
            httpx.AsyncClient.__init__ = async_client_init
            httpx._smarti_ssl_compat_patched = True
    except Exception:
        pass

    try:
        import aiohttp

        connector = getattr(aiohttp, "TCPConnector", None)
        if connector and not getattr(connector, "_smarti_ssl_compat_patched", False):
            original_connector_init = connector.__init__

            def connector_init(instance, *args, **kwargs):
                if _compat_enabled() and "ssl" not in kwargs:
                    kwargs["ssl"] = False
                return original_connector_init(instance, *args, **kwargs)

            connector.__init__ = connector_init
            connector._smarti_ssl_compat_patched = True
    except Exception:
        pass

    _COMPAT_HOOKS_INSTALLED = True


def configure_ssl_from_environment():
    """Install native Windows trust plus the dynamic compatibility hooks."""
    global _TRUSTSTORE_INJECTED
    _install_dynamic_compat_hooks()
    if not _TRUSTSTORE_INJECTED:
        try:
            import truststore

            truststore.inject_into_ssl()
            _TRUSTSTORE_INJECTED = True
        except Exception:
            pass
    return _TRUSTSTORE_INJECTED


def test_https_trust(settings=None, url="https://www.gstatic.com/generate_204", timeout=12):
    """Perform a harmless HTTPS GET and report whether identity was verified."""
    settings = settings if isinstance(settings, dict) else {}
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("כתובת הבדיקה חייבת להיות כתובת HTTPS ללא פרטי התחברות.")
    mode = normalize_ssl_trust_mode(settings.get("ssl_trust_mode"))
    context = create_ssl_context(settings, url=url)
    import urllib3

    if mode == SSL_MODE_LEGACY_INSECURE:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    pool = urllib3.PoolManager(ssl_context=context)
    response = pool.request(
        "GET",
        url,
        timeout=urllib3.Timeout(total=max(3, min(int(timeout), 30))),
        redirect=True,
        retries=False,
        headers={"User-Agent": "SmartiAI TLS trust test"},
    )
    try:
        if int(response.status) >= 400:
            raise RuntimeError(f"שרת הבדיקה החזיר HTTP {int(response.status)}.")
        verified = mode != SSL_MODE_LEGACY_INSECURE
        bundle = (
            resolve_ca_bundle(settings)
            if mode == SSL_MODE_CUSTOM_CA
            else ""
        )
    finally:
        response.release_conn()
    return {
        "ok": True,
        "verified": verified,
        "status_code": int(response.status),
        "host": str(parsed.hostname),
        "mode": mode,
        "ca_bundle_path": str(bundle),
    }


def apply_insecure_ssl_compat():
    """Install the dynamic hooks and report whether compatibility is active."""
    configure_ssl_from_environment()
    return _compat_enabled()


__all__ = [
    "INSECURE_SSL_ENV_KEYS",
    "MANAGED_CA_ENV_KEYS",
    "ResolvedSSLTrust",
    "SSL_MODE_CUSTOM_CA",
    "SSL_MODE_LEGACY_INSECURE",
    "SSL_MODE_SYSTEM",
    "SSL_TRUST_MIGRATION_VERSION",
    "SSL_TRUST_MODES",
    "SSLTrustConfigurationError",
    "apply_insecure_ssl_compat",
    "apply_ssl_trust_environment",
    "configure_ssl_from_environment",
    "create_ssl_context",
    "describe_custom_ca",
    "host_matches_legacy",
    "import_custom_ca",
    "legacy_insecure_for_url",
    "normalize_legacy_hosts",
    "normalize_ssl_trust_mode",
    "resolve_ca_bundle",
    "resolve_ssl_trust",
    "ssl_request_kwargs",
    "test_https_trust",
    "validate_custom_ca",
]
