"""Focused tests for the official Codex ChatGPT sign-in provider."""
import os
import json
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

from smarti.codex_signin import CodexConnectionStatus, CodexProtocolError, CodexSignInError, CodexSignInProvider
from smarti.common import provider_fallback_models
from smarti.common import SmartiCancelled
from smarti.config import DEFAULT_SETTINGS
from smarti.core import SmartiCore
from smarti.managers import AgentRuntime, SettingsManager


class CodexSignInProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = CodexSignInProvider(self.temp.name, executable="codex-test")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _codex_jsonl_response(
        text="תשובה",
        input_tokens=10,
        cached_input_tokens=0,
        output_tokens=4,
        reasoning_tokens=0,
        tool_name=None,
        tool_arguments=None,
        progress_report=None,
    ):
        if tool_name:
            text = json.dumps(
                {
                    "kind": "tool_calls",
                    "tool_calls": [{"name": tool_name, "arguments_json": json.dumps(tool_arguments or {}, ensure_ascii=False)}],
                    "final_answer": None,
                    "progress_report": progress_report,
                },
                ensure_ascii=False,
            )
        else:
            text = json.dumps(
                {
                    "kind": "final",
                    "tool_calls": None,
                    "final_answer": text,
                    "progress_report": None,
                },
                ensure_ascii=False,
            )
        return "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}}, ensure_ascii=False),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": input_tokens,
                            "cached_input_tokens": cached_input_tokens,
                            "output_tokens": output_tokens,
                            "reasoning_output_tokens": reasoning_tokens,
                        },
                    }
                ),
            )
        )

    def test_environment_preserves_official_cli_home_without_api_credentials(self):
        with mock.patch.dict(
            os.environ,
            {
                "CODEX_HOME": r"C:\Users\test user\Codex Home",
                "OPENAI_API_KEY": "must-not-reach-codex",
                "CODEX_API_KEY": "must-not-reach-codex",
                "CODEX_ACCESS_TOKEN": "must-not-reach-codex",
            },
            clear=False,
        ):
            environment = self.provider._environment()

        self.assertEqual(environment["CODEX_HOME"], r"C:\Users\test user\Codex Home")
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("CODEX_API_KEY", environment)
        self.assertNotIn("CODEX_ACCESS_TOKEN", environment)

    def test_rate_limits_are_normalized_to_remaining_five_hour_and_weekly_quota(self):
        response = {
            "rateLimits": {
                "planType": "fallback",
                "primary": {"usedPercent": 99, "windowDurationMins": 300},
                "secondary": {"usedPercent": 99, "windowDurationMins": 10080},
            },
            "rateLimitsByLimitId": {
                "codex": {
                    "planType": "plus",
                    "primary": {
                        "usedPercent": 37,
                        "windowDurationMins": 300,
                        "resetsAt": 1900000000,
                    },
                    "secondary": {
                        "usedPercent": 6,
                        "windowDurationMins": 10080,
                        "resetsAt": 1901000000,
                    },
                }
            },
        }

        quota = self.provider.normalize_rate_limits(response)

        self.assertEqual(quota["plan_type"], "plus")
        self.assertEqual(quota["five_hour"]["remaining_percent"], 63)
        self.assertEqual(quota["five_hour"]["window_minutes"], 300)
        self.assertEqual(quota["weekly"]["remaining_percent"], 94)
        self.assertEqual(quota["weekly"]["window_minutes"], 10080)

    def test_rate_limit_percentages_are_clamped_and_legacy_snapshot_is_supported(self):
        quota = self.provider.normalize_rate_limits({
            "rateLimits": {
                "primary": {"usedPercent": -8, "windowDurationMins": 300},
                "secondary": {"usedPercent": 140, "windowDurationMins": 10080},
            }
        })

        self.assertEqual(quota["five_hour"]["remaining_percent"], 100)
        self.assertEqual(quota["weekly"]["remaining_percent"], 0)

    def test_weekly_primary_window_is_not_mislabeled_as_five_hours(self):
        quota = self.provider.normalize_rate_limits({
            "rateLimits": {
                "planType": "plus",
                "primary": {
                    "usedPercent": 10,
                    "windowDurationMins": 10080,
                    "resetsAt": 1901000000,
                },
                "secondary": None,
            }
        })

        self.assertIsNone(quota["five_hour"])
        self.assertEqual(quota["weekly"]["remaining_percent"], 90)
        self.assertEqual(quota["weekly"]["window_minutes"], 10080)

    def test_smarti_codex_cli_override_is_used_verbatim(self):
        path = r"C:\Users\יהודית סיידון\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe"
        with mock.patch.dict(os.environ, {"SMARTI_CODEX_CLI": path}):
            self.assertEqual(self.provider._find_executable(), path)

    def test_codex_model_choices_are_the_supported_curated_list(self):
        self.assertEqual(
            provider_fallback_models("openai_codex_signin"),
            [
                "codex default",
                "gpt-5.6-sol",
                "gpt-5.6-terra",
                "gpt-5.6-luna",
                "gpt-5.5",
                "gpt-5.4",
                "gpt-5.4-mini",
            ],
        )

    def test_windows_apps_desktop_path_is_not_treated_as_the_cli(self):
        desktop_path = r"C:\Program Files\WindowsApps\OpenAI.Codex\app\resources\codex.exe"
        self.assertTrue(self.provider._is_windows_apps_path(desktop_path))

    @mock.patch("smarti.codex_signin.subprocess.run")
    @mock.patch("smarti.codex_signin.shutil.which", return_value="codex-test")
    def test_status_uses_official_login_status_command(self, _which, run):
        run.return_value = mock.Mock(returncode=0, stdout="Logged in with ChatGPT", stderr="")

        status = self.provider.connection_status()

        self.assertEqual(status.state, "connected")
        command = run.call_args.args[0]
        self.assertEqual(command[1:], ["login", "status"])
        env = run.call_args.kwargs["env"]
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertNotIn("CODEX_ACCESS_TOKEN", env)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_connection_status_distinguishes_missing_and_expired_credentials(self):
        self.provider._run = mock.Mock(return_value=(1, "Not logged in", ""))
        missing = self.provider.connection_status()
        self.assertEqual(missing.state, "not_connected")

        self.provider._run = mock.Mock(return_value=(1, "Access token expired", ""))
        expired = self.provider.connection_status()
        self.assertEqual(expired.state, "reauth_required")

    @mock.patch("smarti.codex_signin.subprocess.run", side_effect=PermissionError())
    @mock.patch("smarti.codex_signin.shutil.which", return_value="codex-test")
    def test_permission_denied_reports_a_runnable_cli_problem(self, _which, _run):
        status = self.provider.connection_status()

        self.assertEqual(status.state, "unavailable")
        self.assertIn("Windows אינו מאפשר", status.message)

    def test_complete_is_ephemeral_and_read_only(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        self.provider._run = mock.Mock(return_value=(
            0,
            self._codex_jsonl_response(
                "תשובה",
                input_tokens=12,
                cached_input_tokens=7,
                output_tokens=5,
                reasoning_tokens=3,
            ),
            "",
        ))

        response, usage = self.provider.complete(
            [
                {"role": "system", "content": "הנחיות"},
                {"role": "user", "content": "שלום"},
            ],
            model="gpt-5.5",
        )

        self.assertEqual(response, "תשובה")
        self.assertEqual(
            usage,
            {"prompt": 12, "completion": 8, "total": 20, "cached_prompt": 7},
        )
        args = self.provider._run.call_args.args[0]
        self.assertEqual(args[:2], ["exec", "--json"])
        self.assertIn("--json", args)
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--ephemeral", args)
        self.assertIn("read-only", args)
        self.assertIn("--skip-git-repo-check", args)
        self.assertIn("--model", args)
        self.assertIn("gpt-5.5", args)
        self.assertEqual(args[-1], "-")
        self.assertIn("[USER]", self.provider._run.call_args.kwargs["input_text"])

    def test_codex_default_defers_model_selection_to_the_signed_in_account(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        self.provider._run = mock.Mock(return_value=(0, self._codex_jsonl_response(), ""))

        self.provider.complete([{"role": "user", "content": "שלום"}], model="codex default")

        args = self.provider._run.call_args.args[0]
        self.assertNotIn("--model", args)

    def test_reasoning_effort_is_passed_as_an_official_cli_config_override(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        self.provider._run = mock.Mock(return_value=(0, self._codex_jsonl_response(), ""))

        self.provider.complete(
            [{"role": "user", "content": "שלום"}],
            model="gpt-5.5",
            reasoning_effort="xhigh",
        )

        args = self.provider._run.call_args.args[0]
        config_values = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "--config"]
        self.assertIn('model_reasoning_effort="xhigh"', config_values)
        self.assertEqual(args[args.index("--model") + 1], "gpt-5.5")

    def test_automatic_reasoning_omits_the_cli_config_override(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        self.provider._run = mock.Mock(return_value=(0, self._codex_jsonl_response(), ""))

        self.provider.complete(
            [{"role": "user", "content": "שלום"}],
            model="codex default",
            reasoning_effort="auto",
        )

        args = self.provider._run.call_args.args[0]
        config_values = [
            args[index + 1]
            for index, value in enumerate(args[:-1])
            if value == "--config"
        ]
        self.assertFalse(
            any(value.startswith("model_reasoning_effort=") for value in config_values)
        )
        self.assertNotIn("--model", args)

    def test_gpt_5_6_max_reasoning_effort_is_passed_to_codex(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        self.provider._run = mock.Mock(return_value=(0, self._codex_jsonl_response(), ""))

        self.provider.complete(
            [{"role": "user", "content": "שלום"}],
            model="gpt-5.6-sol",
            reasoning_effort="max",
        )

        args = self.provider._run.call_args.args[0]
        config_values = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "--config"]
        self.assertIn('model_reasoning_effort="max"', config_values)
        self.assertEqual(args[args.index("--model") + 1], "gpt-5.6-sol")

    def test_noninteractive_codex_process_can_be_cancelled_during_a_long_request(self):
        provider = CodexSignInProvider(self.temp.name, executable=sys.executable)
        cancel_event = threading.Event()
        timer = threading.Timer(0.1, cancel_event.set)
        started = time.monotonic()
        timer.start()
        try:
            with mock.patch.dict(os.environ, {"SMARTI_CODEX_CLI": ""}):
                with self.assertRaises(SmartiCancelled):
                    provider._run(
                        ("-c", "import time; time.sleep(30)"),
                        timeout=30,
                        cancel_event=cancel_event,
                    )
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - started, 5)

    def test_agent_prompt_preserves_system_tools_without_authorizing_native_codex_actions(self):
        messages = [
            {"role": "system", "content": "Use TOOL_CALL syntax when a tool is needed."},
            {"role": "user", "content": "צור קנבס."},
        ]
        instructions = self.provider._build_model_instructions(messages)
        prompt = self.provider._build_prompt(messages)

        self.assertIn("[SMARTIAI SYSTEM INSTRUCTIONS]", instructions)
        self.assertIn("Use TOOL_CALL syntax", instructions)
        self.assertIn("supplied JSON Schema", instructions)
        self.assertIn("legacy instruction", instructions)
        self.assertIn("Never claim that a tool, canvas", instructions)
        self.assertNotIn("Use TOOL_CALL syntax", prompt)
        self.assertIn("[USER]", prompt)

    def test_complete_uses_a_temporary_base_instruction_file_and_disables_native_tools(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        captured = {}

        def run(args, **kwargs):
            args = list(args)
            config_values = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "--config"]
            instructions_config = next(value for value in config_values if value.startswith("model_instructions_file="))
            instructions_path = Path(json.loads(instructions_config.split("=", 1)[1]))
            captured["path"] = instructions_path
            captured["instructions"] = instructions_path.read_text(encoding="utf-8")
            schema_path = Path(args[args.index("--output-schema") + 1])
            captured["schema_path"] = schema_path
            captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
            captured["args"] = args
            captured["prompt"] = kwargs["input_text"]
            return 0, self._codex_jsonl_response(), ""

        self.provider._run = mock.Mock(side_effect=run)
        self.provider.complete(
            [
                {"role": "system", "content": "Smarti system rule."},
                {"role": "user", "content": "שלום"},
            ],
            model="gpt-5.5",
        )

        self.assertIn("Smarti system rule.", captured["instructions"])
        self.assertNotIn("Smarti system rule.", captured["prompt"])
        self.assertIn("--disable", captured["args"])
        self.assertIn("shell_tool", captured["args"])
        self.assertIn("--ignore-user-config", captured["args"])
        self.assertIn("--output-schema", captured["args"])
        self.assertIn('web_search="disabled"', captured["args"])
        self.assertFalse(captured["path"].exists())
        self.assertFalse(captured["schema_path"].exists())
        self.assertEqual(captured["schema"]["properties"]["kind"]["enum"], ["tool_calls", "final"])
        self.assertFalse(captured["schema"]["properties"]["tool_calls"]["items"]["additionalProperties"])
        self.assertEqual(
            captured["schema"]["properties"]["tool_calls"]["items"]["properties"]["arguments_json"]["type"],
            "string",
        )

    def test_schema_tool_turn_is_mapped_to_the_existing_smarti_tool_wire_format(self):
        response = self.provider._decode_structured_turn(json.dumps({
            "kind": "tool_calls",
            "tool_calls": [{"name": "web_manager", "arguments_json": '{"action":"search","query":"test"}'}],
            "final_answer": None,
            "progress_report": "אני בודק מידע עדכני ברשת.",
        }))

        report, wire_format = response.split("\n", 1)
        self.assertEqual(report, "אני בודק מידע עדכני ברשת.")
        self.assertEqual(json.loads(wire_format), {
            "tool_calls": [{"name": "web_manager", "arguments": {"action": "search", "query": "test"}}],
        })

        parsed = AgentRuntime(mock.Mock()).extract_tool_calls(response)
        self.assertEqual(parsed["pre_text"], "אני בודק מידע עדכני ברשת.")
        self.assertEqual(len(parsed["tool_calls"]), 1)

    def test_schema_rejects_non_object_tool_arguments(self):
        with self.assertRaises(CodexSignInError):
            self.provider._decode_structured_turn(json.dumps({
                "kind": "tool_calls",
                "tool_calls": [{"name": "web_manager", "arguments_json": "[]"}],
                "final_answer": None,
                "progress_report": None,
            }))

    def test_invalid_schema_turn_is_rejected_without_text_heuristics(self):
        with self.assertRaises(CodexProtocolError) as raised:
            self.provider._decode_structured_turn('{"kind":"final","tool_calls":null,"final_answer":null,"progress_report":null}')
        feedback = raised.exception.feedback_for_model()
        self.assertIn("SMARTIAI_PROTOCOL_REPAIR", feedback)
        self.assertIn("Correct the response", feedback)
        self.assertIn("Rejected response excerpt", feedback)

    def test_agent_api_layer_preserves_protocol_errors_for_the_repair_loop(self):
        core = SmartiCore.__new__(SmartiCore)
        core.mode = "openai_codex_signin"
        core.settings = {"codex_reasoning_effort": "max", "codex_request_timeout_seconds": 1234}
        protocol_error = CodexProtocolError("invalid structured turn", "{bad json")
        core.codex_signin_provider = mock.Mock()
        core.codex_signin_provider.complete.side_effect = protocol_error
        core._prepare_messages_for_budget = mock.Mock(return_value=[{"role": "user", "content": "test"}])
        core._raise_if_cancelled = mock.Mock()

        with self.assertRaises(CodexProtocolError) as raised:
            core._handle_api_request_with_retry("gpt-5.6-sol", [{"role": "user", "content": "test"}])

        self.assertIs(raised.exception, protocol_error)
        self.assertEqual(core.codex_signin_provider.complete.call_args.kwargs["timeout"], 1234)
        self.assertIsNone(core.codex_signin_provider.complete.call_args.kwargs["cancel_event"])

    def test_agent_api_layer_uses_long_codex_timeout_default(self):
        core = SmartiCore.__new__(SmartiCore)
        core.mode = "openai_codex_signin"
        core.settings = {}
        core.codex_signin_provider = mock.Mock()
        core.codex_signin_provider.complete.return_value = ("done", {})
        core._prepare_messages_for_budget = mock.Mock(return_value=[{"role": "user", "content": "test"}])
        core._raise_if_cancelled = mock.Mock()

        core._handle_api_request_with_retry("gpt-5.6-terra", [{"role": "user", "content": "test"}])

        self.assertEqual(core.codex_signin_provider.complete.call_args.kwargs["timeout"], 1800)

    def test_protocol_error_is_queued_as_model_feedback_instead_of_stopping(self):
        core = SmartiCore.__new__(SmartiCore)
        core.mode = "openai_codex_signin"
        core.settings = {"codex_protocol_repair_attempts": 2}
        messages = [{"role": "user", "content": "original task"}]
        error = CodexProtocolError("invalid tool arguments", '{"kind":"tool_calls"}')

        queued = core._queue_codex_protocol_repair(messages, error, attempt=1)

        self.assertTrue(queued)
        self.assertEqual(messages[-1]["role"], "user")
        self.assertIn("SMARTIAI_PROTOCOL_REPAIR", messages[-1]["content"])
        self.assertIn("continue the same task", messages[-1]["content"])
        self.assertFalse(core._queue_codex_protocol_repair(messages, error, attempt=3))
        self.assertEqual(len(messages), 2)

    def test_login_skips_interactive_command_when_already_connected(self):
        connected = CodexConnectionStatus("connected", "מחובר", "chatgpt")
        self.provider.connection_status = mock.Mock(return_value=connected)
        self.provider._run = mock.Mock()

        status = self.provider.login()

        self.assertIs(status, connected)
        self.provider._run.assert_not_called()

    def test_login_uses_a_new_console_after_a_not_connected_status(self):
        self.provider.connection_status = mock.Mock(
            side_effect=[CodexConnectionStatus("not_connected", "לא מחובר"), CodexConnectionStatus("connected", "מחובר")]
        )
        self.provider._run = mock.Mock(return_value=(0, "", ""))

        status = self.provider.login()

        self.assertEqual(status.state, "connected")
        self.provider._run.assert_called_once_with(
            ("login",), timeout=600, interactive_console=(os.name == "nt")
        )


class LongTaskSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = SettingsManager(
            os.path.join(self.temp.name, "settings.json"),
            DEFAULT_SETTINGS,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_old_shipped_limits_migrate_to_long_running_defaults(self):
        loaded = {
            "settings_schema_version": 2,
            "max_agent_loops": 15,
            "max_total_task_seconds": 3600,
            "preserve_current_task_tool_context": True,
        }

        migrated, changed = self.manager.migrate_or_merge(loaded)

        self.assertTrue(changed)
        self.assertEqual(migrated["max_agent_loops"], 0)
        self.assertEqual(migrated["max_total_task_seconds"], 0)
        self.assertFalse(migrated["preserve_current_task_tool_context"])
        self.assertEqual(migrated["codex_request_timeout_seconds"], 1800)
        self.assertTrue(migrated["allow_unlimited_agent_evaluations"])
        self.assertEqual(migrated["long_task_defaults_version"], 1)

    def test_custom_task_limits_are_preserved_during_long_task_migration(self):
        loaded = {
            "settings_schema_version": 2,
            "max_agent_loops": 9,
            "max_total_task_seconds": 7200,
            "preserve_current_task_tool_context": False,
        }

        migrated, changed = self.manager.migrate_or_merge(loaded)

        self.assertTrue(changed)
        self.assertEqual(migrated["max_agent_loops"], 9)
        self.assertEqual(migrated["max_total_task_seconds"], 7200)
        self.assertFalse(migrated["preserve_current_task_tool_context"])

    def test_completed_long_task_migration_is_idempotent(self):
        loaded = {
            "settings_schema_version": 2,
            "long_task_defaults_version": 1,
            "ssl_trust_migration_version": 1,
            "ssl_trust_mode": "system",
            "allow_insecure_ssl_compat": False,
            "max_agent_loops": 15,
            "max_total_task_seconds": 3600,
            "preserve_current_task_tool_context": True,
            "allow_unlimited_agent_evaluations": True,
            "model_selection_provenance_version": DEFAULT_SETTINGS[
                "model_selection_provenance_version"
            ],
            "selected_model_source": dict(DEFAULT_SETTINGS["selected_model_source"]),
        }

        migrated, changed = self.manager.migrate_or_merge(loaded)

        self.assertFalse(changed)
        self.assertEqual(migrated["max_agent_loops"], 15)
        self.assertEqual(migrated["max_total_task_seconds"], 3600)
        self.assertTrue(migrated["preserve_current_task_tool_context"])
        self.assertTrue(migrated["allow_unlimited_agent_evaluations"])

    def test_obsolete_character_and_message_compaction_limits_are_removed(self):
        loaded = {
            "settings_schema_version": 2,
            "long_task_defaults_version": 1,
            "agent_context_compact_after_loops": 4,
            "agent_inline_history_message_limit": 24,
            "agent_inline_history_chars": 52000,
            "conversation_history_limit": 16,
        }

        migrated, changed = self.manager.migrate_or_merge(loaded)

        self.assertTrue(changed)
        self.assertNotIn("agent_context_compact_after_loops", migrated)
        self.assertNotIn("agent_inline_history_message_limit", migrated)
        self.assertNotIn("agent_inline_history_chars", migrated)
        self.assertNotIn("conversation_history_limit", migrated)

    @staticmethod
    def _context_compaction_core(window=8192):
        core = SmartiCore.__new__(SmartiCore)
        core.mode = "openai_codex_signin"
        core.settings = dict(DEFAULT_SETTINGS)
        core.settings["agent_model_context_window_tokens"] = window
        core.settings["agent_context_compaction_trigger_ratio"] = 0.50
        core.settings["agent_context_compaction_target_ratio"] = 0.30
        core.settings["agent_context_recent_fraction"] = 0.10
        core.system_prompt = "system"
        core.status_callback = None
        core.agent_runtime = None
        core._task_state_summary = mock.Mock(return_value="stable task summary")
        core._generate_context_compaction_summary = mock.Mock(
            return_value="USER REQUIREMENTS\n- Preserve every requested detail.\n\nREMAINING WORK\n- Continue the task."
        )
        core._emit_agent_process_event = mock.Mock()
        return core

    def test_default_model_window_does_not_compact_at_the_old_character_limit(self):
        core = self._context_compaction_core(window=1_050_000)
        messages = [{"role": "system", "content": "system"}]
        messages.extend(
            {"role": "user", "content": f"tool result {index} " + ("x" * 2500)}
            for index in range(30)
        )
        task_state = {"planner_enabled": True}
        original = list(messages)

        compacted = core._compact_current_messages_if_needed(messages, task_state, iteration=50)

        self.assertFalse(compacted)
        self.assertEqual(messages, original)
        core._generate_context_compaction_summary.assert_not_called()

    def test_current_openai_model_windows_are_model_aware(self):
        core = self._context_compaction_core(window=0)

        self.assertEqual(core._model_context_window_tokens("gpt-5.6-sol"), 1_050_000)
        self.assertEqual(core._model_context_window_tokens("gpt-5.4-mini"), 400_000)

    def test_tool_feedback_is_not_cut_at_an_arbitrary_character_limit(self):
        core = self._context_compaction_core()
        feedback = "prefix\n" + ("important-middle-detail\n" * 1500) + "suffix"

        compacted = core._compact_tool_feedback_for_model("email_manager", feedback)

        self.assertEqual(compacted, feedback)
        self.assertNotIn("SMARTI_TOOL_OUTPUT_COMPACTED", compacted)

    def test_oversized_summary_source_is_compacted_hierarchically(self):
        core = self._context_compaction_core()
        del core._generate_context_compaction_summary
        core._handle_api_request_with_retry = mock.Mock(
            return_value=("USER REQUIREMENTS\n- retained chunk facts", {"prompt": 1, "completion": 1, "total": 2})
        )
        core._log_usage = mock.Mock()
        messages = [{"role": "user", "content": "small-detail-123\n" + ("x" * 50000)}]

        summary = core._generate_context_compaction_summary(
            messages,
            {"planner_enabled": False},
            "gpt-test",
        )

        self.assertIn("retained chunk facts", summary)
        self.assertGreater(core._handle_api_request_with_retry.call_count, 1)

    def test_token_pressure_compacts_and_preserves_the_current_user_message(self):
        core = self._context_compaction_core()
        current_user = {"role": "user", "content": "Keep this current request exactly: 123 / C:\\work\\item.txt"}
        messages = [{"role": "system", "content": "system"}]
        messages.extend(
            {"role": "user", "content": f"old tool result {index} " + ("x" * 2500)}
            for index in range(12)
        )
        messages.append(current_user)
        messages.extend(
            {"role": "user", "content": f"recent feedback {index} " + ("y" * 900)}
            for index in range(3)
        )
        task_state = {"planner_enabled": True}

        compacted = core._compact_current_messages_if_needed(
            messages,
            task_state,
            iteration=1,
            protected_user_message=current_user,
        )

        self.assertTrue(compacted)
        self.assertEqual(task_state["compactions"], 1)
        self.assertIn(current_user, messages)
        self.assertEqual(
            next(message for message in messages if message == current_user)["content"],
            current_user["content"],
        )
        self.assertIn("SMARTI_CONTEXT_COMPACTION_BEGIN", messages[1]["content"])
        event_types = [call.args[0] for call in core._emit_agent_process_event.call_args_list]
        self.assertEqual(event_types, ["tool_group_start", "tool_group_finish"])
        start_tool = core._emit_agent_process_event.call_args_list[0].kwargs["group"]
        self.assertEqual(start_tool["action"], "context_compaction")

    def test_provider_overflow_forces_compaction_when_local_window_estimate_is_too_large(self):
        core = self._context_compaction_core(window=1_050_000)
        current_user = {"role": "user", "content": "current request stays exact"}
        messages = [{"role": "system", "content": "system"}]
        messages.extend(
            {"role": "user", "content": f"old result {index} " + ("x" * 2500)}
            for index in range(20)
        )
        messages.append(current_user)

        compacted = core._compact_current_messages_if_needed(
            messages,
            {"planner_enabled": True},
            current_model="unknown-model",
            protected_user_message=current_user,
            force=True,
            reason="provider_context_limit",
        )

        self.assertTrue(compacted)
        self.assertIn(current_user, messages)

    def test_compaction_retains_a_loaded_tool_schema(self):
        core = self._context_compaction_core()
        messages = [{"role": "system", "content": "system"}]
        messages.extend(
            {"role": "user", "content": f"tool result {index} " + ("x" * 2500)}
            for index in range(30)
        )
        task_state = {
            "planner_enabled": True,
            "loaded_tool_schemas": {
                "email_manager": "EMAIL SCHEMA: search, read, uids, save_attachments",
            },
        }

        compacted = core._compact_current_messages_if_needed(messages, task_state, iteration=1)

        self.assertTrue(compacted)
        self.assertIn("SMARTI_RETAINED_TOOL_SCHEMAS_BEGIN", messages[1]["content"])
        self.assertIn("EMAIL SCHEMA: search, read, uids, save_attachments", messages[1]["content"])

    def test_conversation_history_is_not_trimmed_by_message_count(self):
        core = self._context_compaction_core(window=1_050_000)
        core.universal_history = [{"role": "system", "content": "system"}] + [
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"message {index}"}
            for index in range(40)
        ]
        original = list(core.universal_history)

        compacted = core._compact_conversation_history(current_model="gpt-5.4")

        self.assertFalse(compacted)
        self.assertEqual(core.universal_history, original)
        core._generate_context_compaction_summary.assert_not_called()

    def test_conversation_history_compacts_under_pressure_and_keeps_latest_turn(self):
        core = self._context_compaction_core()
        core._save_settings = mock.Mock()
        history = [{"role": "system", "content": "system"}]
        history.extend(
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"old message {index} " + ("x" * 1800)}
            for index in range(14)
        )
        latest_user = {"role": "user", "content": "latest user request in full"}
        latest_assistant = {"role": "assistant", "content": "latest assistant answer in full"}
        history.extend([latest_user, latest_assistant])
        core.universal_history = history

        compacted = core._compact_conversation_history(current_model="gpt-5.4")

        self.assertTrue(compacted)
        self.assertEqual(core.settings["conversation_summary"], core._generate_context_compaction_summary.return_value)
        self.assertIn(latest_user, core.universal_history)
        self.assertIn(latest_assistant, core.universal_history)


class AgentToolLoopRegressionTests(unittest.TestCase):
    def setUp(self):
        self.core = SmartiCore.__new__(SmartiCore)
        self.core.settings = {}
        self.core.agent_runtime = AgentRuntime(self.core)

    def test_distinct_email_uids_are_not_blocked_as_similar_repeats(self):
        counts = {}
        signatures = []

        feedback = [
            self.core._reserve_tool_call(
                {"action": "email_manager", "arguments": {"action": "read", "mailbox": "INBOX", "uid": uid}},
                counts,
                signatures,
            )
            for uid in ("10568", "10566", "10565", "10561")
        ]

        self.assertEqual(feedback, [None, None, None, None])

    def test_identical_safe_read_is_blocked_only_as_an_emergency_loop(self):
        counts = {}
        signatures = []
        call = {"action": "email_manager", "arguments": {"action": "read", "mailbox": "INBOX", "uid": "10568"}}

        feedback = [self.core._reserve_tool_call(call, counts, signatures) for _ in range(9)]

        self.assertEqual(feedback[:8], [None] * 8)
        self.assertIn("Abnormal repeated identical", feedback[8])

    def test_identical_side_effecting_call_remains_strictly_bounded(self):
        counts = {}
        signatures = []
        call = {"action": "email_manager", "arguments": {"action": "send", "to": "a@example.com", "subject": "x", "body": "y"}}

        self.assertIsNone(self.core._reserve_tool_call(call, counts, signatures))
        self.assertIsNone(self.core._reserve_tool_call(call, counts, signatures))
        self.assertIn("Abnormal repeated", self.core._reserve_tool_call(call, counts, signatures))

    def test_schema_can_be_reloaded_after_context_compaction(self):
        counts = {}
        signatures = []
        call = {"action": "get_tool_info", "arguments": {"tool_name": "email_manager"}}

        feedback = [self.core._reserve_tool_call(call, counts, signatures) for _ in range(3)]

        self.assertEqual(feedback, [None, None, None])

    def test_read_only_email_calls_are_safe_for_model_directed_retries(self):
        self.assertFalse(self.core._tool_is_mutating_or_control("email_manager", {"action": "search"}))
        self.assertFalse(self.core._tool_is_mutating_or_control("email_manager", {"action": "read"}))
        self.assertTrue(self.core._tool_is_mutating_or_control("email_manager", {"action": "send"}))
        self.assertTrue(self.core._tool_is_mutating_or_control("email_manager", {"action": "save_attachments"}))

    def test_progress_evaluator_is_not_scheduled_without_model_request(self):
        self.core._trace_agent_phase = mock.Mock()
        self.core._handle_api_request_with_retry = mock.Mock(side_effect=AssertionError("must not run"))

        result = self.core._maybe_evaluate_task_progress(
            {"planner_enabled": True},
            [{"action": "email_manager", "status": "ok", "arguments": {"action": "read"}}],
            "model",
            4,
        )

        self.assertEqual(result, "")
        self.core._handle_api_request_with_retry.assert_not_called()

    def test_successful_schema_result_is_retained_in_task_state(self):
        task_state = {"observations": [], "loaded_tool_schemas": {}}

        self.core._record_results_in_task_state(task_state, [{
            "action": "get_tool_info",
            "arguments": {"tool_name": "email_manager"},
            "status": "ok",
            "output": "EMAIL SCHEMA BODY",
        }])

        self.assertEqual(task_state["loaded_tool_schemas"]["email_manager"], "EMAIL SCHEMA BODY")

    @unittest.skipUnless(os.name == "nt", "Windows execution state is Windows-specific")
    def test_active_task_sleep_prevention_is_scoped_and_released(self):
        core = SmartiCore.__new__(SmartiCore)
        with mock.patch(
            "smarti.agent.execution_policy.ctypes.windll.kernel32.SetThreadExecutionState",
            return_value=1,
        ) as set_execution_state:
            self.assertTrue(core._set_system_sleep_prevention(True))
            self.assertFalse(core._set_system_sleep_prevention(False))

        self.assertEqual(
            [call.args[0] for call in set_execution_state.call_args_list],
            [0x80000001, 0x80000000],
        )


class AgentReportTests(unittest.TestCase):
    def setUp(self):
        self.core = SmartiCore.__new__(SmartiCore)

    def test_first_agent_report_is_allowed(self):
        report = self.core._should_emit_agent_report("סטטוס: אני בודק את הקבצים הרלוונטיים.")

        self.assertEqual(report, "אני בודק את הקבצים הרלוונטיים.")

    def test_duplicate_agent_report_is_suppressed(self):
        report = self.core._should_emit_agent_report(
            "אני בודק את הקבצים הרלוונטיים עכשיו.",
            last_report="אני בודק את הקבצים הרלוונטיים עכשיו",
        )

        self.assertEqual(report, "")

    def test_distinct_agent_report_is_allowed_after_a_previous_report(self):
        report = self.core._should_emit_agent_report(
            "מצאתי את אזור הקוד הרלוונטי, ועכשיו אני בודק את הלוגים מולו.",
            last_report="אני בודק את הקבצים הרלוונטיים.",
        )

        self.assertEqual(report, "מצאתי את אזור הקוד הרלוונטי, ועכשיו אני בודק את הלוגים מולו.")

    def test_first_tool_turn_without_model_report_gets_a_fallback(self):
        report, source = self.core._select_agent_report_for_tool_turn(
            "",
            [{"action": "internet_search", "arguments": {"query": "example"}}],
            report_count=0,
        )

        self.assertTrue(report)
        self.assertEqual(source, "fallback")

    def test_later_tool_turn_without_model_report_does_not_force_fallback(self):
        report, source = self.core._select_agent_report_for_tool_turn(
            "",
            [{"action": "internet_search", "arguments": {"query": "example"}}],
            last_report="Checking current information.",
            report_count=1,
        )

        self.assertEqual(report, "")
        self.assertEqual(source, "")

    def test_later_tool_turn_with_useful_model_report_is_allowed(self):
        report, source = self.core._select_agent_report_for_tool_turn(
            "I found the relevant area and am checking the logs against it.",
            [{"action": "smart_file_search", "arguments": {"query": "logs"}}],
            last_report="Checking the relevant files.",
            report_count=1,
        )

        self.assertEqual(report, "I found the relevant area and am checking the logs against it.")
        self.assertEqual(source, "model")


if __name__ == "__main__":
    unittest.main()
