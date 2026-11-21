"""Shared accounting, provenance, and process-local isolation helpers for benchmark suites (B07)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_path(path: Path) -> str:
    """Deterministic SHA-256 of a file or directory tree."""
    h = hashlib.sha256()
    if path.is_file():
        h.update(path.read_bytes())
    elif path.is_dir():
        for p in sorted(path.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(path)).encode("utf-8"))
                h.update(p.read_bytes())
    return h.hexdigest()


def read_ledger_entries(ledger_path: Path) -> list[dict[str, Any]]:
    """Read valid JSONL entries from an isolated ledger file."""
    if not ledger_path.exists():
        return []
    entries = []
    for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def summarize_local_ledger(entries: list[dict[str, Any]], attempt_id: str | None = None) -> dict[str, Any]:
    """Unified inference-only local ledger summary schema across benchmark suites."""
    if not entries:
        return {
            "status": "unavailable",
            "delegation_verified": False,
            "local_calls": None,
            "local_prompt_tokens": None,
            "local_completion_tokens": None,
            "local_total_tokens": None,
            "estimated_saved_tokens": None,
            "retries": 0,
            "attempt_id": attempt_id,
        }
    llm_entries = [e for e in entries if e.get("kind") == "llm"]
    retries = sum(1 for e in entries if e.get("kind") == "retry")
    delegation_verified = any(e.get("kind") in ("llm", "result", "job") for e in entries)
    if not llm_entries:
        return {
            "status": "unavailable" if not delegation_verified else "no_llm_events",
            "delegation_verified": delegation_verified,
            "local_calls": 0,
            "local_prompt_tokens": None,
            "local_completion_tokens": None,
            "local_total_tokens": None,
            "estimated_saved_tokens": sum(int(e.get("saved_tokens_est", 0) or 0) for e in entries),
            "retries": retries,
            "attempt_id": attempt_id,
        }
    prompt_tok = sum(int(e.get("prompt_tokens", 0) or 0) for e in llm_entries)
    comp_tok = sum(int(e.get("completion_tokens", 0) or 0) for e in llm_entries)
    saved_tok = sum(int(e.get("saved_tokens_est", 0) or 0) for e in entries)
    return {
        "status": "available",
        "delegation_verified": delegation_verified,
        "local_calls": len(llm_entries),
        "local_prompt_tokens": prompt_tok,
        "local_completion_tokens": comp_tok,
        "local_total_tokens": prompt_tok + comp_tok,
        "estimated_saved_tokens": saved_tok,
        "retries": retries,
        "attempt_id": attempt_id,
    }


def write_agy_session_settings(
    settings_path: Path,
    enable_tandem: bool,
    tandem_env: dict[str, str] | None = None,
    python_bin: str = "python3",
    repo_root: Path | None = None,
) -> Path:
    """Write a per-process agy --settings JSON file without mutating global user config."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if enable_tandem:
        args = ["-m", "tandem_mcp"]
        server_cfg: dict[str, Any] = {
            "command": python_bin,
            "args": args,
            "env": dict(tandem_env or {}),
        }
        if repo_root is not None:
            server_cfg["cwd"] = str(repo_root)
        payload = {"mcpServers": {"tandem-mcp": server_cfg}}
    else:
        payload = {"mcpServers": {}}
    settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return settings_path
