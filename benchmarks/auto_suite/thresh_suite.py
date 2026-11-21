"""Targeted suite for refactoring vs from-scratch generation thresholds (dev_t + frozen eval_t)."""
from __future__ import annotations

import json
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
# DEV_T builders (3 refactoring + 3 gen_scratch)
# ---------------------------------------------------------------------------

def b_devt_ref_small(ws: Path) -> None:
    _write(ws, "tags.py", '''def clean_tags(raw):
    return [t.strip().lower().replace(" ", "-") for t in raw if t.strip()]
''')
    _write(ws, "search.py", '''def match_tag(query, candidates):
    q = query.strip().lower().replace(" ", "-")
    return [c for c in candidates if c.strip().lower().replace(" ", "-") == q]
''')
    _write(ws, "test_tags.py", '''import unittest
import tags, search
class TestTags(unittest.TestCase):
    def test_tags(self):
        self.assertEqual(tags.clean_tags([" Py ", "Data Sci"]), ["py", "data-sci"])
        self.assertEqual(search.match_tag(" Data Sci ", ["data sci", "ml"]), ["data sci"])
if __name__ == "__main__":
    unittest.main()
''')


def b_devt_ref_many_mech(ws: Path) -> None:
    for i in range(8):
        _write(ws, f"mod_{i}.py", f'''def get_status_code(code):
    return f"S-{i}-{{code}}"
''')
    imports = "\n".join(f"import mod_{i}" for i in range(8))
    checks = "\n        ".join(f'self.assertEqual(mod_{i}.fetch_status_code(200), "S-{i}-200")' for i in range(8))
    _write(ws, "test_mods.py", f'''import unittest
{imports}
class TestMods(unittest.TestCase):
    def test_old_still_present_until_renamed(self):
        self.assertEqual(mod_0.get_status_code(200), "S-0-200")
if __name__ == "__main__":
    unittest.main()
''')


def b_devt_ref_dep(ws: Path) -> None:
    _write(ws, "h_auth.py", '''def run(user):
    if not user:
        return {"ok": False, "data": None, "error": "no user"}
    return {"ok": True, "data": {"user": user}, "error": None}
''')
    _write(ws, "h_item.py", '''def run(item_id):
    if item_id <= 0:
        return {"ok": False, "data": None, "error": "bad id"}
    return {"ok": True, "data": {"id": item_id}, "error": None}
''')
    _write(ws, "h_pay.py", '''def run(amount):
    if amount <= 0:
        return {"ok": False, "data": None, "error": "bad amount"}
    return {"ok": True, "data": {"paid": amount}, "error": None}
''')
    _write(ws, "test_handlers.py", '''import unittest
import h_auth, h_item, h_pay
class TestHandlers(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(h_auth.run("ada")["ok"], True)
        self.assertEqual(h_item.run(5)["data"]["id"], 5)
        self.assertEqual(h_pay.run(10)["ok"], True)
if __name__ == "__main__":
    unittest.main()
''')


def b_devt_gen_small(ws: Path) -> None:
    _write(ws, "README.txt", "Small in-memory KV store with TTL.\n")


def b_devt_gen_med_few(ws: Path) -> None:
    _write(ws, "README.txt", "Mini Markdown to HTML converter in Python.\n")


def b_devt_gen_large_web(ws: Path) -> None:
    _write(ws, "README.txt", "Interactive N-body gravity HTML5 Canvas simulation.\n")


# ---------------------------------------------------------------------------
# EVAL_T builders (frozen held-out set: 2 refactoring + 2 gen_scratch + 1 simple)
# ---------------------------------------------------------------------------

