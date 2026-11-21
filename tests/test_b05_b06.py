"""Offline tests for B05: digest deadline and deterministic git-stat summary."""
import http.server
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unittest.mock import patch
from tandem_mcp import digest, engine  # noqa: E402


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


if __name__ == '__main__':
    unittest.main(verbosity=2)
