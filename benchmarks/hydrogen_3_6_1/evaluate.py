"""Independent deterministic evaluators for the Hydrogen 3.6.1 benchmark suite."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    return m.group(1) if m else text


def evaluate_attempt(task_id: str, response_text: str, workspace: Path) -> dict[str, Any]:
    """Return {'valid': bool, 'reason': str, 'details': dict}."""
    text = (response_text or "").strip()
    if not text and task_id not in ("bugfix_multifile", "feature_rate_limiter"):
        return {"valid": False, "reason": "Empty response", "details": {}}

    if task_id == "reading_agent_rollback":
        low = text.lower()
        has_unbacked = any(k in low for k in ("unbacked", "skip", "not undone", "cannot", "no backup"))
        has_restore = any(k in low for k in ("restor", "blob", "decompress", "revert"))
        valid = has_unbacked and has_restore
        return {
            "valid": valid,
            "reason": "Verified rollback None=unbacked/skip and string=blob-restore" if valid else f"Missing key rollback concepts (unbacked={has_unbacked}, restore={has_restore})",
            "details": {"has_unbacked": has_unbacked, "has_restore": has_restore},
        }

    if task_id == "reading_package_survey":
        expected = [
            "agent", "digest", "engine", "sandbox", "server", "store",
        ]
        low = text.lower()
        found = [m for m in expected if re.search(rf"\b{m}(?:\.py)?\b", low)]
        missing = [m for m in expected if m not in found]
        valid = len(missing) == 0
        return {
            "valid": valid,
            "reason": f"Found {len(found)}/{len(expected)} modules" if valid else f"Missing modules: {missing}",
            "details": {"found": found, "missing": missing},
        }

    if task_id == "reading_git_log":
        log_path = FIXTURES_DIR / "git_log_25_stat.txt"
        counts: Counter[str] = Counter()
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s+([^|\s]+)\s+\|\s+\d+", line)
            if m:
                counts[m.group(1)] += 1
        top3 = [name for name, _ in counts.most_common(3)]
        hits = [name for name in top3 if Path(name).name in text or name in text]
        valid = len(hits) >= 2
        return {
            "valid": valid,
            "reason": f"Matched {len(hits)}/3 top files ({hits})" if valid else f"Only matched {hits} of top3 {top3}",
            "details": {"top3": top3, "hits": hits},
        }

    if task_id == "extraction_manifest":
        try:
            data = json.loads(_strip_json_fences(text))
        except Exception as exc:
            return {"valid": False, "reason": f"Invalid JSON: {exc}", "details": {}}
        if not isinstance(data, dict):
            return {"valid": False, "reason": "JSON root is not an object", "details": {}}
        name_ok = data.get("name") == "tandem-mcp"
        py_ok = data.get("requires_python") == ">=3.11"
        deps = data.get("dependencies") or []
        deps_str = " ".join(str(d) for d in deps) if isinstance(deps, list) else str(deps)
        deps_ok = ("mcp>=2.3" in deps_str) and ("openai>=1.40" in deps_str)
        script = str(data.get("console_script") or "")
        script_ok = ("tandem-mcp" in script) or ("tandem_mcp.server:main" in script)
        valid = name_ok and py_ok and deps_ok and script_ok
        return {
            "valid": valid,
            "reason": "Schema and values verified" if valid else f"Mismatch: name={name_ok}, py={py_ok}, deps={deps_ok}, script={script_ok}",
            "details": {"parsed": data},
        }

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
            return {"valid": False, "reason": "index.html missing", "details": {}}
        shutil.copy2(FIXTURES_DIR / "generation" / "check_page.js", workspace / "check_page.js")
        proc = subprocess.run(
            ["node", "check_page.js"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )
        valid = proc.returncode == 0 and "page ok" in (proc.stdout or "")
        return {
            "valid": valid,
            "reason": "check_page.js passed (page ok)" if valid else f"check_page.js failed (rc={proc.returncode}): {(proc.stderr or proc.stdout)[-300:]}",
            "details": {"returncode": proc.returncode, "stdout": proc.stdout[-300:], "stderr": proc.stderr[-300:]},
        }

    if task_id == "gen_portal":
        required = ["index.html", "scene.js", "engine3d.js", "app.js"]
        missing = [f for f in required if not (workspace / f).exists()]
        if missing:
            return {"valid": False, "reason": f"Missing files: {missing}", "details": {"missing": missing}}
        shutil.copy2(FIXTURES_DIR / "generation" / "check_engine.js", workspace / "check_engine.js")
        proc = subprocess.run(
            ["node", "check_engine.js"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )
        valid = proc.returncode == 0 and "engine ok" in (proc.stdout or "")
        return {
            "valid": valid,
            "reason": "check_engine.js passed (engine ok)" if valid else f"check_engine.js failed (rc={proc.returncode}): {(proc.stderr or proc.stdout)[-300:]}",
            "details": {"returncode": proc.returncode, "stdout": proc.stdout[-300:], "stderr": proc.stderr[-300:]},
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
            "start_time": "02:14" in text,
            "root_cause": any(k in low for k in ("no space", "disk full", "disk space", "disk was full", "100%")),
            "resolved_time": "03:41" in text,
        }
        valid = all(checks.values())
        return {
            "valid": valid,
            "reason": "Incident reconstructed (service, start, cause, resolution)" if valid else f"Missing: {[k for k, v in checks.items() if not v]}",
            "details": checks,
        }

    return {"valid": False, "reason": f"Unknown task_id: {task_id}", "details": {}}