def b_evalt_ref_many_mech(ws: Path) -> None:
    for i in range(7):
        _write(ws, f"svc_{i}.py", f'''DEFAULT_CURRENCY = "EUR"
def compute_fee(amount, currency=DEFAULT_CURRENCY):
    return f"{{currency}} {{amount * 0.02:.2f}}"
''')
    _write(ws, "test_svcs.py", '''import unittest
import svc_0, svc_6
class TestSvcs(unittest.TestCase):
    def test_fee(self):
        self.assertEqual(svc_0.compute_fee(100), "EUR 2.00")
        self.assertEqual(svc_6.compute_fee(100, "USD"), "USD 2.00")
if __name__ == "__main__":
    unittest.main()
''')


def b_evalt_ref_complex(ws: Path) -> None:
    _write(ws, "steps.py", '''def step_trim(s):
    return s.strip()
def step_upper(s):
    return s.upper()
''')
    _write(ws, "pipeline.py", '''from steps import step_trim, step_upper
def run_pipeline(text):
    return step_upper(step_trim(text))
''')
    _write(ws, "test_pipeline.py", '''import unittest
from pipeline import run_pipeline
class TestPipeline(unittest.TestCase):
    def test_run(self):
        self.assertEqual(run_pipeline("  hi  "), "HI")
if __name__ == "__main__":
    unittest.main()
''')


def b_evalt_gen_med_few(ws: Path) -> None:
    _write(ws, "README.txt", "Recursive-descent math expression evaluator.\n")


def b_evalt_gen_web_app(ws: Path) -> None:
    _write(ws, "README.txt", "Interactive Conway Game of Life HTML5 Canvas app.\n")


def b_evalt_simple_check(ws: Path) -> None:
    _write(ws, "budgets.json", json.dumps({"items": [{"name": "a", "cost": 15}, {"name": "b", "cost": 25}, {"name": "c", "cost": 60}], "currency": "EUR"}) + "\n")


# ---------------------------------------------------------------------------
# Case Definitions
# ---------------------------------------------------------------------------

