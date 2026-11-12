"""Install or uninstall the tandem-mcp server in local MCP clients.

Supports Claude Code (`claude`), OpenAI Codex (`codex`), and Antigravity
(`~/.gemini/config/mcp_config.json`). Uses Python stdlib only.

Examples:
    python3 scripts/install.py
    python3 scripts/install.py --clients claude,codex,antigravity
    python3 scripts/install.py --replace-legacy --env TANDEM_SANDBOX=require
    python3 scripts/install.py --dry-run
    python3 scripts/install.py --uninstall
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_PY = ROOT / 'main.py'


def detect_python():
    for candidate in (ROOT / '.venv/bin/python', ROOT / '.venv/Scripts/python.exe'):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def parse_env_pairs(items):
    env = {}
    for item in items:
        if '=' not in item:
            raise ValueError(f'invalid --env value (expected KEY=VALUE): {item}')
        key, val = item.split('=', 1)
        key = key.strip()
        if not key:
            raise ValueError(f'empty env var name in: {item}')
        env[key] = val
    return env


def _run(cmd, dry_run=False):
    if dry_run:
        print('  [dry-run]', ' '.join(cmd))
        return 0, ''
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return done.returncode, (done.stdout + '\n' + done.stderr).strip()


def antigravity_config_path(home=None):
    base = Path(home) if home else Path.home()
    return base / '.gemini/config/mcp_config.json'


def install_antigravity(name, python_exe, main_py, env_vars, replace_legacy=False, dry_run=False, home=None):
    cfg_path = antigravity_config_path(home)
    if not cfg_path.parent.exists() and not (Path(home) / '.gemini' if home else Path.home() / '.gemini').exists():
        return 'skipped (Antigravity ~/.gemini directory not found)'
    data = {}
    if cfg_path.exists() and cfg_path.read_text().strip():
        data = json.loads(cfg_path.read_text())
    servers = data.setdefault('mcpServers', {})
    if replace_legacy and 'lmstudio' in servers and name != 'lmstudio':
        servers.pop('lmstudio', None)
    entry = {'command': str(python_exe), 'args': [str(main_py)]}
    if env_vars:
        entry['env'] = dict(env_vars)
    servers[name] = entry
    if dry_run:
        print(f'  [dry-run] write {cfg_path} -> mcpServers[{name!r}]')
        return f'would update {cfg_path}'
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg_path.with_name(cfg_path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(cfg_path)
    return f'installed in {cfg_path}'


def uninstall_antigravity(name, dry_run=False, home=None):
    cfg_path = antigravity_config_path(home)
    if not cfg_path.is_file():
        return 'not configured'
    data = json.loads(cfg_path.read_text() or '{}')
    servers = data.get('mcpServers') or {}
    if name not in servers:
        return 'not configured'
    if dry_run:
        print(f'  [dry-run] remove {name!r} from {cfg_path}')
        return f'would remove from {cfg_path}'
    servers.pop(name, None)
    tmp = cfg_path.with_name(cfg_path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(cfg_path)
    return f'removed from {cfg_path}'


def install_claude(name, python_exe, main_py, env_vars, replace_legacy=False, dry_run=False):
    exe = shutil.which('claude')
    if not exe:
        return 'skipped (`claude` CLI not found in PATH)'
    if replace_legacy and name != 'lmstudio':
        _run([exe, 'mcp', 'remove', 'lmstudio', '-s', 'user'], dry_run=dry_run)
    _run([exe, 'mcp', 'remove', name, '-s', 'user'], dry_run=dry_run)
    cmd = [exe, 'mcp', 'add', '-s', 'user']
    for k, v in env_vars.items():
        cmd += ['-e', f'{k}={v}']
    cmd += [name, '--', str(python_exe), str(main_py)]
    code, out = _run(cmd, dry_run=dry_run)
    if code != 0:
        return f'failed ({out[:160]})'
    return 'would install (user scope)' if dry_run else 'installed (user scope)'


def uninstall_claude(name, dry_run=False):
    exe = shutil.which('claude')
    if not exe:
        return 'skipped (`claude` CLI not found in PATH)'
    code, out = _run([exe, 'mcp', 'remove', name, '-s', 'user'], dry_run=dry_run)
    return 'would remove' if dry_run else ('removed' if code == 0 else f'not found ({out[:80]})')


def install_codex(name, python_exe, main_py, env_vars, replace_legacy=False, dry_run=False):
    exe = shutil.which('codex')
    if not exe:
        return 'skipped (`codex` CLI not found in PATH)'
    if replace_legacy and name != 'lmstudio':
        _run([exe, 'mcp', 'remove', 'lmstudio'], dry_run=dry_run)
    _run([exe, 'mcp', 'remove', name], dry_run=dry_run)
    cmd = [exe, 'mcp', 'add', name]
    for k, v in env_vars.items():
        cmd += ['--env', f'{k}={v}']
    cmd += ['--', str(python_exe), str(main_py)]
    code, out = _run(cmd, dry_run=dry_run)
    if code != 0:
        return f'failed ({out[:160]})'
    return 'would install' if dry_run else 'installed'


def uninstall_codex(name, dry_run=False):
    exe = shutil.which('codex')
    if not exe:
        return 'skipped (`codex` CLI not found in PATH)'
    code, out = _run([exe, 'mcp', 'remove', name], dry_run=dry_run)
    return 'would remove' if dry_run else ('removed' if code == 0 else f'not found ({out[:80]})')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Install or uninstall tandem-mcp in Claude Code, Codex, and Antigravity.')
    parser.add_argument('--clients', default='claude,codex,antigravity',
                        help='Comma-separated list of clients: claude, codex, antigravity (default: all)')
    parser.add_argument('--name', default='tandem-mcp', help='MCP server name (default: tandem-mcp)')
    parser.add_argument('--python', default='', help='Python executable to run main.py (default: .venv or current python)')
    parser.add_argument('--env', action='append', default=[], help='Environment variable KEY=VALUE (repeatable)')
    parser.add_argument('--replace-legacy', action='store_true', help='Also remove legacy "lmstudio" MCP entries')
    parser.add_argument('--uninstall', action='store_true', help='Remove the MCP server from selected clients')
    parser.add_argument('--dry-run', action='store_true', help='Show actions without modifying any configuration')
    args = parser.parse_args(argv)

    if not MAIN_PY.is_file():
        print(f'ERROR: {MAIN_PY} not found', file=sys.stderr)
        return 1

    python_exe = args.python or detect_python()
    env_vars = parse_env_pairs(args.env)
    clients = [c.strip().lower() for c in args.clients.split(',') if c.strip()]
    known = {'claude', 'codex', 'antigravity'}
    unknown = [c for c in clients if c not in known]
    if unknown:
        print(f'ERROR: unknown client(s): {", ".join(unknown)}', file=sys.stderr)
        return 1

    action = 'Uninstalling' if args.uninstall else 'Installing'
    print(f'{action} {args.name} ({python_exe} {MAIN_PY})')
    for client in clients:
        if args.uninstall:
            if client == 'claude':
                status = uninstall_claude(args.name, dry_run=args.dry_run)
            elif client == 'codex':
                status = uninstall_codex(args.name, dry_run=args.dry_run)
            else:
                status = uninstall_antigravity(args.name, dry_run=args.dry_run)
        else:
            if client == 'claude':
                status = install_claude(args.name, python_exe, MAIN_PY, env_vars, args.replace_legacy, args.dry_run)
            elif client == 'codex':
                status = install_codex(args.name, python_exe, MAIN_PY, env_vars, args.replace_legacy, args.dry_run)
            else:
                status = install_antigravity(args.name, python_exe, MAIN_PY, env_vars, args.replace_legacy, args.dry_run)
        print(f'  {client:12} {status}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
