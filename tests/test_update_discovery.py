import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests
from aiohttp.test_utils import TestClient, TestServer

from smarti import update_discovery
from smarti.local_gateway import SmartiLocalGateway


class UpdateDiscoveryTests(unittest.TestCase):
    def response(self, payload):
        response = mock.Mock()
        response.json.return_value = payload
        return mock.patch.object(update_discovery.requests, "get", return_value=response)

    def test_current_and_older_releases_are_not_updates(self):
        for version in ("V0.87.0", "V0.86.9"):
            with self.subTest(version=version), self.response({"tag_name": version}):
                self.assertIsNone(update_discovery.discover_update({}, "0.87.0"))

    def test_new_release_exposes_notes_and_page_without_installer(self):
        with self.response({"tag_name": "V0.88.0", "body": "מה חדש", "assets": []}):
            update = update_discovery.discover_update({}, "0.87.0")
        self.assertEqual(update, {
            "version": "0.88.0", "body": "מה חדש",
            "releaseUrl": update_discovery.GITHUB_RELEASES_URL + "/tag/V0.88.0",
        })

    def test_draft_and_prerelease_are_not_offered(self):
        for flag in ("draft", "prerelease"):
            with self.subTest(flag=flag), self.response({"tag_name": "V0.88.0", flag: True}):
                self.assertIsNone(update_discovery.discover_update({}, "0.87.0"))

    def test_invalid_payload_is_a_failure(self):
        for payload in ([], {}, {"tag_name": "invalid"}):
            with self.subTest(payload=payload), self.response(payload):
                with self.assertRaisesRegex(RuntimeError, "unexpected release payload"):
                    update_discovery.discover_update({})

    def test_http_failure_is_not_reported_as_no_update(self):
        with self.response({}) as get:
            get.return_value.raise_for_status.side_effect = requests.HTTPError("rate limited")
            with self.assertRaises(requests.HTTPError):
                update_discovery.discover_update({})

    def test_request_uses_core_trust_settings_and_timeout(self):
        settings = {"ssl_trust_mode": "custom_ca", "ssl_custom_ca_path": "trusted.pem"}
        with self.response({"tag_name": "V0.87.0"}) as get, mock.patch.object(
            update_discovery, "ssl_request_kwargs", return_value={"verify": "trusted.pem"},
        ) as trust:
            update_discovery.discover_update(settings)
        self.assertEqual(trust.call_args.args[0], settings)
        self.assertEqual(trust.call_args.kwargs["url"], update_discovery.GITHUB_API_RELEASE_LATEST)
        self.assertEqual(get.call_args.kwargs["verify"], "trusted.pem")
        self.assertEqual(get.call_args.kwargs["timeout"], 25)

    def test_discovery_and_gateway_import_without_qt(self):
        code = "import sys; import smarti.update_discovery, smarti.local_gateway; assert not any(n == 'PyQt6' or n.startswith('PyQt6.') for n in sys.modules)"
        result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


class UpdateGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.core = SimpleNamespace(settings={"ssl_trust_mode": "system"})
        gateway = SmartiLocalGateway(self.core, "test-token", port=0)
        self.client = TestClient(TestServer(gateway._application()))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer test-token"}

    async def test_authentication_and_success_without_signed_configuration(self):
        with mock.patch("smarti.local_gateway.discover_update", return_value=None) as discover:
            response = await self.client.get("/v2/management/updates")
            self.assertEqual(response.status, 401)
            discover.assert_not_called()
            response = await self.client.get("/v2/management/updates", headers=self.headers)
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())["data"], {"update": None})
            discover.assert_called_once_with(self.core.settings)

    async def test_network_failure_preserves_previous_check_state(self):
        self.core.settings.update(updates_last_checked_at="before", updates_last_available_version="0.88.0")
        before = self.core.settings.copy()
        with mock.patch("smarti.local_gateway.discover_update", side_effect=requests.Timeout("timed out")):
            response = await self.client.get("/v2/management/updates", headers=self.headers)
        self.assertEqual(response.status, 502)
        self.assertEqual((await response.json())["error"], "update_check_failed")
        self.assertEqual(self.core.settings, before)
