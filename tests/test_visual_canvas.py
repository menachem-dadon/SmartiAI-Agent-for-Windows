import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from smarti.history import ChatSessionStore
from smarti.config import CANVAS_MANAGER_MODEL_GUIDANCE
from smarti.core import SmartiCore
from smarti.visual_canvas import canvas_artifacts_from_messages, canvas_context_for_model, materialize_canvas_html, new_canvas_artifact


class PureCoreImportBoundaryTests(unittest.TestCase):
    def test_canvas_capability_probe_does_not_import_qt_parent_package(self):
        code = """
import json, sys
from smarti.canvas_model import web_canvas_available
available = web_canvas_available()
print(json.dumps({"available": available, "qt_loaded": "PyQt6" in sys.modules}))
raise SystemExit("PyQt6" in sys.modules)
"""
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertFalse(json.loads(completed.stdout.strip())["qt_loaded"])

    def test_core_runtime_imports_do_not_load_qt_or_canvas_renderer(self):
        modules = [
            "smarti.core",
            "smarti.history",
            "smarti.run_manager",
            "smarti.local_gateway",
            "smarti.doctor",
            "smarti.email_service",
            "smarti.attachments",
            "smarti.managers",
        ]
        code = """
import importlib, json, sys
for name in %r:
    importlib.import_module(name)
blocked = sorted(
    name for name in sys.modules
    if name == "PyQt6"
    or name.startswith("PyQt6.")
    or name in {
        "smarti.visual_canvas",
        "smarti.native_browser",
        "smarti.ui_common",
    }
)
print(json.dumps(blocked))
raise SystemExit(bool(blocked))
""" % modules

        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertEqual(json.loads(completed.stdout.strip()), [])

    def test_legacy_renderer_reexports_the_pure_canvas_model(self):
        self.assertEqual(new_canvas_artifact.__module__, "smarti.canvas_model")
        self.assertEqual(materialize_canvas_html.__module__, "smarti.canvas_model")


class VisualCanvasPersistenceTests(unittest.TestCase):
    def test_canvas_policy_defaults_to_chat_and_open_button_is_not_a_model_call(self):
        self.assertIn("ברירת המחדל היא תשובת צ'אט רגילה", CANVAS_MANAGER_MODEL_GUIDANCE)
        self.assertIn("אינה פותחת סבב מודל", CANVAS_MANAGER_MODEL_GUIDANCE)
        self.assertIn("אל תסתפק בטבלה שטוחה", CANVAS_MANAGER_MODEL_GUIDANCE)
        self.assertIn("screen_manager", CANVAS_MANAGER_MODEL_GUIDANCE)
        self.assertIn("אימות חזותי", CANVAS_MANAGER_MODEL_GUIDANCE)

    def test_canvas_is_complete_in_model_context(self):
        artifact = new_canvas_artifact({
            "title": "לוח משימות",
            "html": "<main><button id='done'>בוצע</button></main>",
            "buttons": [{"id": "done", "label": "בוצע", "x": 120, "y": 48}],
        })

        context = canvas_context_for_model([artifact])

        self.assertIn("<button id='done'>בוצע</button>", context)
        self.assertIn('"x":120.0', context)

    def test_embedded_image_reference_is_resolved_locally(self):
        image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL9PQAAAABJRU5ErkJggg=="
        artifact = new_canvas_artifact({
            "title": "קנבס עם תמונה",
            "html": "<img src='smarti-image://hero' alt='תמונה'>",
            "images": [{"id": "hero", "data_url": image, "alt": "תמונה"}],
        })

        self.assertIn("smarti-image://hero", artifact["html"])
        self.assertIn(image, materialize_canvas_html(artifact))
        self.assertEqual(artifact["images"][0]["id"], "hero")

    def test_remote_images_require_explicit_opt_in_and_only_materialize_when_enabled(self):
        payload = {
            "title": "remote image",
            "html": "<img src='smarti-image://hero' alt='hero'>",
            "images": [{"id": "hero", "url": "https://images.example.test/hero.jpg"}],
        }
        with self.assertRaises(ValueError):
            new_canvas_artifact(payload)

        artifact = new_canvas_artifact(payload, allow_remote_images=True)
        self.assertIn("about:blank", materialize_canvas_html(artifact))
        self.assertIn("https://images.example.test/hero.jpg", materialize_canvas_html(artifact, allow_remote_images=True))

    def test_source_page_exposes_primary_image_for_canvas_use(self):
        class Response:
            headers = {"content-type": "text/html"}
            encoding = "utf-8"
            apparent_encoding = "utf-8"
            url = "https://example.test/article"
            text = (
                "<html><head><title>Example</title>"
                "<meta property='og:image' content='https://cdn.example.test/hero.jpg'>"
                "</head><body><p>Example</p></body></html>"
            )
            status_code = 200

            def raise_for_status(self):
                return None

        core = SmartiCore.__new__(SmartiCore)
        core._run_cancelable_callable = lambda callback: callback()
        core._request_get = lambda *args, **kwargs: Response()
        page = core._scrape_fetch_page("https://example.test/article", {}, 5)
        self.assertEqual(page["primary_image"], "https://cdn.example.test/hero.jpg")

    def test_canvas_contract_does_not_require_a_schema_round_trip(self):
        core = SmartiCore.__new__(SmartiCore)
        requires_info, reason = core._tool_requires_info_before_use("canvas_manager", {}, set())
        self.assertFalse(requires_info)
        self.assertIsNone(reason)

    def test_multiple_distinct_canvases_are_preserved_in_one_turn(self):
        core = SmartiCore.__new__(SmartiCore)
        core.settings = {"enable_visual_surfaces": True, "enable_web_canvas": True}
        core._pending_canvas_artifacts = []
        first = core.canvas_manager_tool({"action": "create", "title": "one", "html": "<main>one</main>"})
        second = core.canvas_manager_tool({"action": "create", "title": "two", "html": "<main>two</main>"})
        self.assertTrue(first.startswith("SUCCESS:"))
        self.assertTrue(second.startswith("SUCCESS:"))
        self.assertEqual(len(core._pending_canvas_artifacts), 2)

    def test_tauri_canvas_enablement_has_no_qt_runtime_gate(self):
        core = SmartiCore.__new__(SmartiCore)
        core.settings = {"enable_visual_surfaces": True, "enable_web_canvas": True}
        core._pending_canvas_artifacts = []

        self.assertTrue(core.web_canvas_enabled())
        result = core.canvas_manager_tool({
            "action": "create",
            "title": "headless",
            "html": "<main>tauri</main>",
        })

        self.assertTrue(result.startswith("SUCCESS:"), result)

    def test_history_keeps_and_updates_button_positions(self):
        artifact = new_canvas_artifact({
            "title": "בחירה",
            "html": "<button id='choose'>בחר</button>",
        })
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            session = store.ensure_active_session()
            store.add_turn("בנה קנבס", "מוכן", assistant_metadata={"canvases": [artifact]})

            self.assertTrue(store.update_canvas_layout(
                artifact["id"],
                [{"id": "choose", "label": "בחר", "x": 42, "y": 88, "width": 110, "height": 34}],
                session["id"],
            ))

            canvases = canvas_artifacts_from_messages(store.messages(session["id"]))
            self.assertEqual(canvases[0]["button_positions"][0]["x"], 42)
            self.assertEqual(canvases[0]["button_positions"][0]["height"], 34)


if __name__ == "__main__":
    unittest.main()
