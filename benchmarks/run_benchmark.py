"""Reproducible live benchmark for Tandem MCP.

Measures wall-clock latency, local executor tokens, orchestrator character/token
compression, citation verification, and task acceptance against a live local
model server using an isolated temporary TANDEM_HOME (cache disabled).

Usage:
    .venv/bin/python benchmarks/run_benchmark.py
"""
import json
import os
import platform
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['TANDEM_HOME'] = tempfile.mkdtemp(prefix='tandem-bench-')

from tandem_mcp import agent, digest, engine, sandbox, server, store  # noqa: E402

CHARS_PER_TOKEN = store.CHARS_PER_TOKEN


def est_tokens(n_chars):
    return round(n_chars / CHARS_PER_TOKEN)


def bench_digest_file(label, path, question, grep='', max_words=100):
    text = sandbox.read_text(path)
    t0 = time.perf_counter()
    res = digest.answer(text, question, max_words=max_words, grep=grep, tool='digest_file', cache=False)
    rendered = digest.render(res, path.name)
    dt = time.perf_counter() - t0
    in_chars = len(text)
    out_chars = len(rendered)
    saved_tok = max(0, est_tokens(in_chars - out_chars))
    pct = 100.0 * (in_chars - out_chars) / in_chars if in_chars else 0.0
    return {
        'scenario': label,
        'tool': f'digest_file{" (grep)" if grep else ""}',
        'in_chars': in_chars,
        'out_chars': out_chars,
        'cloud_in_est': est_tokens(in_chars),
        'cloud_out_est': est_tokens(out_chars),
        'saved_tok_est': saved_tok,
        'saved_pct': round(pct, 1),
        'local_tokens': res['tokens'],
        'seconds': round(dt, 2),
        'quotes_ok': len(res['evidence']),
        'quotes_bad': res['rejected'],
        'claim_status': res.get('claim_supported', 'n/a'),
        'read_lines': f"{res['read_lines']}/{res['lines']}",
    }


def bench_digest_many(label, folder, glob, question, max_files=10, max_words_each=30):
    t0 = time.perf_counter()
    files = sandbox.walk(folder, glob, max_files)
    in_chars = 0
    for rel in files:
        try:
            in_chars += len(sandbox.read_text(folder / rel, 400_000))
        except Exception:
            pass
    # Clear cache first so every file is genuinely read by the local model
    store.cleanup(cache_keep=0, jobs_keep=0)
    rendered = server.digest_many(str(folder), glob, question, max_files=max_files, max_words_each=max_words_each)
    dt = time.perf_counter() - t0
    rows = [r for r in store.ledger(1) if r.get('tool') == 'digest_many' and r.get('kind') == 'llm']
    local_tok = sum(r.get('prompt_tokens', 0) + r.get('completion_tokens', 0) for r in rows)
    res_rows = [r for r in store.ledger(1) if r.get('tool') == 'digest_many' and r.get('kind') == 'result']
    q_ok = res_rows[-1].get('quotes_ok', 0) if res_rows else 0
    q_bad = res_rows[-1].get('quotes_bad', 0) if res_rows else 0
    out_chars = len(rendered)
    saved_tok = max(0, est_tokens(in_chars - out_chars))
    pct = 100.0 * (in_chars - out_chars) / in_chars if in_chars else 0.0
    return {
        'scenario': label,
        'tool': f'digest_many ({len(files)} files)',
        'in_chars': in_chars,
        'out_chars': out_chars,
        'cloud_in_est': est_tokens(in_chars),
        'cloud_out_est': est_tokens(out_chars),
        'saved_tok_est': saved_tok,
        'saved_pct': round(pct, 1),
        'local_tokens': local_tok,
        'seconds': round(dt, 2),
        'quotes_ok': q_ok,
        'quotes_bad': q_bad,
        'claim_status': 'checked',
        'read_lines': f'{len(files)} files',
    }


def bench_delegate(label, setup_fn, goal, write_globs, verify_commands, max_steps=12):
    ws_dir = Path(tempfile.mkdtemp(prefix='tandem-bench-ws-'))
    in_chars = setup_fn(ws_dir)
    ws = sandbox.Workspace(ws_dir, write_globs=write_globs)
    t0 = time.perf_counter()
    job = agent.start(goal, ws, verify_commands, max_steps=max_steps, max_repairs=1)
    agent.RUNNING[job][0].join(240)
    dt = time.perf_counter() - t0
    data = store.read_job(job) or {}
    receipt = server._receipt(job)
    out_chars = len(receipt)
    # Without Tandem, the cloud model reads the workspace files + failing test output (~600 chars)
    baseline_chars = in_chars + 600
    saved_tok = est_tokens(baseline_chars - out_chars)
    pct = 100.0 * (baseline_chars - out_chars) / baseline_chars if baseline_chars else 0.0
    return {
        'scenario': label,
        'tool': 'delegate',
        'in_chars': baseline_chars,
        'out_chars': out_chars,
        'cloud_in_est': est_tokens(baseline_chars),
        'cloud_out_est': est_tokens(out_chars),
        'saved_tok_est': saved_tok,
        'saved_pct': round(pct, 1),
        'local_tokens': data.get('tokens', 0),
        'seconds': round(dt, 2),
        'state': data.get('state', 'unknown'),
        'steps': data.get('steps', 0),
        'repairs': data.get('repairs', 0),
    }


