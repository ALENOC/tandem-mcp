import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('benchmark_adapters', Path(__file__).resolve().parents[1] / 'benchmarks/comparative_3_6_1/orchestrators.py')
adapters = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapters)


class AdapterTests(unittest.TestCase):
    def test_event_usage_and_answer(self):
        events = [dict(type='item.completed', item=dict(type='agent_message', text='answer')),
                  dict(type='turn.completed', usage=dict(input_tokens=100, output_tokens=20, cached_input_tokens=50))]
        result = adapters.parse_output({'cli': 'codex'}, '\n'.join(map(json.dumps, events)))
        self.assertEqual(result['response'], 'answer')
        self.assertEqual(result['usage']['input_tokens'], 100)
        self.assertEqual(result['usage']['cache_read_tokens'], 50)
        self.assertEqual(result['status'], 'COMPLETED')

    def test_missing_usage_is_not_zero(self):
        result = adapters.parse_output({'cli': 'codex'}, '{"type":"turn.completed"}')
        self.assertIsNone(result['usage'])

    def test_failure_is_not_completion(self):
        result = adapters.parse_output({'cli': 'codex'}, '{"type":"turn.failed"}')
        self.assertEqual(result['status'], 'FAILED')

    def test_process_local_server_isolation(self):
        config = dict(cli='codex', model_id='arbitrary-model')
        servers = json.dumps([dict(name='tandem-mcp', transport=dict(type='stdio', command='/bin/python', args=[])), dict(name='unrelated')])
        env = {k: 'value' for k in ('TANDEM_HOME', 'TANDEM_BASE_URL', 'TANDEM_MODEL', 'TANDEM_TIMEOUT')}
        with patch.object(adapters.subprocess, 'check_output', return_value=servers):
            direct = adapters.command(config, 'task', 20, 'direct', env)
            tandem = adapters.command(config, 'task', 20, 'tandem', env)
        self.assertIn('arbitrary-model', direct)
        self.assertIn('mcp_servers={}', direct)
        self.assertIn('mcp_servers.tandem-mcp.enabled=true', tandem)
        self.assertIn('mcp_servers={}', tandem)

    def test_legacy_alias(self):
        self.assertEqual(adapters.neutral_scenario('gemini_tandem'), 'tandem')
        self.assertEqual(adapters.legacy_scenario('direct'), 'gemini_direct')


class QuotaTests(unittest.TestCase):
    def test_quota_error_is_retryable(self):
        self.assertTrue(adapters.quota_exhausted('{"error":{"code":"usage_limit_reached"}}'))

    def test_task_failure_is_not_quota(self):
        self.assertFalse(adapters.quota_exhausted('test failed: expected 5, got 6'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
