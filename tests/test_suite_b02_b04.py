"""Offline tests for B02 (fair prompts & counterbalanced plan) and B04 (provenance, ledger isolation, merge)."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
H_DIR = ROOT / 'benchmarks' / 'hydrogen_3_6_1'
if str(H_DIR) not in sys.path:
    sys.path.insert(0, str(H_DIR))

spec = importlib.util.spec_from_file_location('hydrogen_suite', H_DIR / 'suite.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)


class B02FairComparisonTests(unittest.TestCase):
    def test_incident_log_prompts_have_clue_parity(self):
        inc = next(t for t in suite.TASKS if t['id'] == 'reading_incident_log')
        for forbidden in ('payments-db', 'INC-4471', 'ERROR'):
            self.assertNotIn(forbidden, inc['direct_prompt'])
            self.assertNotIn(forbidden, inc['tandem_prompt'])

    def test_counterbalanced_plan_is_reproducible_and_balanced(self):
        tasks = suite.TASKS[:4]
        p1 = suite.build_execution_plan(tasks, repeats=2, order='counterbalanced', seed=123)
        p2 = suite.build_execution_plan(tasks, repeats=2, order='counterbalanced', seed=123)
        self.assertEqual([x['scenario'] for x in p1], [x['scenario'] for x in p2])
        firsts = [x['pair_order'][0] for x in p1 if x['pair_position'] == 0]
        self.assertIn('direct', firsts)
        self.assertIn('tandem', firsts)


class B04AccountingAndMergeTests(unittest.TestCase):
    def test_missing_ledger_is_unavailable_not_zero(self):
        res = suite.summarize_local_ledger([], attempt_id='a1')
        self.assertEqual(res['status'], 'unavailable')
        self.assertFalse(res['delegation_verified'])
        self.assertIsNone(res['local_total_tokens'])

    def test_ledger_counts_only_llm_inference_events(self):
        entries = [
            {'kind': 'result', 'tool': 'digest_file', 'prompt_tokens': 999, 'completion_tokens': 999, 'saved_tokens_est': 500},
            {'kind': 'retry', 'tool': 'digest_file'},
            {'kind': 'llm', 'tool': 'digest_file', 'prompt_tokens': 100, 'completion_tokens': 25},
        ]
        res = suite.summarize_local_ledger(entries, attempt_id='a2')
        self.assertEqual(res['status'], 'available')
        self.assertTrue(res['delegation_verified'])
        self.assertEqual(res['local_calls'], 1)
        self.assertEqual(res['local_prompt_tokens'], 100)
        self.assertEqual(res['local_completion_tokens'], 25)
        self.assertEqual(res['local_total_tokens'], 125)
        self.assertEqual(res['retries'], 1)

    def test_validate_merge_rejects_incompatible_or_duplicate_runs(self):
        current = {'evaluator_sha256': 'abc', 'profile': 'lean'}
        with self.assertRaises(ValueError):
            suite.validate_merge({'manifest': {'evaluator_sha256': 'xyz', 'profile': 'lean'}, 'attempts': []}, current)
        with self.assertRaises(ValueError):
            suite.validate_merge({'manifest': {'evaluator_sha256': 'abc', 'profile': 'default'}, 'attempts': []}, current)
        with self.assertRaises(ValueError):
            suite.validate_merge(
                {'manifest': current, 'attempts': [{'attempt_id': 'x'}, {'attempt_id': 'x'}]},
                current,
            )
        # Incompatible fixture_hashes
        with self.assertRaises(ValueError):
            suite.validate_merge(
                {'manifest': {**current, 'fixture_hashes': {'t1': 'h1'}}, 'attempts': []},
                {**current, 'fixture_hashes': {'t1': 'h2'}},
            )
        # Incompatible requested_models
        with self.assertRaises(ValueError):
            suite.validate_merge(
                {'manifest': {**current, 'requested_models': {'orchestrator': 'm1'}}, 'attempts': []},
                {**current, 'requested_models': {'orchestrator': 'm2'}},
            )
        # Duplicate attempt_id across prior and current plan
        with self.assertRaises(ValueError):
            suite.validate_merge(
                {'manifest': current, 'attempts': [{'attempt_id': 'reading_git_log__direct__r1'}]},
                {**current, 'plan': [{'task_id': 'reading_git_log', 'scenario': 'direct', 'repeat': 1}]},
            )

    def test_tandem_success_requires_valid_answer_and_verified_delegation(self):
        import json
        import tempfile
        from unittest.mock import MagicMock, patch

        task = next(t for t in suite.TASKS if t['id'] == 'extraction_manifest')
        valid_json = json.dumps({
            'name': 'tandem-mcp',
            'requires_python': '>=3.11',
            'dependencies': ['mcp>=2.3', 'openai>=1.40'],
            'console_script': 'tandem-mcp = tandem_mcp.server:main',
        })
        fake_stdout = json.dumps({
            'status': 'SUCCESS',
            'response': valid_json,
            'usage': {'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150},
        })

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            # Case 1: Valid answer WITHOUT local calls in isolated ledger -> artifact_valid=True, e2e_success=False
            proc1 = MagicMock()
            proc1.communicate.return_value = (fake_stdout, '')
            proc1.returncode = 0
            with patch.object(suite, 'set_tandem_mcp'), patch.object(suite.subprocess, 'Popen', return_value=proc1):
                res_no_deleg = suite.run_attempt(task, 'tandem', 1, run_dir)
            self.assertTrue(res_no_deleg['artifact_valid'])
            self.assertFalse(res_no_deleg['delegation_verified'])
            self.assertFalse(res_no_deleg['e2e_success'])
            self.assertEqual(res_no_deleg['attribution_reason'], 'missing_verified_delegation')

            # Case 2: Valid answer WITH recorded delegation in isolated ledger -> artifact_valid=True, e2e_success=True
            attempt2_home = run_dir / 'tandem_homes' / f"{task['id']}__tandem__r2"
            attempt2_home.mkdir(parents=True, exist_ok=True)
            (attempt2_home / 'ledger.jsonl').write_text(
                json.dumps({'kind': 'llm', 'tool': 'extract_from_file', 'prompt_tokens': 80, 'completion_tokens': 20}) + '\n',
                encoding='utf-8',
            )
            proc2 = MagicMock()
            proc2.communicate.return_value = (fake_stdout, '')
            proc2.returncode = 0
            with patch.object(suite, 'set_tandem_mcp'), patch.object(suite.subprocess, 'Popen', return_value=proc2):
                res_with_deleg = suite.run_attempt(task, 'tandem', 2, run_dir)
            self.assertTrue(res_with_deleg['artifact_valid'])
            self.assertTrue(res_with_deleg['delegation_verified'])
            self.assertTrue(res_with_deleg['e2e_success'])
            self.assertEqual(res_with_deleg['attribution_reason'], 'ok')

    def test_evaluator_identity_includes_web_browser_check_and_reeval_preserves_archive(self):
        import json
        import tempfile

        h1 = suite.compute_evaluator_sha256()
        self.assertEqual(len(h1), 64)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / 'run1'
            ws = run_dir / 'workspaces' / 'extraction_manifest__direct__r1'
            ws.mkdir(parents=True)
            suite.prepare_workspace(next(t for t in suite.TASKS if t['id'] == 'extraction_manifest'), ws)
            (run_dir / 'logs').mkdir(parents=True)
            (run_dir / 'logs' / 'extraction_manifest__direct__r1.stdout.txt').write_text(
                json.dumps({'status': 'SUCCESS', 'response': json.dumps({
                    'name': 'tandem-mcp',
                    'requires_python': '>=3.11',
                    'dependencies': ['mcp>=2.3', 'openai>=1.40'],
                    'console_script': 'tandem-mcp = tandem_mcp.server:main',
                })}) + '\n',
                encoding='utf-8',
            )
            (run_dir / 'results.json').write_text(
                json.dumps({
                    'run_id': 'test_archive',
                    'attempts': [{
                        'attempt_id': 'extraction_manifest__direct__r1',
                        'task_id': 'extraction_manifest',
                        'task_name': 'Structured JSON extraction (pyproject.toml)',
                        'category': 'extraction',
                        'scenario': 'direct',
                        'completed': True,
                        'wall_seconds': 1.0,
                        'cloud_usage': {'total_tokens': 100},
                        'local_usage': {'local_total_tokens': 0, 'retries': 0},
                    }],
                }),
                encoding='utf-8',
            )
            out_dir = Path(tmp) / 'out'
            out_dir.mkdir()
            report = suite.reevaluate_run(run_dir, out_dir=out_dir)
            self.assertTrue(report['archive_unmodified'])
            self.assertEqual(report['archive_sha256_before'], report['archive_sha256_after'])
            self.assertEqual(report['evaluator_sha256'], h1)

    def test_aggregate_tracks_coverage_failures_and_recoveries(self):
        attempts = [
            {
                'task_id': 'reading_git_log',
                'scenario': 'tandem',
                'e2e_success': True,
                'wall_seconds': 10.0,
                'cloud_usage': {'total_tokens': 1000},
                'local_usage': {'local_total_tokens': 200, 'retries': 1},
            },
            {
                'task_id': 'reading_git_log',
                'scenario': 'tandem',
                'e2e_success': False,
                'wall_seconds': 20.0,
                'cloud_usage': {'total_tokens': None},
                'local_usage': {'local_total_tokens': None, 'retries': 0},
            },
        ]
        summary = suite.aggregate_results(attempts)
        self.assertEqual(len(summary), 1)
        row = summary[0]
        self.assertEqual(row['n'], 2)
        self.assertEqual(row['e2e_success_count'], 1)
        self.assertEqual(row['failed_count'], 1)
        self.assertEqual(row['recoveries'], 1)
        self.assertEqual(row['cloud_coverage'], '1/2')
        self.assertEqual(row['local_coverage'], '1/2')
        self.assertEqual(row['mean_cloud_tokens'], 1000.0)
        self.assertIsNone(row['tokens_per_useful_result'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
