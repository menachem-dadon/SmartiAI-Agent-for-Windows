"""Cache the growing conversation without modifying its content or provider routing."""
import copy
import json
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from smarti.prompt_cache import openai_cache_controls, remove_openai_cache_controls, cache_usage_metrics
from tests.test_api_provider_runtime import RequestCore


class PromptCacheTests(unittest.TestCase):
    def test_reused_prefix_contains_complete_browser_history_on_both_openai_endpoints(self):
        messages = [{'role': 'system', 'content': 'small stable system'},
                    {'role': 'user', 'content': 'read the full article'},
                    {'role': 'assistant', 'content': 'requested snapshot'},
                    {'role': 'user', 'content': 'UNTRUSTED_TOOL_OUTPUT ' + 'important prose ' * 4000}]
        original = copy.deepcopy(messages)
        for model in ('gpt-5.6-sol', 'gpt-6-astra', 'gpt-6.1-sol'):
            for field in ('messages', 'input'):
                first = {field: messages}
                openai_cache_controls(first, model, 'agent', 'run-a', message_field=field)
                grown = messages + [{'role': 'assistant', 'content': 'next action'},
                                    {'role': 'user', 'content': 'UNTRUSTED_TOOL_OUTPUT next snapshot'}]
                second = {field: grown}
                openai_cache_controls(second, model, 'agent', 'run-a', message_field=field)
                self.assertEqual(first[field], second[field][:len(messages)])
                self.assertEqual(first[field][-1]['content'][0]['text'], messages[-1]['content'])
                self.assertIn('prompt_cache_breakpoint', first[field][-1]['content'][0])
                self.assertEqual(first['extra_body'], {'prompt_cache_options': {'mode': 'implicit'}})
                self.assertEqual(first['prompt_cache_key'], second['prompt_cache_key'])
        self.assertEqual(messages, original)

    def test_no_paid_write_for_standalone_summary_and_old_models_keep_native_cache(self):
        options = {'messages': [{'role': 'user', 'content': 'title'}]}
        openai_cache_controls(options, 'gpt-6.1-sol', 'title', 'run-a')
        self.assertEqual(options['extra_body'], {'prompt_cache_options': {'mode': 'explicit'}})
        self.assertNotIn('prompt_cache_breakpoint', json.dumps(options))
        older = {'messages': [{'role': 'user', 'content': 'article'}]}
        openai_cache_controls(older, 'gpt-5.4', 'agent', 'run-a')
        self.assertNotIn('extra_body', older)
        self.assertEqual(older['prompt_cache_key'], 'smarti:run-a')

    def test_unsupported_cache_fallback_retains_text_and_images(self):
        source = [{'role': 'system', 'content': 'rules'}, {'role': 'user', 'content': [
            {'type': 'text', 'text': 'UNTRUSTED_TOOL_OUTPUT complete text'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,aW1hZ2U='}}]}]
        options = {'messages': copy.deepcopy(source)}
        openai_cache_controls(options, 'gpt-6.1-sol', 'agent', 'run-a')
        remove_openai_cache_controls(options)
        self.assertNotIn('prompt_cache_breakpoint', json.dumps(options))
        self.assertEqual(options['messages'][1], source[1])
        self.assertEqual(options['messages'][0]['content'][0]['text'], 'rules')
        self.assertNotIn('prompt_cache_key', options)

    def test_counts_are_weighted_by_tokens_and_writes_are_separate_from_hits(self):
        totals = {}
        cache_usage_metrics({'prompt': 100, 'cached_prompt': 0, 'cache_write_prompt': 80}, totals)
        metric = cache_usage_metrics({'prompt': 900, 'cached_prompt': 850, 'completion': 10}, totals)
        self.assertEqual(metric['sequence_hit_percent'], 85)
        self.assertEqual(metric['sequence'], {'prompt': 1000, 'cached': 850, 'written': 80, 'uncached': 70, 'completion': 10, 'requests': 2})

    def test_live_request_metrics_are_content_free_and_reset_for_a_different_run(self):
        core = RequestCore('openai')
        core._execution_context = SimpleNamespace(current_task_id='run-a')
        with mock.patch('smarti.agent.model_context.logging.info') as logger:
            for index in range(2):
                core._log_api_request_success(str(index), 'openai', 'gpt-6.1-sol', 'agent', 1, time.monotonic(),
                    ('private answer', {'prompt': 100, 'cached_prompt': index * 90}))
            self.assertEqual(core._execution_context.cache_measurement[1]['cached'], 90)
            self.assertEqual(core._execution_context.cache_measurement[1]['requests'], 2)
            self.assertNotIn('private answer', str(logger.call_args_list))
            core._execution_context.current_task_id = 'run-b'
            core._log_api_request_success('3', 'openai', 'gpt-6.1-sol', 'agent', 1, time.monotonic(), ('answer', {'prompt': 10}))
            self.assertEqual(core._execution_context.cache_measurement[1]['requests'], 1)

    def test_responses_endpoint_sends_cache_boundaries_and_keeps_usage_on_fallback(self):
        core = RequestCore('openai')
        core._execution_context = SimpleNamespace(current_task_id='response-run')
        received = []
        def create(**kwargs):
            received.append(copy.deepcopy(kwargs))
            if len(received) == 1:
                raise TypeError('unexpected prompt_cache_options parameter')
            return {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'done'}]}],
                    'usage': {'input_tokens': 100, 'output_tokens': 2, 'total_tokens': 102,
                              'input_tokens_details': {'cached_tokens': 80, 'cache_write_tokens': 10}}}
        core.universal_client = SimpleNamespace(responses=SimpleNamespace(create=create))
        core._native_tool_specs_for_request = lambda: [{'name': 'snapshot', 'description': 'inspect', 'parameters': {'type': 'object'}}]
        messages = [{'role': 'system', 'content': 'rules'}, {'role': 'user', 'content': 'UNTRUSTED_TOOL_OUTPUT article'}]
        _, usage = core._handle_api_request_with_retry('gpt-6-sol', messages, retry_wait_times=[])
        # This model uses Responses with its native reasoning contract.
        self.assertEqual(len(received), 2)
        self.assertEqual(received[0]['extra_body'], {'prompt_cache_options': {'mode': 'implicit'}})
        self.assertIn('prompt_cache_breakpoint', received[0]['input'][-1]['content'][0])
        self.assertNotIn('prompt_cache_breakpoint', json.dumps(received[1]['input']))
        self.assertEqual(usage['cached_prompt'], 80)
        self.assertEqual(usage['cache_write_prompt'], 10)
