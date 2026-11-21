"""Automatic request router for Tandem MCP (`usa Tandem`).

Decides between:
- `deterministic`: exact extraction/counting/parsing via deterministic tools or scripts (0 local LLM calls).
- `direct_or_targeted`: cloud direct response or targeted read/edit for small volumes or tight budgets.
- `delegate_local`: local Qwen delegation (host-managed for edits/gen, digest_* for large reads).

Respects explicit user constraints (`solo locale` / `local only`, `non modificare file` / `read only`)
and never uses benchmark IDs, fixture names, or evaluator scores.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from . import store

_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", "runs"}

_LOCAL_ONLY_RE = re.compile(r"\b(solo\s+locale|local\s+only|senza\s+cloud|no\s+cloud|only\s+local)\b", re.I)
_READ_ONLY_RE = re.compile(
    r"\b(non\s+modificare\s+file|non\s+modificare\s+nulla|sola\s+lettura|read[\s-]+only|do\s+not\s+modify|without\s+modifying|senza\s+modificare)\b",
    re.I,
)
_PREFER_CLOUD_SAVINGS_RE = re.compile(
    r"\b("
    r"privilegia\s+(?:il\s+)?risparmio(?:\s+di)?(?:\s+token)?\s+cloud|"
    r"preferisci\s+(?:il\s+)?risparmio(?:\s+di)?(?:\s+token)?\s+cloud|"
    r"risparmia(?:re)?\s+(?:i\s+)?token\s+cloud|"
    r"meno\s+token\s+cloud|"
    r"riduci\s+(?:i\s+)?token\s+cloud|"
    r"save\s+cloud\s+tokens?|"
    r"prefer\s+cloud\s+savings?"
    r")\b",
    re.I,
)
_WRITE_INTENT_RE = re.compile(
    r"\b(crea|create|genera|generate|scrivi|write|implementa|implement|aggiungi|add|modifica|modify|aggiorna|update|correggi|fix|rifattorizza|refactor|rinomina|rename|estrai\s+un\s+helper|extract\s+a?\s*helper)\b",
    re.I,
)
_MULTI_OR_GEN_RE = re.compile(
    r"\b(da\s+zero|from\s+scratch|su\s+pi[uù]\s+file|across\s+\d*\s*files?|multi[\s-]?file|refactor|rifattorizza|rinomina|rename|interactive|html5|canvas)\b",
    re.I,
)
_STRUCTURED_EXTRACT_RE = re.compile(
    r"\b(estrai|extract|conta|count|quanti|how\s+many|somma|sum|totale|total|versione|version|dipendenze|dependencies|toml|json|jsonl|csv|git\s+log|git\s+stat|occorrenze|occurrences|timestamp)\b",
    re.I,
)
_DIAG_OR_EXPLAIN_RE = re.compile(
    r"\b(spiega|explain|come\s+funziona|how\s+does|diagnostica|diagnose|trova\s+la\s+causa|find\s+the\s+cause|perch[eé]\s+fallisce|why\s+does.*fail|riassumi|summarize)\b",
    re.I,
)
_FILE_MENTION_RE = re.compile(r"\b([A-Za-z0-9_./-]+\.(?:py|js|mjs|ts|html|htm|json|jsonl|toml|yaml|yml|csv|log|md|txt))\b")


def inspect_workspace(workspace: str | Path, request: str) -> dict[str, Any]:
    """Cheaply scan workspace metadata (sizes, extensions, test presence) without reading file contents."""
    root = Path(workspace).resolve()
    if not root.is_dir():
        return {"exists": False, "file_count": 0, "total_bytes": 0, "mentioned_bytes": 0, "has_tests": False, "structured_files": 0}

    mentioned = {m.group(1).lstrip("./") for m in _FILE_MENTION_RE.finditer(request or "")}
    file_count = 0
    total_bytes = 0
    mentioned_bytes = 0
    has_tests = False
    structured_files = 0
    has_web = False

    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        rel_dir = Path(cur).relative_to(root)
        for fname in files:
            if fname.startswith("."):
                continue
            fp = Path(cur) / fname
            try:
                sz = fp.stat().st_size
            except OSError:
                continue
            file_count += 1
            total_bytes += sz
            rel_p = str(rel_dir / fname) if str(rel_dir) != "." else fname
            if rel_p in mentioned or fname in mentioned:
                mentioned_bytes += sz
            lower = fname.lower()
            if lower.startswith("test_") or lower.endswith(("_test.py", ".test.js", ".test.mjs")) or "tests" in rel_dir.parts:
                has_tests = True
            if lower.endswith((".json", ".jsonl", ".toml", ".csv", ".log")):
                structured_files += 1
            if lower.endswith((".html", ".htm")):
                has_web = True
            if file_count >= 500:
                break
        if file_count >= 500:
            break

    return {
        "exists": True,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "mentioned_bytes": mentioned_bytes,
        "has_tests": has_tests,
        "structured_files": structured_files,
        "has_web": has_web,
        "mentioned_files": sorted(mentioned),
    }


def classify_request(
    request: str,
    workspace: str | Path,
    budget_seconds: int | None = None,
    *,
    log_decision: bool = True,
) -> dict[str, Any]:
    """Select `deterministic`, `direct_or_targeted`, or `delegate_local` using pre-execution signals."""
    req = (request or "").strip()
    local_only = bool(_LOCAL_ONLY_RE.search(req))
    read_only = bool(_READ_ONLY_RE.search(req))
    prefer_cloud_savings = bool(_PREFER_CLOUD_SAVINGS_RE.search(req))
    ws_info = inspect_workspace(workspace, req)

    is_write = (not read_only) and bool(_WRITE_INTENT_RE.search(req))
    is_multi_or_gen = (not read_only) and bool(_MULTI_OR_GEN_RE.search(req))
    is_structured = bool(_STRUCTURED_EXTRACT_RE.search(req))
    is_diag_or_explain = bool(_DIAG_OR_EXPLAIN_RE.search(req))

    relevant_bytes = ws_info["mentioned_bytes"] or ws_info["total_bytes"]
    budget_absent = budget_seconds is None or budget_seconds <= 0
    tight_budget = (not budget_absent) and int(budget_seconds) < 150

    route: str
    recommended_tools: list[str]
    reason: str

    if is_structured and not is_write and (ws_info["structured_files"] > 0 or "git " in req.lower()):
        route = "deterministic"
        recommended_tools = ["run_command(python/jq read-only)" if not local_only else "digest_command", "extract_from_file"]
        reason = "Structured extraction or exact count requested with structured source files; deterministic parsing avoids LLM approximation and local wait."
    elif local_only:
        route = "delegate_local"
        recommended_tools = ["delegate" if is_write else "digest_many"]
        reason = "User requested local-only execution (`solo locale`); delegating to local Qwen without cloud fallback."
    elif is_write:
        is_from_scratch = bool(re.search(r"\b(da\s+zero|from\s+scratch)\b", req, re.I))
        is_web_req = ws_info["has_web"] or bool(re.search(r"\b(index\.html|html5|canvas|web\s*app)\b", req, re.I))
        min_gen_budget = 1200 if is_web_req else 240
        has_enough_budget_for_gen = budget_absent or int(budget_seconds) >= min_gen_budget
        if prefer_cloud_savings and is_from_scratch and has_enough_budget_for_gen:
            route = "delegate_local"
            recommended_tools = ["delegate", "host_runner"]
            reason = (
                f"User requested cloud savings for substantial from-scratch generation "
                f"(budget={'absent' if budget_absent else f'{budget_seconds}s'}); local Qwen saves cloud output tokens."
            )
        elif (not is_from_scratch) and (relevant_bytes >= 40000 or ws_info["file_count"] > 10) and not tight_budget:
            route = "delegate_local"
            recommended_tools = ["delegate", "host_runner"]
            reason = f"Very large existing-code refactor (relevant_bytes={relevant_bytes}, files={ws_info['file_count']}); delegating locally."
        else:
            route = "direct_or_targeted"
            recommended_tools = ["read_file", "edit_file"]
            reason = (
                f"Default direct execution for ordinary edits, refactors, or generation without cloud-savings preference "
                f"(prefer_cloud_savings={prefer_cloud_savings}, budget={'absent' if budget_absent else f'{budget_seconds}s'})."
            )
    else:
        # Read / diagnosis / explanation
        if relevant_bytes >= 20000 and not tight_budget:
            route = "delegate_local"
            recommended_tools = ["digest_many" if ws_info["file_count"] > 1 else "digest_file"]
            reason = f"Large read/diagnosis volume (relevant_bytes={relevant_bytes} >= 20KB); local Qwen digest reduces cloud input context."
        else:
            route = "direct_or_targeted"
            recommended_tools = ["read_file", "grep"]
            reason = f"Small read/diagnosis volume (relevant_bytes={relevant_bytes} < 20KB) or tight budget ({'absent' if budget_absent else f'{budget_seconds}s'}); direct targeted read avoids local latency."

    decision = {
        "route": route,
        "recommended_tools": recommended_tools,
        "reason": reason,
        "constraints": {
            "local_only": local_only,
            "read_only": read_only,
            "prefer_cloud_savings": prefer_cloud_savings,
        },
        "signals": {
            "is_write": is_write,
            "is_multi_or_gen": is_multi_or_gen,
            "is_structured": is_structured,
            "is_diag_or_explain": is_diag_or_explain,
            "relevant_bytes": relevant_bytes,
            "budget_seconds": budget_seconds,
            "budget_absent": budget_absent,
            "prefer_cloud_savings": prefer_cloud_savings,
            **ws_info,
        },
    }

    if log_decision:
        _append_router_log({
            "ts": time.time(),
            "route": route,
            "reason": reason,
            "constraints": decision["constraints"],
            "signals": decision["signals"],
            "request_preview": req[:200],
        })
    return decision


def _append_router_log(entry: dict[str, Any]) -> None:
    try:
        store.DATA.mkdir(parents=True, exist_ok=True)
        with (store.DATA / "router_log.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def evaluate_fallback(
    *,
    route_used: str,
    outcome: str,
    local_only: bool,
    remaining_budget_s: float,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Decide safe fallback on delegated read timeout/incomplete or partial modification."""
    if outcome == "ok":
        return {"fallback": "none", "reason": "primary route succeeded"}
    if local_only:
        return {"fallback": "none_blocked_local_only", "reason": "local_only constraint forbids cloud fallback"}

    if route_used in ("digest_file", "digest_many", "digest_command"):
        if remaining_budget_s >= 20.0:
            return {"fallback": "targeted_cloud_read", "reason": f"local digest {outcome}; remaining budget {remaining_budget_s:.0f}s allows targeted grep/range read"}
        return {"fallback": "none_budget_exhausted", "reason": f"remaining budget {remaining_budget_s:.0f}s too low for fallback"}

    if route_used in ("delegate", "delegate_many"):
        job_data = store.read_job(job_id) if job_id else None
        changes = (job_data or {}).get("changes") or []
        backup_status = (job_data or {}).get("backup_status")
        if changes:
            return {
                "fallback": "inspect_partial_or_rollback",
                "reason": f"partial workspace edits exist ({len(changes)} files, backup={backup_status}); inspect diff/checks or rollback before retrying to avoid duplicating work",
                "changed_files": [c[0] for c in changes],
            }
        if remaining_budget_s >= 30.0:
            return {"fallback": "direct_or_targeted", "reason": f"no workspace changes persisted before {outcome}; safe to fall back to direct"}
        return {"fallback": "none_budget_exhausted", "reason": "budget exhausted with no partial edits"}

    return {"fallback": "none", "reason": f"no fallback defined for {route_used}/{outcome}"}