def setup_micro(ws_dir):
    f1 = ws_dir / 'math_utils.py'
    f2 = ws_dir / 'test_math_utils.py'
    f1.write_text('def clamp(value, low, high):\n    if value < low:\n        return high\n    if value > high:\n        return high\n    return value\n')
    f2.write_text(
        'import unittest\nfrom math_utils import clamp\n\n'
        'class TestClamp(unittest.TestCase):\n'
        '    def test_within(self): self.assertEqual(clamp(5, 0, 10), 5)\n'
        '    def test_low(self): self.assertEqual(clamp(-3, 0, 10), 0)\n'
        '    def test_high(self): self.assertEqual(clamp(15, 0, 10), 10)\n\n'
        'if __name__ == "__main__":\n    unittest.main()\n'
    )
    return len(f1.read_text()) + len(f2.read_text())


def setup_realistic(ws_dir):
    # A multi-file mini project (~6 KB total) where only config_loader.py needs a fix
    (ws_dir / 'models.py').write_text(
        'from dataclasses import dataclass\n\n'
        '@dataclass\nclass Endpoint:\n    host: str\n    port: int\n    tls: bool = True\n'
        '    timeout_s: float = 30.0\n    retries: int = 3\n\n'
        '    def url(self) -> str:\n'
        '        scheme = "https" if self.tls else "http"\n'
        '        return f"{scheme}://{self.host}:{self.port}"\n\n'
        + '\n'.join(f'# domain helper {i}: validates field_{i} constraints' for i in range(40)) + '\n'
    )
    (ws_dir / 'formatter.py').write_text(
        'def format_summary(ep, ok: bool) -> str:\n'
        '    status = "OK" if ok else "FAIL"\n'
        '    return f"[{status}] {ep.url()} (timeout={ep.timeout_s}s, retries={ep.retries})"\n\n'
        + '\n'.join(f'# formatting rule {i}: keep ASCII output compact' for i in range(40)) + '\n'
    )
    (ws_dir / 'config_loader.py').write_text(
        'from models import Endpoint\n\n'
        'def parse_endpoint(raw: dict) -> Endpoint:\n'
        '    host = str(raw.get("host", "localhost"))\n'
        '    port = int(raw.get("port", 8080))\n'
        '    tls = str(raw.get("tls", "true")).lower() == "true"\n'
        '    timeout_s = float(raw.get("timeout_s", 30.0))\n'
        '    retries = int(raw.get("retries", 3))\n'
        '    # BUG: returns default port 8080 instead of parsed port when tls is False\n'
        '    if not tls:\n'
        '        port = 8080\n'
        '    return Endpoint(host=host, port=port, tls=tls, timeout_s=timeout_s, retries=retries)\n'
    )
    (ws_dir / 'test_config.py').write_text(
        'import unittest\nfrom config_loader import parse_endpoint\nfrom formatter import format_summary\n\n'
        'class TestConfig(unittest.TestCase):\n'
        '    def test_tls_endpoint(self):\n'
        '        ep = parse_endpoint({"host": "api.local", "port": 8443, "tls": "true"})\n'
        '        self.assertEqual(ep.url(), "https://api.local:8443")\n\n'
        '    def test_plain_custom_port(self):\n'
        '        ep = parse_endpoint({"host": "api.local", "port": 9000, "tls": "false"})\n'
        '        self.assertEqual(ep.url(), "http://api.local:9000")\n'
        '        self.assertIn("http://api.local:9000", format_summary(ep, True))\n\n'
        'if __name__ == "__main__":\n    unittest.main()\n'
    )
    return sum(len(p.read_text()) for p in ws_dir.glob('*.py'))


def main():
    srv = engine.connect(refresh=True)
    model = engine.default_model()
    caps = engine.probe(model)
    ctx = engine.context_tokens(model)
    jail = sandbox.describe_jail()
    print(f'Server: {srv["name"]} ({srv["url"]}) | Model: {model} | Context: {ctx} | Caps: {caps}')
    print(f'Sandbox: {jail}\n')

    digest_rows = []
    digest_rows.append(bench_digest_file(
        'Full-file doc QA (`README.md`)',
        ROOT / 'README.md',
        'What environment variables configure the sandbox mode and network access?',
    ))
    print('Done 1/5:', digest_rows[-1])

    digest_rows.append(bench_digest_file(
        'Targeted grep QA (`agent.py`)',
        ROOT / 'tandem_mcp/agent.py',
        'What does rollback do when a pre-existing file has None in snapshot.json?',
        grep='too large',
    ))
    print('Done 2/5:', digest_rows[-1])

    digest_rows.append(bench_digest_many(
        'Multi-file package survey (`tandem_mcp/*.py`)',
        ROOT / 'tandem_mcp',
        '*.py',
        'What is the main responsibility of this module?',
        max_files=10,
        max_words_each=25,
    ))
    print('Done 3/5:', digest_rows[-1])

    del_rows = []
    del_rows.append(bench_delegate(
        'Micro bugfix (1 tiny file, 6 lines)',
        setup_micro,
        'Fix clamp() in math_utils.py so values below low return low instead of high.',
        ['math_utils.py'],
        ['python3 -m unittest test_math_utils.py'],
    ))
    print('Done 4/5:', del_rows[-1])

    del_rows.append(bench_delegate(
        'Multi-file bugfix (`config_loader.py` + 3 other files)',
        setup_realistic,
        'Fix parse_endpoint() in config_loader.py so it keeps the parsed port when tls is False instead of overwriting it with 8080.',
        ['config_loader.py'],
        ['python3 -m unittest test_config.py'],
    ))
    print('Done 5/5:', del_rows[-1])

    report = {
        'date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'platform': f'{platform.system()} {platform.machine()} / Python {platform.python_version()}',
        'server': srv['name'],
        'model': model,
        'context': ctx,
        'caps': caps,
        'sandbox': jail,
        'digest': digest_rows,
        'delegate': del_rows,
    }
    out_json = ROOT / 'benchmarks/latest.json'
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2) + '\n')
    print('\nSaved raw results to', out_json)


if __name__ == '__main__':
    main()