THRESH_CASES: list[dict[str, Any]] = [
    # --- DEV_T ---
    {
        "id": "devt_ref_small",
        "split": "dev_t",
        "family": "refactoring",
        "size_hint": "small_2files",
        "budget_s": 240,
        "read_only": False,
        "prompt": "Estrai una funzione condivisa normalize_tag(text) in norm.py e usala sia in tags.py sia in search.py, mantenendo verdi i test di python3 -m unittest -v test_tags.py.",
        "builder": b_devt_ref_small,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_tags.py", "extra_py": "import norm, tags, search, inspect\nassert norm.normalize_tag(' Data Sci ')=='data-sci'\nassert 'normalize_tag' in inspect.getsource(tags) and 'normalize_tag' in inspect.getsource(search)"},
    },
    {
        "id": "devt_ref_many_mech",
        "split": "dev_t",
        "family": "refactoring",
        "size_hint": "many_files_mechanical_8files",
        "budget_s": 360,
        "read_only": False,
        "prompt": "In tutti gli 8 moduli mod_0.py..mod_7.py rinomina get_status_code(code) in fetch_status_code(code, prefix='') (se prefix è non vuoto antepone f'{prefix}:'), aggiorna test_mods.py affinché testi tutti gli 8 moduli e verifica che python3 -m unittest -v test_mods.py passi.",
        "builder": b_devt_ref_many_mech,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_mods.py", "extra_py": "import importlib\nfor i in range(8):\n m=importlib.import_module(f'mod_{i}')\n assert hasattr(m,'fetch_status_code') and not hasattr(m,'get_status_code')\n assert m.fetch_status_code(200)==f'S-{i}-200' and m.fetch_status_code(200,'OK')==f'OK:S-{i}-200'"},
    },
    {
        "id": "devt_ref_dep",
        "split": "dev_t",
        "family": "refactoring",
        "size_hint": "medium_4files_contract",
        "budget_s": 420,
        "read_only": False,
        "prompt": "Crea envelope.py con la classe ResultEnvelope(ok, data=None, error=None) e metodo to_dict(), aggiorna h_auth.py, h_item.py e h_pay.py affinché i loro run() restituiscano ResultEnvelope.to_dict() e aggiungi test su envelope.py in test_handlers.py verificando python3 -m unittest -v test_handlers.py.",
        "builder": b_devt_ref_dep,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_handlers.py", "extra_py": "import envelope, h_auth, h_item, h_pay, inspect\nassert envelope.ResultEnvelope(True, {'x':1}).to_dict()=={'ok':True,'data':{'x':1},'error':None}\nfor m in (h_auth, h_item, h_pay): assert 'ResultEnvelope' in inspect.getsource(m)"},
    },
    {
        "id": "devt_gen_small",
        "split": "dev_t",
        "family": "gen_scratch",
        "size_hint": "small_kv",
        "budget_s": 240,
        "read_only": False,
        "prompt": "Crea da zero kv_store.py con classe KVStore (metodi set(key, val, ttl=None, now=0), get(key, now=0), delete(key), keys(now=0)) e test_kv_store.py con almeno 6 test, poi verifica che python3 -m unittest -v test_kv_store.py passi.",
        "builder": b_devt_gen_small,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_kv_store.py", "extra_py": "from kv_store import KVStore\ns=KVStore(); s.set('a',1,ttl=5,now=10); assert s.get('a',now=14)==1 and s.get('a',now=15) is None; s.set('b',2); assert s.delete('b') is True and s.get('b') is None"},
    },
    {
        "id": "devt_gen_med_few",
        "split": "dev_t",
        "family": "gen_scratch",
        "size_hint": "medium_few_files_rich_logic",
        "budget_s": 480,
        "read_only": False,
        "prompt": "Crea da zero mini_markdown.py con funzione render_html(md_text) che supporta: HTML-escaping sicuro dei caratteri < > &, titoli #..###, grassetto **x** e corsivo *x*, codice inline `x` e blocchi ```...```, blockquote >, liste non ordinate - e link [testo](url), più test_mini_markdown.py con almeno 12 test reali; verifica che python3 -m unittest -v test_mini_markdown.py passi.",
        "builder": b_devt_gen_med_few,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_mini_markdown.py", "extra_py": "from mini_markdown import render_html\nh=render_html('# Hi\\n\\n**b** *i* `c` [L](https://x.io)\\n\\n- one\\n- two\\n\\n> q\\n\\n```\\n<tag>&\\n```')\nassert '<h1>Hi</h1>' in h and '<strong>b</strong>' in h and '<em>i</em>' in h and '<code>c</code>' in h and '<a href=\"https://x.io\">L</a>' in h and '<li>one</li>' in h and '<blockquote>' in h and '&lt;tag&gt;&amp;' in h"},
    },
    {
        "id": "devt_gen_large_web",
        "split": "dev_t",
        "family": "gen_scratch",
        "budget_s": 600,
        "size_hint": "large_web_app",
        "read_only": False,
        "prompt": "Crea da zero index.html con una simulazione HTML5 Canvas interattiva di gravità N-corpi in spazio scuro (#060913): almeno 6 corpi orbitanti con scie sfumate, stella centrale luminosa, HUD glassmorphism (FPS, tempo simulato in s, numero corpi), pulsanti Pause/Resume, Trails ON/OFF, Reset, slider velocità (0.2..3.0, step 0.1, default 1.0) e click sul canvas per aggiungere un nuovo corpo con velocità iniziale. Zero dipendenze esterne e zero errori JavaScript.",
        "builder": b_devt_gen_large_web,
        "eval_type": "web_widget",
        "eval_spec": {},
    },

    # --- FROZEN EVAL_T ---
    {
        "id": "evalt_ref_many_mech",
        "split": "eval_t",
        "family": "refactoring",
        "size_hint": "many_files_mechanical_7files",
        "budget_s": 360,
        "read_only": False,
        "prompt": "Crea currency.py con DEFAULT_CURRENCY='EUR', e in tutti i 7 moduli svc_0.py..svc_6.py importa DEFAULT_CURRENCY da currency.py e rinomina compute_fee in calculate_fee; aggiorna test_svcs.py per testare tutti i 7 moduli e verifica che python3 -m unittest -v test_svcs.py passi.",
        "builder": b_evalt_ref_many_mech,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_svcs.py", "extra_py": "import importlib, currency\nassert currency.DEFAULT_CURRENCY=='EUR'\nfor i in range(7):\n m=importlib.import_module(f'svc_{i}')\n assert hasattr(m,'calculate_fee') and not hasattr(m,'compute_fee')\n assert m.calculate_fee(100)=='EUR 2.00'"},
    },
    {
        "id": "evalt_ref_complex",
        "split": "eval_t",
        "family": "refactoring",
        "size_hint": "medium_3files_design",
        "budget_s": 420,
        "read_only": False,
        "prompt": "Rifattorizza pipeline.py e steps.py introducendo una classe PipelineBuilder (metodi add_step(fn), validate(), run(text) che solleva ValueError se non ci sono step o se text non è str), aggiungi step_reverse in steps.py e aggiorna test_pipeline.py con almeno 5 test verificando python3 -m unittest -v test_pipeline.py.",
        "builder": b_evalt_ref_complex,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_pipeline.py", "extra_py": "import pipeline, steps\np=pipeline.PipelineBuilder().add_step(steps.step_trim).add_step(steps.step_upper).add_step(steps.step_reverse)\nassert p.run('  ab ')=='BA'\ntry:\n pipeline.PipelineBuilder().run('x'); raise AssertionError('expected ValueError')\nexcept ValueError: pass"},
    },
    {
        "id": "evalt_gen_med_few",
        "split": "eval_t",
        "family": "gen_scratch",
        "size_hint": "medium_few_files_rich_logic",
        "budget_s": 480,
        "read_only": False,
        "prompt": "Crea da zero expr_eval.py con lexer, parser recursive-descent e funzione evaluate(expr, env=None) che supporta numeri int/float, + - * / ** unario -, parentesi, variabili da env, funzioni min/max/abs/pow e solleva ValueError su errori di sintassi o divisione per zero, più test_expr_eval.py con almeno 12 test; verifica che python3 -m unittest -v test_expr_eval.py passi.",
        "builder": b_evalt_gen_med_few,
        "eval_type": "python_test",
        "eval_spec": {"test_cmd": "python3 -m unittest -v test_expr_eval.py", "extra_py": "from expr_eval import evaluate\nassert evaluate('2 + 3 * (4 - 1) ** 2') == 29\nassert evaluate('max(abs(-5), pow(2, x))', {'x': 3}) == 8\ntry:\n evaluate('1 / 0'); raise AssertionError('expected ValueError')\nexcept ValueError: pass"},
    },
    {
        "id": "evalt_gen_web_app",
        "split": "eval_t",
        "family": "gen_scratch",
        "size_hint": "large_web_app",
        "budget_s": 600,
        "read_only": False,
        "prompt": "Crea da zero index.html con un automa cellulare interattivo Conway Game of Life su HTML5 Canvas a tutto schermo (#080c18), HUD glassmorphism (FPS, generazione, celle vive), pulsanti Play/Pause, Step, Randomize, Clear, slider velocità (1..30) e click/drag per disegnare celle. Zero dipendenze esterne e zero errori JavaScript.",
        "builder": b_evalt_gen_web_app,
        "eval_type": "gol_web",
        "eval_spec": {},
    },
    {
        "id": "evalt_simple_check",
        "split": "eval_t",
        "family": "extract_count",
        "size_hint": "simple_extract",
        "budget_s": 120,
        "read_only": True,
        "prompt": "Estrai da budgets.json il numero di oggetti in items, la somma esatta di cost e currency, rispondendo con un JSON avente chiavi count, total_cost, currency, senza modificare file.",
        "builder": b_evalt_simple_check,
        "eval_type": "extract",
        "eval_spec": {"expected": {"count": 3, "total_cost": 100, "currency": "EUR"}},
    },
]
