"""Offline tests for B05 (digest deadline & deterministic git-stat) and B06 (selective routing)."""
import http.server
import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
H_DIR = ROOT / 'benchmarks' / 'hydrogen_3_6_1'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(H_DIR) not in sys.path:
    sys.path.insert(0, str(H_DIR))

from unittest.mock import patch
from tandem_mcp import digest, engine  # noqa: E402

spec = importlib.util.spec_from_file_location('hydrogen_suite', H_DIR / 'suite.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)


class _SlowHandler(http.server.BaseHTTPRequestHandler):
    request_count = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.endswith('/models'):
            body = json.dumps({'data': [{'id': 'slow-model'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        _SlowHandler.request_count += 1
        time.sleep(3.0)
        body = json.dumps({'choices': [{'message': {'content': '{"answer":"late","evidence":[]}'}}]}).encode()
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except BrokenPipeError:
            pass


class B05Tests(unittest.TestCase):
    def test_slow_server_times_out_within_deadline_without_residual_requests(self):
        _SlowHandler.request_count = 0
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _SlowHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            url = f'http://127.0.0.1:{srv.server_address[1]}/v1'
            engine.connect(url=url)
            t0 = time.monotonic()
            with patch.object(engine, 'caps', return_value={'tools': False, 'schema': False, 'context': 8192}):
                with self.assertRaises(engine.ExecutorError):
                    digest.answer('line1\nline2\n', 'What is in line1?', model='slow-model', cache=False, timeout=0.8)
            elapsed = time.monotonic() - t0
            self.assertLess(elapsed, 2.5)
            # Only 1 request should have been sent (no retries after deadline)
            self.assertEqual(_SlowHandler.request_count, 1)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_deterministic_git_stat_with_ties_and_repeated_files_in_commit(self):
        log = '\n'.join([
            'commit aaaaaa1',
            '    src/a.py | 4 ++--',
            '    src/a.py | 2 +-',
            '    src/b.py | 3 ++-',
            'commit bbbbbb2',
            '    src/a.py | 1 +',
            '    src/c.py | 5 +++++',
            'commit cccccc3',
            '    src/b.py | 2 ++',
            '    src/c.py | 1 -',
        ])
        res = digest.deterministic_git_stat_summary(log)
        self.assertIsNotNone(res)
        # a.py appeared in 2 commits (repeated twice in commit 1 counts once), b.py in 2, c.py in 2 -> 3-way tie at 2
        self.assertEqual(res['groups'][0]['count'], 2)
        self.assertEqual(res['groups'][0]['files'], ['src/a.py', 'src/b.py', 'src/c.py'])


class B06SelectiveRoutingTests(unittest.TestCase):
    def test_selective_routing_and_explicit_override(self):
        # Structured extraction -> direct_parse (not delegated)
        r_ext = suite.recommend_route('extraction', 1200, 1, '.toml')
        self.assertFalse(r_ext['delegated'])
        self.assertEqual(r_ext['route'], 'direct_parse')

        # Small reading -> direct_focused
        r_small = suite.recommend_route('reading', 18000, 1, '.py')
        self.assertFalse(r_small['delegated'])
        self.assertEqual(r_small['route'], 'direct_focused')

        # Large reading (85 KB log) -> tandem_digest
        r_big = suite.recommend_route('reading', 85000, 1, '.txt')
        self.assertTrue(r_big['delegated'])
        self.assertEqual(r_big['route'], 'tandem_digest')

        # Explicit user choice preserved
        r_exp = suite.recommend_route('extraction', 1200, 1, '.toml', explicit_mode='tandem')
        self.assertTrue(r_exp['delegated'])
        self.assertEqual(r_exp['route'], 'tandem')

    def test_held_out_unseen_cases(self):
        # Unseen large multi-file refactor with strong checks -> delegated
        r_ref = suite.recommend_route('refactor', 42000, 10, '.py', has_strong_checks=True)
        self.assertTrue(r_ref['delegated'])
        # Unseen small JSON config -> direct_parse
        r_json = suite.recommend_route('reading', 2400, 1, '.json')
        self.assertFalse(r_json['delegated'])
        # Unseen 3-way execution plan includes selective
        plan = suite.build_execution_plan(suite.TASKS[:2], repeats=1, scenarios=('direct', 'tandem', 'selective'))
        self.assertEqual({p['scenario'] for p in plan}, {'direct', 'tandem', 'selective'})

    def test_direct_parse_and_direct_route_and_fallback_accounting(self):
        import json
        import tempfile
        from unittest.mock import MagicMock, patch

        ext_task = next(t for t in suite.TASKS if t['id'] == 'extraction_manifest')
        git_task = next(t for t in suite.TASKS if t['id'] == 'reading_git_log')

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            # 1. direct_parse succeeds deterministically without invoking cloud client
            with patch.object(suite.subprocess, 'Popen') as mock_popen:
                res_parse = suite.run_attempt(ext_task, 'selective', 1, run_dir)
                mock_popen.assert_not_called()
            self.assertTrue(res_parse['e2e_success'])
            self.assertEqual(res_parse['effective_scenario'], 'direct_parse')
            self.assertEqual(res_parse['executed_route'], 'direct_parse')
            self.assertEqual(res_parse['route_steps'], ['direct_parse'])
            self.assertFalse(res_parse['fallback_used'])
            self.assertEqual(res_parse['cloud_usage']['total_tokens'], 0)

            # 2. direct_focused records executed_route as 'direct'
            git_stdout = json.dumps({
                'status': 'SUCCESS',
                'response': 'README.md (13 commits), tests/test_offline.py (12 commits), tandem_mcp/sandbox.py (7 commits).',
                'usage': {'input_tokens': 400, 'output_tokens': 50, 'total_tokens': 450},
            })
            proc_git = MagicMock()
            proc_git.communicate.return_value = (git_stdout, '')
            proc_git.returncode = 0
            with patch.object(suite, 'set_tandem_mcp'), patch.object(suite.subprocess, 'Popen', return_value=proc_git):
                res_git = suite.run_attempt(git_task, 'selective', 1, run_dir)
            self.assertTrue(res_git['e2e_success'])
            self.assertEqual(res_git['effective_scenario'], 'direct')
            self.assertEqual(res_git['executed_route'], 'direct')
            self.assertEqual(res_git['route_steps'], ['direct'])
            self.assertFalse(res_git['fallback_used'])

            # 3. Fallback from direct_parse to direct records both steps and full cloud cost
            fb_stdout = json.dumps({
                'status': 'SUCCESS',
                'response': json.dumps({
                    'name': 'tandem-mcp',
                    'requires_python': '>=3.11',
                    'dependencies': ['mcp>=2.3', 'openai>=1.40'],
                    'console_script': 'tandem-mcp = tandem_mcp.server:main',
                }),
                'usage': {'input_tokens': 500, 'output_tokens': 80, 'total_tokens': 580},
            })
            proc_fb = MagicMock()
            proc_fb.communicate.return_value = (fb_stdout, '')
            proc_fb.returncode = 0
            with patch.object(suite, 'set_tandem_mcp'), \
                 patch.object(suite, 'deterministic_parse_manifest', side_effect=ValueError('corrupt toml')), \
                 patch.object(suite.subprocess, 'Popen', return_value=proc_fb):
                res_fb = suite.run_attempt(ext_task, 'selective', 2, run_dir)
            self.assertTrue(res_fb['e2e_success'])
            self.assertEqual(res_fb['effective_scenario'], 'direct')
            self.assertEqual(res_fb['route_steps'], ['direct_parse', 'direct'])
            self.assertTrue(res_fb['fallback_used'])
            self.assertEqual(res_fb['cloud_usage']['total_tokens'], 580)


if __name__ == '__main__':
    unittest.main(verbosity=2)
