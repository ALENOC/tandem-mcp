"""Deterministic regression tests for the comparative benchmark methodology.

Runs without any live LLM server or cloud API calls (suitable for GitHub Actions CI).
Never presents synthetic test data as real benchmark measurements.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import time
from unittest.mock import patch, MagicMock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMP_DIR = ROOT / 'benchmarks/comparative_3_6_1'
if str(CMP_DIR) not in sys.path:
    sys.path.insert(0, str(CMP_DIR))

import evaluate  # noqa: E402
import metrics  # noqa: E402
import run_comparison  # noqa: E402
import lm_studio_harness as harness  # noqa: E402


def _make_record(status='COMPLETED', passed=True, cloud_total=1000, local_total=2000, wall=10.0, evaluated=True):
    quality = {'evaluated': evaluated, 'passed': passed, 'constraint_compliance_pct': 100.0 if passed else 0.0}
    outcome = metrics.classify_outcome(status, quality)
    cloud = (
        {'cloud_tokens_status': 'measured', 'cloud_total_tokens': cloud_total}
        if cloud_total is not None
        else {'cloud_tokens_status': 'unavailable', 'cloud_total_tokens': None}
    )
    return {
        'task_id': 'synthetic_task',
        'scenario': 'gemini_tandem',
        'status': outcome['execution_status'],
        'outcome': outcome,
        'wall_seconds': wall,
        'cloud_usage': cloud,
        'local_compute': {'local_total_tokens': local_total, 'provenance': 'measured', 'repair_attempts': 0},
        'quality': quality,
    }


class TestBenchmarkDeadlines(unittest.TestCase):
    def test_defaults_are_bounded(self):
        cfg = run_comparison.load_config()
        self.assertTrue(all(t > 0 for t in cfg['timeouts_seconds'].values()))
        with self.assertRaises(ValueError):
            harness.run_task(Path('/tmp'), 'test', timeout=0)
        with self.assertRaises(ValueError):
            harness.run_bounded(['true'], timeout=0)

    def test_timeout_kills_descendants_and_preserves_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / 'child.pid'
            code = ('import os,time; pid=os.fork(); '
                    f'open({str(pid_file)!r}, "w").write(str(pid)) if pid else None; '
                    'print("started", flush=True); time.sleep(30)')
            start = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                harness.run_bounded([sys.executable, '-c', code], timeout=0.5)
            self.assertLess(time.monotonic() - start, 3)
            self.assertIn('started', caught.exception.output)
            child = int(pid_file.read_text())
            # A killed orphan can remain a zombie until the system reaps it.
            stat = Path(f'/proc/{child}/stat')
            for _ in range(50):
                if not stat.exists() or stat.read_text().split()[2] == 'Z':
                    break
                time.sleep(0.01)
            else:
                self.fail('timed-out descendant is still running')

    def test_success_does_not_wait_for_inherited_output_pipes(self):
        code = ('import subprocess,sys; subprocess.Popen([sys.executable,"-c",'
                '"import time; time.sleep(30)"]); print("done")')
        start = time.monotonic()
        result = harness.run_bounded([sys.executable, '-c', code], timeout=2)
        self.assertEqual(result.returncode, 0)
        self.assertIn('done', result.stdout)
        self.assertLess(time.monotonic() - start, 3)

    def test_http_timeout_uses_remaining_budget_and_persists_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats_file = Path(tmp) / 'stats.json'
            with patch.object(harness.time, 'perf_counter', return_value=100), \
                    patch.object(harness.urllib.request, 'urlopen', side_effect=TimeoutError('stalled')) as request:
                result = harness.run_task(Path(tmp), 'test', timeout=7, stats_out=stats_file)
            self.assertEqual(request.call_args.kwargs['timeout'], 7)
            self.assertEqual(result['status'], 'TIMEOUT')
            self.assertEqual(json.loads(stats_file.read_text())['status'], 'TIMEOUT')

    def test_step_exhaustion_is_explicit_and_usage_is_saved(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            'usage': {'prompt_tokens': 20, 'completion_tokens': 5},
            'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': 'x', 'function': {'name': 'list_files', 'arguments': '{}'}}]}}],
        }).encode()
        with tempfile.TemporaryDirectory() as tmp:
            stats_file = Path(tmp) / 'stats.json'
            with patch.object(harness.urllib.request, 'urlopen', return_value=response):
                result = harness.run_task(Path(tmp), 'test', max_steps=1, stats_out=stats_file)
            self.assertEqual(result['status'], 'STEP_LIMIT')
            saved = json.loads(stats_file.read_text())
            self.assertEqual(saved['local_total_tokens'], 25)
            self.assertEqual(saved['local_requests'], 1)

    def test_no_tools_execute_after_inference_exhausts_budget(self):
        clock = [0]
        response = MagicMock()
        def read():
            clock[0] = 11
            return json.dumps({'choices': [{'message': {'tool_calls': [
                {'id': 'x', 'function': {'name': 'list_files', 'arguments': '{}'}}]}}]}).encode()
        response.__enter__.return_value.read.side_effect = read
        with patch.object(harness.time, 'perf_counter', side_effect=lambda: clock[0]), \
                patch.object(harness.urllib.request, 'urlopen', return_value=response), \
                patch.object(harness, '_exec_tool') as execute:
            result = harness.run_task(Path('/tmp'), 'test', timeout=10)
        self.assertEqual(result['status'], 'TIMEOUT')
        execute.assert_not_called()

    def test_prompts_use_short_waits_and_configured_executor(self):
        cfg = run_comparison.load_config()
        fixtures = CMP_DIR / 'fixtures'
        for task in cfg['tasks']:
            prompt = run_comparison._build_prompt(task, 'gemini_tandem', Path('/tmp/ws'), fixtures, 180)
            self.assertNotIn('wait_seconds=1500', prompt)
            self.assertNotIn('wait_seconds=600', prompt)
        prompt = run_comparison._build_prompt(cfg['tasks'][0], 'gemini_lmstudio', Path('/tmp/ws'), fixtures,
                                              180, {'endpoint': 'http://localhost:4321/v1', 'model_id': 'custom-model'})
        self.assertIn('--timeout 162', prompt)
        self.assertIn('--model "custom-model"', prompt)
        self.assertIn('--endpoint "http://localhost:4321/v1"', prompt)

    def test_preflight_fails_before_starting_unavailable_executor(self):
        with patch.object(run_comparison.shutil, 'which', return_value='/bin/agy'), \
                patch.object(run_comparison.urllib.request, 'urlopen', side_effect=OSError('offline')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot reach local executor'):
                run_comparison.check_runtime(run_comparison.load_config(), ['gemini_lmstudio'])

    def test_runner_does_not_accept_unfinished_local_execution(self):
        cfg = run_comparison.load_config()
        task = next(t for t in cfg['tasks'] if t['id'] == 'extraction_manifest')
        def incomplete(command, *, cwd, **kwargs):
            (cwd / 'lm_studio_stats.json').write_text(json.dumps({'status': 'RUNNING', 'local_requests': 1}))
            return subprocess.CompletedProcess(command, 0, json.dumps({'status': 'COMPLETED', 'response': 'still waiting'}), '')
        with tempfile.TemporaryDirectory() as tmp:
            # Keep all runner workspaces under a directory that this test cleans up.
            real_mkdtemp = tempfile.mkdtemp
            with patch.object(run_comparison.tempfile, 'mkdtemp', side_effect=lambda **kw: real_mkdtemp(dir=tmp, **kw)), \
                    patch.object(run_comparison, 'run_bounded', side_effect=incomplete):
                record = run_comparison.run_single(task, 'gemini_lmstudio', 1, cfg, CMP_DIR / 'fixtures', 20)
        self.assertEqual(record['status'], 'PARTIAL')
        self.assertFalse(record['outcome']['end_to_end_success'])

    def test_runner_timeout_is_recorded_with_partial_logs(self):
        cfg = run_comparison.load_config()
        task = next(t for t in cfg['tasks'] if t['id'] == 'extraction_manifest')
        with tempfile.TemporaryDirectory() as tmp:
            real_mkdtemp = tempfile.mkdtemp
            with patch.object(run_comparison.tempfile, 'mkdtemp', side_effect=lambda **kw: real_mkdtemp(dir=tmp, **kw)), \
                    patch.object(run_comparison, 'run_bounded', side_effect=subprocess.TimeoutExpired(
                        'agy', 10, output='partial stdout', stderr='partial stderr')):
                record = run_comparison.run_single(task, 'gemini_direct', 1, cfg, CMP_DIR / 'fixtures',
                                                   10, run_dir=Path(tmp) / 'run')
            self.assertEqual(record['status'], 'TIMEOUT')
            self.assertEqual(record['timeout_seconds'], 10)
            log = Path(tmp) / 'run/logs/extraction_manifest/gemini_direct/r1/stdout.txt'
            self.assertEqual(log.read_text(), 'partial stdout')
            self.assertIn('partial stderr', record['error_preview'])

    def test_interrupt_cleans_up_the_process_group(self):
        process = MagicMock()
        process.pid = 123456
        process.wait.side_effect = [KeyboardInterrupt, 0, 0]
        with patch.object(harness.subprocess, 'Popen', return_value=process), \
                patch.object(harness.os, 'killpg') as kill:
            with self.assertRaises(KeyboardInterrupt):
                harness.run_bounded(['command'], timeout=10)
        self.assertEqual(kill.call_count, 2)

    def test_preflight_checks_model_identity(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"data": [{"id": "different-model"}]}'
        with patch.object(run_comparison.shutil, 'which', return_value='/bin/agy'), \
                patch.object(run_comparison.urllib.request, 'urlopen', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'Required executor model'):
                run_comparison.check_runtime(run_comparison.load_config(), ['gemini_tandem'])


class TestExecutionVsArtifactOutcomes(unittest.TestCase):
    def test_timeout_with_valid_artifact_is_not_e2e_success(self):
        out = metrics.classify_outcome('TIMEOUT', {'evaluated': True, 'passed': True})
        self.assertEqual(out['execution_status'], 'TIMEOUT')
        self.assertTrue(out['artifact_valid'])
        self.assertFalse(out['execution_completed'])
        self.assertFalse(out['end_to_end_success'])

    def test_timeout_with_invalid_artifact(self):
        out = metrics.classify_outcome('TIMEOUT', {'evaluated': True, 'passed': False})
        self.assertEqual(out['execution_status'], 'TIMEOUT')
        self.assertFalse(out['artifact_valid'])
        self.assertFalse(out['execution_completed'])
        self.assertFalse(out['end_to_end_success'])

    def test_completed_with_invalid_artifact(self):
        out = metrics.classify_outcome('COMPLETED', {'evaluated': True, 'passed': False})
        self.assertEqual(out['execution_status'], 'COMPLETED')
        self.assertTrue(out['execution_completed'])
        self.assertFalse(out['artifact_valid'])
        self.assertFalse(out['end_to_end_success'])

    def test_missing_evaluation_marks_evaluation_error(self):
        out = metrics.classify_outcome('COMPLETED', {'evaluated': False, 'passed': False})
        self.assertEqual(out['execution_status'], 'EVALUATION_ERROR')
        self.assertFalse(out['execution_completed'])
        self.assertFalse(out['artifact_valid'])
        self.assertFalse(out['end_to_end_success'])

    def test_interrupted_and_partial_and_crash(self):
        for st in ['INTERRUPTED', 'PARTIAL', 'FAILED']:
            out = metrics.classify_outcome(st, {'evaluated': True, 'passed': True})
            self.assertEqual(out['execution_status'], st)
            self.assertFalse(out['execution_completed'])
            self.assertFalse(out['end_to_end_success'])


class TestCloudTokenAccounting(unittest.TestCase):
    def test_success_aggregation_and_failed_attempts_included_in_tokens(self):
        recs = [
            _make_record('COMPLETED', True, cloud_total=1000, wall=10.0),
            _make_record('COMPLETED', False, cloud_total=2000, wall=20.0),
            _make_record('TIMEOUT', True, cloud_total=None, wall=2400.0),
        ]
        agg = metrics.aggregate_runs(recs)
        self.assertEqual(agg['n'], 3)
        self.assertEqual(agg['completed_executions'], 2)
        self.assertEqual(agg['end_to_end_successes'], 1)
        self.assertEqual(agg['artifact_valid_count'], 2)
        self.assertEqual(agg['timeouts'], 1)
        self.assertEqual(agg['end_to_end_success_rate'], 33.3)
        self.assertEqual(agg['artifact_pass_rate'], 66.7)
        # Failed attempt (2000) MUST be included in total_measured_cloud_tokens
        self.assertEqual(agg['total_measured_cloud_tokens'], 3000)
        self.assertEqual(agg['mean_cloud_tokens_per_attempt'], 1500.0)
        self.assertEqual(agg['measured_usage_count'], 2)
        self.assertEqual(agg['missing_usage_count'], 1)
        self.assertEqual(agg['usage_coverage_pct'], 66.7)
        self.assertEqual(agg['cloud_tokens_per_success'], 3000.0)
        self.assertFalse(agg['cloud_tokens_per_success_complete'])

    def test_zero_successful_runs_returns_none(self):
        recs = [_make_record('FAILED', False, cloud_total=1500)]
        agg = metrics.aggregate_runs(recs)
        self.assertEqual(agg['end_to_end_successes'], 0)
        self.assertIsNone(agg['cloud_tokens_per_success'])

    def test_missing_usage_handling(self):
        rec = metrics.build_cloud_usage_record(None, num_turns=None)
        self.assertEqual(rec['cloud_tokens_status'], 'unavailable')
        self.assertIsNone(rec['cloud_total_tokens'])

    def test_no_double_counting_thinking_tokens(self):
        raw = {'input_tokens': 15000, 'output_tokens': 700, 'thinking_tokens': 400, 'cache_read_tokens': 10000}
        rec = metrics.build_cloud_usage_record(raw, num_turns=1)
        self.assertEqual(rec['cloud_total_tokens'], 15700)
        self.assertEqual(rec['cloud_cached_tokens'], 10000)
        self.assertTrue(rec['thinking_included_in_output'])

    def test_negative_savings_and_coverage_comparability(self):
        sav = metrics.compute_cloud_token_savings(1000, 1250, direct_coverage_pct=100.0, candidate_coverage_pct=100.0)
        self.assertEqual(sav['cloud_savings_pct'], -25.0)
        self.assertTrue(sav['coverage_comparable'])
        inc = metrics.compute_cloud_token_savings(1000, 900, direct_coverage_pct=100.0, candidate_coverage_pct=66.7)
        self.assertFalse(inc['coverage_comparable'])
        self.assertEqual(inc['status'], 'incomplete')


class TestToolPayloadAndContextReduction(unittest.TestCase):
    def test_actual_mcp_payload_accounting(self):
        interactions = [
            {'tool_name': 'mcp:tandem-mcp:digest_file', 'request_bytes': 120, 'response_bytes': 480, 'truncated': False},
            {'tool_name': 'mcp:tandem-mcp:job_evidence', 'request_bytes': 80, 'response_bytes': 220, 'truncated': True},
        ]
        tc = metrics.build_tool_context_record(interactions, source_bytes=10000)
        self.assertEqual(tc['tool_call_count'], 2)
        self.assertEqual(tc['total_request_bytes'], 200)
        self.assertEqual(tc['total_response_bytes'], 700)
        self.assertEqual(tc['truncated_calls'], 1)
        self.assertEqual(tc['source_reduction']['source_reduction_pct'], 93.0)
        self.assertEqual(tc['source_reduction']['provenance'], 'derived')
        self.assertEqual(tc['source_reduction']['est_tokens_provenance'], 'estimated')

    def test_unavailable_tool_payload_not_derived_from_answer(self):
        tc = metrics.build_tool_context_record(None, source_bytes=10000)
        self.assertEqual(tc['provenance'], 'unavailable')
        self.assertIsNone(tc['total_response_bytes'])
        self.assertEqual(tc['source_reduction']['provenance'], 'unavailable')


class TestIdentityAndEnvironmentIntegrity(unittest.TestCase):
    def test_model_identity_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            brain = Path(tmp)
            cid = 'conv-123'
            log_dir = brain / cid / '.system_generated/logs'
            log_dir.mkdir(parents=True)
            (log_dir / 'transcript.jsonl').write_text(json.dumps({'type': 'PLANNER_RESPONSE', 'model': 'gemini-4-hydrogen-medium'}) + '\n')
            ok = metrics.verify_agy_model_identity('gemini-4-hydrogen-medium', cid, brain_root=brain)
            self.assertTrue(ok['identity_verified'])
            self.assertEqual(ok['provider_reported_model_id'], 'gemini-4-hydrogen-medium')

            missing = metrics.verify_agy_model_identity('gemini-4-hydrogen-medium', None, brain_root=brain)
            self.assertFalse(missing['identity_verified'])

    def test_git_version_enforcement_and_dirty_detection(self):
        with self.assertRaises(RuntimeError):
            metrics.verify_git_commit(ROOT, expected_commit='deadbeef', allow_override=False)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init'], cwd=repo, capture_output=True, check=True)
            subprocess.run(['git', 'config', 'user.email', 't@example.com'], cwd=repo, check=True)
            subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=repo, check=True)
            pkg = repo / 'tandem_mcp'
            pkg.mkdir()
            (pkg / '__init__.py').write_text('__version__ = "3.6.1"\n')
            subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
            subprocess.run(['git', 'commit', '-m', 'init'], cwd=repo, capture_output=True, check=True)
            head = subprocess.check_output(['git', 'rev-parse', '--short=7', 'HEAD'], cwd=repo, text=True).strip()
            clean = metrics.verify_tandem_environment(repo, expected_commit=head, expected_version='3.6.1')
            self.assertTrue(clean['verified'])
            (pkg / '__init__.py').write_text('__version__ = "3.6.1"\n# dirty\n')
            with self.assertRaises(RuntimeError):
                metrics.verify_tandem_environment(repo, expected_commit=head, expected_version='3.6.1')

    def test_fixture_hash_verification(self):
        res = metrics.verify_fixtures_manifest(CMP_DIR / 'fixtures')
        self.assertTrue(res['ok'])
        self.assertGreaterEqual(res['checked_files'], 24)
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            (td / 'a.txt').write_text('hello')
            (td / 'manifest.json').write_text(json.dumps({'files': {'a.txt': {'sha256': hashlib.sha256(b'bad').hexdigest()}}}))
            with self.assertRaises(RuntimeError):
                metrics.verify_fixtures_manifest(td)


class TestEvaluatorsAndReporting(unittest.TestCase):
    def test_evaluator_ground_truth(self):
        fix = CMP_DIR / 'fixtures'
        # Git history frequency parser
        top = evaluate.parse_git_log_top_files((fix / 'git_log_30_stat.txt').read_text(), top_k=3)
        self.assertEqual(len(top), 3)
        self.assertGreater(top[0][1], 0)
        # README evaluator rejects hallucinated TANDEM_NET
        bad_readme = evaluate.eval_reading_readme('TANDEM_SANDBOX and TANDEM_NET configure it.', fix)
        self.assertFalse(bad_readme['passed'])
        good_readme = evaluate.eval_reading_readme('TANDEM_SANDBOX defaults to secure with bubblewrap.', fix)
        self.assertTrue(good_readme['passed'])

    def test_historical_records_preserved_and_report_generation(self):
        for p in [
            ROOT / 'benchmarks/RESULTS.md',
            ROOT / 'benchmarks/latest.json',
            ROOT / 'benchmarks/gemini_3_6_1/RESULTS.md',
            ROOT / 'benchmarks/gemini_3_6_1/results.json',
            ROOT / 'benchmarks/gemini_3_6_1/generation.json',
        ]:
            self.assertTrue(p.exists(), f'Missing historical file: {p}')
        with tempfile.TemporaryDirectory() as tmp:
            rd = Path(tmp)
            cfg = run_comparison.load_config()
            recs = [_make_record('TIMEOUT', True, cloud_total=None, wall=2400.0)]
            run_comparison._save_report('test-run', rd, cfg, {'commit': {'actual_commit': '010cbb6'}}, {'ok': True}, recs)
            md = (rd / 'RESULTS.md').read_text()
            self.assertIn('0.0%', md)
            self.assertIn('100.0%', md)

    def test_resume_skips_completed_keys(self):
        prev = {'records': [{'task_id': 'reading_readme', 'scenario': 'gemini_direct', 'repeat': 1}]}
        done = {(r['task_id'], r['scenario'], r['repeat']) for r in prev['records'] if not r.get('dry_run')}
        self.assertIn(('reading_readme', 'gemini_direct', 1), done)


if __name__ == '__main__':
    unittest.main()
