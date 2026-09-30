import json
import asyncio
import io
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from smarti.agent.model_context import ModelContextMixin
from smarti.desktop_services import clear_usage, usage_snapshot
from smarti import usage_pricing


class UsageStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "usage.json"
        self.core = SimpleNamespace(_usage_lock=threading.RLock(), memory_manager=SimpleNamespace(
            memory_stats=mock.Mock(side_effect=AssertionError("Usage must not query memory/RAG")),
        ))
        self.today = datetime.now().date()
        self.catalog = {"gemini/gemini-test": {
            "input_cost_per_token": 0.000001, "output_cost_per_token": 0.000002,
            "cache_read_input_token_cost": 0.0000002, "cache_creation_input_token_cost": 0.00000125,
        }}
        for patch in (
            mock.patch("smarti.common.USAGE_FILE", str(self.path)),
            mock.patch("smarti.agent.model_context.USAGE_FILE", str(self.path)),
            mock.patch("smarti.usage_pricing.pricing_cache", return_value={}),
            mock.patch("smarti.usage_pricing.bundled_pricing", return_value=self.catalog),
            mock.patch("smarti.usage_pricing.request_pricing_refresh", return_value={"refreshing": False}),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, rows):
        self.path.write_text(json.dumps(rows), encoding="utf-8")

    def test_reads_real_runtime_log_and_prices_cache_without_double_counting(self):
        ModelContextMixin._log_usage(self.core, "gemini-test", {
            "prompt": 1000, "completion": 500, "total": 1500,
            "cached_prompt": 200, "cache_write_prompt": 100, "reasoning": 50,
        })
        data = usage_snapshot(self.core, "today")
        self.assertEqual(data["total_tokens"], 1500)
        self.assertEqual((data["input_tokens"], data["output_tokens"]), (1000, 500))
        self.assertAlmostEqual(data["cost_usd"], 0.001865)
        self.assertEqual(data["models"][0]["cost_status"], "estimated")
        self.assertNotIn("memory", data)

    def test_existing_dates_models_and_internal_memory_rows(self):
        self.write({
            str(self.today): {"gemini-test": {"prompt": 20, "completion": 10, "total": 30},
                             "memory-rag/local": {"prompt": 9000, "total": 9000},
                             "smarti-memory-rag/local": {"total": 5000}},
            str(self.today - timedelta(days=20)): {"gemini-test": {"prompt": 100, "completion": 50, "total": 150}},
        })
        self.assertEqual(usage_snapshot(self.core, "all")["total_tokens"], 180)
        self.assertEqual(usage_snapshot(self.core, "today")["total_tokens"], 30)
        self.assertEqual(len(usage_snapshot(self.core)["models"]), 1)

    def test_modern_schema_and_zero_recorded_cost_take_precedence(self):
        self.write({str(self.today): {"free-cloud": {
            "input_tokens": 100, "output_tokens": 50, "cached_input_tokens": 25,
            "cache_write_tokens": 10, "cost_usd": 0,
        }}})
        row = usage_snapshot(self.core)["models"][0]
        self.assertEqual(row["tokens"], 150)
        self.assertEqual(row["cost_usd"], 0)
        self.assertEqual(row["cost_status"], "recorded")

    def test_partial_cost_does_not_present_unpriced_models_as_free(self):
        self.write({str(self.today): {
            "unknown-cloud": {"prompt": 500, "completion": 50},
            "gemini-test": {"prompt": 100, "completion": 50},
            "models/local.gguf": {"prompt": 200, "completion": 50},
        }})
        data = usage_snapshot(self.core)
        self.assertEqual(data["total_tokens"], 950)
        self.assertIsNone(data["cost_usd"])
        self.assertAlmostEqual(data["known_cost_usd"], 0.0002)
        self.assertEqual(data["unpriced_models"], 1)
        rows = {row["model"]: row for row in data["models"]}
        self.assertIsNone(rows["unknown-cloud"]["cost_usd"])
        self.assertEqual(rows["models/local.gguf"]["cost_status"], "local")

    def test_persisted_rates_and_negative_cache_entries(self):
        self.write({str(self.today): {"gemini-test": {"prompt": 1000, "completion": 500}}})
        with mock.patch("smarti.usage_pricing.pricing_cache", return_value={
            "gemini/gemini-test": {"input": 0.000002, "output": 0.000004},
        }):
            self.assertAlmostEqual(usage_snapshot(self.core)["cost_usd"], 0.004)
        with mock.patch("smarti.usage_pricing.pricing_cache", return_value={
            "gemini/gemini-test": {"unpriced": True},
        }):
            self.assertAlmostEqual(usage_snapshot(self.core)["cost_usd"], 0.002)

    def test_period_boundaries_and_invalid_dates(self):
        rows = {str(self.today - timedelta(days=age)): {"gemini-test": {"prompt": 1}} for age in (0, 6, 7, 29, 30)}
        rows["not-a-date"] = {"gemini-test": {"prompt": 100}}
        rows[str(self.today + timedelta(days=1))] = {"gemini-test": {"prompt": 100}}
        self.write(rows)
        for period, expected in (("today", 1), ("week", 2), ("month", 4), ("all", 5)):
            with self.subTest(period=period):
                self.assertEqual(usage_snapshot(self.core, period)["total_tokens"], expected)

    def test_invalid_token_values_do_not_hide_other_models(self):
        self.write({str(self.today): {"broken": {"prompt": "oops", "completion": -1, "total": "NaN"},
                                     "gemini-test": {"prompt": "10", "completion": 5}}})
        self.assertEqual(usage_snapshot(self.core)["total_tokens"], 15)

    def test_read_failure_is_reported_and_missing_file_is_empty(self):
        self.assertEqual(usage_snapshot(self.core)["models"], [])
        self.path.write_text("{unfinished", encoding="utf-8")
        with self.assertRaises(ValueError):
            usage_snapshot(self.core)
        self.write([])
        with self.assertRaises(ValueError):
            usage_snapshot(self.core)

    def test_clear_preserves_backup_and_resets_usage(self):
        original = {str(self.today): {"gemini-test": {"prompt": 100}}}
        self.write(original)
        data = clear_usage(self.core)
        self.assertTrue(data["cleared"])
        self.assertEqual(json.loads(Path(data["backup_path"]).read_text(encoding="utf-8")), original)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {})
        self.assertEqual(data["total_tokens"], 0)

    def test_authenticated_gateway_returns_saved_usage_and_clear_backup(self):
        from aiohttp.test_utils import TestClient, TestServer
        from smarti.local_gateway import SmartiLocalGateway

        self.write({str(self.today): {"gemini-test": {"prompt": 100, "completion": 50}}})
        self.core.settings = {}

        async def check():
            gateway = SmartiLocalGateway(self.core, "test-token", port=0)
            async with TestClient(TestServer(gateway._application())) as client:
                response = await client.get("/v2/management/usage?timeframe=all")
                self.assertEqual(response.status, 401)
                headers = {"Authorization": "Bearer test-token"}
                response = await client.get("/v2/management/usage?timeframe=all", headers=headers)
                self.assertEqual(response.status, 200)
                data = (await response.json())["data"]
                self.assertEqual(data["total_tokens"], 150)
                self.assertAlmostEqual(data["cost_usd"], 0.0002)
                response = await client.delete("/v2/management/usage", headers=headers)
                self.assertEqual(response.status, 200)
                data = (await response.json())["data"]
                self.assertTrue(Path(data["backup_path"]).exists())
                self.assertEqual(data["total_tokens"], 0)
        asyncio.run(check())


class UsagePricingCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "prices.json"
        self.store = usage_pricing.UsagePricingCatalog(self.path)
        self.rates = {"input": 0.000002, "output": 0.000008, "cache_read": 0.0000002,
                      "cache_write": 0.000002, "_source": "remote"}

    def saved_catalog(self, *, fresh=False):
        updated = datetime.now(timezone.utc) - timedelta(days=0 if fresh else 2)
        self.path.write_text(json.dumps({
            "version": 1, "updated_at": updated.isoformat(),
            "models": {"retired-model": self.rates},
        }), encoding="utf-8")

    def join_refresh(self):
        with self.store._lock:
            worker = self.store._worker
        if worker:
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())

    def test_download_normalizes_new_models_and_uses_verified_tls(self):
        payload = {
            "gpt-new": {"input_cost_per_token": 0.000002, "output_cost_per_token": 0.000008,
                        "input_cost_per_token_cache_hit": 0.0000002},
            "bad": {"input_cost_per_token": -1, "output_cost_per_token": 2},
            "nan": {"input_cost_per_token": "NaN", "output_cost_per_token": 2},
            "metadata": {"max_tokens": 1000},
        }
        context = object()
        with mock.patch.object(usage_pricing, "create_ssl_context", return_value=context) as tls, \
             mock.patch.object(usage_pricing.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as download:
            prices = self.store._download({"ssl_trust_mode": "system"})
        self.assertEqual(prices, {"gpt-new": self.rates})
        tls.assert_called_once_with({"ssl_trust_mode": "system"}, url=usage_pricing.PRICING_CATALOG_URL,
                                    data_dir=self.root, allow_legacy=False)
        self.assertIs(download.call_args.kwargs["context"], context)
        self.assertEqual(download.call_args.kwargs["timeout"], 8)

    def test_invalid_downloads_preserve_saved_prices(self):
        self.saved_catalog()
        original = self.path.read_bytes()
        for payload in (b"unfinished{", b"[]", b"{}", b'{"bad":{"input_cost_per_token":-1}}', b"x" * 65):
            with self.subTest(payload=payload), \
                 mock.patch.object(usage_pricing, "PRICING_MAX_BYTES", 64), \
                 mock.patch.object(usage_pricing, "create_ssl_context"), \
                 mock.patch.object(usage_pricing.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
                self.store._refresh({})
                self.assertEqual(self.path.read_bytes(), original)
                self.assertTrue(self.store.status()["refresh_failed"])

    def test_save_failure_keeps_old_catalog_and_removes_temporary_file(self):
        self.saved_catalog()
        original = self.path.read_bytes()
        with mock.patch.object(self.store, "_download", return_value={"new-model": self.rates}), \
             mock.patch.object(usage_pricing.os, "replace", side_effect=OSError("disk unavailable")):
            self.store._refresh({})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.root.glob(".usage-pricing-*.tmp")), [])
        self.assertTrue(self.store.status()["refresh_failed"])

    def test_refresh_is_nonblocking_and_shared_across_requests(self):
        started, release = threading.Event(), threading.Event()

        def delayed_download(settings):
            started.set()
            if not release.wait(timeout=2):
                raise TimeoutError("Test did not release download")
            self.assertEqual(settings, {"ssl_trust_mode": "system"})
            return {"new-model": self.rates}

        with mock.patch.object(self.store, "_download", side_effect=delayed_download) as download:
            try:
                self.assertTrue(self.store.request_refresh({"ssl_trust_mode": "system", "api_key": "must-not-be-forwarded"}))
                self.assertTrue(started.wait(timeout=1))
                self.assertTrue(self.store.status()["refreshing"])
                self.assertFalse(self.store.request_refresh())
                download.assert_called_once()
            finally:
                release.set()
                self.join_refresh()
        self.assertTrue(self.store.status()["cached"])
        self.assertFalse(self.store.status()["refresh_failed"])

    def test_fresh_catalog_avoids_network_and_failures_are_throttled(self):
        self.saved_catalog(fresh=True)
        with mock.patch.object(self.store, "_download") as download:
            self.assertFalse(self.store.request_refresh())
            download.assert_not_called()
        self.saved_catalog(fresh=False)
        with mock.patch.object(self.store, "_download", side_effect=OSError("offline")) as download, \
             mock.patch.object(usage_pricing.time, "monotonic", return_value=100):
            self.assertTrue(self.store.request_refresh())
            self.join_refresh()
            self.assertFalse(self.store.request_refresh())
            with mock.patch.object(usage_pricing.time, "monotonic", return_value=100 + usage_pricing.PRICING_RETRY_DELAY):
                self.assertTrue(self.store.request_refresh())
                self.join_refresh()
            self.assertEqual(download.call_count, 2)

    def test_saved_new_prices_survive_restart_offline_and_override_old_rates(self):
        self.saved_catalog()
        with mock.patch.object(self.store, "_download", return_value={"gemini/gemini-new": self.rates}):
            self.store._refresh({})
        self.assertIn("retired-model", self.store.document()["models"])
        original = self.path.read_bytes()
        restarted = usage_pricing.UsagePricingCatalog(self.path)
        with mock.patch.object(restarted, "_download", side_effect=OSError("offline")):
            restarted._refresh({})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(restarted.status()["cached"])
        self.assertTrue(restarted.status()["refresh_failed"])
        (self.root / "smarti_usage_cost_cache.json").write_text(json.dumps({
            "version": 1, "models": {"gemini/gemini-new": {"input": 1, "output": 1}},
        }), encoding="utf-8")
        with mock.patch.object(usage_pricing, "pricing_catalog", return_value=restarted), \
             mock.patch.object(usage_pricing, "USER_DATA_DIR", self.root):
            cached = usage_pricing.pricing_cache()
        tokens = usage_pricing.normalize_tokens({"prompt": 1000, "completion": 500, "cached_prompt": 200})
        cost, status = usage_pricing.usage_cost("gemini-new", {}, tokens, cached, {})
        self.assertAlmostEqual(cost, 0.00564)
        self.assertEqual(status, "estimated")
        self.assertEqual(usage_pricing.usage_cost("unknown-new", {}, tokens, cached, {}), (None, "unavailable"))

    def test_first_start_offline_uses_bundled_and_fallback_prices(self):
        usage = self.root / "usage.json"
        usage.write_text(json.dumps({str(datetime.now().date()): {
            "bundled-model": {"prompt": 1000, "completion": 500},
            "gpt-5.6-sol": {"prompt": 1000, "completion": 500},
        }}), encoding="utf-8")
        with mock.patch.object(self.store, "_download", side_effect=OSError("offline")):
            self.assertTrue(self.store.request_refresh())
            self.join_refresh()
        with mock.patch("smarti.common.USAGE_FILE", str(usage)), \
             mock.patch.object(usage_pricing, "USER_DATA_DIR", self.root), \
             mock.patch.object(usage_pricing, "pricing_catalog", return_value=self.store), \
             mock.patch.object(usage_pricing, "bundled_pricing", return_value={"bundled-model": {
                 "input_cost_per_token": 0.000002, "output_cost_per_token": 0.000008,
             }}):
            data = usage_snapshot(SimpleNamespace(settings={}), "today")
        self.assertAlmostEqual(data["cost_usd"], 0.026)
        self.assertEqual(data["unpriced_models"], 0)
        self.assertFalse(data["pricing"]["cached"])
        self.assertTrue(data["pricing"]["refresh_failed"])
        self.assertFalse(self.path.exists())

    def test_usage_snapshot_updates_cost_after_background_refresh(self):
        usage = self.root / "usage.json"
        usage.write_text(json.dumps({str(datetime.now().date()): {
            "new-model": {"prompt": 1000, "completion": 500},
        }}), encoding="utf-8")
        release = threading.Event()

        def delayed_download(settings):
            if not release.wait(timeout=2):
                raise TimeoutError("Test did not release download")
            return {"new-model": self.rates}

        with mock.patch("smarti.common.USAGE_FILE", str(usage)), \
             mock.patch.object(usage_pricing, "USER_DATA_DIR", self.root), \
             mock.patch.object(usage_pricing, "pricing_catalog", return_value=self.store), \
             mock.patch.object(usage_pricing, "bundled_pricing", return_value={}), \
             mock.patch.object(self.store, "_download", side_effect=delayed_download):
            try:
                initial = usage_snapshot(SimpleNamespace(settings={}), "today")
                self.assertEqual(initial["total_tokens"], 1500)
                self.assertIsNone(initial["cost_usd"])
                self.assertTrue(initial["pricing"]["refreshing"])
            finally:
                release.set()
                self.join_refresh()
            updated = usage_snapshot(SimpleNamespace(settings={}), "today")
        self.assertEqual(updated["total_tokens"], 1500)
        self.assertAlmostEqual(updated["cost_usd"], 0.006)
        self.assertEqual(updated["unpriced_models"], 0)
        self.assertFalse(updated["pricing"]["refreshing"])
        self.assertTrue(updated["pricing"]["cached"])


if __name__ == "__main__":
    unittest.main()
