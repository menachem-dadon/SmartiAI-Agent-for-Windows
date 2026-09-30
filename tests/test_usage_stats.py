import json
import asyncio
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from smarti.agent.model_context import ModelContextMixin
from smarti.desktop_services import clear_usage, usage_snapshot


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


if __name__ == "__main__":
    unittest.main()
