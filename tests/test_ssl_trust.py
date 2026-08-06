"""Contract tests for Smarti's filtered-network TLS trust controls."""
import copy
import datetime
import http.server
import inspect
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PyQt6.QtWidgets import QApplication, QLabel

from smarti.agent.model_context import ModelContextMixin
from smarti.agent.runtime_services import RuntimeServicesMixin
from smarti.agent.system_tools import SystemToolsMixin
from smarti.config import DEFAULT_SETTINGS
from smarti.managers import SettingsManager
from smarti.ssl_compat import (
    INSECURE_SSL_ENV_KEYS,
    SSL_MODE_CUSTOM_CA,
    SSL_MODE_LEGACY_INSECURE,
    SSL_MODE_SYSTEM,
    apply_ssl_trust_environment,
    host_matches_legacy,
    import_custom_ca,
    ssl_request_kwargs,
    test_https_trust as run_https_trust_test,
    validate_custom_ca,
)
from smarti.ui_pages import SSLTrustSettingsCard
from smarti import updater
from smarti.common import APP_VERSION


class _QuietHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, _format, *_args):
        return


class _QuietHTTPServer(http.server.ThreadingHTTPServer):
    def handle_error(self, _request, _client_address):
        return


def _new_ca(common_name, *, expired=False):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=60 if expired else 1))
        .not_valid_after(now - datetime.timedelta(days=30) if expired else now + datetime.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _new_server_certificate(ca_key, ca_cert):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=7))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


