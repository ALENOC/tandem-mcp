"""Deterministic tests for the comparative benchmark methodology and historical preservation.

Runs without any live LLM server or cloud API calls (suitable for GitHub Actions CI).
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMP_DIR = ROOT / 'benchmarks/comparative_3_6_1'
if str(CMP_DIR) not in sys.path:
    sys.path.insert(0, str(CMP_DIR))

import evaluate  # noqa: E402
import metrics  # noqa: E402
import run_comparison  # noqa: E402


class TestContextReduction(unittest.TestCase):
    def test_positive_reduction_and_provenance(self):
        res = metrics.compute_context_reduction(10000, 1000)
        self.assertEqual(res['context_reduction_pct'], 90.0)
        self.assertEqual(res['provenance'], 'derived')
        self.assertEqual(res['est_tokens_provenance'], 'estimated')
        self.assertEqual(res['est_tokens_saved'], metrics.est_tokens(9000))

    def test_negative_context_reduction_not_clamped(self):
        res = metrics.compute_context_reduction(1000, 2500)
        self.assertEqual(res['context_reduction_pct'], -150.0)
        self.assertLess(res['est_tokens_saved'], 0)

    def test_zero_source_bytes_unavailable(self):
        res = metrics.compute_context_reduction(0, 100)
        self.assertEqual(res['provenance'], 'unavailable')
        self.assertIsNone(res['context_reduction_pct'])


class TestCloudTokenSavings(unittest.TestCase):
    def test_positive_cloud_savings(self):
        res = metrics.compute_cloud_token_savings(10000, 2500)
        self.assertEqual(res['status'], 'measured')
        self.assertEqual(res['provenance'], 'measured')
        self.assertEqual(res['cloud_tokens_saved'], 7500)
        self.assertEqual(res['cloud_savings_pct'], 75.0)

    def test_negative_cloud_savings_preserved(self):
        res = metrics.compute_cloud_token_savings(5000, 8000)
        self.assertEqual(res['status'], 'measured')
        self.assertEqual(res['cloud_tokens_saved'], -3000)
        self.assertEqual(res['cloud_savings_pct'], -60.0)

    def test_unavailable_tokens_not_estimated(self):
        res = metrics.compute_cloud_token_savings(None, 2500, direct_status='unavailable')
        self.assertEqual(res['status'], 'unavailable')
        self.assertEqual(res['provenance'], 'unavailable')
        self.assertIsNone(res['cloud_savings_pct'])
        self.assertIsNone(res['cloud_tokens_saved'])

    def test_missing_baseline_returns_unavailable(self):
        res = metrics.compute_cloud_token_savings(0, 100)
        self.assertEqual(res['status'], 'unavailable')
        self.assertIsNone(res['cloud_savings_pct'])


class TestAggregation(unittest.TestCase):
    def test_aggregation_and_variability_threshold(self):
        r1 = {
            'wall_seconds': 10.0,
            'cloud_usage': {'cloud_tokens_status': 'measured', 'cloud_total_tokens': 1000},
            'local_compute': {'local_total_tokens': 2000, 'repair_attempts': 0},
            'quality': {'passed': True, 'constraint_compliance_pct': 100.0},
        }
        r2 = {
            'wall_seconds': 20.0,
            'cloud_usage': {'cloud_tokens_status': 'measured', 'cloud_total_tokens': 2000},
            'local_compute': {'local_total_tokens': 4000, 'repair_attempts': 1},
            'quality': {'passed': False, 'constraint_compliance_pct': 50.0},
        }
        r3 = {
            'wall_seconds': 15.0,
            'cloud_usage': {'cloud_tokens_status': 'measured', 'cloud_total_tokens': 1200},
            'local_compute': {'local_total_tokens': 2500, 'repair_attempts': 0},
            'quality': {'passed': True, 'constraint_compliance_pct': 100.0},
        }
        agg2 = metrics.aggregate_runs([r1, r2])
        self.assertFalse(agg2['statistically_representative'])
        self.assertNotIn('seconds_stdev', agg2)

        agg3 = metrics.aggregate_runs([r1, r2, r3])
        self.assertTrue(agg3['statistically_representative'])
        self.assertEqual(agg3['n'], 3)
        self.assertEqual(agg3['successes'], 2)
        self.assertEqual(agg3['success_rate'], 66.7)
        self.assertEqual(agg3['failure_rate'], 33.3)
        self.assertEqual(agg3['median_seconds'], 15.0)
        self.assertEqual(agg3['cloud_tokens_per_success_mean'], 1100.0)
        self.assertEqual(agg3['repair_attempts_total'], 1)
        self.assertIn('seconds_stdev', agg3)


class TestVersionAndFixtures(unittest.TestCase):
    def test_fixture_manifest_and_sha256(self):
        fix_dir = CMP_DIR / 'fixtures'
        res = metrics.verify_fixtures_manifest(fix_dir)
        self.assertTrue(res['ok'])
        self.assertGreaterEqual(res['checked_files'], 24)

    def test_sha256_mismatch_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            f = td / 'sample.txt'
            f.write_text('hello')
            (td / 'manifest.json').write_text(json.dumps({
                'git_commit': '010cbb6',
                'files': {'sample.txt': {'sha256': hashlib.sha256(b'tampered').hexdigest(), 'bytes': 5}},
            }))
            with self.assertRaises(RuntimeError):
                metrics.verify_fixtures_manifest(td)

    def test_version_identification_mismatch_raises(self):
        with self.assertRaises(RuntimeError):
            metrics.verify_git_commit(ROOT, expected_commit='deadbeef', allow_override=False)
        res = metrics.verify_git_commit(ROOT, expected_commit='deadbeef', allow_override=True)
        self.assertFalse(res['matches'])
        self.assertTrue(res['overridden'])


class TestHistoricalPreservationAndDocs(unittest.TestCase):
    def test_historical_fable_and_gemini_intact(self):
        fable_md = ROOT / 'benchmarks/RESULTS.md'
        fable_json = ROOT / 'benchmarks/latest.json'
        gem_md = ROOT / 'benchmarks/gemini_3_6_1/RESULTS.md'
        gem_json = ROOT / 'benchmarks/gemini_3_6_1/results.json'
        gem_gen = ROOT / 'benchmarks/gemini_3_6_1/generation.json'
        for p in [fable_md, fable_json, gem_md, gem_json, gem_gen]:
            self.assertTrue(p.exists(), f'Missing historical artifact: {p}')
        self.assertIn('Fable 5.2', fable_md.read_text())
        gj = json.loads(gem_json.read_text())
        self.assertEqual(gj['git_commit'], '010cbb6')
        self.assertEqual(gj['orchestrator'], 'Gemini 4 Hydrogen')
        gg = json.loads(gem_gen.read_text())
        self.assertEqual(gg['git_commit'], '010cbb6')

    def test_json_validity_and_demo_links(self):
        cfg = json.loads((CMP_DIR / 'configs/suite.json').read_text())
        self.assertEqual(cfg['expected_commit'], '010cbb6')
        self.assertEqual(len(cfg['tasks']), 9)
        for demo in [
            ROOT / 'benchmarks/animation_comparison.html',
            ROOT / 'benchmarks/scene3d_comparison.html',
            ROOT / 'benchmarks/gemini_3_6_1/animation_comparison.html',
            ROOT / 'benchmarks/gemini_3_6_1/scene3d_comparison.html',
        ]:
            self.assertTrue(demo.exists(), f'Missing demo: {demo}')


if __name__ == '__main__':
    unittest.main()
