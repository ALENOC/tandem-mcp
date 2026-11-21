"""Independent deterministic evaluators for the Hydrogen 3.6.1 benchmark suite."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import urljoin
from pathlib import Path
from typing import Any

BENCHMARKS_DIR = Path(__file__).resolve().parents[1]
if str(BENCHMARKS_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS_DIR))
from web_browser_check import run_browser_check  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

_FAILURE_MARKERS = (
    "unable to complete",
    "timed out",
    "context deadline exceeded",
    "cannot complete the request",
)

_PACKAGE_DOMAINS: dict[str, tuple[str, ...]] = {
    "agent": ("executor", "loop", "tool", "job", "rollback", "backup", "snapshot", "evidence", "diff"),
    "digest": ("digest", "read", "extract", "grep", "chunk", "command", "summar", "file"),
    "engine": ("llm", "openai", "http", "client", "model", "stream", "retry", "endpoint", "completion", "probe"),
    "sandbox": ("sandbox", "jail", "bubblewrap", "bwrap", "path", "glob", "allowlist", "redact", "secret", "workspace"),
    "server": ("mcp", "server", "tool", "fastmcp", "contract", "lean", "ledger", "receipt", "entry"),
    "store": ("store", "persist", "json", "jsonl", "ledger", "lesson", "capabilit", "disk", "state", "storage"),
}


class PortalPage(HTMLParser):
    """Inspect the actual page that loads the separately tested engine."""
    def __init__(self):
        super().__init__()
        self.ids = {}
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids[attrs["id"]] = tag
        if tag == "script" and attrs.get("src"):
            self.scripts.append(urljoin("file:///demo/index.html", attrs["src"]))

    def problems(self):
        problems = []
        for name in ("c", "fps", "polys", "parts", "btnPause", "btnOrbit", "btnReset", "speed", "spdVal"):
            if name not in self.ids:
                problems.append(f"missing #{name}")
        if self.ids.get("c") != "canvas":
            problems.append("#c must be a canvas")
        ordered = ["file:///demo/" + name for name in ("scene.js", "engine3d.js", "app.js")]
        if [src for src in self.scripts if src in ordered] != ordered:
            problems.append("load scene.js, engine3d.js and app.js in order")
        return problems


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    return m.group(1) if m else text


def _has_failure_marker(low: str) -> bool:
    return any(m in low for m in _FAILURE_MARKERS)


def _eval_rollback(text: str) -> dict[str, Any]:
    low = text.lower()
    if _has_failure_marker(low):
        return {
            "valid": False,
            "reason": "Response reports incomplete/timed-out execution",
            "details": {"requirements": {"complete": {"status": "failed"}}},
        }
    clauses = [c.strip() for c in re.split(r"(?<=[.!?;])\s+|\n+", low) if c.strip()]
    neg_skip = re.compile(r"\b(?:does not|doesn't|do not|don't|never|not)\s+(?:\w+\s+){0,2}(?:skip|leave\b.*\bunbacked)\b")
    neg_restore = re.compile(r"\b(?:does not|doesn't|do not|don't|never|not)\s+(?:\w+\s+){0,2}(?:restor\w*|decompress\w*|revert\w*)\b")

    none_ok = False
    for cl in clauses:
        if any(k in cl for k in ("none", "null", "unbacked")):
            if neg_skip.search(cl):
                continue
            if any(k in cl for k in ("unbacked", "skip", "not undone", "cannot", "no backup", "leaves", "left")):
                none_ok = True
                break

    restore_ok = False
    for cl in clauses:
        if any(k in cl for k in ("string", "path", "hash", "blob", "gzip", "backup")):
            if neg_restore.search(cl):
                continue
            if any(k in cl for k in ("restor", "decompress", "revert")):
                restore_ok = True
                break

    reqs = {
        "none_unbacked": {"status": "passed" if none_ok else "failed"},
        "string_restore": {"status": "passed" if restore_ok else "failed"},
    }
    valid = none_ok and restore_ok
    return {
        "valid": valid,
        "reason": "Verified rollback None=unbacked/skip and string=blob-restore" if valid else f"Missing or negated rollback semantics (none_unbacked={none_ok}, string_restore={restore_ok})",
        "details": {"has_unbacked": none_ok, "has_restore": restore_ok, "requirements": reqs},
    }


def _eval_package_survey(text: str) -> dict[str, Any]:
    low = text.lower()
    if _has_failure_marker(low):
        return {
            "valid": False,
            "reason": "Response reports incomplete/timed-out execution",
            "details": {"requirements": {"complete": {"status": "failed"}}},
        }
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    reqs: dict[str, Any] = {}
    found, bad = [], []
    for mod, keywords in _PACKAGE_DOMAINS.items():
        mod_re = re.compile(rf"\b{mod}(?:\.py)?\b", re.I)
        matched_lines = [ln for ln in lines if mod_re.search(ln)]
        if not matched_lines:
            # fallback: sentence-level search
            matched_lines = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if mod_re.search(s)]
        ok_mod = False
        for ln in matched_lines:
            # Require a real summary (>= 4 words besides module name) and at least one domain keyword
            cleaned = re.sub(rf"\b{mod}(?:\.py)?\b", "", ln, flags=re.I)
            words = re.findall(r"[A-Za-z0-9_]+", cleaned)
            if len(words) >= 4 and any(kw in ln.lower() for kw in keywords):
                ok_mod = True
                break
        reqs[mod] = {"status": "passed" if ok_mod else "failed"}
        if ok_mod:
            found.append(mod)
        else:
            bad.append(mod)
    valid = len(bad) == 0
    return {
        "valid": valid,
        "reason": f"Verified {len(found)}/{len(_PACKAGE_DOMAINS)} module summaries" if valid else f"Missing or invalid module summaries: {bad}",
        "details": {"found": found, "missing": bad, "requirements": reqs},
    }


def _eval_git_log(text: str) -> dict[str, Any]:
    low = text.lower()
    if _has_failure_marker(low):
        return {
            "valid": False,
            "reason": "Response reports incomplete/timed-out execution",
            "details": {"requirements": {"complete": {"status": "failed"}}},
        }
    log_path = FIXTURES_DIR / "git_log_25_stat.txt"
    counts: Counter[str] = Counter()
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s+([^|\s]+)\s+\|\s+\d+", line)
        if m:
            counts[m.group(1)] += 1
    ranked = counts.most_common()
    cutoff = ranked[2][1] if len(ranked) >= 3 else 0
    strict_top = [(name, c) for name, c in ranked if c > cutoff]
    tied_at_cutoff = [(name, c) for name, c in ranked if c == cutoff]
    needed_from_tied = max(0, 3 - len(strict_top))

    lines = text.splitlines()
    def _match_file_and_count(name: str, expected_count: int) -> bool:
        base = Path(name).name
        for ln in lines:
            if name in ln or base in ln:
                if re.search(rf"\b{expected_count}\b", ln):
                    return True
        # Also allow file + count within 80 chars in full text
        for pat in (re.escape(name), re.escape(base)):
            for m in re.finditer(pat, text):
                window = text[max(0, m.start() - 20):m.end() + 80]
                if re.search(rf"\b{expected_count}\b", window):
                    return True
        return False

    reqs: dict[str, Any] = {}
    strict_hits = []
    for name, c in strict_top:
        ok = _match_file_and_count(name, c)
        reqs[f"top:{name}"] = {"status": "passed" if ok else "failed", "expected_count": c}
        if ok:
            strict_hits.append(name)

    tied_hits = []
    for name, c in tied_at_cutoff:
        ok = _match_file_and_count(name, c)
        reqs[f"tied:{name}"] = {"status": "passed" if ok else "failed", "expected_count": c}
        if ok:
            tied_hits.append(name)

    valid = (len(strict_hits) == len(strict_top)) and (len(tied_hits) >= needed_from_tied)
    expected_names = [n for n, _ in strict_top] + [n for n, _ in tied_at_cutoff]
    return {
        "valid": valid,
        "reason": f"Matched top files and counts ({strict_hits + tied_hits})" if valid else f"Expected all strict top {strict_top} and {needed_from_tied} of tied {tied_at_cutoff}; matched {strict_hits + tied_hits}",
        "details": {"top_ranked": expected_names, "strict_hits": strict_hits, "tied_hits": tied_hits, "requirements": reqs},
    }


def _eval_manifest(text: str) -> dict[str, Any]:
    try:
        data = json.loads(_strip_json_fences(text))
    except Exception as exc:
        return {"valid": False, "reason": f"Invalid JSON: {exc}", "details": {"requirements": {"json": {"status": "failed"}}}}
    if not isinstance(data, dict):
        return {"valid": False, "reason": "JSON root is not an object", "details": {"requirements": {"json": {"status": "failed"}}}}
    expected_keys = {"name", "requires_python", "dependencies", "console_script"}
    keys_ok = set(data.keys()) == expected_keys
    name_ok = data.get("name") == "tandem-mcp"
    py_ok = data.get("requires_python") == ">=3.11"
    deps = data.get("dependencies")
    deps_ok = (
        isinstance(deps, list)
        and all(isinstance(d, str) for d in deps)
        and sorted(d.strip() for d in deps) == ["mcp>=2.3", "openai>=1.40"]
    )
    script = data.get("console_script")
    script_ok = isinstance(script, str) and script.strip() in {
        "tandem_mcp.server:main",
        "tandem-mcp = tandem_mcp.server:main",
        "tandem-mcp",
    }
    reqs = {
        "exact_keys": {"status": "passed" if keys_ok else "failed"},
        "name": {"status": "passed" if name_ok else "failed"},
        "requires_python": {"status": "passed" if py_ok else "failed"},
        "dependencies": {"status": "passed" if deps_ok else "failed"},
        "console_script": {"status": "passed" if script_ok else "failed"},
    }
    valid = keys_ok and name_ok and py_ok and deps_ok and script_ok
    return {
        "valid": valid,
        "reason": "Schema and exact values verified" if valid else f"Mismatch: keys={keys_ok}, name={name_ok}, py={py_ok}, deps={deps_ok}, script={script_ok}",
        "details": {"parsed": data, "requirements": reqs},
    }


def evaluate_attempt(task_id: str, response_text: str, workspace: Path) -> dict[str, Any]:
    """Return {'valid': bool, 'reason': str, 'details': dict}."""
    text = (response_text or "").strip()
    if not text and task_id not in ("bugfix_multifile", "feature_rate_limiter", "gen_orbital", "gen_portal", "refactor_rename"):
        return {"valid": False, "reason": "Empty response", "details": {"requirements": {"non_empty": {"status": "failed"}}}}

    if task_id == "reading_agent_rollback":
        return _eval_rollback(text)

    if task_id == "reading_package_survey":
        return _eval_package_survey(text)

    if task_id == "reading_git_log":
        return _eval_git_log(text)

    if task_id == "extraction_manifest":
        return _eval_manifest(text)

    if task_id == "bugfix_multifile":
        ref_test = FIXTURES_DIR / "bugfix_multifile" / "test_suite.py"
        shutil.copy2(ref_test, workspace / "test_suite.py")
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "test_suite.py"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )
        valid = proc.returncode == 0
        return {
            "valid": valid,
            "reason": "test_suite.py passed" if valid else f"test_suite.py failed (rc={proc.returncode})",
            "details": {"returncode": proc.returncode, "stdout": proc.stdout[-500:], "stderr": proc.stderr[-500:]},
        }

    if task_id == "feature_rate_limiter":
        eval_src = FIXTURES_DIR / "feature_rate_limiter_eval.py"
        shutil.copy2(eval_src, workspace / "eval_rate_limiter.py")
        proc_eval = subprocess.run(
            [sys.executable, "-m", "unittest", "eval_rate_limiter.py"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )
        user_test = workspace / "test_rate_limiter.py"
        user_ok = False
        user_rc = None
        if user_test.exists():
            proc_user = subprocess.run(
                [sys.executable, "-m", "unittest", "test_rate_limiter.py"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=30,
            )
            user_rc = proc_user.returncode
            user_ok = user_rc == 0
        valid = (proc_eval.returncode == 0) and user_ok
        return {
            "valid": valid,
            "reason": "Hidden eval + user tests passed" if valid else f"eval_rc={proc_eval.returncode}, user_test_exists={user_test.exists()}, user_rc={user_rc}",
            "details": {
                "eval_returncode": proc_eval.returncode,
                "user_test_exists": user_test.exists(),
                "user_returncode": user_rc,
                "eval_stderr": proc_eval.stderr[-500:],
            },
        }

    if task_id == "gen_orbital":
        idx = workspace / "index.html"
        if not idx.exists():
            return {"valid": False, "reason": "index.html missing", "details": {"requirements": {"index_html": {"status": "failed"}}}}
        shutil.copy2(FIXTURES_DIR / "generation" / "check_page.js", workspace / "check_page.js")
        proc = subprocess.run(
            ["node", "check_page.js"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )
        harness_ok = proc.returncode == 0 and "page ok" in (proc.stdout or "")
        browser = run_browser_check(workspace, "orbital")
        browser_status = browser.get("status", "failed")
        stars_script = Path(__file__).resolve().parent / "check_stars.mjs"
        stars_res = {"passed": False, "error": "check_stars.mjs missing"}
        if browser_status == "passed" and stars_script.exists():
            sp = subprocess.run(["node", str(stars_script), str(workspace)], capture_output=True, text=True, timeout=30)
            try:
                stars_res = json.loads((sp.stdout or "{}").strip().splitlines()[-1])
            except Exception:
                stars_res = {"passed": False, "stderr": (sp.stderr or "")[-200:]}
        elif browser_status == "not_evaluated":
            stars_res = {"passed": False, "status": "not_evaluated"}
        stars_ok = bool(stars_res.get("passed"))
        reqs = {
            "harness": {"status": "passed" if harness_ok else "failed"},
            "browser": {"status": browser_status},
            "visual_stars": {"status": "passed" if stars_ok else ("not_evaluated" if browser_status == "not_evaluated" else "failed")},
        }
        valid = harness_ok and browser_status == "passed" and stars_ok
        if valid:
            reason = "check_page.js, browser, and 4x4 star distribution checks passed"
        elif browser_status == "not_evaluated":
            reason = f"browser check not_evaluated ({browser.get('error', 'browser unavailable')})"
        elif not harness_ok:
            reason = f"check_page.js failed (rc={proc.returncode}): {(proc.stderr or proc.stdout)[-300:]}"
        elif browser_status != "passed":
            reason = f"browser check failed: {browser.get('error') or browser.get('controls') or browser.get('console_errors')}"
        else:
            reason = f"star distribution check failed: {stars_res}"
        return {
            "valid": valid,
            "reason": reason,
            "details": {
                "returncode": proc.returncode,
                "stdout": proc.stdout[-300:],
                "stderr": proc.stderr[-300:],
                "browser": browser,
                "visual_stars": stars_res,
                "requirements": reqs,
            },
        }

    if task_id == "gen_portal":
        required = ["index.html", "scene.js", "engine3d.js", "app.js"]
        missing = [f for f in required if not (workspace / f).exists()]
        if missing:
            return {"valid": False, "reason": f"Missing files: {missing}", "details": {"missing": missing, "requirements": {"files": {"status": "failed"}}}}
        page = PortalPage()
        page.feed((workspace / "index.html").read_text(encoding="utf-8"))
        page.close()
        problems = page.problems()
        if problems:
            return {"valid": False, "reason": ", ".join(problems), "details": {"page_errors": problems, "requirements": {"html_structure": {"status": "failed"}}}}
        app = subprocess.run(["node", "--check", "app.js"], cwd=workspace, capture_output=True, text=True, timeout=30)
        if app.returncode:
            return {"valid": False, "reason": "app.js syntax error", "details": {"stderr": app.stderr[-500:], "requirements": {"app_syntax": {"status": "failed"}}}}
        shutil.copy2(FIXTURES_DIR / "generation" / "check_engine.js", workspace / "check_engine.js")
        proc = subprocess.run(
            ["node", "check_engine.js"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )
        harness_ok = proc.returncode == 0 and "engine ok" in (proc.stdout or "")
        browser = run_browser_check(workspace, "portal")
        browser_status = browser.get("status", "failed")
        vis_script = Path(__file__).resolve().parent / "check_portal_visual.mjs"
        vis_res = {"passed": False, "error": "check_portal_visual.mjs missing"}
        if browser_status == "passed" and vis_script.exists():
            vp = subprocess.run(["node", str(vis_script), str(workspace)], capture_output=True, text=True, timeout=30)
            try:
                vis_res = json.loads((vp.stdout or "{}").strip().splitlines()[-1])
            except Exception:
                vis_res = {"passed": False, "stderr": (vp.stderr or "")[-200:]}
        elif browser_status == "not_evaluated":
            vis_res = {"passed": False, "status": "not_evaluated"}
        vis_ok = bool(vis_res.get("passed"))
        reqs = {
            "html_structure": {"status": "passed"},
            "app_syntax": {"status": "passed"},
            "harness": {"status": "passed" if harness_ok else "failed"},
            "browser": {"status": browser_status},
            "visual_portal": {"status": "passed" if vis_ok else ("not_evaluated" if browser_status == "not_evaluated" else "failed")},
        }
        valid = harness_ok and browser_status == "passed" and vis_ok
        if valid:
            reason = "check_engine.js, browser, and portal visual shading checks passed"
        elif browser_status == "not_evaluated":
            reason = f"browser check not_evaluated ({browser.get('error', 'browser unavailable')})"
        elif not harness_ok:
            reason = f"check_engine.js failed (rc={proc.returncode}): {(proc.stderr or proc.stdout)[-300:]}"
        elif browser_status != "passed":
            reason = f"browser check failed: {browser.get('error') or browser.get('controls') or browser.get('console_errors')}"
        else:
            reason = f"portal visual shading check failed: {vis_res}"
        return {
            "valid": valid,
            "reason": reason,
            "details": {
                "returncode": proc.returncode,
                "stdout": proc.stdout[-300:],
                "stderr": proc.stderr[-300:],
                "browser": browser,
                "visual_portal": vis_res,
                "requirements": reqs,
            },
        }

    if task_id == "refactor_rename":
        ref_test = FIXTURES_DIR / "refactor_rename" / "test_rename.py"
        shutil.copy2(ref_test, workspace / "test_rename.py")
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "test_rename.py"],
            cwd=str(workspace), capture_output=True, text=True, timeout=60,
        )
        valid = proc.returncode == 0
        return {
            "valid": valid,
            "reason": "test_rename.py passed (13 files renamed)" if valid else f"test_rename.py failed (rc={proc.returncode}): {proc.stderr[-200:]}",
            "details": {"returncode": proc.returncode, "stderr": proc.stderr[-500:]},
        }

    if task_id == "reading_incident_log":
        low = text.lower()
        checks = {
            "first_service": "payments-db" in low,
            "start_time": "02:14:07" in text,
            "root_cause": any(k in low for k in ("no space", "disk full", "disk space", "disk was full", "100%")),
            "resolved_time": "03:41:00" in text,
        }
        reqs = {k: {"status": "passed" if v else "failed"} for k, v in checks.items()}
        valid = all(checks.values())
        return {
            "valid": valid,
            "reason": "Incident reconstructed (service, exact start/resolution HH:MM:SS, cause)" if valid else f"Missing: {[k for k, v in checks.items() if not v]}",
            "details": {**checks, "requirements": reqs},
        }

    return {"valid": False, "reason": f"Unknown task_id: {task_id}", "details": {}}
