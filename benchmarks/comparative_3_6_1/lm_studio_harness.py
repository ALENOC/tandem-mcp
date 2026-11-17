"""Minimal LM Studio local tool harness for Scenario B (Gemini + Direct LM Studio).

Provides the local model (qwen3.8-27b@iq3_s via http://127.0.0.1:1234/v1) with basic
workspace tools (list_files, read_file, grep_file, write_file, run_command) WITHOUT any
Tandem MCP features: no contracts, no snapshots/journal/rollback, no lexical quote
verification, and no digest/extract map-reduce.

Usage:
    python3 lm_studio_harness.py --workspace /path/to/ws --prompt "Your task..."
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_ENDPOINT = 'http://127.0.0.1:1234/v1'
DEFAULT_MODEL = 'qwen3.8-27b@iq3_s'

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'list_files',
            'description': 'List files in the workspace directory.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'read_file',
            'description': 'Read a file from the workspace (optionally line range).',
            'parameters': {
                'type': 'object',
                'required': ['path'],
                'properties': {
                    'path': {'type': 'string'},
                    'start_line': {'type': 'integer'},
                    'end_line': {'type': 'integer'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'grep_file',
            'description': 'Search a file for lines matching a regex pattern.',
            'parameters': {
                'type': 'object',
                'required': ['path', 'pattern'],
                'properties': {
                    'path': {'type': 'string'},
                    'pattern': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'write_file',
            'description': 'Write full content to a file in the workspace.',
            'parameters': {
                'type': 'object',
                'required': ['path', 'content'],
                'properties': {
                    'path': {'type': 'string'},
                    'content': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'run_command',
            'description': 'Run a shell command in the workspace.',
            'parameters': {
                'type': 'object',
                'required': ['command'],
                'properties': {
                    'command': {'type': 'string'},
                },
            },
        },
    },
]


def _safe_path(ws: Path, rel: str) -> Path:
    p = (ws / rel).resolve()
    if ws.resolve() not in p.parents and p != ws.resolve():
        raise ValueError(f'Path outside workspace: {rel}')
    return p


def _exec_tool(ws: Path, name: str, args: dict, stats: dict) -> str:
    try:
        if name == 'list_files':
            files = sorted(str(p.relative_to(ws)) for p in ws.rglob('*') if p.is_file() and p.name != 'lm_studio_harness.py')
            return '\n'.join(files) or '(empty)'
        if name == 'read_file':
            p = _safe_path(ws, args['path'])
            lines = p.read_text(errors='replace').splitlines()
            s = max(1, int(args.get('start_line') or 1))
            e = min(len(lines), int(args.get('end_line') or len(lines)))
            chunk = '\n'.join(f'{i}| {lines[i - 1]}' for i in range(s, e + 1))
            stats['bytes_read_local'] += len(chunk.encode('utf-8', errors='replace'))
            return chunk[:24000]
        if name == 'grep_file':
            p = _safe_path(ws, args['path'])
            rx = re.compile(args['pattern'], re.I)
            lines = p.read_text(errors='replace').splitlines()
            hits = [f'{i + 1}| {line}' for i, line in enumerate(lines) if rx.search(line)]
            out = '\n'.join(hits[:80]) or 'No matches.'
            stats['bytes_read_local'] += len(out.encode('utf-8', errors='replace'))
            return out
        if name == 'write_file':
            p = _safe_path(ws, args['path'])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args['content'])
            return f'Wrote {len(args["content"])} chars to {args["path"]}'
        if name == 'run_command':
            res = subprocess.run(
                args['command'], shell=True, cwd=ws, capture_output=True, text=True, timeout=60
            )
            out = f'exit={res.returncode}\n{res.stdout}\n{res.stderr}'.strip()
            return out[:12000]
        return f'Unknown tool: {name}'
    except Exception as exc:
        return f'ERROR: {exc}'


def run_task(workspace: Path, prompt: str, endpoint: str = DEFAULT_ENDPOINT, model: str = DEFAULT_MODEL, max_steps: int = 12, timeout: int = 600) -> dict:
    messages = [
        {'role': 'system', 'content': 'You are a helpful coding and analysis assistant. Use the provided tools in the workspace to complete the user request accurately and concisely.'},
        {'role': 'user', 'content': prompt},
    ]
    stats = {
        'local_prompt_tokens': 0,
        'local_completion_tokens': 0,
        'local_total_tokens': 0,
        'local_inference_seconds': 0.0,
        'local_requests': 0,
        'retry_attempts': 0,
        'bytes_read_local': 0,
        'tool_interactions': [],
    }
    t_start = time.perf_counter()
    final_answer = ''
    for _step in range(max_steps):
        if time.perf_counter() - t_start > timeout:
            final_answer = 'ERROR: timeout reached'
            break
        payload = json.dumps({
            'model': model,
            'messages': messages,
            'tools': TOOLS,
            'temperature': 0.1,
            'max_tokens': 4096,
        }).encode('utf-8')
        req = urllib.request.Request(
            f'{endpoint.rstrip("/")}/chat/completions',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=max(30, timeout)) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        stats['local_inference_seconds'] += time.perf_counter() - t0
        stats['local_requests'] += 1
        usage = data.get('usage') or {}
        stats['local_prompt_tokens'] += int(usage.get('prompt_tokens') or 0)
        stats['local_completion_tokens'] += int(usage.get('completion_tokens') or 0)
        stats['local_total_tokens'] = stats['local_prompt_tokens'] + stats['local_completion_tokens']

        msg = data['choices'][0]['message']
        calls = msg.get('tool_calls') or []
        if not calls:
            final_answer = (msg.get('content') or '').strip()
            break
        messages.append(msg)
        for c in calls:
            fn = c['function']['name']
            raw_args = c['function'].get('arguments') or '{}'
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            out = _exec_tool(workspace, fn, args, stats)
            stats['tool_interactions'].append({
                'tool_name': fn,
                'request_bytes': len(raw_args.encode('utf-8', errors='replace')),
                'response_bytes': len(out.encode('utf-8', errors='replace')),
                'truncated': (fn == 'read_file' and len(out) >= 24000) or (fn == 'run_command' and len(out) >= 12000),
            })
            messages.append({'role': 'tool', 'tool_call_id': c['id'], 'content': out})

    stats['local_inference_seconds'] = round(stats['local_inference_seconds'], 2)
    return {'answer': final_answer, 'stats': stats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', required=True)
    ap.add_argument('--prompt', required=True)
    ap.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    ap.add_argument('--model', default=DEFAULT_MODEL)
    ap.add_argument('--max-steps', type=int, default=12)
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--stats-out', default='')
    args = ap.parse_args()

    res = run_task(Path(args.workspace), args.prompt, args.endpoint, args.model, args.max_steps, args.timeout)
    if args.stats_out:
        Path(args.stats_out).write_text(json.dumps(res['stats'], indent=2) + '\n')
    print(json.dumps(res, indent=2))


if __name__ == '__main__':
    main()
