#!/usr/bin/env python3
"""Deterministic generator of the large-context fixtures (part C of the lean evaluation).

refactor_rename/   12 service modules (~150 lines each) that call settings.get_conf(); the task renames it
                   to load_settings() everywhere. A direct orchestrator must read and rewrite every module.
incident_log.txt   ~70 KB service log with heavy WARN/ERROR noise around one real incident; the task
                   reconstructs it. A direct orchestrator must pull large slices of the log into context.
"""
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'fixtures'
SERVICES = ['billing', 'catalog', 'checkout', 'inventory', 'ledger', 'mailer',
            'orders', 'pricing', 'reports', 'search', 'shipping', 'users']


def make_refactor():
    out = ROOT / 'refactor_rename'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'settings.py').write_text(
        '"""Central settings access."""\n\n'
        '_DEFAULTS = {"timeout": 30, "retries": 3, "region": "eu-west-1", "batch": 50}\n\n\n'
        'def get_conf(key, default=None):\n'
        '    """Return the setting `key`, or `default` when unknown."""\n'
        '    return _DEFAULTS.get(key, default)\n')
    rng = random.Random(7)
    for name in SERVICES:
        body = [f'"""{name.capitalize()} service helpers."""', 'from settings import get_conf', '', '']
        for i in range(12):
            key = rng.choice(['timeout', 'retries', 'region', 'batch'])
            body += [
                f'def {name}_step_{i}(items):',
                f'    """Step {i} of the {name} pipeline: scale, filter and tag each item."""',
                f'    limit = get_conf("{key}", 1)',
                '    out = []',
                '    for n, item in enumerate(items):',
                f'        if n >= (limit if isinstance(limit, int) else {i + 1}):',
                '            break',
                f'        out.append((item, "{name}-{i}"))',
                '    return out',
                '', '',
            ]
        body += [f'def {name}_summary():',
                 f'    return {{"service": "{name}", "region": get_conf("region"), "steps": 12}}', '']
        (out / f'svc_{name}.py').write_text('\n'.join(body))
    (out / 'test_rename.py').write_text(
        'import importlib\nimport pathlib\nimport unittest\n\n'
        f'SERVICES = {SERVICES!r}\n\n\n'
        'class TestRename(unittest.TestCase):\n'
        '    def test_new_name(self):\n'
        '        import settings\n'
        '        self.assertTrue(hasattr(settings, "load_settings"))\n'
        '        self.assertFalse(hasattr(settings, "get_conf"))\n'
        '        self.assertEqual(settings.load_settings("retries"), 3)\n'
        '        self.assertEqual(settings.load_settings("nope", 9), 9)\n\n'
        '    def test_no_old_name_left(self):\n'
        '        for path in pathlib.Path(".").glob("*.py"):\n'
        '            if path.name != "test_rename.py":\n'
        '                self.assertNotIn("get_conf", path.read_text(), path.name)\n\n'
        '    def test_services_work(self):\n'
        '        for name in SERVICES:\n'
        '            mod = importlib.import_module("svc_" + name)\n'
        '            self.assertEqual(mod.__dict__[name + "_summary"]()["region"], "eu-west-1")\n'
        '            self.assertTrue(mod.__dict__[name + "_step_0"](list(range(100))))\n\n\n'
        'if __name__ == "__main__":\n    unittest.main()\n')


def make_log():
    rng = random.Random(11)
    noise_err = ['upstream timeout after 5000ms', 'retrying request (attempt 2/3)', 'cache miss storm detected',
                 'slow query 1840ms', 'connection reset by peer', 'TLS handshake took 900ms', 'rate limit 429 from partner']
    lines = []
    t = 2 * 3600                                              # 02:00:00
    events = {
        2 * 3600 + 14 * 60 + 7: 'ERROR payments-db: write failed: No space left on device (/var/lib/pg 100% used)',
        2 * 3600 + 14 * 60 + 9: 'ERROR payments-db: checkpoint aborted, WAL segment could not be written',
        2 * 3600 + 15 * 60 + 2: 'ERROR checkout: payment authorisation failed: payments-db unavailable',
        2 * 3600 + 16 * 60 + 40: 'ERROR orders: 503 from checkout for 41% of requests',
        2 * 3600 + 31 * 60 + 0: 'WARN oncall: page acknowledged by m.rossi (incident INC-4471 opened)',
        2 * 3600 + 52 * 60 + 18: 'INFO payments-db: old WAL archives purged, 38 GB freed, disk at 61%',
        3 * 3600 + 5 * 60 + 33: 'INFO payments-db: accepting writes again',
        3 * 3600 + 22 * 60 + 10: 'INFO checkout: payment authorisation success rate back to 99.2%',
        3 * 3600 + 41 * 60 + 0: 'INFO oncall: INC-4471 resolved, all services nominal',
    }
    while t < 3 * 3600 + 50 * 60:
        for at in sorted(k for k in events if t <= k < t + 5):
            lines.append(f'2026-11-14 {at // 3600:02d}:{at % 3600 // 60:02d}:{at % 60:02d} {events[at]}')
        svc = rng.choice(SERVICES)
        roll = rng.random()
        if roll < 0.12:
            lvl, msg = rng.choice(['WARN', 'ERROR']), rng.choice(noise_err)
        else:
            lvl, msg = 'INFO', f'handled {rng.randint(20, 900)} requests p95={rng.randint(40, 400)}ms'
        lines.append(f'2026-11-14 {t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d} {lvl} {svc}: {msg}')
        t += 5
    (ROOT / 'incident_log.txt').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    make_refactor()
    make_log()
    print('fixtures written')
