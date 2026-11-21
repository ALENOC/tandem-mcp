"""Benchmark tasks: the same user request is given to the direct arm and to the Tandem arm.

Each task has a prompt, a time budget, an optional workspace setup and an independent evaluator that
neither arm sees. A result counts as a success only when the evaluator passes and the attempt ended
inside the budget.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _node_eval(script: str, ws: Path, timeout: int = 120) -> dict:
    try:
        proc = subprocess.run(["node", str(ROOT / script), str(ws)], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"passed": False, "failed": ["evaluator_timeout"], "reason": f"{script} timed out"}
    try:
        return {"raw": json.loads(proc.stdout), "rc": proc.returncode}
    except json.JSONDecodeError:
        return {"passed": False, "failed": ["evaluator_error"], "reason": (proc.stderr or proc.stdout)[-300:]}


def eval_orbital(ws: Path) -> dict:
    out = _node_eval("check_orbital_behavioral.mjs", ws)
    if "raw" not in out:
        return out
    reqs = out["raw"].get("requirements") or {}
    failed = [k for k, v in reqs.items() if v.get("status") != "Pass"]
    return {"passed": bool(out["raw"].get("passed")), "failed": failed,
            "reason": "; ".join(f"{k}: {reqs[k].get('evidence', '')}"[:160] for k in failed)}


def eval_portal(ws: Path) -> dict:
    out = _node_eval("check_portal_behavioral.mjs", ws)
    if "raw" not in out:
        return out
    d = out["raw"]
    failed = [k for k in ("startup", "canvasMotion", "interactions") if (d.get(k) or {}).get("status") != "passed"]
    if not d.get("visual_passed"):
        failed.append("visual")
    return {"passed": bool(d.get("functional_passed")) and bool(d.get("visual_passed")), "failed": failed,
            "reason": ((d.get("interactions") or {}).get("evidence") or "")[-240:] + f" visual={d.get('visual')}"}


def eval_boids(ws: Path) -> dict:
    out = _node_eval("check_boids_behavioral.mjs", ws, timeout=90)
    if "raw" not in out:
        return out
    d = out["raw"]
    failed = [k for k, v in (d.get("checks") or {}).items() if not (v is True or (isinstance(v, dict) and v.get("passed")))]
    return {"passed": bool(d.get("correct")), "failed": failed, "reason": str(d.get("reason", ""))[:300]}


CRON_CHECK = (
    "from datetime import datetime, timezone\n"
    "import pathlib, re\n"
    "from cron_sched import next_runs\n"
    "src = pathlib.Path('test_cron_sched.py').read_text(encoding='utf-8')\n"
    "assert len(re.findall(r'def\\s+test_', src)) >= 12, 'need >=12 unittest methods'\n"
    "r1 = next_runs('*/15 9-17 * * 1-5', datetime(2026, 11, 20, 8, 50, tzinfo=timezone.utc), 3)\n"
    "assert r1 == [datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc), datetime(2026, 11, 20, 9, 15, tzinfo=timezone.utc), "
    "datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)], r1\n"
    "r2 = next_runs('0 10 * * 1-5', datetime(2026, 11, 20, 11, 0, tzinfo=timezone.utc), 1)\n"
    "assert r2 == [datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)], r2\n"
    "r3 = next_runs('30 2 1 */3 *', datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc), 2)\n"
    "assert r3 == [datetime(2027, 1, 1, 2, 30, tzinfo=timezone.utc), datetime(2027, 4, 1, 2, 30, tzinfo=timezone.utc)], r3\n"
    "for bad in ('61 * * * *', '* * *', '0 25 * * *', '*/0 * * * *', '5-2 * * * *'):\n"
    "    try:\n"
    "        next_runs(bad, datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc), 1)\n"
    "        raise AssertionError(f'expected ValueError for {bad}')\n"
    "    except ValueError:\n"
    "        pass\n"
)


def eval_cron(ws: Path) -> dict:
    try:
        p1 = subprocess.run([sys.executable, "-m", "unittest", "test_cron_sched.py"], cwd=ws, capture_output=True,
                            text=True, timeout=60)
        if p1.returncode != 0:
            return {"passed": False, "failed": ["own_tests"], "reason": (p1.stderr or p1.stdout)[-300:]}
        p2 = subprocess.run([sys.executable, "-c", CRON_CHECK], cwd=ws, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {"passed": False, "failed": ["timeout"], "reason": "tests timed out"}
    if p2.returncode != 0:
        return {"passed": False, "failed": ["independent_check"], "reason": (p2.stderr or p2.stdout)[-300:]}
    return {"passed": True, "failed": [], "reason": "own tests and independent check pass"}


DISCOUNT_SRC = '''"""Price helpers used by the checkout."""


def apply_discount(price, percent):
    """Return price reduced by percent (0-100), rounded to 2 decimals.

    Raise ValueError when price is negative or percent is outside 0..100.
    """
    return round(price - price * percent, 2)


def total(items, percent=0):
    """Sum of (price, quantity) pairs after the discount."""
    return apply_discount(sum(p * q for p, q in items), percent)
'''

DISCOUNT_TEST = '''import unittest

from discount import apply_discount, total


class DiscountTest(unittest.TestCase):
    def test_ten_percent(self):
        self.assertEqual(apply_discount(200, 10), 180.0)

    def test_zero(self):
        self.assertEqual(apply_discount(19.99, 0), 19.99)

    def test_rounding(self):
        self.assertEqual(apply_discount(10, 33), 6.7)

    def test_invalid_percent(self):
        with self.assertRaises(ValueError):
            apply_discount(10, 120)

    def test_negative_price(self):
        with self.assertRaises(ValueError):
            apply_discount(-1, 10)

    def test_total(self):
        self.assertEqual(total([(10, 2), (5, 1)], 20), 20.0)


if __name__ == "__main__":
    unittest.main()
'''

DISCOUNT_CHECK = (
    "from discount import apply_discount, total\n"
    "assert apply_discount(100, 100) == 0.0\n"
    "assert apply_discount(99.99, 15) == 84.99\n"
    "for args in ((10, -1), (10, 100.5), (-0.01, 0)):\n"
    "    try:\n"
    "        apply_discount(*args)\n"
    "        raise AssertionError(args)\n"
    "    except ValueError:\n"
    "        pass\n"
    "assert total([], 50) == 0.0\n"
)


def setup_discount(ws: Path) -> None:
    (ws / "discount.py").write_text(DISCOUNT_SRC, encoding="utf-8")
    (ws / "test_discount.py").write_text(DISCOUNT_TEST, encoding="utf-8")


def eval_discount(ws: Path) -> dict:
    try:
        if (ws / "test_discount.py").read_text(encoding="utf-8") != DISCOUNT_TEST:
            return {"passed": False, "failed": ["tests_modified"], "reason": "test_discount.py was changed"}
        p1 = subprocess.run([sys.executable, "-m", "unittest", "test_discount.py"], cwd=ws, capture_output=True,
                            text=True, timeout=60)
        if p1.returncode != 0:
            return {"passed": False, "failed": ["tests"], "reason": (p1.stderr or p1.stdout)[-300:]}
        p2 = subprocess.run([sys.executable, "-c", DISCOUNT_CHECK], cwd=ws, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"passed": False, "failed": ["error"], "reason": str(exc)[:200]}
    if p2.returncode != 0:
        return {"passed": False, "failed": ["independent_check"], "reason": (p2.stderr or p2.stdout)[-300:]}
    return {"passed": True, "failed": [], "reason": "tests and independent check pass"}


TASKS = {
    "gen_portal": {
        "prompt": (ROOT / "fixtures" / "portal_prompt.txt").read_text(encoding="utf-8").strip(),
        "budget_s": 4200,
        "evaluate": eval_portal,
    },
    "gen_orbital": {
        "prompt": (ROOT / "fixtures" / "orbital_prompt.txt").read_text(encoding="utf-8").strip(),
        "budget_s": 2400,
        "evaluate": eval_orbital,
    },
    "web_boids": {
        "prompt": (
            "Crea da zero index.html con una simulazione HTML5 Canvas a tutto schermo (#070b14) di stormo Boids "
            "(separazione, allineamento, coesione) che parte in pausa con almeno 40 boids visibili, HUD glassmorphism "
            "(FPS, numero boids, velocità), pulsanti Play/Pause (parte mostrando Play), Step, Reset, "
            "slider velocità (0.5..3.0), e click sul canvas per aggiungere un nuovo boid. Zero dipendenze esterne e "
            "zero errori JavaScript."
        ),
        "budget_s": 2400,
        "evaluate": eval_boids,
    },
    "py_cron": {
        "prompt": (
            "Crea da zero cron_sched.py con parser e iteratore di espressioni cron a 5 campi "
            "(minuto, ora, giorno_mese, mese, giorno_settimana) supportando *, numeri, intervalli a-b, "
            "liste a,b,c, step */n e a-b/n, più la funzione next_runs(expr, start_dt, count=5) che restituisce "
            "i prossimi count datetime UTC successivi a start_dt, sollevando ValueError su espressioni non valide; "
            "aggiungi test_cron_sched.py con almeno 12 test unittest e verifica che python3 -m unittest -v "
            "test_cron_sched.py passi."
        ),
        "budget_s": 2400,
        "evaluate": eval_cron,
    },
    "py_discount": {
        "prompt": ("I test in test_discount.py falliscono: correggi apply_discount in discount.py senza modificare "
                   "i test, poi esegui python3 -m unittest test_discount.py."),
        "budget_s": 900,
        "setup": setup_discount,
        "evaluate": eval_discount,
    },
}
