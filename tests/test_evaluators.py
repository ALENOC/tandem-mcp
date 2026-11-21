"""Regression tests for B01 (meaningful PASS) and B03 (independent web evaluation)."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
H_EVAL_PATH = ROOT / 'benchmarks' / 'hydrogen_3_6_1' / 'evaluate.py'
C_EVAL_PATH = ROOT / 'benchmarks' / 'comparative_3_6_1' / 'evaluate.py'
C_FIXTURES = ROOT / 'benchmarks' / 'comparative_3_6_1' / 'fixtures'
H_WS_ROOT = ROOT / 'benchmarks' / 'hydrogen_3_6_1' / 'runs' / '20261118-051116' / 'workspaces'


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


h_eval = _load('hydrogen_evaluate', H_EVAL_PATH)
c_eval = _load('comparative_evaluate', C_EVAL_PATH)


class B01EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_package_survey_rejects_names_only_timeout_and_swapped_roles(self):
        names_only = 'agent digest engine sandbox server store'
        res = h_eval.evaluate_attempt('reading_package_survey', names_only, self.ws)
        self.assertFalse(res['valid'])

        timed_out = (
            'I am unable to complete the request because digest_many timed out after 3m0s: '
            'context deadline exceeded. Modules: agent.py digest.py engine.py sandbox.py server.py store.py'
        )
        res_to = h_eval.evaluate_attempt('reading_package_survey', timed_out, self.ws)
        self.assertFalse(res_to['valid'])

        swapped = '\n'.join([
            '- agent.py: Exposes FastMCP server tools and formats ledger_report.',
            '- digest.py: Persists JSONL ledger and lesson files to disk.',
            '- engine.py: Enforces bubblewrap jail and path allowlists.',
            '- sandbox.py: Streams OpenAI HTTP completions from LM Studio.',
            '- server.py: Runs the executor tool-calling loop and snapshot rollback.',
            '- store.py: Reads and greps files into compact digests.',
        ])
        res_sw = h_eval.evaluate_attempt('reading_package_survey', swapped, self.ws)
        self.assertFalse(res_sw['valid'])

        valid_alt = '\n'.join([
            '1. agent.py - Drives the local executor loop, snapshots, and rollback.',
            '2. digest.py - Reads and extracts file or command digests with grep.',
            '3. engine.py - Connects to the OpenAI-compatible LLM endpoint with retries.',
            '4. sandbox.py - Confines workspace paths, command allowlists, and bwrap jail.',
            '5. server.py - Implements the MCP server tools, contracts, and lean receipts.',
            '6. store.py - Handles JSON/JSONL persistence for jobs, ledger, and lessons.',
        ])
        res_ok = h_eval.evaluate_attempt('reading_package_survey', valid_alt, self.ws)
        self.assertTrue(res_ok['valid'], res_ok)
        self.assertIn('requirements', res_ok['details'])
        self.assertEqual(res_ok['details']['requirements']['agent']['status'], 'passed')

    def test_rollback_rejects_negation_and_accepts_valid_paraphrase(self):
        negated = 'rollback does not skip unbacked files and does not restore blobs.'
        self.assertFalse(h_eval.evaluate_attempt('reading_agent_rollback', negated, self.ws)['valid'])

        valid_alt = (
            'If snapshot[rel] is None, the file had no backup (unbacked) and rollback leaves it untouched (skipped). '
            'If snapshot[rel] is a string path, rollback decompresses the gzip backup blob and restores the file.'
        )
        res = h_eval.evaluate_attempt('reading_agent_rollback', valid_alt, self.ws)
        self.assertTrue(res['valid'], res)
        self.assertEqual(res['details']['requirements']['none_unbacked']['status'], 'passed')
        self.assertEqual(res['details']['requirements']['string_restore']['status'], 'passed')

    def test_manifest_rejects_string_deps_extra_deps_and_bad_script(self):
        bad_str = json.dumps({
            'name': 'tandem-mcp',
            'requires_python': '>=3.11',
            'dependencies': 'mcp>=2.3 openai>=1.40 extra-pkg',
            'console_script': 'not-tandem-mcp',
        })
        self.assertFalse(h_eval.evaluate_attempt('extraction_manifest', bad_str, self.ws)['valid'])

        extra_dep = json.dumps({
            'name': 'tandem-mcp',
            'requires_python': '>=3.11',
            'dependencies': ['mcp>=2.3', 'openai>=1.40', 'pytest'],
            'console_script': 'tandem_mcp.server:main',
        })
        self.assertFalse(h_eval.evaluate_attempt('extraction_manifest', extra_dep, self.ws)['valid'])

        valid = json.dumps({
            'name': 'tandem-mcp',
            'requires_python': '>=3.11',
            'dependencies': ['openai>=1.40', 'mcp>=2.3'],
            'console_script': 'tandem-mcp = tandem_mcp.server:main',
        })
        res = h_eval.evaluate_attempt('extraction_manifest', valid, self.ws)
        self.assertTrue(res['valid'], res)

    def test_git_log_requires_all_three_and_exact_counts(self):
        two_only = 'Top files: README.md (13 commits), tests/test_offline.py (12 commits).'
        self.assertFalse(h_eval.evaluate_attempt('reading_git_log', two_only, self.ws)['valid'])

        wrong_counts = (
            '1. README.md (10 commits)\n'
            '2. tests/test_offline.py (12 commits)\n'
            '3. tandem_mcp/sandbox.py (7 commits)\n'
        )
        self.assertFalse(h_eval.evaluate_attempt('reading_git_log', wrong_counts, self.ws)['valid'])

        valid_alt = (
            'Most modified: README.md appeared in 13 commits, tests/test_offline.py in 12 commits, '
            'and tandem_mcp/sandbox.py in 7 commits.'
        )
        res = h_eval.evaluate_attempt('reading_git_log', valid_alt, self.ws)
        self.assertTrue(res['valid'], res)

    def test_incident_log_requires_full_hh_mm_ss(self):
        minutes_only = 'payments-db failed at 02:14 due to disk full (100%), resolved at 03:41.'
        self.assertFalse(h_eval.evaluate_attempt('reading_incident_log', minutes_only, self.ws)['valid'])

        full_ts = 'payments-db failed first at 02:14:07 because of No space left on device, resolved at 03:41:00.'
        res = h_eval.evaluate_attempt('reading_incident_log', full_ts, self.ws)
        self.assertTrue(res['valid'], res)


class B03WebEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_missing_browser_is_not_evaluated_and_prevents_pass(self):
        if not (H_WS_ROOT / 'gen_orbital__direct__r1').exists():
            self.skipTest('saved 20261118-051116 workspace not present')
        shutil.copytree(H_WS_ROOT / 'gen_orbital__direct__r1', self.ws / 'orb')
        with patch.dict(os.environ, {'TANDEM_DISABLE_BROWSER': '1'}):
            h_res = h_eval.evaluate_attempt('gen_orbital', '', self.ws / 'orb')
            self.assertFalse(h_res['valid'])
            self.assertEqual(h_res['details']['requirements']['browser']['status'], 'not_evaluated')

            if C_FIXTURES.exists():
                c_res = c_eval.eval_gen_orbital(self.ws / 'orb', C_FIXTURES)
                self.assertFalse(c_res['passed'])
                self.assertEqual(c_res['status'], 'not_evaluated')

    def test_tampered_checker_is_overwritten(self):
        (self.ws / 'index.html').write_text('<html><body>empty</body></html>')
        (self.ws / 'check_page.js').write_text('process.exit(0);\n')
        res = h_eval.evaluate_attempt('gen_orbital', '', self.ws)
        self.assertFalse(res['valid'])
        self.assertEqual(res['details']['requirements']['harness']['status'], 'failed')

    def test_blank_and_static_and_dead_button_pages_fail(self):
        # Blank page
        (self.ws / 'blank.html').write_text('<html><body><canvas id="c" width="0" height="0"></canvas></body></html>')
        blank_dir = self.ws / 'blank'
        blank_dir.mkdir()
        (blank_dir / 'index.html').write_text('<html><body><canvas id="c" width="0" height="0"></canvas></body></html>')
        res_blank = h_eval.run_browser_check(blank_dir, 'orbital')
        if res_blank['status'] == 'not_evaluated':
            self.skipTest('chromium not available in environment')
        self.assertEqual(res_blank['status'], 'failed')

        # Static animation with dead buttons
        static_dir = self.ws / 'static'
        static_dir.mkdir()
        (static_dir / 'index.html').write_text(
            '<html><body>'
            '<canvas id="sky" width="400" height="300"></canvas>'
            '<button id="btnPlay">Pause</button><button id="btnTrails">Trails</button>'
            '<button id="btnReset">Reset</button><input id="speed" type="range" value="1.0">'
            '<span id="speedVal">1.0x</span><span id="simTime">1.0</span><span id="bursts">0</span>'
            '<script>const ctx=document.getElementById("sky").getContext("2d");'
            'ctx.fillStyle="#123456";ctx.fillRect(0,0,400,300);'
            'ctx.fillStyle="#ffffff";ctx.fillRect(10,10,20,20);</script>'
            '</body></html>'
        )
        res_static = h_eval.run_browser_check(static_dir, 'orbital')
        self.assertEqual(res_static['status'], 'failed')
        self.assertFalse(res_static.get('pixels_changed'))

    def test_valid_saved_web_artifacts_pass(self):
        orb = H_WS_ROOT / 'gen_orbital__direct__r1'
        por = H_WS_ROOT / 'gen_portal__direct__r1'
        if not orb.exists() or not por.exists():
            self.skipTest('saved 20261118-051116 workspaces not present')
        if h_eval.run_browser_check(orb, 'orbital')['status'] == 'not_evaluated':
            self.skipTest('chromium not available in environment')
        shutil.copytree(orb, self.ws / 'orb')
        shutil.copytree(por, self.ws / 'por')
        res_orb = h_eval.evaluate_attempt('gen_orbital', '', self.ws / 'orb')
        res_por = h_eval.evaluate_attempt('gen_portal', '', self.ws / 'por')
        self.assertTrue(res_orb['valid'], res_orb)
        self.assertTrue(res_por['valid'], res_por)

    def test_overexposed_portal_fails_visual_check(self):
        bad_por = H_WS_ROOT / 'gen_portal__tandem__r1'
        if not bad_por.exists():
            self.skipTest('saved 20261118-051116 gen_portal__tandem__r1 not present')
        if h_eval.run_browser_check(bad_por, 'portal')['status'] == 'not_evaluated':
            self.skipTest('chromium not available in environment')
        shutil.copytree(bad_por, self.ws / 'bad_por_vis')
        res = h_eval.evaluate_attempt('gen_portal', '', self.ws / 'bad_por_vis')
        self.assertFalse(res['valid'], 'overexposed portal must fail visual check')
        self.assertEqual(res['details']['requirements']['visual_portal']['status'], 'failed')

    def test_portal_reset_without_handler_fails(self):
        por = H_WS_ROOT / 'gen_portal__direct__r1'
        if not por.exists():
            self.skipTest('saved 20261118-051116 gen_portal workspace not present')
        if h_eval.run_browser_check(por, 'portal')['status'] == 'not_evaluated':
            self.skipTest('chromium not available in environment')
        bad_por = self.ws / 'bad_por'
        shutil.copytree(por, bad_por)
        app_js = bad_por / 'app.js'
        text = app_js.read_text(encoding='utf-8')
        text = text.replace('Engine3D.reset();', '/* reset handler disabled */')
        app_js.write_text(text, encoding='utf-8')
        res = h_eval.run_browser_check(bad_por, 'portal')
        self.assertEqual(res['status'], 'failed')
        self.assertFalse(res.get('controls', {}).get('resetOk'))

    def test_static_canvas_with_changing_fps_fails(self):
        fps_only_dir = self.ws / 'fps_only'
        fps_only_dir.mkdir()
        (fps_only_dir / 'index.html').write_text(
            '<html><body>'
            '<canvas id="c" width="400" height="300"></canvas>'
            '<div id="fps" style="position:fixed;top:10px;left:10px;color:#fff;">60</div>'
            '<span id="polys">36</span><span id="parts">110</span>'
            '<button id="btnPause">Pause</button><button id="btnOrbit">Orbit ON</button>'
            '<button id="btnReset">Reset</button><input id="speed" type="range" value="1.0">'
            '<b id="spdVal">1.0x</b>'
            '<script>'
            'const ctx=document.getElementById("c").getContext("2d");'
            'ctx.fillStyle="#0a0e1a";ctx.fillRect(0,0,400,300);'
            'ctx.fillStyle="#00ffcc";ctx.fillRect(40,40,80,80);'
            'let f=55; setInterval(()=>{ f=(f===55?60:55); document.getElementById("fps").textContent=String(f); }, 40);'
            '</script></body></html>',
            encoding='utf-8',
        )
        res = h_eval.run_browser_check(fps_only_dir, 'portal')
        if res['status'] == 'not_evaluated':
            self.skipTest('chromium not available in environment')
        self.assertEqual(res['status'], 'failed')
        self.assertFalse(res.get('pixels_changed'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
