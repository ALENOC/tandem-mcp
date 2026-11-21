"""Representative 6-family benchmark suite (dev + frozen eval split) for Tandem Auto Mode."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SUITE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SUITE_ROOT.parents[1]


def _write(ws: Path, rel: str, text: str) -> None:
    p = ws / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixture builders (clean isolated workspace per attempt)
# ---------------------------------------------------------------------------

def build_dev_explain_small(ws: Path) -> None:
    _write(ws, "cache.py", '''"""Tiny LRU-like cache."""
class MiniCache:
    def __init__(self, cap=4):
        self.cap = cap
        self.items = {}
        self.order = []

    def _evict_oldest(self):
        if self.order:
            k = self.order.pop(0)
            self.items.pop(k, None)

    def put(self, key, val):
        if key not in self.items and len(self.order) >= self.cap:
            self._evict_oldest()
        if key in self.order:
            self.order.remove(key)
        self.items[key] = val
        self.order.append(key)
''')
    _write(ws, "service.py", '''from cache import MiniCache
c = MiniCache(cap=2)
def store_user(uid, name):
    c.put(uid, name)
''')


def build_eval_explain_large(ws: Path) -> None:
    # ~42KB across 6 modules so router sees substantial read volume
    pad = "\n".join(f"# padding comment line {i}: pipeline validation metadata" for i in range(180))
    _write(ws, "errors.py", f'''class ValidationError(Exception):
    def __init__(self, field, reason):
        super().__init__(f"{{field}}: {{reason}}")
        self.field = field
        self.reason = reason
{pad}
''')
    _write(ws, "schema.py", f'''from errors import ValidationError
def check_positive(name, val):
    if not isinstance(val, (int, float)) or val <= 0:
        raise ValidationError(name, "must be positive")
{pad}
''')
    _write(ws, "ingest.py", f'''from schema import check_positive
def parse_order(row):
    check_positive("amount", row.get("amount"))
    return {{"id": row["id"], "amount": row["amount"]}}
{pad}
''')
    _write(ws, "pipeline.py", f'''from ingest import parse_order
from errors import ValidationError
def run_batch(rows):
    accepted, rejected = [], []
    for r in rows:
        try:
            accepted.append(parse_order(r))
        except ValidationError as exc:
            rejected.append({{"field": exc.field, "reason": exc.reason}})
    return {{"accepted": accepted, "rejected": rejected}}
{pad}
''')
    _write(ws, "audit.py", f'''def summarize(res):
    return len(res["accepted"]), len(res["rejected"])
{pad}
''')
    _write(ws, "cli.py", f'''from pipeline import run_batch
def main(rows):
    return run_batch(rows)
{pad}
''')


def build_dev_extract_toml(ws: Path) -> None:
    _write(ws, "pyproject.toml", '''[project]
name = "sample-pkg"
version = "1.8.3"
dependencies = [
  "httpx>=0.27",
  "pydantic>=2.6",
  "uvicorn>=0.30",
]
''')
    _write(ws, "metrics.json", json.dumps({"batches": [14, 26, 40, 20]}, indent=2) + "\n")


def build_eval_extract_log_counts(ws: Path) -> None:
    lines = []
    services = ["auth", "billing", "billing", "worker", "auth", "billing"]
    for i in range(360):
        lvl = "ERROR" if i % 9 == 0 else ("INFO" if i % 3 else "WARN")
        svc = services[i % len(services)]
        lines.append(json.dumps({"ts": f"2026-11-19T10:{i//60:02d}:{i%60:02d}Z", "level": lvl, "service": svc, "msg": f"evt_{i}"}))
    lines[250] = json.dumps({"ts": "2026-11-19T10:04:10Z", "level": "CRITICAL", "service": "billing", "msg": "disk_full"})
    lines[350] = json.dumps({"ts": "2026-11-19T10:05:50Z", "level": "CRITICAL", "service": "auth", "msg": "token_expired"})
    _write(ws, "app.jsonl", "\n".join(lines) + "\n")


def build_dev_diag_offbyone(ws: Path) -> None:
    _write(ws, "pagination.py", '''def paginate(items, page, per_page):
    if page < 1 or per_page < 1:
        raise ValueError("invalid pagination")
    # BUG: off-by-one uses page instead of (page - 1)
    start = page * per_page
    return items[start:start + per_page]
''')
    _write(ws, "test_pagination.py", '''import unittest
from pagination import paginate
class TestPaginate(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(paginate([10, 20, 30, 40], 1, 2), [10, 20])
if __name__ == "__main__":
    unittest.main()
''')


def build_eval_diag_state_bug(ws: Path) -> None:
    pad = "\n".join(f"# scheduler internal docs {i}" for i in range(260))
    _write(ws, "scheduler.py", f'''import heapq
class PriorityQueue:
    def __init__(self):
        self._heap = []
        self._seq = 0
    def push(self, priority, task_id):
        # BUG: stores +priority in min-heap, so lower numeric priority pops first instead of highest priority
        heapq.heappush(self._heap, (priority, self._seq, task_id))
        self._seq += 1
    def pop(self):
        return heapq.heappop(self._heap)[2]
{pad}
''')
    _write(ws, "worker.py", f'''from scheduler import PriorityQueue
def dispatch_order(tasks):
    q = PriorityQueue()
    for tid, prio in tasks:
        q.push(prio, tid)
    out = []
    while q._heap:
        out.append(q.pop())
    return out
{pad}
''')
    _write(ws, "test_worker.py", f'''import unittest
from worker import dispatch_order
class TestWorker(unittest.TestCase):
    def test_high_priority_first(self):
        # higher numeric priority (10) should run before (1)
        self.assertEqual(dispatch_order([("low", 1), ("high", 10)]), ["high", "low"])
if __name__ == "__main__":
    unittest.main()
''')


def build_dev_edit_func(ws: Path) -> None:
    _write(ws, "retry.py", '''def compute_backoff(attempt, base_delay):
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    return base_delay * (2 ** attempt)
''')
    _write(ws, "test_retry.py", '''import unittest
from retry import compute_backoff
class TestRetry(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(compute_backoff(2, 0.5), 2.0)
    def test_negative_attempt(self):
        with self.assertRaises(ValueError):
            compute_backoff(-1, 1.0)
if __name__ == "__main__":
    unittest.main()
''')


def build_eval_edit_validator(ws: Path) -> None:
    pad = "\n".join(f"# config loader helper note {i}" for i in range(220))
    _write(ws, "config_loader.py", f'''def validate_config(cfg):
    if not isinstance(cfg, dict):
        raise ValueError("cfg must be dict")
    if not cfg.get("host"):
        raise ValueError("host required")
    return True
{pad}
''')
    _write(ws, "test_config_loader.py", '''import unittest
from config_loader import validate_config
class TestConfig(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_config({"host": "localhost", "port": 8080}))
    def test_missing_host(self):
        with self.assertRaises(ValueError):
            validate_config({"port": 8080})
if __name__ == "__main__":
    unittest.main()
''')


def build_dev_refactor_rename(ws: Path) -> None:
    _write(ws, "models.py", '''def fetch_record(store_map, key):
    return store_map.get(key)
''')
    _write(ws, "repo.py", '''from models import fetch_record
def get_user(db, uid):
    return fetch_record(db, uid)
''')
    _write(ws, "api.py", '''from models import fetch_record
def handle(db, uid):
    rec = fetch_record(db, uid)
    return {"found": rec is not None, "data": rec}
''')
    _write(ws, "test_app.py", '''import unittest
import api, repo
class TestApp(unittest.TestCase):
    def test_flow(self):
        db = {"u1": {"name": "Ada"}}
        self.assertEqual(repo.get_user(db, "u1")["name"], "Ada")
        self.assertTrue(api.handle(db, "u1")["found"])
if __name__ == "__main__":
    unittest.main()
''')


def build_eval_refactor_split(ws: Path) -> None:
    pad = "\n".join(f"# billing module note {i}" for i in range(90))
    _write(ws, "invoice.py", f'''def render_invoice(cents):
    return f"${{cents / 100:.2f}}"
{pad}
''')
    _write(ws, "receipt.py", f'''def render_receipt(cents):
    return f"PAID ${{cents / 100:.2f}}"
{pad}
''')
    _write(ws, "report.py", f'''def render_total(cents):
    return f"TOTAL=${{cents / 100:.2f}}"
{pad}
''')
    _write(ws, "cli.py", f'''from invoice import render_invoice
from receipt import render_receipt
from report import render_total
def summary(cents):
    return [render_invoice(cents), render_receipt(cents), render_total(cents)]
{pad}
''')
    _write(ws, "test_billing.py", '''import unittest
from cli import summary
class TestBilling(unittest.TestCase):
    def test_summary(self):
        self.assertEqual(summary(1250), ["$12.50", "PAID $12.50", "TOTAL=$12.50"])
if __name__ == "__main__":
    unittest.main()
''')


def build_dev_gen_cli(ws: Path) -> None:
    _write(ws, "README.txt", "Workspace for csv_stats CLI tool.\n")


def build_eval_gen_canvas_widget(ws: Path) -> None:
    _write(ws, "README.txt", "Workspace for interactive HTML5 Canvas wave simulator.\n")


# ---------------------------------------------------------------------------
# Case registry (dev vs frozen eval)
# ---------------------------------------------------------------------------

CASES: list[dict[str, Any]] = [
    # --- DEV SPLIT ---
    {
        "id": "dev_explain_small",
        "split": "dev",
        "family": "code_explain",
        "budget_s": 120,
        "read_only": True,
        "prompt": "Spiega brevemente come funziona la politica di eviction in cache.py e quali metodi la invocano, senza modificare file.",
        "builder": build_dev_explain_small,
        "eval_type": "explain",
        "eval_spec": {"required_all": [["_evict_oldest"], ["put"], ["pop(0)", "oldest", "primo", "cap"]]},
    },
    {
        "id": "dev_extract_toml",
        "split": "dev",
        "family": "extract_count",
        "budget_s": 120,
        "read_only": True,
        "prompt": "Estrai la versione da pyproject.toml, il numero esatto di dipendenze elencate e la somma esatta dei valori in batches dentro metrics.json. Rispondi con un oggetto JSON con chiavi version, dep_count, batches_sum, senza modificare file.",
        "builder": build_dev_extract_toml,
        "eval_type": "extract",
        "eval_spec": {"expected": {"version": "1.8.3", "dep_count": 3, "batches_sum": 100}},
    },
    {
        "id": "dev_diag_offbyone",
        "split": "dev",
        "family": "bug_diagnosis",
        "budget_s": 150,
        "read_only": True,
        "prompt": "Diagnostica perché test_pagination.py fallisce in pagination.py, indicando file, riga/espressione errata e correzione necessaria, senza modificare file.",
        "builder": build_dev_diag_offbyone,
        "eval_type": "explain",
        "eval_spec": {"required_all": [["pagination.py"], ["page - 1", "page-1", "start = page * per_page"]]},
    },
    {
        "id": "dev_edit_func",
        "split": "dev",
        "family": "targeted_edit",
        "budget_s": 240,
        "read_only": False,
        "prompt": "Aggiorna compute_backoff in retry.py in modo che sollevi ValueError se base_delay <= 0, aggiungi un test in test_retry.py e verifica che python3 -m unittest -v test_retry.py passi.",
        "builder": build_dev_edit_func,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_retry.py", "extra_py": "from retry import compute_backoff\nimport unittest\ntry:\n compute_backoff(0, 0)\n raise AssertionError('expected ValueError')\nexcept ValueError:\n pass\nassert compute_backoff(2, 0.5) == 2.0"},
    },
    {
        "id": "dev_refactor_rename",
        "split": "dev",
        "family": "multi_refactor",
        "budget_s": 420,
        "read_only": False,
        "prompt": "Rinomina fetch_record in load_record su tutti i file (models.py, repo.py, api.py) e verifica che python3 -m unittest -v test_app.py continui a passare.",
        "builder": build_dev_refactor_rename,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_app.py", "extra_py": "import models, repo, api\nassert hasattr(models, 'load_record') and not hasattr(models, 'fetch_record')\nassert repo.get_user({'a': 1}, 'a') == 1"},
    },
    {
        "id": "dev_gen_cli",
        "split": "dev",
        "family": "gen_scratch",
        "budget_s": 420,
        "read_only": False,
        "prompt": "Crea da zero csv_stats.py (con funzione summarize_column(csv_path, col) che restituisce dict {count, min, max, mean} e CLI --file/--col) e test_csv_stats.py, poi verifica che python3 -m unittest -v test_csv_stats.py passi.",
        "builder": build_dev_gen_cli,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_csv_stats.py", "extra_py": "import tempfile, pathlib, csv_stats\np=pathlib.Path(tempfile.mkdtemp())/'d.csv'\np.write_text('x,y\\n1,10\\n2,20\\n3,30\\n')\nr=csv_stats.summarize_column(str(p),'y')\nassert r['count']==3 and r['min']==10 and r['max']==30 and abs(r['mean']-20)<1e-6"},
    },

    # --- FROZEN EVAL SPLIT ---
    {
        "id": "eval_explain_large",
        "split": "eval",
        "family": "code_explain",
        "budget_s": 240,
        "read_only": True,
        "prompt": "Spiega come vengono sollevati e propagati gli errori di validazione in questo progetto, indicando i file coinvolti e cosa restituisce run_batch per le righe non valide, senza modificare file.",
        "builder": build_eval_explain_large,
        "eval_type": "explain",
        "eval_spec": {"required_all": [["ValidationError"], ["schema.py"], ["ingest.py"], ["pipeline.py"], ["rejected"]]},
    },
    {
        "id": "eval_extract_log_counts",
        "split": "eval",
        "family": "extract_count",
        "budget_s": 120,
        "read_only": True,
        "prompt": "Conta in app.jsonl il numero esatto di eventi ERROR, quale servizio ha più eventi ERROR e l'ultima timestamp CRITICAL. Rispondi con JSON avente chiavi error_count, top_error_service, last_critical_ts, senza modificare file.",
        "builder": build_eval_extract_log_counts,
        "eval_type": "extract",
        "eval_spec": {"derive_from_jsonl": "app.jsonl"},
    },
    {
        "id": "eval_diag_state_bug",
        "split": "eval",
        "family": "bug_diagnosis",
        "budget_s": 240,
        "read_only": True,
        "prompt": "Trova la causa del bug per cui test_worker.py fallisce (i task a priorità maggiore non escono per primi), indicando file, metodo e causa esatta, senza modificare file.",
        "builder": build_eval_diag_state_bug,
        "eval_type": "explain",
        "eval_spec": {"required_all": [["scheduler.py"], ["push"], ["-priority", "min-heap", "min heap", "negat"]]},
    },
    {
        "id": "eval_edit_validator",
        "split": "eval",
        "family": "targeted_edit",
        "budget_s": 240,
        "read_only": False,
        "prompt": "Aggiorna validate_config in config_loader.py affinché verifichi anche che port sia un int compreso tra 1 e 65535 (escludendo bool), aggiungi un test in test_config_loader.py e verifica che python3 -m unittest -v test_config_loader.py passi.",
        "builder": build_eval_edit_validator,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_config_loader.py", "extra_py": "from config_loader import validate_config\nassert validate_config({'host':'a','port':80}) is True\nfor bad in [{'host':'a','port':0},{'host':'a','port':70000},{'host':'a','port':True}]:\n try:\n  validate_config(bad)\n  raise AssertionError(f'expected ValueError for {bad}')\n except ValueError:\n  pass"},
    },
    {
        "id": "eval_refactor_split",
        "split": "eval",
        "family": "multi_refactor",
        "budget_s": 480,
        "read_only": False,
        "prompt": "Estrai la formattazione valuta condivisa in un nuovo modulo formatting.py con format_currency(cents) e aggiornalo in invoice.py, receipt.py e report.py mantenendo verdi tutti i test di test_billing.py.",
        "builder": build_eval_refactor_split,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_billing.py", "extra_py": "import formatting, invoice, receipt, report, cli, inspect\nassert formatting.format_currency(1250) == '$12.50'\nassert cli.summary(1250) == ['$12.50', 'PAID $12.50', 'TOTAL=$12.50']\nfor m in (invoice, receipt, report):\n assert 'format_currency' in inspect.getsource(m)"},
    },
    {
        "id": "eval_gen_canvas_widget",
        "split": "eval",
        "family": "gen_scratch",
        "budget_s": 600,
        "read_only": False,
        "prompt": "Crea da zero index.html con una simulazione HTML5 Canvas interattiva di onde sinusoidali animate in dark mode (#0b1020), con pulsanti Pause/Resume e Reset, slider velocità (0.5..2.5) e 0 errori JavaScript.",
        "builder": build_eval_gen_canvas_widget,
        "eval_type": "web_widget",
        "eval_spec": {},
    },
]


def _expected_from_jsonl(jsonl_path: Path) -> dict[str, Any]:
    """Derive exact error_count, tied max services, and last_critical_ts directly from JSONL fixture."""
    from collections import Counter
    err_cnt = 0
    svc_counts: Counter[str] = Counter()
    last_crit = None
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("level") == "ERROR":
            err_cnt += 1
            svc_counts[str(row.get("service"))] += 1
        elif row.get("level") == "CRITICAL":
            last_crit = row.get("ts")
    max_svc = max(svc_counts.values(), default=0)
    top_services = sorted([s for s, c in svc_counts.items() if c == max_svc]) if max_svc > 0 else []
    return {
        "error_count": err_cnt,
        "top_error_service": top_services,
        "last_critical_ts": last_crit,
    }


def _expected_from_csv(csv_path: Path) -> dict[str, Any]:
    """Derive exact EU count, EU amount sum, and top product directly from CSV fixture."""
    import csv
    from collections import defaultdict
    eu_count = 0
    eu_sum = 0
    prod_rev: dict[str, int] = defaultdict(int)
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            amt = int(row["amount"])
            prod_rev[row["product"]] += amt
            if row["region"] == "EU":
                eu_count += 1
                eu_sum += amt
    max_rev = max(prod_rev.values(), default=0)
    top_prods = sorted([p for p, v in prod_rev.items() if v == max_rev]) if max_rev > 0 else []
    return {"eu_count": eu_count, "eu_amount_sum": eu_sum, "top_product": top_prods}


def build_eval2_explain_hooks(ws: Path) -> None:
    pad = "\n".join(f"# hook pipeline metadata {i}" for i in range(180))
    _write(ws, "hook_types.py", f'''from dataclasses import dataclass
@dataclass
class HookResult:
    abort: bool = False
    note: str = ""
{pad}
''')
    _write(ws, "registry.py", f'''class HookRegistry:
    def __init__(self):
        self._hooks = []
    def register(self, priority, fn):
        self._hooks.append((priority, fn))
        self._hooks.sort(key=lambda item: item[0])
    def iter_hooks(self):
        return [fn for _, fn in self._hooks]
{pad}
''')
    _write(ws, "runner.py", f'''from hook_types import HookResult
def execute_chain(registry, ctx):
    executed = []
    for fn in registry.iter_hooks():
        res = fn(ctx)
        executed.append(getattr(fn, "__name__", "hook"))
        if isinstance(res, HookResult) and res.abort:
            return {{"aborted": True, "executed": executed, "reason": res.note}}
    return {{"aborted": False, "executed": executed, "reason": ""}}
{pad}
''')
    _write(ws, "builtins_hooks.py", f'''from hook_types import HookResult
def auth_guard(ctx):
    if not ctx.get("user"):
        return HookResult(abort=True, note="missing user")
    return HookResult(abort=False)
{pad}
''')
    _write(ws, "app.py", f'''from runner import execute_chain
def handle(registry, ctx):
    return execute_chain(registry, ctx)
{pad}
''')


def build_eval2_extract_csv(ws: Path) -> None:
    rows = ["region,product,amount"]
    prods = ["core", "edge", "edge", "relay", "core", "edge"]
    regs = ["EU", "US", "EU", "APAC"]
    for i in range(240):
        reg = regs[i % len(regs)]
        prod = prods[i % len(prods)]
        amt = 10 + (i % 5) * 5 + (15 if prod == "edge" else 0)
        rows.append(f"{reg},{prod},{amt}")
    _write(ws, "sales.csv", "\n".join(rows) + "\n")


def build_eval2_diag_ttl(ws: Path) -> None:
    pad = "\n".join(f"# cache internals {i}" for i in range(220))
    _write(ws, "ttl_cache.py", f'''class TTLCache:
    def __init__(self):
        self._data = {{}}
    def set(self, key, value, now, ttl):
        self._data[key] = (value, now + ttl)
    def get(self, key, now):
        if key not in self._data:
            return None
        val, expires_at = self._data[key]
        # BUG: uses strictly greater (now > expires_at) instead of >=, and never deletes expired key
        if now > expires_at:
            return None
        return val
{pad}
''')
    _write(ws, "test_ttl_cache.py", f'''import unittest
from ttl_cache import TTLCache
class TestTTL(unittest.TestCase):
    def test_exact_expiry(self):
        c = TTLCache()
        c.set("k", "v", now=10, ttl=5)
        self.assertIsNone(c.get("k", now=15))
if __name__ == "__main__":
    unittest.main()
''')


def build_eval2_edit_slug(ws: Path) -> None:
    _write(ws, "slug.py", '''import re
def slugify(text, max_len=50):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s
''')
    _write(ws, "test_slug.py", '''import unittest
from slug import slugify
class TestSlug(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
if __name__ == "__main__":
    unittest.main()
''')


def build_eval2_refactor_logger(ws: Path) -> None:
    pad = "\n".join(f"# audit module {i}" for i in range(80))
    _write(ws, "auth.py", f'''def log_login(user):
    return f"[AUDIT] actor={{user}} action=login status=ok"
{pad}
''')
    _write(ws, "orders.py", f'''def log_order(user):
    return f"[AUDIT] actor={{user}} action=order status=created"
{pad}
''')
    _write(ws, "billing.py", f'''def log_charge(user):
    return f"[AUDIT] actor={{user}} action=charge status=paid"
{pad}
''')
    _write(ws, "test_audit.py", '''import unittest
import auth, orders, billing
class TestAudit(unittest.TestCase):
    def test_events(self):
        self.assertEqual(auth.log_login("ada"), "[AUDIT] actor=ada action=login status=ok")
        self.assertEqual(orders.log_order("ada"), "[AUDIT] actor=ada action=order status=created")
        self.assertEqual(billing.log_charge("ada"), "[AUDIT] actor=ada action=charge status=paid")
if __name__ == "__main__":
    unittest.main()
''')


def build_eval2_gen_particles(ws: Path) -> None:
    _write(ws, "README.txt", "Workspace for interactive bouncing/orbiting particles Canvas widget.\n")


CASES.extend([
    {
        "id": "eval2_explain_hooks",
        "split": "eval_v2",
        "family": "code_explain",
        "budget_s": 240,
        "read_only": True,
        "prompt": "Spiega in che ordine vengono eseguiti i hook in questo progetto e cosa succede quando un hook restituisce abort=True, citando i file coinvolti, senza modificare file.",
        "builder": build_eval2_explain_hooks,
        "eval_type": "explain",
        "eval_spec": {"required_all": [["registry.py"], ["runner.py"], ["priority"], ["abort"]]},
    },
    {
        "id": "eval2_extract_csv_sum",
        "split": "eval_v2",
        "family": "extract_count",
        "budget_s": 120,
        "read_only": True,
        "prompt": "Da sales.csv calcola il numero esatto di righe con region=EU, la somma esatta di amount per region=EU e il product con somma amount totale più alta. Rispondi con JSON avente chiavi eu_count, eu_amount_sum, top_product, senza modificare file.",
        "builder": build_eval2_extract_csv,
        "eval_type": "extract",
        "eval_spec": {"derive_from_csv": "sales.csv"},
    },
    {
        "id": "eval2_diag_cache_ttl",
        "split": "eval_v2",
        "family": "bug_diagnosis",
        "budget_s": 240,
        "read_only": True,
        "prompt": "Diagnostica perché test_ttl_cache.py fallisce quando now è esattamente uguale a expires_at, indicando file, metodo e condizione errata, senza modificare file.",
        "builder": build_eval2_diag_ttl,
        "eval_type": "explain",
        "eval_spec": {"required_all": [["ttl_cache.py"], ["get"], ["now > expires_at", ">=", "strictly"]]},
    },
    {
        "id": "eval2_edit_slugify",
        "split": "eval_v2",
        "family": "targeted_edit",
        "budget_s": 240,
        "read_only": False,
        "prompt": "Aggiorna slugify(text, max_len=50) in slug.py affinché tronchi a max_len senza lasciare trattini finali, aggiungi un test in test_slug.py e verifica che python3 -m unittest -v test_slug.py passi.",
        "builder": build_eval2_edit_slug,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_slug.py", "extra_py": "from slug import slugify\nassert slugify('hello---world')=='hello-world'\nres=slugify('a-b-c-d-e', max_len=4)\nassert len(res)<=4 and not res.endswith('-')"},
    },
    {
        "id": "eval2_refactor_logger",
        "split": "eval_v2",
        "family": "multi_refactor",
        "budget_s": 420,
        "read_only": False,
        "prompt": "Estrai la formattazione dei log di audit in un nuovo modulo audit_fmt.py con format_audit_event(actor, action, status) e aggiornalo in auth.py, orders.py e billing.py mantenendo verdi tutti i test di test_audit.py.",
        "builder": build_eval2_refactor_logger,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_audit.py", "extra_py": "import audit_fmt, auth, orders, billing, inspect\nassert audit_fmt.format_audit_event('u','act','ok')=='[AUDIT] actor=u action=act status=ok'\nfor m in (auth, orders, billing):\n assert 'format_audit_event' in inspect.getsource(m)"},
    },
    {
        "id": "eval2_gen_particles_canvas",
        "split": "eval_v2",
        "family": "gen_scratch",
        "budget_s": 480,
        "read_only": False,
        "prompt": "Crea da zero index.html con una simulazione HTML5 Canvas interattiva di particelle animate su sfondo scuro (#0a0f1e), con pulsanti Pause/Resume e Reset, slider velocità (0.5..3.0) e 0 errori JavaScript.",
        "builder": build_eval2_gen_particles,
        "eval_type": "web_widget",
        "eval_spec": {},
    },
])


def snapshot_before(ws: Path) -> dict[str, str]:
    out = {}
    for p in sorted(ws.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out[str(p.relative_to(ws))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def evaluate_case(case: dict[str, Any], ws: Path, response_text: str, before_hashes: dict[str, str]) -> dict[str, Any]:
    if case["read_only"]:
        after_hashes = snapshot_before(ws)
        if after_hashes != before_hashes:
            return {"correct": False, "reason": "read_only violation: workspace files modified"}

    etype = case["eval_type"]
    spec = case["eval_spec"]

    if etype == "explain":
        low = (response_text or "").lower()
        missing = []
        for group in spec["required_all"]:
            if not any(tok.lower() in low for tok in group):
                missing.append("/".join(group))
        return {"correct": len(missing) == 0, "reason": "ok" if not missing else f"missing key facts: {missing}"}

    if etype == "extract":
        if "derive_from_jsonl" in spec:
            exp = _expected_from_jsonl(ws / spec["derive_from_jsonl"])
        elif "derive_from_csv" in spec:
            exp = _expected_from_csv(ws / spec["derive_from_csv"])
        else:
            exp = spec["expected"]
        txt = (response_text or "").strip()
        # Try JSON object extraction from response
        m = re.findall(r"\{[^{}]*\}", txt, re.S)
        parsed = None
        for cand in reversed(m):
            try:
                obj = json.loads(cand)
                if all(k in obj for k in exp):
                    parsed = obj
                    break
            except Exception:
                pass
        if not parsed:
            return {"correct": False, "reason": "no matching JSON object with expected keys in response"}
        mismatches = {}
        for k, v in exp.items():
            got = parsed.get(k)
            if isinstance(v, list):
                if not v or type(got) is not type(v[0]) or got not in v:
                    mismatches[k] = (got, v)
            else:
                if type(got) is not type(v) or got != v:
                    mismatches[k] = (got, v)
        return {"correct": len(mismatches) == 0, "reason": "ok" if not mismatches else f"mismatches: {mismatches}"}

    if etype == "python_test":
        p1 = subprocess.run(spec["test_cmd"], shell=True, cwd=str(ws), capture_output=True, text=True, timeout=30)
        if p1.returncode != 0:
            return {"correct": False, "reason": f"test_cmd failed: {(p1.stderr or p1.stdout)[-250:]}"}
        p2 = subprocess.run([sys.executable, "-c", spec["extra_py"]], cwd=str(ws), capture_output=True, text=True, timeout=30)
        if p2.returncode != 0:
            return {"correct": False, "reason": f"independent check failed: {(p2.stderr or p2.stdout)[-250:]}"}
        return {"correct": True, "reason": "all unit and independent checks passed"}

    if etype == "web_widget":
        sys.path.insert(0, str(REPO_ROOT))
        from tandem_mcp import web_check
        wc_spec = web_check.spec_for(case["prompt"], ["index.html"])
        rc, out = web_check.run(ws, wc_spec, timeout_s=40)
        if rc != 0:
            return {"correct": False, "reason": out}
        html_txt = (ws / "index.html").read_text(encoding="utf-8", errors="replace") if (ws / "index.html").is_file() else ""
        has_pause = bool(re.search(r"pause|resume", html_txt, re.I))
        has_reset = bool(re.search(r"reset", html_txt, re.I))
        has_range = bool(re.search(r'type=["\']?range', html_txt, re.I))
        ok = has_pause and has_reset and has_range
        return {"correct": ok, "reason": out if ok else f"missing UI controls (pause={has_pause}, reset={has_reset}, range={has_range})"}

    if etype == "gol_web":
        checker = Path(__file__).resolve().with_name("check_gol_behavioral.mjs")
        p = subprocess.run(["node", str(checker), str(ws)], capture_output=True, text=True, timeout=60)
        try:
            data = json.loads(p.stdout)
            return {"correct": bool(data.get("correct")), "reason": data.get("reason", ""), "checks": data.get("checks", {})}
        except Exception:
            return {"correct": False, "reason": f"gol_web checker error (rc={p.returncode}): {(p.stderr or p.stdout)[-300:]}"}

    return {"correct": False, "reason": f"unknown eval_type {etype}"}