class SSLTrustMigrationTests(unittest.TestCase):
    def test_legacy_global_default_migrates_to_verified_system_store(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = SettingsManager(os.path.join(temp, "settings.json"), DEFAULT_SETTINGS)
            migrated, changed = manager.migrate_or_merge({
                "settings_schema_version": 2,
                "allow_insecure_ssl_compat": True,
            })

        self.assertTrue(changed)
        self.assertEqual(migrated["ssl_trust_mode"], SSL_MODE_SYSTEM)
        self.assertFalse(migrated["allow_insecure_ssl_compat"])
        self.assertTrue(migrated["ssl_migrated_from_global_insecure"])
        self.assertEqual(migrated["ssl_legacy_insecure_allowed_hosts"], [])

    def test_explicit_new_trust_settings_round_trip_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = SettingsManager(os.path.join(temp, "settings.json"), DEFAULT_SETTINGS)
            loaded = copy.deepcopy(DEFAULT_SETTINGS)
            loaded.update({
                "settings_schema_version": 2,
                "ssl_trust_mode": SSL_MODE_CUSTOM_CA,
                "ssl_custom_ca_path": os.path.join(temp, "filter.pem"),
                "ssl_legacy_insecure_allowed_hosts": ["api.example.com"],
            })
            migrated, changed = manager.migrate_or_merge(loaded)

        self.assertFalse(changed)
        self.assertEqual(migrated["ssl_trust_mode"], SSL_MODE_CUSTOM_CA)
        self.assertEqual(migrated["ssl_custom_ca_path"], loaded["ssl_custom_ca_path"])


class SSLTrustCompatibilityModeTests(unittest.TestCase):
    def test_explicit_legacy_mode_is_global_and_not_session_scoped(self):
        settings = {
            "ssl_trust_mode": SSL_MODE_LEGACY_INSECURE,
            "ssl_legacy_insecure_allowed_hosts": ["api.example.com"],
            "_ssl_legacy_insecure_session_enabled": False,
        }
        self.assertIs(
            ssl_request_kwargs(settings, url="https://api.example.com/v1")["verify"],
            False,
        )
        self.assertIs(
            ssl_request_kwargs(settings, url="https://other.example.com/v1").get("verify"),
            False,
        )

    def test_deprecated_host_matcher_remains_deterministic_for_migration_tools(self):
        self.assertTrue(host_matches_legacy("one.filter.example", ["*.filter.example"]))
        self.assertFalse(host_matches_legacy("filter.example", ["*.filter.example"]))
        self.assertFalse(host_matches_legacy("evilfilter.example", ["*.filter.example"]))


class SSLTrustCertificateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        ca_key, ca_cert = _new_ca("Smarti Test Filter CA")
        wrong_key, wrong_cert = _new_ca("Wrong Smarti Test CA")
        _, expired_cert = _new_ca("Expired Smarti Test CA", expired=True)
        server_key, server_cert = _new_server_certificate(ca_key, ca_cert)
        self.ca_path = root / "filter-ca.pem"
        self.wrong_ca_path = root / "wrong-ca.pem"
        self.cert_path = root / "server.pem"
        self.key_path = root / "server-key.pem"
        self.mixed_bundle_path = root / "mixed-filter-bundle.pem"
        self.expired_ca_path = root / "expired-filter-ca.pem"
        self.ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
        self.wrong_ca_path.write_bytes(wrong_cert.public_bytes(serialization.Encoding.PEM))
        self.cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
        self.mixed_bundle_path.write_bytes(
            expired_cert.public_bytes(serialization.Encoding.PEM)
            + ca_cert.public_bytes(serialization.Encoding.PEM)
        )
        self.expired_ca_path.write_bytes(
            expired_cert.public_bytes(serialization.Encoding.PEM)
        )
        self.key_path.write_bytes(
            server_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        self.server = _QuietHTTPServer(("127.0.0.1", 0), _QuietHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self.cert_path), str(self.key_path))
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"https://127.0.0.1:{self.server.server_port}/trust-test"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def _settings(self, ca_path):
        return {
            "ssl_trust_mode": SSL_MODE_CUSTOM_CA,
            "ssl_custom_ca_path": str(ca_path),
            "_ssl_data_dir": self.temp.name,
        }

    def test_verified_request_succeeds_with_selected_filter_ca(self):
        result = run_https_trust_test(self._settings(self.ca_path), self.url)
        self.assertTrue(result["ok"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["host"], "127.0.0.1")

    def test_wrong_ca_fails_without_silent_downgrade(self):
        with self.assertRaises(Exception):
            run_https_trust_test(self._settings(self.wrong_ca_path), self.url)

    def test_leaf_certificate_is_rejected_as_custom_ca(self):
        ok, message = validate_custom_ca(self.cert_path)
        self.assertFalse(ok)
        self.assertIn("CA", message)

    def test_provider_bundle_keeps_valid_ca_and_omits_expired_history(self):
        ok, message = validate_custom_ca(self.mixed_bundle_path)
        self.assertTrue(ok)
        self.assertIn("1", message)
        managed_path = import_custom_ca(self.mixed_bundle_path, self.temp.name)
        managed_blocks = Path(managed_path).read_text(encoding="ascii").count(
            "-----BEGIN CERTIFICATE-----"
        )
        self.assertEqual(managed_blocks, 1)

    def test_expired_only_provider_bundle_is_rejected(self):
        ok, message = validate_custom_ca(self.expired_ca_path)
        self.assertFalse(ok)
        self.assertIn("פגה", message)


class SSLTrustPropagationTests(unittest.TestCase):
    def test_child_environment_uses_ca_paths_and_no_disable_flags(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {
                "NODE_TLS_REJECT_UNAUTHORIZED": "0",
                "GIT_SSL_NO_VERIFY": "true",
                "PIP_TRUSTED_HOST": "pypi.org",
            }
            apply_ssl_trust_environment(
                {"ssl_trust_mode": SSL_MODE_SYSTEM, "_ssl_data_dir": temp},
                env,
                data_dir=temp,
            )

            for key in INSECURE_SSL_ENV_KEYS:
                self.assertNotEqual(str(env.get(key, "")).lower(), "0")
                self.assertNotEqual(str(env.get(key, "")).lower(), "false")
                self.assertNotEqual(str(env.get(key, "")).lower(), "true" if key == "GIT_SSL_NO_VERIFY" else "__never__")
            bundle = env["SSL_CERT_FILE"]
            self.assertTrue(os.path.isfile(bundle))
            self.assertEqual(env["REQUESTS_CA_BUNDLE"], bundle)
            self.assertEqual(env["NODE_EXTRA_CA_CERTS"], bundle)
            self.assertEqual(env["npm_config_cafile"], bundle)
            self.assertEqual(env["GIT_SSL_CAINFO"], bundle)
            self.assertEqual(env["PIP_CERT"], bundle)
            self.assertEqual(env["npm_config_strict_ssl"], "true")

    def test_global_compatibility_environment_restores_all_runtime_bypasses(self):
        env = {
            "REQUESTS_CA_BUNDLE": "old.pem",
            "SSL_CERT_FILE": "old.pem",
            "NODE_EXTRA_CA_CERTS": "old.pem",
        }
        apply_ssl_trust_environment(
            {"ssl_trust_mode": SSL_MODE_LEGACY_INSECURE},
            env,
        )

        self.assertEqual(env["SMARTI_ALLOW_INSECURE_SSL"], "1")
        self.assertEqual(env["PYTHONHTTPSVERIFY"], "0")
        self.assertEqual(env["NODE_TLS_REJECT_UNAUTHORIZED"], "0")
        self.assertEqual(env["GIT_SSL_NO_VERIFY"], "true")
        self.assertEqual(env["npm_config_strict_ssl"], "false")
        self.assertEqual(env["NPM_CONFIG_STRICT_SSL"], "false")
        self.assertEqual(env["YARN_ENABLE_STRICT_SSL"], "false")
        self.assertEqual(env["PNPM_CONFIG_STRICT_SSL"], "false")
        self.assertNotIn("REQUESTS_CA_BUNDLE", env)
        self.assertNotIn("SSL_CERT_FILE", env)
        self.assertNotIn("NODE_EXTRA_CA_CERTS", env)

    def test_mcp_environment_and_wrapper_keep_python_and_node_verified(self):
        class Core(RuntimeServicesMixin):
            def _sandbox_enabled(self):
                return False

        core = Core()
        core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        core._ssl_legacy_insecure_session_enabled = False
        env = core._mcp_env()
        bundle = env["SSL_CERT_FILE"]
        self.assertEqual(env["REQUESTS_CA_BUNDLE"], bundle)
        self.assertEqual(env["NODE_EXTRA_CA_CERTS"], bundle)
        self.assertEqual(env["npm_config_cafile"], bundle)
        self.assertNotIn("NODE_TLS_REJECT_UNAUTHORIZED", env)
        self.assertNotIn("GIT_SSL_NO_VERIFY", env)
        self.assertNotIn("PIP_TRUSTED_HOST", env)
        wrapper_source = inspect.getsource(SystemToolsMixin._write_mcp_wrapper)
        self.assertNotIn('env["NODE_TLS_REJECT_UNAUTHORIZED"]', wrapper_source)
        self.assertNotIn('env["PYTHONHTTPSVERIFY"]', wrapper_source)

    def test_updater_consumes_explicit_global_compatibility_mode(self):
        settings = {
            "ssl_trust_mode": SSL_MODE_LEGACY_INSECURE,
        }
        kwargs = updater._request_kwargs(settings, updater.GITHUB_API_RELEASE_LATEST)
        self.assertIs(kwargs.get("verify"), False)

    def test_openai_compatible_client_receives_verified_context(self):
        class Core(RuntimeServicesMixin, ModelContextMixin):
            pass

        core = Core()
        core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        core.settings.update({
            "api_mode": "openai",
            "openai_api_key": "test-key",
        })
        core.system_prompt = "system"
        core._ssl_legacy_insecure_session_enabled = False
        fake_openai = types.SimpleNamespace(OpenAI=mock.Mock(return_value=object()))
        with mock.patch.dict(sys.modules, {"openai": fake_openai}):
            with mock.patch("httpx.Client") as http_client:
                http_client.return_value = object()
                ModelContextMixin.setup_model(core)

        verify = http_client.call_args.kwargs["verify"]
        self.assertIsNot(verify, False)
        self.assertEqual(verify.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(verify.check_hostname)


class SSLTrustUiRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_settings_card_round_trips_global_mode_and_clears_obsolete_hosts(self):
        class Core:
            def __init__(self):
                self.settings = copy.deepcopy(DEFAULT_SETTINGS)
                self._ssl_legacy_insecure_session_enabled = False

            def _set_legacy_ssl_session_enabled(self, enabled):
                self._ssl_legacy_insecure_session_enabled = bool(enabled)

        core = Core()
        card = SSLTrustSettingsCard(core)
        card.apply_values({
            "ssl_trust_mode": SSL_MODE_LEGACY_INSECURE,
            "ssl_custom_ca_path": "",
            "ssl_filter_setup_completed": False,
            "ssl_legacy_insecure_allowed_hosts": "api.example.com, api.example.com",
        }, legacy_session_enabled=True, emit=False)
        values = card.settings_values()

        self.assertEqual(values["ssl_trust_mode"], SSL_MODE_LEGACY_INSECURE)
        self.assertEqual(values["ssl_legacy_insecure_allowed_hosts"], [])
        self.assertTrue(values["allow_insecure_ssl_compat"])
        self.assertTrue(card.ssl_snapshot()["_ssl_legacy_insecure_session_enabled"])
        self.assertFalse(card.is_expanded())
        self.assertEqual(card.configure_btn.text(), "הגדר")
        self.assertEqual(card.cancel_btn.text(), "ביטול")
        self.assertEqual(card.cancel_btn.height(), card.save_btn.height())
        self.assertEqual(card.cancel_btn.size(), card.save_btn.size())
        self.assertIn("border-radius: 24px", card.cancel_btn.styleSheet())
        self.assertIn("border-radius: 24px", card.save_btn.styleSheet())
        self.assertEqual(
            card.test_status.property("smartiSSLTestStatusTone"),
            "muted",
        )
        self.assertIn("color:", card.test_status.styleSheet())
        self.assertTrue(card.compat_ack.wordWrap())
        self.assertGreater(card.compat_ack.heightForWidth(260), 38)
        labels = " ".join(label.text() for label in card.findChildren(QLabel))
        self.assertIn("נטפרי, רימון וכדומה", labels)
        paragraph_labels = [
            card.findChild(QLabel, "SSLTrustEditorHelp"),
            *[
                label
                for label in card.findChildren(QLabel)
                if label.property("smartiSSLModeBody")
            ],
        ]
        for label in paragraph_labels:
            self.assertRegex(label.text().strip(), r"^[\u0590-\u05FF]")
        card.open_setup()
        self.assertTrue(card.is_expanded())
        self.assertEqual(card.configure_btn.text(), "ביטול")
        card._cancel_editor()
        self.assertFalse(card.is_expanded())
        self.assertEqual(card.configure_btn.text(), "הגדר")
        self.assertNotIn("isRunning", inspect.getsource(card._run_test))
        card.deleteLater()


class ReleaseReadinessTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    RELEASE_VERSION = "0.87.0"

    def test_source_build_docs_and_installer_are_version_synchronized(self):
        self.assertEqual(APP_VERSION, f"V{self.RELEASE_VERSION}")
        build_script = (self.ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8-sig")
        installer = (self.ROOT / "packaging" / "smarti.iss").read_text(encoding="utf-8-sig")
        readme = (self.ROOT / "README.md").read_text(encoding="utf-8-sig")
        packaging_readme = (self.ROOT / "packaging" / "README.md").read_text(encoding="utf-8-sig")
        self.assertIn("Assert-AppVersionMatchesRelease", build_script)
        self.assertIn("/DMyAppVersion=$ReleaseVersion", build_script)
        self.assertIn("AppVersion={#MyAppVersion}", installer)
        self.assertIn(f"-Version {self.RELEASE_VERSION}", readme)
        self.assertIn(f"-Version {self.RELEASE_VERSION}", packaging_readme)
        runtime_script = (self.ROOT / "scripts" / "prepare_runtime.ps1").read_text(encoding="utf-8-sig")
        for variable in ("SMARTI_PYTHON_SHA256", "SMARTI_NODE_SHA256", "SMARTI_GET_PIP_SHA256"):
            self.assertIn(variable, runtime_script)

    def test_private_runtime_downloads_are_pinned_to_sha256(self):
        config = json.loads((self.ROOT / "packaging" / "runtime-versions.json").read_text(encoding="utf-8-sig"))
        for name in ("python", "node", "getPip"):
            self.assertRegex(str(config[name].get("sha256") or ""), r"^[0-9a-f]{64}$", name)

    def test_updater_and_inno_installer_share_the_same_stable_app_id(self):
        installer = (self.ROOT / "packaging" / "smarti.iss").read_text(encoding="utf-8-sig")
        match = re.search(r"^AppId=\{\{([0-9A-F-]+)\}", installer, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertIn(match.group(1), updater.INNO_UNINSTALL_KEY)

    def test_version_comparison_handles_v_prefix_and_current_release(self):
        self.assertFalse(updater.is_newer_version("V0.87.0", "V0.87.0"))
        self.assertTrue(updater.is_newer_version("0.87.1", "V0.87.0"))
        self.assertFalse(updater.is_newer_version("0.86.9", "V0.87.0"))

    def test_release_assets_match_installer_and_portable_build_names(self):
        release = {"assets": [
            {"name": f"SmartiAI-Agent-for-Windows-{self.RELEASE_VERSION}-win-x64-portable.zip"},
            {"name": f"SmartiAI-Agent-for-Windows-{self.RELEASE_VERSION}-Setup.exe"},
        ]}
        self.assertTrue(updater._select_update_asset(release, "installer")["name"].endswith("-Setup.exe"))
        self.assertTrue(updater._select_update_asset(release, "portable")["name"].endswith("-portable.zip"))

    def test_current_release_is_not_offered_as_an_update(self):
        response = mock.Mock()
        response.json.return_value = {"tag_name": "V0.87.0", "assets": []}
        response.raise_for_status.return_value = None
        with mock.patch.object(updater.requests, "get", return_value=response):
            self.assertIsNone(updater.check_for_updates({}))

    def test_future_release_selects_portable_asset_for_portable_install(self):
        response = mock.Mock()
        response.json.return_value = {
            "tag_name": "V0.88.0",
            "name": "SmartiAI V0.88.0",
            "assets": [
                {"name": "SmartiAI-Agent-for-Windows-0.88.0-Setup.exe", "browser_download_url": "https://example.test/setup.exe"},
                {"name": "SmartiAI-Agent-for-Windows-0.88.0-win-x64-portable.zip", "browser_download_url": "https://example.test/portable.zip", "digest": "sha256:" + "a" * 64},
            ],
        }
        response.raise_for_status.return_value = None
        with mock.patch.object(updater.requests, "get", return_value=response), mock.patch.object(
            updater, "detect_installation_kind", return_value="portable"
        ):
            info = updater.check_for_updates({})
        self.assertEqual(info.version, "0.88.0")
        self.assertEqual(info.asset_kind, "portable")
        self.assertTrue(info.asset_name.endswith("-portable.zip"))
        self.assertEqual(updater._expected_sha256(info.asset_digest), "a" * 64)


if __name__ == "__main__":
    unittest.main()
